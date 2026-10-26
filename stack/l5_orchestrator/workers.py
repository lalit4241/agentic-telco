"""L5 · Operaton external-task workers (deterministic – no model is ever called from here).
Each worker: fetch-and-lock → (OPA gate for SoR writes) → idempotent TMF call → complete / bpmnError.
Idempotency key = <processInstanceId>:<step>, so a crashed worker's retry after lock expiry replays, never duplicates."""
import os, socket, sys, time, traceback
from stack.zg_common.config import SOR_BASE, url
from stack.zg_common.db import q, q1, J
from stack.zg_common.http import call
from stack.zg_common.telemetry import setup, RUN_ID
from stack.l5_orchestrator.engine import req

WORKER_ID = os.environ.get("ZG_WORKER_ID", f"zg-l5-worker-{os.getpid()}")
CALLER = "l5-worker"
LOCK_MS = int(os.environ.get("ZG_LOCK_MS", "8000"))
ORD = SOR_BASE + "/tmf-api/productOrderingManagement/v4"
INV = SOR_BASE + "/tmf-api/productInventory/v4"
SO = url("oss_mock") + "/tmf-api/serviceOrdering/v4"
VARS = ["runId", "customerId", "offeringId", "quoteId", "exchange", "currentProductId", "productOrderId", "serviceOrderId"]
tracer = setup("l5-operaton-workers")

class BpmnErr(Exception):
    def __init__(self, code, msg, data=None):
        super().__init__(msg); self.code, self.msg, self.data = code, msg, data or {}

def log_step(pi, rid, step, idem, status, output=None, compensation=None):
    attempt = q1("select count(*) n from l5.saga_step where workflow_id=%s and step=%s and status='started'", pi, step)["n"]
    q("insert into l5.saga_step(workflow_id, step, idem_key, status, attempt, output, compensation, worker) values(%s,%s,%s,%s,%s,%s,%s,%s)",
      pi, step, idem, status, max(attempt, 1), J(output), J(compensation), WORKER_ID)

def gate(v, step, pi):
    """Every SoR write asks L4/OPA first. Deny → BPMN error POLICY_BLOCKED → explicit 'Policy blocked' path."""
    d = call(CALLER, "POST", url("l4_context") + "/zg/context/v1/gate", run_id=v["runId"],
             json={"action": "sor-write", "step": step, "customerId": v["customerId"], "offeringId": v["offeringId"], "processInstanceId": pi}).json()
    if not d.get("allow"):
        raise BpmnErr("POLICY_BLOCKED", f"OPA denied {step}: " + "; ".join(d.get("reasons", [])), {"policyReasons": ", ".join(d.get("reasons", [])),
                      "policyVersion": d.get("policyVersion")})
    return d

def ok(r):
    if r.status_code >= 400:
        raise RuntimeError(f"{r.request.method} {r.request.url} → {r.status_code} {r.text[:200]}")
    return r.json()

# ---------------- handlers: (vars, processInstanceId, idemKey) → output variables
def tmf622_create(v, pi, idem):
    gate(v, "tmf622-create", pi)
    body = {"externalId": v["runId"], "description": "Agentic broadband upgrade (Zero Gravity L5 saga)", "category": "broadband",
            "productOrderItem": [{"id": "1", "action": "modify" if v.get("currentProductId") else "add",
                                  "productOffering": {"id": v["offeringId"]},
                                  **({"product": {"id": v["currentProductId"]}} if v.get("currentProductId") else {})}],
            "quote": [{"id": v.get("quoteId")}], "relatedParty": [{"id": v["customerId"], "role": "customer", "@referredType": "Customer"}]}
    o = ok(call(CALLER, "POST", ORD + "/productOrder", json=body, idem=idem, run_id=v["runId"]))
    return {"productOrderId": o["id"], "_replay": bool(o.get("_idempotentReplay"))}

def tmf641_activate(v, pi, idem):
    # OSS write, not an SoR write → no OPA gate here (the SoR writes either side are gated)
    r = call(CALLER, "POST", SO + "/serviceOrder", idem=idem, run_id=v["runId"], timeout=60,
             json={"externalId": v["runId"], "exchange": v.get("exchange"), "relatedParty": [{"id": v["customerId"], "role": "customer"}],
                   "serviceOrderItem": [{"id": "1", "action": "modify", "service": {"serviceSpecification": {"name": "FTTP access"}}}],
                   "productOrder": {"id": v.get("productOrderId")}})
    if r.status_code == 422:
        e = r.json().get("errorMessage", [{}])[0]
        raise BpmnErr("ACTIVATION_FAILED", f"{e.get('code')}: {e.get('reason')}", {"activationError": e.get("code")})
    o = ok(r)
    return {"serviceOrderId": o["id"], "_replay": bool(o.get("_idempotentReplay"))}

def tmf622_complete(v, pi, idem):
    gate(v, "tmf622-complete", pi)
    ok(call(CALLER, "PATCH", f"{ORD}/productOrder/{v['productOrderId']}", json={"state": "completed"}, run_id=v["runId"]))
    return {}

def tmf637_update(v, pi, idem):
    gate(v, "tmf637-update", pi)
    o = ok(call(CALLER, "POST", INV + "/product", idem=idem, run_id=v["runId"],
                json={"name": v["offeringId"], "productOffering": {"id": v["offeringId"]}, "relatedParty": [{"id": v["customerId"], "role": "customer"}],
                      "productOrderItem": [{"productOrderId": v.get("productOrderId")}]}))
    return {"productId": o["id"]}

# Compensations restore the SoR to its prior state; they are always permitted (never policy-gated) and are idempotent.
def tmf622_cancel(v, pi, idem):
    if not v.get("productOrderId"):
        return {}
    ok(call(CALLER, "POST", ORD + "/cancelProductOrder", idem=idem, run_id=v["runId"],
            json={"productOrder": {"id": v["productOrderId"]}, "cancellationReason": "L5 saga compensation"}))
    return {}

def tmf641_cancel(v, pi, idem):
    o = ok(call(CALLER, "POST", SO + "/cancelServiceOrder", idem=idem, run_id=v["runId"], json={"externalId": v["runId"]}))
    return {"portsReleased": o.get("reservationsReleased", 0)}

HANDLERS = {"tmf622-create": tmf622_create, "tmf641-activate": tmf641_activate, "tmf622-complete": tmf622_complete,
            "tmf637-update": tmf637_update, "tmf622-cancel": tmf622_cancel, "tmf641-cancel": tmf641_cancel}
COMPENSATION = {"tmf622-create": "tmf622-cancel", "tmf641-activate": "tmf641-cancel"}

def tv(d):  # typed variables for Operaton
    out = {}
    for k, val in d.items():
        if k.startswith("_") or val is None:
            continue
        out[k] = {"value": val, "type": "Boolean" if isinstance(val, bool) else "Integer" if isinstance(val, int) else "String"}
    return out

def handle(t):
    topic, pi = t["topicName"], t["processInstanceId"]
    v = {k: x.get("value") for k, x in (t.get("variables") or {}).items()}
    rid = v.get("runId") or t.get("businessKey")
    tok = RUN_ID.set(rid)
    idem = f"{pi}:{topic}"
    q("insert into l5.saga(workflow_id, run_id, engine, state, input) values(%s,%s,'operaton','running',%s) on conflict (workflow_id) do update set updated_at=now()",
      pi, rid, J(v))
    log_step(pi, rid, topic, idem, "started")
    try:
        with tracer.start_as_current_span(f"l5.{topic}") as sp:
            sp.set_attribute("zg.layer", "L5"); sp.set_attribute("zg.run_id", rid); sp.set_attribute("bpmn.processInstanceId", pi)
            sp.set_attribute("zg.model_called", False)
            out = HANDLERS[topic](v, pi, idem)
        status = "compensated" if topic in COMPENSATION.values() else "completed"
        log_step(pi, rid, topic, idem, status, output=out, compensation={"handler": COMPENSATION.get(topic)} if topic in COMPENSATION else None)
        r = req("worker", "POST", f"/external-task/{t['id']}/complete", json={"workerId": WORKER_ID, "variables": tv(out)}, run_id=rid, caller=CALLER)
        if r.status_code >= 300:
            print("complete failed", r.status_code, r.text[:200], flush=True)
    except BpmnErr as e:
        log_step(pi, rid, topic, idem, "policy-blocked" if e.code == "POLICY_BLOCKED" else "failed", output={"errorCode": e.code, "message": e.msg, **e.data})
        q("update l5.saga set state=%s, result=%s, updated_at=now() where workflow_id=%s",
          "policy-blocked" if e.code == "POLICY_BLOCKED" else "compensating", J({"reason": e.msg, "errorCode": e.code}), pi)
        req("worker", "POST", f"/external-task/{t['id']}/bpmnError", run_id=rid, caller=CALLER,
            json={"workerId": WORKER_ID, "errorCode": e.code, "errorMessage": e.msg, "variables": tv({"failureReason": e.msg, **e.data})})
    except Exception as e:
        traceback.print_exc()
        log_step(pi, rid, topic, idem, "retrying", output={"error": str(e)[:300]})
        retries = t.get("retries")
        req("worker", "POST", f"/external-task/{t['id']}/failure", run_id=rid, caller=CALLER,
            json={"workerId": WORKER_ID, "errorMessage": str(e)[:200], "retries": (retries if retries is not None else 3) - 1, "retryTimeout": 1000})
    finally:
        RUN_ID.reset(tok)

def main():
    print(f"{WORKER_ID} polling Operaton topics {list(HANDLERS)} (lock {LOCK_MS} ms)", flush=True)
    while True:
        try:
            r = req("worker", "POST", "/external-task/fetchAndLock", record=False, timeout=40,
                    json={"workerId": WORKER_ID, "maxTasks": 1, "usePriority": True, "asyncResponseTimeout": 20000,
                          "topics": [{"topicName": n, "lockDuration": LOCK_MS, "variables": VARS} for n in HANDLERS]})
            if r.status_code != 200:
                print("fetchAndLock", r.status_code, r.text[:200], flush=True); time.sleep(2); continue
            for t in r.json():
                handle(t)
        except Exception as e:
            print("poll error", e, flush=True); time.sleep(2)

if __name__ == "__main__":
    sys.exit(main())
