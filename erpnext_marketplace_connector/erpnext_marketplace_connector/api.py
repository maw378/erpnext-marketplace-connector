import json
from urllib.parse import urlencode

import frappe

from .connectors import get_connector


def _get_channel(channel_name: str):
	if not frappe.db.exists("Marketplace Channel", channel_name):
		frappe.throw(f"No Marketplace Channel named {channel_name}", frappe.DoesNotExistError)
	return frappe.get_doc("Marketplace Channel", channel_name)


@frappe.whitelist()
def oauth_redirect(channel: str):
	"""Send the browser to the platform's OAuth authorize page for this channel.

	Used by the "Connect" button on the Marketplace Channel form. Only Salla
	implements OAuth so far; other platforms can add their own authorize URL
	builder the same way once their connector needs one.
	"""
	doc = _get_channel(channel)
	frappe.only_for("System Manager")

	if doc.platform != "Salla":
		frappe.throw(f"OAuth connect isn't implemented for {doc.platform} yet.")

	connector = get_connector(doc)
	redirect_uri = frappe.utils.get_url(
		"/api/method/erpnext_marketplace_connector.erpnext_marketplace_connector.api.oauth_callback"
	)
	authorize_url = connector.get_authorize_url(doc.api_key, redirect_uri, state=doc.name)

	frappe.local.response["type"] = "redirect"
	frappe.local.response["location"] = authorize_url


@frappe.whitelist()
def oauth_callback(code: str | None = None, state: str | None = None, error: str | None = None):
	"""Receives the redirect back from the platform's OAuth consent screen.

	`state` carries the Marketplace Channel name we sent in oauth_redirect.
	This is a simplification appropriate for a small number of internally
	managed channels (not a public multi-tenant app listing) - it relies on
	the operator already being logged in as System Manager rather than a
	dedicated CSRF nonce.
	"""
	frappe.only_for("System Manager")

	channel_form_url = frappe.utils.get_url(f"/app/marketplace-channel/{state}" if state else "/app/marketplace-channel")

	if error or not code or not state:
		frappe.local.response["type"] = "redirect"
		frappe.local.response["location"] = f"{channel_form_url}?oauth_error={error or 'missing_code'}"
		return

	doc = _get_channel(state)
	connector = get_connector(doc)
	redirect_uri = frappe.utils.get_url(
		"/api/method/erpnext_marketplace_connector.erpnext_marketplace_connector.api.oauth_callback"
	)
	connector.exchange_code_for_token(code, redirect_uri)
	doc.db_set("sync_status", "Idle", update_modified=False)
	doc.db_set("last_sync_error", "", update_modified=False)

	frappe.local.response["type"] = "redirect"
	frappe.local.response["location"] = f"{channel_form_url}?oauth_connected=1"


@frappe.whitelist(allow_guest=True)
def webhook(channel: str | None = None):
	"""Generic inbound webhook receiver, shared by every platform.

	Each Marketplace Channel gets its own webhook URL by putting its name in
	the `channel` query param, e.g.:
	.../api/method/erpnext_marketplace_connector.erpnext_marketplace_connector.api.webhook?channel=Salla+Main-Store

	Verifies the signature using that channel's webhook secret and logs the event
	to Marketplace Webhook Log. Valid events are then handed to a background job
	(orders.process_webhook_log) that creates/updates the ERPNext documents.
	"""
	# For JSON deliveries Frappe fills form_dict from the body only, so the channel
	# name in the URL's query string has to be read from the request itself.
	channel = channel or frappe.request.args.get("channel")
	if not channel:
		frappe.throw("Missing channel", frappe.ValidationError)
	doc = _get_channel(channel)
	connector = get_connector(doc)

	request_body = frappe.request.get_data()
	signature_header = frappe.get_request_header("X-Salla-Signature") or frappe.get_request_header("X-Signature")
	is_valid = connector.verify_webhook_signature(request_body, signature_header or "")

	try:
		payload = json.loads(request_body or "{}")
	except ValueError:
		payload = {}

	log = frappe.get_doc(
		{
			"doctype": "Marketplace Webhook Log",
			"marketplace_channel": doc.name,
			"event": payload.get("event", ""),
			"signature_valid": 1 if is_valid else 0,
			"payload": frappe.as_json(payload),
		}
	)
	log.insert(ignore_permissions=True)
	frappe.db.commit()

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
def register_webhooks(channel: str):
	"""Subscribe the platform to order events, delivering to this site's webhook URL."""
	frappe.only_for("System Manager")
	doc = _get_channel(channel)
	url = frappe.utils.get_url(
		"/api/method/erpnext_marketplace_connector.erpnext_marketplace_connector.api.webhook"
	) + "?" + urlencode({"channel": doc.name})
	registered = get_connector(doc).register_webhooks(url, ["order.created", "order.updated", "order.cancelled"])
	return {"url": url, "registered": registered}
