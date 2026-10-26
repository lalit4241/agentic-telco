"""Outbound HTTP for every layer: propagates run id, caller name and W3C traceparent (via OTel httpx instrumentation)."""
import httpx
from .telemetry import RUN_ID

def headers(caller, extra=None, run_id=None):
    h = {"x-zg-caller": caller}
    rid = run_id or RUN_ID.get()
    if rid:
        h["x-zg-run-id"] = rid
    h.update(extra or {})
    return h

def call(caller, method, url, json=None, params=None, idem=None, run_id=None, timeout=90.0):
    extra = {"Idempotency-Key": idem} if idem else {}
    with httpx.Client(timeout=timeout) as c:
        r = c.request(method, url, json=json, params=params, headers=headers(caller, extra, run_id))
    return r

async def acall(caller, method, url, json=None, params=None, idem=None, run_id=None, timeout=90.0):
    extra = {"Idempotency-Key": idem} if idem else {}
    async with httpx.AsyncClient(timeout=timeout) as c:
        return await c.request(method, url, json=json, params=params, headers=headers(caller, extra, run_id))
