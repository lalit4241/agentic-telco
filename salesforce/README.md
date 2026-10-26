# AgenticTelco custom TMF APIs on Salesforce (Apex REST)

Per the ADR amendment in `docs/adr-amendments/`, every TMF Open API that the sfcomms org does **not** expose natively
(or exposes but cannot serve on this org) is provided as an Apex REST resource under
`/services/apexrest/agentictelco/tmf<NNN>/...`. Native OOTB Comms Cloud APIs stay first choice.

| Class | Path | Resources | Backed by |
|---|---|---|---|
| AgenticTelco_TMF620 | /agentictelco/tmf620/ | productOffering, productOfferingPrice, productSpecification, category, catalog (GET) | Native EPC (Product2, ProductCatalog/Category, ProductAttributeDefinition, ProductRelatedComponent, PricebookEntry, ProductSellingModel) |
| AgenticTelco_TMF622 | /agentictelco/tmf622/ | productOrder (GET list/id, POST, PATCH state) | Order, OrderItem |
| AgenticTelco_TMF648 | /agentictelco/tmf648/ | quote (GET list/id, POST, PATCH state) | Quote, QuoteLineItem |
| AgenticTelco_TMF671 | /agentictelco/tmf671/ | promotion (GET) | Promotion |

Shared helpers: `AgenticTelco_Tmf`. Tests: `AgenticTelco_TmfTest` (target ≥ 85 % coverage).

Rules: only records created by these APIs carry the `AgenticTelco` prefix; nothing existing is updated or deleted
(PATCH only accepts AgenticTelco-prefixed records; there is no DELETE). Agents, policy (OPA), orchestration (Operaton),
data and observability stay outside Salesforce.

Deploy: `sf project deploy start --target-org sfcomms --source-dir force-app --test-level RunSpecifiedTests --tests AgenticTelco_TmfTest`

## Deployed to sfcomms

| Deploy ID | Tests | Coverage |
|---|---|---|
| 0AfQH00000Q1oYT0AZ | 6/6 passed | ≥ 85 % |
| 0AfQH00000Q1p370AB (current, 2026-10-26 19:01 Europe/London) | 6/6 passed | 97.3 % |

The L6 adapter (`stack/l6_salesforce_adapter`) calls these APIs for TMF620, TMF648 and TMF622, and labels each call
"custom TMF API on Salesforce". TMF629, TMF632 and TMF637 use the org's native APIs and are labelled "OOTB".
See `docs/api/org-capabilities.md`.
