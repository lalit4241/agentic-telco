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
- Every other paragraph or bullet under the heading is the panel body (Markdown, shown as written).
- One `## Glossary` section of lines in the form `**Term**: definition`.
- Anything under other `##` headings (like this one) is ignored by the parser.

Wording below is PLACEHOLDER until TMForumCTO replaces it.

## L1 Intent

**Question**: What does Sam want?
**Tech**: Web chat; TMF921-shaped intent service (ours), stored in Postgres
**Status**: Real

Placeholder: Sam's need is captured as an outcome, not a product, and recorded as a TMF921-shaped Intent outside Salesforce.

## L2 Agent

**Question**: What should we offer and why?
**Tech**: LangGraph (MIT), MCP SDK (MIT), local model via Ollama
**Status**: Real

Placeholder: one agent with three tools (get context, request upgrade, order status) and no write tools.

## L3 Data

**Question**: What do we remember?
**Tech**: PostgreSQL
**Status**: Real; IDs are examples

Placeholder: conversation, audit trail, intents, jeopardy history and the customer ID cross-reference.

## L4 Context & Policy

**Question**: What do we know, and is it allowed?
**Tech**: YAML semantic model, Python/FastAPI context service, OPA (Rego)
**Status**: Real; balance and availability are stand-ins

Placeholder: business terms defined once; the same policy runs before the offer (advisory) and before any write (binding).

## L5 Execution

**Question**: Who actually does the work?
**Tech**: Operaton BPMN (Apache-2.0), Python workers
**Status**: Real; OSS is a stand-in

Placeholder: one business process: binding check, quote, order, fulfilment wait, delay alert, asset change.

## L6 Systems of record

**Question**: Where is the truth recorded?
**Tech**: Salesforce native APIs plus thin TMF facades
**Status**: Salesforce real; legacy billing, availability, inventory and OSS mocked

Placeholder: Salesforce keeps customers, orders and installed services; legacy systems sit behind standard adapters.

## L7 Digital Core

**Question**: What does it run on, and where does the order reach the network?
**Tech**: Network view (mocked); MVP runs on a single host
**Status**: Mocked, our illustration

Placeholder: exchange, fibre path and access port for site 4471, changing from 150 to 900.

## L8 Observability

**Question**: How do we prove what happened?
**Tech**: Step timeline built from the L3 audit log, OTel-style trace IDs
**Status**: Real data from each run

Placeholder: a step-by-step timeline of every request, decisions and model usage.

## Glossary

**Intent**: Placeholder. The outcome the customer wants, not a product.
**Authorised contact**: Placeholder. A contact with the Decision Maker role on the account.
**Overdue balance**: Placeholder. An unpaid amount past its due date in the billing system.
**Available at site**: Placeholder. The product can be delivered at the site's address key.
**Upgrade-only mid-contract**: Placeholder. During a contract the customer can move up a speed tier, not down.
**Advisory check**: Placeholder. The policy check before an offer is made.
**Binding check**: Placeholder. The same policy check, run by the workflow before any write.
**Jeopardy**: Placeholder. A warning that an order will miss its date.
