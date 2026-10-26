"""L4 · Enterprise Context & Policy (our layer).
Assembles cross-domain context (SoR records via TMF629/632 + L3 data products) and asks OPA for a decision.
Policy is versioned here and can be changed live – with zero calls to Salesforce."""
import time
from fastapi import FastAPI, HTTPException, Request
from stack.zg_common.config import OPA_URL, SOR_BASE, url
from stack.zg_common.db import q, q1, J
from stack.zg_common.http import call
from stack.zg_common.telemetry import instrument_app, record_call, RUN_ID

SVC = "l4-context"
app = FastAPI(title="AgenticTelco L4 context & policy")
instrument_app(app, SVC)
B = "/zg/context/v1"
L3 = url("l3_data") + "/zg/data/v1"

def opa(method, path, body=None):
    t0 = time.perf_counter()
    r = call(SVC, method, OPA_URL + path, json=body)
    out = r.json() if r.content else None
    record_call(caller=SVC, callee="opa", method=method, path=path, status=r.status_code, req=body, resp=out,
                ms=round((time.perf_counter() - t0) * 1000, 1))
    return out

def current():
    r = q1("select * from l4.policy_version order by version desc limit 1")
    return r

@app.on_event("startup")
def boot():
    if not current():
        import json, pathlib
        d = json.loads((pathlib.Path(__file__).parent / "policy" / "data.json").read_text())["zg"]["policy"]
        q("insert into l4.policy_version(version,data,author,reason) values(1,%s,'seed','Initial operator policy')", J(d))
    try:
        call(SVC, "PUT", OPA_URL + "/v1/data/zg/policy", json=current()["data"])
    except Exception as e:
        print("OPA not reachable yet", e)

@app.get("/health")
def health():
    return {"ok": True, "service": SVC, "policyVersion": current()["version"]}

@app.post(B + "/context")
async def context(request: Request):
    b = await request.json()
    cid = b["customerId"]
    cust = call(SVC, "GET", f"{SOR_BASE}/tmf-api/customerManagement/v4/customer/{cid}").json()
    party = call(SVC, "GET", f"{SOR_BASE}/tmf-api/partyManagement/v4/individual/{cust['engagedParty']['id']}").json()
    addr = cust["contactMedium"][0]["characteristic"]
    consent = next(c["value"] for c in party["partyCharacteristic"] if c["name"] == "marketingConsent")
    credit = call(SVC, "GET", f"{L3}/creditProfile/{cid}").json()
    usage = call(SVC, "GET", f"{L3}/usage/{cid}").json()
    net = call(SVC, "GET", f"{L3}/networkCapacity/{addr['exchange']}").json()
    return {"customer": {"id": cid, "name": cust["name"], "address": addr}, "consent": consent,
            "credit": {"score": credit["score"], "source": credit["dataProduct"]}, "usage": usage,
            "network": {"exchange": net["exchange"], "utilisation": net["utilisation"], "source": net["dataProduct"]},
            "assembledBy": "L4 context service (our layer)"}

@app.post(B + "/decision")
async def decision(request: Request):
    b = await request.json()
    pol = current()
    out = opa("POST", "/v1/data/zg/upgrade/decision", {"input": b})
    res = out.get("result") if out else None
    if res is None:
        raise HTTPException(503, "OPA returned no decision")
    res["reasons"] = sorted(res.get("reasons") or [])
    res["engine"] = "OPA/Rego"
    res["policyData"] = pol["data"]
    q("insert into l4.decision(run_id, policy_version, input, result) values(%s,%s,%s,%s)", RUN_ID.get(), pol["version"], J(b), J(res))
    return res

@app.get(B + "/policy")
def get_policy():
    p = current()
    return {"version": p["version"], "data": p["data"], "author": p["author"], "reason": p["reason"], "changedAt": str(p["changed_at"])}

@app.get(B + "/policy/history")
def history():
    return [{"version": r["version"], "data": r["data"], "author": r["author"], "reason": r["reason"], "changedAt": str(r["changed_at"]),
             "salesforceCallsDuringChange": r["salesforce_calls_during_change"]} for r in q("select * from l4.policy_version order by version")]

@app.put(B + "/policy")
async def put_policy(request: Request):
    b = await request.json()
    before = q1("select coalesce(max(seq),0) m from l8.api_calls")["m"]
    p = current()
    allowed = {"creditMin", "consentRule", "networkMaxUtilisation", "aiGuardrail"}
    bad = set(b.get("changes", {})) - allowed
    if bad:
        raise HTTPException(400, f"unknown policy keys {bad}")
    data = {**p["data"], **b.get("changes", {}), "version": p["version"] + 1}
    opa("PUT", "/v1/data/zg/policy", data)
    sf = q1("select count(*) n from l8.api_calls where seq > %s and owner='salesforce'", before)["n"]
    q("insert into l4.policy_version(version,data,author,reason,salesforce_calls_during_change) values(%s,%s,%s,%s,%s)",
      data["version"], J(data), b.get("author", "operator"), b.get("reason", ""), sf)
    return {"version": data["version"], "data": data, "salesforceCallsDuringChange": sf,
            "note": "Policy changed in L4/OPA only – no Salesforce metadata, Flow or Apex was touched."}

@app.post(B + "/gate")
async def gate(request: Request):
    """Pre-write gate called by every L5 BPMN service task that writes to the SoR.
    Context is re-assembled fresh from the SoR + L3 (the agent's earlier view is not trusted) and OPA decides.
    Deterministic: no model is ever consulted here."""
    b = await request.json()
    ctx = await context_for(b["customerId"])
    inp = {"action": b.get("action", "sor-write"), "offeringId": b.get("offeringId"), "context": ctx, "decidedByModel": False,
           "step": b.get("step"), "processInstanceId": b.get("processInstanceId")}
    pol = current()
    out = opa("POST", "/v1/data/zg/upgrade/decision", {"input": inp})
    res = (out or {}).get("result")
    if res is None:
        raise HTTPException(503, "OPA returned no decision")
    res["reasons"] = sorted(res.get("reasons") or [])
    res.update(engine="OPA/Rego", gate=b.get("step"), modelConsulted=False)
    q("insert into l4.decision(run_id, policy_version, input, result) values(%s,%s,%s,%s)", RUN_ID.get(), pol["version"], J(inp), J(res))
    return res

async def context_for(cid):
    class _R:  # reuse the /context assembly without an HTTP hop
        async def json(self):
            return {"customerId": cid}
    return await context(_R())
