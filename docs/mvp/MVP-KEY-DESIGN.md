# AgenticTelco MVP: key design

**Status: AGREED v1.0 — LalitC [x] (signed off 30 Oct 2026: "This is the approach it has been agreed for MVP - let's go ahead and build it") DevBot [x] (agreed subject to the decision 6 edit, 27 Oct 2026) TMForumCTO [x] (agreed)**

v1.1 (30 Oct 2026): TMF-only API presentation; hosting and runtime wording removed. Agreed by LalitC.

27 Oct 2026. This is the one document all three must agree before any development starts. It consolidates [MVP-design.md](MVP-design.md) and [layer-walkthrough.md](layer-walkthrough.md). The walkthrough is superseded (30 Oct 2026) and kept for history only; the on-screen wording is in [layer-panels.md](layer-panels.md). Where they differ, this document wins once agreed.

Labels: CONFIRMED (checked in a primary source or our own org/code), REPORTED (stated by others, not checked), INFERRED (our analysis), RECOMMENDED (our proposal), UNKNOWN. Customer names, IDs and prices are examples. Layer names follow TechM's Zero Gravity report. Everything else is our design, not the report's.

## 1. Purpose

**In one line:** prove that a telco can put AI agents in front of customers safely, on its existing Salesforce estate, without rewriting its business rules.

Three reasons:
1. **For TechM.** Zero Gravity is a framework on paper today: eight layers and the rule that no business rules stay in systems of record. The report has no worked example, no named customer and no Salesforce role (CONFIRMED). This makes it real on one journey, for the MWC27 Autonomous Enterprise theme (TechM's sponsorship of the theme is REPORTED).
2. **For a telco CIO or CTO.** It answers three fears. Replacing the BSS: Salesforce and the rest of the estate stay. Losing control to AI: policy decides, not the model. Lock-in: open source plus industry-standard telco APIs (TM Forum Open APIs).
3. **For TechM's Salesforce practice.** It positions Salesforce as the trusted system of record in an agentic telco.

**Legacy reality (INFERRED, general industry patterns).** CIOs can't simply "go agentic". Rules are buried in old CRM code, customised flows and billing configuration. Mergers leave duplicate stacks. Data is messy: address formats, duplicate customers, thousands of old tariffs. Fulfilment runs through batches, manual queues and vendor systems without APIs. Bolting an agent on top of that is what the CIO fears. The MVP shows the alternative on one journey: wrap the legacy, extract the rule, resolve the identities, then let the agent act.

**Rule:** anything in the demo that doesn't serve this purpose is cut.

## 2. Setting: "UK Telco" (fictional)

UK Telco is an invented Tier 1 UK operator. It is illustrative only and is not any real operator. Salesforce is one system among several:

| System | Role | Quirk (stand-in behaviour) | In the MVP |
|---|---|---|---|
| Salesforce Communications Cloud | System of record for the SME segment: customer, contacts, site, products, quotes, orders, installed services | Customised over the years (section 6) | **Real** |
| Billing B (one of two billing systems from a merger) | Account balance | Its own customer ID (`BIL-B-0077812`); slow to answer | Legacy stand-in (mocked) |
| Network inventory | Sites, exchange ports | Its own site ID (`4471`) | Legacy stand-in (mocked) |
| Availability | What can be delivered at an address key | Data refreshed only overnight | Legacy stand-in (mocked) |
| Legacy OSS | Network fulfilment | Overnight batches; no modern API | Legacy stand-in (mocked) |

The same business customer exists under three IDs. All IDs are examples.

## 3. Journey and cases

**Customer (example):** Brightwell Design Ltd, a 25-person design agency at 1 Fibre Way, Martlesham, Ipswich IP5 3RE. The postcode is real: BT Adastral Park, home of BT's research labs since 1975. The street, business and address key `A00000001975` are examples. Brightwell is on AgenticTelco Fibre 150, 14 months into a 24-month contract, and expanding. Sam is the authorised contact (Account Contact Role "Decision Maker"). A regular employee has the role "Business User" and is not authorised.

**Happy path:**
1. Sam signs in to the business portal and describes the problem in plain words.
2. The agent gets the context: company, Sam's role, the site, the current Fibre 150 service, the contract position, the balance and what is available at the address key.
3. The agent confirms the site with Sam.
4. **Advisory policy check.** The same policy that later binds the workflow runs first. The agent only offers what Sam is allowed to buy.
5. The agent recommends Fibre 900, with its price and contract effect (decision 1).
6. Sam accepts, and consent is recorded.
7. The agent proposes the filled Intent. The intent service validates it (schema, plus the policy check that Sam is an authorised contact) and records it. The upgrade proposal then goes to the workflow, whose **binding policy check** runs before any write.
8. The workflow creates the quote and places an upgrade order from Fibre 150 to Fibre 900.
9. Fulfilment starts in the legacy OSS. Its overnight batch reports that no exchange port is free yet, and the date moves by two days. The order stays in progress.
10. The agent tells Sam the new date proactively.
11. The port is reserved and the service is activated. The order is completed.
12. **End state:** the Fibre 150 installed service is set to Obsolete with an end date. One Fibre 900 installed service is active at the same location and linked to the old one (decision 6). Sam is told it is live.

**Cases:**

| Case | What happens | Who decides |
|---|---|---|
| Happy path with a legacy-caused jeopardy | As above, ending with a working Fibre 900 service | L5 raises the jeopardy from the legacy OSS; the agent tells Sam |
| Not authorised (Business User) | The advisory check fails. The agent politely explains it can't place the order and points to the Decision Maker. No offer, no quote, no order | L4 policy |
| Overdue balance | The advisory check fails. The agent explains and offers a payment link (mocked). No order | L4 policy |
| Identity not certain (safety rule, not a demo button) | The workflow stops and raises the case for human review | L3 / L5 |

## 4. The eight layers

**Rule: the agent proposes, policy decides, the workflow writes.** The agent never bypasses business rules, authorisation, consent or financial controls, and never writes to a system of record.

| Layer | Question it answers | What it does | Tech (licence) | Artefact shown | Real / mocked |
|---|---|---|---|---|---|
| L1 Intent & Experience | What does Sam want? | Portal chat; the need becomes an Intent [TMF921] | React (MIT); small intent service (ours) | Intent and its reports | Real; demo sign-in |
| L2 Agent Mesh | What should we offer and why? | One agent: understands, gets context, recommends, explains, tells Sam about delays | LangGraph (MIT), MCP SDK (MIT), small local model via Ollama (MIT) | Plan, tool calls, model calls and tokens | Real |
| L3 Data Foundation | What do we remember? | Conversation, decisions, consent, workflow and jeopardy history, audit; identity cross-reference | PostgreSQL (PostgreSQL Licence) | Cross-reference rows, audit rows | Real; IDs are examples |
| L4 Enterprise Context | What do we know, and is it allowed? | Semantic definitions, context pack with sources, policy decision | Context service (ours), OPA (Apache-2.0) | Context pack, policy decision and rule | Real; balance and availability are stand-ins |
| L5 Deterministic Execution | Who actually does the work? | One BPMN process: binding check, quote, order, fulfilment wait, jeopardy, asset change; idempotent; absorbs slow and batch legacy | Operaton (Apache-2.0), Python workers (ours) | BPMN diagram, current step highlighted | Real; OSS is a stand-in |
| L6 Agent-Ready SoR | Where is the truth recorded? | Salesforce, plus legacy stand-ins, each behind a standard API | Salesforce (commercial), exposed only through TM Forum Open APIs: two out of the box, the rest from a thin TMF facade layer within Salesforce (Apex, ours) | Each call, shown by its TMF API number and labelled "TMF Open API (Salesforce)" or "Legacy stand-in (mocked)", with record links; the detail drawer says whether Salesforce provides it out of the box or our facade does | Salesforce real |
| L7 Digital Core | What does it run on, and where does the order reach the network? | Mocked network view of Brightwell's site (exchange, fibre path, access port changing from 150 to 900) plus the platform in one line | Mock panel | Network view for site 4471, platform line | Target state mocked, labelled |
| L8 Observability & Governance | How do we prove what happened? | Step timeline per request across all layers (agreed by LalitC, 27 Oct 2026) | Built from the L3 audit log | Step timeline | Real data from each run |

**L1.** Sam types "We're hiring 15 people and moving to cloud video editing; the line can't keep up." Sam never has to name a product. The agent fills a structured **Intent** [TMF921] and submits it as a proposal. The Intent states an outcome, not a product. For example: "support 15 more staff and cloud video at the Martlesham site, no extra visits, within contract, by 30 Nov 2026" (example date). Fibre 900 is the agent's recommendation in answer to the Intent; the Intent never names it. Progress comes back as **IntentReports**: a delay means "intent at risk, revised date", and Fibre 900 going live closes the Intent as fulfilled.

TMF921 is designed mainly for intent handover between autonomous-network layers (INFERRED from the spec). Using it at the customer edge is our design choice (RECOMMENDED), and we say so. It is TMF921-shaped and not conformance-tested; the expression is simplified. A small intent service in L1 validates and records the Intent; it is stored in L3 Postgres, not in Salesforce (decision 8). No voice or other channels in the MVP.

**L2.** One agent with three tools: get context, start the upgrade, read order status. It has no write tools to any system of record: it proposes the Intent to the intent service and the upgrade to the workflow, which does every write. It never sees a legacy system, a legacy ID or a batch job. Its recommendation is reasoning ("15 more people and cloud video need more than 150 Mbps"). Whether an offer is allowed comes from the advisory policy check, never from the model.

**L3.** One Postgres database. It holds the conversation, the context pack used, both policy decisions, consent, workflow state, Intents and IntentReports (their system of record), jeopardy and milestone history, and audit. It also holds the identity cross-reference (section 6). This is an operational database, not the lakehouse and data products the report describes for L3 (INFERRED).

**L4.** The semantic file defines each business term once ("authorised contact", "in contract", "available at site") and says where it comes from. It also holds a plain-English glossary, which is the source the model explains from. The context service builds one context pack per request from the identity L3 has resolved. Each fact is tagged with its source: Salesforce, or legacy stand-in. The **same OPA rule runs twice**: advisory before the recommendation, binding in the workflow before any write. The rule checks four things: authorised contact, no overdue balance, available at the site, and upgrade-only mid-contract.

**L5.** One BPMN process on Operaton (decision 4) does every system-of-record write. It runs the binding policy check, quote, upgrade order and the fulfilment wait. A timer raises the delay and the revised date. The process decides each Intent state change: at risk = `icm:StateDegrades`, fulfilled = `icm:StateComplies` (INFERRED mapping). It posts these as IntentReports to the intent service. It then makes the asset change. The order external ID is the business key, so reruns can't double-write. Python workers absorb slow and batch legacy systems.

**L6.** Salesforce keeps the records and nothing else. Everything above L6 reaches Salesforce only through TM Forum Open APIs, labelled "TMF Open API (Salesforce)" (LalitC, 30 Oct 2026). Two come out of the box from Salesforce: the customer record [TMF629] and reading one installed service by its ID [TMF637 get-by-id]. A thin, mapping-only TMF facade layer within Salesforce (Apex) provides the rest: the organisation and its contact roles [TMF632], listing, creating and updating installed services and linking them as an upgrade [TMF637 list/create/update/relationship], catalogue [TMF620], quote [TMF648], order [TMF622] and promotion [TMF671] (ADR amendment 001, approved by LalitC). The usage record our demo org expects on each order is created inside the TMF622 order, not as a separate call. The facades live in the Salesforce org, not in a separate integration tier, and hold no business rules. Nothing above L6 uses SOQL or sObject REST; a test and a runtime guard enforce that. The legacy stand-ins (billing [TMF666], availability [TMF679], network inventory [TMF639], network fulfilment [TMF641]) are mocked behind TMF-shaped adapters. The overdue-balance payment link is mocked and is not a TMF API. The claim is "TMF-aligned" only. The Intent [TMF921] is not in Salesforce (decision 8). Every legacy system sits behind an adapter speaking a standard API. A system that can't be adapted is wrapped, and systems are replaced one at a time.

**L7.** Mocked in the MVP (decision 9). The L7 card leads with a network view of Brightwell's site, labelled "mocked, operator's digital core (network and edge)": the exchange, the fibre path to Martlesham and the access port, whose capacity changes from 150 to 900 at the moment the OSS step completes. It uses the same site ID 4471 as the L6 inventory stand-in. The records about the network (inventory, site, OSS order) stay in L6; L7 is the network and platform itself. A note says "network view is our illustration": the Zero Gravity report (p. 17) names network virtualisation and edge in L7 but does not place physical assets (INFERRED). Underneath, one line lists the platform target state: Kubernetes, secrets vault, network zones, API gateway, agent and workload identity, event bus. The card makes no hosting or runtime statement. The plumbing underneath is real but not presented as a feature; Salesforce credentials are kept server-side.

**L8.** A step timeline per request, built from the L3 audit log (agreed by LalitC, 27 Oct 2026). It shows each layer's step and its timing, both policy decisions and the model token counts. Each step carries a trace ID and timing fields in OpenTelemetry shape, so moving to OpenTelemetry and Jaeger later is configuration, not a rewrite (roadmap).

## 5. Tech view

| Layer | MVP job | Technology | Real or mocked | Out of scope for now |
|---|---|---|---|---|
| L1 Intent | Sam's free-text need becomes a TMF921 Intent (proposed by the agent, validated and recorded by the intent service); progress and delay come back as IntentReports | Web chat in a separate MVP mode of the demo; TMF921-shaped Intent and IntentReport (simplified expression; v5.0.0 verified), hosted by a small intent service in L1, stored in L3 Postgres; IntentReports posted by the BPMN process to the intent service | Real when run live; the public site replays recorded runs, labelled "recorded run" | Rich UI, full TM Forum Intent Ontology expression, intent negotiation, multi-layer intent handlers |
| L2 Agent | One agent: understands the need, gets context, recommends Fibre 900 and explains why, tells Sam about delays. Proposes only, never writes | LangGraph agent with 3 tools (get context, request upgrade, order status) over MCP; small local model via Ollama (Qwen3-4B-Instruct-2507, Apache 2.0; scripted fallback) | Real | Agent mesh, A2A, multiple models |
| L3 Data | Conversation, decisions, audit, the customer ID cross-reference (Salesforce Account, billing ID BIL-B-0077812, inventory site 4471, address key A00000001975), order milestones and delay history, Intents and IntentReports (system of record) | Postgres | Real | Kafka, pgvector, semantic cache |
| L4 Enterprise Context and Policy | Business terms defined once with their source; one context pack per request, each fact tagged with its source; one policy run twice (advisory before the offer, binding before any write): authorised contact, no overdue balance, available at the site, upgrade-only mid-contract | YAML semantic model (checked with JSON Schema), context service in Python and FastAPI, OPA (Rego, tested with `opa test`) | Real | Multiple policy packs, graph |
| L5 Execution | One business process: binding policy check, quote, upgrade order, wait for fulfilment, timer raises the delay and revised date, then Fibre 150 set to Obsolete, Fibre 900 created as Installed, the two linked as an Upgrade. Order ID as business key, so reruns can't double-write | Operaton BPMN with Python workers; no DMN, rules stay in OPA | Real | Multiple processes, human task queues |
| L6 Systems of record (Salesforce and legacy) | Salesforce: reads customer, contacts and roles, site, current product; writes quote, order and asset changes. Legacy: billing (own ID, slow), availability (refreshed overnight), inventory, OSS fulfilment (overnight batch, +2 day delay), each behind an adapter | TMF Open APIs only, labelled "TMF Open API (Salesforce)": out of the box TMF629 and TMF637 get-by-id; thin mapping-only Apex facade for TMF632 contact roles, TMF637 list/create/update/relationship, catalogue, quote, order with the upgrade action (usage record created inside the order), promotion (TMF620/648/622/671); no SOQL or sObject REST above L6 (test and runtime guard); legacy stand-ins (TMF666/679/639/641); payment link mocked, not TMF | Salesforce real; legacy mocked and labelled | Real BSS/OSS, the org's own availability check (returns an error) |
| L7 Digital Core | Shown as a labelled mocked panel led by a network view of site 4471 (exchange, fibre path, access port 150 to 900 when the OSS step completes; "network view is our illustration"), then the operator's platform services (Kubernetes, secrets vault, network zones, API gateway, agent/workload identity, event bus), "provided by the operator's digital core, mocked in the MVP", labelled "mocked, target state"; no hosting or runtime line on the card | Mock panel; the demo itself runs as local processes (plumbing, not presented as a layer); Salesforce credentials server-side in environment secrets (security baseline) | Target state mocked, labelled; plumbing real | Kubernetes, gateway, vault, agent identity, event bus, multi-region |
| L8 Observability (agreed) | Step timeline per request: each layer's step, its timing, both policy decisions, model token counts | Built from the L3 audit log | Real data from each run | OpenTelemetry and Jaeger (roadmap), Grafana, Langfuse |

The public GitHub Pages site is static and cannot reach the agent, OPA, Operaton or Salesforce. It replays recorded runs (real record IDs and timelines), labelled "recorded run". The live version runs from the local demo stack.

Deployment diagram: DevBot to attach.

## 6. Legacy handling

**A real hidden rule (CONFIRMED, our demo org).** An existing org customisation, the record-triggered flow "Custom Assetize Order", silently required a Subscription Management usage record on each order before activation. Nothing documented it. It broke our orders, and we worked out the hidden rule from the error emails. We handled it outside the flow, by creating that record before activation (now inside the TMF622 order), and did not modify the flow. This is an org customisation, not a Salesforce product flaw. The lesson applies to any customised system of record: rules hide in it. The agentic contrast is the upgrade-only mid-contract rule, written as one visible, versioned, tested OPA policy.

**Adapters.** Every legacy system (billing, inventory, availability, OSS) sits behind an adapter that speaks a standard API. Wrap a system if it can't speak one, as we did on Salesforce, then replace systems one at a time. There is no big bang: wrap, resolve identities, extract rules, let the agent act on that journey, retire systems incrementally (the strangler pattern, which the report also describes for legacy-heavy operators; CONFIRMED).

**Identity cross-reference (L3).** Matching Brightwell's Salesforce account, billing customer and inventory site is deterministic. It is a maintained cross-reference table, with the source of each link. The agent never does the matching, and there is no fuzzy matching. If a link is missing or not verified, the workflow stops for human review. L4 then uses the resolved identity: matching in L3, meaning in L4.

**Jeopardy history (L3).** Our Apex order add-on stores order state only (CONFIRMED, code). Jeopardy and milestone history is therefore kept in L3 and sent as standard-shaped events from L5, with the Salesforce order left unchanged (RECOMMENDED; decision 7).

## 7. How we present it

Four acts, about 20 minutes. The journey is the same in every act. The presented part uses business words, with API numbers as small tags only (for example "order [TMF622]").

1. **The story (2 min).** Customer view only. Sam describes the problem, is offered Fibre 900, accepts, is told of the two-day delay before asking, and the service goes live.
2. **Layer by layer (10 min).** One stack picture with Sam's journey as a line down the eight layers, then one screen per layer answering its question (section 4).
3. **CIO/CTO view and proof (5 min).** Run it live with the layer panel. Then press **Not authorised**: policy, not the model, stops the agent.
4. **Real vs mocked, and MVP to scale (3 min).** Show what is a stand-in, and the path from MVP to pilot to scale.

**Layer view (proposal, DevBot to build after agreement).**
- **Split screen:** Sam's chat on the left. On the right, all eight layers light up as the request passes through them. Clicking a layer shows what it did for this request, with real data. The L3 card shows the cross-reference. The L4 card shows the context pack with source chips, the decision and the rule. The L5 card shows the BPMN diagram with the current step highlighted. The L6 card shows each call by its TMF API number, labelled "TMF Open API (Salesforce)" or "Legacy stand-in (mocked)", with record links; the detail drawer says whether Salesforce provides it out of the box or our facade does.
- **Presenter mode:** a Step button pauses after each layer. The layer text is written by us, not generated.
- **Architecture tab:** one card per layer: purpose, open-source tech and licence, contract with its neighbours, real or mocked.
- **Scenario buttons:**
  - happy path with jeopardy: L5 and the agent handle it;
  - not authorised: L4 policy;
  - overdue balance: L4 policy.

**Key message:** the agent proposes, policy decides, the workflow writes.

## 8. CIO/CTO questions

| # | Question | Answer | Shown in |
|---|---|---|---|
| 1 | Do we replace Salesforce or our BSS? | No. Salesforce stays the system of record for SME. The rest of the estate stays, behind adapters | L6 |
| 2 | Who is in control? | The agent proposes, policy decides, the workflow writes | Not authorised button |
| 3 | Lock-in? | Standard telco APIs between layers; open source outside Salesforce; the TMF facade layer within Salesforce only translates. TMF-aligned | Architecture tab, L6 labels |
| 4 | Safe and compliant? | Every decision is recorded in the audit timeline. Data residency: see decision 2; no UK-only claim yet | L8, L4, L3 |
| 5 | Run cost? | Real model calls and token usage from the run's audit timeline; OpenTelemetry is on the roadmap (L8 agreed: audit-log step timeline). An agent makes several calls per request. No figures until measured | L2, L8 |
| 6 | Path to production? | MVP, then pilot, then scale. What changes: runtime platform, real availability, real billing, real fulfilment, more BPMN processes | Architecture tab |
| 7 | Fit with the industry reference architecture? | It adds to the estate and rips nothing out; mapping in Appendix B | Architecture tab |
| 8 | Pilot business case? | Measure order cycle time, right-first-time orders, cost per upgrade and "where's my order?" calls avoided, against the operator's own baseline. No figures before a pilot | Happy path, timeline timings |
| 9 | Who owns the rules? | The business owns versioned policies under change control; IT owns the platform; the agent owns neither | L4 |
| 10 | What about my legacy? | It stays, wrapped: adapters, identities cross-referenced, rules extracted one at a time, systems retired incrementally | L3, L4, stand-in labels |

## 9. Real vs mocked

**Real:**
- Salesforce reads and writes: customer, contacts and roles, site, catalogue and prices, quote, order, installed services.
- The agent and the local model.
- Context service and both policy decisions.
- BPMN process, idempotency, Postgres records, cross-reference, step timeline.
- Plumbing (not presented as a feature): Salesforce credentials server-side.

**Legacy stand-ins (mocked, always labelled on screen):**
- Billing balance.
- Availability by address key.
- Network inventory site ID.
- Legacy OSS fulfilment, including the jeopardy.
- Payment link (not a TMF API).

**Mocked digital core (labelled "mocked, operator's digital core"):** the L7 network view of site 4471 (exchange, fibre path, access port 150 to 900), then the platform line: Kubernetes, secrets vault, network zones, API gateway, agent/workload identity, event bus.

**Examples, not real data:** UK Telco, Brightwell, Sam, street name, address key, legacy IDs.

## 10. Decisions needed

Each decision has a recommended default.

1. **Contract effect of a mid-contract upgrade.** Default: keep the current end date (10 months left), no re-contract, new price from the upgrade date. The seeded term price is £45.00 a month for Fibre 900, against £27.00 for Fibre 150 (CONFIRMED in the seed catalogue; read from Salesforce at run time). DevBot agrees with this default; accepted by LalitC (30 Oct 2026).
2. **Hosting wording.** Resolved by LalitC (30 Oct 2026): the demo makes no hosting statement. The footer reads "Concept demo by Lalit Chauhan · not an official Salesforce product". (Superseded the earlier default, which named a Salesforce instance and region.)
3. **Model.** Qwen3-4B-Instruct-2507 via Ollama (Apache 2.0, non-thinking variant), agreed by LalitC on 27 Oct 2026. It replaces Qwen2.5 3B, whose Qwen Research License allows non-commercial use only (CONFIRMED, Hugging Face licence file), which rules it out for client demos. Backups: Phi-4-mini-instruct (MIT), then Granite 3.3 2B (Apache 2.0). Build step 0 speed-tests all three on the CPU-only host against the 5-second-per-turn target and picks the fastest that calls the tools correctly. 7B is not used in the MVP. Memory to be re-measured on the 15 GB host (Qwen2.5 3B stack was about 5 GB, CONFIRMED by DevBot).
   - **Narrow tasks only:** the model understands the need, fills the Intent, chooses from the allowed offers in the context pack and phrases the reply.
   - **Explanations:** concept explanations come from the layer panels, the context pack and the glossary, not from the model, so they are always correct.
   - **Fallback:** the scripted presenter fallback stays.
   - **Measured:** real response times and token usage are recorded in the audit timeline.
4. **L5 engine.** L5 uses BPMN (Operaton), decided by LalitC on 27 Oct 2026.
   - **Process:** one process, adapted from the repo's `stack/l5_orchestrator/bpmn/broadband-upgrade-saga.bpmn`. Its steps are: binding OPA check, quote, upgrade order, then a fulfilment wait whose timer raises the jeopardy and the revised date. It ends with the asset change: Fibre 150 Obsolete with an end date, Fibre 900 Installed at the same Location, and an AssetRelationship of type "Upgrade".
   - **Workers:** Python external-task workers. The order external ID is the business key, for idempotency.
   - **Rules:** policy stays in OPA. There is no DMN, so rules are not duplicated.
   - **Cost:** one more Java container, about 1 GB RAM (to be checked against the 15 GB host with the chosen model).
   - **Demo:** the L5 card shows the BPMN diagram with the current step highlighted.
5. **MVP mode.** Default: run as a separate "MVP mode" alongside the full AgenticTelco demo.
6. **Installed-service end state.** CONFIRMED read-only (DevBot, 27 Oct 2026, flow metadata pulled, org unchanged):
   - **How the flow behaves:** the active "Custom Assetize Order" flow fires on any Order update to Activated, whatever the order type. If the Subscription Management usage record is missing, it calls Salesforce's licensed create-or-update-asset action. If the record exists, it ends with no action.
   - **No duplicate Asset on upgrade:** our workflow always creates the usage record first (inside the TMF622 order), so the flow ends without action.
   - **The L5 workflow owns the Asset end state, because the flow won't touch Assets:**
     - It sets the Fibre 150 Asset to Obsolete, with an end date.
     - It creates the Fibre 900 Asset as Installed at the same Location.
     - It links the two with the standard AssetRelationship object, type "Upgrade" (createable; no custom field).
   - **No logic in the org:** all writes go through TMF Open APIs from the mapping-only facade layer.
   - **Live test:** released: all three agreed this document (30 Oct 2026); live org tests run from DevBot's secure setup, never from the room.
7. **Jeopardy storage.** Default: L3 plus events, with no change to the Salesforce order (section 6).
8. **Where TMF921 lives.** Outside Salesforce, confirmed by LalitC on 27 Oct 2026.
   - **Where:** a small intent service in L1, stored in L3 Postgres, which is the system of record for the Intent and IntentReports. An Intent is agent-layer state, not system-of-record data.
   - **Who writes:** the agent proposes the structured Intent. The intent service validates it (schema plus the OPA authorised-contact check) and records it. L5 posts the IntentReports. The agent has no write tools to any system of record.
   - **Rule (LalitC, 27 Oct 2026: "TMF921 stays out of Salesforce - Salesforce only has the APIs for SoR"):** Salesforce hosts only APIs for data it is the system of record for (TMF Open APIs, out of the box or from thin mapping-only Apex facades). Agent-layer state such as TMF921 Intent lives outside Salesforce.
   - **Apex facades:** TMF620/622/648/671, extended by LalitC on 30 Oct 2026 to TMF632 contact roles and TMF637 list/create/update/relationship (TMF-only presentation).
   - **Rejected:** an Apex facade with a custom object, and stretching Opportunity or Case.
   - **Record:** an ADR-001 amendment.
9. **L7 mocked** (LalitC, 27 Oct 2026). Interpretation: L7 is the operator's digital core, the network and the platform. The card leads with a mocked network view of Brightwell's site (site 4471, access port 150 to 900 when the OSS step completes), labelled as our illustration, with platform services as one line underneath. Network records stay in L6. No hosting or runtime wording is shown, and credentials stay server-side regardless.
10. **No Salesforce MCP in the MVP** (LalitC, 27 Oct 2026). MCP is used only between the agent and our own three tools, named in our business terms. The L4 context service reads Salesforce through TMF Open APIs (out of the box and our facades), read-only, per request; only the L5 workflow writes. To avoid vendor lock-in, no vendor's tools define the agent's vocabulary: a vendor MCP server, if used later, sits behind the context layer as one more source, called by code (roadmap).

## 11. Build items (released by LalitC, 30 Oct 2026; built on branch `mvp-build`)

0. Install Ollama (after sign-off).
1. Upgrade ("modify") action on the order Apex add-on [TMF622]: mapping only, no business rules.
2. Test data in standard objects only: Account, Contact with Account Contact Role, Location with External Reference, Address, Asset at Location. AgenticTelco records only; nothing existing is changed.
3. L5 BPMN process on Operaton with Python workers: binding policy check, quote, order, fulfilment timer and jeopardy, asset change; business-key idempotency.
4. L4 semantic file, context service and one OPA policy (advisory and binding), with tests.
5. TMF921-shaped intent service (L1), after sign-off: Intent and IntentReport resources stored in L3 Postgres; validates schema and calls the same OPA policy for the authorised-contact check (no copy of rules); receives IntentReports from the L5 BPMN process.
6. Legacy stand-ins with their quirks, and the L3 cross-reference.
7. MVP mode.
8. Layer view UI: split screen, presenter mode, architecture tab, scenario buttons.

## 12. Out of scope

- Zero Gravity Index positioning (later).
- Kafka, A2A, multiple agents, inference gateway.
- Multiple BPMN processes, DMN, human task queues.
- Graph database, vector search, semantic cache, data products.
- OpenTelemetry and Jaeger (roadmap), Grafana, Langfuse.
- Kubernetes, gateway, vault, agent identity, event bus, multi-region (L7 target state is mocked only).
- Salesforce or other vendor MCP servers (roadmap: behind the context layer only).
- Voice and other channels.
- Full TM Forum Intent Ontology expression, intent negotiation, multi-layer intent handlers.
- Real billing, real availability, real OSS.
- Downgrade journey.
- Any change to existing Salesforce records, settings or flows.

---

## Appendix A: examples (illustrative values)

Detailed versions are in [layer-walkthrough.md](layer-walkthrough.md), which remains the detailed appendix.

Context pack (excerpt):
```json
{
  "requester": {"name": "Sam", "authorisedContact": true, "role": "Decision Maker", "src": "salesforce:AccountContactRole"},
  "identity": {"salesforceAccount": "001-example-brightwell", "billingCustomer": "BIL-B-0077812", "inventorySite": "4471", "src": "L3 identity_xref (verified)"},
  "site": {"addressKey": "A00000001975", "postcode": "IP5 3RE", "src": "salesforce:Location+Address"},
  "currentBroadband": {"product": "AgenticTelco Fibre 150", "downloadSpeedMbps": 150, "src": "salesforce:Asset via TMF637"},
  "contractMonthsLeft": {"value": 10, "src": "salesforce:Asset end date (stand-in for agreement)"},
  "availableAtSite": {"value": ["AgenticTelco Fibre 900"], "asOf": "2026-10-27T02:00:00Z", "src": "legacy stand-in: availability"},
  "overdueBalance": {"value": false, "src": "legacy stand-in: Billing B"}
}
```

OPA rule (same rule for the advisory and binding calls; syntax checked with OPA 1.21.4):
```rego
package agentictelco.upgrade
default allow := false
allow if count(deny) == 0
deny contains "not_authorised" if not input.context.requester.authorisedContact
deny contains "overdue_balance" if input.context.overdueBalance.value
deny contains "not_available_at_site" if not available
deny contains "downgrade_mid_contract" if {
  input.context.contractMonthsLeft.value > 0
  target.downloadSpeedMbps <= input.context.currentBroadband.downloadSpeedMbps
}
available if { some n in input.context.availableAtSite.value; n == target.name }
target := o if { some o in input.context.offerings; o.id == input.proposal.to }
```
The input carries `mode: advisory` or `mode: binding` for the audit only; the rule is identical.

## Appendix B: standards mapping

Older full table (superseded 30 Oct 2026): [layer-walkthrough.md, section 12](layer-walkthrough.md#12-appendix-standards-mapping-for-architects). This table wins.

| Step | API | Served by |
|---|---|---|
| Customer | TMF629 | TMF Open API (Salesforce), out of the box |
| Contact role | TMF632 | TMF Open API (Salesforce), TMF facade (Apex) |
| Site, address key | TMF674 / TMF673 shape | Our layer over standard Location / Address |
| Installed service | TMF637 | TMF Open API (Salesforce): get-by-id out of the box; list, create, update and relationship from the TMF facade (Apex) |
| Catalogue, price | TMF620 | TMF Open API (Salesforce), TMF facade (Apex) |
| Availability | TMF679 shape | Legacy stand-in (the org's own availability check returns 400, CONFIRMED) |
| Balance | TMF666 / TMF678 shape | Legacy stand-in |
| Quote | TMF648 | TMF Open API (Salesforce), TMF facade (Apex) |
| Order (`action: modify`) | TMF622 | TMF Open API (Salesforce), TMF facade (Apex, build item 1); usage record created inside the order |
| Promotion | TMF671 | TMF Open API (Salesforce), TMF facade (Apex) |
| Network inventory site | TMF639 shape | Legacy stand-in |
| Fulfilment, jeopardy | TMF641 shape | Adapter over the legacy OSS stand-in |
| Payment link | Not a TMF API | Mocked stand-in |
| Customer need, progress | TMF921 Intent Management v5.0.0 (Intent, IntentReport), TMF921-shaped | Small intent service in L1, stored in L3 Postgres; not in Salesforce (decision 8) |

**TMF921 (CONFIRMED, 27 Oct 2026):**
- **Version:** v5.0.0 is the current stable release (02 Oct 2024) on the [TM Forum directory](https://www.tmforum.org/oda/open-apis/directory/intent-management-api-TMF921), which also lists v4. Spec files: [tmforum-apis/TMF921_Intent](https://github.com/tmforum-apis/TMF921_Intent) (`TMF921_Intent_Management_v5.0.0.oas.yaml`; the v4 swagger reports 4.0.2).
- **Resources:** `Intent`, `IntentReport` (under `/intent/{intentId}/intentReport`) and `IntentSpecification`, plus events.
- **Expression:** `Intent.expression` holds the expectations in an ontology language, validated by the TM Forum Intent Ontology (TIO). The spec offers JSON-LD and Turtle expression types.
- **Lifecycle:** `lifecycleStatus` is a free string in v5.0.0, with no enumerated values; spec examples use "Created" and "Active". Our labels acknowledged, in progress and fulfilled are therefore MVP labels, not spec values.
- **Report states:** the spec's examples use the TIO terms `icm:StateComplies` and `icm:StateDegrades`. We map "at risk" to `StateDegrades` and "fulfilled" to `StateComplies` (INFERRED mapping).

**Jeopardy field correction (CONFIRMED, tmforum-apis spec files, 27 Oct 2026):**
- TMF622 v4.0.0 has no jeopardy or milestone fields on the product order, only `expectedCompletionDate`.
- TMF622 v5.0.0 adds `productOrderJeopardyAlert`, `productOrderMilestone`, `ProductOrderJeopardyAlertEvent` and `ProductOrderMilestoneEvent`.
- TMF641 v4.2.0 has `jeopardyAlert`, `milestone` and the matching service-order events.
- The order stays `inProgress` throughout.

SID mapping of the business terms is in MVP-design.md section 10. It is conceptual alignment only (TMF-aligned).
