"""AgenticTelco MVP · L1 intent service (TMF921 v5-shaped, not conformance-tested; simplified expression).

The agent PROPOSES an Intent. This service validates it (JSON Schema + the same OPA policy for the authorised-contact check),
records it in L3 Postgres (its system of record; never in Salesforce) and hands the upgrade proposal to the L5 workflow,
starting it with the order external ID as business key. L5 posts IntentReports back (StateDegrades = at risk, StateComplies = fulfilled)."""
import json, threading, uuid
from datetime import datetime, timezone
from pathlib import Path
import httpx, jsonschema
from fastapi import FastAPI, HTTPException, Request
from stack.mvp.common import q, q1, J, Span, url, traceparent, parse_traceparent, init_schema, OPERATON_URL
from stack.l5_orchestrator.engine import creds

app = FastAPI(title="AgenticTelco MVP L1 intent service (TMF921-shaped)")
BASE = "/tmf-api/intentManagement/v5"
SCHEMA = json.loads((Path(__file__).parent / "intent.schema.json").read_text())
PROCESS_KEY = "agentictelcoMvpUpgrade"

def now():
    return datetime.now(timezone.utc).isoformat()

@app.on_event("startup")
def _start():
    init_schema()

@app.get("/health")
def health():
    return {"ok": True, "service": "mvp-intent", "api": "TMF921 v5-shaped"}

def ctx(request):
    return parse_traceparent(request.headers.get("traceparent"))

@app.post(BASE + "/intent", status_code=201)
async def create_intent(request: Request):
    body = await request.json()
    trace, parent = ctx(request)
    with Span(trace, "L1", "Intent service", "Validate and record the Intent", runtime="ours (Python, FastAPI)", api="TMF921", method="POST",
              path=BASE + "/intent", parent=parent, request=body) as sp:
        try:
            jsonschema.validate(body, SCHEMA)
        except jsonschema.ValidationError as e:
            sp.status = 400
            raise HTTPException(400, {"code": "INVALID_INTENT", "reason": e.message})
        parties = {p["role"]: p["id"] for p in body["relatedParty"]}
        r = httpx.post(f"{url('context')}/policy/authorised-contact", json={"contactId": parties["requester"], "accountId": parties["customer"]},
                       headers={"traceparent": traceparent(trace, sp.span_id)}, timeout=60).json()
        if not r["authorisedContact"]:
            sp.status = 403
            sp.attrs["rejected"] = "not_authorised"
            raise HTTPException(403, {"code": "NOT_AUTHORISED", "reason": "Requester is not an authorised contact (policy agentictelco.upgrade)"})
        prop = body["x-proposal"]
        consent = q1("select id from mvp.consent where id=%s and conversation_id=%s and contact_id=%s", prop["consentId"], prop["conversationId"], parties["requester"])
        if not consent:
            sp.status = 409
            raise HTTPException(409, {"code": "NO_CONSENT", "reason": "No recorded consent for this conversation"})
        iid = "INT-" + uuid.uuid4().hex[:8].upper()
        order_ext = "MVP-" + iid[4:]
        intent = {**body, "id": iid, "href": f"{BASE}/intent/{iid}", "lifecycleStatus": "acknowledged", "creationDate": now(),
                  "lastUpdate": now(), "version": "1", "x-orderExternalId": order_ext, "x-traceId": trace}
        q("insert into mvp.intent(id, conversation_id, trace_id, lifecycle_status, body) values (%s,%s,%s,%s,%s)",
          iid, prop["conversationId"], trace, "acknowledged", J(intent))
        sp.status, sp.response = 201, {"id": iid, "lifecycleStatus": "acknowledged", "businessKey": order_ext}
        # hand the proposal to the workflow (start-only identity; it cannot complete or skip a step)
        with Span(trace, "L5", "Operaton", "Start the upgrade process", runtime="Operaton BPMN (start-only identity)", api="Operaton REST",
                  method="POST", path=f"/process-definition/key/{PROCESS_KEY}/start", parent=sp.span_id) as s2:
            variables = {"intentId": iid, "orderExternalId": order_ext, "traceId": trace, "conversationId": prop["conversationId"],
                         "contactId": parties["requester"], "accountId": parties["customer"], "toOffering": prop["recommendedOffering"],
                         "parentSpan": s2.span_id}
            rr = httpx.post(f"{OPERATON_URL}/process-definition/key/{PROCESS_KEY}/start", auth=creds("agent"), timeout=30,
                            json={"businessKey": order_ext, "variables": {k: {"value": v, "type": "String"} for k, v in variables.items()}})
            s2.status, s2.response = rr.status_code, rr.json()
            if rr.status_code != 200:
                raise HTTPException(502, f"workflow start failed: {rr.text[:200]}")
        intent["x-workflow"] = {"processInstanceId": rr.json()["id"], "businessKey": order_ext}
        q("update mvp.intent set body=%s where id=%s", J(intent), iid)
        return intent

@app.get(BASE + "/intent/{iid}")
def get_intent(iid: str):
    r = q1("select body, lifecycle_status from mvp.intent where id=%s", iid)
    if not r:
        raise HTTPException(404, "intent not found")
    return {**r["body"], "lifecycleStatus": r["lifecycle_status"]}

@app.get(BASE + "/intent/{iid}/intentReport")
def list_reports(iid: str):
    return [r["body"] for r in q("select body from mvp.intent_report where intent_id=%s order by created_at", iid)]

LIFECYCLE = {"icm:StateDegrades": "atRisk", "icm:StateComplies": "fulfilled", "icm:StateInProgress": "inProgress"}

@app.post(BASE + "/intent/{iid}/intentReport", status_code=201)
async def post_report(iid: str, request: Request):
    """Posted by the L5 workflow only. Records the report, moves the Intent lifecycle, and tells the agent (proactive update)."""
    b = await request.json()
    trace, parent = ctx(request)
    it = q1("select conversation_id from mvp.intent where id=%s", iid)
    if not it:
        raise HTTPException(404, "intent not found")
    rid = "IR-" + uuid.uuid4().hex[:8].upper()
    rep = {"@type": "IntentReport", "id": rid, "href": f"{BASE}/intent/{iid}/intentReport/{rid}", "creationDate": now(),
           "intent": {"id": iid}, "expression": {"@type": "JsonLdExpression", "expressionValue": {"icm:reportState": b["state"], **(b.get("detail") or {})}},
           "name": b.get("name", b["state"])}
    with Span(trace, "L1", "Intent service", f"IntentReport {b['state'].split(':')[-1]}", runtime="ours (Python, FastAPI)", api="TMF921",
              method="POST", path=f"{BASE}/intent/{iid}/intentReport", parent=parent, request=b) as sp:
        q("insert into mvp.intent_report(id, intent_id, state, body) values (%s,%s,%s,%s)", rid, iid, b["state"], J(rep))
        q("update mvp.intent set lifecycle_status=%s, updated_at=now() where id=%s", LIFECYCLE.get(b["state"], "inProgress"), iid)
        sp.status, sp.response = 201, rep
    def notify():   # proactive message to the customer: the agent phrases it from the report + order status
        try:
            httpx.post(f"{url('agent')}/notify", json={"conversationId": it["conversation_id"], "intentId": iid, "report": rep},
                       headers={"traceparent": traceparent(trace, sp.span_id)}, timeout=180)
        except Exception as e:
            print("agent notify failed:", e, flush=True)
    threading.Thread(target=notify, daemon=True).start()
    return rep
