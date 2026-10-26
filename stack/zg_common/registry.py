"""Every API call is tagged with its Zero Gravity layer, ODA block, owner and runtime (OOTB / custom TMF API on Salesforce / our layer / stand-in)."""
APIS = {
    "TMF921": dict(name="Intent Management", block="Engagement Management", layer="L1/L2", owner="ours",
                   base="/tmf-api/intentManagement/v4", note="Not supported by Salesforce – our layer"),
    # L6 SoR = Salesforce Communications Cloud (org sfcomms). sfRuntime = how the real-org adapter serves it (docs/api/org-capabilities.md):
    #   OOTB = native Direct Access TMF API or standard sObject REST · custom = AgenticTelco_* Apex REST on Salesforce (ADR amendment 001)
    "TMF632": dict(name="Party Management", block="Party Management", layer="L6", owner="salesforce", base="/tmf-api/partyManagement/v4", sfRuntime="OOTB",
                   note="Native TMF632 v5 individual/organization by id (OOTB)"),
    "TMF629": dict(name="Customer Management", block="Party Management", layer="L6", owner="salesforce", base="/tmf-api/customerManagement/v4", sfRuntime="OOTB",
                   note="Native TMF629 v4 customer by id (OOTB)"),
    "TMF620": dict(name="Product Catalog", block="Core Commerce Management", layer="L6", owner="salesforce", certified=True, base="/tmf-api/productCatalogManagement/v4", sfRuntime="custom",
                   note="Org exposes no TMF620 (PCM Connect APIs only) – AgenticTelco_TMF620 Apex REST over standard EPC/PCM objects"),
    "TMF679": dict(name="Product Offering Qualification", block="Core Commerce Management", layer="L6", owner="salesforce", certified=True, base="/tmf-api/productOfferingQualification/v4", sfRuntime="OOTB-attempt",
                   note="Native TMF679 v5 called first; org has no default qualification procedure, so our layer applies the technology rule (labelled)"),
    "TMF648": dict(name="Quote Management", block="Core Commerce Management", layer="L6", owner="salesforce", base="/tmf-api/quoteManagement/v4", sfRuntime="custom",
                   note="Org exposes no TMF648 – AgenticTelco_TMF648 Apex REST over standard Quote/QuoteLineItem"),
    "TMF622": dict(name="Product Ordering", block="Core Commerce Management", layer="L6", owner="salesforce", certified=True, base="/tmf-api/productOrderingManagement/v4", sfRuntime="custom",
                   note="Native TMF622 v5 read path fails in this org – AgenticTelco_TMF622 Apex REST over standard Order/OrderItem"),
    "TMF637": dict(name="Product Inventory", block="Core Commerce Management", layer="L6", owner="salesforce", base="/tmf-api/productInventory/v4", sfRuntime="OOTB",
                   note="Native TMF637 v5 GET by id (OOTB); native POST is not allowed (405) so Assets are written with OOTB sObject REST"),
    "TMF645": dict(name="Service Qualification", block="Production", layer="OSS", owner="oss", base="/tmf-api/serviceQualificationManagement/v4"),
    "TMF641": dict(name="Service Ordering", block="Production", layer="OSS", owner="oss", base="/tmf-api/serviceOrdering/v4"),
    "TMF621": dict(name="Trouble Ticket", block="Production", layer="OSS", owner="oss", base="/tmf-api/troubleTicket/v4"),
    "TMF688": dict(name="Event Management", block="Decoupling & Integration", layer="L3", owner="ours", base="/tmf-api/eventManagement/v4", note="TMF688-style events on Apache Kafka (KRaft) – our layer"),
    "A2A": dict(name="Agent-to-Agent (A2A-style JSON-RPC)", block="Engagement Management", layer="L2", owner="ours", base="/a2a", note="Agent mesh – our layer"),
    "A2A-CARD": dict(name="A2A agent card discovery", block="Engagement Management", layer="L2", owner="ours", base="/.well-known/agent-card.json", note="Agent mesh – our layer"),
    "MCP": dict(name="MCP tools server", block="Engagement Management", layer="L2", owner="ours", base="/mcp", note="Agent tools – our layer"),
    "ZG-L3": dict(name="Data products (pgvector)", block="Intelligence Management", layer="L3", owner="ours", base="/zg/data/v1", note="Our layer"),
    "ZG-L4": dict(name="Context & policy service (OPA)", block="Intelligence Management (context)", layer="L4", owner="ours", base="/zg/context/v1", note="Policy lives here, not in Salesforce – our layer"),
    "ZG-L5": dict(name="L5 read-only saga view", block="Decoupling & Integration", layer="L5", owner="ours", base="/zg/orchestrator/v1", note="Read-only projection of Operaton state – our layer"),
    "BPMN": dict(name="Operaton BPMN engine REST (Camunda 7 API)", block="Decoupling & Integration", layer="L5", owner="ours", base="/engine-rest", note="Deterministic BPMN saga on Operaton (Apache-2.0) – our layer; agents may only start + read"),
    "INFER": dict(name="Shared inference gateway (OpenAI-compatible)", block="Intelligence Management", layer="L7→L2", owner="ours", base="/v1/chat/completions",
                  note="Hosted in L7 runtime, used by L2 agent mesh – our extension of the Zero Gravity framework (not a ninth layer)"),
    "LITELLM": dict(name="LiteLLM proxy → model serving", block="Intelligence Management", layer="L7", owner="ours", base="/litellm", note="Model gateway behind our inference service – our extension"),
    "OPA": dict(name="Open Policy Agent data/decision API", block="Intelligence Management (context)", layer="L4", owner="ours", base="/v1/data", note="Our layer"),
    "OPA-INF": dict(name="OPA model allow-list (UK residency)", block="Intelligence Management (governance)", layer="L4", owner="ours", base="/v1/data/zg/inference", note="L4 decides which models are allowed – our layer"),
}

def api_for(path: str):
    best = None
    for k, a in APIS.items():
        if path.startswith(a["base"]) and (best is None or len(a["base"]) > len(APIS[best]["base"])):
            best = k
    return best

def runtime_tag(key, sor_mode="standin", live=()):
    if key is None:
        return "unknown"
    a = APIS[key]
    if a["owner"] == "ours":
        return "our layer"
    if a["owner"] == "oss":
        return "stand-in (mocked OSS)"
    if sor_mode == "commscloud":   # the real-org adapter normally sends the exact runtime per call (x-zg-runtime); this is the default
        return {"OOTB": "OOTB", "custom": "custom TMF API on Salesforce", "OOTB-attempt": "OOTB"}[a["sfRuntime"]]
    return "stand-in"

def owner_label(key):
    if key is None:
        return ""
    o = APIS[key]["owner"]
    return {"salesforce": "Salesforce SoR (Comms Cloud contract)", "oss": "Production OSS (mocked)", "ours": "Zero Gravity custom layer"}[o]
