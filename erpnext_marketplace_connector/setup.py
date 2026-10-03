import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def ensure_sales_order_store_field() -> None:
	"""Tag each Sales Order with the Marketplace Store it came from.

	Lets several stores share one site: duplicate detection is per store, and the
	field doubles as a list filter/report column. Idempotent.
	"""
	create_custom_fields(
		{
			"Sales Order": [
				{
					"fieldname": "marketplace_store",
					"fieldtype": "Link",
					"options": "Marketplace Store",
					"label": "Marketplace Store",
					"insert_after": "po_no",
					"read_only": 1,
					"allow_on_submit": 1,
					"in_standard_filter": 1,
					"no_copy": 1,
				}
			]
		}
	)


def after_install() -> None:
	ensure_sales_order_store_field()
