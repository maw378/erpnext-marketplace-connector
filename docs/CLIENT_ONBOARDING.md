# Client onboarding: Salla stores on a client site

One client = one ERPNext site (e.g. `client1.zainzone.net`), standard or AI-enhanced.
One Salla private app per client site. One Marketplace Channel per Salla store.

## 0. Before you start
- [ ] Site name decided (`<client>.zainzone.net`) and variant chosen (standard / AI-enhanced).
- [ ] List of the client's Salla store URLs (`https://demostore.salla.sa/dev-...` or their real domain) and which ERPNext company each store sells under.
- [ ] Client's seller legal data: VAT number and national address (street, building no., district, city, postal code) for each company.

## 1. ERPNext site
- [ ] Site created with these apps installed: `erpnext`, `zatca_integration`, `erpnext_howto_assistant`, `erpnext_marketplace_connector` (+ `erpnext_ai_dashboards` for AI-enhanced). `bench migrate` ran clean.
- [ ] Check the Contact table has the column `is_billing_contact` (Custom Field `Contact-is_billing_contact`). If missing, run `erpnext.setup.install.create_address_and_contact_custom_fields`. Without it, Sales Orders from Salla fail.
- [ ] Companies created; seller VAT number and national address filled in on each (the Saudi Tax Invoice shows a red "Legal data incomplete" banner until they are).
- [ ] Per store: a Warehouse, a Price List, a Sales Taxes and Charges Template (VAT 15%) for that company.
- [ ] A customer named `Salla Customer` (group Individual). It is the Default Customer for Salla orders.

## 2. Salla Partners portal: the app (once per client site)
- [ ] Create a **Private App**, named with the client, e.g. `ZZ - client1`.
- [ ] OAuth callback URL: `https://<client>.zainzone.net/api/method/erpnext_marketplace_connector.erpnext_marketplace_connector.api.oauth_callback`
- [ ] Scopes: `settings.read`, `customers.read`, `orders.read`, `products.read_write`, `webhooks.read_write`, `offline_access`.
- [ ] Leave the app-level **Webhook URL** blank. The per-store webhooks are registered by the connector and carry the right channel name. (The app-level URL receives every store's events but names only one channel.)
- [ ] Save the **Client ID** and **Client Secret** somewhere private. Never commit them.

## 3. Salla Partners portal: store access (once per store)
- [ ] Demo/test store: install the app from the app's test options.
- [ ] Real store: publish the app, then Partners > My Apps > the app > Stores > **Request Store Access** with the store URL; the store manager approves. Check what publishing locks (e.g. callback URL) before you publish.

## 4. Marketplace Channel (once per store, in ERPNext)
Create a Marketplace Channel:
- [ ] Channel Name: unique, e.g. `Salla - Main Store`. **The name appears in the webhook URL and must match exactly.**
- [ ] Platform Salla, Enabled, Store URL = that store's URL.
- [ ] API Key = Client ID; API Secret = Client Secret (the same pair for every store of this client).
- [ ] Webhook Secret: any long random string (the connector registers it with Salla).
- [ ] Warehouse (belongs to the right company), Price List, Customer Group `Individual`, Default Customer `Salla Customer`, Tax Template.
- [ ] Save, then click **Connect to Salla** while signed in as that store's manager. You return with "Connected to Salla successfully".
- [ ] Click **Register Webhooks**: expect `order.created, order.updated, order.cancelled` (or "nothing new" if already done).
- [ ] Click **Import Products**: creates an Item and an Item Map per Salla variant. Safe to re-run.
- [ ] Post opening stock for items that will be sold (the import creates items with stock tracking and zero stock; draft Sales Orders work without it, submitting needs stock).

## 5. Test
- [ ] Place or edit an order on the Salla store.
- [ ] Marketplace Webhook Log: new `order.created` row, Signature Valid ticked, error empty.
- [ ] A draft Sales Order exists with PO number `Salla-<order number>`, the right company and items.
- [ ] Changing the order's status adds a comment to the same Sales Order; cancelling it removes the draft.
- [ ] Print an invoice: the Saudi Tax Invoice shows seller details and a reserved QR box (the QR fills in after ZATCA clearance).

## 6. Troubleshooting
| Symptom | Likely cause |
|---|---|
| No webhook log rows at all | Order is on a different store than the one the token belongs to; or webhooks not registered. Re-run Connect, then Register Webhooks. |
| Request answered 404, nothing logged | Channel name in the webhook URL does not match a channel on that site (check spaces and hyphens). |
| Log shows `signature_valid` 0 / HTTP 401 | Webhook Secret on the channel differs from the secret the webhook was registered with. Re-register. |
| "Set Default Customer on Marketplace Channel ..." | Default Customer empty on the channel. |
| "No Marketplace Item Map for: ..." | Run Import Products; the order's variant is not mapped yet. |
| `Unknown column 'tabContact.is_billing_contact'` | See step 1: Contact custom field missing. |
| Log has an empty error and no Sales Order | Check ERPNext Error Log for `Marketplace webhook <name> failed`. |
| Failed log does not retry | Expected. Trigger a new event (change the order's status) after fixing the cause. |

## Still open for every client
- Tax Template per channel decides whether Salla orders carry VAT.
- ZATCA clearance needs the client's own simulation/production credentials; the QR appears on the invoice only after clearance.
