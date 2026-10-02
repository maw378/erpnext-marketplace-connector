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

			frm.add_custom_button(__("Register Webhooks"), () => {
				frappe.call({
					method: "erpnext_marketplace_connector.erpnext_marketplace_connector.api.register_webhooks",
					args: { channel: frm.doc.name },
					freeze: true,
					callback: (r) => {
						const done = r.message.registered.length ? r.message.registered.join(", ") : __("nothing new");
						frappe.msgprint({ title: __("Webhooks"), message: `${__("Registered")}: ${done}<br>${r.message.url}`, indicator: "green" });
					},
				});
			});

			frm.add_custom_button(__("Import Products"), () => {
				frappe.confirm(__("Create ERPNext Items and item mappings for every product on this Salla store?"), () => {
					frappe.call({
						method: "erpnext_marketplace_connector.erpnext_marketplace_connector.api.import_products",
						args: { channel: frm.doc.name },
						freeze: true,
						freeze_message: __("Importing products..."),
						callback: (r) => {
							const m = r.message;
							frappe.msgprint({
								title: __("Products imported"),
								message: __("{0} items created, {1} mappings created, {2} already mapped.", [m.items_created, m.maps_created, m.skipped]),
								indicator: "green",
							});
						},
					});
				});
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
