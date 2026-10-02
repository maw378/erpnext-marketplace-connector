"""One-off Salla catalog import that works on the ALREADY-DEPLOYED connector code.

Run from <bench>/sites with the bench's own python:
    ../env/bin/python import_salla_products.py <site> "<Marketplace Channel name>"
Creates an Item + Marketplace Item Map per Salla variant; safe to re-run.
"""
import sys

import frappe
import requests

site, channel_name = sys.argv[1], sys.argv[2]
frappe.init(site=site)
frappe.connect()

from erpnext_marketplace_connector.erpnext_marketplace_connector.connectors import get_connector

channel = frappe.get_doc("Marketplace Channel", channel_name)
headers = get_connector(channel)._headers()

variants, page = [], 1
while True:
	body = requests.get(
		"https://api.salla.dev/admin/v2/products", headers=headers, params={"per_page": 50, "page": page}, timeout=30
	).json()
	for p in body.get("data", []):
		vals = {v["id"]: v.get("name") for o in p.get("options") or [] for v in o.get("values") or []}
		for s in p.get("skus") or []:
			labels = [vals.get(v) for v in s.get("related_option_values") or [] if vals.get(v)]
			variants.append(
				{
					"product_id": p["id"],
					"variant_id": s["id"],
					"sku": s.get("sku") or p.get("sku"),
					"name": " - ".join([p.get("name") or "", *labels]),
					"price": float((s.get("price") or {}).get("amount") or 0),
				}
			)
	if page >= ((body.get("pagination") or {}).get("totalPages") or 1):
		break
	page += 1

if not frappe.db.exists("Item Group", "Salla Products"):
	frappe.get_doc({"doctype": "Item Group", "item_group_name": "Salla Products", "parent_item_group": "All Item Groups"}).insert(ignore_permissions=True)

mapped = set(frappe.get_all("Marketplace Item Map", {"marketplace_channel": channel.name}, pluck="channel_variant_id"))
count = {}
for v in variants:
	count[v["sku"]] = count.get(v["sku"], 0) + 1

items = maps = skipped = 0
for v in variants:
	vid = str(v["variant_id"])
	if vid in mapped:
		skipped += 1
		continue
	sku = v["sku"]
	code = f"{sku}{vid}" if sku and count[sku] > 1 else (sku or f"SALLA-{vid}")
	if not frappe.db.exists("Item", code):
		frappe.get_doc({"doctype": "Item", "item_code": code, "item_name": v["name"][:140], "item_group": "Salla Products", "stock_uom": "Nos", "is_stock_item": 1, "standard_rate": v["price"]}).insert(ignore_permissions=True)
		items += 1
	frappe.get_doc({"doctype": "Marketplace Item Map", "marketplace_channel": channel.name, "item_code": code, "channel_sku": code, "channel_product_id": str(v["product_id"]), "channel_variant_id": vid, "enabled": 1}).insert(ignore_permissions=True)
	maps += 1

frappe.db.commit()
print({"variants": len(variants), "items_created": items, "maps_created": maps, "skipped": skipped})
