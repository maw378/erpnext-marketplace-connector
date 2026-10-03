import json

import frappe

from .connectors import get_connector

API = "erpnext_marketplace_connector.erpnext_marketplace_connector.api"
WEBHOOK_EVENTS = ["order.created", "order.updated", "order.cancelled"]
DEFAULT_PLATFORM = "Salla"


def store_matches(store, payload: dict) -> bool:
	"""A store that knows its store id only accepts webhooks from that store.

	Salla puts the store id in `merchant`. Stores without a store id (not connected yet,
	or platforms without one) accept everything.
	"""
	if not store.get("store_id") or "merchant" not in payload:
		return True
	return str(payload["merchant"]) == str(store.store_id)


def resolve_store(payload: dict, legacy_name: str | None = None, platform: str = DEFAULT_PLATFORM) -> str | None:
	"""Find the Marketplace Store an inbound webhook belongs to.

	The payload's store id (`merchant` for Salla) decides, so one URL serves every store.
	`legacy_name` is the old `?channel=<name>` form that earlier registrations used: it
	still works, naming either a store or a channel that has exactly one store.
	"""
	merchant = payload.get("merchant")
	if merchant not in (None, ""):
		name = frappe.db.get_value(
			"Marketplace Store", {"store_id": str(merchant), "platform": platform, "enabled": 1}, "name"
		)
		if name:
			return name
	if legacy_name:
		if frappe.db.exists("Marketplace Store", {"name": legacy_name, "enabled": 1}):
			return legacy_name
		stores = frappe.get_all("Marketplace Store", {"marketplace_channel": legacy_name, "enabled": 1}, pluck="name")
		if len(stores) == 1:
			return stores[0]
	return None


def _get_store(store_name: str):
	if not frappe.db.exists("Marketplace Store", store_name):
		frappe.throw(f"No Marketplace Store named {store_name}", frappe.DoesNotExistError)
	return frappe.get_doc("Marketplace Store", store_name)


def _platform(store) -> str:
	return frappe.db.get_value("Marketplace Channel", store.marketplace_channel, "platform")


@frappe.whitelist()
def oauth_redirect(store: str):
	"""Send the browser to the platform's OAuth authorize page for this store.

	Used by the "Connect" button on the Marketplace Store form. The client ID/secret
	come from the store's Marketplace Channel. Only Salla implements OAuth so far.
	"""
	doc = _get_store(store)
	frappe.only_for("System Manager")

	if _platform(doc) != "Salla":
		frappe.throw(f"OAuth connect isn't implemented for {_platform(doc)} yet.")

	connector = get_connector(doc)
	redirect_uri = frappe.utils.get_url(f"/api/method/{API}.oauth_callback")
	authorize_url = connector.get_authorize_url(connector.channel.api_key, redirect_uri, state=doc.name)

	frappe.local.response["type"] = "redirect"
	frappe.local.response["location"] = authorize_url


@frappe.whitelist()
def oauth_callback(code: str | None = None, state: str | None = None, error: str | None = None):
	"""Receives the redirect back from the platform's OAuth consent screen.

	`state` carries the Marketplace Store name we sent in oauth_redirect.
	This is a simplification appropriate for a small number of internally
	managed stores (not a public multi-tenant app listing) - it relies on
	the operator already being logged in as System Manager rather than a
	dedicated CSRF nonce.
	"""
	frappe.only_for("System Manager")

	store_form_url = frappe.utils.get_url(f"/app/marketplace-store/{state}" if state else "/app/marketplace-store")

	if error or not code or not state:
		frappe.local.response["type"] = "redirect"
		frappe.local.response["location"] = f"{store_form_url}?oauth_error={error or 'missing_code'}"
		return

	doc = _get_store(state)
	connector = get_connector(doc)
	redirect_uri = frappe.utils.get_url(f"/api/method/{API}.oauth_callback")
	connector.exchange_code_for_token(code, redirect_uri)
	try:
		store_id = connector.fetch_store_id()
		if store_id:
			doc.db_set("store_id", store_id, update_modified=False)
	except Exception:
		# Connecting still succeeds; without a store id webhooks cannot be routed to this
		# store by id (use Refresh Store ID once the token works).
		frappe.log_error(title=f"Could not read store id for {doc.name}")
	doc.db_set("sync_status", "Idle", update_modified=False)
	doc.db_set("last_sync_error", "", update_modified=False)

	frappe.local.response["type"] = "redirect"
	frappe.local.response["location"] = f"{store_form_url}?oauth_connected=1"


@frappe.whitelist()
def refresh_store_id(store: str):
	"""Re-read the store id from the platform with the store's current token."""
	frappe.only_for("System Manager")
	doc = _get_store(store)
	store_id = get_connector(doc).fetch_store_id()
	if not store_id:
		frappe.throw("The platform did not return a store id for this token.")
	doc.db_set("store_id", store_id, update_modified=False)
	return {"store_id": store_id}


@frappe.whitelist(allow_guest=True)
def webhook(channel: str | None = None, store: str | None = None):
	"""Inbound webhook receiver for every store of every platform on this site.

	One URL for all of them: .../api/method/<this module>.webhook
	The store is identified from the payload (`merchant` for Salla), the payload is
	verified with that store's channel's webhook secret, logged to Marketplace Webhook
	Log, and valid events are handed to a background job (orders.process_webhook_log).

	`?channel=<name>` / `?store=<name>` still work for webhooks registered the old way.
	"""
	request_body = frappe.request.get_data()
	try:
		payload = json.loads(request_body or "{}")
	except ValueError:
		payload = {}
	if not isinstance(payload, dict):
		payload = {}

	# For JSON deliveries Frappe fills form_dict from the body only, so a name in the
	# URL's query string has to be read from the request itself.
	legacy_name = channel or store or frappe.request.args.get("channel") or frappe.request.args.get("store")
	platform = frappe.request.args.get("platform") or DEFAULT_PLATFORM
	store_name = resolve_store(payload, legacy_name, platform)
	if not store_name:
		frappe.local.response["http_status_code"] = 404
		return {"ok": False, "error": "unknown store"}

	doc = _get_store(store_name)
	connector = get_connector(doc)
	signature_header = frappe.get_request_header("X-Salla-Signature") or frappe.get_request_header("X-Signature")
	is_valid = connector.verify_webhook_signature(request_body, signature_header or "")

	log = frappe.get_doc(
		{
			"doctype": "Marketplace Webhook Log",
			"marketplace_store": doc.name,
			"marketplace_channel": doc.marketplace_channel,
			"event": payload.get("event", ""),
			"signature_valid": 1 if is_valid else 0,
			"payload": frappe.as_json(payload),
		}
	)
	log.insert(ignore_permissions=True)
	frappe.db.commit()

	if is_valid and not store_matches(doc, payload):
		log.db_set("error", f"Ignored: webhook is from store {payload.get('merchant')}, {doc.name} is store {doc.store_id}.")
		frappe.db.commit()
		return {"ok": True, "ignored": "store mismatch"}

	if is_valid:
		frappe.enqueue(
			"erpnext_marketplace_connector.erpnext_marketplace_connector.orders.process_webhook_log",
			queue="short",
			log_name=log.name,
			enqueue_after_commit=True,
		)

	if not is_valid:
		frappe.local.response["http_status_code"] = 401
		return {"ok": False, "error": "invalid signature"}

	return {"ok": True}


@frappe.whitelist()
def register_webhooks(store: str):
	"""Subscribe the platform to order events, delivering to this site's one webhook URL."""
	frappe.only_for("System Manager")
	doc = _get_store(store)
	url = frappe.utils.get_url(f"/api/method/{API}.webhook")
	result = get_connector(doc).register_webhooks(url, WEBHOOK_EVENTS)
	return {"url": url, **result}


@frappe.whitelist()
def import_products(store: str):
	"""Create ERPNext Items + Marketplace Item Map rows for the store's catalog."""
	frappe.only_for("System Manager")
	from .catalog import import_products as run

	return run(store)
