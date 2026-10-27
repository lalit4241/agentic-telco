# AgenticTelco — powered by Zero Gravity Framework
## Architecture documentation pack

**Audience:** TechM leadership and telco architects (MWC27 Autonomous Enterprise theme).
**Status:** working draft, 26 Oct 2026 (Europe/London). It describes the demo as agreed so far. It is not a product description and makes no conformance claim.

### Evidence labels used throughout
| Label | Meaning |
|---|---|
| **CONFIRMED** | A primary source (vendor doc, standard, licence file, report) states it; link given. |
| **REPORTED** | Stated by a vendor or third party but not checked against a primary source, or a vendor claim. |
| **INFERRED** | Our analysis or interpretation. |
| **RECOMMENDED** | Our proposal or design choice. |
| **UNKNOWN** | Not yet known or verified. |

"Our extension" marks anything we add that the Zero Gravity report does not define (for example the Inference Gateway).

### Contents
| File | What it covers |
|---|---|
| [01-architecture-overview.md](01-architecture-overview.md) | Executive summary, system context, 8-layer model diagram, responsibility matrix |
| [02-sequence-and-flows.md](02-sequence-and-flows.md) | Sequence diagrams: happy path, policy block, compensation and fallout |
| [03-api-event-sid-mapping.md](03-api-event-sid-mapping.md) | TMF Open APIs, ODA functional blocks, SID entities, Salesforce vs stand-in |
| [04-adrs.md](04-adrs.md) | Architecture decision records (ADR-001 to ADR-009) |
| [05-security-and-governance.md](05-security-and-governance.md) | Secrets, access, agent guardrails, data protection, audit |
| [06-tech-stack-and-licences.md](06-tech-stack-and-licences.md) | Every component, its layer and its licence, checked against the licence file |
| [07-risks-open-items-roadmap.md](07-risks-open-items-roadmap.md) | Risks, open items to verify, roadmap |
| [08-sources.md](08-sources.md) | All sources with links |

### Three things to read first
1. **ODA alignment here is conceptual, not certified.** We map the demo to ODA functional blocks and TMF Open APIs. Neither the demo nor the Zero Gravity framework has ODA Component or Open API conformance certification. Salesforce's certified APIs are Salesforce's certifications, not ours. See [03](03-api-event-sid-mapping.md#conceptual-alignment-vs-certified-conformance).
2. **Salesforce Communications Cloud is only the system of record (L6).** It is used through out-of-the-box APIs. No Agentforce, Flow or custom rules are added to the org. Where a TMF API isn't native, a thin Apex REST facade in TMF shapes is allowed, with no business logic (ADR-001 as amended by [ADR amendment 001](../adr-amendments/001-custom-tmf-apis-on-salesforce.md)).
3. **Everything else is open source**, and the licence of each component was checked against its licence file (see [06](06-tech-stack-and-licences.md)).

### Diagram validation
All Mermaid diagrams in this pack were rendered with `@mermaid-js/mermaid-cli` (see [07, "Pack maintenance"](07-risks-open-items-roadmap.md#5-pack-maintenance)).
