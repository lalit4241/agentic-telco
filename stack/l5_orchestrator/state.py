"""Read-only view of a BPMN process instance (Operaton history + our saga log). Uses the *agent* identity: read only."""
from stack.zg_common.db import q, q1, J
from stack.l5_orchestrator.engine import req

END_STATES = {"End_Completed": "completed", "End_Compensated": "compensated", "End_PolicyBlocked": "policy-blocked"}

def process_state(pi, run_id=None, record=False):
    h = req("agent", "GET", f"/history/process-instance/{pi}", run_id=run_id, record=record, caller="l5-state")
    if h.status_code != 200:
        return {"processInstanceId": pi, "state": "unknown", "httpStatus": h.status_code}
    hp = h.json()
    acts = req("agent", "GET", "/history/activity-instance", params={"processInstanceId": pi, "sortBy": "startTime", "sortOrder": "asc"},
               run_id=run_id, record=record, caller="l5-state").json()
    acts = sorted(acts, key=lambda a: (a.get("startTime") or "", a.get("id")))
    done = [a for a in acts if a.get("endTime")]
    active = [a["activityId"] for a in acts if not a.get("endTime") and not a.get("canceled")]
    end = next((a["activityId"] for a in reversed(done) if a["activityId"] in END_STATES), None)
    state = END_STATES.get(end) or ("running" if hp.get("state") == "ACTIVE" else hp.get("state", "unknown").lower())
    steps = q("select step, idem_key, status, attempt, output, worker, at from l5.saga_step where workflow_id=%s order by id", pi)
    reason = next((s["output"].get("message") for s in reversed(steps) if s["status"] in ("failed", "policy-blocked") and s["output"]), None)
    res = {"engine": "Operaton (BPMN, Apache-2.0)", "processInstanceId": pi, "businessKey": hp.get("businessKey"),
           "processDefinitionKey": hp.get("processDefinitionKey"), "state": state, "endEvent": end, "reason": reason,
           "activities": [{"activityId": a["activityId"], "name": a.get("activityName"), "type": a["activityType"],
                           "start": a.get("startTime"), "end": a.get("endTime"), "canceled": a.get("canceled", False)} for a in acts],
           "activeActivities": active,
           "steps": [{**s, "at": str(s["at"])} for s in steps]}
    if state != "running":
        q("update l5.saga set state=%s, result=%s, updated_at=now() where workflow_id=%s", state, J({"endEvent": end, "reason": reason}), pi)
    return res
