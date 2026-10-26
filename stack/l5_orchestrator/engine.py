"""Thin client for the Operaton REST API (Camunda 7 compatible). Three identities, three privilege levels:
  admin  – bootstrap only (deploy BPMN, create users / groups / authorizations)
  agent  – L2 agents: may START a process instance and READ state. Nothing else (enforced by Operaton authorizations).
  worker – L5 external-task workers: fetch-and-lock / complete / bpmnError."""
import os, time
import httpx
from stack.zg_common.telemetry import record_call

BASE = os.environ.get("ZG_OPERATON_URL", "http://127.0.0.1:8180/engine-rest")
PROCESS_KEY = "broadbandUpgradeSaga"

def creds(role):
    u = os.environ.get(f"ZG_OPERATON_{role.upper()}_USER")
    p = os.environ.get(f"ZG_OPERATON_{role.upper()}_PASSWORD")
    if not u or not p:
        from pathlib import Path
        f = Path(__file__).resolve().parents[2] / ".data" / "secrets.env"
        env = dict(l.split("=", 1) for l in f.read_text().split() if "=" in l) if f.exists() else {}
        u, p = env.get(f"ZG_OPERATON_{role.upper()}_USER"), env.get(f"ZG_OPERATON_{role.upper()}_PASSWORD")
    return (u, p)

def req(role, method, path, json=None, params=None, caller=None, run_id=None, record=True, timeout=30):
    t0 = time.perf_counter()
    r = httpx.request(method, BASE + path, json=json, params=params, auth=creds(role), timeout=timeout)
    if record and run_id:
        try:
            out = r.json() if r.content else None
        except Exception:
            out = r.text[:300]
        record_call(caller=caller or role, callee="operaton", method=method, path="/engine-rest" + path, status=r.status_code,
                    req=json, resp=out, ms=round((time.perf_counter() - t0) * 1000, 1), run_id=run_id,
                    extra={"operatonIdentity": creds(role)[0], "role": role})
    return r

def vars_(d):
    return {k: {"value": v, "type": "String" if isinstance(v, str) else ("Boolean" if isinstance(v, bool) else "Json" if isinstance(v, (dict, list)) else "Integer")}
            for k, v in d.items() if v is not None and not isinstance(v, (dict, list))}
