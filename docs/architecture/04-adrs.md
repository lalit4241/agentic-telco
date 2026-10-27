# 04 · Architecture decision records

Status key: **Accepted** = agreed in the working group and approved by the user (LalitC). **Proposed** = agreed in principle, details open.
Date for all records: 26 Oct 2026.

| ADR | Title | Status |
|---|---|---|
| [001](#adr-001-salesforce-communications-cloud-is-only-the-l6-system-of-record) | Salesforce Communications Cloud is only the L6 system of record | Accepted |
| [002](#adr-002-strictly-open-source-for-every-other-layer) | Strictly open source for every other layer | Accepted |
| [003](#adr-003-agents-start-and-read-processes-they-never-execute-them) | Agents start and read processes; they never execute them | Accepted |
| [004](#adr-004-fastapi-sor-stand-in-behind-the-same-tmf-contracts) | FastAPI SoR stand-in behind the same TMF contracts | Accepted |
| [005](#adr-005-security-of-the-demo-page-and-salesforce-credentials) | Security of the demo page and Salesforce credentials | Accepted |
| [006](#adr-006-hosting-password-gated-replay-plus-one-command-local-stack) | Hosting: password-gated replay plus one-command local stack | Accepted |
| [007](#adr-007-operaton-as-the-l5-bpmn-engine) | Operaton as the L5 BPMN engine | Accepted |
| [008](#adr-008-graphql-for-reads-only-tmf-rest-for-all-writes) | GraphQL for reads only; TMF REST for all writes | Accepted |
| [009](#adr-009-inference-gateway-as-a-shared-platform-service) | Inference Gateway as a shared platform service (our extension) | Accepted |

---

## ADR-001 Salesforce Communications Cloud is only the L6 system of record
> **Amended 2026-10-27 (confirmed by LalitC):** where the org has no working native TMF API, thin Apex REST facades in TMF shapes (`AgenticTelco_*`, `/services/apexrest/agentictelco/tmf<NNN>/`) are allowed in the org. They only map records to TMF shapes and hold no business rules, policy or orchestration, which stay in L4/L5. See [ADR amendment 001](../adr-amendments/001-custom-tmf-apis-on-salesforce.md). The "no custom Apex" bullet below is superseded to that extent.

**Context.** The Zero Gravity Axiom says rules and policies have "zero residual" in systems of record (report PDF p.24). Salesforce Communications Cloud can also host agents (Agentforce), automation (Flow) and custom code (Apex). Using those would put rules back into the SoR and contradict the thesis the demo exists to show.

**Decision.**
- Salesforce Communications Cloud is used **only** as the L6 SoR for party, catalogue, quote, order and product inventory state.
- Access is only through out-of-the-box APIs: the TMF Open APIs the org exposes, standard REST and query APIs, the standard GraphQL API for reads (ADR-008) and change events (Change Data Capture via Pub/Sub API).
- **No** Agentforce, Flow, custom Apex, validation rules or other custom logic added to the org.
- Inbound TMF APIs are called through Salesforce's **Direct Access** (Connect/Apex REST) endpoints. Salesforce states the MuleSoft gateway option is deprecated from Winter '27 ([TMF620 doc](https://developer.salesforce.com/docs/industries/communications/guide/TMF620.html), CONFIRMED).

**Alternatives considered.** (a) Agentforce for Communications as the L2 agent layer; (b) Flow or Apex for order orchestration; (c) MuleSoft TMF gateway. All rejected: (a) and (b) put logic in the SoR; (c) is deprecated.

**Consequences.**
- The demo shows the Axiom cleanly. INFERRED.
- Out-of-the-box configuration still embeds some logic (for example catalogue structure, CPQ pricing, built-in order decomposition). We treat that as SoR configuration and show it, not hide it. Where it overlaps with OPA policy, OPA decides first. INFERRED.
- Anything the org does not expose has to come from the stand-in (ADR-004).
- Salesforce-shipped prerequisites (datapacks, static resources, permission set licences) are still needed for the TMF APIs. CONFIRMED for TMF620.

## ADR-002 Strictly open source for every other layer
**Context.** The user requires every non-Salesforce component to be open source, usable in production without a commercial licence. Several popular choices are source-available, not open source.

**Decision.** Use OSI-approved licences only. Selected per layer (licences checked in [06](06-tech-stack-and-licences.md)):

| Layer | Selected | Alternatives considered |
|---|---|---|
| L1 | React; TMF921-style intents; optional Strawberry GraphQL BFF | Vue/Nuxt, SvelteKit, Angular |
| L2 | LangGraph agents over A2A and MCP | CrewAI, AutoGen/AG2, Google ADK, Semantic Kernel, LlamaIndex |
| L3 | PostgreSQL + pgvector; Apache Kafka for TMF688-style events | Qdrant, Milvus, Weaviate; Pulsar, NATS JetStream |
| L4 | Open Policy Agent (credit, consent, network capacity, model allow-list; live toggle) | Cedar, OpenFGA, Casbin |
| L5 | Operaton (ADR-007) | Temporal, Flowable, Netflix/Orkes Conductor, Postgres saga log |
| L7 | Docker Compose; optional k3s; Inference Gateway (ADR-009) | Kubernetes, Knative, Dapr |
| L8 | OpenTelemetry, Jaeger, Prometheus, Grafana, Langfuse | Tempo, SigNoz, Arize Phoenix |

**Rejected on licence:** Redpanda (BSL 1.1), Camunda 8 (Camunda License 1.0 source; production use needs Enterprise licence), Restate (BSL 1.1). Licence texts CONFIRMED in [06](06-tech-stack-and-licences.md).

**Consequences.**
- No production licence fees for the stack. CONFIRMED for selected components' licences.
- Some projects are "open core": Langfuse and LiteLLM have separately licensed `ee/` or `enterprise/` directories. We use only the MIT-licensed core. CONFIRMED (licence files).
- Grafana is AGPL-3.0: open source, but changes to Grafana itself that are offered over a network must be shared. We do not modify Grafana. INFERRED.
- A component licence list must ship in the repo and be re-checked before each public release. RECOMMENDED.

## ADR-003 Agents start and read processes; they never execute them
**Context.** Telco order and fallout teams need determinism and audit. LLM agents are non-deterministic. The Zero Gravity report describes L5 as "auditable, predictable, fully compensated" (report p.22).

**Decision.**
- L2 agents may only **start** a BPMN process instance and **read** its state and history.
- Agents may **never** complete, skip, cancel or modify BPMN tasks or variables, and never write to any SoR.
- **Every** BPMN task that writes to Salesforce (or the stand-in) calls OPA first.
- A policy deny is an **explicit BPMN path** (visible on the diagram), not an agent's judgement.
- OPA and BPMN steps never call a language model.

**Enforcement (RECOMMENDED).** Agents get an Operaton API identity whose authorisations allow only process start and read. The task-completion and modification REST operations are denied. The rule is tested: a test tries to complete a task with the agent identity and must fail.

**Alternatives considered.** Agents calling TMF APIs directly through MCP tools (rejected: no compensation, no deterministic audit); agents completing human or service tasks (rejected: blurs accountability).

**Consequences.** Clear split: agents propose, BPMN executes, OPA decides. Less agent autonomy in the demo by design. Operaton also publishes an MCP server that can work with tasks ([Operaton FAQ](https://operaton.org/faq/), CONFIRMED); if used, it must be limited to read and start operations. RECOMMENDED.

## ADR-004 FastAPI SoR stand-in behind the same TMF contracts
**Context.** Which TMF APIs the trial org exposes is UNKNOWN. The demo must run without a licensed org, and switching to a real org must not need code changes.

**Decision.**
- A FastAPI service implements the same TMF API resources and versions the demo uses.
- Swapping between stand-in and Salesforce is a configuration switch per API.
- Anything served by the stand-in is labelled **"stand-in"** on screen and in traces.
- The trial org (Comms Cloud 30-day trial on Salesforce Platform, REPORTED as created) is probed per API; results are recorded in the repo.

**Alternatives considered.** TM Forum reference implementations (possible later; versions and licences to check); WireMock-style static mocks (rejected: no state for order lifecycle).

**Consequences.** The demo never depends on the org being up. The risk is drift between the stand-in and Salesforce's actual payloads; contract tests against the TMF OpenAPI files and recorded org responses reduce it. RECOMMENDED.

## ADR-005 Security of the demo page and Salesforce credentials
**Context.** The demo is shared with an executive and partner audience. Salesforce credentials must never leak.

**Decision.**
- The public demo page is a static page encrypted with AES-GCM. The password comes from an environment variable at build time and is never committed.
- Salesforce credentials live server-side only, injected at runtime. Never in the browser, the static site, the repo or chat.
- An OAuth connected app (for example the client credentials or JWT bearer flow) is **recommended** over a stored username and password. Salesforce's own TMF620 guide says to use a connected app and OAuth 2.0 ([TMF620 doc](https://developer.salesforce.com/docs/industries/communications/guide/TMF620.html), CONFIRMED).

**Alternatives considered.** Basic auth on a hosted server (needs a server); GitHub private Pages (needs GitHub Enterprise plan; not checked).

**Consequences.** Client-side encryption means anyone with the file can try passwords offline, so the password must be long and random and rotated after events. INFERRED. Details in [05](05-security-and-governance.md).

## ADR-006 Hosting: password-gated replay plus one-command local stack
**Context.** Live demos at events fail on network and credentials. Viewers still need to trust that what they see is real.

**Decision.**
- GitHub Pages serves a password-gated **replay of real recorded runs** (events, traces, process states), clearly marked as a replay.
- The full stack runs locally or on a VM with one command (`docker compose up`).

**Alternatives considered.** Hosted live stack on a cloud VM (cost, attack surface, credentials on the internet); video only (not inspectable).

**Consequences.** Recordings must be real runs, with run ID and date shown, and must contain no customer data or credentials. RECOMMENDED.

## ADR-007 Operaton as the L5 BPMN engine
**Context.** Order and fallout teams read BPMN. Camunda 7 Community Edition reached end of life in October 2025 ([Camunda announcement](https://camunda.com/blog/2025/02/migrating-solutions-camunda-7-camunda-8-strategy-update/), CONFIRMED via the Operaton FAQ and Camunda blog). Camunda 8 Self-Managed from 8.6 needs a commercial licence for production ([Camunda licensing docs](https://docs.camunda.io/docs/reference/licenses/), CONFIRMED).

**Decision.** Use **Operaton**, the community fork of Camunda 7 CE: Apache 2.0, free for production, REST API compatible with Camunda 7 ([Operaton FAQ](https://operaton.org/faq/), CONFIRMED). Every service task is idempotent (key = process instance + step) and each forward step persists its compensation before the next step runs. The process diagram is drawn live in the UI.

**Alternatives considered.**
| Option | Why not chosen |
|---|---|
| Temporal (MIT) | Strong saga support, but workflows are code, not BPMN; less readable to order teams. Kept as fallback. |
| Flowable (Apache 2.0) | Viable BPMN engine; Operaton chosen for Camunda 7 familiarity and tooling. |
| Conductor (Apache 2.0) | JSON workflows, not BPMN. |
| Postgres saga log | Simplest, but no visual process model. |
| Camunda 8 | Not open source for production. |
| Restate | BSL 1.1. |

**Consequences.**
- Operaton supports each minor version for about six months, with no LTS line ([Operaton FAQ](https://operaton.org/faq/), CONFIRMED). We pin a version.
- If the live diagram uses bpmn-js, its licence requires the bpmn.io watermark to stay visible ([bpmn-js licence](https://github.com/bpmn-io/bpmn-js/blob/develop/LICENSE), CONFIRMED). We keep it.
- **Status note (CONFIRMED at time of writing):** DevBot reported the switch to Operaton in the working group, but the L5 code on the shared machine (`stack/l5_orchestrator/workflow.py`) was still a Temporal workflow when this pack was written. Recheck before publishing.

## ADR-008 GraphQL for reads only; TMF REST for all writes
**Context.** The care agent and UI need a single customer view (party, products, open orders) and a single view of our own state (context, process state, traces). Calling many REST APIs per screen is slow and noisy. But TMF contracts must stay the write interface to the SoR.

**Decision.**
1. **Salesforce standard GraphQL API** (`/services/data/vXX.X/graphql`, `uiapi.query`) is used **only** as an optional **L3 read path** to aggregate a customer view. Results are mapped to SID-aligned entities in our layer. ([Salesforce GraphQL docs](https://developer.salesforce.com/docs/platform/graphql/guide/query-record-objects.html), CONFIRMED that it exists and is read via UI API-supported objects.)
2. **All SoR writes stay on TMF REST APIs** (TMF679, TMF648, TMF622 and the others in [03](03-api-event-sid-mapping.md)), called only by BPMN tasks. Salesforce GraphQL mutations (GA from API v66.0) are **not** used.
3. DevBot is adding an **open-source GraphQL layer in front of our own services**, so the UI can fetch customer context, order state and traces in one query. Strawberry (Python, MIT) is the default; Apollo Server (MIT) is the alternative. It is read-only for SoR data; actions such as "start process" stay as explicit calls.

**Alternatives considered.** REST-only aggregation in a BFF; Salesforce Composite API; Apollo Router/GraphOS federation (rejected: Apollo Router is Elastic License 2.0, not open source; [licence](https://github.com/apollographql/router/blob/dev/LICENSE), CONFIRMED).

**Consequences.**
- Salesforce GraphQL only sees UI API-supported objects and respects user permissions. Whether the Comms Cloud objects we need are queryable is UNKNOWN.
- Two read shapes exist (TMF and GraphQL). The SID mapping in our layer is the single vocabulary. RECOMMENDED.
- The GraphQL layer must not become a back door for writes. Tests check that no mutation reaches the SoR. RECOMMENDED.

## ADR-009 Inference Gateway as a shared platform service
**Context.** Agents need several models: small and fast for classification, stronger for planning, local for customer data. The Zero Gravity report discusses the **cost** of inference ("Token Economics", printed p.35; and costing "inference costs and governance overhead" in its operating-model section) and says deterministic queries should be resolved "without invoking a language model at all". It defines **no inference layer or gateway**. This ADR is **our extension**. INFERRED/RECOMMENDED.

**Decision.**
- An **Inference Gateway** is a shared platform service **hosted in L7**, **consumed by L2** agents, **governed by L4** (OPA model allow-list) and **metered in L8** (Langfuse). It is not a ninth layer.
- Stack: **LiteLLM** proxy (MIT core; `enterprise/` directory separately licensed and not used) as gateway and router; **vLLM** (Apache 2.0) or **Ollama** (MIT) serving open-weight models locally.
- Capabilities:
  - model routing by task type;
  - data residency: OPA allow-list rule, for example "prompts with customer personal data go only to local or UK-sovereign models" (UK GDPR);
  - PII stripping or masking before any prompt leaves our boundary;
  - per-call budgets, response caching and provider fallback;
  - every prompt, model, token count and cost traced to Langfuse.
- OPA policies and Operaton BPMN steps **never** call a model (ADR-003).

**Alternatives considered.** Agents calling providers directly (no central policy or metering); a dedicated "inference layer" as L9 (rejected: changes the report's model).

**Consequences.**
- One place to enforce residency and cost. INFERRED.
- The gateway is on the critical path for agents, not for order execution, so an outage degrades explanation and planning but not BPMN execution. INFERRED.
- Which LiteLLM features (budgets, caching, fallback, PII masking hooks) are in the MIT core versus the enterprise directory must be checked per feature before we claim them. UNKNOWN.
- The PII-stripping method (for example rule-based or an open-source detector such as Microsoft Presidio, MIT) is not yet chosen. UNKNOWN.
