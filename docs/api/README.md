# AgenticTelco APIs

| Artefact | What it is |
|---|---|
| [`org-capabilities.md`](org-capabilities.md) / [`.json`](org-capabilities.json) | Read-only TMF capability check of the `sfcomms` org (API 68.0): what is OOTB, what is a custom TMF API on Salesforce, and what is our layer |
| [`openapi/l2-tmf921-intent.json`](openapi/l2-tmf921-intent.json) | TMF921 Intent Management (L1/L2). **Not supported by Salesforce – our layer** |
| [`openapi/l3-data.json`](openapi/l3-data.json) | L3 data products (Postgres + pgvector, semantic cache) |
| [`openapi/l4-context.json`](openapi/l4-context.json) | L4 context and policy API (OPA decisions; the model is never consulted) |
| [`openapi/l5-orchestrator.json`](openapi/l5-orchestrator.json) | L5 read-only view of Operaton 2.2.0 BPMN instances (agents can only start and read) |
| [`openapi/l6-salesforce-adapter.json`](openapi/l6-salesforce-adapter.json) | L6 adapter: TMF paths routed to the org through the sf CLI session (server-side; no token in code, browser or recording) |
| [`graphql-schema.graphql`](graphql-schema.graphql) | L1 read-only GraphQL (Strawberry), exported from `schema.as_str()` |

The OpenAPI files are exported from the FastAPI apps.

## Runtime labels

Every call is written to the L8 ledger (`l8.api_calls`) with:

- its ODA block, layer, owner and runtime;
- for L6, the exact Salesforce REST calls behind it (`extra.salesforceCalls`, ids masked below).

| Label | Meaning |
|---|---|
| `OOTB` | Native Communications Cloud TMF API or standard sObject REST |
| `custom TMF API on Salesforce` | `AgenticTelco_*` Apex REST at `/services/apexrest/agentictelco/tmf<NNN>/...`, returning TMF shapes ([ADR amendment 001](../adr-amendments/001-custom-tmf-apis-on-salesforce.md)) |
| `our layer (native TMF679 tried: 400)` | The native TMF679 call was made first. The org has no default qualification procedure, so a labelled rule was applied instead |
| `our layer` | L1–L5, L7 and L8 services. These sit outside Salesforce by design |

## Salesforce REST calls in the recorded run (2026-10-26, 19:27–19:32 UK time)

- **Totals:** 90 adapter calls and 149 Salesforce REST calls.
- **Adapter calls by runtime:** 58 OOTB, 24 custom TMF API on Salesforce, 8 TMF679 attempts that fell back to our layer.

| Count | Salesforce call | Runtime |
|---|---|---|
| 23 | `GET /services/data/v68.0/connect/comms/customermanagement/v4/customer/{id}` (TMF629) | OOTB |
| 23 | `GET …/connect/comms/partymanagement/v5/organization/{id}` (TMF632) | OOTB |
| 23 | `GET …/connect/comms/partymanagement/v5/individual/{id}` (TMF632) | OOTB |
| 16 | `GET /services/data/v68.0/query?…` (SOQL: Account by AccountNumber, Asset ids) | OOTB |
| 12 | `GET …/connect/comms/productinventorymanagement/v5/productinventory/{id}` (TMF637) | OOTB |
| 8 | `POST …/connect/comms/productofferingqualification/v5/checkProductOfferingQualification` (TMF679) | OOTB attempt → 400 |
| 4 / 4 | `POST` / `PATCH /services/data/v68.0/sobjects/Asset` (inventory write after order completion) | OOTB |
| 17 | `GET /services/apexrest/agentictelco/tmf620/{id}` | custom TMF API on Salesforce |
| 3 | `GET /services/apexrest/agentictelco/tmf620/{id}?isBundle=true` | custom TMF API on Salesforce |
| 6 | `POST /services/apexrest/agentictelco/tmf648/quote` | custom TMF API on Salesforce |
| 5 / 5 | `POST` / `PATCH /services/apexrest/agentictelco/tmf622/productOrder[/{id}]` | custom TMF API on Salesforce |

The adapter never issues DELETE. Writes touch only AgenticTelco-prefixed records.

## Caveat: TMF620 and TMF648

The `sfcomms` org does not expose TMF620 (Product Catalog) or TMF648 (Quote) through Communications Cloud Direct Access: v4, v5 and the managed-package paths all return 404.

AgenticTelco therefore serves them as **custom TMF APIs on Salesforce**:

- `AgenticTelco_TMF620` sits over the standard EPC objects (Product2, PricebookEntry, ProductCategory and related objects) seeded by `seed/epc/`.
- `AgenticTelco_TMF648` sits over Quote and QuoteLineItem.

They return TMF-shaped JSON, but they are **not** TM Forum-certified implementations and not a Salesforce product. Other Comms Cloud orgs, editions or releases may expose these APIs natively. Rerun `scripts/verify_org.py` before you rely on this table for another org.
