#!/usr/bin/env python3
"""MVP build step 2: idempotent seed of the Brightwell Design Ltd B2B test customer into the sfcomms org.

Standard objects only, via OOTB sObject REST through the Salesforce CLI (no token handled):
  Account · 2 Contacts · 2 AccountContactRole (Sam = Decision Maker, Alex = Business User) · Location (site 4471,
  ExternalReference = address key A00000001975) · Address · Fibre 150 Asset at that Location.
Every record except the Account (named Brightwell Design Ltd, keyed by AccountNumber AT-B-BRIGHTWELL) carries the AgenticTelco prefix; existing records are reused, never deleted. Data is synthetic.
  --reset   put the demo back to the baseline before a recorded run: the seeded Fibre 150 Asset → Installed (contract end
            date restored) and Assets created by earlier MVP runs on this Account → Obsolete. Only AgenticTelco Assets on the
            Brightwell Account (AccountNumber AT-B-BRIGHTWELL) are touched; nothing is deleted.
Writes seed/customers/brightwell.json (ids only)."""
import json, os, sys
from urllib.parse import quote
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)
from stack.zg_common.sf_session import request, API_V
D = f"/services/data/{API_V}"
ACC_NO = "AT-B-BRIGHTWELL"
ADDRESS_KEY = "A00000001975"
CONTRACT_END = "2027-08-28"   # 24-month term; Asset end date stands in for the agreement (MVP-KEY-DESIGN Appendix A)

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

def patch(obj, rid, fields):
    r = request("PATCH", f"{D}/sobjects/{obj}/{rid}", fields)
    if r.status_code not in (200, 204):
        raise SystemExit(f"! PATCH {obj} {rid}: {r.status_code} {r.text[:300]}")

def main():
    fib150 = soql("SELECT Id FROM Product2 WHERE ProductCode='AT-FIBRE-150' AND Name LIKE 'AgenticTelco%' LIMIT 1")
    if not fib150:
        raise SystemExit("run seed/epc/seed_epc.py first (AT-FIBRE-150 missing)")
    fib150 = fib150[0]["Id"]
    log = []
    acc, n = ensure("Account", f"AccountNumber='{ACC_NO}'", dict(
        Name="Brightwell Design Ltd", AccountNumber=ACC_NO, Type="Customer", Industry="Media",
        BillingStreet="1 Fibre Way, Martlesham", BillingCity="Ipswich", BillingPostalCode="IP5 3RE", BillingCountry="United Kingdom",
        Description="AgenticTelco MVP B2B demo customer (synthetic). Legacy billing account BIL-B-0077812."))
    log.append(("Account", acc, n))
    people = {}
    for key, first, last, role, title in [("sam", "Sam", "Taylor", "Decision Maker", "Operations Director"),
                                          ("alex", "Alex", "Reed", "Business User", "Designer")]:
        con, n = ensure("Contact", f"AccountId='{acc}' AND FirstName='{first}' AND LastName='{last}'", dict(
            AccountId=acc, FirstName=first, LastName=last, Title=title, Email=f"{first.lower()}.{last.lower()}@brightwell.example.com",
            Description="AgenticTelco MVP demo contact (synthetic)"))
        log.append(("Contact " + first, con, n))
        acr, n = ensure("AccountContactRole", f"AccountId='{acc}' AND ContactId='{con}'", dict(AccountId=acc, ContactId=con, Role=role))
        log.append(("AccountContactRole " + role, acr, n))
        people[key] = dict(contactId=con, role=role, roleId=acr, name=f"{first} {last}")
    loc, n = ensure("Location", f"ExternalReference='{ADDRESS_KEY}' AND Name LIKE 'AgenticTelco%'", dict(
        Name="AgenticTelco Site 4471 – Brightwell, Martlesham", LocationType="Site", ExternalReference=ADDRESS_KEY,
        IsInventoryLocation=False, Description="AgenticTelco MVP site 4471 (synthetic). Address key A00000001975."))
    log.append(("Location", loc, n))
    addr, n = ensure("Address", f"ParentId='{loc}'", dict(ParentId=loc, LocationType="Site", AddressType="Shipping",
        Street="1 Fibre Way, Martlesham", City="Ipswich", PostalCode="IP5 3RE", Country="United Kingdom"))
    log.append(("Address", addr, n))
    if not soql(f"SELECT VisitorAddressId FROM Location WHERE Id='{loc}'")[0]["VisitorAddressId"]:
        patch("Location", loc, {"VisitorAddressId": addr})
    asset, n = ensure("Asset", f"AccountId='{acc}' AND SerialNumber='AT-PI-B4471' AND Name LIKE 'AgenticTelco%'", dict(
        Name="AgenticTelco Fibre 150 – Brightwell site 4471", AccountId=acc, ContactId=people["sam"]["contactId"], Product2Id=fib150,
        Status="Installed", Quantity=1, Price=27, SerialNumber="AT-PI-B4471", LocationId=loc, InstallDate="2025-08-28", UsageEndDate=CONTRACT_END,
        Street="1 Fibre Way, Martlesham", City="Ipswich", PostalCode="IP5 3RE", Country="United Kingdom",
        Description="AgenticTelco MVP: Fibre 150 on a 24-month term (synthetic)"))
    log.append(("Asset Fibre 150", asset, n))
    if "--reset" in sys.argv:
        for a in soql(f"SELECT Id, Status, UsageEndDate FROM Asset WHERE AccountId='{acc}' AND Name LIKE 'AgenticTelco%'"):
            if a["Id"] == asset:
                if a["Status"] != "Installed" or a["UsageEndDate"] != CONTRACT_END:
                    patch("Asset", a["Id"], {"Status": "Installed", "UsageEndDate": CONTRACT_END}); print("  reset", a["Id"], "→ Installed")
            elif a["Status"] != "Obsolete":
                patch("Asset", a["Id"], {"Status": "Obsolete"}); print("  reset", a["Id"], "→ Obsolete")
    for name, rid, new in log:
        print("+" if new else "=", name, rid)
    out = dict(accountId=acc, accountNumber=ACC_NO, billingAccount="BIL-B-0077812", site="4471", addressKey=ADDRESS_KEY,
               locationId=loc, addressId=addr, assetId=asset, contacts=people)
    json.dump(out, open(os.path.join(os.path.dirname(__file__), "brightwell.json"), "w"), indent=1)

if __name__ == "__main__":
    main()
