// Copyright (c) 2026, Zainzone and contributors
// For license information, please see license.txt

frappe.ui.form.on("Marketplace Channel", {
	refresh(frm) {
		if (frm.is_new()) return;
		frm.add_custom_button(__("Add Store"), () => {
			frappe.new_doc("Marketplace Store", { marketplace_channel: frm.doc.name });
		});
	},
});
