import json

import frappe


def process_webhook_log(log_name: str) -> None:
	"""Turn one logged, signature-verified webhook into ERPNext changes (background job)."""
	# The webhook endpoint is allow_guest, so the queued job inherits the Guest user,
	# which can't read Items/Customers. The signature was already verified before
	# this job was enqueued, so run the ERPNext side as Administrator.
	frappe.set_user("Administrator")
	log = frappe.get_doc("Marketplace Webhook Log", log_name)
	if log.processed or not log.signature_valid:
		return

	try:
		payload = json.loads(log.payload or "{}")
		event = payload.get("event") or log.event or ""
		if event.startswith("order."):
			_process_order_event(log, event, payload.get("data") or {})
		else:
			log.db_set("error", f"Event {event or '(none)'} is logged but not handled.")
			return
	except Exception as e:
		frappe.db.rollback()
		log.db_set("error", str(e)[:500])
		frappe.log_error(title=f"Marketplace webhook {log_name} failed")
		frappe.db.commit()
		return

	log.db_set("processed", 1)
	frappe.db.commit()


def _process_order_event(log, event: str, order: dict) -> None:
	from .connectors import get_connector

	channel = frappe.get_doc("Marketplace Channel", log.marketplace_channel)
	reference = str(order.get("reference_id") or order.get("id") or "")
	if not reference:
		frappe.throw("Order payload has neither reference_id nor id")
	log.db_set("order_reference", reference)
	# Channel name, not just platform: ERPNext rejects two Sales Orders with the same
	# customer + PO number, and two stores can share an order number and a default
	# customer. `legacy_po_no` is the format used before multi-store support.
	po_no = f"{channel.name}-{reference}"
	legacy_po_no = f"{channel.platform}-{reference}"

	status_slug = ((order.get("status") or {}).get("slug") or "").lower()
	# Per channel, so two stores that share an order number stay separate.
	# Untagged orders (the patch tags them from their webhook logs; this covers any it
	# could not) are only attributed to a channel when the site has a single one.
	only_channel = frappe.db.count("Marketplace Channel", {"platform": channel.platform}) == 1
	existing = frappe.db.get_value(
		"Sales Order",
		{
			"po_no": ["in", [po_no, legacy_po_no]],
			"docstatus": ["<", 2],
			"marketplace_channel": ["in", [channel.name, ""] if only_channel else [channel.name]],
		},
		"name",
	)

	if event == "order.cancelled" or status_slug in ("canceled", "cancelled"):
		if existing:
			so = frappe.get_doc("Sales Order", existing)
			if so.docstatus == 1:
				so.cancel()
			else:
				# A draft can't be cancelled, only deleted - and not while logs link to it.
				# The logs keep the order reference, so the history stays traceable.
				frappe.db.set_value("Marketplace Webhook Log", {"sales_order": existing}, "sales_order", None)
				frappe.delete_doc("Sales Order", existing)
				return
			log.db_set("sales_order", existing)
		return

	if existing:
		so = frappe.get_doc("Sales Order", existing)
		so.add_comment("Comment", f"Salla order updated: status {status_slug or '-'}")
		log.db_set("sales_order", existing)
		return

	items = order.get("items")
	if not items:
		items = get_connector(channel).fetch_order_items(order.get("id"))
	so = _create_sales_order(channel, order, items, po_no)
	log.db_set("sales_order", so.name)


def _resolve_item(channel_name: str, line: dict) -> str | None:
	"""Match a Salla order line to an ERPNext Item via Marketplace Item Map."""
	variant_id = line.get("product_sku_id") or line.get("variant_id")
	product_id = line.get("product_id") or (line.get("product") or {}).get("id")
	base = {"marketplace_channel": channel_name, "enabled": 1}
	if variant_id:
		hit = frappe.db.get_value("Marketplace Item Map", {**base, "channel_variant_id": str(variant_id)}, "item_code")
		if hit:
			return hit
	if product_id:
		# Only safe when the product has no variants mapped (one map row per product).
		rows = frappe.get_all("Marketplace Item Map", filters={**base, "channel_product_id": str(product_id)}, pluck="item_code")
		if len(rows) == 1:
			return rows[0]
	# Simple (variant-less) products arrive with only the SKU on the line.
	sku = line.get("sku")
	if sku:
		return frappe.db.get_value("Marketplace Item Map", {**base, "channel_sku": sku}, "item_code")
	return None


def _amount(value) -> float:
	if isinstance(value, dict):
		value = value.get("amount")
	return float(value or 0)


def _create_sales_order(channel, order: dict, items: list[dict], po_no: str):
	if not channel.default_customer:
		frappe.throw(f"Set Default Customer on Marketplace Channel {channel.name}")

	lines, unmapped = [], []
	for line in items:
		item_code = _resolve_item(channel.name, line)
		if not item_code:
			unmapped.append(f"{line.get('sku') or line.get('name')} (product {line.get('product_id')}, variant {line.get('product_sku_id')})")
			continue
		lines.append(
			{
				"item_code": item_code,
				"qty": line.get("quantity") or 1,
				"rate": _amount((line.get("amounts") or {}).get("price_without_tax")),
				"warehouse": channel.warehouse,
			}
		)
	if unmapped:
		frappe.throw("No Marketplace Item Map for: " + "; ".join(unmapped))

	company = frappe.db.get_value("Warehouse", channel.warehouse, "company") if channel.warehouse else None
	so = frappe.get_doc(
		{
			"doctype": "Sales Order",
			"company": company,
			"customer": channel.default_customer,
			"po_no": po_no,
			"marketplace_channel": channel.name,
			"transaction_date": frappe.utils.today(),
			"delivery_date": frappe.utils.today(),
			"selling_price_list": channel.price_list or None,
			"items": lines,
		}
	)
	# A tax template only applies to its own company; never attach a mismatched one.
	if channel.tax_template and frappe.db.get_value("Sales Taxes and Charges Template", channel.tax_template, "company") == so.company:
		so.taxes_and_charges = channel.tax_template
		so.set_taxes()
	so.insert(ignore_permissions=True)

	buyer = order.get("customer") or {}
	so.add_comment(
		"Comment",
		f"Salla order {order.get('reference_id')} - buyer {buyer.get('full_name') or '-'}, "
		f"{buyer.get('mobile_code') or ''}{buyer.get('mobile') or ''}, payment {order.get('payment_method') or '-'}",
	)
	from .connectors import get_connector

	if get_connector(channel).get_setting("auto_submit_sales_orders", False):
		so.submit()
	return so
