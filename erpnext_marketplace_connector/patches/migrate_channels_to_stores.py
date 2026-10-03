import frappe
from frappe.utils.password import get_decrypted_password, set_encrypted_password

from erpnext_marketplace_connector.setup import ensure_sales_order_store_field

STORE_COPY_FIELDS = (
	"store_url",
	"store_id",
	"token_expires_at",
	"sync_status",
	"last_synced_orders",
	"last_synced_stock",
	"last_sync_error",
	"notes",
)


def execute():
	"""Channels used to be one-per-store. Make each existing channel the master of one store
	of the same name, so old `?channel=<name>` webhook URLs, item maps, logs and Sales
	Orders all keep pointing at the right store. Idempotent."""
	ensure_sales_order_store_field()

	for channel in frappe.get_all("Marketplace Channel", fields=["name", "platform", "enabled", *STORE_COPY_FIELDS]):
		if frappe.db.exists("Marketplace Store", channel.name):
			continue
		store = frappe.get_doc(
			{
				"doctype": "Marketplace Store",
				"store_name": channel.name,
				"marketplace_channel": channel.name,
				"platform": channel.platform,
				"enabled": channel.enabled,
				"status": "Active",
				**{f: channel.get(f) for f in STORE_COPY_FIELDS},
			}
		)
		store.flags.ignore_mandatory = True
		store.flags.ignore_validate = True
		store.insert(ignore_permissions=True)
		# Warehouse, price list, customer and tax template stay on the channel as the
		# defaults the store inherits.
		for fieldname in ("access_token", "refresh_token"):
			value = get_decrypted_password("Marketplace Channel", channel.name, fieldname, raise_exception=False)
			if value:
				set_encrypted_password("Marketplace Store", store.name, value, fieldname)
				store.db_set(fieldname, "*" * len(value), update_modified=False)

	# Same name as the channel they came from.
	for doctype in ("Marketplace Item Map", "Marketplace Webhook Log"):
		frappe.db.sql(
			f"update `tab{doctype}` set marketplace_store = marketplace_channel where ifnull(marketplace_store, '') = ''"
		)

	# The short-lived channel tag on Sales Orders (never released) becomes the store tag.
	if frappe.db.has_column("Sales Order", "marketplace_channel"):
		frappe.db.sql(
			"update `tabSales Order` set marketplace_store = marketplace_channel "
			"where ifnull(marketplace_store, '') = '' and ifnull(marketplace_channel, '') != ''"
		)
		if frappe.db.exists("Custom Field", "Sales Order-marketplace_channel"):
			frappe.delete_doc("Custom Field", "Sales Order-marketplace_channel", force=True, ignore_missing=True)

	# Orders created before any tag: attribute them from the webhook log that created them.
	for log in frappe.get_all(
		"Marketplace Webhook Log",
		filters={"sales_order": ["is", "set"], "marketplace_store": ["is", "set"]},
		fields=["sales_order", "marketplace_store"],
	):
		if frappe.db.exists("Sales Order", log.sales_order):
			frappe.db.set_value("Sales Order", log.sales_order, "marketplace_store", log.marketplace_store, update_modified=False)
