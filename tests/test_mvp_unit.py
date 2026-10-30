"""MVP unit tests (no services needed): copy, BPMN shape, trace helpers, date logic, semantic model, policy, intent schema."""
import json, re, xml.etree.ElementTree as ET
from datetime import date
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parent.parent
MVP = ROOT / "stack" / "mvp"


def test_copy_json_has_8_layers_and_27_terms():
    c = json.loads((ROOT / "web" / "src" / "mvp" / "copy.json").read_text())
    assert [l["id"] for l in c["layers"]] == [f"L{i}" for i in range(1, 9)]
    assert len(c["glossary"]) == 27
    assert "TM Forum Open APIs exposed by Salesforce: two out of the box, the rest through a thin TMF facade layer within Salesforce" in json.dumps(c)
    assert "native Salesforce API" not in json.dumps(c)


def test_bpmn_has_the_business_steps_and_a_diagram():
    x = (MVP / "bpmn" / "agentictelco-mvp-upgrade.bpmn").read_text()
    root = ET.fromstring(x)
    ns = {"b": "http://www.omg.org/spec/BPMN/20100524/MODEL"}
    p = root.find("b:process", ns)
    assert p.get("isExecutable") == "true"
    names = " ".join((e.get("name") or "") for e in p.iter())
    for step in ["Binding policy check", "Create quote", "Place upgrade order", "legacy OSS", "jeopardy", "Complete order", "Asset change", "Intent fulfilled"]:
        assert re.search(step, names, re.I), step
    assert "bpmndi:BPMNShape" in x


def test_traceparent_round_trip():
    from stack.mvp.common import new_trace, new_span, traceparent, parse_traceparent
    t, s = new_trace(), new_span()
    assert len(t) == 32 and len(s) == 16
    assert parse_traceparent(traceparent(t, s)) == (t, s)


def test_contract_months_left_from_today_to_end():
    from stack.mvp.context import months_between
    assert months_between(date(2026, 10, 30), date(2027, 8, 28)) == 9
    assert months_between(date(2027, 8, 28), date(2027, 8, 28)) == 0


def test_semantic_model_defines_policy_terms():
    txt = "".join(p.read_text() for p in (MVP / "semantic").glob("*")).lower()
    for term in ["authorised", "overdue", "available"]:
        assert term in txt, term


def test_policy_version_and_deny_codes():
    rego = (MVP / "policy" / "upgrade.rego").read_text()
    assert "mvp-2026-10-30.1" in rego
    for code in ["not_authorised", "overdue_balance", "not_available_at_site", "downgrade_mid_contract"]:
        assert code in rego


def test_intent_schema_is_tmf921_shaped():
    s = json.loads((MVP / "intent.schema.json").read_text())
    assert "expression" in json.dumps(s)


# ---- Salesforce IDs are checked before they go into a TMF API path or filter (review item 4) ----
from stack.mvp.common import sf_id, safe_key


@pytest.mark.parametrize("good", ["001QH00002La125YAB", "001QH00002La125", "02iQH000003GH4nYAG", "801QH00002LZvb2YAD"])
def test_sf_id_accepts_real_15_and_18_char_ids(good):
    assert sf_id(good) == good


@pytest.mark.parametrize("bad", [
    "001QH00002La125YAC",            # 18 chars, wrong case-safe checksum
    "001QH00002La12",                # 14 chars
    "001QH00002La125YA",             # 17 chars
    "001QH00002La125YABX",           # 19 chars
    "001QH00002La1' OR Name!='x",    # SOQL injection attempt
    "001QH00002La125YAB'--",
    "", None, 123,
])
def test_sf_id_rejects_anything_else(bad):
    with pytest.raises(ValueError):
        sf_id(bad)


def test_business_key_guard():
    assert safe_key("MVP-60744BC6") == "MVP-60744BC6"
    for bad in ["MVP-1' OR 'a'='a", "", "x" * 65]:
        with pytest.raises(ValueError):
            safe_key(bad)


def test_context_service_returns_400_for_a_bad_id():
    from fastapi import HTTPException
    from stack.mvp.context import ids_or_400, AUTH_ROLE
    assert AUTH_ROLE == "Decision Maker"     # read from semantic/model.yaml
    with pytest.raises(HTTPException) as e:
        ids_or_400(accountId="001' OR Id!='")
    assert e.value.status_code == 400


def test_authorised_role_is_not_hard_coded():
    ctx = (MVP / "context.py").read_text()
    assert "Role == 'Decision Maker'" not in ctx and "Role='Decision Maker'" not in ctx and '== "Decision Maker"' not in ctx


# ---- TM Forum Open APIs only above the systems-of-record layer (no SOQL, no sObject REST) ----
FORBIDDEN = [
    (r"/query\?q=|/queryAll|/search\?q=", "SOQL/SOSL query endpoint"),
    (r"/sobjects\b|/composite\b|/tooling/", "Salesforce sObject / composite / tooling REST"),
    (r"\bSELECT\s+[\w.,\s]+\s+FROM\s+\w+", "SOQL statement"),
    (r"\bsoql\s*\(", "soql() helper"),
    (r"zg_common\.sf_session|from stack\.zg_common import sf_session|sf_session\.request", "direct Salesforce session call (bypasses the TMF guard)"),
]


def _mvp_sources():
    return sorted(p for p in MVP.rglob("*.py") if "__pycache__" not in p.parts)


def test_mvp_stack_issues_no_soql_or_sobject_rest():
    """Fails if anything in the MVP stack (L1-L5 services, workers, gateway) reaches Salesforce outside the TMF Open APIs."""
    hits = []
    for p in _mvp_sources():
        src = p.read_text()
        for pat, what in FORBIDDEN:
            for m in re.finditer(pat, src):
                line = src[:m.start()].count("\n") + 1
                if p.name == "common.py" and "_sf_request" in src.splitlines()[line - 1]:
                    continue
                hits.append(f"{p.relative_to(ROOT)}:{line}: {what}: {m.group(0)[:60]}")
    # the one allowed import of the session is the guarded wrapper in common.py
    assert hits == [], "\n".join(hits)


def test_sf_calls_are_tmf_only_at_runtime():
    from stack.mvp.common import provided_by, APEX, CC, SF_DATA, OOTB, FACADE, tmf
    assert provided_by(f"{APEX}/tmf637/product?relatedParty.id=1") == FACADE
    assert provided_by(f"{CC}/customermanagement/v4/customer/1") == OOTB
    for bad in [f"{SF_DATA}/query?q=SELECT+Id+FROM+Asset", f"{SF_DATA}/sobjects/Asset/1", "/services/apexrest/other/x", f"{SF_DATA}/connect/other"]:
        with pytest.raises(ValueError):
            provided_by(bad)
    assert tmf("TMF622") == "TMF622 Product Order"


def test_the_scan_catches_a_regression(tmp_path):
    bad = 'r = sf_session.request("GET", "/services/data/v62.0/sobjects/Asset/x")\nsoql(t, "x", "SELECT Id FROM Asset")\n'
    found = [what for pat, what in FORBIDDEN if re.search(pat, bad)]
    assert len(found) >= 3


def test_no_native_salesforce_label_left():
    for p in _mvp_sources() + [ROOT / "web" / "src" / "mvp" / "mvp.js"]:
        assert "native Salesforce API" not in p.read_text(), p
        assert not re.search(r"\b(conformant|certified)\b", p.read_text().replace("not certified", ""), re.I), p


def test_redaction():
    from stack.mvp.common import redact
    r = redact({"Authorization": "Bearer abc", "x": "https://acme.my.salesforce.com/secur/frontdoor.jsp?sid=00D000000000001!AQ.xyz",
                "link": "https://acme.lightning.force.com/lightning/r/Asset/02i/view", "promptTokens": 5, "sid": "s"})
    assert r["Authorization"] == "[redacted]" and r["sid"] == "[redacted]" and r["promptTokens"] == 5
    assert "acme.my.salesforce.com" not in r["x"] and "sid=" not in r["x"] and "00D" not in r["x"]
    assert r["link"].endswith("/lightning/r/Asset/02i/view")
