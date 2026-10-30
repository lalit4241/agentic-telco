# AgenticTelco MVP: layer panels and glossary (single source of truth)

This file is the **only** source for the wording in the MVP layer panels and for the glossary the agent explains from.
The web build (`web/build.js`) parses it into `web/src/mvp/copy.json` (generated, do not edit by hand).
The agent service reads the same generated file, so wording changes here need no code change.

## How to edit (structure the parser expects)

- One `## L<n> <Name>` heading per layer, L1 to L8, for example `## L4 Context & Policy`.
- Under each layer heading, optional key lines, each on its own line:
  - `**Question**: ...` the question the layer answers
  - `**Tech**: ...` technology and licence
  - `**Status**: ...` real / mocked label shown on the card
  - `**Label**: ...` optional one-line label for the architecture view card (defaults to Tech)
  - `**Chip**: ...` optional short label for the layer chip (defaults to the layer name)
- Every other paragraph or bullet under the heading is the panel body (Markdown, shown as written).
- One `## Glossary` section of lines in the form `**Term**: definition`.
- Anything under other `##` headings (like this one) is ignored by the parser.

Wording status: written by TMForumCTO, 30 Oct 2026, for LalitC's review. It follows [MVP-KEY-DESIGN.md](MVP-KEY-DESIGN.md), which wins if anything here differs. Text here is written by us, not generated. UK Telco, Brightwell Design Ltd, Sam, the street name, the address key and the legacy IDs are examples, not real data. API numbers appear as small tags only.

## The story

**Banner:** Agent proposes · Policy decides · Workflow writes

**Setting.** UK Telco is a fictional Tier 1 UK operator with a legacy estate. Salesforce is the system of record for its business (SME) customers. Billing, availability, network inventory and network fulfilment sit in older systems, each with its own quirks.

**Customer.** Brightwell Design Ltd is a design agency at site 4471 in Martlesham. It has Fibre 150 and is part-way through its contract. Sam is Brightwell's authorised contact, with the role "Decision Maker".

**Six steps (happy path):**

1. **Sam asks.** "We're hiring 15 more staff and moving to cloud video. The line can't keep up." Sam does not name a product.
2. **Checks.** The agent gathers the facts: who Sam is, the site, the current service, the contract, the balance and what is available at the site. A policy check confirms what Sam is allowed to buy.
3. **Recommends.** The agent recommends Fibre 900 at £45 a month and explains why.
4. **Agrees.** Sam accepts and consent is recorded. The workflow runs the binding policy check, then creates the quote and the upgrade order in Salesforce.
5. **Delay.** The legacy network system reports no free exchange port yet. The date moves by two days. The agent tells Sam before Sam has to ask.
6. **Live.** The port is ready and the service is switched on. Fibre 900 is recorded as installed, linked to the old Fibre 150 as an upgrade. Sam is told it is live.

## The four cases

| Case | What happens | Who decides |
|---|---|---|
| Happy path | The six steps above, ending with Fibre 900 live | Policy allows; the workflow does the writes |
| Not authorised | A regular employee (role "Business User") asks for the same upgrade. The agent explains politely that it can't place the order and points to the Decision Maker. No offer, no quote, no order | Policy (L4) |
| Overdue balance | The account has an overdue balance. The agent explains and offers a payment link (mocked). No order | Policy (L4) |
| Order delayed | The legacy network system raises a delay. The order stays in progress, Sam is told the new date first, and the order then completes | The workflow (L5) raises it; the agent tells Sam |

## L1 Intent

**Question**: What does Sam want?
**Tech**: Web chat; TMF921-shaped intent service (ours), stored in Postgres
**Status**: Real; demo sign-in

Sam types the problem in plain words in the business portal. The agent turns it into a structured intent: an outcome such as "support 15 more staff and cloud video at the Martlesham site, within contract". A small intent service outside Salesforce checks and records it. It later records progress reports, including the delay and the final "fulfilled".

- **Why it matters:** the customer states an outcome, not a product, so the operator can meet the need without exposing its catalogue or its systems.
- **What you'll see:** the intent and its progress reports (at risk with a revised date, then fulfilled).
- **Tags:** intent [TMF921-shaped]

## L2 Agent

**Question**: What should we offer and why?
**Tech**: LangGraph (MIT), MCP SDK (MIT), local model Qwen3-4B-Instruct-2507 (Apache 2.0) via Ollama
**Status**: Real

One agent reads the facts it is given, recommends Fibre 900 and explains why in plain words. It has three tools: get the context, request the upgrade and check the order status. It proposes only. It cannot write to Salesforce or any other system of record.

- **Why it matters:** the model reasons and talks to the customer, but it holds no business rules and no write access, so it can't place an order on its own.
- **What you'll see:** the agent's plan, each tool call and its result, and the model calls with their token counts.
- **Tags:** none (MCP links the agent to our own three tools only)

## L3 Data

**Question**: What do we remember?
**Tech**: PostgreSQL
**Status**: Real; IDs are examples

It stores the conversation, the decisions, the intent and its reports, the delay history and the audit log. It also holds the cross-reference showing that Brightwell's Salesforce account, billing ID BIL-B-0077812, inventory site 4471 and address key A00000001975 belong to the same customer and site. The matching is a maintained table, not a guess by the agent.

- **Why it matters:** every system is talking about the same customer, and every step can be reconstructed afterwards.
- **What you'll see:** the cross-reference rows, each with where the link came from, and the audit rows written for this request.
- **Tags:** none

## L4 Context & Policy

**Question**: What do we know, and is it allowed?
**Tech**: YAML semantic model, Python/FastAPI context service, OPA (Rego)
**Status**: Real; balance and availability are stand-ins

Business terms such as "authorised contact" and "available at site" are defined once, with their source. For Sam's request, the context service builds one context pack, with every fact tagged with where it came from. The same policy then runs twice: first as an advisory check before the agent makes an offer, then as the binding check in the workflow before anything is written. It checks four things: Sam is an authorised contact, there is no overdue balance, Fibre 900 is available at the site, and mid-contract changes are upgrades only.

- **Why it matters:** rules live in one visible, versioned, tested place, not inside the model and not buried in a system of record.
- **What you'll see:** the context pack with source chips ("TMF Open API (Salesforce)" with the API name, or "Legacy stand-in (mocked)"), the policy decision and the rule that applied.
- **Today vs agentic:** in our own demo org, the "Custom Assetize Order" flow silently required a usage record on each order. Nothing documented it. That is an org customisation, not a Salesforce flaw. Here the same kind of rule is one visible policy, and the usage record is created inside the TMF622 order itself, not as a separate call.
- **Tags:** none (policy engine: OPA)

## L5 Execution

**Question**: Who actually does the work?
**Tech**: Operaton BPMN (Apache-2.0), Python workers
**Status**: Real; OSS is a stand-in

One business process takes Sam's acceptance through to "live". It runs the binding policy check, creates the quote, places the upgrade order and waits for fulfilment. A timer raises the delay and the revised date. At the end it marks Fibre 150 as obsolete, records Fibre 900 as installed and links the two as an upgrade. It is the only component that writes. The order ID is its business key, so a rerun can't write the same order twice.

- **Why it matters:** writes follow a fixed, auditable process that absorbs slow and batch legacy systems, whatever the agent says.
- **What you'll see:** the process diagram (BPMN) with the current step highlighted, including the delay.
- **Tags:** none

## L6 Systems of record

**Question**: Where is the truth recorded?
**Tech**: Salesforce as the system of record, exposed only through TM Forum Open APIs: TMF629 and TMF637 get-by-id out of the box from Salesforce; TMF632, TMF637 list/create/update/relationship, TMF620, TMF648, TMF622 and TMF671 from a thin TMF facade layer within Salesforce (Apex); legacy stand-ins behind TMF-shaped adapters
**Status**: Salesforce real; legacy billing, availability, inventory and OSS mocked
**Label**: TM Forum Open APIs exposed by Salesforce: two out of the box, the rest through a thin TMF facade layer within Salesforce
**Chip**: TMF Open APIs (Salesforce)

Salesforce holds Brightwell's customer record, contacts, site, quote, order and installed services. Everything above this layer reaches it only through TM Forum Open APIs, never through Salesforce-specific APIs. Out of the box, Salesforce provides two of them: the customer record (TMF629) and reading one installed service by its ID (TMF637). A thin TMF facade layer within Salesforce (Apex) provides the rest: the organisation and its contact roles (TMF632), listing, creating and updating installed services and linking them as an upgrade (TMF637), catalogue (TMF620), quote (TMF648), order (TMF622) and promotion (TMF671). It lives in the Salesforce org itself, not in a separate integration tier, and it only translates data: it holds no business rules. The usage record that our demo org expects on each order is created inside the TMF622 order itself, not as a separate call. The legacy billing, availability, network inventory and network fulfilment systems sit behind adapters with the same TM Forum API shapes. The overdue-balance payment link is a mocked stand-in and is not a TMF API. The APIs are TMF-aligned.

- **Why it matters:** Salesforce and the legacy estate stay in place, keep the records and nothing else, and can be replaced one at a time behind the same APIs.
- **What you'll see:** each call, shown by its TM Forum API number and name (for example "TMF622 Product Order") and labelled "TMF Open API (Salesforce)" or "Legacy stand-in (mocked)", with links to the Salesforce records behind it.
- **Tags:** TMF Open API (Salesforce), out of the box [TMF629] [TMF637 get-by-id] · TMF Open API (Salesforce), TMF facade [TMF632] [TMF637 list/create/update/relationship] [TMF620] [TMF648] [TMF622] [TMF671] · legacy stand-ins [TMF666 billing] [TMF679 availability] [TMF639 network inventory] [TMF641 network fulfilment] (shape only) · payment link (mocked, not a TMF API)

## L7 Digital Core

**Question**: What does it run on, and where does the order reach the network?
**Tech**: Network view (mocked); MVP runs on a single host
**Status**: Mocked, our illustration

It shows the operator's network at site 4471: the exchange, the fibre path to Martlesham and the access port. The port changes from 150 to 900 when the network fulfilment step completes. One line underneath lists the platform services an operator would provide.

- **Why it matters:** it shows where the order meets the network and what a production platform needs, without claiming the MVP has it.
- **What you'll see:** the network view for site 4471, labelled "network view is our illustration"; one platform line (Kubernetes, secrets vault, network zones, API gateway, agent and workload identity, event bus).
- **Tags:** none

## L8 Observability

**Question**: How do we prove what happened?
**Tech**: Step timeline built from the L3 audit log, OTel-style trace IDs
**Status**: Real data from each run

It builds a step timeline for Sam's request from the audit log. It shows each step across the layers, how long it took, both policy decisions and the model's token counts.

- **Why it matters:** every decision can be explained and checked afterwards, and run cost comes from measured calls, not estimates.
- **What you'll see:** the step timeline for this request.
- **Tags:** none

## Glossary

**Intent**: A customer need written as an outcome, not a product, such as "support 15 more staff and cloud video at this site". Here it follows the shape of the TM Forum intent API (TMF921) and is TMF-aligned.
**Intent report**: A progress update on an intent, such as "at risk, revised date" or "fulfilled". The workflow sends these reports.
**Agent**: Software that uses a language model to understand a request, gather facts and propose an action. In this demo it proposes only and cannot write to any system of record.
**MCP**: Model Context Protocol, an open protocol that lets an agent call tools. Here it connects the agent to our own three tools only: get context, request upgrade and order status.
**Business term**: A word such as "authorised contact", defined once with the system it comes from, so every layer means the same thing.
**Authorised contact**: A contact allowed to order for the business. In Salesforce this is a contact with the role "Decision Maker" on the account; a "Business User" is not authorised.
**Overdue balance**: An unpaid amount past its due date in the billing system. If there is one, no order is placed.
**Available at site**: The product can be delivered at the site's address key, according to the availability system. That data is refreshed overnight.
**Upgrade-only mid-contract**: During a contract the customer can move up a speed tier, not down.
**Context pack**: The set of facts gathered for one request, each tagged with its source. The agent and the policy both work from it.
**Policy**: A written, versioned, tested business rule that a policy engine (OPA) evaluates. It decides whether an action is allowed; the model does not.
**Advisory check**: The policy check that runs before the agent makes an offer, so the agent only offers what is allowed.
**Binding check**: The same policy check, run by the workflow just before any write. This is the one that counts.
**Workflow**: The business process that carries out an agreed action step by step. It is the only part of the demo that writes to a system of record.
**BPMN**: Business Process Model and Notation, a standard way to draw and run business processes. The demo's workflow is a BPMN process running on Operaton.
**Business key**: A unique ID, here the order ID, that the workflow uses so that running a step again does not create a second order.
**System of record**: The system that holds the official version of a piece of data. Here Salesforce holds customers, quotes, orders and installed services; legacy systems hold billing and network data.
**TMF facade**: A thin layer within Salesforce, written in Apex, that exposes Salesforce's records as TM Forum Open APIs where Salesforce's out-of-the-box TMF APIs (TMF629 and TMF637 get-by-id) don't cover the need: TMF632 contact roles, TMF637 list, create, update and relationship, TMF620 catalogue, TMF648 quote, TMF622 order (including the usage record, created inside the order) and TMF671 promotion. It lives in the Salesforce org, not in a separate integration tier, and only translates data.
**Legacy stand-in**: A mocked version of an older system, such as billing (TMF666 shape), availability (TMF679), network inventory (TMF639) or network fulfilment (TMF641), built to behave like the real thing, including slow answers and overnight batches. It is always labelled on screen.
**Adapter**: A small piece of software in front of a legacy system that gives it a standard API, so the rest of the architecture never deals with its quirks.
**Cross-reference**: A maintained table linking one customer's IDs across systems, such as the Salesforce account, billing ID and network site. If a link is not verified, the workflow stops for human review.
**Jeopardy**: A warning that an order is at risk of missing its date. Here the legacy network system reports no free exchange port, the date moves by two days and the order stays in progress.
**Hidden rule**: A business rule buried inside a system's configuration or code, often undocumented. In our demo org, a custom flow silently required a usage record on each order; the demo now creates it inside the TMF622 order.
**TM Forum Open APIs**: Industry-standard telco APIs published by TM Forum, each with a number, such as TMF622 for product orders. The demo is TMF-aligned.
**ODA**: Open Digital Architecture, TM Forum's reference architecture for telco IT, built from functional blocks. The demo is aligned to ODA functional blocks and uses TMF Open API contracts.
**Digital core**: The operator's network and the platform that runs its software. In the demo it is a labelled illustration.
**Audit timeline**: The step-by-step record of one request, built from the audit log: each step, its timing, both policy decisions and the model's token use.
