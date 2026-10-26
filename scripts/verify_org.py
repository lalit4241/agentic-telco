#!/usr/bin/env python3
"""Read-only capability probe of the connected Salesforce Comms Cloud org (alias $SF_TARGET_ORG, default sfcomms).

* Every call goes through the Salesforce CLI (`sf api request rest`), so no token is ever handled, printed or stored.
* Only GET requests, plus one GraphQL *read* query (POST is GraphQL's transport; it cannot write).
* A 405 on a GET for a POST-only resource is evidence the resource exists; 404 NOT_FOUND means not exposed.
Writes docs/api/org-capabilities.json (raw evidence, sanitised). docs/api/org-capabilities.md is hand-written from it and is never overwritten."""
import json, os, re, sys, datetime
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import quote
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from stack.zg_common.sf_session import request, API_V

D = f"/services/data/{API_V}"
CC = f"{D}/connect/comms"
A = "/services/apexrest"
NS = ["vlocity_cmt", ""]   # managed-package namespace, and unmanaged / no namespace

def apex(ns, tail): return f"{A}/{ns + '/' if ns else ''}{tail}"

PROBES = {
 "TMF620": [("Direct Access v5 (guess)", f"{CC}/productcatalogmanagement/v5/productOffering"),
            ("Direct Access v4 (guess)", f"{CC}/productCatalogManagement/v4/productOffering")]
           + [(f"Managed package {ns or 'no-ns'} v4", apex(ns, "tmforum/productopenapi/v1/productOffering")) for ns in NS]
           + [("Industries PCM catalogs", f"{D}/connect/pcm/catalogs")],
 "TMF621": [("Direct Access v4 (guess)", f"{CC}/troubleTicket/v4/troubleTicket"),
            ("Direct Access v5 (guess)", f"{CC}/troubleticketmanagement/v5/troubleTicket")]
           + [(f"Managed package {ns or 'no-ns'}", apex(ns, "tmforum/troubleTicket/v1/troubleTicket")) for ns in NS],
 "TMF622": [("Direct Access v5", f"{CC}/productOrderingManagement/v5/productOrder?pageLimit=2")]
           + [(f"Managed package {ns or 'no-ns'} v4", apex(ns, "tmforum/productopenapi/v1/productorder")) for ns in NS],
 "TMF629": [("Direct Access v4", f"{CC}/customermanagement/v4/customer?limit=2")],
 "TMF632": [("Direct Access v5 individual (guess)", f"{CC}/partymanagement/v5/individual"),
            ("Direct Access v5 organization (guess)", f"{CC}/partymanagement/v5/organization"),
            ("Direct Access v5 individual (guess, camel)", f"{CC}/partyManagement/v5/individual")],
 "TMF637": [("Direct Access v5", f"{CC}/productinventorymanagement/v5/productinventory?limit=2")]
           + [(f"Managed package {ns or 'no-ns'} v4", apex(ns, "tmforum/productopenapi/v1/product")) for ns in NS],
 "TMF648": [("Direct Access v4 (guess)", f"{CC}/quoteManagement/v4/quote"),
            ("Direct Access v5 (guess)", f"{CC}/quotemanagement/v5/quote")]
           + [(f"Managed package {ns or 'no-ns'}", apex(ns, "tmforum/quoteManagement/v1/quote")) for ns in NS],
 "TMF651": [("Direct Access v4 (guess)", f"{CC}/agreementManagement/v4/agreement"),
            ("Direct Access v4 (guess, lower)", f"{CC}/agreementmanagement/v4/agreement")],
 "TMF667": [("Direct Access v4", f"{CC}/document/v4/document")],
 "TMF671": [("Direct Access v4", f"{CC}/promotionManagement/v4/promotion")],
 "TMF679": [("Direct Access v5 check (POST-only)", f"{CC}/productofferingqualification/v5/checkProductOfferingQualification"),
            ("Direct Access v5 query (POST-only)", f"{CC}/productofferingqualification/v5/queryProductOfferingQualification")],
}
SOBJECTS = ["Account", "Contact", "BillingAccount", "Product2", "ProductCatalog", "ProductSellingModel", "Order", "OrderItem",
            "Quote", "Asset", "Contract", "Promotion", "Case", "ContentDocument"]
SOBJ_FOR = {"TMF620": ["Product2", "ProductCatalog"], "TMF621": ["Case"], "TMF622": ["Order", "OrderItem"], "TMF629": ["Account"],
            "TMF632": ["Account", "Contact"], "TMF637": ["Asset"], "TMF648": ["Quote"], "TMF651": ["Contract"],
            "TMF667": ["ContentDocument"], "TMF671": ["Promotion"], "TMF679": ["Product2"]}

def evidence(r):
    j = r.json()
    if isinstance(j, list) and j and isinstance(j[0], dict) and "errorCode" in j[0]:
        return f"{j[0]['errorCode']}: {j[0].get('message','')[:160]}"
    if isinstance(j, dict):
        if "errorCode" in j: return f"{j['errorCode']}: {str(j.get('message',''))[:160]}"
        keys = list(j.keys())[:6]
        return "JSON object keys " + ", ".join(keys)
    if isinstance(j, list): return f"JSON array, {len(j)} item(s)" + (f"; first keys {', '.join(list(j[0].keys())[:6])}" if j and isinstance(j[0], dict) else "")
    return (r.text or "")[:160].replace("\n", " ")

def verdict(status, ev, post_only=False):
    if status == 200: return "exposed"
    if status == 405 and post_only: return "exposed (POST-only)"
    if status in (400, 405): return "exposed (request shape rejected)"
    if status == 403: return "exists, not permitted"
    if status == 404: return "not exposed"
    if status == 401: return "auth error"
    return "unclear"

def scrub(s):
    return re.sub(r"\b00D[A-Za-z0-9]{12,15}\b", "00D…", s)

def probe(item):
    api, label, path = item
    r = request("GET", path)
    ev = scrub(evidence(r))
    return dict(api=api, label=label, method="GET", path=path, status=r.status_code, evidence=ev,
                verdict=verdict(r.status_code, ev, "POST-only" in label))

def sobject_count(name):
    r = request("GET", f"{D}/query?q=" + quote(f"SELECT COUNT() FROM {name}"))
    j = r.json() or {}
    return name, r.status_code, (j.get("totalSize") if isinstance(j, dict) else None)

def graphql():
    q = {"query": "query { uiapi { query { Account(first: 3) { edges { node { Id Name { value } } } } } } }"}
    r = request("POST", f"{D}/graphql", q)
    j = r.json() or {}
    edges = (((j.get("data") or {}).get("uiapi") or {}).get("query") or {}).get("Account", {}).get("edges", []) if isinstance(j, dict) else []
    return dict(api="GraphQL", label="UI API GraphQL read query (Account, first 3)", method="POST (read query)", path=f"{D}/graphql",
                status=r.status_code, evidence=f"{len(edges)} Account edge(s) returned; errors={bool(j.get('errors')) if isinstance(j, dict) else 'n/a'}",
                verdict="exposed" if r.status_code == 200 and edges is not None and not (isinstance(j, dict) and j.get("errors")) else "unclear")

def main():
    items = [(api, l, p) for api, lst in PROBES.items() for l, p in lst]
    with ThreadPoolExecutor(6) as ex:
        rows = list(ex.map(probe, items))
        counts = list(ex.map(sobject_count, SOBJECTS))
    gq = graphql()
    pk = request("GET", f"{D}/query?q=" + quote("SELECT NamespacePrefix FROM PackageLicense")).json() or {}
    namespaces = sorted(x["NamespacePrefix"] for x in pk.get("records", []))
    now = datetime.datetime.now().astimezone()
    summary = {}
    for api in PROBES:
        rs = [r for r in rows if r["api"] == api]
        best = next((r for r in rs if r["verdict"].startswith("exposed")), None)
        summary[api] = dict(live=bool(best), path=best["path"] if best else None, label=best["label"] if best else None,
                            statuses={r["label"]: r["status"] for r in rs})
    out = dict(generatedAt=now.isoformat(timespec="seconds"), org="00DQH00000P7uDa (alias sfcomms)",
               instance="https://<my-domain>.my.salesforce.com (withheld)", apiVersion=API_V, method="sf api request rest (Salesforce CLI); read-only",
               installedPackageNamespaces=namespaces, probes=rows, graphql=gq,
               sobjects={n: dict(status=s, count=c) for n, s, c in counts}, summary=summary)
    os.makedirs("docs/api", exist_ok=True)
    json.dump(out, open("docs/api/org-capabilities.json", "w"), indent=2)
    print(json.dumps(summary, indent=1)); print(gq); print(counts); print(namespaces)

if __name__ == "__main__":
    main()
