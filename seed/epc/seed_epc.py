#!/usr/bin/env python3
"""Repeatable, idempotent seed of the AgenticTelco EPC catalogue into the sfcomms org.

* OOTB REST only (`/services/data/vXX.X/sobjects/...`) through the Salesforce CLI (`sf api request rest`): no token handled,
  no Apex, no Flow, no metadata deploy.
* Detects which EPC flavour the org has (native Product Catalog Management objects vs vlocity_cmt namespaced) and refuses
  to run against anything else.
* Every record is named/coded with the AgenticTelco prefix; existing records are looked up and reused, never modified,
  never deleted (existing org records such as the standard selling models are only referenced).
Usage:  .venv/bin/python seed/epc/seed_epc.py [--dry-run]
Writes seed/epc/last-run.json (ids + counts, no secrets)."""
import json, os, sys, datetime
from urllib.parse import quote
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)
from stack.zg_common.sf_session import request, API_V

D = f"/services/data/{API_V}"
DRY = "--dry-run" in sys.argv
SPEC = json.load(open(os.path.join(os.path.dirname(__file__), "catalog.json")))
created, reused, errors = {}, {}, []
ids_global = {}

def soql(s):
    r = request("GET", f"{D}/query?q=" + quote(s))
    j = r.json()
    if r.status_code != 200:
        raise RuntimeError(f"SOQL failed {r.status_code}: {str(j)[:300]}")
    return j["records"]

def esc(v): return str(v).replace("\\", "\\\\").replace("'", "\\'")

def ensure(obj, where, fields, label=None):
    """Return Id of the record matching `where`, creating it with `fields` if none exists."""
    rows = soql(f"SELECT Id FROM {obj} WHERE {where} LIMIT 1")
    if rows:
        reused[obj] = reused.get(obj, 0) + 1
        return rows[0]["Id"]
    if DRY:
        created[obj] = created.get(obj, 0) + 1
        return f"dry-{obj}"
    r = request("POST", f"{D}/sobjects/{obj}", fields)
    j = r.json()
    if r.status_code not in (200, 201) or not isinstance(j, dict) or not j.get("id"):
        errors.append(dict(object=obj, label=label or where, status=r.status_code, error=str(j)[:400]))
        print(f"  ! {obj} {label or where}: {r.status_code} {str(j)[:300]}")
        raise SystemExit(f"stopping at first error ({obj}); rerun after fixing – the seed is idempotent")
    created[obj] = created.get(obj, 0) + 1
    print(f"  + {obj} {label or where}")
    return j["id"]

def activate(obj, rid, field="Status", value="Active"):
    if not rid or DRY or rid.startswith("dry-"): return
    cur = soql(f"SELECT {field} FROM {obj} WHERE Id='{rid}'")
    if cur and cur[0].get(field) != value:
        r = request("PATCH", f"{D}/sobjects/{obj}/{rid}", {field: value})
        if r.status_code not in (200, 204):
            errors.append(dict(object=obj, label=f"activate {rid}", status=r.status_code, error=r.text[:300]))

def prc_fields(bid, c, rel, groups, si):
    f = dict(ParentProductId=bid, ChildProductId=ids_global[c["code"]], ProductRelationshipTypeId=rel, ProductComponentGroupId=groups[c["group"]],
             Quantity=1, IsComponentRequired=c["required"], IsDefaultComponent=c["default"], IsQuantityEditable=(c["max"] > 1),
             Sequence=si + 1, DoesBundlePriceIncludeChild=(c["group"] == "Core"))
    if c["max"] > 1:  # min/max are only allowed when quantity is editable
        f.update(MinQuantity=c["min"], MaxQuantity=c["max"])
    return f

def detect():
    names = {s["name"] for s in request("GET", f"{D}/sobjects").json()["sobjects"]}
    native = {"ProductCatalog", "ProductClassification", "AttributeDefinition", "ProductRelatedComponent", "ProductSellingModel"} <= names
    vlocity = any(n.startswith("vlocity_cmt__") for n in names)
    return dict(native=native, vlocity=vlocity, objectsPresent=sorted(n for n in names if n in {
        "ProductCatalog", "ProductCategory", "ProductCategoryProduct", "ProductClassification", "ProductClassificationAttr",
        "AttributeDefinition", "AttributeCategory", "AttributeCategoryAttribute", "AttributePicklist", "AttributePicklistValue",
        "ProductAttributeDefinition", "ProductRelatedComponent", "ProductComponentGroup", "ProductRelationshipType",
        "ProductSellingModel", "ProductSellingModelOption", "Pricebook2", "PricebookEntry", "Product2"}))

def main():
    flavour = detect()
    print("EPC flavour:", "native PCM (core)" if flavour["native"] else "?", "| vlocity_cmt:", flavour["vlocity"])
    if not flavour["native"]:
        sys.exit("Native EPC objects not found; this seed targets Comms Cloud on core (no vlocity_cmt variant written).")
    ids = ids_global
    # 1 picklists + values
    for p in SPEC["picklists"]:
        pid = ensure("AttributePicklist", f"Code='{p['code']}'", dict(Name=p["name"], Code=p["code"], DataType=p["dataType"], Status="Draft"), p["name"])
        ids[p["code"]] = pid
        for i, (val, disp) in enumerate(p["values"]):
            code = f"{p['code']}_{val}"
            ensure("AttributePicklistValue", f"Code='{code}'", dict(Name=f"AgenticTelco {disp}", PicklistId=pid, Code=code, Value=val,
                   DisplayValue=disp, Sequence=i + 1, Status="Active"), code)
        activate("AttributePicklist", pid)
    # 2 categories
    for c in SPEC["attributeCategories"]:
        ids["cat:" + c] = ensure("AttributeCategory", f"Name='{esc(c)}'", dict(Name=c, Code=c.upper().replace(" ", "_").replace("-", "_")), c)
    # 3 attribute definitions
    for a in SPEC["attributes"]:
        f = dict(Name=a["name"], Label=a["name"], DeveloperName=a["dev"], Code=a["code"], DataType=a["type"], IsActive=True)
        if a.get("picklist"): f["PicklistId"] = ids[a["picklist"]]
        if a.get("default"): f["DefaultValue"] = a["default"]
        ids[a["code"]] = ensure("AttributeDefinition", f"Code='{a['code']}'", f, a["name"])
        ensure("AttributeCategoryAttribute", f"AttributeCategoryId='{ids['cat:' + a['category']]}' AND AttributeDefinitionId='{ids[a['code']]}'",
               dict(AttributeCategoryId=ids["cat:" + a["category"]], AttributeDefinitionId=ids[a["code"]]), a["code"] + "→" + a["category"])
    attr_cat = {a["code"]: ids["cat:" + a["category"]] for a in SPEC["attributes"]}
    # 4 classifications + attrs
    for c in SPEC["classifications"]:
        cid = ensure("ProductClassification", f"Name='{esc(c['name'])}'", dict(Name=c["name"], Code=c["code"], Status="Draft"), c["name"])
        ids["class:" + c["name"]] = cid
        for i, code in enumerate(c["attributes"]):
            ids[f"pca:{c['name']}:{code}"] = ensure("ProductClassificationAttr",
                f"ProductClassificationId='{cid}' AND AttributeDefinitionId='{ids[code]}'",
                dict(Name=f"AgenticTelco {code}", ProductClassificationId=cid, AttributeDefinitionId=ids[code], AttributeCategoryId=attr_cat[code],
                     Status="Active", Sequence=i + 1, IsRequired=True), f"{c['name']}:{code}")
        activate("ProductClassification", cid)
    # 5 catalog + categories
    cat = SPEC["catalog"]
    ids["catalog"] = ensure("ProductCatalog", f"Name='{esc(cat['name'])}'", dict(Name=cat["name"], CatalogType="Sales", Code=cat["code"]), cat["name"])
    for i, (nm, code) in enumerate(cat["categories"]):
        ids[code] = ensure("ProductCategory", f"Name='{esc(nm)}' AND CatalogId='{ids['catalog']}'",
                           dict(Name=nm, CatalogId=ids["catalog"], Code=code, SortOrder=i + 1, IsNavigational=True), nm)
    # 6 selling models (create ours, only reference existing ones)
    for nm, m in SPEC["sellingModels"].items():
        if m.get("existing"):
            rows = soql(f"SELECT Id FROM ProductSellingModel WHERE Name='{esc(nm)}' AND Status='Active' LIMIT 1")
            if not rows: errors.append(dict(object="ProductSellingModel", label=nm, status=0, error="existing model not found"))
            ids["psm:" + nm] = rows[0]["Id"] if rows else None
        else:
            pid = ensure("ProductSellingModel", f"Name='{esc(nm)}'", dict(Name=nm, SellingModelType=m["type"], PricingTerm=m["term"], PricingTermUnit=m["unit"], Status="Draft"), nm)
            activate("ProductSellingModel", pid)
            ids["psm:" + nm] = pid
    # 7 products
    for p in SPEC["products"]:
        f = dict(Name=p["name"], ProductCode=p["code"], Description=p["desc"], Family=p["family"], IsActive=True, IsAssetizable=True,
                 StockKeepingUnit=p["code"])
        if p.get("bundle"): f.update(Type="Bundle", ConfigureDuringSale="Allowed")
        if p.get("class"): f["BasedOnId"] = ids["class:" + p["class"]]
        ids[p["code"]] = ensure("Product2", f"ProductCode='{p['code']}'", f, p["name"])
        for k, nm in enumerate(p["prices"]):
            ensure("ProductSellingModelOption", f"Product2Id='{ids[p['code']]}' AND ProductSellingModelId='{ids['psm:' + nm]}'",
                   dict(Product2Id=ids[p["code"]], ProductSellingModelId=ids["psm:" + nm], IsDefault=(k == 0)), f"{p['code']}/{nm}")
        if p.get("category"):
            ensure("ProductCategoryProduct", f"ProductId='{ids[p['code']]}' AND ProductCategoryId='{ids[p['category']]}'",
                   dict(ProductId=ids[p["code"]], ProductCategoryId=ids[p["category"]], IsPrimaryCategory=True), f"{p['code']}→{p['category']}")
        # product attribute definitions (speed fixed per tier, read-only; term defaults to 24)
        if p.get("class"):
            cls = next(c for c in SPEC["classifications"] if c["name"] == p["class"])
            for i, code in enumerate(cls["attributes"]):
                a = next(x for x in SPEC["attributes"] if x["code"] == code)
                dv = p.get("speed") if code == "AT_ATT_DL_SPEED" else a.get("default")
                f2 = dict(Name=f"AgenticTelco {p['code']} {code}", Product2Id=ids[p["code"]], AttributeDefinitionId=ids[code],
                          ProductClassificationAttributeId=ids[f"pca:{p['class']}:{code}"], AttributeCategoryId=attr_cat[code],
                          Status="Active", Sequence=i + 1, IsPriceImpacting=(code == "AT_ATT_TERM"),
                          IsReadOnly=(code == "AT_ATT_DL_SPEED"), IsRequired=True)
                if dv: f2["DefaultValue"] = dv
                ensure("ProductAttributeDefinition", f"Product2Id='{ids[p['code']]}' AND AttributeDefinitionId='{ids[code]}'", f2, f"{p['code']}:{code}")
    # 8 price books
    std = soql("SELECT Id FROM Pricebook2 WHERE IsStandard=true LIMIT 1")[0]["Id"]
    ids["pricebook"] = ensure("Pricebook2", f"Name='{esc(SPEC['pricebook'])}'", dict(Name=SPEC["pricebook"], IsActive=True,
                              Description="AgenticTelco demo price list (GBP-style demo prices)"), SPEC["pricebook"])
    for p in SPEC["products"]:
        for nm, price in p["prices"].items():
            for pb in (std, ids["pricebook"]):
                f = dict(Pricebook2Id=pb, Product2Id=ids[p["code"]], UnitPrice=price, IsActive=True, ProductSellingModelId=ids["psm:" + nm])
                if pb != std: f["UseStandardPrice"] = False
                ensure("PricebookEntry", f"Pricebook2Id='{pb}' AND Product2Id='{ids[p['code']]}' AND ProductSellingModelId='{ids['psm:' + nm]}'",
                       f, f"{p['code']}/{nm}/{'std' if pb == std else 'AT'}")
    # 9 bundle structure
    rel = soql("SELECT Id FROM ProductRelationshipType WHERE MainProductRoleCat='Bundle' AND AssociatedProductRoleCat='BundleComponent' LIMIT 1")[0]["Id"]
    for b in [p for p in SPEC["products"] if p.get("bundle")]:
        bid = ids[b["code"]]
        groups = {}
        for gi, g in enumerate(dict.fromkeys(c["group"] for c in SPEC["bundleComponents"])):
            groups[g] = ensure("ProductComponentGroup", f"ParentProductId='{bid}' AND Name='{esc('AgenticTelco ' + g + ' ' + b['speed'])}'",
                               dict(Name=f"AgenticTelco {g} {b['speed']}", ParentProductId=bid, Sequence=gi + 1,
                                    Code=f"AT_GRP_{g.upper().replace('-', '')}_{b['speed']}",
                                    MinBundleComponents=(2 if g == "Core" else 0)), f"{b['code']}/{g}")
        for si, c in enumerate(SPEC["bundleComponents"]):
            ensure("ProductRelatedComponent", f"ParentProductId='{bid}' AND ChildProductId='{ids[c['code']]}'",
                   prc_fields(bid, c, rel, groups, si), f"{b['code']}→{c['code']}")
    out = dict(ranAt=datetime.datetime.now().astimezone().isoformat(timespec="seconds"), dryRun=DRY, flavour=flavour,
               created=created, reused=reused, errors=errors,
               ids={k: v for k, v in ids.items() if v})
    json.dump(out, open(os.path.join(os.path.dirname(__file__), "last-run.json"), "w"), indent=2)
    print(json.dumps(dict(created=created, reused=reused, errors=len(errors)), indent=1))
    return 1 if errors else 0

if __name__ == "__main__":
    sys.exit(main())
