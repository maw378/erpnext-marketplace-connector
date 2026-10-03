# Client onboarding: Salla stores on a client site

Model: one client = one ERPNext site (e.g. `client1.zainzone.net`), standard or AI-enhanced.
- **Marketplace Channel** = the master. One per platform per client site. Holds the Salla app's Client ID/Secret, the Webhook Secret and the ERPNext defaults (warehouse, price list, customer, tax template).
- **Marketplace Store** = the detail. One per Salla store. Holds the store's name, URL, status, cost, OAuth token and optional overrides of the channel defaults.
- **One webhook URL for every store:** `https://<site>/api/method/erpnext_marketplace_connector.erpnext_marketplace_connector.api.webhook`. The store is identified from the store ID Salla puts in each payload (`merchant`); the channel's Webhook Secret verifies the signature.

## 0. Before you start
- [ ] Site name decided (`<client>.zainzone.net`) and variant chosen (standard / AI-enhanced).
- [ ] The client's Salla store URLs, and which ERPNext company each store sells under.
- [ ] Seller legal data per company: VAT number and national address (street, building no., district, city, postal code).

## 1. ERPNext site
- [ ] Apps installed: `erpnext`, `zatca_integration`, `erpnext_howto_assistant`, `erpnext_marketplace_connector` (+ `erpnext_ai_dashboards` for AI-enhanced). `bench migrate` ran clean.
- [ ] Contact has the column `is_billing_contact` (Custom Field `Contact-is_billing_contact`). If missing run `erpnext.setup.install.create_address_and_contact_custom_fields`; without it Sales Orders from Salla fail.
- [ ] Companies created; seller VAT number and national address filled in on each (the Saudi Tax Invoice shows a red "Legal data incomplete" banner until they are).
- [ ] A Warehouse, Price List and Sales Taxes and Charges Template (VAT 15%) per company.
- [ ] A customer `Salla Customer` (group Individual).

## 2. Salla Partners portal: the app (once per client site)
- [ ] Create a **Private App** named with the client, e.g. `ZZ - client1`.
- [ ] OAuth callback URL: `https://<client>.zainzone.net/api/method/erpnext_marketplace_connector.erpnext_marketplace_connector.api.oauth_callback`
- [ ] Scopes: `settings.read`, `customers.read`, `orders.read`, `products.read_write`, `webhooks.read_write`, `offline_access`.
- [ ] Leave the app-level Webhook URL blank (the connector registers the webhooks on each store).
- [ ] Save the **Client ID** and **Client Secret** privately. Never commit them.

## 3. Marketplace Channel (once per client site)
- [ ] Channel Name (e.g. `Salla`), Platform Salla, Enabled.
- [ ] API Key = Client ID, API Secret = Client Secret.
- [ ] Webhook Secret: a long random string (shared by all stores of this channel).
- [ ] Defaults for all stores: Warehouse, Price List, Customer Group `Individual`, Default Customer `Salla Customer`, Tax Template.

## 4. Marketplace Store (once per Salla store)
Open the channel and click **Add Store** (or create a Marketplace Store and pick the channel).
- [ ] Store Name (unique, e.g. `Salla - Main Store`), Store URL, Status, Cost (informational).
- [ ] Only if this store differs from the channel defaults: its own Warehouse / Price List / Customer / Tax Template.
- [ ] Give the app access to the store: demo/test store, install the app from the app's test options. Real store, publish the app, then Partners > My Apps > the app > Stores > **Request Store Access** with the store URL; the manager approves. Check what publishing locks (e.g. the callback URL) first.
- [ ] Save the store, then click **Connect to Salla** signed in as that store's manager. You return with "Connected to Salla successfully" and **Store ID** is filled in. (If Store ID stays empty, click **Refresh Store ID**.)
- [ ] Click **Register Webhooks**: expect `order.created, order.updated, order.cancelled` (or "nothing new"). It also removes older subscriptions of this site's endpoint in the `?channel=` form so events do not arrive twice.
- [ ] Click **Import Products** (Items + Item Maps for this store; safe to re-run).
- [ ] Post opening stock for items that will be sold (the import creates stock items with zero stock; draft Sales Orders work without it, submitting needs stock).

## 5. Test
- [ ] Place or edit an order on the store.
- [ ] Marketplace Webhook Log: a new `order.created` row, Marketplace Store set, Signature Valid ticked, error empty.
- [ ] A draft Sales Order with PO number `<Store Name>-<order number>` and its **Marketplace Store** field set.
- [ ] Changing the order's status adds a comment to the same Sales Order; cancelling it removes the draft.
- [ ] Print an invoice: the Saudi Tax Invoice shows seller details and a reserved QR box (filled after ZATCA clearance).

## Several stores on one site
- Add another Marketplace Store under the same channel: no new credentials, secret or URL. Connect, Register Webhooks, Import Products.
- Item maps, Sales Order duplicate detection and PO numbers are per store, so two stores with the same order number stay separate.
- A webhook for a store ID that no store has is answered with 404 and ignored.

## 6. Troubleshooting
| Symptom | Likely cause |
|---|---|
| No webhook log rows | The order is on a store this site has no token for, or Register Webhooks was not run for that store. |
| Request answered 404, nothing logged | No enabled store has that Store ID. Connect the store (or Refresh Store ID). With the old `?channel=` form: the name does not match a store or a single-store channel. |
| Log has `signature_valid` 0 / HTTP 401 | Webhook Secret on the channel differs from the secret the webhook was registered with. Register Webhooks again. |
| "Set Default Customer on Marketplace Store ..." | No Default Customer on the store or its channel. |
| "No Marketplace Item Map for: ..." | Run Import Products on that store. |
| `Unknown column 'tabContact.is_billing_contact'` | See step 1. |
| Log has an empty error and no Sales Order | Check ERPNext Error Log for `Marketplace webhook <name> failed`. |
| Failed log does not retry | Expected. Trigger a new event (change the order's status) after fixing the cause. |

## Still open for every client
- The Tax Template decides whether Salla orders carry VAT.
- ZATCA clearance needs the client's own simulation/production credentials; the QR appears on the invoice only after clearance.
