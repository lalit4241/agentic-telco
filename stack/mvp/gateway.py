"""AgenticTelco MVP · gateway: serves the two-view UI (live mode) and the small read API it polls.
L1 web chat enters here; everything after that is the real layer services. Local only (127.0.0.1)."""
import os, subprocess, sys, uuid
from pathlib import Path
import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, Response
from stack.mvp.common import (ROOT, q, q1, J, Span, url, new_trace, traceparent, brightwell, copy_json, init_schema, OPERATON_URL, MODEL)
from stack.l5_orchestrator.engine import creds

app = FastAPI(title="AgenticTelco MVP gateway")
SF_UI = os.environ.get("MVP_SF_LIGHTNING", "https://techmahindra5.lightning.force.com")
BPMN = Path(__file__).parent / "bpmn" / "agentictelco-mvp-upgrade.bpmn"
WEB = ROOT / "web"
B = brightwell()
CASES = {
    "happy":   {"title": "Happy path", "contact": "sam", "scenario": {"overdue": False, "portFree": True}},
    "notauth": {"title": "Not authorised", "contact": "alex", "scenario": {"overdue": False, "portFree": True}},
    "overdue": {"title": "Overdue balance", "contact": "sam", "scenario": {"overdue": True, "portFree": True}},
    "delayed": {"title": "Order delayed", "contact": "sam", "scenario": {"overdue": False, "portFree": False}},
}
OPENING = ("We're taking on 15 more staff at the Martlesham office next month, 35 people in total, and moving everyone to cloud video calls. "
           "Our broadband already struggles. What do you suggest?")

@app.on_event("startup")
def _s():
    init_schema()

@app.get("/health")
def health():
    return {"ok": True, "service": "mvp-gateway"}

@app.get("/", response_class=HTMLResponse)
def index():
    p = WEB / "dist" / "mvp-live.html"
    if not p.exists():
        raise HTTPException(503, "Run: node web/build.js --live")
    return p.read_text()

@app.get("/api/copy")
def copy():
    return copy_json()

@app.get("/api/bpmn")
def bpmn():
    return Response(BPMN.read_text(), media_type="application/xml")

def asset_installed():
    from stack.zg_common import sf_session
    r = sf_session.request("GET", f"/services/data/v62.0/sobjects/Asset/{B['assetId']}?fields=Status")
    return r.json().get("Status") == "Installed"

@app.post("/api/demo/start")
async def start(request: Request):
    """Start one use case: set the legacy stand-in scenario, make sure the seed is in its starting state, open a conversation."""
    b = await request.json()
    case = CASES.get(b.get("case"))
    if not case:
        raise HTTPException(400, "unknown case")
    httpx.post(f"{url('standins')}/standin/reset", timeout=10)
    httpx.put(f"{url('standins')}/standin/scenario", json=case["scenario"], timeout=10)
    if not asset_installed():   # every case starts from Fibre 150 Installed
        subprocess.run([sys.executable, "seed/customers/seed_brightwell.py", "--reset"], cwd=ROOT, check=True, capture_output=True, timeout=600)
    who = B["contacts"][case["contact"]]
    cid, trace = "C-" + uuid.uuid4().hex[:10], new_trace()
    q("insert into mvp.conversation(id, trace_id, contact_id, case_name, state) values (%s,%s,%s,%s,%s)", cid, trace, who["contactId"], b["case"],
      J({"accountId": B["accountId"], "contactName": who["name"].split()[0], "contactFullName": who["name"], "contactRole": who["role"],
         "customerName": "Brightwell Design Ltd", "case": b["case"]}))
    return {"conversationId": cid, "traceId": trace, "case": b["case"], "title": case["title"], "contact": who, "opening": OPENING}

@app.post("/api/chat")
async def chat(request: Request):
    b = await request.json()
    c = q1("select trace_id from mvp.conversation where id=%s", b["conversationId"])
    if not c:
        raise HTTPException(404, "unknown conversation")
    with Span(c["trace_id"], "L1", "Web chat", "Customer message", runtime="ours (web chat)", api="HTTPS", method="POST", path="/api/chat",
              conversation_id=b["conversationId"], request={"message": b["message"]}) as sp:
        async with httpx.AsyncClient(timeout=300) as cl:
            r = await cl.post(f"{url('agent')}/chat", json=b, headers={"traceparent": traceparent(c["trace_id"], sp.span_id)})
        sp.status, sp.response = r.status_code, r.json()
    return r.json()

def sf_link(obj, rid):
    return f"{SF_UI}/lightning/r/{obj}/{rid}/view" if rid else None

@app.get("/api/state")
def state(conversationId: str, since: int = 0):
    c = q1("select id, trace_id, contact_id, case_name, started_at, state from mvp.conversation where id=%s", conversationId)
    if not c:
        raise HTTPException(404, "unknown conversation")
    st = c["state"] or {}
    msgs = q("select seq, at, role, content, meta from mvp.message where conversation_id=%s and role in ('user','assistant') order by seq", conversationId)
    spans = q("select seq, trace_id, span_id, parent_span_id, layer, component, step, runtime, api, method, path, status, start_ts, end_ts, "
              "duration_ms, attributes, request, response from mvp.audit where trace_id=%s and seq > %s order by seq", c["trace_id"], since)
    decisions = q("select mode, policy_version, input, result, at from mvp.decision where trace_id=%s order by id", c["trace_id"])
    out = {"conversation": {k: c[k] for k in ("id", "trace_id", "contact_id", "case_name", "started_at")}, "state": {k: v for k, v in st.items() if k != "agentSpan"},
           "messages": msgs, "spans": spans, "decisions": decisions, "model": MODEL,
           "xref": q("select system, external_id, source, verified from mvp.identity_xref where subject='brightwell' order by id"),
           "consent": q("select id, text, at from mvp.consent where conversation_id=%s", conversationId)}
    try:
        out["network"] = httpx.get(f"{url('standins')}/standin/network/4471", timeout=5).json()
    except Exception:
        out["network"] = None
    if st.get("intentId"):
        it = q1("select id, lifecycle_status, body from mvp.intent where id=%s", st["intentId"])
        out["intent"] = it
        out["reports"] = [r["body"] for r in q("select body from mvp.intent_report where intent_id=%s order by created_at", st["intentId"])]
        ext = st["orderExternalId"]
        out["milestones"] = q("select name, body, at from mvp.milestone where order_ext=%s order by id", ext)
        out["jeopardy"] = q("select body, at from mvp.jeopardy where order_ext=%s order by id", ext)
        pi = st.get("processInstanceId")
        acts = httpx.get(f"{OPERATON_URL}/history/activity-instance", params={"processInstanceId": pi, "sortBy": "startTime", "sortOrder": "asc"},
                         auth=creds("agent"), timeout=20).json()
        out["bpmn"] = [{"id": a["activityId"], "name": a.get("activityName"), "type": a["activityType"], "start": a["startTime"], "end": a.get("endTime")}
                       for a in acts] if isinstance(acts, list) else []
        links = {"order": None}
        for m in out["milestones"]:
            bd = m["body"] or {}
            if m["name"] == "OrderInProgress":
                links["order"] = sf_link("Order", bd.get("productOrderId"))
                links["orderNumber"] = bd.get("orderNumber")
            if m["name"] == "QuoteCreated":
                links["quote"] = sf_link("Quote", bd.get("quoteId"))
            if m["name"] == "AssetChanged":
                links["newAsset"] = sf_link("Asset", bd.get("new"))
                links["relationship"] = sf_link("AssetRelationship", bd.get("relationship"))
        links["oldAsset"] = sf_link("Asset", B["assetId"])
        links["account"] = sf_link("Account", B["accountId"])
        out["links"] = links
    return out
