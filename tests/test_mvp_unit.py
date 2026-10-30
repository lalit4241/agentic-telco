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


# ---- Salesforce IDs are checked before they go into a SOQL string (review item 4) ----
from stack.mvp.common import sf_id, safe_key, soql_datetime


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


def test_business_key_and_datetime_guards():
    assert safe_key("MVP-60744BC6") == "MVP-60744BC6"
    assert soql_datetime("2026-10-30T17:05:08.123+00:00") == "2026-10-30T17:05:08"
    for bad in ["MVP-1' OR 'a'='a", "", "x" * 65]:
        with pytest.raises(ValueError):
            safe_key(bad)
    with pytest.raises(ValueError):
        soql_datetime("2026-10-30 OR Id != null")


def test_context_service_returns_400_for_a_bad_id():
    from fastapi import HTTPException
    from stack.mvp.context import ids_or_400, AUTH_ROLE
    assert AUTH_ROLE == "Decision Maker"     # read from semantic/model.yaml
    with pytest.raises(HTTPException) as e:
        ids_or_400(accountId="001' OR Id!='")
    assert e.value.status_code == 400


def test_no_soql_string_takes_an_unchecked_id():
    import re as _re
    ctx = (MVP / "context.py").read_text()
    wk = (MVP / "workers.py").read_text()
    assert "Role == 'Decision Maker'" not in ctx and "Role='Decision Maker'" not in ctx and '== "Decision Maker"' not in ctx
    assert not _re.search(r"WHERE[^\"]*'\{v\[", wk), "workers.py puts a raw variable into SOQL"
    assert not _re.search(r"\+ b\[\"(accountId|contactId)\"\]", ctx), "context.py puts a raw request field into SOQL"
