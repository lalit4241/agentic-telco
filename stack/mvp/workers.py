"""AgenticTelco MVP · L5 Operaton external-task workers (deterministic: no model is called from here).

Every system-of-record write happens here, after the binding policy check. Idempotency: the order external ID is the business key;
Salesforce facades are idempotent on externalId, Assets on SerialNumber AT-<key>, and each step's result is kept in mvp.step_result,
so a rerun after a crash replays instead of writing twice."""
import json, os, sys, time, traceback
from datetime import date, datetime, timezone
import httpx
from stack.mvp.common import (q, q1, J, Span, sf, soql, SF_DATA, NATIVE, FACADE, url, traceparent, init_schema, OPERATON_URL)
from stack.l5_orchestrator.engine import creds

WORKER_ID = f"mvp-l5-worker-{os.getpid()}"
APEX = "/services/apexrest/agentictelco"
LOCK_MS = 120000
STEP_NAMES = {
    "mvp-binding-check": "Binding policy check + identity", "mvp-quote": "Create quote", "mvp-order": "Place upgrade order",
    "mvp-oss-submit": "Send to legacy OSS", "mvp-oss-read": "Read OSS batch result", "mvp-jeopardy": "Raise jeopardy (+2 days)",
    "mvp-activate": "Complete order", "mvp-asset-change": "Asset change", "mvp-intent-fulfilled": "Intent fulfilled",
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
    r = ok(sf(v["traceId"], "Create quote", "POST", f"{APEX}/tmf648/quote", body, runtime=FACADE, api="TMF648", parent=sp.span_id), "TMF648")
    milestone(v["orderExternalId"], "QuoteCreated", {"quoteId": r["id"]})
    return {"quoteId": r["id"]}

def order(v, sp):
    body = {"externalId": v["orderExternalId"], "description": f"Upgrade Fibre 150 to {v['toName']} (intent {v['intentId']})",
            "relatedParty": [{"id": v["accountId"], "role": "Customer"}], "quote": [{"id": v.get("quoteId")}],
            "productOrderItem": [{"id": "1", "action": "modify", "quantity": 1, "productOffering": {"id": v["toOffering"]},
                                  "productOfferingPrice": {"id": v["toPriceId"]}, "product": {"id": v["currentAssetId"], **term_item(v)}}]}
    o = ok(sf(v["traceId"], "Place upgrade order (action modify)", "POST", f"{APEX}/tmf622/productOrder", body, runtime=FACADE, api="TMF622",
              parent=sp.span_id), "TMF622")
    usage = ensure_usage_record(v, sp, o["id"])
    o2 = ok(sf(v["traceId"], "Order in progress", "PATCH", f"{APEX}/tmf622/productOrder/{o['id']}", {"state": "inProgress"}, runtime=FACADE,
               api="TMF622", parent=sp.span_id), "TMF622 PATCH")
    milestone(v["orderExternalId"], "OrderInProgress", {"productOrderId": o["id"], "orderNumber": o.get("x-orderNumber"), "state": o2.get("state"), "usageRecord": usage})
    return {"productOrderId": o["id"], "orderNumber": o.get("x-orderNumber") or ""}

def oss_submit(v, sp):
    r = httpx.post(f"{url('standins')}/tmf-api/serviceOrdering/v4/serviceOrder", headers={"traceparent": traceparent(v["traceId"], sp.span_id)},
                   json={"externalId": v["orderExternalId"], "site": v["site"], "toCapacityMbps": int(v["toSpeed"]),
                         "productOrder": {"id": v["productOrderId"]}}, timeout=30).json()
    milestone(v["orderExternalId"], "SentToOSS", {"serviceOrderId": r["id"], "expectedCompletionDate": r["expectedCompletionDate"]})
    return {"serviceOrderId": r["id"]}

def oss_read(v, sp):
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

def ensure_usage_record(v, sp, oid):
    """The org's 'Custom Assetize Order' flow fires when an Order is activated and expects a Subscription Management usage record.
    Salesforce only accepts that record while the order is still Draft, so we add it right after creating the order, through the
    native sObject API. The flow then takes its 'record exists' branch. The flow itself is untouched."""
    t = v["traceId"]
    have = soql(t, "Check usage record (hidden rule in Custom Assetize Order)", "SELECT Id FROM AppUsageAssignment WHERE RecordId='" + oid
                + "' AND AppUsageType='SubscriptionManagement'", api="sObject")
    if have:
        return have[0]["Id"]
    return ok(sf(t, "Add usage record while the order is Draft (hidden rule)", "POST", f"{SF_DATA}/sobjects/AppUsageAssignment",
                 {"RecordId": oid, "AppUsageType": "SubscriptionManagement"}, api="sObject", parent=sp.span_id), "AppUsageAssignment")["id"]

def activate(v, sp):
    t = v["traceId"]
    ensure_usage_record(v, sp, v["productOrderId"])
    o = ok(sf(t, "Complete order", "PATCH", f"{APEX}/tmf622/productOrder/{v['productOrderId']}", {"state": "completed"}, runtime=FACADE,
              api="TMF622", parent=sp.span_id), "TMF622 complete")
    milestone(v["orderExternalId"], "OrderCompleted", {"state": o.get("state"), "sfStatus": o.get("x-sfStatus")})
    return {"activatedAt": datetime.now(timezone.utc).isoformat()}

def asset_change(v, sp):
    t, key = v["traceId"], v["orderExternalId"]
    serial = "AT-" + key
    ex = soql(t, "Find new installed service (idempotent)", f"SELECT Id FROM Asset WHERE SerialNumber='{serial}' AND Name LIKE 'AgenticTelco%' LIMIT 1", api="sObject")
    old = soql(t, "Read current installed service", f"SELECT Id, Name, ContactId, LocationId, UsageEndDate FROM Asset WHERE Id='{v['currentAssetId']}'", api="sObject")[0]
    live = (v.get("liveDate") or date.today().isoformat())[:10]          # billed at the new price from the upgrade (go-live) date
    keep_end = v.get("contractEnd") or old.get("UsageEndDate")            # decision: the existing contract end date is kept
    if ex:
        new_id = ex[0]["Id"]
    else:
        new_id = ok(sf(t, "Create Fibre 900 Installed at the same Location", "POST", f"{SF_DATA}/sobjects/Asset",
                       {"Name": f"{v['toName']} – Brightwell site {v['site']}", "AccountId": v["accountId"], "ContactId": old.get("ContactId"),
                        "Product2Id": v["toOffering"], "Status": "Installed", "Quantity": 1, "Price": float(v["toPrice"]), "SerialNumber": serial,
                        "LocationId": old["LocationId"], "InstallDate": live, "UsageEndDate": keep_end,
                        "Description": f"AgenticTelco MVP: upgraded from Fibre 150 by order {v.get('orderNumber')} ({key}). "
                                       f"£{v['toPrice']} a month from {live}; contract end {keep_end} unchanged."},
                       api="TMF637 (sObject write)", parent=sp.span_id), "Asset create")["id"]
    r = sf(t, "Fibre 150 to Obsolete with an end date", "PATCH", f"{SF_DATA}/sobjects/Asset/{v['currentAssetId']}",
           {"Status": "Obsolete", "UsageEndDate": live}, api="TMF637 (sObject write)", parent=sp.span_id)
    if r.status_code != 204:
        raise RuntimeError(f"Asset obsolete → {r.status_code} {r.text[:200]}")
    rel = soql(t, "Find Upgrade link (idempotent)", f"SELECT Id FROM AssetRelationship WHERE AssetId='{v['currentAssetId']}' AND RelatedAssetId='{new_id}'", api="sObject")
    rel_id = rel[0]["Id"] if rel else ok(sf(t, "Link old and new: AssetRelationship Upgrade", "POST", f"{SF_DATA}/sobjects/AssetRelationship",
                                           {"AssetId": v["currentAssetId"], "RelatedAssetId": new_id, "RelationshipType": "Upgrade",
                                            "FromDate": datetime.now(timezone.utc).isoformat()}, api="sObject", parent=sp.span_id), "AssetRelationship")["id"]
    # Live check of the hidden rule: the flow must NOT have created its own Asset for this order.
    time.sleep(3)
    flow_assets = soql(t, "Check: Custom Assetize Order created no Asset", f"SELECT Id, Name FROM Asset WHERE AccountId='{v['accountId']}' "
                       f"AND CreatedDate >= {v['activatedAt'][:19]}Z AND Id != '{new_id}'", api="sObject")
    sp.attrs.update(newAssetId=new_id, oldAssetId=v["currentAssetId"], relationshipId=rel_id, assetizeFlowAssets=len(flow_assets))
    milestone(key, "AssetChanged", {"old": v["currentAssetId"], "new": new_id, "relationship": rel_id, "flowCreatedAssets": len(flow_assets)})
    return {"newAssetId": new_id, "relationshipId": rel_id, "flowCreatedAssets": str(len(flow_assets))}

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
