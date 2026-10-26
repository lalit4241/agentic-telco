"""L2 · Network/OSS agent – an A2A-style peer (agent card + JSON-RPC message/send).
Receives a hand-off from the care agent, runs a TMF645 line test, raises a TMF641 corrective service order,
and resolves the TMF621 ticket. Diagnosis is rule-based (deterministic) – no model decides network actions."""
import uuid
from fastapi import FastAPI, Request
from stack.zg_common.config import url, PORTS
from stack.zg_common.http import call
from stack.zg_common.telemetry import instrument_app, RUN_ID

SVC = "network-agent"
OSS = url("oss_mock")
app = FastAPI(title="AgenticTelco network agent (A2A)")
instrument_app(app, SVC)

CARD = {"name": "zg-network-agent", "description": "Network assurance agent: line tests, corrective service orders, ticket resolution",
        "url": f"http://127.0.0.1:{PORTS['network_agent']}/a2a", "version": "1.0.0", "protocolVersion": "0.3.0",
        "capabilities": {"streaming": False, "pushNotifications": False},
        "defaultInputModes": ["application/json"], "defaultOutputModes": ["application/json"],
        "skills": [{"id": "diagnose-and-fix", "name": "Diagnose and fix broadband performance fault",
                    "description": "TMF645 line test → TMF641 corrective service order → TMF621 resolve", "tags": ["TMF645", "TMF641", "TMF621"]}]}

@app.get("/.well-known/agent-card.json")
def card():
    return CARD

@app.get("/health")
def health():
    return {"ok": True, "service": SVC}

@app.post("/a2a")
async def a2a(request: Request):
    rpc = await request.json()
    if rpc.get("method") != "message/send":
        return {"jsonrpc": "2.0", "id": rpc.get("id"), "error": {"code": -32601, "message": "method not found"}}
    data = next(p["data"] for p in rpc["params"]["message"]["parts"] if p.get("kind") == "data")
    rid = RUN_ID.get()
    steps = []
    sq = call(SVC, "POST", OSS + "/tmf-api/serviceQualificationManagement/v4/checkServiceQualification", run_id=rid,
              json={"service": {"id": data.get("serviceId", "SVC-" + data["customerId"]), "serviceSpecification": {"name": "FTTP-Access"}},
                    "relatedParty": [{"id": data["customerId"]}]}).json()
    lt = sq["serviceQualificationItem"][0]["lineTest"]
    steps.append({"step": "TMF645 line test", "result": lt})
    if lt["verdict"] == "pass":
        fix = {"action": "none", "note": "Line healthy – advise in-home Wi-Fi optimisation"}
    else:
        action = "Clean/replace ONT optical connector" if (lt.get("opticalPowerDbm") or 0) < -25 else "Re-profile line (DLM reset)"
        so = call(SVC, "POST", OSS + "/tmf-api/serviceOrdering/v4/serviceOrder", run_id=rid, idem=f"{rid}:tmf641-fix",
                  json={"externalId": f"fix-{data['ticketId']}", "description": action, "category": "corrective",
                        "relatedParty": [{"id": data["customerId"]}],
                        "serviceOrderItem": [{"id": "1", "action": "modify", "service": {"serviceSpecification": {"name": "FTTP-Access"}}}],
                        "troubleTicket": {"id": data["ticketId"]}}).json()
        fix = {"action": action, "serviceOrderId": so["id"], "state": so["state"]}
    steps.append({"step": "TMF641 corrective service order", "result": fix})
    tt = call(SVC, "PATCH", OSS + f"/tmf-api/troubleTicket/v4/troubleTicket/{data['ticketId']}", run_id=rid,
              json={"status": "resolved", "resolution": fix["action"], "note": [{"author": "zg-network-agent", "text": f"Line test {lt['verdict']}; {fix['action']}"}]}).json()
    steps.append({"step": "TMF621 resolve", "result": {"status": tt["status"]}})
    task = {"id": "task-" + uuid.uuid4().hex[:8], "contextId": rpc["params"]["message"].get("contextId"), "kind": "task",
            "status": {"state": "completed"}, "artifacts": [{"artifactId": "diagnosis", "parts": [{"kind": "data", "data": {"steps": steps, "ticket": tt["id"]}}]}]}
    return {"jsonrpc": "2.0", "id": rpc.get("id"), "result": task}
