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
    assert "Salesforce native APIs plus a thin TMF facade layer within Salesforce" in json.dumps(c)


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
