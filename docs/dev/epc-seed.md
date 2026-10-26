# EPC product model and demo customers in `sfcomms`

Both seeds are **repeatable and idempotent**. They use **standard objects only**, loaded through OOTB sObject REST using the
Salesforce CLI session. They involve no Apex, no Flow and no custom metadata. Every record is prefixed `AgenticTelco`.
Existing records are reused, and nothing that already existed in the org is changed or deleted.

```bash
.venv/bin/python seed/epc/seed_epc.py                 # catalogue (definition: seed/epc/catalog.json) → seed/epc/last-run.json
.venv/bin/python seed/customers/seed_customers.py     # 4 demo customers → seed/customers/last-run.json
.venv/bin/python seed/customers/seed_customers.py --reset-inventory   # before a recorded run (done by ./run.sh journeys)
```

## Catalogue (native Communications Cloud EPC / Product Catalog Management on core)

These are the AgenticTelco record counts in the org after the last seed run on 2026-10-26 (Europe/London):

| Object | Count | What |
|---|---|---|
| Product2 | 9 | 4 bundles (Fibre 150/500/900/1600), access line, Wi-Fi 6 router, installation, Static IP add-on, Wi-Fi Extender add-on |
| ProductCatalog / ProductCategory / ProductCategoryProduct | 1 / 2 / 6 | AgenticTelco Catalog → Broadband, Add-ons |
| ProductComponentGroup / ProductRelatedComponent | 8 / 20 | Each bundle has a Core group (line 1..1, router 1..1, install 0..1 default) and an Add-ons group (Static IP 0..1, Extender 0..3) |
| AttributePicklist / AttributePicklistValue | 2 / 7 | Download speed (150/500/900/1600), contract term (0/12/24) |
| AttributeCategory / AttributeDefinition / AttributeCategoryAttribute | 3 / 3 / 3 | Speed, Contract Term (price-impacting), Static IP count |
| ProductClassification / ProductClassificationAttr / ProductAttributeDefinition | 2 / 3 / 9 | Fibre Broadband class (speed + term), Static IP class |
| ProductSellingModel / ProductSellingModelOption | 1 created + 2 standard referenced / 14 | "AgenticTelco Term Monthly" (TermDefined), plus the org's existing Evergreen-Monthly and One-Time |
| Pricebook2 / PricebookEntry | 1 / 28 | AgenticTelco Price Book, plus the required standard price-book entries |

### Sample offer: AgenticTelco Fibre 500 (`01tQH00000IbOKLYA3`), as returned by TMF620

- `GET /services/apexrest/agentictelco/tmf620/productOffering/01tQH00000IbOKLYA3` returns `x-runtime: custom TMF API on Salesforce`.
- `isBundle: true`, category AgenticTelco Broadband.
- `prodSpecCharValueUse`:
  - AgenticTelco Download Speed = 500 (default).
  - AgenticTelco Contract Term: 0, 12 or 24 months (default 24). This attribute is configurable and price-impacting.
- `bundledProductOffering`:
  - Core: Access Line 1..1, Wi-Fi 6 Router 1..1, Standard Installation 0..1 (default 1).
  - Add-ons: Static IP 0..1, Wi-Fi Extender 0..3.
- `productOfferingPrice`:
  - £40/month Evergreen-Monthly.
  - £35/month AgenticTelco Term Monthly, with a 12- or 24-month minimum term.
- `productOfferingTerm`: 1, 12 and 24 months.

TMF620 returns this catalogue. TMF679 qualifies these offers, and TMF648/TMF622 quote and order them. For example, a 24-month
Fibre 500 order line is priced at £35 from the Term Monthly price-book entry.

## Demo customers (standard Account, Contact, Asset)

| Agent id | Account (`AccountNumber`) | Contact | Baseline Asset (Fibre 150, Installed) |
|---|---|---|---|
| C-1001 Arthur Bennett, Leeds | 001QH00002LK7uiYAD (`AT-C-1001`) | 003QH00000TOKXxYAP | 02iQH000003EkndYAC |
| C-1002 David Okafor, Manchester | 001QH00002LK3lZYAT (`AT-C-1002`) | 003QH00000TOKZZYA5 | 02iQH000003EkpFYAS |
| C-1003 Priya Shah, Bristol | 001QH00002LKV91YAH (`AT-C-1003`) | 003QH00000TOKbBYAX | 02iQH000003EkqrYAC |
| C-1004 Sarah Mitchell, York | 001QH00002LKUAXYA5 (`AT-C-1004`) | 003QH00000TOK8AYAX | 02iQH000003EksTYAS |

All names, addresses and `example.com` emails are synthetic. Each completed journey adds an Asset named
`AgenticTelco Fibre <speed> – C-100x` and sets the previous AgenticTelco Asset to `Obsolete`.
`--reset-inventory` restores the baseline. It touches AgenticTelco Assets on AgenticTelco Accounts only.
