"""AgenticTelco MVP · L6 legacy stand-ins (MOCKED, always labelled). Each one speaks a TM Forum-shaped API, as an adapter would.

  Billing B      TMF666-shaped billing account + balance. Own customer ID (BIL-B-…). Slow to answer.
  Availability   TMF679-shaped qualification by address key. Data refreshed only overnight (asOf 02:00).
  Inventory      TMF639-shaped resource view of site 4471 (exchange, fibre path, access port).
  Legacy OSS     TMF641-shaped service order. No push: results come from the overnight batch (each read = one batch run, demo clock).
  Payment link   Mocked payment link for an overdue balance.

Scenario knobs (PUT /standin/scenario) are labelled in the UI: they change only the mocked legacy systems, never Salesforce or policy."""
import time, uuid
from datetime import datetime, timedelta, timezone
from fastapi import FastAPI, HTTPException, Request
from stack.mvp.common import q, q1, J, Span, STANDIN, parse_traceparent, DEMO_DAY_SECONDS, init_schema

app = FastAPI(title="AgenticTelco MVP legacy stand-ins (mocked)")
BILLING_DELAY_S = 1.2
DEFAULT = {
    "scenario": {"overdue": False, "portFree": True},
    "billing": {"BIL-B-0077812": {"name": "BRIGHTWELL DESIGN LTD", "balanceGBP": 0.0, "overdueGBP": 0.0}},
    "availability": {"A00000001975": ["AgenticTelco Fibre 150", "AgenticTelco Fibre 500", "AgenticTelco Fibre 900"]},
    "site": {"4471": {"site": "4471", "addressKey": "A00000001975", "exchange": "Martlesham Heath exchange (MH)",
                      "fibrePath": ["MH exchange OLT-07", "Splitter cabinet MH-C12", "Brightwell, 1 Fibre Way"],
                      "accessPort": {"id": "MH-OLT-07/1/14", "capacityMbps": 150, "state": "inService"}, "freePorts900": 1}},
    "oss": {},
}

def st(name):
    r = q1("select value from mvp.standin where name=%s", name)
    if r is None:
        q("insert into mvp.standin(name, value) values (%s,%s) on conflict do nothing", name, J(DEFAULT[name]))
        return DEFAULT[name]
    return r["value"]

def put(name, v):
    q("insert into mvp.standin(name, value) values (%s,%s) on conflict (name) do update set value=excluded.value", name, J(v))

def tid(request):
    return parse_traceparent(request.headers.get("traceparent"))

def span(request, step, api, comp):
    t, p = tid(request)
    return Span(t, "L6", comp, step, runtime=STANDIN, api=api, method=request.method, path=request.url.path, parent=p)

def now():
    return datetime.now(timezone.utc)

@app.on_event("startup")
def _start():
    init_schema()

@app.get("/health")
def health():
    return {"ok": True, "service": "mvp-standins", "label": "Legacy stand-ins (mocked)"}

# ---- scenario knobs ------------------------------------------------------------------------------------------------
@app.get("/standin/scenario")
def get_scenario():
    return st("scenario")

@app.put("/standin/scenario")
async def set_scenario(request: Request):
    b = await request.json()
    s = {**st("scenario"), **{k: bool(v) for k, v in b.items() if k in ("overdue", "portFree")}}
    put("scenario", s)
    bil = st("billing"); bil["BIL-B-0077812"].update(overdueGBP=312.40 if s["overdue"] else 0.0, balanceGBP=312.40 if s["overdue"] else 0.0)
    put("billing", bil)
    site = st("site"); site["4471"]["freePorts900"] = 1 if s["portFree"] else 0
    put("site", site)
    return s

@app.get("/standin/network/{site_id}")
def network_view(site_id: str):
    """Read-only snapshot for the L7 network view (not an API call in the story, so no span)."""
    s = st("site").get(site_id) or {}
    o = next((x for x in st("oss").values() if x.get("site") == site_id), None)
    return {"site": site_id, "exchange": s.get("exchange"), "fibrePath": s.get("fibrePath"), "accessPort": s.get("accessPort"), "freePorts900": s.get("freePorts900"),
            "ossState": (o or {}).get("state"), "x-mocked": True}

@app.post("/standin/reset")
def reset():
    for k, v in DEFAULT.items():
        put(k, v)
    return {"reset": True}

# ---- TMF666 billing (slow) -----------------------------------------------------------------------------------------
@app.get("/tmf-api/accountManagement/v4/billingAccount/{bid}")
def billing_account(bid: str, request: Request):
    with span(request, "Billing B: read balance (slow legacy)", "TMF666", "Billing B stand-in") as sp:
        time.sleep(BILLING_DELAY_S)
        b = st("billing").get(bid)
        if not b:
            sp.status = 404
            raise HTTPException(404, f"billing account {bid} unknown to Billing B")
        res = {"id": bid, "@type": "BillingAccount", "name": b["name"], "state": "active",
               "accountBalance": [{"balanceType": "current", "amount": {"unit": "GBP", "value": b["balanceGBP"]}},
                                  {"balanceType": "overdue", "amount": {"unit": "GBP", "value": b["overdueGBP"]}}],
               "x-legacy": "Billing B (one of two billing systems from a merger); answers in ~1.2 s", "x-mocked": True}
        sp.status, sp.response = 200, res
        return res

# ---- TMF679 availability (overnight refresh) -----------------------------------------------------------------------
@app.get("/tmf-api/productOfferingQualification/v5/availability/{address_key}")
def availability(address_key: str, request: Request):
    with span(request, "Availability: what can be delivered at the address key", "TMF679", "Availability stand-in") as sp:
        names = st("availability").get(address_key)
        if names is None:
            sp.status = 404
            raise HTTPException(404, "unknown address key")
        as_of = now().replace(hour=2, minute=0, second=0, microsecond=0)
        res = {"@type": "CheckProductOfferingQualification", "addressKey": address_key, "state": "done",
               "qualifiedProductOffering": [{"name": n} for n in names], "asOf": as_of.isoformat(),
               "x-legacy": "Refreshed only by the overnight job (02:00)", "x-mocked": True}
        sp.status, sp.response = 200, res
        return res

# ---- TMF639-shaped inventory: site 4471 ----------------------------------------------------------------------------
@app.get("/tmf-api/resourceInventoryManagement/v4/site/{site_id}")
def site(site_id: str, request: Request):
    with span(request, "Network inventory: site, exchange and access port", "TMF639", "Inventory stand-in") as sp:
        s = st("site").get(site_id)
        if not s:
            sp.status = 404
            raise HTTPException(404, "unknown site")
        sp.status, sp.response = 200, {**s, "x-mocked": True}
        return sp.response

# ---- TMF641 legacy OSS (overnight batch) ---------------------------------------------------------------------------
@app.post("/tmf-api/serviceOrdering/v4/serviceOrder", status_code=201)
async def service_order(request: Request):
    b = await request.json()
    ext = b.get("externalId") or uuid.uuid4().hex[:10]
    with span(request, "Legacy OSS: submit service order (queued for the overnight batch)", "TMF641", "Legacy OSS stand-in") as sp:
        oss = st("oss")
        if ext not in oss:   # idempotent on externalId
            committed = (now() + timedelta(days=1)).date().isoformat()   # business date: live next day (the demo clock only speeds up the waiting)
            oss[ext] = {"id": "SO-" + uuid.uuid4().hex[:8].upper(), "externalId": ext, "state": "acknowledged", "site": b.get("site", "4471"),
                        "toCapacityMbps": b.get("toCapacityMbps", 900), "batchRuns": 0, "jeopardyAlert": [], "milestone": [],
                        "requestedCompletionDate": committed, "expectedCompletionDate": committed}
            put("oss", oss)
        res = {**oss[ext], "@type": "ServiceOrder", "x-mocked": True, "x-legacy": "No API push; results only after the overnight batch"}
        sp.status, sp.response = 201, res
        return res

@app.get("/tmf-api/serviceOrdering/v4/serviceOrder")
def service_order_batch(externalId: str, request: Request):
    """Each read is one overnight batch run (demo clock). No free 900 port → jeopardy NoFreePort, date +2 days; next batch reserves it."""
    with span(request, "Legacy OSS: overnight batch result", "TMF641", "Legacy OSS stand-in") as sp:
        oss, sites = st("oss"), st("site")
        o = oss.get(externalId)
        if not o:
            sp.status = 404
            raise HTTPException(404, "unknown service order")
        s = sites[o["site"]]
        if o["state"] not in ("completed",):
            o["batchRuns"] += 1
            if s["freePorts900"] > 0:
                s["accessPort"].update(capacityMbps=o["toCapacityMbps"], state="inService")
                s["freePorts900"] -= 1
                o["state"] = "completed"
                o["milestone"].append({"name": "PortReserved", "milestoneDate": now().isoformat(), "message": "Exchange port reserved; access port now 900 Mbps"})
                o["completionDate"] = o["expectedCompletionDate"]
            elif not o["jeopardyAlert"]:
                revised = (datetime.fromisoformat(o["expectedCompletionDate"]) + timedelta(days=2)).date().isoformat()
                o["state"] = "inProgress"
                o["jeopardyAlert"].append({"jeopardyType": "NoFreePort", "name": "No free exchange port", "alertDate": now().isoformat(),
                                           "message": "No 900 Mbps port free at Martlesham Heath; next port frees in 2 days", "revisedDays": 2,
                                           "revisedCompletionDate": revised})
                o["expectedCompletionDate"] = revised
                s["freePorts900"] = 1   # the port frees up in two (demo) days: the next batch run reserves it
            put("site", sites)
            put("oss", oss)
        res = [{**o, "@type": "ServiceOrder", "x-mocked": True}]
        sp.status, sp.response = 200, res
        return res

# ---- payment link (mocked) -----------------------------------------------------------------------------------------
@app.post("/payment/link")
async def payment_link(request: Request):
    b = await request.json()
    with span(request, "Payment link (mocked)", None, "Payment stand-in") as sp:
        res = {"url": f"https://pay.agentictelco.example/b/{b.get('billingAccount', 'unknown')}/{uuid.uuid4().hex[:6]}", "x-mocked": True,
               "amount": {"unit": "GBP", "value": st("billing").get(b.get("billingAccount"), {}).get("overdueGBP", 0)}}
        sp.status, sp.response = 201, res
        return res
