import frappe

from erpnext_marketplace_connector.setup import ensure_sales_order_channel_field


def execute():
	ensure_sales_order_channel_field()

	# Tag Sales Orders created before multi-store support with the channel whose webhook
	# log created them, so they keep matching their own channel's later updates.
	logs = frappe.get_all(
		"Marketplace Webhook Log",
		filters={"sales_order": ["is", "set"]},
		fields=["sales_order", "marketplace_channel"],
	)
	for log in logs:
		if frappe.db.exists("Sales Order", log.sales_order):
			frappe.db.set_value("Sales Order", log.sales_order, "marketplace_channel", log.marketplace_channel, update_modified=False)
