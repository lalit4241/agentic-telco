# AgenticTelco MVP: key design

**Status: DRAFT v0.1 for agreement — LalitC [ ] DevBot [ ] TMForumCTO [ ]**

27 Oct 2026. This is the one document all three must agree before any development starts. It consolidates [MVP-design.md](MVP-design.md) and [layer-walkthrough.md](layer-walkthrough.md). The walkthrough stays as the detailed appendix. Where they differ, this document wins once agreed.

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
| Salesforce Communications Cloud | System of record for the SME segment: customer, contacts, site, products, quotes, orders, installed services | Customised over the years (section 5) | **Real** |
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
7. **Binding policy check** in the workflow, before any write.
8. The workflow creates the quote and places an upgrade order from Fibre 150 to Fibre 900.
9. Fulfilment starts in the legacy OSS. Its overnight batch reports that no exchange port is free yet, and the date moves by two days. The order stays in progress.
10. The agent tells Sam the new date proactively.
11. The port is reserved and the service is activated. The order is completed.
12. **End state:** the Fibre 150 installed service is closed or inactive. One Fibre 900 installed service is active at the same location and linked to the old one (decision 6). Sam is told it is live.

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
| L1 Intent & Experience | What does Sam want? | Portal chat; captures the need in plain words | React (MIT) | Intent message | Real; demo sign-in |
| L2 Agent Mesh | What should we offer and why? | One agent: understands, gets context, recommends, explains, tells Sam about delays | LangGraph (MIT), MCP SDK (MIT), small local model via Ollama (MIT) | Plan, tool calls, model calls and tokens | Real |
| L3 Data Foundation | What do we remember? | Conversation, decisions, consent, workflow and jeopardy history, audit; identity cross-reference | PostgreSQL (PostgreSQL Licence) | Cross-reference rows, audit rows | Real; IDs are examples |
| L4 Enterprise Context | What do we know, and is it allowed? | Semantic definitions, context pack with sources, policy decision | Context service (ours), OPA (Apache-2.0) | Context pack, policy decision and rule | Real; balance and availability are stand-ins |
| L5 Deterministic Execution | Who actually does the work? | Coded workflow: binding check, quote, order, fulfilment, jeopardy, completion; idempotent; absorbs slow and batch legacy | Python (ours) | State machine, current state | Real; OSS is a stand-in |
| L6 Agent-Ready SoR | Where is the truth recorded? | Salesforce, plus legacy stand-ins, each behind a standard API | Salesforce (commercial), Apex add-ons (ours) | Each call, labelled native or Apex add-on, with record links | Salesforce real |
| L7 Digital Core | What does it run on? | One small stack; secrets server-side; one internal network | Docker Compose (Apache-2.0) | Running containers, boundary | Real; single host |
| L8 Observability & Governance | How do we prove what happened? | One trace per request across all layers | OpenTelemetry, Jaeger (Apache-2.0) | Trace and span list | Real |

**L1.** Sam types "We're hiring 15 people and moving to cloud video editing; the line can't keep up." Sam never has to name a product. No voice or other channels in the MVP.

**L2.** One agent with three tools: get context, start the upgrade, read order status. It has no write tools and never sees a legacy system, a legacy ID or a batch job. Its recommendation is reasoning ("15 more people and cloud video need more than 150 Mbps"). Whether an offer is allowed comes from the advisory policy check, never from the model.

**L3.** One Postgres database. It holds the conversation, the context pack used, both policy decisions, consent, workflow state, jeopardy and milestone history, and audit. It also holds the identity cross-reference (section 5). This is an operational database, not the lakehouse and data products the report describes for L3 (INFERRED).

**L4.** The semantic file defines each business term once ("authorised contact", "in contract", "available at site") and says where it comes from. The context service builds one context pack per request from the identity L3 has resolved. Each fact is tagged with its source: Salesforce, or legacy stand-in. The **same OPA rule runs twice**: advisory before the recommendation, binding in the workflow before any write. The rule checks four things: authorised contact, no overdue balance, available at the site, and upgrade-only mid-contract.

**L5.** A small coded workflow with fixed states (Operaton stays in the full demo; decision 4). Its states are: identity check, binding policy check, consent, quote, order, in fulfilment, in jeopardy, installed service updated, completed. It uses one idempotency key per request. It waits for the overnight batch, retries slow systems and turns a legacy delay into a jeopardy event.

**L6.** Salesforce keeps the records and nothing else. Calls use native Salesforce APIs where the org has them: customer and contacts [TMF629/632] and installed services [TMF637]. Otherwise they use thin, mapping-only Apex add-ons: catalogue [TMF620], quote [TMF648] and order [TMF622] (ADR amendment 001, approved by LalitC). Every legacy system sits behind an adapter speaking a standard API. A system that can't be adapted is wrapped, and systems are replaced one at a time.

**L7.** It runs as one Docker Compose stack on one host. Salesforce access stays server-side and never reaches the browser. There is no Kubernetes, zero-trust mesh or agent identity yet; we say so plainly.

**L8.** One OpenTelemetry trace links Sam's words, the facts and their sources, both decisions, every API call and the final records. It also shows real model calls and token counts.

## 5. Legacy handling

**A real hidden rule (CONFIRMED, our demo org).** An existing org customisation, the record-triggered flow "Custom Assetize Order", silently required a Subscription Management usage record on each order before activation. Nothing documented it. It broke our orders, and we worked out the hidden rule from the error emails. We handled it outside the flow, by creating that record before activation, and did not modify the flow. This is an org customisation, not a Salesforce product flaw. The lesson applies to any customised system of record: rules hide in it. The agentic contrast is the upgrade-only mid-contract rule, written as one visible, versioned, tested OPA policy.

**Adapters.** Every legacy system (billing, inventory, availability, OSS) sits behind an adapter that speaks a standard API. Wrap a system if it can't speak one, as we did on Salesforce, then replace systems one at a time. There is no big bang: wrap, resolve identities, extract rules, let the agent act on that journey, retire systems incrementally (the strangler pattern, which the report also describes for legacy-heavy operators; CONFIRMED).

**Identity cross-reference (L3).** Matching Brightwell's Salesforce account, billing customer and inventory site is deterministic. It is a maintained cross-reference table, with the source of each link. The agent never does the matching, and there is no fuzzy matching. If a link is missing or not verified, the workflow stops for human review. L4 then uses the resolved identity: matching in L3, meaning in L4.

**Jeopardy history (L3).** Our Apex order add-on stores order state only (CONFIRMED, code). Jeopardy and milestone history is therefore kept in L3 and sent as standard-shaped events from L5, with the Salesforce order left unchanged (RECOMMENDED; decision 7).

## 6. How we present it

Four acts, about 20 minutes. The journey is the same in every act. The presented part uses business words, with API numbers as small tags only (for example "order [TMF622]").

1. **The story (2 min).** Customer view only. Sam describes the problem, is offered Fibre 900, accepts, is told of the two-day delay before asking, and the service goes live.
2. **Layer by layer (10 min).** One stack picture with Sam's journey as a line down the eight layers, then one screen per layer answering its question (section 4).
3. **CIO/CTO view and proof (5 min).** Run it live with the layer panel. Then press **Not authorised**: policy, not the model, stops the agent.
4. **Real vs mocked, and MVP to scale (3 min).** Show what is a stand-in, and the path from MVP to pilot to scale.

**Layer view (proposal, DevBot to build after agreement).**
- **Split screen:** Sam's chat on the left. On the right, all eight layers light up as the request passes through them. Clicking a layer shows what it did for this request, with real data. The L3 card shows the cross-reference. The L4 card shows the context pack with source chips, the decision and the rule. The L6 card shows each call labelled "native Salesforce API" or "custom Apex facade on Salesforce", with record links.
- **Presenter mode:** a Step button pauses after each layer.
- **Architecture tab:** one card per layer: purpose, open-source tech and licence, contract with its neighbours, real or mocked.
- **Scenario buttons:**
  - happy path with jeopardy: L5 and the agent handle it;
  - not authorised: L4 policy;
  - overdue balance: L4 policy.

**Key message:** the agent proposes, policy decides, the workflow writes.

## 7. CIO/CTO questions

| # | Question | Answer | Shown in |
|---|---|---|---|
| 1 | Do we replace Salesforce or our BSS? | No. Salesforce stays the system of record for SME. The rest of the estate stays, behind adapters | L6 |
| 2 | Who is in control? | The agent proposes, policy decides, the workflow writes | Not authorised button |
| 3 | Lock-in? | Standard telco APIs between layers; open source outside Salesforce; the Apex add-ons only translate. Aligned with industry standards, not certified | Architecture tab, L6 labels |
| 4 | Safe and compliant? | Every decision is traced and audited. Data residency: see decision 2; no UK-only claim yet | L8, L4, L3 |
| 5 | Run cost? | Real model calls and tokens from the trace. An agent makes several calls per request. No figures until measured | L2, L8 |
| 6 | Path to production? | MVP, then pilot, then scale. What changes: runtime platform, real availability, real billing, real fulfilment, BPMN where needed | Architecture tab |
| 7 | Fit with the industry reference architecture? | It adds to the estate and rips nothing out; mapping in Appendix B | Architecture tab |
| 8 | Pilot business case? | Measure order cycle time, right-first-time orders, cost per upgrade and "where's my order?" calls avoided, against the operator's own baseline. No figures before a pilot | Happy path, trace timings |
| 9 | Who owns the rules? | The business owns versioned policies under change control; IT owns the platform; the agent owns neither | L4 |
| 10 | What about my legacy? | It stays, wrapped: adapters, identities cross-referenced, rules extracted one at a time, systems retired incrementally | L3, L4, stand-in labels |

## 8. Real vs mocked

**Real:**
- Salesforce reads and writes: customer, contacts and roles, site, catalogue and prices, quote, order, installed services.
- The agent and the local model.
- Context service and both policy decisions.
- Workflow, idempotency, Postgres records, cross-reference, traces.

**Legacy stand-ins (mocked, always labelled on screen):**
- Billing balance.
- Availability by address key.
- Network inventory site ID.
- Legacy OSS fulfilment, including the jeopardy.
- Payment link.

**Examples, not real data:** UK Telco, Brightwell, Sam, street name, address key, legacy IDs.

## 9. Decisions needed

Each decision has a recommended default.

1. **Contract effect of a mid-contract upgrade.** Default: keep the current end date (10 months left), no re-contract, new price from the upgrade date. The seeded term price is £45.00 a month for Fibre 900, against £27.00 for Fibre 150 (CONFIRMED in the seed catalogue; read from Salesforce at run time).
2. **Hosting wording.** Default: "The agent and model run locally in our stack. Salesforce runs on instance GBR58 (REPORTED; UK region to be confirmed)." Make no UK-only claim yet. The GitHub Pages replay, the org region and model hosting are unverified.
3. **Model.** Default: a small open model running locally via Ollama (the repo currently uses Qwen2.5 0.5B, CONFIRMED). The size is settled in the first build test. Real token usage is shown from the trace. The two views:
   - **TMForumCTO:** test a 7B-class tool-calling model (for example Qwen2.5-7B-Instruct), with a scripted presenter fallback.
   - **DevBot:** stay small.
4. **L5 engine.** Default: a small coded workflow, not Operaton, in the MVP.
5. **MVP mode.** Default: run as a separate "MVP mode" alongside the full AgenticTelco demo.
6. **Installed-service end state.** Default:
   - Fibre 150 is closed or inactive. The existing adapter sets the replaced Asset to "Obsolete" (CONFIRMED, code).
   - One Fibre 900 Asset is active at the same Location and linked to the old one. The linking method still has to be chosen: a standard Asset relationship is a candidate, but its availability on this org is UNKNOWN.
   - **Risk:** the "Custom Assetize Order" flow might create a duplicate Asset on activation. The read-only flow check ([org-capabilities](../api/org-capabilities.md#org-automation-custom-assetize-order-flow)) shows the flow ends without assetizing when the Subscription Management record exists (CONFIRMED). Whether that holds for an upgrade order is to be re-checked read-only now, from the flow metadata. The live test happens only after all three agree this document.
7. **Jeopardy storage.** Default: L3 plus events, with no change to the Salesforce order (section 5).

## 10. Build items (not started until all three agree)

1. Upgrade ("modify") action on the order Apex add-on [TMF622]: mapping only, no business rules.
2. Test data in standard objects only: Account, Contact with Account Contact Role, Location with External Reference, Address, Asset at Location. AgenticTelco records only; nothing existing is changed.
3. Coded L5 workflow with idempotency, the binding policy check, legacy waits and retries, and jeopardy.
4. L4 semantic file, context service and one OPA policy (advisory and binding), with tests.
5. Legacy stand-ins with their quirks, and the L3 cross-reference.
6. MVP mode.
7. Layer view UI: split screen, presenter mode, architecture tab, scenario buttons.

## 11. Out of scope

- Zero Gravity Index positioning (later).
- Kafka, A2A, multiple agents, inference gateway.
- Operaton BPMN in the MVP.
- Graph database, vector search, semantic cache, data products.
- Grafana and Langfuse.
- Kubernetes, zero-trust mesh, agent identity.
- Voice and other channels.
- A full intent model.
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

Full table: [layer-walkthrough.md, section 12](layer-walkthrough.md#12-appendix-standards-mapping-for-architects).

| Step | API | Served by |
|---|---|---|
| Customer, contact role | TMF629, TMF632 | Salesforce native |
| Site, address key | TMF674 / TMF673 shape | Our layer over standard Location / Address |
| Installed service | TMF637 | Salesforce native (Asset write via standard sObject REST) |
| Catalogue, price | TMF620 | Apex add-on |
| Availability | TMF679 shape | Legacy stand-in (native returns 400 on this org, CONFIRMED) |
| Balance | TMF666 / TMF678 shape | Legacy stand-in |
| Quote | TMF648 | Apex add-on |
| Order (`action: modify`) | TMF622 | Apex add-on (build item 1) |
| Fulfilment, jeopardy | TMF641 shape | Adapter over the legacy OSS stand-in |

**Jeopardy field correction (CONFIRMED, tmforum-apis spec files, 27 Oct 2026):**
- TMF622 v4.0.0 has no jeopardy or milestone fields on the product order, only `expectedCompletionDate`.
- TMF622 v5.0.0 adds `productOrderJeopardyAlert`, `productOrderMilestone`, `ProductOrderJeopardyAlertEvent` and `ProductOrderMilestoneEvent`.
- TMF641 v4.2.0 has `jeopardyAlert`, `milestone` and the matching service-order events.
- The order stays `inProgress` throughout.

SID mapping of the business terms is in MVP-design.md section 10. It is conceptual alignment, not certified.
