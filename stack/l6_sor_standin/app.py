"""L6 · System of Record stand-in.

A TMF-compliant stand-in for Salesforce Communications Cloud, using the same TMF Open API paths that Comms Cloud
exposes (TMF620/622/679 are Salesforce-certified; TMF629/632/637/648 are present in Comms Cloud). It holds RECORDS
and PRODUCT CONFIGURATION only (offer, price, required technology). No credit, consent, network or AI policy lives
here – that is the Zero Gravity Axiom: business rules have zero residual in the SoR.
"""
import uuid, datetime
from fastapi import FastAPI, Header, HTTPException, Request
from stack.zg_common.db import q, q1, J
from stack.zg_common.telemetry import instrument_app, RUN_ID
from stack.zg_common.events import apublish

SVC = "l6-sor-standin"
app = FastAPI(title="AgenticTelco L6 SoR stand-in (Comms Cloud TMF contract)")
instrument_app(app, SVC)
now = lambda: datetime.datetime.now(datetime.timezone.utc).isoformat()
CAT = "/tmf-api/productCatalogManagement/v4"
POQ = "/tmf-api/productOfferingQualification/v4"
ORD = "/tmf-api/productOrderingManagement/v4"
INV = "/tmf-api/productInventory/v4"

def idem(key, method, path, fn):
    if key:
        hit = q1("select status, response from sor.idempotency where key=%s", key)
        if hit:
            return hit["response"], True
    body = fn()
    if key:
        q("insert into sor.idempotency(key,method,path,status,response) values(%s,%s,%s,201,%s) on conflict do nothing", key, method, path, J(body))
        body = q1("select response from sor.idempotency where key=%s", key)["response"]
    return body, False

@app.get("/health")
def health():
    return {"ok": True, "service": SVC, "role": "SoR stand-in (records + product configuration only)"}

# ---- Party / Customer (TMF632 / TMF629)
@app.get("/tmf-api/partyManagement/v4/individual/{pid}")
def individual(pid: str):
    r = q1("select * from sor.party where id=%s", pid) or HTTPException(404)
    if isinstance(r, HTTPException):
        raise r
    first, last = r["name"].split(" ", 1)
    return {"id": r["id"], "@type": "Individual", "givenName": first, "familyName": last,
            "contactMedium": [{"mediumType": "email", "characteristic": {"emailAddress": r["email"]}}],
            "partyCharacteristic": [{"name": "marketingConsent", "valueType": "object", "value": r["consent"]["marketing"]}]}

def _customer(r):
    return {"id": r["id"], "@type": "Customer", "name": r["name"], "status": r["status"],
            "engagedParty": {"id": r["party_id"], "@referredType": "Individual"},
            "contactMedium": [{"mediumType": "postalAddress", "characteristic": r["address"]}],
            "characteristic": [{"name": "sfAccountName", "value": r["sf_account_name"]}]}

@app.get("/tmf-api/customerManagement/v4/customer")
def customers(name: str | None = None):
    rows = q("select * from sor.customer where (%s::text is null or name ilike %s)", name, f"%{name}%" if name else None)
    return [_customer(r) for r in rows]

@app.get("/tmf-api/customerManagement/v4/customer/{cid}")
def customer(cid: str):
    r = q1("select * from sor.customer where id=%s", cid)
    if not r:
        raise HTTPException(404, "customer not found")
    return _customer(r)

# ---- Catalog (TMF620 v4 – Salesforce-certified)
def _offer(r):
    return {"id": r["id"], "href": f"{CAT}/productOffering/{r['id']}", "name": r["name"], "description": r["description"],
            "lifecycleStatus": r["lifecycle_status"], "isSellable": True, "@type": "ProductOffering",
            "productOfferingPrice": [{"name": "Monthly", "priceType": "recurring", "recurringChargePeriod": "month",
                                      "price": {"taxIncludedAmount": {"unit": "GBP", "value": float(r["price_gbp"])}}}],
            "prodSpecCharValueUse": [{"name": "downloadSpeedMbps", "productSpecCharacteristicValue": [{"value": r["download_mbps"]}]},
                                     {"name": "requiredTechnology", "productSpecCharacteristicValue": [{"value": t} for t in r["required_technology"]]}]}

@app.get(CAT + "/productOffering")
def offerings():
    return [_offer(r) for r in q("select * from sor.product_offering order by price_gbp")]

@app.get(CAT + "/productOffering/{oid}")
def offering(oid: str):
    r = q1("select * from sor.product_offering where id=%s", oid)
    if not r:
        raise HTTPException(404)
    return _offer(r)

# ---- Qualification (TMF679 – Salesforce-certified). Product-configuration rule only: offer tech vs address tech.
@app.post(POQ + "/checkProductOfferingQualification")
async def check_poq(request: Request):
    body = await request.json()
    cid = body.get("relatedParty", [{}])[0].get("id")
    cust = q1("select * from sor.customer where id=%s", cid)
    items = []
    for it in body.get("checkProductOfferingQualificationItem", []):
        o = q1("select * from sor.product_offering where id=%s", it["productOffering"]["id"])
        avail = (cust or {}).get("address", {}).get("technology", [])
        ok = bool(o) and bool(set(o["required_technology"]) & set(avail))
        items.append({"id": it.get("id", "1"), "productOffering": it["productOffering"],
                      "qualificationItemResult": "qualified" if ok else "unqualified", "state": "done",
                      "eligibilityUnavailabilityReason": [] if ok else [{"code": "TECH_UNAVAILABLE",
                          "label": f"Requires {o['required_technology'] if o else '?'}; address has {avail}"}]})
    res = {"id": "POQ-" + uuid.uuid4().hex[:8], "@type": "CheckProductOfferingQualification", "state": "done",
           "qualificationResult": "qualified" if all(i["qualificationItemResult"] == "qualified" for i in items) else "unqualified",
           "effectiveQualificationDate": now(), "relatedParty": body.get("relatedParty"), "checkProductOfferingQualificationItem": items}
    q("insert into sor.qualification values(%s,%s)", res["id"], J(res))
    return res

# ---- Quote (TMF648)
@app.post("/tmf-api/quoteManagement/v4/quote", status_code=201)
async def quote(request: Request, idempotency_key: str | None = Header(None)):
    body = await request.json()
    def mk():
        o = q1("select * from sor.product_offering where id=%s", body["quoteItem"][0]["productOffering"]["id"])
        res = {"id": "Q-" + uuid.uuid4().hex[:8], "@type": "Quote", "state": "approved", "quoteDate": now(),
               "relatedParty": body.get("relatedParty"), "quoteItem": body["quoteItem"],
               "quoteTotalPrice": [{"priceType": "recurring", "price": {"taxIncludedAmount": {"unit": "GBP", "value": float(o["price_gbp"])}}}]}
        q("insert into sor.quote values(%s,%s,%s)", res["id"], J(res), res["state"])
        return res
    return idem(idempotency_key, "POST", "quote", mk)[0]

# ---- Product order (TMF622 – Salesforce-certified)
@app.post(ORD + "/productOrder", status_code=201)
async def create_order(request: Request, idempotency_key: str | None = Header(None)):
    body = await request.json()
    created = {}
    def mk():
        oid = "PO-ORD-" + uuid.uuid4().hex[:8]
        res = {**body, "id": oid, "href": f"{ORD}/productOrder/{oid}", "@type": "ProductOrder", "state": "acknowledged",
               "orderDate": now(), "creationDate": now()}
        q("insert into sor.product_order(id, body, state) values(%s,%s,%s)", oid, J(res), res["state"])
        created["new"] = res
        return res
    res, replay = idem(idempotency_key, "POST", "productOrder", mk)
    if not replay:
        await apublish("ProductOrderCreateEvent", {"productOrder": {"id": res["id"], "state": res["state"]}}, SVC, RUN_ID.get())
    return {**res, **({"_idempotentReplay": True} if replay else {})}

@app.get(ORD + "/productOrder/{oid}")
def get_order(oid: str):
    r = q1("select body from sor.product_order where id=%s", oid)
    if not r:
        raise HTTPException(404)
    return r["body"]

@app.get(ORD + "/productOrder")
def list_orders(externalId: str | None = None):
    rows = q("select body from sor.product_order where (%s::text is null or body->>'externalId'=%s) order by created_at", externalId, externalId)
    return [r["body"] for r in rows]

@app.patch(ORD + "/productOrder/{oid}")
async def patch_order(oid: str, request: Request):
    patch = await request.json()
    r = q1("select body from sor.product_order where id=%s", oid)
    if not r:
        raise HTTPException(404)
    b = {**r["body"], **patch, "lastUpdate": now()}
    q("update sor.product_order set body=%s, state=%s, updated_at=now() where id=%s", J(b), b.get("state"), oid)
    if patch.get("state") and patch["state"] != r["body"].get("state"):
        await apublish("ProductOrderStateChangeEvent", {"productOrder": {"id": oid, "state": b["state"]}}, SVC, RUN_ID.get())
    return b

@app.post(ORD + "/cancelProductOrder", status_code=201)
async def cancel_order(request: Request, idempotency_key: str | None = Header(None)):
    body = await request.json()
    oid = body["productOrder"]["id"]
    def mk():
        r = q1("select body from sor.product_order where id=%s", oid)
        if not r:
            raise HTTPException(404)
        b = {**r["body"], "state": "cancelled", "cancellationReason": body.get("cancellationReason"), "lastUpdate": now()}
        q("update sor.product_order set body=%s, state='cancelled', updated_at=now() where id=%s", J(b), oid)
        return {"id": "CPO-" + uuid.uuid4().hex[:8], "@type": "CancelProductOrder", "state": "done",
                "productOrder": {"id": oid}, "cancellationReason": body.get("cancellationReason"), "effectiveCancellationDate": now()}
    res, replay = idem(idempotency_key, "POST", "cancelProductOrder", mk)
    if not replay:
        await apublish("CancelProductOrderStateChangeEvent", {"cancelProductOrder": res}, SVC, RUN_ID.get())
    return res

# ---- Product inventory (TMF637)
@app.get(INV + "/product")
def products(customerId: str | None = None):
    rows = q("select i.*, o.name from sor.product_inventory i join sor.product_offering o on o.id=i.offering_id where (%s::text is null or customer_id=%s) order by start_date", customerId, customerId)
    return [{"id": r["id"], "@type": "Product", "name": r["name"], "status": r["status"], "productOffering": {"id": r["offering_id"]},
             "relatedParty": [{"id": r["customer_id"], "role": "customer"}], "startDate": str(r["start_date"])} for r in rows]

@app.post(INV + "/product", status_code=201)
async def create_product(request: Request, idempotency_key: str | None = Header(None)):
    body = await request.json()
    def mk():
        pid = "PI-" + uuid.uuid4().hex[:8]
        cid = body["relatedParty"][0]["id"]
        q("update sor.product_inventory set status='terminated' where customer_id=%s and status='active'", cid)
        q("insert into sor.product_inventory(id,customer_id,offering_id,status) values(%s,%s,%s,'active')", pid, cid, body["productOffering"]["id"])
        return {"id": pid, "@type": "Product", "status": "active", **body}
    return idem(idempotency_key, "POST", "product", mk)[0]
