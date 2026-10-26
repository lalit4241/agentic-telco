#!/usr/bin/env python3
"""Repeatable, idempotent seed of the four AgenticTelco demo customers into the sfcomms org.

Standard objects only (Account + Contact + Asset) via OOTB sObject REST through the Salesforce CLI – no token handled, no Apex.
Every record carries the AgenticTelco prefix; existing records are reused, never modified or deleted.
Demo customer ids (C-1001..C-1004) are kept in the standard Account.AccountNumber field as 'AT-C-100x' so that L6 can map
the agent-facing ids to Salesforce ids. Data is synthetic (example.com addresses).
Usage: .venv/bin/python seed/customers/seed_customers.py   → writes seed/customers/last-run.json (ids only).
       add --reset-inventory to put the AgenticTelco demo inventory back to the baseline before a recorded run: each demo
       customer's seeded Fibre 150 Asset → Installed, AgenticTelco Assets created by earlier journey runs → Obsolete
       (only AgenticTelco demo Assets on AgenticTelco demo Accounts are touched; nothing is deleted)."""
import json, os, sys
from urllib.parse import quote
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)
from stack.zg_common.sf_session import request, API_V
D = f"/services/data/{API_V}"

CUSTOMERS = [
    dict(cid="C-1001", first="Arthur", last="Bennett", street="14 Elm Row", city="Leeds", pc="LS6 2AB"),
    dict(cid="C-1002", first="David", last="Okafor", street="3 Canal Wharf", city="Manchester", pc="M4 7HR"),
    dict(cid="C-1003", first="Priya", last="Shah", street="88 Queens Rd", city="Bristol", pc="BS8 1QU"),
    dict(cid="C-1004", first="Sarah", last="Mitchell", street="21 Mill Lane", city="York", pc="YO1 9TX"),
]

def soql(s):
    r = request("GET", f"{D}/query?q=" + quote(s))
    if r.status_code != 200:
        raise SystemExit(f"SOQL failed {r.status_code}: {r.text[:300]}")
    return r.json()["records"]

def ensure(obj, where, fields):
    rows = soql(f"SELECT Id FROM {obj} WHERE {where} LIMIT 1")
    if rows:
        return rows[0]["Id"], False
    r = request("POST", f"{D}/sobjects/{obj}", fields)
    j = r.json()
    if r.status_code not in (200, 201) or not isinstance(j, dict) or not j.get("id"):
        raise SystemExit(f"! {obj} {where}: {r.status_code} {str(j)[:300]} – rerun (idempotent)")
    return j["id"], True

def main():
    out, n_created = {}, 0
    rows = soql("SELECT Id FROM Product2 WHERE ProductCode='AT-FIBRE-150' AND Name LIKE 'AgenticTelco%' LIMIT 1")
    if not rows:
        raise SystemExit("run seed/epc/seed_epc.py first (AT-FIBRE-150 missing)")
    fib150 = rows[0]["Id"]
    for c in CUSTOMERS:
        name = f"AgenticTelco Demo – {c['first']} {c['last']}"
        acc, a_new = ensure("Account", f"AccountNumber='AT-{c['cid']}' AND Name LIKE 'AgenticTelco%'", dict(
            Name=name, AccountNumber=f"AT-{c['cid']}", Type="Customer", BillingStreet=c["street"], BillingCity=c["city"],
            BillingPostalCode=c["pc"], BillingCountry="United Kingdom", Description="AgenticTelco demo customer (synthetic)"))
        con, c_new = ensure("Contact", f"AccountId='{acc}' AND LastName='{c['last']}'", dict(
            AccountId=acc, FirstName=c["first"], LastName=c["last"], Email=f"{c['first'].lower()}.{c['last'].lower()}@example.com",
            Description="AgenticTelco demo contact (synthetic)"))
        # current broadband line (the upgrade journeys start from it) – standard Asset, read back through native TMF637
        asset, s_new = ensure("Asset", f"AccountId='{acc}' AND SerialNumber='AT-PI-{c['cid'][2:]}' AND Name LIKE 'AgenticTelco%'", dict(
            Name=f"AgenticTelco Fibre 150 – {c['cid']}", AccountId=acc, ContactId=con, Product2Id=fib150, Status="Installed",
            Quantity=1, SerialNumber=f"AT-PI-{c['cid'][2:]}", Description="AgenticTelco demo product inventory (synthetic)"))
        n_created += a_new + c_new + s_new
        print(("+" if a_new else "="), c["cid"], acc, ("+" if c_new else "="), con, ("+" if s_new else "="), asset)
        if "--reset-inventory" in sys.argv:
            for a in soql(f"SELECT Id, Status, SerialNumber FROM Asset WHERE AccountId='{acc}' AND Name LIKE 'AgenticTelco%'"):
                want = "Installed" if a["Id"] == asset else "Obsolete"
                if a["Status"] != want:
                    r = request("PATCH", f"{D}/sobjects/Asset/{a['Id']}", {"Status": want})
                    print("   reset", a["Id"], a["Status"], "→", want, r.status_code)
        out[c["cid"]] = dict(accountId=acc, contactId=con, assetId=asset, partyId="P-" + c["cid"][2:], name=f"{c['first']} {c['last']}")
    json.dump(dict(customers=out, created=n_created), open(os.path.join(os.path.dirname(__file__), "last-run.json"), "w"), indent=1)

if __name__ == "__main__":
    main()
