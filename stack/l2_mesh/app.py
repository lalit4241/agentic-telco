"""L2 · Agent Mesh – care agent as a LangGraph graph. Exposes TMF921 Intent Management (not supported by Salesforce –
our layer). Agents reason and call tools over MCP, hand off over A2A, and may only *request* execution from L5."""
import asyncio, json, time, uuid
from typing import Any, TypedDict
from fastapi import FastAPI, HTTPException, Request
from langgraph.graph import StateGraph, END
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client
from stack.zg_common.config import url, PORTS
from stack.zg_common.db import q, q1, J
from stack.zg_common.http import acall
from stack.zg_common.telemetry import instrument_app, record_call, RUN_ID, setup
from stack.zg_common.runs import collect_run
from stack.l2_mesh import model_router
from stack.l5_orchestrator import engine
from stack.l5_orchestrator.state import process_state

SVC = "l2-care-agent"
app = FastAPI(title="AgenticTelco L2 agent mesh")
instrument_app(app, SVC)
tracer = setup(SVC)
MCP_URL = url("mcp_tools") + "/mcp"
INT = "/tmf-api/intentManagement/v4"

CARE_CARD = {"name": "zg-care-agent", "description": "Customer care agent: understands intents, assembles context, proposes offers, files tickets",
             "url": f"http://127.0.0.1:{PORTS['l2_mesh']}/a2a", "version": "1.0.0", "protocolVersion": "0.3.0",
             "capabilities": {"streaming": False}, "defaultInputModes": ["text/plain"], "defaultOutputModes": ["application/json"],
             "skills": [{"id": "broadband-upgrade", "name": "Agentic broadband upgrade", "tags": ["TMF921", "TMF620", "TMF679", "TMF622"]},
                        {"id": "fault-care", "name": "Fault care with network hand-off", "tags": ["TMF621", "A2A"]}]}

async def tool(st, name, **args):
    """Call an MCP tool; the hop is recorded in the L8 ledger (caller-side) and as an OTel span."""
    args = {"run_id": st["run_id"], **args}
    t0 = time.perf_counter()
    with tracer.start_as_current_span(f"mcp.tools/call {name}") as sp:
        sp.set_attribute("zg.layer", "L2"); sp.set_attribute("mcp.tool", name); sp.set_attribute("zg.run_id", st["run_id"])
        async with streamablehttp_client(MCP_URL) as (r, w, _):
            async with ClientSession(r, w) as s:
                await s.initialize()
                res = await s.call_tool(name, args)
    out = res.structuredContent
    if out is None:  # mcp 1.x: list results come back as one text item per element
        items = [json.loads(c.text) for c in res.content if getattr(c, "text", None)]
        out = items[0] if len(items) == 1 and not name.startswith(("tmf620_list", "tmf637_products", "l3_knowledge")) else items
    if isinstance(out, dict) and set(out) == {"result"}:
        out = out["result"]
    record_call(caller=SVC, callee="mcp-tools", method="MCP", path=f"/mcp/tools/{name}", status=200 if not res.isError else 500,
                req={k: v for k, v in args.items() if k != "context"}, resp=out, ms=round((time.perf_counter() - t0) * 1000, 1), run_id=st["run_id"])
    return out

def step(st, node, layer, thought, data=None):
    st.setdefault("steps", []).append({"node": node, "layer": layer, "thought": thought, "data": data, "at": time.time()})

class S(TypedDict, total=False):
    run_id: str; utterance: str; customer_id: str; intent: dict; route: dict; context: dict; offers: list
    offer: dict; qualification: dict; decision: dict; quote: dict; saga: dict; ticket: dict; handoff: dict
    outcome: str; steps: list; skip_policy: bool; knowledge: list; current: list

# ---------------- nodes
async def intake(st: S):
    intent, route = await asyncio.to_thread(model_router.extract, st["utterance"], st["run_id"], "l2-care-agent")
    st["intent"], st["route"] = intent, route
    step(st, "intake", "L2", f"Understood intent '{intent['intentType']}' via {route['route']}"
         + (f" ({route.get('why')})" if route.get("why") else f" ({route.get('model')} via {route.get('servedBy')})"), {"intent": intent, "modelRoute": route})
    return st

async def context(st: S):
    st["context"] = await tool(st, "l4_context", customer_id=st["customer_id"])
    c = st["context"]
    step(st, "context", "L4", f"Context for {c['customer']['name']}: credit {c['credit']['score']}, consent via {c['consent']['channel']}, "
         f"exchange {c['network']['exchange']} at {int(c['network']['utilisation'] * 100)}% utilisation", c)
    return st

async def offer(st: S):
    offers = await tool(st, "tmf620_list_offerings")
    st["current"] = await tool(st, "tmf637_products", customer_id=st["customer_id"])
    st["knowledge"] = await tool(st, "l3_knowledge", query="upgrade full fibre work from home " + st["utterance"])
    speed = lambda o: next(v["value"] for c in o["prodSpecCharValueUse"] if c["name"] == "downloadSpeedMbps" for v in c["productSpecCharacteristicValue"])
    price = lambda o: o["productOfferingPrice"][0]["price"]["taxIncludedAmount"]["value"]
    u = st["utterance"].lower()
    named = [o for o in offers if o["name"].lower() in u or str(speed(o)) in u or (int(speed(o)) >= 1000 and f"{int(speed(o)) / 1000:g}g" in u)]
    need = max(300, st["context"]["usage"]["peakMbps"] * 3)
    budget = st["intent"].get("budgetGBP")
    cands = named or sorted([o for o in offers if speed(o) >= need and (not budget or price(o) <= budget)], key=price)
    st["offers"] = offers
    st["offer"] = cands[0] if cands else offers[-1]
    step(st, "offer", "L2", f"Proposed {st['offer']['name']} (£{price(st['offer']):.0f}/mo) – " +
         ("customer asked for it by name" if named else f"cheapest offer ≥ {need} Mb/s for {st['context']['usage']['devices']} devices"),
         {"offer": st["offer"]["id"], "knowledge": [k["id"] for k in st["knowledge"]]})
    return st

async def qualify(st: S):
    st["qualification"] = await tool(st, "tmf679_qualify", customer_id=st["customer_id"], offering_id=st["offer"]["id"])
    qn = st["qualification"]
    how = (f"native TMF679 tried ({qn['x-nativeAttempt']['status']}), labelled our-layer rule: offer vs address technology"
           if qn.get("x-nativeAttempt") else "product configuration check in the SoR")
    step(st, "qualify", "L6", f"TMF679 says {qn['qualificationResult']} ({how})", qn)
    return st

async def policy(st: S):
    st["decision"] = await tool(st, "l4_decide", action="broadband-upgrade", context=st["context"], offering_id=st["offer"]["id"])
    d = st["decision"]
    step(st, "policy", "L4", ("Policy v%s ALLOWS the upgrade" % d["policyVersion"]) if d["allow"]
         else "Policy v%s BLOCKS the upgrade: %s" % (d["policyVersion"], ", ".join(d["reasons"])), d)
    return st

async def rogue(st: S):
    """Demo only: a misbehaving agent that skips the L4 check. L5 still asks OPA before every SoR write."""
    step(st, "skip-policy", "L2", "⚠ Simulated misbehaving agent: skipping the L4 policy check and going straight to execution")
    return st

async def quote(st: S):
    st["quote"] = await tool(st, "tmf648_quote", customer_id=st["customer_id"], offering_id=st["offer"]["id"])
    step(st, "quote", "L6", f"TMF648 quote {st['quote']['id']} {st['quote'].get('state', 'approved')}", {"quote": st["quote"]["id"]})
    return st

async def execute(st: S):
    """Agents may only START the L5 process and READ its state (Operaton authorizations enforce this)."""
    c = st["context"]
    cur = next((p for p in st.get("current", []) if p["status"] == "active"), None)
    step(st, "execute", "L5", "Starting the deterministic BPMN saga on Operaton (agent identity: start + read only)")
    variables = {"runId": st["run_id"], "customerId": st["customer_id"], "offeringId": st["offer"]["id"], "quoteId": st["quote"]["id"],
                 "exchange": c["network"]["exchange"], "currentProductId": cur["id"] if cur else None}
    r = await asyncio.to_thread(engine.req, "agent", "POST", f"/process-definition/key/{engine.PROCESS_KEY}/start",
                                json={"businessKey": st["run_id"], "variables": engine.vars_(variables)}, run_id=st["run_id"], caller=SVC)
    if r.status_code >= 300:
        st["saga"] = {"state": "start-rejected", "reason": r.text[:200]}
        return st
    pi = r.json()["id"]
    deadline = time.time() + 120
    while True:
        s_ = await asyncio.to_thread(process_state, pi)
        if s_["state"] != "running" or time.time() > deadline:
            break
        await asyncio.sleep(0.4)
    s_ = await asyncio.to_thread(process_state, pi, st["run_id"], True)  # final read recorded in the ledger
    st["saga"] = {k: v for k, v in s_.items() if k not in ("activities",)}
    step(st, "saga-result", "L5", f"BPMN process {pi[:8]}… ended at '{s_.get('endEvent')}' → {s_['state']}" + (f": {s_['reason']}" if s_.get("reason") else ""),
         {"processInstanceId": pi, "state": s_["state"], "endEvent": s_.get("endEvent"), "reason": s_.get("reason")})
    return st

async def ticket(st: S):
    st["ticket"] = await tool(st, "tmf621_open_ticket", customer_id=st["customer_id"], description=st["utterance"], severity="major")
    step(st, "ticket", "OSS", f"Opened TMF621 trouble ticket {st['ticket']['id']}", {"ticket": st["ticket"]["id"]})
    return st

async def handoff(st: S):
    card = (await acall(SVC, "GET", url("network_agent") + "/.well-known/agent-card.json", run_id=st["run_id"])).json()
    msg = {"jsonrpc": "2.0", "id": 1, "method": "message/send", "params": {"message": {"role": "agent", "messageId": uuid.uuid4().hex, "contextId": st["run_id"],
           "parts": [{"kind": "text", "text": "Customer reports slow broadband – please diagnose and fix"},
                     {"kind": "data", "data": {"ticketId": st["ticket"]["id"], "customerId": st["customer_id"], "exchange": st["context"]["network"]["exchange"]}}]}}}
    step(st, "handoff", "L2", f"A2A hand-off to '{card['name']}' (skill {card['skills'][0]['id']})", {"agentCard": card["name"]})
    r = await acall(SVC, "POST", card["url"], json=msg, run_id=st["run_id"], timeout=60)
    st["handoff"] = r.json()["result"]
    d = st["handoff"]["artifacts"][0]["parts"][0]["data"]
    step(st, "network-result", "L2", "Network agent: " + "; ".join(f"{s['step']}" for s in d["steps"]) + " – ticket resolved", d)
    return st

async def report(st: S):
    if st["intent"]["intentType"] == "fault-report":
        st["outcome"] = "resolved"
    elif st.get("qualification", {}).get("qualificationResult") == "unqualified":
        st["outcome"] = "not-qualified"
    elif st.get("decision") and not st["decision"]["allow"]:
        st["outcome"] = "blocked-by-policy"
    elif st.get("saga"):
        st["outcome"] = {"completed": "completed", "compensated": "compensated", "policy-blocked": "blocked-by-policy-in-L5"}.get(
            st["saga"].get("state"), st["saga"].get("state", "unknown"))
    else:
        st["outcome"] = "no-action"
    step(st, "report", "L1", f"Outcome: {st['outcome']}")
    return st

def build():
    g = StateGraph(S)
    for n, f in [("intake", intake), ("context", context), ("offer", offer), ("qualify", qualify), ("policy", policy), ("quote", quote),
                 ("execute", execute), ("rogue", rogue), ("ticket", ticket), ("handoff", handoff), ("report", report)]:
        g.add_node(n, f)
    g.set_entry_point("intake")
    g.add_edge("intake", "context")
    g.add_conditional_edges("context", lambda s: "ticket" if s["intent"]["intentType"] == "fault-report" else
                            ("offer" if s["intent"]["intentType"] == "broadband-upgrade" else "report"))
    g.add_edge("offer", "qualify")
    g.add_conditional_edges("qualify", lambda s: ("rogue" if s.get("skip_policy") else "policy") if s["qualification"]["qualificationResult"] == "qualified" else "report")
    g.add_edge("rogue", "quote")
    g.add_conditional_edges("policy", lambda s: "quote" if s["decision"]["allow"] else "report")
    g.add_edge("quote", "execute"); g.add_edge("execute", "report")
    g.add_edge("ticket", "handoff"); g.add_edge("handoff", "report")
    g.add_edge("report", END)
    return g.compile()

GRAPH = build()
GRAPH_MERMAID = GRAPH.get_graph().draw_mermaid()

@app.get("/health")
def health():
    return {"ok": True, "service": SVC}

@app.get("/.well-known/agent-card.json")
def card():
    return CARE_CARD

@app.get("/zg/mesh/v1/graph")
def graph():
    return {"mermaid": GRAPH_MERMAID}

@app.post(INT + "/intent", status_code=201)
async def create_intent(request: Request):
    b = await request.json()
    expr = b["expression"]["expressionValue"]
    rid = b.get("id") or "INT-" + uuid.uuid4().hex[:10]
    RUN_ID.set(rid)
    q("insert into l8.runs(run_id, scenario, title, customer_id, utterance) values(%s,%s,%s,%s,%s)",
      rid, b.get("scenario"), b.get("name"), expr["customerId"], expr["utterance"])
    record_call(caller=b.get("_caller", "l1-intent-ui"), callee=SVC, method="POST", path=INT + "/intent", status=201, req=b, resp={"id": rid}, run_id=rid)
    with tracer.start_as_current_span("tmf921.intent " + rid) as sp:
        sp.set_attribute("zg.run_id", rid)
        st = await GRAPH.ainvoke({"run_id": rid, "utterance": expr["utterance"], "customer_id": expr["customerId"], "steps": [],
                                   "skip_policy": bool(b.get("_simulateAgentSkipsPolicy"))})
    summary = {k: st.get(k) for k in ("intent", "outcome", "decision", "saga", "ticket", "handoff", "qualification")}
    summary["offer"] = st.get("offer", {}).get("name") if st.get("offer") else None
    summary["steps"] = st["steps"]
    q("update l8.runs set finished_at=now(), outcome=%s, summary=%s, model_routes=%s where run_id=%s", st["outcome"], J(summary), J([st["route"]]), rid)
    return {"id": rid, "href": f"{INT}/intent/{rid}", "@type": "Intent", "name": b.get("name"), "lifecycleStatus": "completed",
            "intentReport": {"outcome": st["outcome"], "steps": st["steps"]},
            "note": "TMF921 Intent Management is not supported by Salesforce – this is our layer"}

@app.get(INT + "/intent/{rid}")
def get_intent(rid: str):
    r = q1("select * from l8.runs where run_id=%s", rid)
    if not r:
        raise HTTPException(404)
    return {"id": rid, "@type": "Intent", "lifecycleStatus": "completed" if r["finished_at"] else "inProgress", "intentReport": r["summary"]}

@app.get("/zg/mesh/v1/runs/{rid}")
def run(rid: str):
    return collect_run(rid)
