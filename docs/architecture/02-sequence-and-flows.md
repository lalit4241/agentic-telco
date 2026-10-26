# 02 · Sequences and flows

All three flows are the demo design (RECOMMENDED). API names are TM Forum Open API contracts. Whether each call reaches Salesforce or the stand-in depends on what the trial org exposes, which is UNKNOWN until verified (see [03](03-api-event-sid-mapping.md)).

**Rules that apply to every flow (ADR-003):**
- Agents only **start** a process and **read** its state. They never complete, skip or modify BPMN tasks.
- Every BPMN task that writes to Salesforce calls OPA first. A policy "deny" follows an explicit BPMN path.
- OPA and BPMN steps never call a language model. Only agents do, and only through the Inference Gateway.
- Each step uses an idempotency key (process instance ID plus step name), so a retry does not create a duplicate.

## 1. Happy path
```mermaid
sequenceDiagram
  autonumber
  actor C as Customer
  participant UI as L1 Intent UI
  participant AG as L2 Agents (LangGraph)
  participant GW as Inference Gateway
  participant CTX as L3 Context (Postgres)
  participant OPA as L4 OPA
  participant BP as L5 Operaton
  participant SOR as L6 Salesforce or stand-in
  participant OSS as Mocked OSS
  participant EV as Kafka + L8 traces
  C->>UI: "I need faster broadband"
  UI->>AG: TMF921-style intent
  AG->>GW: reason over intent (PII stripped)
  GW-->>AG: proposed plan
  AG->>CTX: read customer context
  AG->>OPA: pre-check eligibility (advisory)
  OPA-->>AG: allow, with reasons
  AG->>BP: start process "broadband-upgrade"
  BP->>OPA: policy check before writes
  OPA-->>BP: allow
  BP->>SOR: TMF679 product offering qualification
  SOR-->>BP: qualified
  BP->>SOR: TMF648 quote
  SOR-->>BP: quote
  BP->>SOR: TMF622 product order
  SOR-->>BP: order acknowledged
  BP->>OSS: TMF641 service order
  OSS-->>BP: completed
  BP->>SOR: TMF637 product inventory update
  BP->>EV: TMF688-style event per step
  AG->>BP: read process state
  AG-->>UI: explain outcome
  UI-->>C: upgrade confirmed
```
The agent's OPA pre-check is advisory, to give a fast explanation. The binding check is the one the BPMN task makes before it writes (RECOMMENDED).

## 2. Policy block
```mermaid
sequenceDiagram
  autonumber
  participant AG as L2 Agents
  participant BP as L5 Operaton
  participant OPA as L4 OPA
  participant SOR as L6 Salesforce or stand-in
  participant UI as L1 Intent UI
  AG->>BP: start process
  BP->>OPA: evaluate credit, consent, capacity
  OPA-->>BP: deny, reason "capacity: no headroom on cabinet"
  Note over BP: Explicit BPMN path "Policy blocked".<br/>No write reaches the system of record.
  BP-->>AG: state = POLICY_BLOCKED, reasons
  AG-->>UI: explain block, offer alternative or human handover
  Note over OPA,UI: Live toggle: a presenter flips a policy flag in OPA data<br/>and reruns, to show the same intent being blocked.
```

## 3. Compensation and fallout
```mermaid
sequenceDiagram
  autonumber
  participant BP as L5 Operaton
  participant SOR as L6 Salesforce or stand-in
  participant OSS as Mocked OSS
  participant DB as Compensation log (Postgres)
  participant EV as Kafka + L8 traces
  BP->>SOR: TMF622 create product order
  SOR-->>BP: order id
  BP->>DB: persist compensation "cancel product order"
  BP->>OSS: TMF641 service order
  OSS-->>BP: failed (injected fault)
  BP->>BP: bounded retries with same idempotency key
  Note over BP: Retries exhausted, so compensation starts.
  BP->>SOR: TMF622 cancelProductOrder
  SOR-->>BP: cancelled
  BP->>DB: mark compensation done
  BP->>OSS: TMF621 create trouble ticket (fallout)
  BP->>EV: compensation and fallout events
```

## 4. BPMN process outline
```mermaid
flowchart LR
  s(("Start")) --> p{"OPA allow?"}
  p -- "deny" --> pb["Policy blocked<br/>(explicit end)"]
  p -- "allow" --> q["TMF679 qualify"]
  q --> qt["TMF648 quote"]
  qt --> po["TMF622 order"]
  po --> so["TMF641 service order"]
  so --> inv["TMF637 inventory"]
  inv --> e(("Done"))
  so -. "error after retries" .-> comp["Compensate:<br/>TMF622 cancel"]
  comp --> tt["TMF621 fallout ticket"]
  tt --> f(("Failed, compensated"))
```
This outline is the design intent (RECOMMENDED). The BPMN XML in the repo is the source of truth once DevBot commits it.

## 5. Notes on SoR write semantics (INFERRED)
- TMF622 v5 defines a `cancelProductOrder` task resource ([TMF622 v5 OAS](https://github.com/tmforum-apis/TMF622_ProductOrder)). Whether the Salesforce org supports cancellation through it is **UNKNOWN**.
- Salesforce documents TMF641 as an **outbound** integration (Salesforce calls an external service-order system) via MuleSoft Direct Integrations ([Salesforce doc](https://developer.salesforce.com/docs/industries/communications/guide/get_started_industry_integrations.html)). In the demo, our BPMN process calls the mocked OSS directly, so Salesforce's outbound TMF641 is not used (RECOMMENDED).
