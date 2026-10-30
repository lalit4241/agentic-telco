"""AgenticTelco MVP · L4 Enterprise Context: builds one context pack per request (each fact tagged with its source) and runs the
ADVISORY policy check. Read-only: it reads Salesforce only through TM Forum Open APIs (Salesforce's own and the TMF facade within
Salesforce), and the legacy stand-ins through their adapters. Identity comes from the L3 cross-reference (matching in L3, meaning in L4)."""
import json, time
from urllib.parse import quote
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path
import httpx, jsonschema, yaml
from fastapi import FastAPI, HTTPException, Request
from stack.mvp.common import (sf_id, q, q1, J, Span, sf, tmf_ok, APEX, CC, OPA_URL, url, traceparent, parse_traceparent,
                              brightwell, copy_json, init_schema)

app = FastAPI(title="AgenticTelco MVP L4 context service")
HERE = Path(__file__).parent

def semantic_model():
    m = yaml.safe_load((HERE / "semantic" / "model.yaml").read_text())
    jsonschema.validate(m, json.loads((HERE / "semantic" / "model.schema.json").read_text()))
    return m

SEM = semantic_model()

def seed_xref():
    """Deterministic, maintained cross-reference for the example customer (each link with its source)."""
    b = brightwell()
    rows = [("brightwell", "salesforceAccount", b["accountId"], "Salesforce Account (seed/customers/seed_brightwell.py)"),
            ("brightwell", "billingCustomer", b["billingAccount"], "Billing B customer master (merger mapping file)"),
            ("brightwell", "inventorySite", b["site"], "Network inventory site register"),
            ("brightwell", "addressKey", b["addressKey"], "Salesforce Location.ExternalReference")]
    for s, sys_, ext, src in rows:
        q("""insert into mvp.identity_xref(subject, system, external_id, source, verified) values (%s,%s,%s,%s,true)
             on conflict (subject, system) do update set external_id=excluded.external_id, source=excluded.source""", s, sys_, ext, src)

@app.on_event("startup")
def _start():
    init_schema()
    seed_xref()

@app.get("/health")
def health():
    return {"ok": True, "service": "mvp-context", "semanticModel": SEM["version"], "terms": len(SEM["terms"])}

@app.get("/semantic")
def semantic():
    return {"model": SEM, "glossary": copy_json().get("glossary", [])}

def resolve_identity(account_id):
    sub = q1("select subject from mvp.identity_xref where system='salesforceAccount' and external_id=%s", account_id)
    if not sub:
        return None
    rows = q("select system, external_id, source, verified from mvp.identity_xref where subject=%s", sub["subject"])
    return {"subject": sub["subject"], "links": {r["system"]: r for r in rows},
            "verified": all(r["verified"] for r in rows) and {"billingCustomer", "inventorySite", "addressKey"} <= {r["system"] for r in rows}}

_offers = {"t": 0, "v": None}
def offerings(trace):
    # no cache: every run reads the catalogue, so each trace shows where the offer came from
    r = sf(trace, "Catalogue and prices", "GET", f"{APEX}/tmf620/productOffering?isBundle=true", api="TMF620")
    out = []
    for o in r.json() or []:
        speed = next((int(v["value"]) for c in o.get("prodSpecCharValueUse") or [] if c.get("x-code") == "AT_ATT_DL_SPEED"
                      for v in c.get("productSpecCharacteristicValue") or [] if v.get("isDefault")), None)
        prices = {p.get("x-sellingModel"): p for p in o.get("productOfferingPrice") or []}
        term = prices.get("AgenticTelco Term Monthly") or {}
        ever = prices.get("Evergreen - Monthly") or {}
        out.append({"id": o["id"], "code": o.get("code"), "name": o["name"], "downloadSpeedMbps": speed,
                    "monthlyPriceGBP": (term.get("price") or {}).get("value"), "priceId": term.get("id"),
                    "evergreenPriceGBP": (ever.get("price") or {}).get("value"), "src": "salesforce:TMF620 Product Catalog"})
    out.sort(key=lambda x: x["downloadSpeedMbps"] or 0)
    _offers.update(t=time.time(), v=out)
    return out

_promos = {"t": 0, "v": None}
def promotions(trace):
    """TMF671 read: promotions in the org. Only AgenticTelco business promotions could apply to this upgrade (none today),
    so Fibre 900 stays at its list price of £45 a month."""
    if True:   # no cache: every run's trace shows the TMF671 read
        r = sf(trace, "Promotions", "GET", f"{APEX}/tmf671/promotion", api="TMF671")
        _promos.update(t=time.time(), v=r.json() if r.status_code == 200 else [])
    active = [p for p in _promos["v"] if p.get("lifecycleStatus") == "active"]
    return {"activeInOrg": len(active), "applicable": [p["name"] for p in active if (p.get("name") or "").startswith("AgenticTelco Business")],
            "src": "salesforce:TMF671 Promotion"}

def months_between(d0, d1):
    return max(0, (d1.year - d0.year) * 12 + d1.month - d0.month - (1 if d1.day < d0.day else 0))

def opa(trace, mode, ctx, to, parent=None, component="L4 context service"):
    inp = {"mode": mode, "context": ctx, "proposal": {"to": to}}
    layer = "L4" if mode == "advisory" else "L5"
    with Span(trace, layer, component, f"Policy check ({mode})", runtime="OPA (Rego) · agentictelco.upgrade", api="OPA", method="POST",
              path="/v1/data/agentictelco/upgrade/decision", parent=parent, request={"mode": mode, "proposal": {"to": to}}) as sp:
        r = httpx.post(f"{OPA_URL}/v1/data/agentictelco/upgrade/decision", json={"input": inp}, timeout=10)
        d = r.json().get("result")
        sp.status, sp.response = r.status_code, d
        sp.attrs.update(allow=d["allow"], deny=d["deny"], policyVersion=d["policyVersion"])
    q("insert into mvp.decision(trace_id, mode, policy_version, input, result) values (%s,%s,%s,%s,%s)", trace, mode, d["policyVersion"], J(inp), J(d))
    return d

def ids_or_400(**ids):
    """Check every Salesforce ID before it goes into a TMF API path or filter; reject anything else with 400."""
    try:
        return [sf_id(v, k) for k, v in ids.items()]
    except ValueError as e:
        raise HTTPException(400, str(e))


AUTH_ROLE = SEM["terms"]["authorisedContact"]["rule"].split('"')[1]   # the authorised role comes from semantic/model.yaml, not code


def build_pack(trace, contact_id, account_id, parent=None):
    contact_id, account_id = ids_or_400(contactId=contact_id, accountId=account_id)
    def hdr():
        return {"traceparent": traceparent(trace, parent or "0" * 16)}
    ident = resolve_identity(account_id)
    with Span(trace, "L3", "Postgres identity_xref", "Resolve the same customer across systems", runtime="ours (Postgres)", api="SQL",
              parent=parent) as sp:
        sp.status, sp.response = (200 if ident else 404), ident
    if not ident:
        raise HTTPException(409, "identity not in the cross-reference: stop for human review")
    L = ident["links"]
    jobs = {
        "org": lambda: tmf_ok(sf(trace, "Organization and contact roles", "GET", f"{APEX}/tmf632/organization/{account_id}", api="TMF632"), "TMF632"),
        "customer": lambda: sf(trace, "Customer", "GET", f"{CC}/customermanagement/v4/customer/{account_id}", api="TMF629").json(),
        "products": lambda: tmf_ok(sf(trace, "Installed service, site and contract end", "GET",
                                      f"{APEX}/tmf637/product?relatedParty.id={account_id}&status=active&limit=1", api="TMF637"), "TMF637"),
        "offers": lambda: offerings(trace),
        "promos": lambda: promotions(trace),
        "billing": lambda: httpx.get(f"{url('standins')}/tmf-api/accountManagement/v4/billingAccount/{L['billingCustomer']['external_id']}",
                                     headers=hdr(), timeout=20).json(),
        "avail": lambda: httpx.get(f"{url('standins')}/tmf-api/productOfferingQualification/v5/availability/{L['addressKey']['external_id']}",
                                   headers=hdr(), timeout=20).json(),
    }
    with ThreadPoolExecutor(len(jobs)) as ex:
        fut = {k: ex.submit(f) for k, f in jobs.items()}
        res = {k: f.result() for k, f in fut.items()}
    prod = (res["products"] or [None])[0]
    if prod:   # Salesforce's own TMF637 resource for the same installed product (serial number)
        inv = sf(trace, "Installed service (Salesforce TMF637)", "GET", f"{CC}/productinventorymanagement/v5/productinventory/{prod['id']}", api="TMF637").json()
    me = next((p for p in (res["org"] or {}).get("relatedParty", []) if p.get("id") == contact_id), {})
    role = me.get("role")
    place = ((prod or {}).get("place") or [{}])[0]
    adr = place.get("geographicAddress") or {}
    asset = prod and {"Id": prod["id"], "Product2Id": (prod.get("productOffering") or {}).get("id"), "UsageEndDate": prod.get("terminationDate"),
                      "Price": (((prod.get("productPrice") or [{}])[0].get("price") or {}).get("taxIncludedAmount") or {}).get("value"),
                      "LocationId": place.get("id")}
    offers = res["offers"]
    cur = next((o for o in offers if asset and o["id"] == asset["Product2Id"]), None)
    end = date.fromisoformat(asset["UsageEndDate"]) if asset and asset.get("UsageEndDate") else None
    bal = {b["balanceType"]: b["amount"]["value"] for b in res["billing"].get("accountBalance", [])}
    pack = {
        "requester": {"name": me.get("x-givenName") or me.get("name"), "fullName": me.get("name"),
                      "contactId": contact_id, "authorisedContact": role == AUTH_ROLE, "role": role,
                      "src": "salesforce:TMF632 Party (contact role)"},
        "customer": {"name": (res["customer"] or {}).get("name", "").replace("AgenticTelco – ", ""), "salesforceAccount": account_id, "src": "salesforce:TMF629 Customer"},
        "identity": {"salesforceAccount": account_id, "billingCustomer": L["billingCustomer"]["external_id"], "inventorySite": L["inventorySite"]["external_id"],
                     "verified": ident["verified"], "src": "L3 identity_xref (verified)"},
        "site": {"addressKey": ((place.get("externalIdentifier") or [{}])[0]).get("id"), "name": place.get("name"), "street": adr.get("streetName"),
                 "city": adr.get("city"), "postcode": adr.get("postcode"), "locationId": place.get("id"), "src": "salesforce:TMF637 Product Inventory (place)"},
        "currentBroadband": {"product": (cur or {}).get("name"), "productId": (cur or {}).get("id"), "assetId": (asset or {}).get("Id"),
                             "downloadSpeedMbps": (cur or {}).get("downloadSpeedMbps"), "monthlyPriceGBP": (asset or {}).get("Price"),
                             "serialNumber": (inv or {}).get("productSerialNumber") if asset else None, "src": "salesforce:TMF637 Product Inventory"},
        "contractMonthsLeft": {"value": months_between(date.today(), end) if end else 0, "contractEnd": str(end) if end else None,
                               "src": "salesforce:TMF637 Product Inventory (terminationDate as contract end)"},
        "availableAtSite": {"value": [x["name"] for x in res["avail"].get("qualifiedProductOffering", [])], "asOf": res["avail"].get("asOf"),
                            "src": "legacy stand-in: availability (TMF679 shape, refreshed overnight)"},
        "overdueBalance": {"value": (bal.get("overdue") or 0) > 0, "amountGBP": bal.get("overdue") or 0, "src": "legacy stand-in: Billing B (TMF666 shape)"},
        "promotions": res["promos"],
        "offerings": [{k: o[k] for k in ("id", "name", "downloadSpeedMbps", "monthlyPriceGBP", "evergreenPriceGBP", "priceId")} for o in offers],
    }
    return pack

@app.post("/context")
async def context(request: Request):
    """Body: {contactId, accountId}. Returns the context pack plus the advisory decision for each upgrade the site could take."""
    b = await request.json()
    trace, parent = parse_traceparent(request.headers.get("traceparent"))
    with Span(trace, "L4", "L4 context service", "Build the context pack", runtime="ours (Python, FastAPI)", api="REST", method="POST",
              path="/context", parent=parent, conversation_id=b.get("conversationId"), request=b) as sp:
        pack = build_pack(trace, b["contactId"], b["accountId"], parent=sp.span_id)
        cur = pack["currentBroadband"]["downloadSpeedMbps"] or 0
        candidates = [o for o in pack["offerings"] if (o["downloadSpeedMbps"] or 0) > cur]
        decisions = {o["id"]: opa(trace, "advisory", pack, o["id"], parent=sp.span_id) for o in candidates}
        allowed = [dict(o, decision=decisions[o["id"]]) for o in candidates if decisions[o["id"]]["allow"]]
        # Reasons that block every candidate are about the customer (authorisation, balance); the rest are per product.
        text = {d: r for x in decisions.values() for d, r in zip(x["deny"], x["reasons"])}
        sets = [set(x["deny"]) for x in decisions.values()]
        denied = sorted(set.intersection(*sets)) if sets else []
        out = {"contextPack": pack, "advisory": {"mode": "advisory", "allowedOffers": allowed, "deniedReasons": denied,
               "reasons": [text[d] for d in denied],
               "notOffered": {o["name"]: [text[d] for d in decisions[o["id"]]["deny"]] for o in candidates if not decisions[o["id"]]["allow"]},
               "perOffer": {o["name"]: decisions[o["id"]] for o in candidates}, "policyVersion": next(iter(decisions.values()))["policyVersion"] if decisions else None},
               "semanticModel": SEM["version"]}
        if "overdue_balance" in denied:
            with httpx.Client(timeout=10) as c:
                out["paymentLink"] = c.post(f"{url('standins')}/payment/link", json={"billingAccount": pack["identity"]["billingCustomer"]},
                                            headers={"traceparent": traceparent(trace, sp.span_id)}).json()
        if "not_authorised" in denied:
            org = tmf_ok(sf(trace, "Who can order for this business", "GET", f"{APEX}/tmf632/organization/{ids_or_400(accountId=b.get('accountId'))[0]}"
                            f"?relatedParty.role={quote(AUTH_ROLE)}", api="TMF632", parent=sp.span_id), "TMF632")
            dm = org.get("relatedParty") or []
            out["decisionMaker"] = (dm[0]["name"] if dm else None)
        sp.status, sp.response = 200, {"allowed": [o["name"] for o in allowed], "denied": denied}
        sp.attrs.update(allowed=[o["name"] for o in allowed], denied=denied)
    q("update mvp.conversation set state = state || %s where id=%s", J({"contextPack": pack}), b.get("conversationId"))
    return out

@app.post("/policy/binding")
async def binding(request: Request):
    """Used by the L5 workflow: rebuilds the pack (fresh data, not the agent's copy) and runs the same rule with mode=binding."""
    b = await request.json()
    trace, parent = parse_traceparent(request.headers.get("traceparent"))
    pack = build_pack(trace, b["contactId"], b["accountId"], parent=parent)
    d = opa(trace, "binding", pack, b["to"], parent=parent, component="L5 binding check")
    return {"decision": d, "contextPack": pack}

@app.post("/policy/authorised-contact")
async def authorised_contact(request: Request):
    """Used by the L1 intent service: same policy, only the authorised-contact outcome is read (no copy of the rule)."""
    b = await request.json()
    trace, parent = parse_traceparent(request.headers.get("traceparent"))
    contact_id, account_id = ids_or_400(contactId=b.get("contactId"), accountId=b.get("accountId"))
    r = sf(trace, "Contact role on the account", "GET", f"{APEX}/tmf632/organization/{account_id}", api="TMF632", parent=parent)
    org = r.json() if r.status_code == 200 else {}   # 404: not an AgenticTelco organization, so nobody there is authorised
    role = next((p.get("role") for p in org.get("relatedParty") or [] if p.get("id") == contact_id), None)
    ctx = {"requester": {"authorisedContact": role == AUTH_ROLE}}
    with Span(trace, "L1", "Intent service", "Policy check: authorised contact", runtime="OPA (Rego) · agentictelco.upgrade", api="OPA",
              method="POST", path="/v1/data/agentictelco/upgrade/deny", parent=parent) as sp:
        r = httpx.post(f"{OPA_URL}/v1/data/agentictelco/upgrade/deny", json={"input": {"mode": "intent-validation", "context": ctx, "proposal": {}}}, timeout=10)
        deny = r.json().get("result", [])
        sp.status, sp.response = r.status_code, {"authorisedContact": "not_authorised" not in deny}
    return {"authorisedContact": "not_authorised" not in deny}
