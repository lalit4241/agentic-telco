"""AgenticTelco MVP · L2 MCP server: exactly three tools, none of which writes to a system of record.

- get_context      → L4 context service (facts with sources + advisory policy decision)
- request_upgrade  → L1 intent service (records a TMF921-shaped Intent; the L5 workflow does the writes)
- order_status     → read-only: intent reports, L3 milestones, workflow position

The conversation (and therefore the signed-in contact and account) is bound by the agent service, never chosen by the model."""
import json
import httpx
from mcp.server.fastmcp import FastMCP
from stack.mvp.common import q, q1, J, Span, url, traceparent, PORTS, OPERATON_URL
from stack.l5_orchestrator.engine import creds

mcp = FastMCP("agentictelco-mvp", host="127.0.0.1", port=PORTS["mcp"], stateless_http=True, json_response=True)

def nice_date(d):
    from datetime import date
    return f"{date.fromisoformat(d).day} {date.fromisoformat(d):%B %Y}" if d else None

VIDEO_MBPS_PER_USER = 25   # our sizing assumption: 25 Mbps per video user (advice for the recommendation, not a business rule)

def conv(cid):
    c = q1("select id, trace_id, contact_id, state from mvp.conversation where id=%s", cid)
    if not c:
        raise ValueError("unknown conversation")
    return c

def hdr(c, span):
    return {"traceparent": traceparent(c["trace_id"], span.span_id)}

def parent(c):
    return (c["state"] or {}).get("agentSpan")

@mcp.tool()
def get_context(conversationId: str, staffOnVideoCalls: int = 0) -> str:
    """staffOnVideoCalls: total people who will be on video calls, if the customer said. Get the facts for the signed-in business customer (who they are, current broadband, contract, site availability,
    balance) and which upgrades the policy allows. Call this before recommending anything."""
    c = conv(conversationId)
    acc = c["state"]["accountId"]
    with Span(c["trace_id"], "L2", "MCP server", "Tool: get_context", runtime="ours (MCP SDK)", api="MCP", method="CALL", path="get_context",
              parent=parent(c), conversation_id=conversationId) as sp:
        r = httpx.post(f"{url('context')}/context", json={"contactId": c["contact_id"], "accountId": acc, "conversationId": conversationId},
                       headers=hdr(c, sp), timeout=120).json()
        p, a = r["contextPack"], r["advisory"]
        out = {"customer": p["customer"]["name"], "requester": {"name": p["requester"]["name"], "role": p["requester"]["role"],
               "authorisedContact": p["requester"]["authorisedContact"]},
               "site": p["site"]["name"], "current": f"{p['currentBroadband']['product']} at £{p['currentBroadband']['monthlyPriceGBP']}/month",
               "contractMonthsLeft": p["contractMonthsLeft"]["value"],
               "contractEndDate": nice_date(p["contractMonthsLeft"].get("contractEnd")), "overdueBalanceGBP": p["overdueBalance"]["amountGBP"],
               "allowedUpgrades": [{"offeringId": o["id"], "name": o["name"], "downloadSpeedMbps": o["downloadSpeedMbps"],
                                    "monthlyPriceGBP": o["monthlyPriceGBP"],
                                    "videoCallUsersSupported": (o["downloadSpeedMbps"] or 0) // VIDEO_MBPS_PER_USER} for o in a["allowedOffers"]],
               "blockedBecause": a["reasons"], "policyVersion": a["policyVersion"]}
        if staffOnVideoCalls and out["allowedUpgrades"]:
            need = int(staffOnVideoCalls) * VIDEO_MBPS_PER_USER
            fits = sorted([o for o in out["allowedUpgrades"] if (o["downloadSpeedMbps"] or 0) >= need], key=lambda o: o["monthlyPriceGBP"])
            out["sizing"] = {"staffOnVideoCalls": int(staffOnVideoCalls), "neededMbps": need, "mbpsPerPerson": VIDEO_MBPS_PER_USER,
                             "bestFit": fits[0]["offeringId"] if fits else None,
                             "bestFitName": fits[0]["name"] if fits else None}
        if r.get("paymentLink"):
            out["paymentLink"] = r["paymentLink"]["url"]
        if r.get("decisionMaker"):
            out["whoCanOrder"] = r["decisionMaker"]
        sp.status, sp.response = 200, out
    return json.dumps(out)

@mcp.tool()
def request_upgrade(conversationId: str, offeringId: str, outcome: str) -> str:
    """Ask for an upgrade the customer has agreed to. Only use after the customer said yes. offeringId must be one of the
    allowedUpgrades from get_context. outcome is the customer's need in plain words (not a product name).
    This records an intent; the workflow checks policy again and does all system changes."""
    c = conv(conversationId)
    st = c["state"]
    with Span(c["trace_id"], "L2", "MCP server", "Tool: request_upgrade", runtime="ours (MCP SDK)", api="MCP", method="CALL",
              path="request_upgrade", parent=parent(c), conversation_id=conversationId, request={"offeringId": offeringId, "outcome": outcome}) as sp:
        consent = q1("select id from mvp.consent where conversation_id=%s order by id desc limit 1", conversationId)
        if not consent:
            sp.status = 409
            return json.dumps({"error": "The customer has not agreed yet. Ask them first."})
        site = (st.get("contextPack") or {}).get("identity", {}).get("inventorySite", "")
        intent = {"@type": "Intent", "name": "Business broadband outcome", "description": outcome,
                  "expression": {"@type": "JsonLdExpression", "expressionValue": {
                      "outcome": outcome, "extraStaff": st.get("extraStaff"), "useCases": ["cloud video calls"], "site": site,
                      "constraints": ["within current contract", "upgrade only"], "byDate": None}},
                  "relatedParty": [{"id": c["contact_id"], "role": "requester"}, {"id": st["accountId"], "role": "customer"}],
                  "x-proposal": {"recommendedOffering": offeringId, "consentId": consent["id"], "conversationId": conversationId}}
        r = httpx.post(f"{url('intent')}/tmf-api/intentManagement/v5/intent", json=intent, headers=hdr(c, sp), timeout=120)
        sp.status = r.status_code
        if r.status_code != 201:
            out = {"accepted": False, "status": r.status_code, "detail": r.json().get("detail")}
        else:
            b = r.json()
            out = {"accepted": True, "intentId": b["id"], "lifecycleStatus": b["lifecycleStatus"], "orderReference": b["x-orderExternalId"]}
            q("update mvp.conversation set state = state || %s where id=%s", J({"intentId": b["id"], "orderExternalId": b["x-orderExternalId"],
              "processInstanceId": b["x-workflow"]["processInstanceId"]}), conversationId)
        sp.response = out
    return json.dumps(out)

@mcp.tool()
def order_status(conversationId: str) -> str:
    """Read the progress of the customer's upgrade: intent status, progress reports, milestones and any delay. Read-only."""
    c = conv(conversationId)
    st = c["state"]
    with Span(c["trace_id"], "L2", "MCP server", "Tool: order_status", runtime="ours (MCP SDK)", api="MCP", method="CALL", path="order_status",
              parent=parent(c), conversation_id=conversationId) as sp:
        if not st.get("intentId"):
            return json.dumps({"status": "no upgrade requested yet"})
        it = q1("select lifecycle_status from mvp.intent where id=%s", st["intentId"])
        reps = [r["body"]["expression"]["expressionValue"] for r in q("select body from mvp.intent_report where intent_id=%s order by created_at", st["intentId"])]
        ms = [r["name"] for r in q("select name from mvp.milestone where order_ext=%s order by id", st["orderExternalId"])]
        acts = httpx.get(f"{OPERATON_URL}/history/activity-instance", params={"processInstanceId": st["processInstanceId"], "sortBy": "startTime",
                         "sortOrder": "asc"}, auth=creds("agent"), timeout=20).json()
        out = {"intentStatus": it["lifecycle_status"], "reports": reps, "milestones": ms,
               "workflowAt": [a["activityName"] for a in acts if not a.get("endTime")] if isinstance(acts, list) else []}
        sp.status, sp.response = 200, out
    return json.dumps(out)

app = mcp.streamable_http_app()
