"""Record the AgenticTelco journeys against the REAL open-source stack (./run.sh up must be running).
Writes recordings/run-<date>.json – GitHub Pages replays exactly this file, labelled
"recorded from the open-source stack run on <date>". Run on a fresh stack (./run.sh reset && ./run.sh up) for repeatable data."""
import datetime, json, os, subprocess, sys, threading, time
from pathlib import Path
import httpx
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from stack.zg_common.db import q, q1
from stack.zg_common.runs import collect_run
from stack.zg_common.registry import APIS
from stack.l5_orchestrator import engine
from stack.l5_orchestrator.state import process_state

ROOT = Path(__file__).resolve().parents[1]
L2 = "http://127.0.0.1:8102/tmf-api/intentManagement/v4/intent"
L4 = "http://127.0.0.1:8104/zg/context/v1"
OSS = "http://127.0.0.1:8107/admin/faults"
GW = "http://127.0.0.1:8110"
H = httpx.Client(timeout=240)

def intent(scenario, title, cid, utterance, **extra):
    body = {"name": title, "scenario": scenario, "expression": {"expressionValue": {"customerId": cid, "utterance": utterance}}, **extra}
    r = H.post(L2, json=body); r.raise_for_status(); return r.json()

def proc_for(rid):
    s = q1("select workflow_id from l5.saga where run_id=%s", rid)
    return process_state(s["workflow_id"]) if s else None

def package(scenario, title, story, rid, **more):
    data = collect_run(rid)
    p = proc_for(rid)
    out = {"scenario": scenario, "title": title, "story": story, "runId": rid, **data, "process": p, **more}
    r = data["run"] or {}
    print(f"  {scenario:28s} {rid}  outcome={r.get('outcome')}  calls={len(data['calls'])}  events={len(data['events'])}"
          f"  bpmnEnd={(p or {}).get('endEvent')}  inference={[i['served_by'] for i in data['inference']]}", flush=True)
    return out

def worker_pid():
    return int((ROOT / ".data" / "l5-worker.pid").read_text().strip())

def main():
    J = []
    t_run = datetime.datetime.now(datetime.timezone.utc)   # SoR counters cover this recording only (the ledger keeps earlier runs)
    q("delete from l3.semantic_cache")   # recording starts cold: first use of each prompt goes to the model, repeats show cache hits
    # 1 · happy path
    r = intent("upgrade", "Work-from-home upgrade", "C-1002",
               "I work from home and my broadband is too slow for video calls, I want to upgrade to something faster under £50")
    J.append(package("upgrade", "Work-from-home upgrade (happy path)",
                     "L1 captures the intent as TMF921 → L2 agent reasons over L4 context and L3 data → Salesforce SoR (TMF620/679/648) → "
                     "L5 BPMN saga writes the order (TMF622/641/637), each SoR write gated by OPA.", r["id"]))
    # 2 · blocked in L4 by the agent's own policy check
    r = intent("policy-blocked", "Gigabit request below credit threshold", "C-1001", "Can I get Full Fibre 900? The kids game all evening and it lags")
    J.append(package("policy-blocked", "L4 policy blocks the upgrade", "Credit 598 is below policy v1 creditMin 620 – the rule lives in L4 (OPA), not in Salesforce.", r["id"]))
    # 3 · misbehaving agent skips L4 → L5 pre-write gate takes the explicit 'Policy blocked' path
    r = intent("rogue-agent", "Agent skips the policy check", "C-1001", "Can I get Full Fibre 900? The kids game all evening and it lags",
               _simulateAgentSkipsPolicy=True)
    J.append(package("rogue-agent", "Misbehaving agent → 'Policy blocked' path in L5",
                     "The agent skips L4 and starts the saga. The first SoR-writing BPMN task calls OPA, is denied, and the process ends at End_PolicyBlocked. No order, service order or inventory is written (only the agent's draft TMF648 quote exists).", r["id"]))
    # 4 · activation fallout → compensation
    H.put(OSS + "/serviceOrder", json={"mode": "fail", "customer": "C-1004", "reason": "No free OLT port on the PON tree"})
    try:
        r = intent("fallout", "Activation fails – compensate", "C-1004", "Please upgrade me to Full Fibre 900, I stream 4K on three TVs")
    finally:
        H.delete(OSS + "/serviceOrder")
    J.append(package("fallout", "Activation fallout → BPMN compensation",
                     "TMF641 activation fails in the (mocked) OSS. The boundary error triggers compensation: the TMF622 order is cancelled in the SoR. No half-done order is left.", r["id"]))
    # 5 · fault → TMF621 ticket → A2A network agent
    r = intent("fault", "Broadband keeps dropping", "C-1003", "My broadband keeps dropping out every evening, it has cut out twice today")
    J.append(package("fault", "Fault care with A2A hand-off", "The care agent opens a TMF621 ticket and hands off to the network agent over A2A.", r["id"]))
    # 6 · not qualified
    r = intent("not-qualified", "Multi-gig not available", "C-1003", "I want Full Fibre 1.6G please")
    J.append(package("not-qualified", "TMF679 says not available at this address", ("TMF679 is called on the real org first (400: no default qualification procedure, and org setup is left unchanged), so the labelled "
                 "our-layer rule compares the offer's XGS-PON requirement with the address technology (FTTP/FTTC). Result: unqualified. The agent stops without writing anything." if os.environ.get("ZG_SOR_BASE") else "The SoR's qualification check says the address has no XGS-PON. The agent stops without writing anything."), r["id"]))
    # 7 · change the rule in L4 only, re-run the blocked customer
    before = q1("select coalesce(max(seq),0) m from l8.api_calls")["m"]
    pol = H.put(L4 + "/policy", json={"changes": {"creditMin": 590}, "author": "Head of Credit Risk", "reason": "Q4 retention campaign"}).json()
    r = intent("policy-change", "Same customer after the policy change", "C-1001", "Can I get Full Fibre 900? The kids game all evening and it lags")
    H.put(L4 + "/policy", json={"changes": {"creditMin": 620}, "author": "Head of Credit Risk", "reason": "Campaign ended – restore"})
    J.append(package("policy-change", "Rule changed in L4 – zero Salesforce changes",
                     f"creditMin 620 → 590 in OPA (policy v{pol['version']}). Salesforce calls during the change: {pol['salesforceCallsDuringChange']}. "
                     "The same request now completes.", r["id"], policyChange=pol))
    # 8 · crash mid-order → resume, exactly once
    H.put(OSS + "/serviceOrder", json={"delaySeconds": 5, "customer": "C-1004"})
    res = {}
    th = threading.Thread(target=lambda: res.update(intent("crash-resume", "Worker killed mid-order", "C-1004",
                                                            "Upgrade me to Full Fibre 900 please")))
    th.start()
    killed = None
    for _ in range(300):
        s = q1("select s.workflow_id, g.run_id from l5.saga_step s join l5.saga g using(workflow_id) where s.step='tmf641-activate' "
               "and s.status='started' and g.run_id like 'INT-%%' and g.created_at > now() - interval '2 minutes' order by s.id desc limit 1")
        if s and not q1("select 1 from l5.saga_step where workflow_id=%s and step='tmf641-activate' and status='completed'", s["workflow_id"]):
            time.sleep(1.0)
            killed = worker_pid(); os.kill(killed, 9)
            break
        time.sleep(0.2)
    th.join(); H.delete(OSS + "/serviceOrder")
    rid = res["id"]
    so = q("select id from oss.service_order where body->>'externalId'=%s", rid)
    J.append(package("crash-resume", "Worker killed mid-order → resumes exactly once",
                     f"The L5 worker (pid {killed}) was killed with SIGKILL while TMF641 was in flight. The supervisor restarted it; after the {int(os.environ.get('ZG_LOCK_MS', '8000')) // 1000} s lock expired "
                     f"Operaton re-delivered the task and the idempotency key replayed the stored result. Service orders created: {len(so)}.",
                     rid, crash={"killedPid": killed, "serviceOrders": [x["id"] for x in so]}))
    # 9 · guardrails: the agent identity may only START and READ (Operaton authorizations), tried against a LIVE instance
    g = []
    t_guard = datetime.datetime.now(datetime.timezone.utc)
    H.put(OSS + "/serviceOrder", json={"delaySeconds": 6, "customer": "C-1004"})
    res = {}
    th = threading.Thread(target=lambda: res.update(intent("guardrail", "Guardrail probe (live instance)", "C-1004", "Upgrade me to Full Fibre 900 please, we stream a lot")))
    th.start()
    pi = None
    for _ in range(300):
        s = q1("select g.workflow_id from l5.saga_step s join l5.saga g using(workflow_id) join l8.runs r on r.run_id=g.run_id "
               "where r.scenario='guardrail' and r.started_at > %s and s.step='tmf641-activate' and s.status='started' order by s.id desc limit 1", t_guard)
        if s:
            pi = s["workflow_id"]; break
        time.sleep(0.2)
    if not pi:
        raise SystemExit("guardrail probe: no live process instance appeared")
    bpmn = (ROOT / "stack/l5_orchestrator/bpmn/broadband-upgrade-saga.bpmn").read_bytes()
    tasks = engine.req("worker", "GET", "/external-task", params={"processInstanceId": pi}).json()
    tid = tasks[0]["id"] if tasks else "none"
    attempts = [("agent completes the in-flight service task", "POST", f"/external-task/{tid}/complete", {"workerId": "agent"}),
                ("agent unlocks the in-flight service task", "POST", f"/external-task/{tid}/unlock", None),
                ("agent changes a process variable", "PUT", f"/process-instance/{pi}/variables/offeringId", {"value": "PO-FF-1600", "type": "String"}),
                ("agent suspends the process instance", "PUT", f"/process-instance/{pi}/suspended", {"suspended": True}),
                ("agent deletes the process instance", "DELETE", f"/process-instance/{pi}", None),
                ("agent reads the process instance", "GET", f"/process-instance/{pi}", None)]
    for label, m, path, body in attempts:
        r = engine.req("agent", m, path, json=body)
        res_ = "allowed" if r.status_code < 300 else "rejected"
        g.append({"attempt": label, "method": m, "path": "/engine-rest" + path, "status": r.status_code,
                  "result": res_, "detail": r.text[:200] if r.status_code >= 300 else ""})
    import httpx as _h
    r = _h.post(engine.BASE + "/deployment/create", auth=engine.creds("agent"), files={"data": ("rogue.bpmn", bpmn, "application/xml")},
                data={"deployment-name": "rogue", "enable-duplicate-filtering": "false"})
    g.append({"attempt": "agent deploys a new process definition", "method": "POST", "path": "/engine-rest/deployment/create",
              "status": r.status_code, "result": "allowed" if r.status_code < 300 else "rejected", "detail": r.text[:200] if r.status_code >= 300 else ""})
    th.join(); H.delete(OSS + "/serviceOrder")
    J.append(package("guardrail", "Agent identity tries to drive the process", "While a saga is in flight, the agent's Operaton identity tries to "
                     "complete a task, change variables, delete, suspend and deploy. Operaton rejects all of them; only start and read work.", res["id"], guardrails=g))
    for caller in ("l4-context", "l5-worker"):
        r = H.post(GW + "/v1/chat/completions", headers={"x-zg-caller": caller, "x-zg-task-class": "classification", "x-zg-data-class": "internal"},
                   json={"messages": [{"role": "user", "content": "Should this order be approved?"}]})
        g.append({"attempt": f"{caller} asks the inference gateway for a model", "method": "POST", "path": "/v1/chat/completions",
                  "status": r.status_code, "result": "rejected" if r.status_code == 403 else "allowed", "detail": r.text[:160]})
    r = H.post(GW + "/v1/chat/completions", headers={"x-zg-caller": "l2-care-agent", "x-zg-task-class": "reasoning", "x-zg-data-class": "customer",
                                                      "x-zg-run-id": "GUARD-inference"},
               json={"messages": [{"role": "user", "content": "Summarise: David Okafor (C-1002, david@example.com, M4 7HR) wants faster broadband."}]})
    route = r.json().get("zg_route")
    print("  guardrails:", [(x["attempt"], x["status"]) for x in g], "| reasoning route:", route and route["routedModel"], route and route["servedBy"])
    # meta
    ver = engine.req("agent", "GET", "/version").json().get("version")
    stub_used = q1("select count(*) n from l8.inference where stub")["n"]
    sf = q1("""select count(*) n, coalesce(sum(jsonb_array_length(extra->'salesforceCalls')),0) sfcalls from l8.api_calls
                 where callee='l6-salesforce-adapter' and jsonb_typeof(extra->'salesforceCalls')='array' and at >= %s""", t_run)
    sor = ({"system": "Salesforce Communications Cloud (real org)", "orgAlias": "sfcomms", "orgId": "00DQH00000P7uDa", "apiVersion": "68.0",
            "adapter": "stack/l6_salesforce_adapter (server-side, sf CLI session – no token in code, browser or recording)",
            "adapterCalls": sf["n"], "salesforceRestCalls": int(sf["sfcalls"])}
           if os.environ.get("ZG_SOR_MODE") == "commscloud" else {"system": "labelled stand-in"})
    rec = {"recordedAt": datetime.datetime.now(datetime.timezone.utc).isoformat(), "date": datetime.date.today().isoformat(),
           "label": f"recorded from the open-source stack run on {datetime.date.today().isoformat()}",
           "stack": {"l5Engine": f"Operaton {ver}", "eventBus": "Apache Kafka 4.4.0 (KRaft)", "policy": "OPA", "db": "PostgreSQL 17 + pgvector",
                     "inference": "LiteLLM 1.106.2 (MIT core) → Ollama qwen2.5:0.5b", "sorMode": os.environ.get("ZG_SOR_MODE", "standin"),
                     "inferenceStubCalls": stub_used, "sor": sor},
           "bpmn": (ROOT / "stack/l5_orchestrator/bpmn/broadband-upgrade-saga.bpmn").read_text(),
           "apis": APIS, "journeys": J, "guardrails": g, "inferenceGovernance": route,
           "policyHistory": q("select version, data, author, reason, salesforce_calls_during_change, changed_at::text from l4.policy_version order by version")}
    out = ROOT / "recordings" / f"run-{rec['date']}.json"
    out.write_text(json.dumps(rec, indent=1, default=str))
    (ROOT / "recordings" / "latest.json").write_text(json.dumps({"file": out.name, "date": rec["date"]}))
    print("wrote", out, f"{out.stat().st_size/1024:.0f} KB")

if __name__ == "__main__":
    main()
