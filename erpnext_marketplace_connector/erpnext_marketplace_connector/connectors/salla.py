import hashlib
import hmac

import frappe
import requests

from .base import BaseConnector

API_BASE_URL = "https://api.salla.dev/admin/v2"
TOKEN_URL = "https://accounts.salla.sa/oauth2/token"
AUTHORIZE_URL = "https://accounts.salla.sa/oauth2/auth"
REQUEST_TIMEOUT = 30


class SallaConnector(BaseConnector):
	"""Salla Open API connector (https://docs.salla.dev).

	Auth is OAuth2 against accounts.salla.sa: access tokens last 14 days,
	refresh tokens are single-use and last 1 month, so every refresh must
	persist the *new* refresh token Salla hands back, not just the access
	token. Works identically for the dev/demo store and a real production
	store - only the credentials stored on the Marketplace Channel differ.
	"""

	@staticmethod
	def get_authorize_url(client_id: str, redirect_uri: str, state: str) -> str:
		from urllib.parse import urlencode

		params = {
			"client_id": client_id,
			"response_type": "code",
			"redirect_uri": redirect_uri,
			"scope": "offline_access",
			"state": state,
		}
		return f"{AUTHORIZE_URL}?{urlencode(params)}"

	def exchange_code_for_token(self, code: str, redirect_uri: str) -> None:
		response = requests.post(
			TOKEN_URL,
			data={
				"client_id": self.channel.api_key,
				"client_secret": self.channel.get_password("api_secret", raise_exception=False),
				"grant_type": "authorization_code",
				"code": code,
				"redirect_uri": redirect_uri,
			},
			timeout=REQUEST_TIMEOUT,
		)
		response.raise_for_status()
		data = response.json()
		self.save_tokens(data["access_token"], data.get("refresh_token"), data.get("expires_in"))

	def refresh_access_token(self) -> None:
		refresh_token = self.store.get_password("refresh_token", raise_exception=False)
		if not refresh_token:
			frappe.throw(
				f"Marketplace Store {self.store.name} has no refresh token yet - "
				"use the Connect to Salla button to complete the OAuth authorization flow first."
			)
		response = requests.post(
			TOKEN_URL,
			data={
				"client_id": self.channel.api_key,
				"client_secret": self.channel.get_password("api_secret", raise_exception=False),
				"grant_type": "refresh_token",
				"refresh_token": refresh_token,
			},
			timeout=REQUEST_TIMEOUT,
		)
		response.raise_for_status()
		data = response.json()
		self.save_tokens(data["access_token"], data.get("refresh_token"), data.get("expires_in"))

	def get_access_token(self) -> str:
		expires_at = self.store.token_expires_at
		current_token = self.store.get_password("access_token", raise_exception=False)
		token_missing_or_stale = (
			not current_token
			or not expires_at
			or frappe.utils.now_datetime() >= frappe.utils.get_datetime(expires_at)
		)
		if token_missing_or_stale:
			self.refresh_access_token()
			current_token = self.store.get_password("access_token", raise_exception=False)
		return current_token

	def _headers(self) -> dict:
		return {"Authorization": f"Bearer {self.get_access_token()}"}

	def fetch_new_orders(self) -> list[dict]:
		"""Pull orders via GET /orders.

		Salla's orders endpoint only supports from_date/to_date (creation date),
		not an updated-since filter - see docs.salla.dev. Treat this as a coarse
		backstop; order.created/order.updated webhooks are the primary sync path.
		"""
		params = {"per_page": 60}
		if self.store.last_synced_orders:
			params["from_date"] = frappe.utils.get_datetime(self.store.last_synced_orders).strftime("%Y-%m-%d")

		orders = []
		page = 1
		while True:
			response = requests.get(
				f"{API_BASE_URL}/orders",
				headers=self._headers(),
				params={**params, "page": page},
				timeout=REQUEST_TIMEOUT,
			)
			response.raise_for_status()
			body = response.json()
			orders.extend(body.get("data", []))
			pagination = body.get("pagination") or {}
			total_pages = pagination.get("totalPages", page)
			if page >= total_pages:
				break
			page += 1

		self.store.db_set("last_synced_orders", frappe.utils.now_datetime(), update_modified=False)
		frappe.db.commit()
		return orders

	def push_stock_levels(self, item_code_to_qty: dict[str, float]) -> None:
		"""Bulk-overwrite quantities via POST /products/quantities/bulk.

		Salla identifies products by their own numeric id/variant_id, not by our
		Item Code, so this only touches items that already have a Marketplace
		Item Map row recording that id. Map new items there first.
		"""
		branch_id = self.get_setting("branch_id")
		item_maps = frappe.get_all(
			"Marketplace Item Map",
			filters={
				"marketplace_store": self.store.name,
				"item_code": ["in", list(item_code_to_qty)],
				"enabled": 1,
			},
			fields=["item_code", "channel_product_id", "channel_variant_id"],
		)

		products = []
		for item_map in item_maps:
			qty = item_code_to_qty.get(item_map.item_code)
			identifier = item_map.channel_variant_id or item_map.channel_product_id
			if qty is None or not identifier:
				continue
			entry = {
				"identifer_type": "variant_id" if item_map.channel_variant_id else "id",
				"identifer": identifier,
				"quantity": qty,
				"mode": "overwrite",
			}
			if branch_id:
				entry["branch"] = branch_id
			products.append(entry)

		if not products:
			return

		response = requests.post(
			f"{API_BASE_URL}/products/quantities/bulk",
			headers=self._headers(),
			json={"products": products},
			timeout=REQUEST_TIMEOUT,
		)
		response.raise_for_status()
		self.store.db_set("last_synced_stock", frappe.utils.now_datetime(), update_modified=False)
		frappe.db.commit()

	def push_prices(self, item_code_to_rate: dict[str, float]) -> None:
		"""Push prices via POST /products/sku/{sku}/price.

		NOTE: available docs describe this endpoint but not its exact body shape
		for certain; this assumes {"price": <number>}. Verify against a real
		response the first time this runs against a live store, since Salla's
		money fields elsewhere (e.g. order totals) are {amount, currency}
		objects rather than a flat number.
		"""
		item_maps = frappe.get_all(
			"Marketplace Item Map",
			filters={
				"marketplace_store": self.store.name,
				"item_code": ["in", list(item_code_to_rate)],
				"enabled": 1,
			},
			fields=["item_code", "channel_sku"],
		)
		for item_map in item_maps:
			rate = item_code_to_rate.get(item_map.item_code)
			if rate is None or not item_map.channel_sku:
				continue
			response = requests.post(
				f"{API_BASE_URL}/products/sku/{item_map.channel_sku}/price",
				headers=self._headers(),
				json={"price": rate},
				timeout=REQUEST_TIMEOUT,
			)
			response.raise_for_status()

	def verify_webhook_signature(self, request_body: bytes, signature_header: str) -> bool:
		"""Salla signs webhooks with HMAC-SHA256(webhook_secret, raw_body), hex-encoded,
		sent in the X-Salla-Signature header. See docs.salla.dev/docs/back-end/webhooks.
		"""
		secret = self.channel.get_password("webhook_secret", raise_exception=False)
		if not secret or not signature_header:
			return False
		expected = hmac.new(secret.encode(), request_body, hashlib.sha256).hexdigest()
		return hmac.compare_digest(expected, signature_header)

	def fetch_store_id(self) -> str | None:
		response = requests.get(f"{API_BASE_URL}/store/info", headers=self._headers(), timeout=REQUEST_TIMEOUT)
		response.raise_for_status()
		store_id = (response.json().get("data") or {}).get("id")
		return str(store_id) if store_id else None

	def fetch_catalog(self) -> list[dict]:
		"""Walk GET /products (paginated); each product's `skus` are its variants."""
		variants = []
		page = 1
		while True:
			response = requests.get(
				f"{API_BASE_URL}/products",
				headers=self._headers(),
				params={"per_page": 50, "page": page},
				timeout=REQUEST_TIMEOUT,
			)
			response.raise_for_status()
			body = response.json()
			for product in body.get("data", []):
				option_values = {
					value["id"]: value.get("name")
					for option in product.get("options") or []
					for value in option.get("values") or []
				}
				skus = product.get("skus") or []
				for sku in skus:
					labels = [option_values.get(v) for v in sku.get("related_option_values") or []]
					name = " - ".join([product.get("name") or "", *[label for label in labels if label]])
					variants.append(
						{
							"product_id": product["id"],
							"variant_id": sku["id"],
							"sku": sku.get("sku") or product.get("sku"),
							"name": name,
							"price": float((sku.get("price") or {}).get("amount") or 0),
							"stock_qty": None if sku.get("unlimited_quantity") else sku.get("stock_quantity"),
						}
					)
			pagination = body.get("pagination") or {}
			if page >= (pagination.get("totalPages") or 1):
				return variants
			page += 1

	def fetch_order_items(self, order_id) -> list[dict]:
		"""Webhook payloads normally carry items; fall back to GET /orders/items if not."""
		response = requests.get(
			f"{API_BASE_URL}/orders/items",
			headers=self._headers(),
			params={"order_id": order_id},
			timeout=REQUEST_TIMEOUT,
		)
		response.raise_for_status()
		return response.json().get("data", [])

	def register_webhooks(self, url: str, events: list[str]) -> dict:
		"""Subscribe `url` to `events`, skipping ones already subscribed to this url.

		Returns {"registered": [...events newly subscribed], "removed": [...events whose
		older subscription to this same endpoint, e.g. the `?channel=` form, was deleted]}.

		Uses Salla's signature strategy so deliveries carry X-Salla-Signature, which is
		HMAC-SHA256(webhook_secret, raw_body) - exactly what verify_webhook_signature checks.
		"""
		secret = self.channel.get_password("webhook_secret", raise_exception=False)
		if not secret:
			frappe.throw(f"Set a Webhook Secret on Marketplace Channel {self.channel.name} first.")

		existing = requests.get(f"{API_BASE_URL}/webhooks", headers=self._headers(), timeout=REQUEST_TIMEOUT)
		existing.raise_for_status()
		subscriptions = existing.json().get("data", [])
		already = {(w.get("event"), w.get("url")) for w in subscriptions}

		registered = []
		for event in events:
			if (event, url) in already:
				continue
			response = requests.post(
				f"{API_BASE_URL}/webhooks/subscribe",
				headers=self._headers(),
				json={
					"name": f"ERPNext {event}",
					"event": event,
					"url": url,
					"version": 2,
					"security_strategy": "signature",
					"secret": secret,
				},
				timeout=REQUEST_TIMEOUT,
			)
			if not response.ok:
				frappe.throw(f"Salla rejected webhook {event}: {response.status_code} {response.text[:300]}")
			registered.append(event)

		# Older subscriptions to this same endpoint (same URL without/with a different query
		# string) would deliver every event twice. Only this site's own endpoint is touched.
		endpoint = url.split("?")[0]
		removed = []
		for w in subscriptions:
			if w.get("event") in events and (w.get("url") or "").split("?")[0] == endpoint and w.get("url") != url:
				response = requests.delete(f"{API_BASE_URL}/webhooks/{w['id']}", headers=self._headers(), timeout=REQUEST_TIMEOUT)
				if response.ok:
					removed.append(w["event"])
		return {"registered": registered, "removed": removed}
