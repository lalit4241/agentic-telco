"""Shared inference service – hosted in L7 runtime, used by L2 agent mesh.
Our extension of the Zero Gravity framework (not a ninth layer): OPA in L4 decides which models are allowed,
Langfuse/OTel in L8 meter usage. Agents never call model providers directly – only this OpenAI-compatible endpoint.

Pipeline per request: caller check → PII redaction → task-class routing → OPA allow-list → semantic cache (pgvector)
→ LiteLLM proxy → Ollama (local, UK) → fallbacks → deterministic stub (flagged) → metering (OTel + l8.inference + Langfuse)."""
import json, os, re, time, uuid
import httpx
from fastapi import FastAPI, HTTPException, Request
from stack.zg_common.config import OPA_URL
from stack.zg_common.db import q, q1, J
from stack.zg_common.embed import embed
from stack.zg_common.telemetry import instrument_app, record_call, setup, RUN_ID, current_trace_id

SVC = "inference-gateway"
app = FastAPI(title="AgenticTelco shared inference service (our extension of the Zero Gravity framework)")
instrument_app(app, SVC, record_inbound=False)
tracer = setup(SVC)
LITELLM = os.environ.get("ZG_LITELLM_URL", "http://127.0.0.1:4000")
CATALOG = json.load(open(os.path.join(os.path.dirname(__file__), "policy", "models.json")))["zg"]["modelcatalog"]

# Task-class routing table: ordered candidates + budgets. Small/local for classification & extraction, larger for reasoning.
ROUTES = {
    "classification": {"candidates": ["zg-local-small"], "maxTokens": 128, "latencyBudgetMs": 15000, "costBudgetGBP": 0.001},
    "extraction":     {"candidates": ["zg-local-small"], "maxTokens": 192, "latencyBudgetMs": 20000, "costBudgetGBP": 0.001},
    "reasoning":      {"candidates": ["us-frontier-saas", "zg-sovereign-large", "zg-local-small"], "maxTokens": 512, "latencyBudgetMs": 30000, "costBudgetGBP": 0.02},
    "summarisation":  {"candidates": ["zg-sovereign-large", "zg-local-small"], "maxTokens": 256, "latencyBudgetMs": 30000, "costBudgetGBP": 0.01},
}
CALLER_LAYER = {"l2": "L2", "l4": "L4", "l5": "L5", "l3": "L3", "l6": "L6", "l1": "L1"}
CACHE_MAX_DISTANCE = 0.02

# ---------------- PII redaction (before any prompt leaves the boundary)
_names = []
def known_names():
    global _names
    if not _names:
        try:
            _names = [r["name"] for r in q("select distinct name from sor.customer where name is not null")] or []
        except Exception:
            _names = []
        try:
            _names += [r["n"] for r in q("select name n from sor.party where name is not null")]
        except Exception:
            pass
        _names = sorted({n for n in _names if n and n.strip()}, key=len, reverse=True)
    return _names

PII = [("EMAIL", re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")),
       ("PHONE", re.compile(r"(?:\+44\s?7\d{3}|\b07\d{3})\s?\d{3}\s?\d{3}\b")),
       ("POSTCODE", re.compile(r"\b[A-Z]{1,2}\d[A-Z\d]?\s?\d[A-Z]{2}\b", re.I)),
       ("CARD", re.compile(r"\b(?:\d[ -]?){13,19}\b")),
       ("ACCOUNT", re.compile(r"\bC-\d{4}\b"))]

def redact(text):
    n = 0
    for name in known_names():
        for part in [name] + name.split():
            if len(part) > 2 and re.search(rf"\b{re.escape(part)}\b", text):
                text, k = re.subn(rf"\b{re.escape(part)}\b", "[NAME]", text); n += k
    for label, rx in PII:
        text, k = rx.subn(f"[{label}]", text); n += k
    return text, n

def opa_allow(model, data_class, task_class, layer, run_id):
    body = {"input": {"model": model, "dataClass": data_class, "taskClass": task_class, "callerLayer": layer}}
    t0 = time.perf_counter()
    r = httpx.post(OPA_URL + "/v1/data/zg/inference/decision", json=body, timeout=5)
    res = (r.json() or {}).get("result") or {"allow": False, "reasons": ["no OPA decision"]}
    record_call(caller=SVC, callee="opa", method="POST", path="/v1/data/zg/inference/decision", status=r.status_code, req=body, resp=res,
                ms=round((time.perf_counter() - t0) * 1000, 1), run_id=run_id)
    return res

def cache_scope(msgs):
    """Cache scope = exact hash of the instructions (every message except the last user turn) + task class + model.
    Only the last user turn is compared semantically, so a long shared prompt can never make two different questions look alike."""
    import hashlib
    head = json.dumps([[m.get("role"), m.get("content")] for m in msgs[:-1]])
    return hashlib.sha256(head.encode()).hexdigest()[:16], (msgs[-1].get("content") or "") if msgs else ""

def cache_get(task_class, model, msgs):
    scope, last = cache_scope(msgs)
    r = q1("select response, embedding <=> %s::vector as d from l3.semantic_cache where task_class=%s and model=%s and scope=%s order by d limit 1",
           embed(last), task_class, model, scope)
    return (r["response"], float(r["d"])) if r and r["d"] is not None and float(r["d"]) <= CACHE_MAX_DISTANCE else (None, None)

def cache_put(task_class, model, msgs, response):
    scope, last = cache_scope(msgs)
    q("insert into l3.semantic_cache(task_class, model, scope, prompt, embedding, response) values(%s,%s,%s,%s,%s::vector,%s)",
      task_class, model, scope, last, embed(last), J(response))

def litellm_call(model, messages, max_tokens, timeout_s, fmt):
    body = {"model": model, "messages": messages, "max_tokens": max_tokens, "temperature": 0, "seed": 7}
    if fmt:
        body["response_format"] = fmt
    r = httpx.post(LITELLM + "/v1/chat/completions", json=body, timeout=timeout_s,
                   headers={"Authorization": "Bearer " + os.environ.get("LITELLM_MASTER_KEY", "")})
    r.raise_for_status()
    return r.json()

def stub(messages):
    """Deterministic stub – used ONLY when no allowed model answers. Flagged everywhere as zg.stub=true."""
    return {"id": "stub-" + uuid.uuid4().hex[:8], "object": "chat.completion", "model": "deterministic-stub",
            "choices": [{"index": 0, "message": {"role": "assistant", "content": ""}, "finish_reason": "stub"}],
            "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}}

@app.get("/health")
def health():
    try:
        ok = httpx.get(LITELLM + "/health/liveliness", timeout=3).status_code == 200
    except Exception:
        ok = False
    return {"ok": True, "service": SVC, "litellm": ok, "placement": "hosted in L7 runtime, used by L2 agent mesh",
            "label": "our extension of the Zero Gravity framework"}

@app.get("/zg/inference/v1/routes")
def routes():
    return {"routes": ROUTES, "catalog": CATALOG, "placement": "hosted in L7 runtime, used by L2 agent mesh",
            "governance": {"allowList": "OPA in L4 (data.zg.inference)", "metering": "Langfuse + OTel in L8"}}

@app.get("/zg/inference/v1/usage")
def usage(run_id: str | None = None):
    return q("""select agent, task_class, routed_model, served_by, count(*) calls, sum(prompt_tokens) prompt_tokens,
                sum(completion_tokens) completion_tokens, sum(cost_gbp) cost_gbp, sum(case when cache='hit' then 1 else 0 end) cache_hits
                from l8.inference where (%s::text is null or run_id=%s) group by 1,2,3,4 order by 1""", run_id, run_id)

@app.post("/v1/chat/completions")
async def chat(request: Request):
    b = await request.json()
    agent = request.headers.get("x-zg-agent") or request.headers.get("x-zg-caller") or "unknown"
    caller = request.headers.get("x-zg-caller", agent)
    run_id = request.headers.get("x-zg-run-id") or RUN_ID.get()
    task_class = request.headers.get("x-zg-task-class", "reasoning")
    data_class = request.headers.get("x-zg-data-class", "customer")  # default to the strictest class
    layer = CALLER_LAYER.get(caller.split("-")[0], "L2")
    route = ROUTES.get(task_class)
    if not route:
        raise HTTPException(400, f"unknown task class {task_class}")
    t0 = time.perf_counter()
    with tracer.start_as_current_span("gen_ai.chat " + task_class) as sp:
        sp.set_attribute("zg.layer", "L7 runtime → L2 consumer"); sp.set_attribute("zg.agent", agent); sp.set_attribute("zg.run_id", run_id or "")
        sp.set_attribute("gen_ai.operation.name", "chat"); sp.set_attribute("zg.task_class", task_class); sp.set_attribute("zg.data_class", data_class)
        # 1. PII redaction
        msgs, red = [], 0
        for m in b.get("messages", []):
            c, n = redact(m.get("content") or "")
            msgs.append({**m, "content": c}); red += n
        prompt = "\n".join(m["content"] for m in msgs)
        # 2. OPA allow-list per candidate (L4 decides)
        decisions, chosen = [], None
        for cand in route["candidates"]:
            d = opa_allow(cand, data_class, task_class, layer, run_id)
            decisions.append({"model": cand, "allow": d["allow"], "reasons": sorted(d.get("reasons") or [])})
            if d["allow"] and chosen is None:
                chosen = cand
        fallbacks, served_by, cache_state, resp, stubbed = [], None, "miss", None, False
        if chosen is None:
            if layer in ("L4", "L5"):
                _meter(run_id, agent, task_class, data_class, None, "refused", "n/a", red, 0, 0, 0, t0, route, decisions, [], False)
                raise HTTPException(403, f"{layer} is deterministic and may never call a model (OPA)")
            stubbed, resp, served_by = True, stub(msgs), "deterministic-stub"
            fallbacks.append({"reason": "no allowed model for this request"})
        else:
            # 3. semantic cache
            hit, dist = cache_get(task_class, chosen, msgs)
            if hit:
                resp, cache_state, served_by = hit, "hit", "semantic-cache"
                sp.set_attribute("zg.cache_distance", dist)
            else:
                allowed = [x["model"] for x in decisions if x["allow"]]
                for cand in allowed:
                    try:
                        resp = litellm_call(cand, msgs, min(b.get("max_tokens") or route["maxTokens"], route["maxTokens"]),
                                            route["latencyBudgetMs"] / 1000, b.get("response_format"))
                        chosen, served_by = cand, f"litellm → {CATALOG[cand]['provider']}/{CATALOG[cand]['servedModel']}"
                        break
                    except Exception as e:
                        fallbacks.append({"model": cand, "error": type(e).__name__})
                if resp is None:
                    stubbed, resp, served_by = True, stub(msgs), "deterministic-stub"
                    fallbacks.append({"reason": "all allowed models failed or exceeded latency budget"})
                elif not stubbed:
                    cache_put(task_class, chosen, msgs, resp)
        u = resp.get("usage") or {}
        pt, ct = int(u.get("prompt_tokens") or 0), int(u.get("completion_tokens") or 0)
        cost = round((pt + ct) / 1000 * CATALOG.get(chosen or "", {}).get("costPer1kTokensGBP", 0.0), 6) if cache_state != "hit" else 0.0
        over = cost > route["costBudgetGBP"]
        for k, v in {"gen_ai.request.model": chosen or "none", "gen_ai.usage.input_tokens": pt, "gen_ai.usage.output_tokens": ct,
                     "zg.cost_gbp": cost, "zg.cache": cache_state, "zg.pii_redacted": red, "zg.stub": stubbed, "zg.served_by": served_by}.items():
            sp.set_attribute(k, v)
        route_rec = {"agent": agent, "taskClass": task_class, "dataClass": data_class, "routedModel": chosen, "servedBy": served_by,
                     "cache": cache_state, "piiRedacted": red, "opa": decisions, "fallbacks": fallbacks, "stub": stubbed,
                     "tokens": {"prompt": pt, "completion": ct}, "costGBP": cost, "overBudget": over,
                     "latencyMs": round((time.perf_counter() - t0) * 1000), "budget": {k: route[k] for k in ("latencyBudgetMs", "costBudgetGBP", "maxTokens")}}
        _meter(run_id, agent, task_class, data_class, chosen, served_by, cache_state, red, pt, ct, cost, t0, route, decisions, fallbacks, stubbed)
        record_call(caller=caller, callee=SVC, method="POST", path="/v1/chat/completions", status=200,
                    req={"taskClass": task_class, "dataClass": data_class, "redactedPrompt": prompt[:400]},
                    resp={"model": chosen, "servedBy": served_by, "content": (resp["choices"][0]["message"]["content"] or "")[:400]},
                    ms=route_rec["latencyMs"], run_id=run_id, extra={"route": route_rec})
    return {**resp, "zg_route": route_rec}

def _meter(run_id, agent, tc, dc, model, served, cache, red, pt, ct, cost, t0, route, decisions, fallbacks, stubbed):
    q("""insert into l8.inference(run_id, agent, task_class, data_class, routed_model, served_by, route, cache, pii_redacted, prompt_tokens,
         completion_tokens, cost_gbp, latency_ms, budget, opa, fallbacks, stub, trace_id) values(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
      run_id, agent, tc, dc, model, served, tc, cache, red, pt, ct, cost, round((time.perf_counter() - t0) * 1000, 1),
      J({k: route[k] for k in ("latencyBudgetMs", "costBudgetGBP", "maxTokens")}), J(decisions), J(fallbacks), stubbed, current_trace_id())
