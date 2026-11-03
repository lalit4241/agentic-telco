"""Run the four MVP journeys live against the local stack (gateway :8120) and save each final /api/state as a recorded run.

Usage: .venv/bin/python scripts/record_mvp.py [happy notauth overdue delayed]
Each case starts from the seed (Fibre 150 Installed), so runs are independent. Output: recordings/mvp/<case>.json
"""
import json, sys, time, datetime, pathlib, httpx

G = "http://127.0.0.1:8120"
OUT = pathlib.Path(__file__).resolve().parent.parent / "recordings" / "mvp"
YES = "Yes please, go ahead."


def state(cid):
    return httpx.get(G + "/api/state", params={"conversationId": cid}, timeout=60).json()


def run(case):
    s = httpx.post(G + "/api/demo/start", json={"case": case}, timeout=900).json()
    cid, turns = s["conversationId"], []
    t = time.time(); r = httpx.post(G + "/api/chat", json={"conversationId": cid, "message": s["opening"]}, timeout=600).json()
    turns.append({"message": "opening", "seconds": round(time.time() - t, 1), "tools": r.get("tools")})
    if case in ("happy", "delayed"):
        t = time.time(); r = httpx.post(G + "/api/chat", json={"conversationId": cid, "message": YES}, timeout=600).json()
        turns.append({"message": YES, "seconds": round(time.time() - t, 1), "tools": r.get("tools")})
        for _ in range(120):
            time.sleep(3); st = state(cid)
            if st.get("intent") and st["intent"]["lifecycle_status"] == "fulfilled":
                break
        for _ in range(40):   # wait for the proactive "live" message
            st = state(cid)
            if any((m.get("meta") or {}).get("reportState") == "icm:StateComplies" for m in st["messages"]):
                break
            time.sleep(2)
    st = state(cid)
    rec = {"case": case, "title": s["title"], "label": "recorded run", "recordedAt": datetime.datetime.now(datetime.timezone.utc).isoformat(),
           "conversationId": cid, "turns": turns, "state": st}
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"{case}.json").write_text(json.dumps(rec, indent=1, default=str))
    print(f"=== {case} {cid} turns={turns} intent={(st.get('intent') or {}).get('lifecycle_status')} spans={len(st['spans'])}")
    for m in st["messages"]:
        print(" ", m["role"], ":", m["content"])
    print("  milestones:", [m["name"] for m in st.get("milestones", [])])
    print("  links:", st.get("links"))
    sys.stdout.flush()


if __name__ == "__main__":
    for c in sys.argv[1:] or ["happy", "notauth", "overdue", "delayed"]:
        run(c)
