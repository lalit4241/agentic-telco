"""Check the recorded MVP runs (recordings/mvp/*.json) against the Salesforce org and the accepted business decisions.
Read-only: SOQL queries only. Usage (repo root): PYTHONPATH=. .venv/bin/python scripts/mvp/verify_recordings.py"""
import json, pathlib, re, sys
from urllib.parse import quote
from stack.zg_common.sf_session import request as sfr, API_V

ROOT = pathlib.Path(__file__).resolve().parents[2]
R = {c: json.loads((ROOT / "recordings" / "mvp" / f"{c}.json").read_text()) for c in ("happy", "notauth", "overdue", "delayed")}
fails = []
def check(ok, msg):
    print(("PASS " if ok else "FAIL ") + msg); ok or fails.append(msg)
def q(s):
    return sfr("GET", f"/services/data/{API_V}/query?q=" + quote(s)).json()["records"]
def text(c):
    return "\n".join(m["content"] for m in R[c]["state"]["messages"] if m["role"] != "user")
def nice(d):
    import datetime as dt; d = dt.date.fromisoformat(d[:10]); return f"{d.day} {d.strftime('%B %Y')}"

for c in ("happy", "delayed"):
    s = R[c]["state"]; L = s["links"]; ev = [r for r in s["reports"] if r["expression"]["expressionValue"].get("icm:reportState") == "icm:StateComplies"]
    check(s["intent"]["lifecycle_status"] == "fulfilled", f"{c}: intent fulfilled")
    live = ev[-1]["expression"]["expressionValue"]["liveDate"][:10]
    check("Fibre 900" in text(c) and "£45" in text(c) and "28 August 2027" in text(c), f"{c}: offer says Fibre 900, £45, contract end 28 August 2027")
    check(nice(live) in text(c), f"{c}: live message uses the live date {nice(live)}")
    new = L["newAsset"].split("/")[-2]; old = L["oldAsset"].split("/")[-2]; oid = L["order"].split("/")[-2]
    a = q(f"select Name, Status, InstallDate, UsageEndDate, Price, Product2.Name from Asset where Id in ('{new}','{old}')")
    na = next(x for x in a if x["Product2"]["Name"].endswith("900")); oa = next(x for x in a if x["Product2"]["Name"].endswith("150"))
    later = c != "delayed"   # each case resets to the seed, so an earlier run's Fibre 900 asset is Obsolete after the next run
    check(na["Status"] in (("Installed", "Obsolete") if later else ("Installed",)) and na["InstallDate"] == live and na["UsageEndDate"] == "2027-08-28" and float(na["Price"]) == 45.0,
          f"{c}: new asset Installed, InstallDate={na['InstallDate']} (live {live}), UsageEndDate={na['UsageEndDate']}, £{na['Price']}")
    check(oa["Status"] == "Obsolete", f"{c}: Fibre 150 asset {oa['Status']}")
    wrote = json.dumps([sp.get("request") for sp in s["spans"]])
    check('"Obsolete"' in wrote and '"Installed"' in wrote, f"{c}: the run itself wrote Fibre 150 -> Obsolete and Fibre 900 -> Installed (status now {na['Status']})")
    o = q(f"select Status, OrderNumber, (select Product2.Name, UnitPrice from OrderItems) from Order where Id='{oid}'")[0]
    check(o["Status"] == "Activated" and all(float(i["UnitPrice"]) == 45.0 for i in o["OrderItems"]["records"]), f"{c}: order {o['OrderNumber']} {o['Status']} at £45")
    check(any("TMF671" in (sp.get("api") or "") for sp in s["spans"]), f"{c}: TMF671 promotion read in the trace")
    fca = [m for m in s.get("milestones", []) if m["name"] == "AssetChanged"]
    check(bool(fca) and json.dumps(fca[-1]).count('"flowCreatedAssets": 0') == 1, f"{c}: Custom_Assetize_Order created no assets (flowCreatedAssets = 0)")
d = R["delayed"]["state"]
rev = [j for j in d["jeopardy"]][-1]
revd = json.dumps(rev)
live = [r for r in d["reports"] if r["expression"]["expressionValue"].get("icm:reportState") == "icm:StateComplies"][-1]["expression"]["expressionValue"]["liveDate"][:10]
check(live in revd, f"delayed: revised date in the jeopardy equals the live date {live}")
msgs = d["messages"]; i_delay = next(i for i, m in enumerate(msgs) if m["role"] != "user" and re.search(r"delay|risk|two more days", m["content"], re.I))
i_live = max(i for i, m in enumerate(msgs) if m["role"] != "user" and re.search(r"live", m["content"], re.I))
check(i_delay < i_live and nice(live) in msgs[i_delay]["content"], f"delayed: Sam told the delay (with {nice(live)}) before go-live")
check("Sam" in text("notauth") and not (R["notauth"]["state"].get("links") or {}).get("order"), "notauth: points to Sam, no order")
ot = text("overdue")
check(re.search(r"overdue|outstanding", ot, re.I) and not re.search(r"not authori|available at", ot, re.I) and not (R["overdue"]["state"].get("links") or {}).get("order"),
      "overdue: only the overdue reason, no order")
print("FAILED:" if fails else "ALL PASS", len(fails)); sys.exit(1 if fails else 0)
