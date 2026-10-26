"""L5 · read-only façade over the Operaton engine for the UI (BPMN XML + live step state). Starts nothing, changes nothing."""
from pathlib import Path
from fastapi import FastAPI
from fastapi.responses import Response
from stack.zg_common.db import q
from stack.zg_common.telemetry import instrument_app
from stack.l5_orchestrator.state import process_state
from stack.l5_orchestrator.engine import req

app = FastAPI(title="AgenticTelco L5 read-only view")
instrument_app(app, "l5-view")
B = "/zg/orchestrator/v1"
BPMN = Path(__file__).parent / "bpmn" / "broadband-upgrade-saga.bpmn"

@app.get("/health")
def health():
    v = req("agent", "GET", "/version", record=False)
    return {"ok": v.status_code == 200, "service": "l5-view", "engine": "Operaton", "engineVersion": v.json().get("version") if v.status_code == 200 else None}

@app.get(B + "/bpmn")
def bpmn():
    return Response(BPMN.read_text(), media_type="application/xml")

@app.get(B + "/process/{pi}")
def process(pi: str):
    return process_state(pi)

@app.get(B + "/sagas")
def sagas():
    return q("select workflow_id, run_id, engine, state, result, created_at::text from l5.saga order by created_at desc limit 50")
