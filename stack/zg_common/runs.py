"""L8 · collect everything about one run (ledger, saga log, events, decisions, spans) – used live and for recordings."""
import json
from .db import q, q1
from .telemetry import SPAN_FILE

def _s(rows):
    return [{k: (str(v) if k in ("at", "changed_at", "started_at", "finished_at", "created_at", "updated_at") else (float(v) if k == "duration_ms" and v is not None else v))
             for k, v in r.items()} for r in rows]

def collect_run(rid):
    run = q1("select * from l8.runs where run_id=%s", rid)
    calls = _s(q("select * from l8.api_calls where run_id=%s order by seq", rid))
    trace_ids = {c["trace_id"] for c in calls if c["trace_id"]}
    spans = []
    if SPAN_FILE.exists():
        for line in SPAN_FILE.read_text().splitlines():
            s = json.loads(line)
            if s["trace_id"] in trace_ids or s["attributes"].get("zg.run_id") == rid:
                spans.append(s)
    sagas = _s(q("select * from l5.saga where run_id=%s", rid))
    steps = _s(q("select s.* from l5.saga_step s join l5.saga g on g.workflow_id=s.workflow_id where g.run_id=%s order by s.id", rid))
    return {"run": _s([run])[0] if run else None, "calls": calls, "spans": sorted(spans, key=lambda s: s["start_ns"]),
            "saga": sagas[0] if sagas else None, "sagaSteps": steps,
            "events": _s(q("select * from l8.events where run_id=%s order by seq", rid)),
            "inference": _s(q("select seq, at, agent, task_class, data_class, routed_model, served_by, cache, pii_redacted, prompt_tokens, "
                               "completion_tokens, cost_gbp, latency_ms, budget, opa, fallbacks, stub from l8.inference where run_id=%s order by seq", rid)),
            "decisions": _s(q("select id, run_id, policy_version, result, at from l4.decision where run_id=%s order by id", rid))}
