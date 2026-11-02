"""AgenticTelco MVP · L5 Operaton external-task workers (deterministic: no model is called from here).

Every system-of-record write happens here, after the binding policy check. Idempotency: the order external ID is the business key;
Salesforce facades are idempotent on externalId, Assets on SerialNumber AT-<key>, and each step's result is kept in mvp.step_result,
so a rerun after a crash replays instead of writing twice."""
import json, os, sys, time, traceback
from datetime import date, datetime, timezone
import httpx
from stack.mvp.common import (sf_id, safe_key, q, q1, J, Span, sf, APEX, url, traceparent, init_schema, OPERATON_URL, tmf)
from stack.l5_orchestrator.engine import creds

WORKER_ID = f"mvp-l5-worker-{os.getpid()}"
LOCK_MS = 120000
STEP_NAMES = {
    "mvp-binding-check": "Binding policy check + identity", "mvp-quote": "Create quote", "mvp-order": "Place upgrade order",
    "mvp-oss-submit": "Salesforce order orchestration: plan and network service order",
    "mvp-oss-read": "Salesforce order orchestration: wait for network activation", "mvp-jeopardy": "Raise jeopardy (+2 days)",
    "mvp-activate": "Complete order", "mvp-asset-change": "Check the installed product", "mvp-intent-fulfilled": "Intent fulfilled",
}

class BpmnErr(Exception):
    def __init__(self, code, msg):
        super().__init__(msg)
        self.code, self.msg = code, msg

def ok(r, what):
    if r.status_code >= 400 or r.status_code == 0:
        raise RuntimeError(f"{what} → {r.status_code} {r.text[:300]}")
    return r.json()

def remembered(key, step, fn):
    """Business-key idempotency for steps whose side effects are not naturally idempotent."""
    r = q1("select result from mvp.step_result where business_key=%s and step=%s", key, step)
    if r:
        return {**r["result"], "_replay": True}
    out = fn()
    q("insert into mvp.step_result(business_key, step, result) values (%s,%s,%s) on conflict do nothing", key, step, J(out))
    return out

def milestone(ext, name, body):
    q("insert into mvp.milestone(order_ext, name, body) values (%s,%s,%s)", ext, name, J(body))

def report(v, span, state, name, detail):
    r = httpx.post(f"{url('intent')}/tmf-api/intentManagement/v5/intent/{v['intentId']}/intentReport",
                   json={"state": state, "name": name, "detail": detail}, headers={"traceparent": traceparent(v["traceId"], span.span_id)}, timeout=30)
    if r.status_code != 201:
        raise RuntimeError(f"IntentReport → {r.status_code} {r.text[:200]}")
    return r.json()

# ------------------------------------------------------------------------------------------------------------ handlers
def binding_check(v, sp):
    links = q("select system, verified from mvp.identity_xref where subject=(select subject from mvp.identity_xref where system='salesforceAccount' and external_id=%s)",
              v["accountId"])
    have = {r["system"] for r in links if r["verified"]}
    if not {"salesforceAccount", "billingCustomer", "inventorySite", "addressKey"} <= have:
        raise BpmnErr("IDENTITY_REVIEW", "Identity cross-reference incomplete or unverified: raised for human review")
    r = httpx.post(f"{url('context')}/policy/binding", json={"contactId": v["contactId"], "accountId": v["accountId"], "to": v["toOffering"]},
                   headers={"traceparent": traceparent(v["traceId"], sp.span_id)}, timeout=120).json()
    d, pack = r["decision"], r["contextPack"]
    sp.attrs.update(allow=d["allow"], deny=d["deny"], policyVersion=d["policyVersion"])
    if not d["allow"]:
        raise BpmnErr("POLICY_BLOCKED", "Binding policy denied: " + ", ".join(d["deny"]))
    to = next(o for o in pack["offerings"] if o["id"] == v["toOffering"])
    return {"currentAssetId": pack["currentBroadband"]["assetId"], "locationId": pack["site"]["locationId"], "toName": to["name"],
            "toPriceId": to["priceId"], "toPrice": str(to["monthlyPriceGBP"]), "toSpeed": str(to["downloadSpeedMbps"]),
            "contractEnd": pack["contractMonthsLeft"]["contractEnd"], "monthsLeft": str(pack["contractMonthsLeft"]["value"]),
            "site": pack["identity"]["inventorySite"]}

def term_item(v):
    return {"productCharacteristic": [{"name": "AgenticTelco Contract Term", "value": v.get("monthsLeft") or "12"}]}

def quote(v, sp):
    body = {"externalId": v["orderExternalId"] + "-Q", "description": f"AgenticTelco MVP upgrade quote for intent {v['intentId']}",
            "relatedParty": [{"id": v["accountId"], "role": "Customer"}],
            "quoteItem": [{"id": "1", "action": "add", "quantity": 1, "productOffering": {"id": v["toOffering"]},
                           "productOfferingPrice": {"id": v["toPriceId"]}, "product": term_item(v)}]}
    r = ok(sf(v["traceId"], "Create quote", "POST", f"{APEX}/tmf648/quote", body, api="TMF648", parent=sp.span_id), "TMF648")
    milestone(v["orderExternalId"], "QuoteCreated", {"quoteId": r["id"]})
    return {"quoteId": r["id"]}

def order(v, sp):
    # The upgrade as two linked TMF622 items: delete the installed Fibre 150 and add Fibre 900, which 'replaces' item 1.
    # The new line keeps the running contract end date; its monthly price applies from the upgrade date.
    body = {"externalId": v["orderExternalId"], "description": f"Upgrade Fibre 150 to {v['toName']} (intent {v['intentId']})",
            "relatedParty": [{"id": v["accountId"], "role": "Customer"}], "quote": [{"id": v.get("quoteId")}],
            "productOrderItem": [
                {"id": "1", "action": "delete", "quantity": 1, "product": {"id": v["currentAssetId"]}},
                {"id": "2", "action": "add", "quantity": 1, "productOffering": {"id": v["toOffering"]},
                 "productOfferingPrice": {"id": v["toPriceId"]}, "product": term_item(v),
                 "productOrderItemRelationship": [{"id": "1", "relationshipType": "replaces"}]}]}
    o = ok(sf(v["traceId"], "Place upgrade order (delete Fibre 150, add Fibre 900)", "POST", f"{APEX}/tmf622/productOrder", body, api="TMF622",
              parent=sp.span_id), "TMF622")
    usage = o.get("x-usageRecord")   # added inside the TMF622 facade while the order is Draft (internal step, see AgenticTelco_TMF622)
    o2 = ok(sf(v["traceId"], "Order in progress", "PATCH", f"{APEX}/tmf622/productOrder/{o['id']}", {"state": "inProgress"},
               api="TMF622", parent=sp.span_id), "TMF622 PATCH")
    orch = o2.get("x-orchestration") or {}
    plan = orch.get("fulfillmentPlanId") or ""
    sp.attrs.update(orchestration=orch.get("status"), fulfillmentPlanId=plan, orchestrationError=orch.get("error"))
    milestone(v["orderExternalId"], "OrderInProgress", {"productOrderId": o["id"], "orderNumber": o.get("x-orderNumber"), "state": o2.get("state"), "usageRecord": usage,
              "fulfillmentPlanId": plan or None, "orchestration": orch.get("status")})
    # Salesforce order orchestration runs the plan (decomposition, TMF641 through the network order adapter). No silent fallback:
    # if no fulfilment plan was created, the run stops here with a clear error (BPMN end event "Stopped: no fulfilment plan").
    if not plan:
        milestone(v["orderExternalId"], "OrchestrationNotStarted", {"productOrderId": o["id"], "orderNumber": o.get("x-orderNumber"),
                  "error": orch.get("error") or "No fulfilment plan was created", "route": "stopped (no fallback route)"})
        raise BpmnErr("NO_FULFILMENT_PLAN", "Salesforce order orchestration created no fulfilment plan for order " + str(o.get("x-orderNumber") or o["id"])
                      + ": " + str(orch.get("error") or "no plan") + " The run stops (no fallback route).")
    return {"productOrderId": o["id"], "orderNumber": o.get("x-orderNumber") or "", "fulfillmentPlanId": plan,
            "fulfilment": "salesforce", "orderPlacedAt": datetime.now(timezone.utc).isoformat()}

# ---- Salesforce order orchestration (the plan runs inside Salesforce; the workflow only reads it through TMF622) ----------------------
ORCH_POLL_S, ORCH_WAIT_S = 3, 120

def orch_view(v, sp, step):
    o = ok(sf(v["traceId"], step, "GET", f"{APEX}/tmf622/productOrder/{v['productOrderId']}", api="TMF622", parent=sp.span_id), "TMF622 GET")
    return o, (o.get("x-orchestration") or {})

def network_spans(v, sp, x, seen):
    """One L7 audit row per network call the plan made (TMF641 only: POST plus status reads), as recorded by the network order adapter."""
    for c in x.get("networkCalls") or []:
        if c.get("name") in seen:
            continue
        seen.add(c.get("name"))
        api = c.get("api") or ""
        if not api.startswith("TMF") or " /" not in (c.get("operation") or ""):
            continue  # e.g. the customer notification step: recorded on the order, not a network call
        mocked = (c.get("mode") or x.get("adapterMode")) == "Mock"
        meth, _, path = (c.get("operation") or "").partition(" ")
        with Span(v["traceId"], "L6", "Network order adapter" + (" (Mocked)" if mocked else ""), c.get("step") or api,
                  runtime="Salesforce order orchestration → network order adapter" + (" (Mocked)" if mocked else ""),
                  api=tmf(api) if api.startswith("TMF") else api, method=meth or None, path=path or None, parent=sp.span_id,
                  request=c.get("request"), attrs={"networkId": c.get("networkId"), "state": c.get("state"), "adapterMode": c.get("mode") or x.get("adapterMode"),
                  "simulated": x.get("adapterNote") if mocked else None, "at": c.get("at"), "tmf": api}) as n:
            n.status, n.response = int(float(c.get("statusCode") or 200)), c.get("response") or {"state": c.get("state"), "id": c.get("networkId")}

def plan_summary(x):
    """Compact copy of TMF622 x-orchestration for the web views (decomposition with action codes, plan steps, the TMF641 order)."""
    so = x.get("serviceOrder") or {}
    return {"engine": x.get("engine"), "fulfillmentPlanId": x.get("fulfillmentPlanId"), "status": x.get("status"), "planState": x.get("planState"),
            "adapterMode": x.get("adapterMode"), "adapterNote": x.get("adapterNote"), "idempotencyKey": x.get("idempotencyKey"),
            "decomposition": x.get("decomposition") or [],
            "steps": [{k: st.get(k) for k in ("name", "state", "jeopardy", "message", "startedAt", "completedAt", "dependsOn")} for st in x.get("steps") or []],
            "serviceOrder": {"id": so.get("id"), "state": so.get("state"), "externalId": so.get("externalId"),
                             "stateChange": so.get("stateChange") or [],
                             "items": so.get("items") or [], "networkFulfilment": so.get("networkFulfilment")},
            "actionCodesNote": x.get("actionCodesNote"), "networkBreakdownNote": x.get("networkBreakdownNote"),
            # only the route and writer reach the demo UI ("Assetisation done (TMF637)"); the raw platform status stays in the docs
            "productInventory": {k: v for k, v in (x.get("productInventory") or {}).items() if k in ("route", "routeLabel", "writer")} or None,
            "networkCalls": len(x.get("networkCalls") or [])}

def oss_submit(v, sp):
    if v.get("fulfilment") == "salesforce":
        seen, x, t0 = set(), {}, time.time()
        while time.time() - t0 < ORCH_WAIT_S:
            _, x = orch_view(v, sp, "Read the fulfilment plan (TMF622 x-orchestration)")
            if x.get("serviceOrder") or x.get("status") in ("failed", "completed"):
                break
            time.sleep(ORCH_POLL_S)
        so = x.get("serviceOrder") or {}
        sp.attrs.update(engine=x.get("engine"), fulfillmentPlanId=x.get("fulfillmentPlanId"), planState=x.get("planState"), adapterMode=x.get("adapterMode"),
                        serviceOrderId=so.get("id"), idempotencyKey=x.get("idempotencyKey"),
                        decomposition=[f"{r.get('level')} {r.get('item')}: {r.get('action')}" for r in x.get("decomposition") or []])
        if x.get("status") == "failed":
            raise RuntimeError("Salesforce order orchestration step failed: " + "; ".join(s.get("message") or s.get("name") for s in x.get("steps") or [] if s.get("state") == "Failed"))
        if not so:
            raise RuntimeError("Salesforce order orchestration: no TMF641 service order yet (plan " + str(x.get("planState")) + ")")
        milestone(v["orderExternalId"], "SentToOSS", {"serviceOrderId": so.get("id"), "via": "Salesforce order orchestration", "adapterMode": x.get("adapterMode"),
                  "fulfillmentPlanId": x.get("fulfillmentPlanId"), "items": len(so.get("serviceOrderItem") or []), "expectedCompletionDate": date.today().isoformat()})
        return {"serviceOrderId": so.get("id") or ""}
    r = httpx.post(f"{url('standins')}/tmf-api/serviceOrdering/v4/serviceOrder", headers={"traceparent": traceparent(v["traceId"], sp.span_id)},

                   json={"externalId": v["orderExternalId"], "site": v["site"], "toCapacityMbps": int(v["toSpeed"]),
                         "productOrder": {"id": v["productOrderId"]}}, timeout=30).json()
    milestone(v["orderExternalId"], "SentToOSS", {"serviceOrderId": r["id"], "expectedCompletionDate": r["expectedCompletionDate"]})
    return {"serviceOrderId": r["id"]}

def oss_read(v, sp):
    if v.get("fulfilment") == "salesforce":
        seen, x, t0 = set(), {}, time.time()
        while time.time() - t0 < ORCH_WAIT_S:
            _, x = orch_view(v, sp, "Read the fulfilment plan (TMF622 x-orchestration)")
            if x.get("status") in ("failed", "completed"):
                break
            time.sleep(ORCH_POLL_S)
        network_spans(v, sp, x, seen)
        steps = x.get("steps") or []
        late = [s for s in steps if (s.get("jeopardy") or "On Time") not in ("On Time", "")]
        so = x.get("serviceOrder") or {}
        sp.attrs.update(planState=x.get("planState"), orchestration=x.get("status"), serviceOrderState=so.get("state"),
                        stateChange=[c.get("state") for c in so.get("stateChange") or []], jeopardySteps=[s.get("name") for s in late])
        if x.get("status") == "failed":
            raise RuntimeError("Salesforce order orchestration step failed: " + "; ".join(s.get("message") or s.get("name") for s in steps if s.get("state") == "Failed"))
        if x.get("status") != "completed":
            if late and v.get("jeopardyRaised") != "yes":
                return {"ossState": "jeopardy", "liveDate": "", "ossJeopardy": json.dumps({"jeopardyType": "Late", "name": "Plan step late",
                        "message": "Salesforce order orchestration step late: " + ", ".join(s.get("name") for s in late), "revisedDays": 2})}
            raise RuntimeError(f"Salesforce order orchestration still {x.get('status')} after {ORCH_WAIT_S}s; retrying")
        milestone(v["orderExternalId"], "FulfilmentPlan", plan_summary(x))
        for c in so.get("stateChange") or []:
            milestone(v["orderExternalId"], "ServiceOrder" + (c.get("state") or "").capitalize(), {"serviceOrderId": so.get("id"), "state": c.get("state"), "at": c.get("changeDate")})
        milestone(v["orderExternalId"], "PortReserved", {"name": "PortReserved", "message": "Bandwidth profile 150 → 900 Mbps on the access port; router swapped (TMF641 completed)",
                  "serviceOrderId": so.get("id"), "via": "Salesforce order orchestration", "adapterMode": x.get("adapterMode")})
        return {"ossState": "completed", "liveDate": date.today().isoformat(), "ossJeopardy": ""}
    o = httpx.get(f"{url('standins')}/tmf-api/serviceOrdering/v4/serviceOrder", params={"externalId": v["orderExternalId"]},
                  headers={"traceparent": traceparent(v["traceId"], sp.span_id)}, timeout=30).json()[0]
    state = "completed" if o["state"] == "completed" else ("jeopardy" if o["jeopardyAlert"] and v.get("jeopardyRaised") != "yes" else "inProgress")
    sp.attrs.update(ossState=state, batchRun=o["batchRuns"])
    if state == "completed":
        milestone(v["orderExternalId"], "PortReserved", o["milestone"][-1] if o["milestone"] else {})
    return {"ossState": state, "liveDate": o.get("completionDate") or o.get("expectedCompletionDate") or "", "ossJeopardy": json.dumps(o["jeopardyAlert"][-1]) if o["jeopardyAlert"] else ""}

def jeopardy(v, sp):
    j = json.loads(v["ossJeopardy"]) if v.get("ossJeopardy") else {"revisedDays": 2}
    def raise_it():
        alert = {"@type": "ProductOrderJeopardyAlert", "id": "JA-" + v["orderExternalId"][-8:], "alertDate": datetime.now(timezone.utc).isoformat(),
                 "jeopardyType": j.get("jeopardyType", "NoFreePort"), "name": j.get("name"), "message": j.get("message"),
                 "x-revisedCompletionDate": j.get("revisedCompletionDate"), "productOrder": {"id": v["productOrderId"], "state": "inProgress"}}
        q("insert into mvp.jeopardy(order_ext, body) values (%s,%s)", v["orderExternalId"], J(alert))
        milestone(v["orderExternalId"], "Jeopardy", alert)
        report(v, sp, "icm:StateDegrades", "Intent at risk: revised date",
               {"reason": j.get("message"), "revisedCompletionDate": j.get("revisedCompletionDate"), "delayDays": j.get("revisedDays", 2),
                "productOrderState": "inProgress"})
        return {"alert": alert["id"]}
    remembered(v["orderExternalId"], "jeopardy", raise_it)
    sp.attrs.update(revisedCompletionDate=j.get("revisedCompletionDate"), salesforceOrder="unchanged (inProgress)")
    return {"jeopardyRaised": "yes", "revisedDate": j.get("revisedCompletionDate") or ""}

def activate(v, sp):
    t = v["traceId"]
    o = ok(sf(t, "Complete order", "PATCH", f"{APEX}/tmf622/productOrder/{v['productOrderId']}", {"state": "completed"},
              api="TMF622", parent=sp.span_id), "TMF622 complete")
    milestone(v["orderExternalId"], "OrderCompleted", {"state": o.get("state"), "sfStatus": o.get("x-sfStatus")})
    return {"activatedAt": datetime.now(timezone.utc).isoformat()}

def asset_check(ok_, what):
    if not ok_:
        raise RuntimeError("Installed product check failed (TMF637): " + what + ". The run stops; the workflow writes nothing to the installed base.")

def asset_change(v, sp):
    """Read-back only. The installed product has one writer: the Salesforce plan step (or the built-in asset step, chosen at
    build time). The workflow checks through TMF637: Fibre 150 terminated on the upgrade date; Fibre 900 active at the new
    monthly price with the contract end date kept, linked to Fibre 150 (Upgrade) and with its components as children."""
    t, key = v["traceId"], safe_key(v["orderExternalId"], "orderExternalId")
    serial = "AT-" + key
    cur, acct = sf_id(v["currentAssetId"], "currentAssetId"), sf_id(v["accountId"], "accountId")   # checked before they go into a path
    P = f"{APEX}/tmf637/product"
    _, x = orch_view(v, sp, "Read the assetisation route (TMF622 x-orchestration)")
    inv = x.get("productInventory") or {}
    route, route_label = inv.get("route") or "", inv.get("routeLabel") or ""
    live = (v.get("liveDate") or date.today().isoformat())[:10]
    keep_end = (v.get("contractEnd") or "")[:10]
    old = ok(sf(t, "Read Fibre 150 (terminated)", "GET", f"{P}/{cur}", api="TMF637", parent=sp.span_id), "TMF637 read")
    found = ok(sf(t, "Read Fibre 900 (active)", "GET", f"{P}?productSerialNumber={serial}&limit=5", api="TMF637", parent=sp.span_id), "TMF637 read")
    asset_check(len(found) == 1, f"expected one installed product with serial {serial}, found {len(found)}")
    new = found[0]
    new_id = sf_id(new["id"], "newAssetId")
    price = ((((new.get("productPrice") or [{}])[0]).get("price") or {}).get("taxIncludedAmount") or {}).get("value")
    pt = ((new.get("productPrice") or [{}])[0]).get("priceType")
    rel = next((r for r in old.get("productRelationship") or [] if r.get("relationshipType") == "Upgrade"
                and (r.get("product") or {}).get("id") == new_id), None)
    kids = [c.get("name") for c in new.get("product") or []]
    asset_check(old.get("status") == "terminated", f"Fibre 150 status is {old.get('status')}, not terminated")
    asset_check(str(old.get("terminationDate") or "")[:10] == live, f"Fibre 150 ends {old.get('terminationDate')}, not {live}")
    asset_check(new.get("status") == "active", f"Fibre 900 status is {new.get('status')}, not active")
    asset_check(pt == "recurring" and price is not None and float(price) == float(v["toPrice"]), f"Fibre 900 price is {price} ({pt}), not £{v['toPrice']} recurring")
    asset_check(not keep_end or str(new.get("terminationDate") or "")[:10] == keep_end, f"Fibre 900 ends {new.get('terminationDate')}, not {keep_end}")
    asset_check(rel is not None, "no Upgrade link from Fibre 150 to Fibre 900")
    asset_check(len(kids) >= 2, f"Fibre 900 has {len(kids)} component products, expected the router and the access line")
    # Live check of the hidden rule: nothing else (e.g. the org's Custom Assetize Order flow) created a product for this order.
    since = (v.get("orderPlacedAt") or v["activatedAt"])[:19] + "Z"   # the plan activates the order inside Salesforce, so check from order placement
    recent = ok(sf(t, "Check: no other writer created a product", "GET",
                   f"{P}?relatedParty.id={acct}&creationDate.gt={since}&limit=50", api="TMF637", parent=sp.span_id), "TMF637 list")
    others = [p for p in recent if p["id"] != new_id and not p.get("x-bundledIn") and not str(p.get("productSerialNumber") or "").startswith("AT-")]
    rel_id = rel.get("id")
    sp.attrs.update(newAssetId=new_id, oldAssetId=cur, relationshipId=rel_id, components=kids, assetisationRoute=route,
                    assetisationRouteLabel=route_label, assetizeFlowAssets=len(others))
    milestone(key, "AssetChanged", {"old": cur, "new": new_id, "relationship": rel_id, "components": kids, "route": route,
              "routeLabel": route_label, "flowCreatedAssets": len(others)})
    return {"newAssetId": new_id, "relationshipId": rel_id or "", "flowCreatedAssets": str(len(others)), "assetisationRoute": route}

def fulfilled(v, sp):
    remembered(v["orderExternalId"], "fulfilled", lambda: report(v, sp, "icm:StateComplies", "Intent fulfilled",
               {"product": v["toName"], "liveDate": v.get("liveDate"), "newAssetId": v.get("newAssetId"), "productOrderState": "completed"}) and {"ok": True})
    milestone(v["orderExternalId"], "Live", {"product": v["toName"]})
    return {}

HANDLERS = {"mvp-binding-check": binding_check, "mvp-quote": quote, "mvp-order": order, "mvp-oss-submit": oss_submit,
            "mvp-oss-read": oss_read, "mvp-jeopardy": jeopardy, "mvp-activate": activate, "mvp-asset-change": asset_change,
            "mvp-intent-fulfilled": fulfilled}

def engine(method, path, json_=None, timeout=30):
    return httpx.request(method, OPERATON_URL + path, json=json_, auth=creds("worker"), timeout=timeout)

def handle(t):
    v = {k: x.get("value") for k, x in (t.get("variables") or {}).items()}
    topic = t["topicName"]
    with Span(v.get("traceId"), "L5", "Operaton worker", STEP_NAMES[topic], runtime="Operaton BPMN + Python worker", api="BPMN",
              method="TASK", path=f"{t['activityId']} ({topic})", parent=v.get("parentSpan"), conversation_id=v.get("conversationId"),
              attrs={"activityId": t["activityId"], "businessKey": t.get("businessKey"), "processInstanceId": t["processInstanceId"]}) as sp:
        try:
            out = HANDLERS[topic](v, sp) or {}
            sp.status, sp.response = 200, out
            r = engine("POST", f"/external-task/{t['id']}/complete",
                       {"workerId": WORKER_ID, "variables": {k: {"value": str(x), "type": "String"} for k, x in out.items() if not k.startswith("_")}})
            if r.status_code >= 300:
                print("complete failed", r.status_code, r.text[:200], flush=True)
        except BpmnErr as e:
            sp.status, sp.attrs["bpmnError"] = 409, e.code
            sp.response = {"errorCode": e.code, "message": e.msg}
            engine("POST", f"/external-task/{t['id']}/bpmnError", {"workerId": WORKER_ID, "errorCode": e.code, "errorMessage": e.msg,
                   "variables": {"failureReason": {"value": e.msg, "type": "String"}}})
            if e.code == "POLICY_BLOCKED":
                report(v, sp, "icm:StateDegrades", "Intent not progressed: stopped by policy", {"reason": e.msg})
            if e.code == "NO_FULFILMENT_PLAN":
                report(v, sp, "icm:StateDegrades", "Intent not progressed: no fulfilment plan (run stopped, no fallback route)", {"reason": e.msg})
        except Exception as e:
            traceback.print_exc()
            sp.status = 500
            retries = t.get("retries")
            engine("POST", f"/external-task/{t['id']}/failure", {"workerId": WORKER_ID, "errorMessage": str(e)[:200],
                   "retries": (retries if retries is not None else 3) - 1, "retryTimeout": 2000})

def main():
    init_schema()
    print(f"{WORKER_ID} polling {list(HANDLERS)}", flush=True)
    while True:
        try:
            r = engine("POST", "/external-task/fetchAndLock", {"workerId": WORKER_ID, "maxTasks": 4, "asyncResponseTimeout": 20000,
                       "topics": [{"topicName": n, "lockDuration": LOCK_MS} for n in HANDLERS]}, timeout=40)
            if r.status_code != 200:
                print("fetchAndLock", r.status_code, r.text[:200], flush=True)
                time.sleep(2)
                continue
            for t in r.json():
                handle(t)
        except Exception as e:
            print("poll error", e, flush=True)
            time.sleep(2)

if __name__ == "__main__":
    sys.exit(main())
