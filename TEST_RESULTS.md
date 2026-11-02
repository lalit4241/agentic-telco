# Test results — AgenticTelco MVP, 30 Oct 2026 (UK time)

The MVP ("Agent upgrades a Business Customer Service (B2B), on existing systems") ran live on this host on 30 Oct 2026, 17:04–17:09 UK time (GMT): Brightwell Design Ltd, Fibre 150 (£27) → Fibre 900 (£45), against the Salesforce org `sfcomms` (instance GBR58). Start it with `./run.sh mvp-up`; re-record and verify with `./run.sh mvp-record`.

## MVP summary

Latest run: 30 Oct 2026, 18:00–18:11 UK time (GMT), happy path re-recorded 21:12, after the "TMF Open APIs only" change: everything above L6 reaches Salesforce only through TM Forum Open APIs (Salesforce's own TMF APIs plus the `AgenticTelco_` Apex facades); no SOQL and no sObject REST.

| Suite | Command | Result |
|---|---|---|
| Apex tests (TMF620/622/632/637/648/671 facades in Salesforce) | `sf apex run test -o sfcomms --class-names AgenticTelco_TmfTest --code-coverage` | **10/10 passed, 97.1% coverage** (deploy 0AfQH00000Q5Zm90AF; TMF637 98%, TMF632 90%, TMF622 98%, TMF648 97%, TMF620 95%, TMF671 100%, shared Tmf 99%) |
| OPA policy tests (MVP rule `mvp-2026-10-30.1`) | `.tools/bin/opa test stack/mvp/policy` | **10/10 passed** |
| Python unit tests | `.venv/bin/python -m pytest -q tests/test_unit.py tests/test_mvp_unit.py` | **53/53 passed**, including: the MVP stack issues no SOQL and no sObject REST (static scan of `stack/mvp/**`), the runtime guard rejects `/query` and `/sobjects`, the scan catches a planted regression, no "native Salesforce" label left, redaction |
| Web build tests (MVP) | `cd web && npm test` | **13/13 passed**, including: every L6 call in the four recordings has method, path and a "TMFnnn Name" tag (the mocked payment link is the one non-TMF stand-in); Salesforce paths are only `apexrest/agentictelco/tmfNNN` or `connect/comms`; chips read "TMF Open API (Salesforce)" / "Legacy stand-in (mocked)"; no "conformant"/"certified" claims; evidence gallery in story order |
| Legacy web build tests | `cd web && npm run test:legacy` | **10/10 passed** |
| Playwright e2e (MVP) | `cd web && npm run e2e` | **48/48 passed** (adds: L6 API view, call detail with "Provided by", record link and redaction, L4 TMF reads behind the context pack, Exposed APIs list, Salesforce evidence gallery) |
| Live journeys, checked against the org | `./run.sh mvp-record` (`scripts/record_mvp.py` + `scripts/mvp/verify_recordings.py`) | **4/4 passed, ALL PASS** (also checks the TMF637 Upgrade productRelationship and that no trace path uses `/query` or `/sobjects`) |

## Model speed test (build step 0)

8 vCPU, 15 GB RAM, CPU only, Ollama, `think=false`, temperature 0, `num_ctx` 4096 (`scripts/mvp/model_speedtest.py`, raw data in `docs/mvp/model-speedtest.json`).

| Model (licence) | Load | Median turn | p90 | Max | Tool calls correct |
|---|---|---|---|---|---|
| **Qwen3-4B-Instruct-2507 (Apache 2.0) — chosen** | 11.4 s | 4.26 s | 5.91 s | 5.94 s | **8/8** |
| Phi-4-mini-instruct (MIT) | 9.4 s | 3.20 s | 5.79 s | 8.32 s | 2/8 (writes tool calls as text) |
| Granite 3.3 2B (Apache 2.0) | 7.6 s | 2.95 s | 6.98 s | 7.93 s | 2/8 (skips tool calls) |

Qwen3-4B-Instruct-2507 is the only model that called the tools correctly, so it was chosen. In the full journeys a turn takes longer than in the speed test, because one turn includes the context pack (Salesforce reads) and up to three model calls.

## MVP journeys (live, 30 Oct 2026, TMF Open APIs only)

| Case | Turn times | Outcome | Salesforce calls | Checked in the org |
|---|---|---|---|---|
| 1. Happy path (Sam, Decision Maker), recorded 21:12 UK | 31.1 s, 15.7 s | Offer Fibre 900 £45, contract end 28 August 2027 kept; order 00000173 (MVP-DD97C74D) Activated at £45; Live 31 October 2026; intent fulfilled | 22, all TMF (620, 622, 629, 632, 637, 648, 671) | Fibre 900 Installed (serial AT-MVP-DD97C74D), install 31/10/2026, usage end 28/08/2027, £45; Fibre 150 Obsolete with end date 31/10/2026; Upgrade relationship Fibre 150 → Fibre 900; flowCreatedAssets = 0 |
| 2. Not authorised (Alex, Business User), 18:00 UK | 16.4 s | Policy says no; agent points to Sam; no order | 7 reads, all TMF | No records written |
| 3. Overdue balance, 18:00 UK | 18.0 s | Only the overdue reason (£312.40) and the pay link; no order | 6 reads, all TMF | No records written |
| 4. Order delayed (+2 days), 18:02 UK | 22.8 s, 21.3 s | Sam told first with the revised date 2 November 2026; order 00000171 Activated at £45; Live 2 November 2026; intent atRisk → fulfilled | 22, all TMF | Fibre 900 install date 2026-11-02 = live date; Fibre 150 Obsolete; Upgrade relationship; flowCreatedAssets = 0 |

- Each case resets the seed first, so the org now holds the happy-path end state (recorded last); the delayed run's Fibre 900 is Obsolete again, and the verifier allows for that by comparing recording times.
- The happy-path recording is the run after the account was renamed to Brightwell Design Ltd (order 00000173, recorded 21:12 UK, regenerated from its stored conversation and audit trail); it is the last write case, so the org holds its end state.
- Salesforce evidence screenshots (`web/src/mvp/evidence/`, 01–07), for the order 00000173 run: account and contact, order 00000173 (Activated, one Fibre 900 line at £45.00), Fibre 150 Obsolete, Fibre 900 Installed, the Upgrade relationship (From Date 30/10/2026 21:12) and the Apex facade classes. No 'before' shot of Fibre 150 (the org now holds the after state); the quote shot is held back pending a decision.

## What is real and what is mocked in the MVP

- **Real:** Salesforce records (Account, Contacts and roles, Quote, Order, Assets), the TMF620/622/648/671 facades (Apex inside Salesforce), OPA, Operaton BPMN, the model (local), the audit timeline.
- **Stand-ins (labelled on screen):** Billing B (overdue balance), site availability, the legacy OSS (port reservation and the overnight batch).
- **Mocked:** the L7 network view and the payment link.

---

# Earlier results — full AgenticTelco demo, 26 Oct 2026 (UK time)

All results below come from runs on 26 Oct 2026. The stack ran in real-org mode:

- `ZG_SOR_MODE=commscloud`.
- L6 was the Salesforce Communications Cloud org `sfcomms` (`00DQH00000P7uDa`, API 68.0), reached through `stack/l6_salesforce_adapter` with a server-side sf CLI session.
- No stand-in was used on the SoR path.

## Summary

| Suite | Command | Result |
|---|---|---|
| Python unit (policy client, router, PII redaction, ledger, adapter labelling, …) | `.venv/bin/python -m pytest -q tests/test_unit.py` | **25 passed** |
| OPA policy tests (Rego) | `.tools/bin/opa test stack/l4_context/policy stack/inference/policy` | **12/12 passed** |
| Apex tests in `sfcomms` (deploy `0AfQH00000Q1p370AB`) | `sf project deploy start … --tests AgenticTelco_TmfTest` | **8/8 passed, 97% coverage** of the AgenticTelco_ classes (gate: 85%; re-run 30 Oct 2026) |
| Stack integration against the real org | `pytest tests/test_stack.py` | see [Stack integration](#stack-integration) |
| Real-org journeys (recorded) | `ZG_SOR_MODE=commscloud ./run.sh journeys` | **9/9 expected outcomes**, 0 inference stub calls |
| Web build tests (recording shape, encryption, labels) | `cd web && npm test` | **10/10 passed** |
| Playwright e2e (encrypted page, gate, all views, replay) | `cd web && node test/e2e.js` | **34/34 passed** |

`scripts/test_all.sh` runs every suite except the Apex deploy.

## Real-org journeys

**Recording:** `recordings/run-2026-10-26.json`, 19:53–20:00 UK time (re-recorded after the AppUsageAssignment fix).

- The recording started with a cold semantic cache. The demo inventory was reset first (AgenticTelco Assets only).
- **SoR counts:** 90 L6 adapter calls → **161 Salesforce REST calls**. Adapter calls by runtime: **58 OOTB**, **24 custom TMF API on Salesforce**, **8 TMF679 calls** that were tried natively, returned 400 and were handled by our layer.

| # | Journey | Customer | Outcome | Ledger calls | BPMN end (Operaton 2.2.0) | Inference |
|---|---|---|---|---|---|---|
| 1 | Work-from-home upgrade (happy path) | C-1002 | completed (quote → order → OSS → Asset) | 55 | End_Completed | litellm → ollama/qwen2.5:0.5b |
| 2 | L4 policy blocks the upgrade | C-1001 | **blocked-by-policy** ("Policy blocked"; no SoR write) | 21 | – (never started) | litellm → ollama |
| 3 | Misbehaving agent → 'Policy blocked' path in L5 | C-1001 | **blocked-by-policy-in-L5** (OPA gate in BPMN before the SoR write) | 31 | End_PolicyBlocked | semantic-cache hit |
| 4 | Activation fallout → BPMN compensation | C-1004 | **compensated** (TMF641 activation failed → TMF622 order cancelled through the custom TMF API, no Asset change) | 39 | End_Compensated | litellm → ollama |
| 5 | Fault care with A2A hand-off | C-1003 | resolved | 16 | – (no order) | litellm → ollama |
| 6 | TMF679 says not available at this address | C-1003 | not-qualified (Fibre 1600 needs XGS-PON; address is FTTP/FTTC) | 18 | – | litellm → ollama |
| 7 | Rule changed in L4 – zero Salesforce changes | C-1001 (same as #2) | completed under the new rule | 55 | End_Completed | semantic-cache hit |
| 8 | Worker killed mid-order → resumes exactly once | C-1004 | completed, **exactly 1** service order (lock 30 s) | 56 | End_Completed | litellm → ollama |
| 9 | Agent identity tries to drive the process | C-1004 | completed. Every probe was rejected | 55 | End_Completed | litellm → ollama |

### Guardrail probes (journey 9)

These probes ran with the agent identity `zgagent`, which has start and read rights only.

| Attempt | HTTP | Result |
|---|---|---|
| Complete the in-flight service task | 400 | rejected (agent cannot complete) |
| Unlock the in-flight service task | 403 | rejected |
| Change a process variable | 403 | rejected |
| Suspend the process instance | 403 | rejected |
| Delete the process instance | 403 | rejected |
| Read the process instance | 200 | allowed |
| Deploy a new process definition | 403 | rejected |
| `l4-context` asks the inference gateway for a model | 403 | rejected (OPA never calls a model) |
| `l5-worker` asks the inference gateway for a model | 403 | rejected (Operaton never calls a model) |

Inference governance:

- **Route:** a customer-data reasoning prompt went to `zg-sovereign-large`, served by `litellm → ollama/qwen2.5:0.5b`, with 4 PII items redacted.
- **Denied:** `us-frontier-saas` was denied by OPA ("customer data may only go to local/sovereign models (UK GDPR)").

### Salesforce REST calls behind the journeys (ids masked)

| Count | Call | Runtime |
|---|---|---|
| 23 | GET customermanagement/v4/customer/{id} (TMF629) | OOTB |
| 23 | GET partymanagement/v5/organization/{id} (TMF632) | OOTB |
| 23 | GET partymanagement/v5/individual/{id} (TMF632) | OOTB |
| 24 | GET query (SOQL: AgenticTelco Account / Asset ids, AppUsageAssignment guard) | OOTB |
| 12 | GET productinventorymanagement/v5/productinventory/{id} (TMF637) | OOTB |
| 8 | POST productofferingqualification/v5/checkProductOfferingQualification (TMF679) | OOTB attempt → 400 → our-layer rule |
| 4 / 4 | POST / PATCH sobjects/Asset | OOTB |
| 4 | POST sobjects/AppUsageAssignment (SubscriptionManagement, before activation) | OOTB |
| 17 + 3 | GET apexrest/agentictelco/tmf620/{id} (+ `?isBundle=true`) | custom TMF API on Salesforce |
| 6 | POST apexrest/agentictelco/tmf648/quote | custom TMF API on Salesforce |
| 5 / 5 | POST / PATCH apexrest/agentictelco/tmf622/productOrder | custom TMF API on Salesforce |

Rules held throughout the run:

- No DELETE was issued.
- Only AgenticTelco-prefixed records were created or changed.
- The recording contains no host name or token.

## Org flow check: "Custom Assetize Order"

The org has an active record-triggered flow, `Custom_Assetize_Order` v3. It runs on Order update to `Status = Activated`, on an async-after-commit path. Each AgenticTelco Order activated before the fix made it fail at `CreateOrUpdateRelatedAsset`, which sent a FlowApplication error email. The fix and its evidence are in [org capabilities](docs/api/org-capabilities.md#org-automation-custom-assetize-order-flow).

**Fix:** since 19:50 UK time, before activating an AgenticTelco Order the adapter creates an OOTB `AppUsageAssignment` with `SubscriptionManagement`. The flow then takes its own no-op branch. The flow and org setup are unchanged.

| Check (fix in place from 19:50 UK time) | Result |
|---|---|
| Orders activated after the fix (single check order `801QH00002LKUxjYAH` + journeys 1, 7, 8, 9) | 5/5 have a `SubscriptionManagement` AppUsageAssignment, created 1–2 s before activation (OOTB POST 201) |
| Journey 4 (fallout) order | Ends in `Exception`, which does not match the flow's `Activated` entry criteria, so the flow is not triggered |
| `FlowInterview` errors after the fix | Every one we traced belongs to an Order activated **before** the fix. They are Salesforce retries of the async path. None belongs to a post-fix Order |
| FlowApplication emails after the fix (Gmail, read-only check) | 10 traced (19:51–19:58 UK time). The `$Record` in each one is a pre-fix Order (for example `801QH00002LKTGvYAP`, `…LKXfWYAX`, `…LKbj3YAD`, `…LK8E3YAL`). **0 name a post-fix Order** |
| Double assetization | None. The flow ends without calling the assetize action, and our layer writes the Asset once (sObject REST) |

**Known residue:** Orders activated before the fix cannot be repaired from our side. Salesforce rejects a SubscriptionManagement AppUsageAssignment on an Order that is already activated (`FIELD_INTEGRITY_EXCEPTION`), and we do not edit existing records. Salesforce may keep retrying those async interviews for a while, so some error emails may still arrive for them.

- **What we saw:** `FlowInterview` errors kept arriving about once a minute, including at 20:00, 20:02 and 20:03 UK time, when nothing on our side was running. That fits retries of pre-fix interviews.
- **What is still unverified:** FlowApplication emails stopped at 19:58 UK time. The interviews logged after that (20:07–20:11) therefore have no email to trace them to a record. All Orders our layer activated in that window have the assignment.

## Stack integration

| Suite | Command | Result |
|---|---|---|
| Live-stack integration (real org: L1 → L2 → L4 → L5 Operaton → L6 → sfcomms) | `ZG_SOR_MODE=commscloud .venv/bin/python -m pytest -q tests/test_stack.py` | **13 passed** in 297.9 s (20:06–20:11 UK time, after the flow fix) |

- **Two earlier fixes:** a per-run cache nonce, so the cache test does not hit a warm entry, and a 180 s wait for the crash/resume saga on the CPU model.
- **Flow check after the integration run:**
  - The run activated 4 AgenticTelco Orders (`801QH00002LK8M9YAL`, `…LKWHzYAP`, `…LKWedYAH`, `…LJtAFYA1`). **Each has a SubscriptionManagement AppUsageAssignment.**
  - The fallout Order `…LKUxkYAH` ended in `Exception`, which does not match the flow's entry criteria.
- **Inventory:** reset afterwards with `seed/customers/seed_customers.py --reset-inventory`.

## Known limits

- **OSS is mocked:** TMF641/645/621 are served by the OSS mock and labelled "stand-in (mocked OSS)", with 9 calls in the recording. Salesforce is the SoR only.
- **TMF679:** the org has no default qualification procedure. Native TMF679 is called first every time, and the labelled our-layer rule decides. Org setup was not changed.
- **Model size:** qwen2.5:0.5b is a small CPU model, chosen for reproducibility. Policy and BPMN make every decision; the model only extracts and summarises.
