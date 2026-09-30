// Copyright (c) 2026, Zainzone and contributors
// For license information, please see license.txt

frappe.ui.form.on("Marketplace Channel", {
	refresh(frm) {
		if (frm.doc.sync_status === "Error" && frm.doc.last_sync_error) {
			frm.dashboard.set_headline_alert(frm.doc.last_sync_error, "red");
		}

		if (frm.doc.platform === "Salla" && !frm.is_new()) {
			frm.add_custom_button(__("Connect to Salla"), () => {
				if (frm.is_dirty()) {
					frappe.msgprint(__("Save the channel before connecting - the redirect needs the API Key/Secret already saved."));
					return;
				}
				window.location.href = `/api/method/erpnext_marketplace_connector.erpnext_marketplace_connector.api.oauth_redirect?channel=${encodeURIComponent(frm.doc.name)}`;
			});
		}
	},

	onload(frm) {
		const params = new URLSearchParams(window.location.search);
		if (params.get("oauth_connected")) {
			frappe.show_alert({ message: __("Connected to Salla successfully."), indicator: "green" });
		} else if (params.get("oauth_error")) {
			frappe.msgprint({
				title: __("OAuth Error"),
				message: params.get("oauth_error"),
				indicator: "red",
			});
		}
	},
});
