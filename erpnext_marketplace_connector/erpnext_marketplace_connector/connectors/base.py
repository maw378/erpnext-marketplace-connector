import json

import frappe
from frappe.model.document import Document


class BaseConnector:
	"""Interface every platform connector (Shopify, WooCommerce, Salla, Zid, ...) implements.

	A connector is constructed from a Marketplace Store document. `self.channel` is its
	Marketplace Channel (the platform account: client ID/secret, webhook secret,
	connector settings) and `self.store` is the store itself (OAuth tokens, sync
	state). Dev and production stores are just different Marketplace Store records
	using the same connector code.
	"""

	def __init__(self, store: Document):
		self.store = store
		self.channel = store.channel_doc()

	def get_setting(self, key: str, default=None):
		"""Read a platform-specific value from the channel's free-form Connector Settings JSON."""
		if not self.channel.connector_settings:
			return default
		try:
			settings = json.loads(self.channel.connector_settings)
		except ValueError:
			return default
		return settings.get(key, default)

	def save_tokens(self, access_token: str, refresh_token: str | None, expires_in: int | None) -> None:
		"""Persist OAuth tokens onto the store, without a full document save/validate cycle.

		Password fields are only encrypted (into the __Auth table) as a side
		effect of Document._save_passwords(), which plain db_set() never runs -
		db_set() alone would silently write the token as plaintext into the
		Marketplace Store table. So encrypt explicitly here and only leave
		the masked dummy value in the doc's own column, matching what a normal
		doc.save() from the Desk form does for api_secret/webhook_secret.
		"""
		from frappe.utils.password import set_encrypted_password

		set_encrypted_password(self.store.doctype, self.store.name, access_token, "access_token")
		self.store.db_set("access_token", "*" * len(access_token), update_modified=False)

		if refresh_token:
			set_encrypted_password(self.store.doctype, self.store.name, refresh_token, "refresh_token")
			self.store.db_set("refresh_token", "*" * len(refresh_token), update_modified=False)

		if expires_in:
			expires_at = frappe.utils.add_to_date(frappe.utils.now_datetime(), seconds=expires_in)
			self.store.db_set("token_expires_at", expires_at, update_modified=False)

		frappe.db.commit()

	def record_sync_error(self, message: str) -> None:
		self.store.db_set("sync_status", "Error", update_modified=False)
		self.store.db_set("last_sync_error", message, update_modified=False)
		frappe.db.commit()

	def fetch_new_orders(self) -> list[dict]:
		"""Return orders created/updated on the channel since the last sync."""
		raise NotImplementedError

	def push_stock_levels(self, item_code_to_qty: dict[str, float]) -> None:
		"""Push available quantities (keyed by Item Code) to the channel."""
		raise NotImplementedError

	def push_prices(self, item_code_to_rate: dict[str, float]) -> None:
		"""Push prices (keyed by Item Code) to the channel."""
		raise NotImplementedError

	def verify_webhook_signature(self, request_body: bytes, signature_header: str) -> bool:
		"""Validate an inbound webhook against this channel's webhook secret."""
		raise NotImplementedError

	def fetch_store_id(self) -> str | None:
		"""Return the platform's id for the store these credentials belong to, if it has one."""
		return None

	def fetch_catalog(self) -> list[dict]:
		"""Return every sellable variant on the channel as dicts with keys:
		product_id, variant_id, sku, name, price, stock_qty (None = unlimited/unknown)."""
		raise NotImplementedError

	def fetch_order_items(self, order_id) -> list[dict]:
		"""Return the line items of one order, when a webhook payload doesn't include them."""
		raise NotImplementedError

	def register_webhooks(self, url: str, events: list[str]) -> dict:
		"""Subscribe the platform to call `url` for `events`.

		Returns {"registered": events newly subscribed, "removed": events whose older
		subscription to the same endpoint was deleted}."""
		raise NotImplementedError
