# 08 · Sources

Accessed 24–26 Oct 2026. "Status" = how the source was checked for this pack.

## Zero Gravity and TechM
| # | Source | Used for | Status |
|---|---|---|---|
| Z1 | TechM, *Zero Gravity Telco Architecture™* report (PDF, 55 pp.), 9 Sep 2026: https://insights.techmahindra.com/assets/zero-gravity-telco-architecture.pdf | 8 layers, Figure 3 (p.21), Axiom (p.24), L5 description, Token Economics (printed p.35), operating model costs | Read in full (local text copy `/workspace/zg.txt`) |
| Z2 | TechM press release, 9 Sep 2026: https://www.techmahindra.com/insights/press-releases/techm-unveils-zero-gravity-telco-architecture-to-accelerate-ai-native-telco-transformation/ | Launch context | From earlier analysis |
| Z3 | TechM whitepaper page: https://www.techmahindra.com/insights/whitepapers/zero-gravity-telco-architecture/ | Context | From earlier analysis |
| Z4 | Internal analysis `/workspace/zero-gravity-analysis.md` (v2) | Layer-to-ODA mapping, gaps (no TMF API numbers, no Salesforce role, no certification, projected value claims) | Internal |
| Z5 | MWC Barcelona themes: https://www.mwcbarcelona.com/themes | Autonomous Enterprise theme sponsor | Sponsor name not readable in page text (REPORTED) |

## TM Forum
| # | Source | Status |
|---|---|---|
| T1 | Conformance certification: https://www.tmforum.org/oda/conformance-certification/ | Fetched |
| T2 | Open API directory: https://www.tmforum.org/open-digital-architecture/open-apis | Link checked |
| T3 | TMF921 Intent Management v5.0: https://www.tmforum.org/open-digital-architecture/open-apis/intent-management-api-TMF921/v5.0 | Link checked |
| T4 | TMF622 Product Ordering v5.0: https://www.tmforum.org/open-digital-architecture/open-apis/product-ordering-management-api-TMF622/v5.0 | Link checked |
| T5 | TMF API repositories: https://github.com/tmforum-apis (TMF620_ProductCatalog, TMF621_TroubleTicket, TMF622_ProductOrder, TMF629_CustomerManagement, TMF632_PartyManagement, TMF637_ProductInventory, TMF641_ServiceOrder, TMF648_QuoteManagement, TMF679_ProductOfferingQualification, TMF688-Event, TMF921_Intent) | Links checked |
| T6 | TMF448 AI Native ODA Roadmap v1.0.0: https://www.tmforum.org/resources/technical-specification/tmf448-ai-native-oda-roadmap-v1-0-0/ | Blocks automated access; REPORTED via earlier analysis |
| T7 | ODA Canvas: https://www.tmforum.org/oda/deployment-and-runtime/oda-canvas | From earlier analysis |
| T8 | TR292 Intent Ontology: https://www.tmforum.org/resources/introductory-guide/tr292-tm-forum-intent-ontology-tio-v3-6-0/ | From earlier analysis |

## Salesforce
| # | Source | Used for | Status |
|---|---|---|---|
| S1 | TMF conformance and availability: https://developer.salesforce.com/docs/industries/communications/guide/TMF_compliance.html | Certified APIs; managed package vs Platform lists | Fetched |
| S2 | TMF620 guide: https://developer.salesforce.com/docs/industries/communications/guide/TMF620.html | Direct Access only from Winter '27; MuleSoft gateway deprecated; OAuth connected app; prerequisites | Fetched |
| S3 | Industry integrations (TMF641 outbound): https://developer.salesforce.com/docs/industries/communications/guide/get_started_industry_integrations.html | TMF641 outbound via MuleSoft Direct Integrations | Fetched |
| S4 | TMF641 reference: https://developer.salesforce.com/docs/industries/communications/references/tmf641/v67.0 | As above | Fetched |
| S5 | GraphQL quick start: https://developer.salesforce.com/docs/platform/graphql/guide/get-started-graphql.html | Endpoint, auth | Fetched |
| S6 | GraphQL query objects: https://developer.salesforce.com/docs/platform/graphql/guide/query-record-objects.html | UI API-supported objects, permissions | Fetched |
| S7 | GraphQL schema conventions: https://developer.salesforce.com/docs/platform/graphql/guide/schema-conventions.html | Mutations GA v66.0 | Fetched |
| S8 | Change Data Capture subscribe: https://developer.salesforce.com/docs/platform/change-data-capture/guide/cdc-subscribe.html | CDC via Pub/Sub API | Fetched |
| S9 | Pub/Sub API Python quick start: https://developer.salesforce.com/docs/platform/pub-sub-api/guide/qs-python-quick-start.html | OAuth recommended for production | Fetched |
| S10 | Internal deck text `/workspace/agentictelco-src-zg-north-star-salesforce.pptx.txt` | Earlier Salesforce mapping | Internal |

## Open source and licences
| # | Source | Status |
|---|---|---|
| L1 | Operaton FAQ: https://operaton.org/faq/ | Fetched |
| L2 | Camunda licences: https://docs.camunda.io/docs/reference/licenses/ | Fetched |
| L3 | Camunda licensing blog, Oct 2024: https://camunda.com/blog/2024/10/camunda-licensing-what-you-need-to-know/ | Fetched |
| L4 | Camunda 7 CE end-of-life strategy update, Feb 2025: https://camunda.com/blog/2025/02/migrating-solutions-camunda-7-camunda-8-strategy-update/ | Link checked |
| L5 | PostgreSQL licence: https://www.postgresql.org/about/licence/ | Link checked |
| L6 | Project LICENSE files on GitHub, listed per component in [06](06-tech-stack-and-licences.md) | Raw LICENSE files read 26 Oct 2026 |
