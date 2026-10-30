"""Idempotent MVP L5 bootstrap: deploy the MVP BPMN and grant least privilege on it (agent = start + read; worker = run tasks)."""
import sys
from pathlib import Path
from stack.l5_orchestrator.bootstrap import a, ensure_user, grant, R_PROCDEF, R_PROCINST
from stack.mvp.common import init_schema

KEY = "agentictelcoMvpUpgrade"
BPMN = Path(__file__).parent / "bpmn" / "agentictelco-mvp-upgrade.bpmn"

def main():
    init_schema()
    a("POST", "/deployment/create", data={"deployment-name": "agentictelco-mvp", "deploy-changed-only": "true", "enable-duplicate-filtering": "true"},
      files={BPMN.name: (BPMN.name, BPMN.read_bytes(), "application/xml")}).raise_for_status()
    ensure_user("agent", "zgagents", "L2 agents (start + read only)")
    ensure_user("worker", "zgl5workers", "L5 external-task workers")
    grant("zgagents", R_PROCDEF, KEY, ["READ", "CREATE_INSTANCE", "READ_INSTANCE", "READ_HISTORY"])
    grant("zgagents", R_PROCINST, "*", ["CREATE"])
    grant("zgl5workers", R_PROCDEF, KEY, ["READ", "READ_INSTANCE", "UPDATE_INSTANCE", "READ_HISTORY"])
    grant("zgl5workers", R_PROCINST, "*", ["READ", "UPDATE"])
    d = a("GET", "/process-definition/key/" + KEY).json()
    if not d.get("key"):
        raise SystemExit(f"BPMN not deployed: {d}")
    print(f"Operaton ready: {d['key']} v{d['version']} deployed; agent = start + read, worker = run tasks")

if __name__ == "__main__":
    sys.exit(main())
