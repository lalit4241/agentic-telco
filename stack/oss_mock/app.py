"""Production OSS (mocked): TMF641 Service Ordering, TMF645 Service Qualification, TMF621 Trouble Ticket.
Clearly a stand-in. Supports fault injection (fail / delay) so the L5 saga's compensation and crash-resume can be shown."""
import asyncio, uuid, datetime
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse
from stack.zg_common.db import q, q1, J
from stack.zg_common.telemetry import instrument_app, RUN_ID
from stack.zg_common.events import apublish

SVC = "oss-mock"
app = FastAPI(title="AgenticTelco mocked OSS (TMF641/645/621)")
instrument_app(app, SVC)
now = lambda: datetime.datetime.now(datetime.timezone.utc).isoformat()
SO = "/tmf-api/serviceOrdering/v4"
TT = "/tmf-api/troubleTicket/v4"
SQ = "/tmf-api/serviceQualificationManagement/v4"

def fault(name):
    r = q1("select value from oss.fault_injection where name=%s", name)
    return r["value"] if r else None

@app.get("/health")
def health():
    return {"ok": True, "service": SVC}

@app.put("/admin/faults/{name}")
async def set_fault(name: str, request: Request):
    v = await request.json()
    q("insert into oss.fault_injection values(%s,%s) on conflict(name) do update set value=excluded.value", name, J(v))
    return {"name": name, "value": v}

@app.delete("/admin/faults/{name}")
def clear_fault(name: str):
    q("delete from oss.fault_injection where name=%s", name)
    return {"cleared": name}

@app.post(SO + "/serviceOrder", status_code=201)
async def service_order(request: Request, idempotency_key: str | None = Header(None)):
    body = await request.json()
    if idempotency_key:
        hit = q1("select status, response from oss.idempotency where key=%s", idempotency_key)
        if hit:
            return JSONResponse({**hit["response"], "_idempotentReplay": True}, status_code=hit["status"])
    f = fault("serviceOrder")
    cust = (body.get("relatedParty") or [{}])[0].get("id")
    if f and (not f.get("customer") or f.get("customer") == cust):
        if f.get("delaySeconds"):
            await asyncio.sleep(float(f["delaySeconds"]))
        if f.get("mode") == "fail":
            res = {"id": "SO-" + uuid.uuid4().hex[:8], "@type": "ServiceOrder", "state": "failed",
                   "errorMessage": [{"code": "OLT_PORT_ALLOCATION_FAILED", "reason": f.get("reason", "No free OLT port on the PON tree")}]}
            q("insert into oss.service_order values(%s,%s,'failed')", res["id"], J(res))
            if idempotency_key:
                q("insert into oss.idempotency values(%s,422,%s) on conflict do nothing", idempotency_key, J(res))
            await apublish("ServiceOrderStateChangeEvent", {"serviceOrder": {"id": res["id"], "state": "failed"}}, SVC, RUN_ID.get())
            return JSONResponse(res, status_code=422)
    exch = body.get("exchange")
    sid = "SO-" + uuid.uuid4().hex[:8]
    if exch:
        q("update oss.capacity set ports_reserved=ports_reserved+1, utilisation=round((ports_reserved+1)::numeric/ports_total,3) where exchange=%s", exch)
        q("insert into oss.reservation values(%s,%s,%s,'held')", "RSV-" + sid, exch, body.get("externalId"))
    res = {**body, "id": sid, "href": f"{SO}/serviceOrder/{sid}", "@type": "ServiceOrder", "state": "completed",
           "orderDate": now(), "completionDate": now(), "reservation": {"id": "RSV-" + sid, "exchange": exch}}
    q("insert into oss.service_order values(%s,%s,'completed')", sid, J(res))
    if idempotency_key:
        q("insert into oss.idempotency values(%s,201,%s) on conflict do nothing", idempotency_key, J(res))
    await apublish("ServiceOrderStateChangeEvent", {"serviceOrder": {"id": sid, "state": "completed"}}, SVC, RUN_ID.get())
    return res

@app.get(SO + "/serviceOrder")
def list_so(externalId: str | None = None):
    return [r["body"] for r in q("select body from oss.service_order where (%s::text is null or body->>'externalId'=%s) order by created_at", externalId, externalId)]

@app.post(SO + "/cancelServiceOrder", status_code=201)
async def cancel_so(request: Request):
    body = await request.json()
    ext = body.get("externalId")
    released = 0
    for r in q("select * from oss.reservation where order_ref=%s and state='held'", ext):
        q("update oss.reservation set state='released' where id=%s", r["id"])
        q("update oss.capacity set ports_reserved=ports_reserved-1, utilisation=round((ports_reserved-1)::numeric/ports_total,3) where exchange=%s", r["exchange"])
        released += 1
    q("update oss.service_order set state='cancelled' where body->>'externalId'=%s and state='completed'", ext)
    return {"@type": "CancelServiceOrder", "state": "done", "externalId": ext, "reservationsReleased": released}

# ---- TMF645 – line test / service qualification
@app.post(SQ + "/checkServiceQualification", status_code=201)
async def check_sq(request: Request):
    body = await request.json()
    f = fault("lineTest") or {}
    res = {"id": "SQ-" + uuid.uuid4().hex[:8], "@type": "CheckServiceQualification", "state": "done", "checkDate": now(),
           "qualificationResult": "qualified" if not f.get("degraded") else "unqualified",
           "serviceQualificationItem": [{"id": "1", "service": body.get("service"), "state": "done",
              "lineTest": {"syncRateMbps": f.get("syncRateMbps", 148), "expectedMbps": f.get("expectedMbps", 150),
                           "opticalPowerDbm": f.get("opticalPowerDbm", -19.2), "verdict": f.get("verdict", "pass"),
                           "suspectedFault": f.get("suspectedFault")}}]}
    return res

# ---- TMF621 – trouble ticket
@app.post(TT + "/troubleTicket", status_code=201)
async def create_tt(request: Request):
    body = await request.json()
    tid = "TT-" + uuid.uuid4().hex[:6].upper()
    res = {**body, "id": tid, "href": f"{TT}/troubleTicket/{tid}", "@type": "TroubleTicket", "status": "acknowledged", "creationDate": now()}
    q("insert into oss.trouble_ticket(id, body, status) values(%s,%s,%s)", tid, J(res), "acknowledged")
    await apublish("TroubleTicketCreateEvent", {"troubleTicket": {"id": tid, "status": "acknowledged"}}, SVC, RUN_ID.get())
    return res

@app.patch(TT + "/troubleTicket/{tid}")
async def patch_tt(tid: str, request: Request):
    patch = await request.json()
    r = q1("select body from oss.trouble_ticket where id=%s", tid)
    if not r:
        raise HTTPException(404)
    b = {**r["body"], **patch, "lastUpdate": now()}
    q("update oss.trouble_ticket set body=%s, status=%s, updated_at=now() where id=%s", J(b), b.get("status"), tid)
    await apublish("TroubleTicketStatusChangeEvent", {"troubleTicket": {"id": tid, "status": b.get("status")}}, SVC, RUN_ID.get())
    return b

@app.get(TT + "/troubleTicket/{tid}")
def get_tt(tid: str):
    r = q1("select body from oss.trouble_ticket where id=%s", tid)
    if not r:
        raise HTTPException(404)
    return r["body"]
