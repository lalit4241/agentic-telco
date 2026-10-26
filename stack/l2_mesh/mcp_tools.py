"""L2 · MCP tool server (Model Context Protocol, streamable HTTP). Agents reach every layer through these tools.
Tools carry run_id so the L8 ledger can stitch the trace together."""
from mcp.server.fastmcp import FastMCP
from stack.zg_common.config import SOR_BASE, url, PORTS
from stack.zg_common.http import call
from stack.zg_common.telemetry import setup

setup("mcp-tools")
CALLER = "mcp-tools"
mcp = FastMCP("agentictelco-tools", host="127.0.0.1", port=PORTS["mcp_tools"], stateless_http=True, json_response=True)

def j(r):
    try:
        return r.json()
    except Exception:
        return {"status": r.status_code, "text": r.text[:300]}

@mcp.tool(description="TMF620 – list sellable broadband product offerings from the system of record")
def tmf620_list_offerings(run_id: str) -> list:
    return j(call(CALLER, "GET", f"{SOR_BASE}/tmf-api/productCatalogManagement/v4/productOffering", run_id=run_id))

@mcp.tool(description="TMF679 – check product offering qualification for a customer (product configuration only)")
def tmf679_qualify(run_id: str, customer_id: str, offering_id: str) -> dict:
    return j(call(CALLER, "POST", f"{SOR_BASE}/tmf-api/productOfferingQualification/v4/checkProductOfferingQualification", run_id=run_id,
                  json={"relatedParty": [{"id": customer_id, "role": "customer"}], "instantSyncQualification": True,
                        "checkProductOfferingQualificationItem": [{"id": "1", "productOffering": {"id": offering_id}}]}))

@mcp.tool(description="TMF648 – create a quote for an offering")
def tmf648_quote(run_id: str, customer_id: str, offering_id: str) -> dict:
    return j(call(CALLER, "POST", f"{SOR_BASE}/tmf-api/quoteManagement/v4/quote", run_id=run_id, idem=f"{run_id}:quote",
                  json={"relatedParty": [{"id": customer_id, "role": "customer"}], "quoteItem": [{"id": "1", "action": "modify", "productOffering": {"id": offering_id}}]}))

@mcp.tool(description="TMF637 – current products held by the customer")
def tmf637_products(run_id: str, customer_id: str) -> list:
    return j(call(CALLER, "GET", f"{SOR_BASE}/tmf-api/productInventory/v4/product", params={"customerId": customer_id}, run_id=run_id))

@mcp.tool(description="L4 – assemble cross-domain customer context (SoR + data products)")
def l4_context(run_id: str, customer_id: str) -> dict:
    return j(call(CALLER, "POST", url("l4_context") + "/zg/context/v1/context", json={"customerId": customer_id}, run_id=run_id))

@mcp.tool(description="L4 – ask the operator policy service (OPA) whether the action is allowed")
def l4_decide(run_id: str, action: str, context: dict, offering_id: str) -> dict:
    return j(call(CALLER, "POST", url("l4_context") + "/zg/context/v1/decision", run_id=run_id,
                  json={"action": action, "offeringId": offering_id, "context": context, "decidedByModel": False}))

@mcp.tool(description="L3 – semantic search over the operator knowledge base (pgvector)")
def l3_knowledge(run_id: str, query: str) -> list:
    return j(call(CALLER, "GET", url("l3_data") + "/zg/data/v1/knowledge/search", params={"query": query, "k": 2}, run_id=run_id))

@mcp.tool(description="TMF621 – open a trouble ticket")
def tmf621_open_ticket(run_id: str, customer_id: str, description: str, severity: str = "minor") -> dict:
    return j(call(CALLER, "POST", url("oss_mock") + "/tmf-api/troubleTicket/v4/troubleTicket", run_id=run_id,
                  json={"description": description, "severity": severity, "ticketType": "broadband-performance",
                        "relatedParty": [{"id": customer_id, "role": "customer"}]}))

@mcp.tool(description="TMF621 – read a trouble ticket")
def tmf621_get_ticket(run_id: str, ticket_id: str) -> dict:
    return j(call(CALLER, "GET", url("oss_mock") + f"/tmf-api/troubleTicket/v4/troubleTicket/{ticket_id}", run_id=run_id))

if __name__ == "__main__":
    mcp.run(transport="streamable-http")
