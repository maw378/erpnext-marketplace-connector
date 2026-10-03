# Copyright (c) 2026, Zainzone and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document

# Settings a store may override; anything left empty falls back to the channel's default.
INHERITED_FIELDS = ("warehouse", "price_list", "default_customer", "customer_group", "tax_template")


class MarketplaceStore(Document):
	def validate(self):
		if self.enabled and not self.get_setting("warehouse"):
			frappe.throw(
				"Set a Warehouse on this store, or a default on its Marketplace Channel, before enabling it, "
				"so orders have somewhere to deduct stock from.",
				title="Missing Warehouse",
			)

	def channel_doc(self) -> Document:
		return frappe.get_doc("Marketplace Channel", self.marketplace_channel)

	def get_setting(self, fieldname: str):
		"""The store's own value, else the channel default."""
		return self.get(fieldname) or frappe.db.get_value("Marketplace Channel", self.marketplace_channel, fieldname)
