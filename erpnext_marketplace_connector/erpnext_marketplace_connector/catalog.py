import frappe

from .connectors import get_connector

ITEM_GROUP = "Salla Products"


def import_products(store_name: str) -> dict:
	"""Pull the store's catalog and create an Item + Marketplace Item Map per variant.

	Safe to re-run: variants that already have a map row are skipped. Stock is not
	touched - post opening stock separately if the ERPNext side should track it.
	Also runnable from a bench console / `bench execute` (see README of the deploy).
	"""
	store = frappe.get_doc("Marketplace Store", store_name)
	variants = get_connector(store).fetch_catalog()
	_ensure_item_group()

	mapped = set(
		frappe.get_all("Marketplace Item Map", {"marketplace_store": store.name}, pluck="channel_variant_id")
	)
	sku_count = {}
	for variant in variants:
		sku_count[variant["sku"]] = sku_count.get(variant["sku"], 0) + 1
	items_created = maps_created = skipped = 0

	for variant in variants:
		variant_id = str(variant["variant_id"])
		if variant_id in mapped:
			skipped += 1
			continue

		# Salla variants often carry no SKU of their own and inherit the product's, so a
		# shared SKU is made unique per variant with the variant id.
		sku = variant["sku"]
		item_code = f"{sku}{variant_id}" if sku and sku_count[sku] > 1 else (sku or f"SALLA-{variant_id}")

		if not frappe.db.exists("Item", item_code):
			frappe.get_doc(
				{
					"doctype": "Item",
					"item_code": item_code,
					"item_name": variant["name"][:140],
					"item_group": ITEM_GROUP,
					"stock_uom": "Nos",
					"is_stock_item": 1,
					"standard_rate": variant["price"],
				}
			).insert(ignore_permissions=True)
			items_created += 1

		frappe.get_doc(
			{
				"doctype": "Marketplace Item Map",
				"marketplace_store": store.name,
				"item_code": item_code,
				"channel_sku": item_code,
				"channel_product_id": str(variant["product_id"]),
				"channel_variant_id": variant_id,
				"enabled": 1,
			}
		).insert(ignore_permissions=True)
		maps_created += 1

	frappe.db.commit()
	return {"items_created": items_created, "maps_created": maps_created, "skipped": skipped}


def _ensure_item_group() -> None:
	if not frappe.db.exists("Item Group", ITEM_GROUP):
		frappe.get_doc(
			{"doctype": "Item Group", "item_group_name": ITEM_GROUP, "parent_item_group": "All Item Groups"}
		).insert(ignore_permissions=True)
