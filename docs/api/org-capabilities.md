# sfcomms org: TMF API capability check

| | |
|---|---|
| Org | `00DQH00000P7uDa` (Salesforce CLI alias `sfcomms`), API v68.0 |
| Method | Salesforce CLI `sf api request rest` / `sf api request graphql`, run server-side. No token is handled by AgenticTelco code. |
| Read-only probe | 2026-10-26 18:33 (Europe/London). Raw evidence is in [`org-capabilities.json`](org-capabilities.json). |
| Write checks | 2026-10-26 18:40–19:10 (Europe/London), using AgenticTelco-prefixed demo records only. |
| Installed packages | No Vlocity / `vlocity_cmt` managed package. Communications Cloud is native (PCM/EPC on standard objects). |

The decision rule (see [ADR amendment 001](../adr-amendments/001-custom-tmf-apis-on-salesforce.md)):

1. **OOTB** is used first when it works. That means a native Communications Cloud Direct Access TMF API, or standard sObject REST.
2. **custom TMF API on Salesforce** is the fallback. These are `AgenticTelco_*` Apex REST classes at `/services/apexrest/agentictelco/tmf<NNN>/...`, and they apply only where the org does not expose the API or the native one fails on this org.
3. **our layer** applies only where neither of those works. It is always labelled in the response (`x-zg-runtime`) and in the L8 ledger.

## Capability table

| TMF API | Native (OOTB) result in sfcomms | Evidence | Decision on the demo path | Runtime label |
|---|---|---|---|---|
| **TMF620** Product Catalog | Not exposed. Direct Access v4/v5 returns 404 and the managed-package paths return 404. Only the Industries PCM Connect API exists (`/connect/pcm/catalogs` returned 400 for the request shape). | 404 ×4, 400 | Use **AgenticTelco_TMF620** (GET productOffering, productOfferingPrice, productSpecification, category, catalog) over the native EPC objects seeded in `seed/epc/`. | custom TMF API on Salesforce |
| **TMF621** Trouble Ticket | Exposed: `/connect/comms/troubleTicket/v4/troubleTicket` returned 400 "Required type must not be null", so the path exists but needs a type parameter. | 400 | Not on the demo path. The demo raises TMF621 against the network in the ODA Production block (OSS, mocked). The native, Case-backed TMF621 is available if a customer-facing ticket is needed later. | not used |
| **TMF622** Product Ordering | Exposed but broken here. GET v5 productOrder returns 400 "Failed to execute GraphQL query" on PoNumber/OrderReferenceNumber. Native POST was **deliberately not called**: an order that cannot be read back by the native API, and that does not carry the AgenticTelco prefix, could not be traced or kept to the "create only AgenticTelco records" rule. | 400 | Use **AgenticTelco_TMF622**: POST productOrder (idempotent on externalId), GET, PATCH state (inProgress, completed, cancelled), over the standard Order and OrderItem objects. | custom TMF API on Salesforce |
| **TMF629** Customer | **Works.** GET customer by Account id returns 200 with name, engagedParty (Contact) and contactMedium. | 200 | **Native.** Agent-facing `C-100x` maps to the Account through standard `AccountNumber = AT-C-100x`. | OOTB |
| **TMF632** Party | **Works.** v5 individual by Contact id and organization by Account id both return 200. | 200 | **Native.** Marketing consent is added from the demo consent store because the integration user cannot read the Contact consent fields (field-level security). The response labels this addition. | OOTB (+ labelled enrichment) |
| **TMF637** Product Inventory | **GET by id works** (200 with productOffering = Product2, relatedParty Account, productSerialNumber). The list endpoint returns `[]`, the `relatedParty.id` filter returns 400 (GraphQL error), and **POST returns 405** (GET/HEAD only). | 200 / 400 / 405 | **Native read.** Asset ids are found by a standard SOQL query and then each one is read through native TMF637. Inventory writes use standard sObject REST on `Asset`. | OOTB |
| **TMF648** Quote | Not exposed. Direct Access v4/v5 and the managed-package paths all return 404. | 404 ×4 | Use **AgenticTelco_TMF648** (POST, GET, PATCH quote) over the standard Quote and QuoteLineItem objects. | custom TMF API on Salesforce |
| **TMF651** Agreement | Exposed: `/connect/comms/agreementManagement/v4/agreement` returns 200 `[]`. | 200 | Available OOTB. Not on the demo journeys. | OOTB (available) |
| **TMF667** Document | Exposed: `/connect/comms/document/v4/document` returns 200 with 33 items. | 200 | Available OOTB. Not on the demo journeys. | OOTB (available) |
| **TMF671** Promotion | Exposed but fails: `/connect/comms/promotionManagement/v4/promotion` returns 500 INTERNAL_ERROR (`rewardDetails` null). | 500 | Use **AgenticTelco_TMF671** (GET promotion over the standard Promotion object). Not on the demo journeys. | custom TMF API on Salesforce |
| **TMF679** Product Offering Qualification | Exposed, POST only (GET returns 405). A correct POST (AccountRef relatedParty) returns **400 "No Default Qualification Procedure is set"**. TMF679 needs a Revenue Cloud product-discovery qualification procedure. Setting one up would change existing org setup, which is out of scope. | 405 / 400 | Native is **called first on every request**. When it returns this 400, the L6 adapter applies the product-configuration rule (offer access technology vs address technology). The native status is kept in `x-nativeAttempt`. | our layer (native TMF679 tried: 400) |
| **GraphQL** (UI API) | **Works.** A read query (Account, first 3) returns 200 with no errors. | 200 | Not used for SoR reads, because the TMF APIs above cover the journeys. The demo's own GraphQL (Strawberry, L1) stays in our layer. | OOTB (available) |
| TMF921 Intent | Not supported by Salesforce. | – | **Our layer** (L1/L2). | our layer |

Customer, party, product inventory, catalogue, qualification check, quote and order calls all reach the real org. Nothing on the journey path uses the stand-in in real-org mode.

## Org automation: Custom Assetize Order flow

This check was read-only. Flow `301QH00002LKPPUYA5` is `Custom_Assetize_Order` v3, active, API 64. Nothing in the flow or the org setup was edited or deactivated.

- **Trigger:** record-triggered (`RecordAfterSave`) on **Order update** where `Status = Activated`, firing only when the record changes to meet that criterion. It runs on an `AsyncAfterCommit` scheduled path.
- **Path:**
  1. `GetApplicationUsageAssignment` finds an `AppUsageAssignment` where `RecordId = $Record.Id` and `AppUsageType = 'SubscriptionManagement'`.
  2. Decision `HaveRecord`: if `AppUsageAssignment.Id` **is null**, the flow calls `createOrUpdateAssetFromOrder`. Otherwise it ends.
- **Problem:** AgenticTelco Orders had no AppUsageAssignment, so the action ran. It failed with "The order must have a related Application Usage Assignment with an Application Usage Type of RevenueLifecycleManagement or SubscriptionManagement", and Salesforce emailed a FlowApplication error for every activation.
- **Fix (OOTB, no licence block):** before an AgenticTelco Order is activated, the L6 adapter (`_ensure_app_usage`) does two things:
  1. Runs a SOQL guard that limits the step to AgenticTelco Orders and makes it idempotent.
  2. Sends `POST /services/data/v68.0/sobjects/AppUsageAssignment` with `{"RecordId": <order>, "AppUsageType": "SubscriptionManagement"}`, labelled **OOTB**. The org returns 201.
- **Effect:** the flow finds the record and ends on its default branch.
- **Why `SubscriptionManagement` rather than `RevenueLifecycleManagement`:** an RLM record would not satisfy this flow's lookup, so the assetize action would still run. Even if that action succeeded, it would assetize a second time, and our layer already writes the Asset through sObject REST (TMF637). With SM there is no flow error and no double assetization.
- **Platform rule we hit:** an SM AppUsageAssignment can only be created **before** activation. On an already activated Order the org returns `FIELD_INTEGRITY_EXCEPTION`: "You can't assign or unassign an Subscription Management Application Usage Type to activated orders". Two consequences:
  - The adapter creates the assignment immediately before the Apex TMF622 PATCH that sets `Activated`. If the POST fails, the adapter stops **before** activation, so the flow is never tripped.
  - The 23 AgenticTelco Orders activated before the fix cannot be given an assignment, and we do not modify existing records. Their earlier error emails remain, and Salesforce may retry their async interviews for a while.
- **Orders that end in `Exception`** (fallout/cancel) do not match the flow's entry criteria.
- **Evidence (26 Oct 2026, fix live from 19:50 UK time):**
  - All 5 Orders activated after the fix have an SM assignment.
  - Every FlowApplication email and `FlowInterview` error traced after the fix names a pre-fix Order. See [TEST_RESULTS.md](../../TEST_RESULTS.md#org-flow-check-custom-assetize-order).

### Licence workarounds

- **None needed so far.** The `AppUsageAssignment` create works as OOTB sObject REST for the integration user.
- **Standing rule from the owner:** if an OOTB route is blocked by licensing, the equivalent is implemented as `AgenticTelco_*` Apex REST under `/services/apexrest/agentictelco/...`, labelled "custom TMF API on Salesforce". It must keep test coverage at 85% or more and must not trip or edit the flow. Each workaround is recorded here.
- **Existing custom TMF APIs:** TMF620, TMF622, TMF648 and TMF671 are custom TMF APIs on Salesforce because the native APIs are missing or broken (404, 400 or 500), not because of licensing. See the table above.

## What is real Salesforce data, and what is not

| Data | Where it lives in real-org mode |
|---|---|
| Customers (Account), contacts (Contact), current broadband line (Asset) | Salesforce. Seeded by `seed/customers/seed_customers.py`. |
| Catalogue: 8 products, 3 bundles with components, attributes, selling models, 24 price-book entries | Salesforce native EPC. Seeded by `seed/epc/` (see [docs/dev/epc-seed.md](../dev/epc-seed.md)). |
| Quotes, orders and order items created by the agents and the L5 saga | Salesforce (Quote, QuoteLineItem, Order, OrderItem) through the AgenticTelco Apex TMF APIs. |
| Inventory created on completion | Salesforce Asset (OOTB REST). The old line is set to `Obsolete`. |
| Exchange and access technology at the address | Demo OSS serviceability data (L3/OSS). It is network data and deliberately not held in the SoR. Labelled `x-zg-enrichment`. |
| Marketing consent | Demo consent store, because Contact consent fields are not readable by the integration user. Labelled. |
| Credit score, usage, policy, saga state, events, ledger | Our layers (L3/L4/L5/L8). These never live in Salesforce. |

## Reproduce

```bash
.venv/bin/python scripts/verify_org.py           # read-only probe → docs/api/org-capabilities.json
ZG_SOR_MODE=commscloud ./run.sh up               # L2/L4/L5 → L6 Salesforce adapter (port 8116) → sfcomms
ZG_SOR_MODE=commscloud ./run.sh journeys         # resets demo inventory, records recordings/run-<date>.json
```
