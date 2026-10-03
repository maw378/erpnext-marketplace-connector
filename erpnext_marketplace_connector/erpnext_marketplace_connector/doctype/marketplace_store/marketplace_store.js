// Copyright (c) 2026, Zainzone and contributors
// For license information, please see license.txt

const MC_API = "erpnext_marketplace_connector.erpnext_marketplace_connector.api";

frappe.ui.form.on("Marketplace Store", {
	refresh(frm) {
		if (frm.doc.sync_status === "Error" && frm.doc.last_sync_error) {
			frm.dashboard.set_headline_alert(frm.doc.last_sync_error, "red");
		}
		if (frm.is_new() || frm.doc.platform !== "Salla") return;

		frm.add_custom_button(__("Connect to Salla"), () => {
			if (frm.is_dirty()) {
				frappe.msgprint(__("Save the store before connecting - the redirect needs the channel's API Key/Secret already saved."));
				return;
			}
			window.location.href = `/api/method/${MC_API}.oauth_redirect?store=${encodeURIComponent(frm.doc.name)}`;
		});

		frm.add_custom_button(__("Refresh Store ID"), () => {
			frappe.call({
				method: `${MC_API}.refresh_store_id`,
				args: { store: frm.doc.name },
				freeze: true,
				callback: (r) => {
					frappe.show_alert({ message: __("Store ID: {0}", [r.message.store_id]), indicator: "green" });
					frm.reload_doc();
				},
			});
		});

		frm.add_custom_button(__("Register Webhooks"), () => {
			frappe.call({
				method: `${MC_API}.register_webhooks`,
				args: { store: frm.doc.name },
				freeze: true,
				callback: (r) => {
					const done = r.message.registered.length ? r.message.registered.join(", ") : __("nothing new");
					const removed = r.message.removed.length ? `<br>${__("Removed old")}: ${r.message.removed.join(", ")}` : "";
					frappe.msgprint({ title: __("Webhooks"), message: `${__("Registered")}: ${done}${removed}<br>${r.message.url}`, indicator: "green" });
				},
			});
		});

		frm.add_custom_button(__("Import Products"), () => {
			frappe.confirm(__("Create ERPNext Items and item mappings for every product on this Salla store?"), () => {
				frappe.call({
					method: `${MC_API}.import_products`,
					args: { store: frm.doc.name },
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
	},

	onload(frm) {
		const params = new URLSearchParams(window.location.search);
		if (params.get("oauth_connected")) {
			frappe.show_alert({ message: __("Connected to Salla successfully."), indicator: "green" });
			window.history.replaceState({}, "", window.location.pathname);
		} else if (params.get("oauth_error")) {
			frappe.msgprint({
				title: __("OAuth Error"),
				message: frappe.utils.escape_html(params.get("oauth_error")),
				indicator: "red",
			});
			window.history.replaceState({}, "", window.location.pathname);
		}
	},
});
