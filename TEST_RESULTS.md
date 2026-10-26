# Test results — 26 Oct 2026 (UK time)

All results below come from runs on 26 Oct 2026. The stack ran in real-org mode:

- `ZG_SOR_MODE=commscloud`.
- L6 was the Salesforce Communications Cloud org `sfcomms` (`00DQH00000P7uDa`, API 68.0), reached through `stack/l6_salesforce_adapter` with a server-side sf CLI session.
- No stand-in was used on the SoR path.

## Summary

| Suite | Command | Result |
|---|---|---|
| Python unit (policy client, router, PII redaction, ledger, adapter labelling, …) | `.venv/bin/python -m pytest -q tests/test_unit.py` | **24 passed** |
| OPA policy tests (Rego) | `.tools/bin/opa test stack/l4_context/policy stack/inference/policy` | **12/12 passed** |
| Apex tests in `sfcomms` (deploy `0AfQH00000Q1p370AB`) | `sf project deploy start … --tests AgenticTelco_TmfTest` | **6/6 passed, 97.3% coverage** of the AgenticTelco_ classes (gate: 85%) |
| Stack integration against the real org | `pytest tests/test_stack.py` | see [Stack integration](#stack-integration) |
| Real-org journeys (recorded) | `ZG_SOR_MODE=commscloud ./run.sh journeys` | **9/9 expected outcomes**, 0 inference stub calls |
| Web build tests (recording shape, encryption, labels) | `cd web && npm test` | **10/10 passed** |
| Playwright e2e (encrypted page, gate, all views, replay) | `cd web && node test/e2e.js` | **34/34 passed** |

`scripts/test_all.sh` runs every suite except the Apex deploy.

## Real-org journeys

**Recording:** `recordings/run-2026-10-26.json`, 19:27–19:32 UK time.

- The recording started with a cold semantic cache. The demo inventory was reset first (AgenticTelco Assets only).
- **SoR counts:** 90 L6 adapter calls → **149 Salesforce REST calls**. Adapter calls by runtime: **58 OOTB**, **24 custom TMF API on Salesforce**, **8 TMF679 calls** that were tried natively, returned 400 and were handled by our layer.

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
| 16 | GET query (SOQL: AgenticTelco Account / Asset ids) | OOTB |
| 12 | GET productinventorymanagement/v5/productinventory/{id} (TMF637) | OOTB |
| 8 | POST productofferingqualification/v5/checkProductOfferingQualification (TMF679) | OOTB attempt → 400 → our-layer rule |
| 4 / 4 | POST / PATCH sobjects/Asset | OOTB |
| 17 + 3 | GET apexrest/agentictelco/tmf620/{id} (+ `?isBundle=true`) | custom TMF API on Salesforce |
| 6 | POST apexrest/agentictelco/tmf648/quote | custom TMF API on Salesforce |
| 5 / 5 | POST / PATCH apexrest/agentictelco/tmf622/productOrder | custom TMF API on Salesforce |

Rules held throughout the run:

- No DELETE was issued.
- Only AgenticTelco-prefixed records were created or changed.
- The recording contains no host name or token.

## Stack integration

STACK_RESULTS_PLACEHOLDER

## Known limits

- **OSS is mocked:** TMF641/645/621 are served by the OSS mock and labelled "stand-in (mocked OSS)", with 9 calls in the recording. Salesforce is the SoR only.
- **TMF679:** the org has no default qualification procedure. Native TMF679 is called first every time, and the labelled our-layer rule decides. Org setup was not changed.
- **Model size:** qwen2.5:0.5b is a small CPU model, chosen for reproducibility. Policy and BPMN make every decision; the model only extracts and summarises.
