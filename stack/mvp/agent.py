"""AgenticTelco MVP · L2 agent: a LangGraph state graph (model ⇄ tools) using a small local model through Ollama (thinking off)
and our MCP server's three tools. The agent proposes; it holds no business rules and has no write tool.

The conversation's contact and account come from the signed-in session, not from the model: the agent injects conversationId
into every tool call, so the model cannot look up or order for anyone else."""
from datetime import date
import json, re, time
from typing import TypedDict
import httpx
from fastapi import FastAPI, HTTPException, Request
from langgraph.graph import StateGraph, END
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client
from stack.mvp.common import q, q1, J, Span, url, OLLAMA_URL, MODEL, parse_traceparent, copy_json, init_schema

app = FastAPI(title="AgenticTelco MVP L2 agent")
MCP_URL = f"{url('mcp')}/mcp"
YES = re.compile(r"^\s*(yes|yeah|yep|ok|okay|sure|go ahead|please do|agreed?|do it|sounds good|let's do it)\b", re.I)

def glossary_lines():
    g = copy_json().get("glossary", [])
    keep = {"Intent", "Authorised contact", "Overdue balance", "Available at site", "Upgrade-only mid-contract", "Policy", "Workflow", "Jeopardy"}
    return "\n".join(f"- {x['term']}: {x['definition']}" for x in g if x["term"] in keep)

SYSTEM = """You are the AgenticTelco business assistant in the business customer portal. You talk to {name}, a contact at {customer}.
Be brief, warm and plain-spoken (UK English, 2 to 4 short sentences, no lists, no markdown headings).
How you work:
1. Before recommending anything, call get_context, passing staffOnVideoCalls = the total number of people the customer mentioned.
2. Only recommend from allowedUpgrades. Recommend sizing.bestFit (bestFitName). Say the name, speed and monthly price (charged from the day it goes live), say their
   contract end date stays the same, quoting contractEndDate exactly, then ask if they want you to go ahead.
3. If allowedUpgrades is empty, explain the blockedBecause reasons kindly. If whoCanOrder is given, say that person can order.
   If paymentLink is given, share it. Never offer a product the policy did not allow and never promise anything you cannot check.
4. When the customer agrees, call request_upgrade with the offeringId and their need in plain words (not a product name).
   Then confirm the order reference and say you will tell them if anything changes.
5. For questions about progress, call order_status.
You never change any system yourself: the workflow does that after a final policy check.
Terms you may need to explain:
{glossary}"""

MODEL_TOOLS = [
    {"type": "function", "function": {"name": "get_context", "description": "Facts about this customer and the upgrades the policy allows.",
                                      "parameters": {"type": "object", "properties": {"staffOnVideoCalls": {"type": "integer",
                                          "description": "total people who will be on video calls"}}}}},
    {"type": "function", "function": {"name": "request_upgrade", "description": "Request an upgrade the customer agreed to.",
                                      "parameters": {"type": "object", "required": ["offeringId", "outcome"], "properties": {
                                          "offeringId": {"type": "string", "description": "offeringId from allowedUpgrades"},
                                          "outcome": {"type": "string", "description": "the customer's need in plain words"}}}}},
    {"type": "function", "function": {"name": "order_status", "description": "Progress of the customer's upgrade (read-only).",
                                      "parameters": {"type": "object", "properties": {}}}},
]

class S(TypedDict):
    cid: str
    trace: str
    span: str
    messages: list
    steps: int
    fallback: bool

async def call_tool(cid, name, args):
    async with streamablehttp_client(MCP_URL) as (r, w, _):
        async with ClientSession(r, w) as s:
            await s.initialize()
            res = await s.call_tool(name, {"conversationId": cid, **args})
            return res.content[0].text if res.content else "{}"

def ollama(trace, parent, cid, messages, tools=True, step="Model call"):
    body = {"model": MODEL, "messages": messages, "stream": False, "think": False, "keep_alive": "60m",
            "options": {"temperature": 0, "num_ctx": 6144, "num_predict": 220}}
    if tools:
        body["tools"] = MODEL_TOOLS
    with Span(trace, "L2", "Agent (LangGraph)", step, runtime=f"Ollama, {MODEL} (local, thinking off)", api="Ollama", method="POST",
              path="/api/chat", parent=parent, conversation_id=cid) as sp:
        r = httpx.post(f"{OLLAMA_URL}/api/chat", json=body, timeout=180)
        r.raise_for_status()
        d = r.json()
        msg = d["message"]
        sp.status = 200
        sp.attrs.update(model=MODEL, promptTokens=d.get("prompt_eval_count"), outputTokens=d.get("eval_count"),
                        toolCalls=[t["function"]["name"] for t in msg.get("tool_calls") or []])
        sp.response = {"content": msg.get("content"), "tool_calls": msg.get("tool_calls")}
    return msg

async def model_node(st: S):
    try:
        msg = ollama(st["trace"], st["span"], st["cid"], st["messages"])
    except Exception as e:
        print("model failed, scripted fallback:", e, flush=True)
        return {"fallback": True, "steps": st["steps"] + 1}
    return {"messages": st["messages"] + [msg], "steps": st["steps"] + 1}

async def tools_node(st: S):
    msgs = list(st["messages"])
    for tc in msgs[-1].get("tool_calls") or []:
        f = tc["function"]
        args = f.get("arguments") or {}
        if isinstance(args, str):
            args = json.loads(args or "{}")
        args.pop("conversationId", None)
        out = await call_tool(st["cid"], f["name"], args)
        msgs.append({"role": "tool", "tool_name": f["name"], "content": out})
    return {"messages": msgs}

def route(st: S):
    if st.get("fallback"):
        return END
    last = st["messages"][-1]
    return "tools" if last.get("tool_calls") and st["steps"] < 5 else END

g = StateGraph(S)
g.add_node("model", model_node)
g.add_node("tools", tools_node)
g.set_entry_point("model")
g.add_conditional_edges("model", route, {"tools": "tools", END: END})
g.add_edge("tools", "model")
GRAPH = g.compile()

# ------------------------------------------------------------------- scripted fallback (used only if the local model fails)
def staff_mentioned(cid, text):
    said = " ".join([r["content"] for r in q("select content from mvp.message where conversation_id=%s and role='user'", cid)] + [text])
    nums = [int(n) for n in re.findall(r"(\d+)\s+(?:people|staff|users)", said)]
    return max(nums) if nums else 0

async def fallback(cid, text, consent):
    staff = staff_mentioned(cid, text)
    if consent:
        ctx = json.loads(await call_tool(cid, "get_context", {"staffOnVideoCalls": staff}))
        best_id = (ctx.get("sizing") or {}).get("bestFit") or ctx["allowedUpgrades"][-1]["offeringId"]
        best = {"offeringId": best_id}
        r = json.loads(await call_tool(cid, "request_upgrade", {"offeringId": best["offeringId"], "outcome": "support more staff on cloud video"}))
        return f"Done. Your upgrade is requested, reference {r.get('orderReference')}. I'll tell you if anything changes."
    ctx = json.loads(await call_tool(cid, "get_context", {"staffOnVideoCalls": staff}))
    if not ctx["allowedUpgrades"]:
        return " ".join(ctx["blockedBecause"]) + (f" {ctx['whoCanOrder']} can order for the business." if ctx.get("whoCanOrder") else "") + \
            (f" You can pay here: {ctx['paymentLink']}" if ctx.get("paymentLink") else "")
    pick = (ctx.get("sizing") or {}).get("bestFit")
    o = next((u for u in ctx["allowedUpgrades"] if u["offeringId"] == pick), ctx["allowedUpgrades"][-1])
    return f"I recommend {o['name']} ({o['downloadSpeedMbps']} Mbps) at £{o['monthlyPriceGBP']} a month; your contract end date stays the same. Shall I go ahead?"

# ------------------------------------------------------------------------------------------------------------- endpoints
@app.on_event("startup")
def _s():
    init_schema()

@app.get("/health")
def health():
    return {"ok": True, "service": "mvp-agent", "model": MODEL, "tools": [t["function"]["name"] for t in MODEL_TOOLS]}

def history(cid):
    rows = q("select role, content, meta from mvp.message where conversation_id=%s order by seq", cid)
    out = []
    for r in rows:
        if r["role"] in ("user", "assistant"):
            out.append({"role": r["role"], "content": r["content"]})
        elif r["role"] == "agent-internal":
            out.append(r["meta"])
    return out

@app.post("/chat")
async def chat(request: Request):
    b = await request.json()
    cid, text = b["conversationId"], b["message"].strip()
    c = q1("select trace_id, contact_id, state from mvp.conversation where id=%s", cid)
    if not c:
        raise HTTPException(404, "unknown conversation")
    trace, parent = parse_traceparent(request.headers.get("traceparent"))
    trace = trace or c["trace_id"]
    st = c["state"] or {}
    with Span(trace, "L2", "Agent (LangGraph)", "Agent turn", runtime="ours (LangGraph + MCP client)", api="MCP", method="TURN",
              path="/chat", parent=parent, conversation_id=cid, request={"message": text}) as sp:
        q("update mvp.conversation set state = state || %s where id=%s", J({"agentSpan": sp.span_id}), cid)
        consent = bool(YES.match(text)) and st.get("recommended") and not st.get("intentId")
        if consent:   # recorded verbatim, with time; request_upgrade refuses without it
            q("insert into mvp.consent(conversation_id, contact_id, text) values (%s,%s,%s)", cid, c["contact_id"], text)
            sp.attrs["consentRecorded"] = True
        m = re.search(r"(\d+)\s+more\s+staff", text)
        if m:
            q("update mvp.conversation set state = state || %s where id=%s", J({"extraStaff": int(m.group(1))}), cid)
        prior = history(cid)
        q("insert into mvp.message(conversation_id, role, content) values (%s,'user',%s)", cid, text)
        pack = (st.get("contextPack") or {})
        sysmsg = SYSTEM.format(name=st.get("contactName", "the customer"), customer=st.get("customerName", "the business"), glossary=glossary_lines())
        msgs = [{"role": "system", "content": sysmsg}] + prior + [{"role": "user", "content": text}]
        res = await GRAPH.ainvoke({"cid": cid, "trace": trace, "span": sp.span_id, "messages": msgs, "steps": 0, "fallback": False})
        if res.get("fallback"):
            reply = await fallback(cid, text, consent)
            sp.attrs["scriptedFallback"] = True
        else:
            reply = (res["messages"][-1].get("content") or "").strip()
            for m in res["messages"][len(msgs):-1]:   # keep tool exchanges so later turns remember the facts
                q("insert into mvp.message(conversation_id, role, content, meta) values (%s,'agent-internal','',%s)", cid,
                  J({k: v for k, v in m.items() if k in ("role", "content", "tool_calls", "tool_name")}))
        used = [m.get("tool_name") for m in res.get("messages", []) if m.get("role") == "tool"]
        q("insert into mvp.message(conversation_id, role, content, meta) values (%s,'assistant',%s,%s)", cid, reply, J({"tools": used}))
        if "get_context" in used and not consent:
            q("update mvp.conversation set state = state || %s where id=%s", J({"recommended": True}), cid)
        sp.status, sp.response = 200, {"reply": reply, "tools": used}
    return {"reply": reply, "tools": used, "consentRecorded": bool(consent)}

@app.post("/notify")
async def notify(request: Request):
    """Proactive message after an IntentReport from the workflow (the customer hears about a delay before they ask)."""
    b = await request.json()
    cid, rep = b["conversationId"], b["report"]
    c = q1("select trace_id, state from mvp.conversation where id=%s", cid)
    trace, parent = parse_traceparent(request.headers.get("traceparent"))
    ev = rep["expression"]["expressionValue"]
    state = ev.get("icm:reportState")
    name = (c["state"] or {}).get("contactName", "there")
    with Span(trace or c["trace_id"], "L2", "Agent (LangGraph)", "Proactive update", runtime="ours (LangGraph)", api="TMF921 Intent", method="NOTIFY",
              path="/notify", parent=parent, conversation_id=cid, request=rep) as sp:
        facts = {k: v for k, v in ev.items() if k != "icm:reportState" and not k.lower().endswith("id")}
        for k in ("liveDate", "revisedCompletionDate", "completionDate"):   # pre-format business dates so the model copies them, not an example
            if facts.get(k):
                try:
                    d = date.fromisoformat(str(facts[k])[:10]); facts[k] = f"{d.day} {d.strftime('%B %Y')}"
                except ValueError:
                    pass
        prompt = [{"role": "system", "content": f"You are the AgenticTelco business assistant. Write one short, warm message (2 sentences, UK English, "
                   f"no markdown) to {name} about this update to their broadband upgrade. Use the facts exactly and copy any date exactly as written in the facts; never mention record IDs."},
                  {"role": "user", "content": ("Status: at risk / delayed. " if state == "icm:StateDegrades" else "Status: done, the upgrade is live. ")
                   + json.dumps(facts)}]
        try:
            reply = (ollama(trace or c["trace_id"], sp.span_id, cid, prompt, tools=False, step="Model call (proactive)").get("content") or "").strip()
        except Exception:
            reply = None
        if not reply:
            reply = (f"Quick update, {name}: the network team needs two more days for a free port, so the new date is {facts.get('revisedCompletionDate')}. "
                     "Nothing else changes.") if state == "icm:StateDegrades" else f"Good news, {name}: {facts.get('product')} is now live from {facts.get('liveDate')}."
        q("insert into mvp.message(conversation_id, role, content, meta) values (%s,'assistant',%s,%s)", cid, reply,
          J({"proactive": True, "reportState": state}))
        sp.status, sp.response = 200, {"reply": reply}
    return {"reply": reply}
