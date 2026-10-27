# 03 · API, event and SID mapping

## Conceptual alignment vs certified conformance
| Statement | Label |
|---|---|
| TM Forum runs separate conformance certification programmes for Open APIs, ODA Components, eTOM and SID ([TM Forum conformance](https://www.tmforum.org/oda/conformance-certification/)). | CONFIRMED |
| Salesforce lists nine Communications Cloud Industry APIs as certified by TM Forum: TMF620 v4, TMF622 v4, TMF629 v4, TMF637 v4, TMF648 v4, TMF651 v4, TMF667 v4, TMF671 v4, TMF679 v5 ([Salesforce TMF conformance](https://developer.salesforce.com/docs/industries/communications/guide/TMF_compliance.html)). These are Salesforce's certifications. | CONFIRMED (Salesforce's statement) |
| The AgenticTelco demo maps its components to ODA functional blocks and uses TMF Open API contracts. That is **conceptual alignment**. | INFERRED |
| The demo, its FastAPI stand-in and its open-source components hold **no** TM Forum certification. We must not say "ODA-compliant" or "ODA-certified". Say "aligned to ODA functional blocks, using TMF Open API contracts". | CONFIRMED (no certification sought) / RECOMMENDED wording |
| Zero Gravity is a framework. TechM claims "every layer aligns with the TM Forum ODA" (report p.21). No certification applies to a framework. | CONFIRMED (claim) / INFERRED (no certification) |

## TMF Open API map
"SF list" = which Salesforce availability list the API appears on, per the [Salesforce availability page](https://developer.salesforce.com/docs/industries/communications/guide/TMF_compliance.html): *MP* managed package, *Platform* Salesforce Platform, *Both*. Whether our trial org (Comms Cloud on Salesforce Platform) actually exposes each API is **UNKNOWN** until tested.

| Step | TMF API | ODA functional block (conceptual) | SID entity (INFERRED) | Served by in demo | SF list (CONFIRMED) | SF certified version (CONFIRMED) | Label for served-by |
|---|---|---|---|---|---|---|---|
| Intent capture | [TMF921 Intent Mgmt](https://www.tmforum.org/open-digital-architecture/open-apis/intent-management-api-TMF921/v5.0) | Engagement Management | Intent (TR292 TIO) | Ours (L1/L2) | Not listed | — | RECOMMENDED |
| Party lookup | [TMF632 Party Mgmt](https://github.com/tmforum-apis/TMF632_PartyManagement) | Party Management | Party, Individual | Salesforce if exposed, else stand-in | Platform (v5) | Not on certified list | UNKNOWN |
| Customer lookup | [TMF629 Customer Mgmt](https://github.com/tmforum-apis/TMF629_CustomerManagement) | Party Management | Customer, CustomerAccount | Salesforce if exposed, else stand-in | Both (v4) | v4 | UNKNOWN |
| Catalogue read | [TMF620 Product Catalog](https://github.com/tmforum-apis/TMF620_ProductCatalog) | Core Commerce Management | ProductOffering, ProductSpecification, ProductOfferingPrice | Salesforce if exposed, else stand-in | MP (v4) | v4 | UNKNOWN |
| Qualification | [TMF679 Product Offering Qualification](https://github.com/tmforum-apis/TMF679_ProductOfferingQualification) | Core Commerce Management | ProductOfferingQualification | Salesforce if exposed, else stand-in | Platform (v5) | v5 | UNKNOWN |
| Quote | [TMF648 Quote Mgmt](https://github.com/tmforum-apis/TMF648_QuoteManagement) | Core Commerce Management | Quote, QuoteItem | Salesforce if exposed, else stand-in | MP (v4) | v4 | UNKNOWN |
| Product order | [TMF622 Product Ordering](https://www.tmforum.org/open-digital-architecture/open-apis/product-ordering-management-api-TMF622/v5.0) | Core Commerce Management | ProductOrder, ProductOrderItem | Salesforce if exposed, else stand-in | MP (v4), Platform (v5) | v4 | UNKNOWN |
| Service order | [TMF641 Service Ordering](https://github.com/tmforum-apis/TMF641_ServiceOrder) | Production | ServiceOrder, ServiceOrderItem | Mocked OSS | Outbound only via MuleSoft Direct ([doc](https://developer.salesforce.com/docs/industries/communications/guide/get_started_industry_integrations.html)) | — | CONFIRMED (design: mocked) |
| Inventory update | [TMF637 Product Inventory](https://github.com/tmforum-apis/TMF637_ProductInventory) | Core Commerce Management | Product | Salesforce if exposed, else stand-in | MP (v4), Platform (v5) | v4 | UNKNOWN |
| Fallout | [TMF621 Trouble Ticket](https://github.com/tmforum-apis/TMF621_TroubleTicket) | Production (as agreed for the demo) | TroubleTicket | Mocked | Not listed | — | CONFIRMED (design: mocked) |
| Events | [TMF688 Event](https://github.com/tmforum-apis/TMF688-Event) | Decoupling & Integration | Event | Ours, on Kafka ("TMF688-style") | Not listed | — | RECOMMENDED |

**Notes**
- **ODA block assignments** are the team's agreed mapping and follow the report's statement that L6 corresponds to Party Management, Core Commerce Management and Production (report p.21). They are not taken from the ODA Component Directory. Checking each API against the ODA Component that lists it as mandatory or optional is an open item (07). INFERRED.
- **SID entity names** are the main resource names in each TMF API, which are derived from SID. We have not checked them against GB922 ABE by ABE. INFERRED.
- **TMF621 placement:** trouble ticket is often placed under Party or Customer management in ODA component designs. We keep it under Production for the demo because fallout comes from the service order. Verify against the ODA Component Directory. INFERRED.
- **Version mismatch:** Salesforce's managed-package TMF620 and TMF648 are v4, while TM Forum's stable TMF622 is v5. The stand-in must implement the same version the org exposes, so the switch is config only (ADR-004). RECOMMENDED.
- **Access method (CONFIRMED):** from Winter '27, Salesforce supports only the Direct Access option (Connect/Apex REST endpoints) for Comms Cloud inbound TMF APIs; the MuleSoft gateway option is deprecated ([TMF620 doc](https://developer.salesforce.com/docs/industries/communications/guide/TMF620.html)). These endpoints are shipped by Salesforce. These are Salesforce-shipped. Separately, TMF620, TMF622 (write), TMF648 and TMF671 are served by our own mapping-only Apex facades because the org has no working native API (CONFIRMED by the 2026-10-26 capability check; ADR amendment 001). TMF679 returns 400 natively and qualification is handled in our layer.
- **Salesforce prerequisites (CONFIRMED for TMF620):** permission set licences or a managed-package licence, datapacks and static resources must be installed ([TMF620 doc](https://developer.salesforce.com/docs/industries/communications/guide/TMF620.html)). This is configuration, not custom rules, but it must be checked on the trial org. UNKNOWN.

## Events
| Event | Producer | Topic (RECOMMENDED) | Shape |
|---|---|---|---|
| Intent received, plan proposed | L2 | `zg.intent` | TMF688-style envelope (eventId, eventType, eventTime, event) |
| Policy decision (allow/deny + reasons) | L5 (from OPA result) | `zg.policy` | as above |
| Order step started, done, failed, compensated | L5 | `zg.order` | as above, plus process instance ID and idempotency key |
| SoR change notifications | Salesforce Change Data Capture via Pub/Sub API, if enabled | `zg.sor.cdc` | Mapped from Salesforce change event to TMF688-style envelope in our adapter |

"TMF688-style" means we follow the event envelope pattern, without claiming TMF688 conformance. Salesforce Change Data Capture and Pub/Sub API are standard platform features ([CDC guide](https://developer.salesforce.com/docs/platform/change-data-capture/guide/cdc-subscribe.html)); which Comms Cloud objects support CDC on the trial org is UNKNOWN.

## Read path: Salesforce GraphQL (ADR-008)
| Item | Finding | Label |
|---|---|---|
| Endpoint | `https://{MyDomain}.my.salesforce.com/services/data/v{version}/graphql`, OAuth bearer token ([quick start](https://developer.salesforce.com/docs/platform/graphql/guide/get-started-graphql.html)) | CONFIRMED |
| Scope | Queries go through `uiapi.query`; only UI API-supported objects (and custom objects) are queryable, subject to the user's object and field permissions ([Query Objects](https://developer.salesforce.com/docs/platform/graphql/guide/query-record-objects.html)) | CONFIRMED |
| Mutations | Exist (GA from API v66.0) ([Schema Conventions](https://developer.salesforce.com/docs/platform/graphql/guide/schema-conventions.html)). **We do not use them**; writes stay on TMF APIs. | CONFIRMED / RECOMMENDED |
| Comms Cloud objects available via UI API | Not checked | UNKNOWN |
