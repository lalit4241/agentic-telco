# AgenticTelco TMF facade within Salesforce (Apex REST)

Per the ADR amendment in `docs/adr-amendments/`, every TMF Open API that the sfcomms org does **not** expose natively
(or exposes but cannot serve on this org) is provided as an Apex REST resource under
`/services/apexrest/agentictelco/tmf<NNN>/...`. Native OOTB Comms Cloud APIs stay first choice.

| Class | Path | Resources | Backed by |
|---|---|---|---|
| AgenticTelco_TMF620 | /agentictelco/tmf620/ | productOffering, productOfferingPrice, productSpecification, category, catalog (GET) | Native EPC (Product2, ProductCatalog/Category, ProductAttributeDefinition, ProductRelatedComponent, PricebookEntry, ProductSellingModel) |
| AgenticTelco_TMF622 | /agentictelco/tmf622/ | productOrder (GET list/id, POST, PATCH state) | Order, OrderItem |
| AgenticTelco_TMF648 | /agentictelco/tmf648/ | quote (GET list/id, POST, PATCH state) | Quote, QuoteLineItem |
| AgenticTelco_TMF671 | /agentictelco/tmf671/ | promotion (GET) | Promotion |
| AgenticTelco_TMF637 | /agentictelco/tmf637/ | product (GET list by relatedParty.id / status / productSerialNumber / creationDate.gt; GET id; POST; PATCH status, terminationDate, productRelationship) | Asset, AssetRelationship (relationshipType Upgrade), Location/Address (place) |
| AgenticTelco_TMF632 | /agentictelco/tmf632/ | organization/{id} (GET, optional relatedParty.role filter): contacts as relatedParty with role | Account, AccountContactRole, Contact |

TMF622 POST also adds the order's usage record (AppUsageAssignment, AppUsageType SubscriptionManagement) as an internal
step, returned as `x-usageRecord`; callers never touch it directly. TMF637 status mapping: Installed ↔ active,
Obsolete ↔ terminated, Purchased ↔ created, Shipped ↔ pendingActive (the Salesforce value is returned as `x-sfStatus`).
The facades only map data: no business rules (policy is OPA, process is Operaton). The resource shapes are TMF-aligned.

Shared helpers: `AgenticTelco_Tmf`. Tests: `AgenticTelco_TmfTest` (target ≥ 85 % coverage).

Rules: only records created by these APIs carry the `AgenticTelco` prefix; nothing existing is updated or deleted
(PATCH only accepts AgenticTelco-prefixed records; there is no DELETE). Agents, policy (OPA), orchestration (Operaton),
data and observability stay outside Salesforce.

Deploy: `sf project deploy start --target-org sfcomms --source-dir force-app --test-level RunSpecifiedTests --tests AgenticTelco_TmfTest`

## Deployed to sfcomms

| Deploy ID | Tests | Coverage |
|---|---|---|
| 0AfQH00000Q1oYT0AZ | 6/6 passed | ≥ 85 % |
| 0AfQH00000Q1p370AB (2026-10-26 19:01 Europe/London) | 6/6 passed | 97.3 % |
| 0AfQH00000Q5Zm90AF (current, 2026-10-30 17:50 Europe/London): + TMF637, TMF632, TMF622 usage record | 10/10 passed | 97.1 % org-wide for these classes (TMF637 135 lines/3 uncovered, TMF632 21/2, TMF622 168/4, TMF648 110/3, TMF620 194/9, TMF671 16/0, Tmf 111/1) |

## How the MVP uses them

Everything above the systems-of-record layer reaches Salesforce only through TM Forum Open APIs; no SOQL and no sObject
REST (enforced by `tests/test_mvp_unit.py::test_mvp_stack_issues_no_soql_or_sobject_rest` and the runtime guard
`stack/mvp/common.py:provided_by`). Out of the box: TMF629 Customer and TMF637 Product Inventory GET by id
(`/services/data/vNN/connect/comms/...`). Everything else goes through the facades above. On screen every Salesforce
call reads "TMF Open API"; the call detail says "Provided by: Salesforce (out of the box)" or
"Provided by: TMF facade within Salesforce (Apex)".

The pre-MVP L6 adapter (`stack/l6_salesforce_adapter`) and the one-time org seeding script (`seed/customers/seed_brightwell.py`)
are setup / legacy tooling and still use the sObject API; the MVP stack does not call them.

## Salesforce order orchestration (fulfilment of the TMF622 order)

TMF622 `PATCH state=inProgress` submits the order to Salesforce order orchestration (`AgenticTelco_Orchestration.submit`,
through the `AgenticTelco_Submit_Order_To_Orchestration` flow). Setup (`AgenticTelco_OrchestrationSetup.run()`, idempotent, new AgenticTelco
records only) creates:

- CFS technical products (customer facing services) and built-in decomposition rules (ProductFulfillmentDecompRule) from the
  commercial products: Fibre bundle → **CFS Fibre Broadband**, access line → **CFS Fibre Access**, router → **CFS Managed Router**
  (CPE), installation → **CFS Installation** (only when installation is on the order).
- Step group *AgenticTelco Fibre Upgrade Fulfilment*: 7 plan-scope steps chained by dependencies (1 validate and set action
  codes from the installed base (TMF637) → 2 send network service order TMF641 → 3 wait for network activation (jeopardy rule:
  2 days, threshold 1 day) → 4 point of no return (milestone) → 5 record the network result (TMF641 response) → 6 notify the customer →
  7 complete, order Activated), and the scenario
  *AgenticTelco Fibre Upgrade Scenario* (Add;Amend).

Action codes: TMF622 carries the commercial codes (bundle `Amend/UpgradeTo` = modify; each bundle component gets its own
OrderAction: Fibre Access Line `No Change` with Quantity 0, Wi-Fi 6 Router `Amend/UpgradeTo`). Each FulfillmentOrderLineItem
carries the CFS code (`Action` plus `Description` `tmf=<add|modify|delete|noChange>;why=...`), derived from the installed base
(TMF637), not by the built-in decomposition (which gives add for every line). TMF641 `serviceOrderItem.action` carries the CFS
codes (noChange / modify / modify); the RFS and resources, including router delete + add, are the network's own breakdown and
appear only in the TMF641 response (`x-action` extension fields). The idempotency key is the order.

Single writer: the installed product (TMF637: Fibre 900 Installed, Fibre 150 Obsolete, Upgrade relationship) is written only
by the L5 workflow. The plan has no assetization step. The platform still attempts its own assetization after the plan and
marks the order `AssetizationFailed` (it writes nothing); `x-orchestration.productInventory.platformStatus` shows it. The demo UI does not show this raw status (the stack's worker drops it); the Dev View says "Assetisation done (TMF637)".

No silent fallback: if no fulfilment plan is created, TMF622 returns `x-orchestration.status=notSubmitted` with an error and
the L5 workflow stops (BPMN error `NO_FULFILMENT_PLAN`).

The network is reached through one interface, `AgenticTelco_NetworkOrderAdapter`, with one outbound interaction: TMF641
(POST plus status reads). Reservation (TMF685) and the network's inventories (TMF638 services, TMF639 resources) are on the
network side and come back as `x-networkFulfilment` data in the TMF641 response; the mode comes from the custom metadata
`AgenticTelco_Network_Adapter__mdt` (`Mock` → `AgenticTelco_MockNetworkAdapter`, `Callout` → `AgenticTelco_CalloutNetworkAdapter`).
The TMF641 request and response are simulated inside Salesforce for this demo (Mock). Every call is logged in
`AgenticTelco_Network_Call__c`; `GET /tmf622/productOrder/{id}` returns them with the plan, steps and decomposition in
`x-orchestration`.
