# ADR amendment 001: custom TMF APIs on Salesforce where the org has no native API

- **Status:** Accepted, 2026-10-26, by LalitC.
- **Amends:** the L6 decision in `docs/architecture/04-adrs.md`. That file is not edited; this amendment takes precedence where they differ.
- **Context:** the capability check of org `sfcomms` ([docs/api/org-capabilities.md](../api/org-capabilities.md)) found:
  - TMF629, TMF632 and TMF637 (read) work natively.
  - TMF620 and TMF648 are not exposed.
  - TMF622's native read path fails on this org.
  - TMF671 returns 500.
  - TMF679 needs a qualification procedure the org does not have.

## Decision

1. **Native OOTB first.** If the org exposes a working Direct Access TMF API, or the job can be done with standard sObject REST, that is what L6 uses. Those calls are labelled **OOTB**.
2. **Apex for every TMF API the org does not expose natively.** These are custom TMF APIs written in Apex REST:
   - Path: `/services/apexrest/agentictelco/tmf<NNN>/...`
   - Request and response bodies use TMF shapes.
   - Classes are prefixed `AgenticTelco_`.
   - Tests must reach at least 85% coverage.
   - Deployment uses `sf project deploy`.
   - Calls are labelled **custom TMF API on Salesforce**.
   - Current set: TMF620, TMF622, TMF648, TMF671 (TMF921 is not a facade; see the amendment below).
3. **Nothing in the org is deleted or changed.**
   - Writes create AgenticTelco-prefixed records only.
   - PATCH accepts AgenticTelco records only.
   - There is no DELETE: the Apex APIs have none, and the server-side `sf_session` refuses it.
   - No org setting, procedure or existing metadata is modified. That is why TMF679 stays native-first with a labelled fallback in our layer, rather than us configuring a qualification procedure.
4. **Agents, policy, orchestration, data and observability stay outside Salesforce.** That means L2 (LangGraph agents), L4 (OPA), L5 (Operaton), L3 (Postgres/pgvector, Kafka) and L8 (ledger, OpenTelemetry). The Apex classes hold no business rules beyond TMF↔sObject mapping and state transitions. Zero Gravity's axiom still holds: rules live in L4.
5. **Credentials.** The server-side adapter reaches Salesforce only through the Salesforce CLI session (`sf api request rest`). No token is read, logged, committed or shipped to the browser.

## Deployments

| Deploy ID | When (Europe/London) | Components | Tests | Org-wide coverage of the AgenticTelco classes |
|---|---|---|---|---|
| `0AfQH00000Q1oYT0AZ` | 2026-10-26 18:52:48–18:52:56 | 6 Apex classes | 6/6 passed | ≥ 85% |
| `0AfQH00000Q1p370AB` | 2026-10-26 19:01:48–19:01:57 | 6 (TMF622 gains `completed`) | **6/6 passed** | **97.3%** (Tmf 110/111, TMF620 185/194, TMF622 128/130, TMF648 107/110, TMF671 16/16) |

A dry-run validation (`0AfQH00000Q1p1V0AR`) preceded the second deploy.

## Consequences

- Every L6 call shows its runtime in the UI and in the L8 ledger (`x-zg-runtime`). Each ledger entry also lists the Salesforce REST calls behind it.
- If the org later enables a native TMF620, TMF648 or TMF622 path, the adapter swaps that API back to OOTB without changing any agent or BPMN contract.
- The custom Apex APIs are demo code. Before production use they would need review, permission sets, and Salesforce's own TMF certification path.

## Reconfirmation

27 Oct 2026: Lalit Chauhan reconfirmed this decision. The thin Apex TMF facades (TMF620, TMF622, TMF648, TMF671) stay in Salesforce and only map records to TMF shapes. Policy, orchestration and agent logic stay outside Salesforce. See ADR-001 (commit 1e98af9).

## Amendment: TMF921 Intent

**Rule:** Salesforce hosts only APIs for data it is the system of record for (native APIs, or thin mapping-only Apex facades where the org lacks them). Agent-layer state such as TMF921 Intent lives outside Salesforce. (LalitC, 27 Oct 2026: "TMF921 stays out of Salesforce - Salesforce only has the APIs for SoR.")

TMF921 Intent is agent-layer state, not system-of-record data, so it is hosted outside Salesforce in a small intent service (L1, stored in L3). Confirmed LalitC 27 Oct 2026; an Apex facade with a custom object was considered and rejected, as was stretching Opportunity/Case.
