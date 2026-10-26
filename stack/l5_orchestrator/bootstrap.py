"""Idempotent L5 bootstrap: deploy the BPMN and set up least-privilege identities in Operaton."""
import sys
from pathlib import Path
import httpx
from stack.l5_orchestrator.engine import BASE, PROCESS_KEY, creds

ADMIN = creds("admin")
BPMN = Path(__file__).parent / "bpmn" / "broadband-upgrade-saga.bpmn"
# Camunda 7 / Operaton resource types
R_PROCDEF, R_PROCINST, R_HIST_PROCINST = 6, 8, 20

def a(method, path, **kw):
    return httpx.request(method, BASE + path, auth=ADMIN, timeout=30, **kw)

def ensure_user(role, group, group_name):
    uid, pw = creds(role)
    if a("GET", f"/group/{group}").status_code == 404:
        a("POST", "/group/create", json={"id": group, "name": group_name, "type": "SYSTEM"}).raise_for_status()
    if a("GET", f"/user/{uid}/profile").status_code == 404:
        a("POST", "/user/create", json={"profile": {"id": uid, "firstName": role, "lastName": "AgenticTelco"}, "credentials": {"password": pw}}).raise_for_status()
    if not a("GET", "/user", params={"id": uid, "memberOfGroup": group}).json():
        a("PUT", f"/group/{group}/members/{uid}")

def grant(group, rtype, rid, perms):
    existing = a("GET", "/authorization", params={"groupIdIn": group, "resourceType": rtype, "resourceId": rid}).json()
    for e in existing:
        a("DELETE", f"/authorization/{e['id']}")
    a("POST", "/authorization/create", json={"type": 1, "permissions": perms, "groupId": group, "resourceType": rtype, "resourceId": rid}).raise_for_status()

def main():
    r = a("POST", "/deployment/create", data={"deployment-name": "agentictelco-l5", "deploy-changed-only": "true", "enable-duplicate-filtering": "true"},
          files={"broadband-upgrade-saga.bpmn": (BPMN.name, BPMN.read_bytes(), "application/xml")})
    r.raise_for_status()
    ensure_user("agent", "zgagents", "L2 agents (start + read only)")
    ensure_user("worker", "zgl5workers", "L5 external-task workers")
    # Agents: start instances of this one process and read state/history. No UPDATE anywhere → cannot complete, skip or modify.
    grant("zgagents", R_PROCDEF, PROCESS_KEY, ["READ", "CREATE_INSTANCE", "READ_INSTANCE", "READ_HISTORY"])
    grant("zgagents", R_PROCINST, "*", ["CREATE"])
    # Workers: lock / complete external tasks of this process.
    grant("zgl5workers", R_PROCDEF, PROCESS_KEY, ["READ", "READ_INSTANCE", "UPDATE_INSTANCE", "READ_HISTORY"])
    grant("zgl5workers", R_PROCINST, "*", ["READ", "UPDATE"])
    d = a("GET", "/process-definition/key/" + PROCESS_KEY).json()
    if not d.get("key"):
        raise SystemExit(f"BPMN not deployed: {d}")
    print(f"Operaton ready: {d.get('key')} v{d.get('version')} deployed; identities zgagent (start+read) and zgl5worker configured")

if __name__ == "__main__":
    sys.exit(main())
