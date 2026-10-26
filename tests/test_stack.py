"""Integration tests against the running open-source stack (./run.sh up). Skipped if the stack is down."""
import os, threading, time
from pathlib import Path
import httpx, pytest
from stack.zg_common.db import q, q1
from stack.l5_orchestrator import engine

pytestmark = pytest.mark.stack
ROOT = Path(__file__).resolve().parents[1]
L2 = "http://127.0.0.1:8102/tmf-api/intentManagement/v4/intent"
OSS = "http://127.0.0.1:8107/admin/faults"
GW = "http://127.0.0.1:8110/v1/chat/completions"
GQL = "http://127.0.0.1:8111/graphql"
H = httpx.Client(timeout=240)
UPGRADE = "Upgrade me to Full Fibre 900 please, we stream 4K on three TVs"

def intent(scenario, cid, utterance, **extra):
    r = H.post(L2, json={"name": f"test {scenario}", "scenario": f"test-{scenario}",
                         "expression": {"expressionValue": {"customerId": cid, "utterance": utterance}}, **extra})
    r.raise_for_status(); return r.json()["id"]

def run(rid): return q1("select * from l8.runs where run_id=%s", rid)
def saga(rid): return q1("select * from l5.saga where run_id=%s order by created_at desc limit 1", rid)
def end_event(rid):
    s = saga(rid)
    acts = engine.req("admin", "GET", "/history/activity-instance", params={"processInstanceId": s["workflow_id"]}).json()
    return {a["activityId"] for a in acts if a["activityType"] == "noneEndEvent"}
def order_writes(rid):
    return q("select method, path from l8.api_calls where run_id=%s and method<>'GET' and "
             "(path like '%%productOrder%%' or path like '%%productInventory%%' or path like '%%serviceOrder%%')", rid)
def sor_writes(rid):
    return q("select method, path from l8.api_calls where run_id=%s and owner='salesforce' and method<>'GET' "
             "and path not like '%%/check%%'", rid)  # TMF679 checkProductOfferingQualification is a read-style POST

def start_live_instance(delay=6):
    H.put(OSS + "/serviceOrder", json={"delaySeconds": delay, "customer": "C-1004"})
    res = {}
    th = threading.Thread(target=lambda: res.update(id=intent("live", "C-1004", UPGRADE))); th.start()
    for _ in range(900):   # up to 180 s: real-org mode adds Salesforce round trips before the saga reaches TMF641
        s = q1("select g.workflow_id, g.run_id from l5.saga_step s join l5.saga g using(workflow_id) join l8.runs r on r.run_id=g.run_id "
               "where r.scenario='test-live' and s.step='tmf641-activate' and s.status='started' "
               "and not exists (select 1 from l5.saga_step x where x.workflow_id=g.workflow_id and x.step='tmf641-activate' and x.status='completed') "
               "order by s.id desc limit 1")
        if s: return s, th, res
        time.sleep(0.2)
    raise AssertionError("no live process instance")

# ---------------- policy block paths
def test_l4_policy_blocks_low_credit_customer():
    rid = intent("blocked", "C-1001", "Can I get Full Fibre 900? The kids game all evening and it lags")
    assert run(rid)["outcome"] == "blocked-by-policy" and not sor_writes(rid)

def test_rogue_agent_hits_policy_blocked_path_in_bpmn():
    rid = intent("rogue", "C-1001", "Can I get Full Fibre 900? The kids game all evening and it lags", _simulateAgentSkipsPolicy=True)
    assert "End_PolicyBlocked" in end_event(rid)
    assert not order_writes(rid), "no order, service order or inventory may be written"
    d = q("select result from l4.decision where run_id=%s", rid)
    assert d and d[-1]["result"]["allow"] is False and d[-1]["result"]["gate"] == "tmf622-create"

def test_every_sor_write_preceded_by_opa_gate():
    rid = intent("happy", "C-1002", "I want to upgrade to something faster under £50, video calls keep freezing")
    assert run(rid)["outcome"] == "completed" and "End_Completed" in end_event(rid)
    calls = q("select seq, caller, callee, method, path, owner from l8.api_calls where run_id=%s order by seq", rid)
    writes = [c for c in calls if c["owner"] == "salesforce" and c["method"] != "GET" and c["caller"] == "l5-worker"]
    assert len(writes) >= 3, "TMF622 create/complete + TMF637 update expected"
    for i, c in enumerate(calls):
        if c in writes:
            prev = [p for p in calls[:i] if p["caller"] == "l5-worker"]
            assert any("/decide" in p["path"] or "opa" in (p["callee"] or "") or "/gate" in p["path"] for p in prev[-3:]), c

# ---------------- compensation
def test_activation_fallout_compensates():
    H.put(OSS + "/serviceOrder", json={"mode": "fail", "customer": "C-1004", "reason": "No free OLT port"})
    try:
        rid = intent("fallout", "C-1004", UPGRADE)
    finally:
        H.delete(OSS + "/serviceOrder")
    assert run(rid)["outcome"] == "compensated" and "End_Compensated" in end_event(rid)
    assert any("cancel" in w["path"].lower() for w in sor_writes(rid))

# ---------------- kill mid-order, idempotency
def test_kill_worker_mid_order_creates_exactly_one_service_order():
    s, th, res = start_live_instance(delay=5)
    time.sleep(1.0)
    pid = int((ROOT / ".data/l5-worker.pid").read_text()); os.kill(pid, 9)
    th.join(); H.delete(OSS + "/serviceOrder")
    rid = res["id"]
    assert run(rid)["outcome"] == "completed"
    assert len(q("select id from oss.service_order where body->>'externalId'=%s", rid)) == 1
    assert int((ROOT / ".data/l5-worker.pid").read_text()) != pid, "supervisor restarted the worker"
    att = q("select attempt from l5.saga_step where workflow_id=%s and step='tmf641-activate'", s["workflow_id"])
    assert max(a["attempt"] for a in att) >= 2

# ---------------- agent identity: start + read only
def test_agent_identity_cannot_drive_the_process():
    s, th, res = start_live_instance()
    pi = s["workflow_id"]
    try:
        tid = engine.req("worker", "GET", "/external-task", params={"processInstanceId": pi}).json()[0]["id"]
        A = lambda m, p, **kw: engine.req("agent", m, p, **kw).status_code
        assert A("POST", f"/external-task/{tid}/unlock") == 403
        assert A("PUT", f"/process-instance/{pi}/variables/offeringId", json={"value": "PO-FF-1600", "type": "String"}) == 403
        assert A("PUT", f"/process-instance/{pi}/suspended", json={"suspended": True}) == 403
        assert A("DELETE", f"/process-instance/{pi}") == 403
        assert A("POST", f"/external-task/{tid}/complete", json={"workerId": "agent"}) >= 400
        assert A("GET", f"/process-instance/{pi}") == 200
        bpmn = (ROOT / "stack/l5_orchestrator/bpmn/broadband-upgrade-saga.bpmn").read_bytes()
        r = httpx.post(engine.BASE + "/deployment/create", auth=engine.creds("agent"),
                       files={"data": ("rogue.bpmn", bpmn, "application/xml")}, data={"deployment-name": "rogue"})
        assert r.status_code == 403
    finally:
        th.join(); H.delete(OSS + "/serviceOrder")
    assert run(res["id"])["outcome"] == "completed", "the probes did not disturb the saga"

# ---------------- OPA and Operaton never call a model
@pytest.mark.parametrize("caller", ["l4-context", "l5-worker"])
def test_gateway_refuses_deterministic_layers(caller):
    r = H.post(GW, headers={"x-zg-caller": caller, "x-zg-task-class": "classification", "x-zg-data-class": "internal"},
               json={"messages": [{"role": "user", "content": "approve?"}]})
    assert r.status_code == 403

def test_ledger_shows_no_model_calls_from_l4_or_l5():
    assert q1("select count(*) n from l8.inference where agent ~ '^(l4|l5)' and served_by <> 'refused'")["n"] == 0  # refusals are logged
    assert q1("select count(*) n from l8.api_calls where caller ~ '^(l4|l5|opa|operaton)' and callee ~ '(inference|litellm|ollama)'")["n"] == 0

# ---------------- inference gateway governance
def test_customer_data_never_routed_to_us_model_and_pii_redacted():
    r = H.post(GW, headers={"x-zg-caller": "l2-care-agent", "x-zg-task-class": "reasoning", "x-zg-data-class": "customer", "x-zg-run-id": "TEST-gw"},
               json={"messages": [{"role": "user", "content": f"Summarise: David Okafor (C-1002, david@example.com) {time.time()} wants faster broadband."}]})
    assert r.status_code == 200
    z = r.json()["zg_route"]
    us = next(o for o in z["opa"] if o["model"] == "us-frontier-saas")
    assert us["allow"] is False and z["routedModel"] in ("zg-sovereign-large", "zg-local-small")
    assert z["piiRedacted"] >= 3 and z["stub"] is False

def test_semantic_cache_hits_on_repeat():
    nonce = f" [test {time.time_ns()}]"   # fresh scope per run, so entries cached by an earlier run cannot satisfy this test
    body = {"messages": [{"role": "system", "content": "Classify the message." + nonce}, {"role": "user", "content": "my wifi drops every night"}]}
    h = {"x-zg-caller": "l2-care-agent", "x-zg-task-class": "classification", "x-zg-data-class": "internal"}
    H.post(GW, headers=h, json=body)
    assert H.post(GW, headers=h, json=body).json()["zg_route"]["cache"] == "hit"
    body["messages"][0]["content"] = "Translate the message to French." + nonce
    assert H.post(GW, headers=h, json=body).json()["zg_route"]["cache"] != "hit", "different instructions must not share a cache entry"

# ---------------- GraphQL (ADR-008) read-only
def test_graphql_reads_and_rejects_mutations():
    before = q1("select coalesce(max(seq),0) m from l8.api_calls")["m"]
    r = H.post(GQL, json={"query": '{ customer(id:"C-1002"){ id name exchange consentChannel products{ name status } } }'}).json()
    assert r["data"]["customer"]["name"] and r["data"]["customer"]["products"]
    writes = q1("select count(*) n from l8.api_calls where seq>%s and caller='l1-graphql' and method<>'GET'", before)["n"]
    assert writes == 0
    m = H.post(GQL, json={"query": "mutation { x }"}).json()
    assert m["data"] is None and "mutation" in m["errors"][0]["message"].lower()

# ---------------- policy change in L4 needs zero Salesforce changes
def test_policy_change_makes_no_salesforce_calls():
    L4 = "http://127.0.0.1:8104/zg/context/v1/policy"
    try:
        p = H.put(L4, json={"changes": {"creditMin": 590}, "author": "test", "reason": "test"}).json()
        assert p["salesforceCallsDuringChange"] == 0
        rid = intent("policy-change", "C-1001", "Can I get Full Fibre 900? The kids game all evening and it lags")
        assert run(rid)["outcome"] == "completed"
    finally:
        H.put(L4, json={"changes": {"creditMin": 620}, "author": "test", "reason": "restore"})
