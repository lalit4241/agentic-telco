"""Unit tests – no running stack needed."""
import ast, json, re, xml.etree.ElementTree as ET
from pathlib import Path
import pytest
ROOT = Path(__file__).resolve().parents[1]

# ---------- registry / labelling
def test_every_api_is_tagged_with_layer_block_owner():
    from stack.zg_common.registry import APIS
    for k, a in APIS.items():
        assert a.get("layer") and a.get("block") and a.get("owner") in ("salesforce", "oss", "ours"), k

def test_tmf921_is_our_layer_not_salesforce():
    from stack.zg_common.registry import APIS, runtime_tag
    assert APIS["TMF921"]["owner"] == "ours"
    assert "not supported by salesforce" in APIS["TMF921"]["note"].lower()
    assert runtime_tag("TMF921", "commscloud", ("TMF921",)) == "our layer"

def test_real_org_runtime_labels_ootb_vs_custom_apex():
    from stack.zg_common.registry import runtime_tag, APIS
    assert runtime_tag("TMF629", "commscloud") == "OOTB" and runtime_tag("TMF637", "commscloud") == "OOTB"
    for k in ("TMF620", "TMF648", "TMF622"):
        assert runtime_tag(k, "commscloud") == "custom TMF API on Salesforce", k
    assert runtime_tag("TMF622", "standin") == "stand-in"
    assert all(a["sfRuntime"] in ("OOTB", "custom", "OOTB-attempt") for a in APIS.values() if a["owner"] == "salesforce")

def test_adapter_offer_translation_and_apex_paths():
    from stack.l6_salesforce_adapter import app as ad
    o = {"id": "01t", "name": "AgenticTelco Fibre 500", "isBundle": True, "href": "/services/apexrest/x",
         "prodSpecCharValueUse": [{"name": "AgenticTelco Download Speed", "x-code": "AT_ATT_DL_SPEED", "productSpecCharacteristicValue": [{"value": "500", "isDefault": True}]}],
         "productOfferingPrice": [{"id": "a", "priceType": "recurring", "x-sellingModel": "Evergreen Monthly", "price": {"unit": "GBP", "value": 40}},
                                  {"id": "b", "priceType": "recurring", "x-sellingModel": "AgenticTelco Term Monthly", "price": {"unit": "GBP", "value": 35}}]}
    t = ad.to_agent_offer(o)
    assert t["productOfferingPrice"][0]["price"]["taxIncludedAmount"]["value"] == 35.0
    sp = {c["name"]: c for c in t["prodSpecCharValueUse"]}
    assert sp["downloadSpeedMbps"]["productSpecCharacteristicValue"][0]["value"] == 500
    assert [v["value"] for v in sp["requiredTechnology"]["productSpecCharacteristicValue"]] == ["FTTP"]
    src = (ROOT / "stack/l6_salesforce_adapter/app.py").read_text()
    assert "/services/apexrest/agentictelco" in src and "ACCESS_TOKEN" not in src and "Bearer" not in src

def test_adapter_adds_sm_app_usage_before_activation(monkeypatch):
    """Org flow 'Custom Assetize Order' ends cleanly when an SM AppUsageAssignment exists; it must be created OOTB before the PATCH."""
    import asyncio, types
    from stack.l6_salesforce_adapter import app as ad
    seen = []
    def fake(method, path, body=None):
        seen.append((method, path.split("?")[0], body))
        if "/query" in path:
            return types.SimpleNamespace(status_code=200, json=lambda: {"records": [{"Id": "801X"}]}, text="")
        if path.endswith("/sobjects/AppUsageAssignment"):
            return types.SimpleNamespace(status_code=201, json=lambda: {"id": "0j8X"}, text="")
        return types.SimpleNamespace(status_code=200, json=lambda: {"state": "completed"}, text="")
    monkeypatch.setattr(ad, "sf_request", fake)
    tr = ad.Trace()
    asyncio.run(ad._patch_state(tr, "801X", "completed"))
    kinds = [(m, p.rsplit("/", 1)[-1]) for m, p, _ in seen]
    assert kinds[1] == ("POST", "AppUsageAssignment") and seen[1][2]["AppUsageType"] == "SubscriptionManagement"
    assert kinds[2][0] == "PATCH" and tr.calls[1]["runtime"] == "OOTB"
    seen.clear(); asyncio.run(ad._patch_state(ad.Trace(), "801X", "cancelled"))
    assert all("AppUsageAssignment" not in p for _, p, _ in seen)
    assert "DELETE" not in (ROOT / "stack/l6_salesforce_adapter/app.py").read_text().split("def _ensure_app_usage")[1].split("async def _patch_state")[0]

def test_tmf688_events_are_kafka_in_l3():
    from stack.zg_common.registry import APIS
    assert APIS["TMF688"]["layer"] == "L3" and "Kafka" in APIS["TMF688"]["note"]

# ---------- inference gateway pieces
def test_pii_redaction(monkeypatch):
    import stack.inference.app as gw
    monkeypatch.setattr(gw, "_names", ["David Okafor"])
    out, n = gw.redact("David Okafor (C-1002) david@example.com 07700 900123 lives at M4 7HR")
    assert "David" not in out and "Okafor" not in out and "C-1002" not in out and "@" not in out and "M4 7HR" not in out
    assert "[NAME]" in out and "[ACCOUNT]" in out and "[EMAIL]" in out and "[POSTCODE]" in out and "[PHONE]" in out and n >= 5

def test_cache_scope_separates_instructions_from_question():
    import stack.inference.app as gw
    a = gw.cache_scope([{"role": "system", "content": "A"}, {"role": "user", "content": "hello"}])
    b = gw.cache_scope([{"role": "system", "content": "B"}, {"role": "user", "content": "hello"}])
    assert a[0] != b[0] and a[1] == b[1] == "hello"

def test_routing_table_small_for_extraction_and_us_model_listed_first_for_reasoning():
    import stack.inference.app as gw
    assert gw.ROUTES["extraction"]["candidates"] == ["zg-local-small"]
    assert gw.ROUTES["reasoning"]["candidates"][0] == "us-frontier-saas"   # OPA must deny it – see stack tests

def test_model_router_falls_back_when_gateway_down(monkeypatch):
    from stack.l2_mesh import model_router
    monkeypatch.setattr(model_router, "INFERENCE_URL", "http://127.0.0.1:1")
    intent, route = model_router.extract("my broadband keeps dropping out", None)
    assert intent["intentType"] == "fault-report" and route["route"] == "deterministic-fallback"

def test_parser_budget():
    from stack.l2_mesh import model_router
    d = model_router.deterministic("I want something faster under £50")
    assert d["intentType"] == "broadband-upgrade" and d["budgetGBP"] == 50

# ---------- OPA and Operaton never call a model (static check)
DETERMINISTIC = ["stack/l4_context/app.py", "stack/l5_orchestrator/workers.py", "stack/l5_orchestrator/engine.py",
                 "stack/l5_orchestrator/state.py", "stack/l5_orchestrator/app.py", "stack/l5_orchestrator/bootstrap.py"]

@pytest.mark.parametrize("path", DETERMINISTIC)
def test_deterministic_layers_import_no_model_client(path):
    src = (ROOT / path).read_text()
    mods = set()
    for n in ast.walk(ast.parse(src)):
        if isinstance(n, ast.Import):
            mods |= {a.name for a in n.names}
        elif isinstance(n, ast.ImportFrom):
            mods.add(n.module or "")
    banned = ("model_router", "litellm", "openai", "ollama", "stack.inference", "langchain")
    assert not [m for m in mods if any(b in m for b in banned)], mods
    assert "INFERENCE_URL" not in src and "/v1/chat/completions" not in src and ":11434" not in src and ":4000" not in src

def test_rego_has_no_http_send():
    for p in (ROOT / "stack").rglob("*.rego"):
        assert "http.send" not in p.read_text(), p

def test_bpmn_has_no_script_or_ai_tasks():
    x = (ROOT / "stack/l5_orchestrator/bpmn/broadband-upgrade-saga.bpmn").read_text()
    assert "scriptTask" not in x and "operaton:class" not in x and "connector" not in x.lower()

# ---------- BPMN saga shape
NS = {"bpmn": "http://www.omg.org/spec/BPMN/20100524/MODEL"}
def _bpmn():
    return ET.parse(ROOT / "stack/l5_orchestrator/bpmn/broadband-upgrade-saga.bpmn").getroot()

def test_bpmn_every_sor_write_has_policy_blocked_path_and_compensation():
    r = _bpmn()
    tasks = {t.get("id"): t for t in r.iter("{%s}serviceTask" % NS["bpmn"])}
    bnd = list(r.iter("{%s}boundaryEvent" % NS["bpmn"]))
    attached = lambda tid, kind: [b for b in bnd if b.get("attachedToRef") == tid and b.find("bpmn:" + kind, NS) is not None]
    for tid in ("Task_CreateOrder", "Task_Complete", "Task_Inventory"):
        assert attached(tid, "errorEventDefinition"), f"{tid} lacks a Policy blocked error path"
    for tid in ("Task_CreateOrder", "Task_Activate"):
        assert attached(tid, "compensateEventDefinition"), f"{tid} lacks compensation"
    ends = {e.get("id") for e in r.iter("{%s}endEvent" % NS["bpmn"])}
    assert {"End_Completed", "End_Compensated", "End_PolicyBlocked"} <= ends
    assert all(t.get("{http://operaton.org/schema/1.0/bpmn}type") == "external" for t in tasks.values())

def test_bpmn_di_present_for_bpmn_js():
    x = (ROOT / "stack/l5_orchestrator/bpmn/broadband-upgrade-saga.bpmn").read_text()
    assert "bpmndi:BPMNDiagram" in x and x.count("bpmndi:BPMNShape") >= 10

# ---------- GraphQL is read-only (ADR-008)
def test_graphql_schema_has_no_mutation():
    from stack.l1_web.graphql_api import schema
    sdl = schema.as_str()
    assert "type Mutation" not in sdl and "type Query" in sdl

def test_graphql_module_issues_no_writes():
    src = (ROOT / "stack/l1_web/graphql_api.py").read_text()
    assert not re.search(r'call\([^)]*"(POST|PUT|PATCH|DELETE)"', src)
    assert not re.search(r"\b(insert|update|delete)\b\s", re.sub(r'""".*?"""', "", src, flags=re.S), re.I)

# ---------- licences / OSI-only (ADR-002, steering)
def test_no_banned_components():
    lines = [l.split("#")[0].strip().lower() for f in ("requirements.txt", "requirements-litellm.txt")
             for l in (ROOT / f).read_text().splitlines()]
    pkgs = {re.split(r"[=<>\[ ]", l)[0] for l in lines if l}
    for bad in ("temporalio", "nats-py", "apollo-router", "redpanda", "camunda", "restate-sdk", "litellm-enterprise", "langfuse-ee"):
        assert bad not in pkgs, bad
    code = "\n".join(p.read_text() for p in (ROOT / "stack").rglob("*.py"))
    assert "temporalio" not in code and not re.search(r"\bnats\b", code, re.I)

def test_operaton_secrets_not_in_repo_files():
    for p in [ROOT / "stack/l5_orchestrator/operaton/production.yml", ROOT / "run.sh", ROOT / "Procfile"]:
        assert not re.search(r"password:\s*\S{8,}", p.read_text(), re.I) or "${" in p.read_text()
