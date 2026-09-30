# Copyright (c) 2026, Zainzone and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class MarketplaceChannel(Document):
	def validate(self):
		if self.enabled and not self.warehouse:
			frappe.throw(
				"Set a Warehouse before enabling this channel, so orders have somewhere to deduct stock from.",
				title="Missing Warehouse",
			)

	def get_api_secret(self) -> str | None:
		return self.get_password("api_secret", raise_exception=False)

	def get_webhook_secret(self) -> str | None:
		return self.get_password("webhook_secret", raise_exception=False)
