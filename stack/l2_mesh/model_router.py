"""Model routing for L2. Language understanding only – never decisions.
Route 1: the shared Inference Gateway (LiteLLM → local Ollama, OPA allow-list, PII redaction). Route 2: deterministic parser fallback. Every route is recorded."""
import json, re, time
import httpx
from stack.zg_common.config import INFERENCE_URL

SCHEMA_KEYS = {"intentType", "wantsFasterSpeed", "mentionsFault", "budgetGBP", "reason"}
PROMPT = ("You classify a telecom customer's message. Reply with JSON only, keys: intentType, wantsFasterSpeed, mentionsFault, budgetGBP, reason.\n"
          "intentType rules: 'broadband-upgrade' if the customer wants a faster plan or an upgrade; 'fault-report' if the service is broken, "
          "dropping or has an outage and they do NOT ask for an upgrade; otherwise 'other'.\n"
          "wantsFasterSpeed and mentionsFault are true/false. budgetGBP is a number or null. reason is 2-4 words.\n"
          "Example: 'my internet keeps cutting out' -> {\"intentType\":\"fault-report\",\"wantsFasterSpeed\":false,\"mentionsFault\":true,\"budgetGBP\":null,\"reason\":\"connection drops\"}\n"
          "Example: 'can I get gigabit, max £45' -> {\"intentType\":\"broadband-upgrade\",\"wantsFasterSpeed\":true,\"mentionsFault\":false,\"budgetGBP\":45,\"reason\":\"wants gigabit\"}\n"
          "Customer message: ")

def deterministic(text):
    t = text.lower()
    fault = bool(re.search(r"\b(slow|drop|dropping|outage|down|not working|keeps cutting|fault|buffer)", t))
    faster = bool(re.search(r"\b(faster|upgrade|gigabit|full fibre|more speed|900|1\.6|quicker)", t))
    m = re.search(r"£\s?(\d+)", t)
    it = "fault-report" if fault and not faster else ("broadband-upgrade" if faster else "other")
    reason = "work from home" if "work" in t else ("gaming" if "gam" in t else ("streaming" if "stream" in t else "general"))
    return {"intentType": it, "wantsFasterSpeed": faster, "mentionsFault": fault, "budgetGBP": float(m.group(1)) if m else None, "reason": reason}

def valid(d):
    return isinstance(d, dict) and SCHEMA_KEYS <= set(d) and d["intentType"] in ("broadband-upgrade", "fault-report", "other") \
        and isinstance(d["wantsFasterSpeed"], bool) and isinstance(d["mentionsFault"], bool)

def extract(text, run_id=None, agent="l2-care-agent"):
    """Agents never call model providers directly: every call goes through the shared Inference Gateway
    (hosted in L7 runtime, used by L2 agent mesh – our extension of the Zero Gravity framework)."""
    t0 = time.perf_counter()
    route = None
    try:
        r = httpx.post(INFERENCE_URL + "/v1/chat/completions", timeout=40,
                       headers={"x-zg-agent": agent, "x-zg-caller": agent, "x-zg-task-class": "extraction",
                                "x-zg-data-class": "customer", "x-zg-run-id": run_id or ""},
                       json={"messages": [{"role": "system", "content": PROMPT.replace("Customer message: ", "").strip()}, {"role": "user", "content": text}], "response_format": {"type": "json_object"}, "max_tokens": 160})
        r.raise_for_status()
        body = r.json()
        route = body.get("zg_route")
        if route and route.get("stub"):
            raise ValueError("gateway returned the deterministic stub")
        d = json.loads(body["choices"][0]["message"]["content"])
        if valid(d):
            det = deterministic(text)
            if d["intentType"] == det["intentType"]:
                # Budget is a hard number: keep the model's value only if the parser found the same £ amount in the text.
                if d.get("budgetGBP") != det["budgetGBP"]:
                    d["budgetGBP"] = det["budgetGBP"]
                return d, {"task": "intent-extraction", "route": "inference-gateway", "model": route and route.get("routedModel"),
                           "servedBy": route and route.get("servedBy"), "validated": True, "gateway": route,
                           "ms": round((time.perf_counter() - t0) * 1000), "crossCheck": "agrees with deterministic parser"}
            return det, {"task": "intent-extraction", "route": "deterministic-fallback", "model": None, "validated": True, "gateway": route,
                         "ms": round((time.perf_counter() - t0) * 1000), "why": f"model said {d['intentType']}, parser said {det['intentType']} – parser wins"}
        why = "model output failed schema validation"
    except Exception as e:
        why = f"inference gateway: {type(e).__name__}: {str(e)[:80]}"
    return deterministic(text), {"task": "intent-extraction", "route": "deterministic-fallback", "model": None, "validated": True, "gateway": route,
                                 "ms": round((time.perf_counter() - t0) * 1000), "why": why}
