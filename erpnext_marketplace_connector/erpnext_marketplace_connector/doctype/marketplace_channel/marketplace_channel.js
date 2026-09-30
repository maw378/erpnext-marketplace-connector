// Copyright (c) 2026, Zainzone and contributors
// For license information, please see license.txt

frappe.ui.form.on("Marketplace Channel", {
	refresh(frm) {
		if (frm.doc.sync_status === "Error" && frm.doc.last_sync_error) {
			frm.dashboard.set_headline_alert(frm.doc.last_sync_error, "red");
		}
	},
});
