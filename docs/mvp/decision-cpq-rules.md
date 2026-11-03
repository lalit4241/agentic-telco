# Decision: which CPQ rules leave the system of record

Status: decided 3 Nov 2026 (LalitC: "ok"). Applies to the AgenticTelco MVP and to the target architecture.

## Context

Zero Gravity's rule is that business rules come out of the systems of record. "CPQ rules" is not one thing, so we sort
each rule with one test:

- If it answers **"is this allowed, and who may approve it?"**, it is a decision. It moves to L4 policy.
- If it answers **"what is this product, and what does it cost?"**, it is master data. It stays where it is mastered.

## Decision (hybrid)

| Rule type | Example in our journey | Where it lives | Label |
|---|---|---|---|
| Eligibility and qualification | Upgrade only, address can take 900 Mbps, authorised contact, no overdue balance | L4 policy (OPA), called before quoting | CONFIRMED in the MVP |
| Approval and authority | Discount above a set level needs approval, margin floor, retention offer limits | L4 decides, L5 workflow routes the approval, the SoR records it | RECOMMENDED |
| Commercial terms | Contract end date carried over, early termination charge | L4 defines and decides; the actual end date is read from the contract record in Salesforce, never copied | RECOMMENDED |
| Configuration | Fibre 900 includes a router, cardinality, compatible add-ons | Product catalogue (TMF620), checked by the configurator | Stays in SoR |
| Pricing | List price, price books, promotions, bundle discounts, co-terming | One pricing and quote engine (TMF620, quote TMF648) | Stays in SoR |
| Commercial to service breakdown | Fibre 900 to Broadband, Access, Router services | Catalogue plus order orchestration (L5/L6) | CONFIRMED in the MVP; never CPQ |

The agent never calculates a price. It asks the catalogue and quote engine for one and asks policy for permission:
the agent proposes, policy decides, the workflow writes.

## Options considered

| Option | What moves | Verdict |
|---|---|---|
| A. Everything stays in Salesforce CPQ | Nothing | Rejected: eligibility and approvals stay hidden in CPQ screens, so the agent and other channels cannot reuse or explain them |
| **B. Hybrid** | Eligibility, approval and terms decisions to L4/L5; definitions and pricing stay in the catalogue and quote engine | **Chosen** |
| C. Standalone CPQ outside Salesforce | Catalogue, configurator and pricing to a separate headless service behind TMF APIs | Roadmap only: worth it for an operator with several order-capture stacks needing one catalogue. It becomes a new SoR in L6, not part of the context layer, and needs its own business case and a full price-parity regression test |

## Why pricing does not move into L4 (by severity)

- **High, two sources of price.** Quote, order, bill and customer contract information must show one price. Price logic
  in L4 next to Salesforce price books will drift: a revenue, audit and regulatory risk (INFERRED).
- **High, L4 is not a system of record.** L4 reads facts and decides. Holding price books would make it a SoR without
  offer versioning, effective dates or product-management ownership.
- **Medium, one answer for every channel.** Agent, web, retail and partner channels must price the same way; one engine
  behind TMF620/TMF648 does that.
- **Medium, rebuild cost.** Moving pricing out means building and running our own configurator and pricing engine.

## Consequences

- **Contracts.** L4 reads the catalogue through TMF620 (cached, versioned, never copied) and returns allow or deny with
  reasons. Quote (TMF648) and order (TMF622) stay in the SoR. Product offering qualification (TMF679) is the natural
  standard home for the eligibility check; the MVP uses a policy call, not a TMF679 implementation (INFERRED fit).
- **Ownership.** Product managers own offers and prices in the catalogue. A commercial or risk owner owns L4 policies,
  versioned, tested and change-approved like code.
- **Audit.** Each quote and decision records the catalogue version, the policy version and the reasons, so any price
  or refusal can be replayed.
- **Overlap with built-in configuration.** Where Salesforce configuration still holds a rule that overlaps OPA, OPA
  decides first and the overlap is documented (risk R9).
- **Demo picture.** The Salesforce box is "Product catalogue and quote" (not removed). L4 lists the rules it holds:
  eligibility, authorised contact, overdue balance, upgrade only.
