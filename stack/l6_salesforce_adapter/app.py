"""L6 · Real Salesforce Communications Cloud adapter (server-side only – no credential ever reaches the browser).

Exposes the SAME agent-facing /tmf-api paths as the stand-in, so L2/L4/L5 switch to the real org by pointing ZG_SOR_BASE
here (./run.sh up with ZG_SOR_MODE=commscloud). Every Salesforce call goes through stack/zg_common/sf_session.py, i.e. the
Salesforce CLI (`sf api request rest --target-org sfcomms`), which signs requests with its own stored session: this code never
reads, logs or returns a token. Order of preference for every API (ADR amendment 001):

  1. OOTB  – Comms Cloud Direct Access TMF API or standard sObject REST, exactly as the org exposes it.
  2. custom TMF API on Salesforce – AgenticTelco_* Apex REST at /services/apexrest/agentictelco/tmf<NNN>/..., used only
     where the org does not expose that TMF API (TMF620, TMF648, TMF671) or the native one is broken (TMF622 read path).
  3. our layer – a rule computed here, ONLY where neither works (TMF679: the org has no default qualification procedure).

Each response carries `x-zg-runtime` (what served it) and `x-zg-sf-calls` (the Salesforce calls behind it); the L8 ledger
records both. Agent-facing customer ids (C-1001..) map to AgenticTelco demo Accounts via the standard AccountNumber field.
Network serviceability (exchange, access technology) and marketing consent are NOT Salesforce data in this demo: they come
from the demo OSS/consent records and are labelled as such in the response (`x-zg-enrichment`).
"""
import asyncio, json, time, uuid, datetime
from urllib.parse import quote as urlq
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse
from stack.zg_common.telemetry import instrument_app, RUN_ID
from stack.zg_common.events import apublish
from stack.zg_common.db import q1
from stack.zg_common.sf_session import request as sf_request, API_V, ALIAS

SVC = "l6-salesforce-adapter"
app = FastAPI(title="AgenticTelco L6 Salesforce adapter (server-side, sf CLI session)")
instrument_app(app, SVC)
D = f"/services/data/{API_V}"
CC = f"{D}/connect/comms"
APEX = "/services/apexrest/agentictelco"
OOTB, CUSTOM, OURS = "OOTB", "custom TMF API on Salesforce", "our layer"
CAT = "/tmf-api/productCatalogManagement/v4"
POQ = "/tmf-api/productOfferingQualification/v4"
ORD = "/tmf-api/productOrderingManagement/v4"
INV = "/tmf-api/productInventory/v4"
QUO = "/tmf-api/quoteManagement/v4"
now = lambda: datetime.datetime.now(datetime.timezone.utc).isoformat()

# --------------------------------------------------------------------------------------------------------------- plumbing
class Trace:
    def __init__(self):
        self.calls = []
    async def sf(self, method, path, body=None, runtime=OOTB, ok=(200, 201, 204)):
        t0 = time.perf_counter()
        r = await asyncio.to_thread(sf_request, method, path, body)
        self.calls.append({"method": method, "path": path.split("?q=")[0] + ("?q=<SOQL>" if "?q=" in path else ""),
                           "status": r.status_code, "runtime": runtime, "ms": round((time.perf_counter() - t0) * 1000)})
        return r
    def respond(self, body, runtime, status=200, enrichment=None):
        h = {"x-zg-runtime": runtime, "x-zg-sf-calls": json.dumps(self.calls)[:7000], "x-zg-sf-org": ALIAS}
        if enrichment:
            h["x-zg-enrichment"] = enrichment
        return JSONResponse(body, status_code=status, headers=h)

def fail(tr, r, what):
    raise HTTPException(502 if r.status_code in (0, 500) else r.status_code, f"{what}: Salesforce returned {r.status_code}: {r.text[:300]}")

async def soql(tr, s):
    r = await tr.sf("GET", f"{D}/query?q=" + urlq(s))
    if r.status_code != 200:
        fail(tr, r, "SOQL")
    return r.json()["records"]

_cust = {}
async def account_for(tr, cid):
    """C-1001 → AgenticTelco demo Account/Contact (standard AccountNumber 'AT-C-1001'; seeded by seed/customers)."""
    if cid in _cust:
        return _cust[cid]
    if cid.startswith("001"):
        rows = await soql(tr, f"SELECT Id, AccountNumber, Name, (SELECT Id FROM Contacts ORDER BY CreatedDate LIMIT 1) FROM Account WHERE Id='{cid}' AND Name LIKE 'AgenticTelco%'")
    else:
        rows = await soql(tr, f"SELECT Id, AccountNumber, Name, (SELECT Id FROM Contacts ORDER BY CreatedDate LIMIT 1) FROM Account "
                              f"WHERE AccountNumber='AT-{cid.replace(chr(39), '')}' AND Name LIKE 'AgenticTelco%' LIMIT 1")
    if not rows:
        raise HTTPException(404, f"customer {cid} is not an AgenticTelco demo account in {ALIAS} – run seed/customers/seed_customers.py")
    a = rows[0]
    con = ((a.get("Contacts") or {}).get("records") or [{}])[0].get("Id")
    m = {"cid": (a.get("AccountNumber") or "")[3:] or cid, "accountId": a["Id"], "name": a["Name"], "contactId": con}
    _cust[cid] = _cust[m["cid"]] = _cust[a["Id"]] = m
    return m

def demo_network(cid):
    """Exchange + access technology at the address: network data (OSS/L3), deliberately not held in the SoR."""
    r = q1("select address from sor.customer where id=%s", cid)
    return (r or {}).get("address") or {}

def speed_of(o):
    for c in o.get("prodSpecCharValueUse") or []:
        if c.get("x-code") == "AT_ATT_DL_SPEED" or "Speed" in (c.get("name") or ""):
            vals = c.get("productSpecCharacteristicValue") or []
            v = next((x for x in vals if x.get("isDefault")), vals[0] if vals else None)
            if v:
                return int(v["value"])
    return None

TECH = {150: ["FTTC", "FTTP"], 1600: ["XGS-PON"]}   # adapter mapping (labelled): 150 runs on FTTC or FTTP; 500/900 need FTTP; 1600 needs XGS-PON

def to_agent_offer(o):
    sp = speed_of(o)
    prices = [p for p in o.get("productOfferingPrice") or [] if p.get("priceType") == "recurring"]
    term = next((p for p in prices if "Term" in (p.get("x-sellingModel") or "")), prices[0] if prices else None)
    pops = ([term] if term else []) + [p for p in prices if p is not term]
    return {**o, "href": f"{CAT}/productOffering/{o['id']}", "x-sfHref": o.get("href"),
            "productOfferingPrice": [{"id": p["id"], "name": p.get("name"), "priceType": "recurring", "recurringChargePeriod": "month",
                                      "x-sellingModel": p.get("x-sellingModel"),
                                      "price": {"taxIncludedAmount": {"unit": p["price"]["unit"], "value": float(p["price"]["value"])}}} for p in pops],
            "prodSpecCharValueUse": (o.get("prodSpecCharValueUse") or []) + [
                {"name": "downloadSpeedMbps", "productSpecCharacteristicValue": [{"value": sp}]},
                {"name": "requiredTechnology", "x-source": "adapter mapping (access technology is network data, not EPC)",
                 "productSpecCharacteristicValue": [{"value": t} for t in TECH.get(sp, ["FTTP"])]}]}

_offers = {"t": 0, "v": None}
async def offers(tr):
    if _offers["v"] is not None and time.time() - _offers["t"] < 120:
        tr.calls.append({"method": "GET", "path": f"{APEX}/tmf620/productOffering", "status": 200, "runtime": CUSTOM, "cached": True})
        return _offers["v"]
    r = await tr.sf("GET", f"{APEX}/tmf620/productOffering?isBundle=true", runtime=CUSTOM)
    if r.status_code != 200:
        fail(tr, r, "TMF620")
    v = [to_agent_offer(o) for o in r.json() if o.get("isBundle")]
    v.sort(key=lambda o: o["productOfferingPrice"][0]["price"]["taxIncludedAmount"]["value"] if o["productOfferingPrice"] else 0)
    _offers.update(t=time.time(), v=v)
    return v

# --------------------------------------------------------------------------------------------------------------- endpoints
@app.get("/health")
def health():
    return {"ok": True, "service": SVC, "org": ALIAS, "apiVersion": API_V, "role": "real Salesforce Comms Cloud SoR adapter"}

# TMF629 / TMF632 – OOTB Direct Access
@app.get("/tmf-api/customerManagement/v4/customer/{cid}")
async def customer(cid: str):
    tr = Trace()
    m = await account_for(tr, cid)
    r = await tr.sf("GET", f"{CC}/customermanagement/v4/customer/{m['accountId']}")
    if r.status_code != 200:
        fail(tr, r, "TMF629")
    c = r.json()
    r2 = await tr.sf("GET", f"{CC}/partymanagement/v5/organization/{m['accountId']}")
    org = r2.json() if r2.status_code == 200 else {}
    adr = next((x for x in org.get("contactMedium") or [] if x.get("@type") == "GeographicAddressContactMedium"), {})
    net = demo_network(m["cid"])
    body = {"id": m["cid"], "@type": "Customer", "name": c.get("name", m["name"]).replace("AgenticTelco Demo – ", ""), "status": "Active",
            "x-sfId": m["accountId"], "x-sfName": c.get("name"), "engagedParty": {**(c.get("engagedParty") or {}), "@referredType": "Individual"},
            "contactMedium": [{"mediumType": "postalAddress", "characteristic": {
                "line": adr.get("street1"), "city": adr.get("city"), "postcode": adr.get("postCode"), "country": adr.get("country"),
                "exchange": net.get("exchange"), "technology": net.get("technology", []),
                "x-source": "address: Salesforce TMF632 organization (OOTB); exchange + technology: demo OSS serviceability data"}}]
                            + (c.get("contactMedium") or []),
            "characteristic": [{"name": "sfAccountName", "value": c.get("name")}]}
    return tr.respond(body, OOTB, enrichment="exchange,technology from demo OSS serviceability data")

@app.get("/tmf-api/partyManagement/v4/individual/{pid}")
async def individual(pid: str):
    tr = Trace()
    r = await tr.sf("GET", f"{CC}/partymanagement/v5/individual/{pid}")
    if r.status_code != 200:
        fail(tr, r, "TMF632")
    p = r.json()
    acc = next((x["partyOrPartyRole"]["id"] for x in p.get("relatedParty") or [] if x.get("partyOrPartyRole", {}).get("@referredType") == "Organization"), None)
    cid = (await account_for(tr, acc))["cid"] if acc else None
    cons = q1("select p.consent from sor.party p join sor.customer c on c.party_id=p.id where c.id=%s", cid) if cid else None
    p["partyCharacteristic"] = (p.get("partyCharacteristic") or []) + [
        {"name": "marketingConsent", "valueType": "object", "value": ((cons or {}).get("consent") or {}).get("marketing") or {"granted": False},
         "x-source": "demo consent store (Contact consent fields are not readable by this integration user)"}]
    return tr.respond(p, OOTB, enrichment="marketingConsent from demo consent store")

# TMF620 – custom TMF API on Salesforce (org exposes PCM Connect APIs only, no TMF620)
@app.get(CAT + "/productOffering")
async def list_offerings():
    tr = Trace()
    return tr.respond(await offers(tr), CUSTOM, enrichment="requiredTechnology: adapter mapping")

@app.get(CAT + "/productOffering/{oid}")
async def get_offering(oid: str):
    tr = Trace()
    o = next((x for x in await offers(tr) if x["id"] == oid), None)
    if not o:
        raise HTTPException(404, f"productOffering {oid} not in the AgenticTelco catalogue")
    return tr.respond(o, CUSTOM)

# TMF679 – OOTB first; the org has no default qualification procedure, so the adapter applies the product-configuration rule
@app.post(POQ + "/checkProductOfferingQualification")
async def check_poq(request: Request):
    body = await request.json()
    tr = Trace()
    cid = (body.get("relatedParty") or [{}])[0].get("id")
    m = await account_for(tr, cid)
    items = body.get("checkProductOfferingQualificationItem") or []
    native = {"relatedParty": [{"role": "Customer", "@type": "RelatedPartyRefOrPartyRoleRef", "partyOrPartyRole": {
                  "id": m["accountId"], "name": m["name"], "@type": "PartyRef", "@referredType": "AccountRef"}}],
              "provideResultReason": True, "@type": "CheckProductOfferingQualification",
              "checkProductOfferingQualificationItem": [{"@type": "CheckProductOfferingQualificationItem",
                                                         "productOffering": {"id": i["productOffering"]["id"], "@type": "ProductOfferingRef"}} for i in items]}
    r = await tr.sf("POST", f"{CC}/productofferingqualification/v5/checkProductOfferingQualification", native)
    if r.status_code in (200, 201):
        res = r.json(); res["x-runtime"] = OOTB
        return tr.respond(res, OOTB)
    reason = (r.json() or [{}])[0].get("message") if isinstance(r.json(), list) else r.text[:200]
    avail = demo_network(m["cid"]).get("technology", [])
    allo = {o["id"]: o for o in await offers(tr)}
    out = []
    for it in items:
        o = allo.get(it["productOffering"]["id"])
        reqs = [v["value"] for c in (o or {}).get("prodSpecCharValueUse", []) if c["name"] == "requiredTechnology" for v in c["productSpecCharacteristicValue"]]
        ok = bool(o) and bool(set(reqs) & set(avail))
        out.append({"id": it.get("id", "1"), "productOffering": it["productOffering"], "state": "done",
                    "qualificationItemResult": "qualified" if ok else "unqualified",
                    "eligibilityUnavailabilityReason": [] if ok else [{"code": "TECH_UNAVAILABLE", "label": f"Requires {reqs or '?'}; address has {avail}"}]})
    res = {"id": "POQ-" + uuid.uuid4().hex[:8], "@type": "CheckProductOfferingQualification", "state": "done",
           "qualificationResult": "qualified" if out and all(i["qualificationItemResult"] == "qualified" for i in out) else "unqualified",
           "effectiveQualificationDate": now(), "relatedParty": body.get("relatedParty"), "checkProductOfferingQualificationItem": out,
           "x-runtime": OURS, "x-nativeAttempt": {"status": r.status_code, "message": reason},
           "x-note": "Native TMF679 was called first; the org has no default qualification procedure configured (org setup left unchanged), "
                     "so the adapter applied the offer-technology vs address-technology rule."}
    return tr.respond(res, f"{OURS} (native TMF679 tried: {r.status_code})")

# TMF648 – custom TMF API on Salesforce (Quote + QuoteLineItem)
@app.post(QUO + "/quote", status_code=201)
async def quote(request: Request, idempotency_key: str | None = Header(None)):
    body = await request.json()
    tr = Trace()
    m = await account_for(tr, (body.get("relatedParty") or [{}])[0].get("id"))
    ext = (idempotency_key or RUN_ID.get() or uuid.uuid4().hex[:10]).replace(":quote", "")
    sfb = {"externalId": ext, "description": "AgenticTelco agent draft quote",
           "relatedParty": [{"id": m["accountId"], "role": "Customer"}],
           "quoteItem": [{"id": i.get("id", "1"), "action": "add", "quantity": 1, "productOffering": {"id": i["productOffering"]["id"]},
                          "product": {"productCharacteristic": [{"name": "AgenticTelco Contract Term", "value": "24"}]}} for i in body.get("quoteItem") or []]}
    r = await tr.sf("POST", f"{APEX}/tmf648/quote", sfb, runtime=CUSTOM)
    if r.status_code not in (200, 201):
        fail(tr, r, "TMF648")
    res = r.json()
    res["relatedParty"] = body.get("relatedParty")
    return tr.respond(res, CUSTOM, status=201 if r.status_code == 201 else 200)

# TMF622 – custom TMF API on Salesforce (native v5 read path fails in this org: GraphQL PoNumber/OrderReferenceNumber errors)
async def _order_events(res, created):
    if created:
        await apublish("ProductOrderCreateEvent", {"productOrder": {"id": res["id"], "state": res["state"]}, "x-source": "L6 adapter after the Salesforce write"}, SVC, RUN_ID.get())

@app.post(ORD + "/productOrder", status_code=201)
async def create_order(request: Request, idempotency_key: str | None = Header(None)):
    body = await request.json()
    tr = Trace()
    m = await account_for(tr, (body.get("relatedParty") or [{}])[0].get("id"))
    items = []
    for it in body.get("productOrderItem") or []:
        items.append({"id": it.get("id", "1"), "action": "add", "quantity": 1, "productOffering": {"id": it["productOffering"]["id"]},
                      "product": {"productCharacteristic": [{"name": "AgenticTelco Contract Term", "value": "24"}]}})
    sfb = {"externalId": body.get("externalId") or idempotency_key, "description": f"L5 saga {body.get('externalId')} (agent intent)",
           "relatedParty": [{"id": m["accountId"], "role": "Customer"}], "productOrderItem": items}
    r = await tr.sf("POST", f"{APEX}/tmf622/productOrder", sfb, runtime=CUSTOM)
    if r.status_code not in (200, 201):
        fail(tr, r, "TMF622")
    res = r.json()
    replay = r.status_code == 200
    res.update({"href": f"{ORD}/productOrder/{res['id']}", "x-sfHref": res.get("href"), "relatedParty": body.get("relatedParty"),
                **({"_idempotentReplay": True} if replay else {})})
    await _order_events(res, not replay)
    return tr.respond(res, CUSTOM, status=200 if replay else 201)

@app.get(ORD + "/productOrder/{oid}")
async def get_order(oid: str):
    tr = Trace()
    r = await tr.sf("GET", f"{APEX}/tmf622/productOrder/{oid}", runtime=CUSTOM)
    if r.status_code != 200:
        fail(tr, r, "TMF622")
    return tr.respond(r.json(), CUSTOM)

@app.get(ORD + "/productOrder")
async def list_orders(externalId: str | None = None):
    tr = Trace()
    r = await tr.sf("GET", f"{APEX}/tmf622/productOrder?limit=200", runtime=CUSTOM)
    if r.status_code != 200:
        fail(tr, r, "TMF622")
    rows = [o for o in r.json() if not externalId or o.get("externalId") == externalId]
    return tr.respond(rows, CUSTOM)

async def _patch_state(tr, oid, state):
    r = await tr.sf("PATCH", f"{APEX}/tmf622/productOrder/{oid}", {"state": state}, runtime=CUSTOM)
    if r.status_code != 200:
        fail(tr, r, "TMF622 PATCH")
    return r.json()

@app.patch(ORD + "/productOrder/{oid}")
async def patch_order(oid: str, request: Request):
    patch = await request.json()
    tr = Trace()
    res = await _patch_state(tr, oid, patch.get("state"))
    await apublish("ProductOrderStateChangeEvent", {"productOrder": {"id": oid, "state": res.get("state")}, "x-source": "L6 adapter after the Salesforce write"}, SVC, RUN_ID.get())
    return tr.respond(res, CUSTOM)

@app.post(ORD + "/cancelProductOrder", status_code=201)
async def cancel_order(request: Request):
    body = await request.json()
    tr = Trace()
    oid = body["productOrder"]["id"]
    o = await _patch_state(tr, oid, "cancelled")        # idempotent on the Apex side
    res = {"id": "CPO-" + oid, "@type": "CancelProductOrder", "state": "done", "productOrder": {"id": oid, "state": o.get("state"), "x-sfStatus": o.get("x-sfStatus")},
           "cancellationReason": body.get("cancellationReason"), "effectiveCancellationDate": now()}
    await apublish("CancelProductOrderStateChangeEvent", {"cancelProductOrder": res, "x-source": "L6 adapter after the Salesforce write"}, SVC, RUN_ID.get())
    return tr.respond(res, CUSTOM, status=201)

# TMF637 – OOTB: native v5 productinventory is read-only (GET/HEAD) → create the Asset with OOTB sObject REST, read it via TMF637
def _inv(p, cid):
    return {"id": p["id"], "@type": "Product", "name": (p.get("productOffering") or {}).get("name") or p.get("name"), "status": "active",
            "productOffering": {"id": (p.get("productOffering") or {}).get("id")}, "relatedParty": [{"id": cid, "role": "customer"}],
            "startDate": p.get("startDate") or p.get("orderDate"), "productSerialNumber": p.get("productSerialNumber"), "x-sfHref": p.get("href")}

@app.get(INV + "/product")
async def products(customerId: str | None = None):
    tr = Trace()
    m = await account_for(tr, customerId)
    rows = await soql(tr, f"SELECT Id FROM Asset WHERE AccountId='{m['accountId']}' AND Name LIKE 'AgenticTelco%' AND Status='Installed' ORDER BY CreatedDate DESC")
    out = []
    for a in rows:
        r = await tr.sf("GET", f"{CC}/productinventorymanagement/v5/productinventory/{a['Id']}")
        if r.status_code == 200:
            out.append(_inv(r.json(), m["cid"]))
    return tr.respond(out, OOTB)

@app.post(INV + "/product", status_code=201)
async def create_product(request: Request, idempotency_key: str | None = Header(None)):
    body = await request.json()
    tr = Trace()
    m = await account_for(tr, body["relatedParty"][0]["id"])
    key = (idempotency_key or uuid.uuid4().hex)[:60].replace("'", "")
    ex = await soql(tr, f"SELECT Id FROM Asset WHERE SerialNumber='AT-{key}' AND Name LIKE 'AgenticTelco%' LIMIT 1")
    if ex:
        aid, replay = ex[0]["Id"], True
    else:
        off = next((o for o in await offers(tr) if o["id"] == body["productOffering"]["id"]), {"name": "AgenticTelco product"})
        prev = await soql(tr, f"SELECT Id FROM Asset WHERE AccountId='{m['accountId']}' AND Name LIKE 'AgenticTelco%' AND Status='Installed'")
        r = await tr.sf("POST", f"{D}/sobjects/Asset", {"Name": f"{off['name']} – {m['cid']}", "AccountId": m["accountId"], "ContactId": m["contactId"],
                         "Product2Id": body["productOffering"]["id"], "Status": "Installed", "Quantity": 1, "SerialNumber": f"AT-{key}",
                         "Description": f"AgenticTelco demo inventory from order {(body.get('productOrderItem') or [{}])[0].get('productOrderId')}"})
        if r.status_code != 201:
            fail(tr, r, "Asset create")
        aid, replay = r.json()["id"], False
        for p in prev:   # the replaced line becomes Obsolete (AgenticTelco demo records only)
            await tr.sf("PATCH", f"{D}/sobjects/Asset/{p['Id']}", {"Status": "Obsolete"})
    r = await tr.sf("GET", f"{CC}/productinventorymanagement/v5/productinventory/{aid}")
    res = _inv(r.json(), m["cid"]) if r.status_code == 200 else {"id": aid, "@type": "Product", "status": "active"}
    return tr.respond({**res, **({"_idempotentReplay": True} if replay else {})}, OOTB, status=200 if replay else 201)
