#!/usr/bin/env python3
"""MVP build step 0: speed-test small local models (Ollama, thinking off) on the L2 agent's tool-calling turns.
Target: < ~5 s per turn on the demo host. Writes docs/mvp/model-speedtest.json and prints a Markdown table."""
import json, os, statistics, sys, time, urllib.request
HOST = os.environ.get("OLLAMA_HOST_URL", "http://127.0.0.1:11434")
MODELS = sys.argv[1:] or ["qwen3-4b-instruct-2507", "phi4-mini-instruct", "granite3.3-2b"]
TOOLS = [
    {"type": "function", "function": {"name": "get_context", "description": "Get the facts for this request: who is asking, the site, current broadband, contract, balance and what is available at the site.",
        "parameters": {"type": "object", "properties": {"need": {"type": "string", "description": "the customer's need in their words"}}, "required": ["need"]}}},
    {"type": "function", "function": {"name": "request_upgrade", "description": "Ask the workflow to upgrade the line once the customer has agreed. Does not write anything itself.",
        "parameters": {"type": "object", "properties": {"offering": {"type": "string", "description": "offering id, e.g. fibre-900"}}, "required": ["offering"]}}},
    {"type": "function", "function": {"name": "order_status", "description": "Get the status of the customer's upgrade order.",
        "parameters": {"type": "object", "properties": {}}}},
]
SYS = ("You are UK Telco's business assistant for Brightwell Design Ltd. You only propose; policy decides and the workflow writes. "
       "Always call get_context before recommending. Call request_upgrade only after the customer clearly agrees. "
       "Call order_status when asked about an order. Answer in at most 3 short sentences.")
ASK = "We're hiring 15 more staff and moving to cloud video. The line can't keep up."
CTX = json.dumps({"requester": {"name": "Sam", "authorisedContact": True}, "currentBroadband": {"name": "Fibre 150", "downloadSpeedMbps": 150, "priceGBP": 27},
                  "contractMonthsLeft": 10, "overdueBalance": 0, "allowedOfferings": [{"id": "fibre-900", "name": "Fibre 900", "downloadSpeedMbps": 900, "priceGBP": 45}],
                  "advisory": {"allow": True}})
CASES = [
    ("ask→get_context", [{"role": "user", "content": ASK}], "get_context"),
    ("context→recommend", [{"role": "user", "content": ASK}, {"role": "assistant", "content": "", "tool_calls": [{"function": {"name": "get_context", "arguments": {"need": ASK}}}]},
                           {"role": "tool", "content": CTX}], None),
    ("agree→request_upgrade", [{"role": "user", "content": ASK}, {"role": "assistant", "content": "I recommend Fibre 900 at £45 a month. Shall I go ahead?"},
                               {"role": "user", "content": "Yes, go ahead with Fibre 900."}], "request_upgrade"),
    ("status→order_status", [{"role": "user", "content": "Where is my upgrade order?"}], "order_status"),
]

def chat(model, msgs):
    body = {"model": model, "messages": [{"role": "system", "content": SYS}] + msgs, "tools": TOOLS, "stream": False, "think": False,
            "keep_alive": "30m", "options": {"temperature": 0, "num_ctx": 4096, "num_predict": 160}}
    t = time.time()
    req = urllib.request.Request(HOST + "/api/chat", json.dumps(body).encode(), {"Content-Type": "application/json"})
    try:
        r = json.load(urllib.request.urlopen(req, timeout=300))
    except urllib.error.HTTPError as e:   # e.g. a model template that rejects the think flag
        if "think" in e.read().decode():
            body.pop("think"); req = urllib.request.Request(HOST + "/api/chat", json.dumps(body).encode(), {"Content-Type": "application/json"})
            r = json.load(urllib.request.urlopen(req, timeout=300))
        else:
            raise
    return time.time() - t, r

def main():
    out = []
    for m in MODELS:
        load, _ = chat(m, [{"role": "user", "content": "hi"}])
        lat, ok, notes = [], 0, []
        for name, msgs, want in CASES:
            for rep in range(2):
                dt, r = chat(m, msgs)
                lat.append(dt)
                calls = [c["function"]["name"] for c in (r["message"].get("tool_calls") or [])]
                text = r["message"].get("content", "")
                good = (want in calls) if want else (not calls and "900" in text)
                ok += good
                if rep == 0:
                    notes.append(f"{name}: {'OK' if good else 'MISS'} calls={calls} text={text[:90]!r}")
        res = dict(model=m, load_s=round(load, 1), median_s=round(statistics.median(lat), 2), p90_s=round(sorted(lat)[int(0.9 * len(lat)) - 1], 2),
                   max_s=round(max(lat), 2), tool_correct=f"{ok}/{len(lat)}", notes=notes)
        print(json.dumps(res, indent=1), flush=True)
        out.append(res)
    json.dump(dict(at=time.strftime("%Y-%m-%d %H:%M %Z"), host="8 vCPU, 15 GB RAM, CPU only, Ollama, think=false, temp 0, num_ctx 4096", results=out),
              open(os.path.join(os.path.dirname(__file__), "../../docs/mvp/model-speedtest.json"), "w"), indent=1)
    print("\n| Model | Load (s) | Median turn (s) | p90 (s) | Max (s) | Tool calls correct |\n|---|---|---|---|---|---|")
    for r in out:
        print(f"| {r['model']} | {r['load_s']} | {r['median_s']} | {r['p90_s']} | {r['max_s']} | {r['tool_correct']} |")

if __name__ == "__main__":
    main()
