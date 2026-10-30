/**
 * TMF620 Product Catalog Management (v4 resource shapes) – TMF facade within Salesforce (Apex).
 * The sfcomms org exposes no TMF620 endpoint (Direct Access and managed-package paths return 404), so this resource
 * reads the native Comms Cloud EPC objects. Read-only.
 *   GET /agentictelco/tmf620/productOffering[/{id}]     ?isBundle=true&category.id=..&scope=all&limit=50
 *   GET /agentictelco/tmf620/productOfferingPrice[/{id}]
 *   GET /agentictelco/tmf620/productSpecification[/{id}]
 *   GET /agentictelco/tmf620/category[/{id}]
 *   GET /agentictelco/tmf620/catalog[/{id}]
 */
@RestResource(urlMapping='/agentictelco/tmf620/*')
global with sharing class AgenticTelco_TMF620 {

    @HttpGet
    global static void doGet() {
        List<String> seg = AgenticTelco_Tmf.segments();
        String res = seg.isEmpty() ? 'productOffering' : seg[0];
        String id = seg.size() > 1 ? seg[1] : null;
        try {
            if (res == 'productOffering') {
                List<Map<String, Object>> l = offerings(id);
                if (id != null && l.isEmpty()) { AgenticTelco_Tmf.error(404, 'NOT_FOUND', 'productOffering ' + id); return; }
                AgenticTelco_Tmf.respond(200, id == null ? (Object) l : (Object) l[0]);
            } else if (res == 'productOfferingPrice') {
                List<Map<String, Object>> l = prices(id);
                if (id != null && l.isEmpty()) { AgenticTelco_Tmf.error(404, 'NOT_FOUND', 'productOfferingPrice ' + id); return; }
                AgenticTelco_Tmf.respond(200, id == null ? (Object) l : (Object) l[0]);
            } else if (res == 'productSpecification') {
                List<Map<String, Object>> l = specifications(id);
                if (id != null && l.isEmpty()) { AgenticTelco_Tmf.error(404, 'NOT_FOUND', 'productSpecification ' + id); return; }
                AgenticTelco_Tmf.respond(200, id == null ? (Object) l : (Object) l[0]);
            } else if (res == 'category') {
                AgenticTelco_Tmf.respond(200, categories(id));
            } else if (res == 'catalog') {
                AgenticTelco_Tmf.respond(200, catalogs(id));
            } else {
                AgenticTelco_Tmf.error(404, 'NOT_FOUND', 'Unknown TMF620 resource ' + res);
            }
        } catch (Exception e) {
            AgenticTelco_Tmf.error(500, 'INTERNAL', e.getTypeName() + ': ' + e.getMessage());
        }
    }

    static List<Product2> products(String id) {
        Integer lim = Math.min(AgenticTelco_Tmf.intParam('limit', 100), 200);
        Boolean all = AgenticTelco_Tmf.param('scope') == 'all';
        String bundle = AgenticTelco_Tmf.param('isBundle');
        String cat = AgenticTelco_Tmf.param('category.id');
        String q = 'SELECT Id, Name, ProductCode, Description, IsActive, Type, Family, LastModifiedDate, BasedOnId, BasedOn.Name FROM Product2 WHERE IsActive = true';
        if (id != null) q += ' AND Id = :id';
        else if (!all) q += ' AND Name LIKE \'AgenticTelco%\'';
        if (bundle == 'true') q += ' AND Type = \'Bundle\'';
        if (bundle == 'false') q += ' AND Type = null';
        if (cat != null) q += ' AND Id IN (SELECT ProductId FROM ProductCategoryProduct WHERE ProductCategoryId = :cat)';
        q += ' ORDER BY ProductCode LIMIT :lim';
        return Database.query(q);
    }

    public static List<Map<String, Object>> offerings(String id) {
        List<Product2> ps = products(id);
        Set<Id> ids = new Map<Id, Product2>(ps).keySet();
        Id pb = AgenticTelco_Tmf.pricebookId();
        Map<Id, List<PricebookEntry>> prices = AgenticTelco_Tmf.pricesFor(ids, pb);
        Map<Id, List<ProductRelatedComponent>> comps = new Map<Id, List<ProductRelatedComponent>>();
        for (ProductRelatedComponent c : [
            SELECT ParentProductId, ChildProductId, ChildProduct.Name, IsComponentRequired, IsDefaultComponent, MinQuantity,
                   MaxQuantity, Quantity, ProductComponentGroup.Name, Sequence
            FROM ProductRelatedComponent WHERE ParentProductId IN :ids ORDER BY Sequence
        ]) {
            if (!comps.containsKey(c.ParentProductId)) comps.put(c.ParentProductId, new List<ProductRelatedComponent>());
            comps.get(c.ParentProductId).add(c);
        }
        Map<Id, List<Map<String, Object>>> cats = new Map<Id, List<Map<String, Object>>>();
        for (ProductCategoryProduct c : [
            SELECT ProductId, ProductCategoryId, ProductCategory.Name FROM ProductCategoryProduct WHERE ProductId IN :ids
        ]) {
            if (!cats.containsKey(c.ProductId)) cats.put(c.ProductId, new List<Map<String, Object>>());
            cats.get(c.ProductId).add(AgenticTelco_Tmf.ref(c.ProductCategoryId, c.ProductCategory.Name, 'Category',
                AgenticTelco_Tmf.href('tmf620', 'category', c.ProductCategoryId)));
        }
        Map<Id, List<Map<String, Object>>> chars = characteristics(ids);
        List<Map<String, Object>> out = new List<Map<String, Object>>();
        for (Product2 p : ps) {
            Boolean isBundle = p.Type == 'Bundle';
            List<Object> pops = new List<Object>();
            if (prices.containsKey(p.Id)) for (PricebookEntry e : prices.get(p.Id)) pops.add(AgenticTelco_Tmf.price(e));
            List<Object> bpo = new List<Object>();
            if (comps.containsKey(p.Id)) {
                for (ProductRelatedComponent c : comps.get(p.Id)) {
                    Integer lower = c.IsComponentRequired == true ? 1 : 0;
                    Integer upper = c.MaxQuantity == null ? 1 : Integer.valueOf(c.MaxQuantity);
                    bpo.add(new Map<String, Object>{
                        'id' => c.ChildProductId, 'name' => c.ChildProduct.Name,
                        'href' => AgenticTelco_Tmf.href('tmf620', 'productOffering', c.ChildProductId),
                        'x-group' => c.ProductComponentGroup == null ? null : c.ProductComponentGroup.Name,
                        'bundledProductOfferingOption' => new Map<String, Object>{
                            'numberRelOfferLowerLimit' => lower, 'numberRelOfferUpperLimit' => upper,
                            'numberRelOfferDefault' => c.IsDefaultComponent == true ? 1 : 0 }
                    });
                }
            }
            List<Map<String, Object>> spc = chars.containsKey(p.Id) ? chars.get(p.Id) : new List<Map<String, Object>>();
            List<Object> terms = new List<Object>();
            for (Map<String, Object> ch : spc) {
                if (String.valueOf(ch.get('name')).containsIgnoreCase('Contract Term')) {
                    for (Object v : (List<Object>) ch.get('productSpecCharacteristicValue')) {
                        String months = String.valueOf(((Map<String, Object>) v).get('value'));
                        terms.add(new Map<String, Object>{
                            'name' => months == '0' ? 'No contract (30-day rolling)' : months + ' months',
                            'duration' => new Map<String, Object>{ 'amount' => months == '0' ? 1 : Integer.valueOf(months), 'units' => 'month' } });
                    }
                }
            }
            out.add(new Map<String, Object>{
                'id' => p.Id,
                'href' => AgenticTelco_Tmf.href('tmf620', 'productOffering', p.Id),
                'name' => p.Name,
                'code' => p.ProductCode,
                'description' => p.Description,
                'version' => '1.0',
                'lifecycleStatus' => p.IsActive ? 'Active' : 'Retired',
                'isBundle' => isBundle,
                'isSellable' => true,
                'lastUpdate' => p.LastModifiedDate,
                'category' => cats.containsKey(p.Id) ? cats.get(p.Id) : new List<Map<String, Object>>(),
                'productSpecification' => AgenticTelco_Tmf.ref(p.Id, p.Name, 'ProductSpecification',
                    AgenticTelco_Tmf.href('tmf620', 'productSpecification', p.Id)),
                'productOfferingPrice' => pops,
                'productOfferingTerm' => terms,
                'bundledProductOffering' => bpo,
                'prodSpecCharValueUse' => spc,
                'x-sor' => 'Salesforce Comms Cloud native EPC (Product2, PricebookEntry, ProductRelatedComponent, ProductAttributeDefinition)',
                'x-runtime' => AgenticTelco_Tmf.SOR_LABEL,
                '@baseType' => 'ProductOffering',
                '@type' => 'ProductOffering'
            });
        }
        return out;
    }

    /** ProductAttributeDefinition (+ picklist values) -> TMF characteristic value uses. */
    public static Map<Id, List<Map<String, Object>>> characteristics(Set<Id> ids) {
        List<ProductAttributeDefinition> pads = [
            SELECT Product2Id, AttributeDefinitionId, AttributeDefinition.Name, AttributeDefinition.Code, AttributeDefinition.DataType,
                   AttributeDefinition.PicklistId, DefaultValue, IsReadOnly, IsRequired, IsPriceImpacting, AttributeCategory.Name, Sequence
            FROM ProductAttributeDefinition WHERE Product2Id IN :ids ORDER BY Sequence
        ];
        Set<Id> picklists = new Set<Id>();
        for (ProductAttributeDefinition d : pads) if (d.AttributeDefinition.PicklistId != null) picklists.add(d.AttributeDefinition.PicklistId);
        Map<Id, List<AttributePicklistValue>> vals = new Map<Id, List<AttributePicklistValue>>();
        for (AttributePicklistValue v : [
            SELECT PicklistId, Value, DisplayValue, IsDefault, Sequence FROM AttributePicklistValue WHERE PicklistId IN :picklists ORDER BY Sequence
        ]) {
            if (!vals.containsKey(v.PicklistId)) vals.put(v.PicklistId, new List<AttributePicklistValue>());
            vals.get(v.PicklistId).add(v);
        }
        Map<Id, List<Map<String, Object>>> out = new Map<Id, List<Map<String, Object>>>();
        for (ProductAttributeDefinition d : pads) {
            List<Object> values = new List<Object>();
            String vt = d.AttributeDefinition.DataType == 'Number' ? 'number' : 'string';
            if (d.AttributeDefinition.PicklistId != null && vals.containsKey(d.AttributeDefinition.PicklistId)) {
                for (AttributePicklistValue v : vals.get(d.AttributeDefinition.PicklistId)) {
                    if (d.IsReadOnly == true && d.DefaultValue != null && v.Value != d.DefaultValue) continue; // fixed per offering
                    values.add(new Map<String, Object>{ 'value' => v.Value, 'x-display' => v.DisplayValue,
                        'isDefault' => v.Value == d.DefaultValue, 'valueType' => vt });
                }
            } else if (d.DefaultValue != null) {
                values.add(new Map<String, Object>{ 'value' => d.DefaultValue, 'isDefault' => true, 'valueType' => vt });
            }
            if (!out.containsKey(d.Product2Id)) out.put(d.Product2Id, new List<Map<String, Object>>());
            out.get(d.Product2Id).add(new Map<String, Object>{
                'name' => d.AttributeDefinition.Name,
                'x-code' => d.AttributeDefinition.Code,
                'x-category' => d.AttributeCategory == null ? null : d.AttributeCategory.Name,
                'valueType' => vt,
                'minCardinality' => d.IsRequired == true ? 1 : 0,
                'maxCardinality' => 1,
                'configurable' => d.IsReadOnly != true,
                'x-priceImpacting' => d.IsPriceImpacting == true,
                'productSpecCharacteristicValue' => values,
                '@type' => 'ProductSpecificationCharacteristicValueUse'
            });
        }
        return out;
    }

    public static List<Map<String, Object>> prices(String id) {
        Id pb = AgenticTelco_Tmf.pricebookId();
        List<Map<String, Object>> out = new List<Map<String, Object>>();
        List<PricebookEntry> l = id == null
            ? [SELECT Id, Product2Id, Product2.Name, UnitPrice, ProductSellingModelId, ProductSellingModel.Name,
                      ProductSellingModel.SellingModelType, ProductSellingModel.PricingTermUnit
               FROM PricebookEntry WHERE Pricebook2Id = :pb AND IsActive = true ORDER BY Product2.ProductCode LIMIT 200]
            : [SELECT Id, Product2Id, Product2.Name, UnitPrice, ProductSellingModelId, ProductSellingModel.Name,
                      ProductSellingModel.SellingModelType, ProductSellingModel.PricingTermUnit
               FROM PricebookEntry WHERE Id = :id LIMIT 1];
        for (PricebookEntry e : l) out.add(AgenticTelco_Tmf.price(e));
        return out;
    }

    public static List<Map<String, Object>> specifications(String id) {
        List<Product2> ps = products(id);
        Map<Id, List<Map<String, Object>>> chars = characteristics(new Map<Id, Product2>(ps).keySet());
        List<Map<String, Object>> out = new List<Map<String, Object>>();
        for (Product2 p : ps) {
            List<Object> psc = new List<Object>();
            if (chars.containsKey(p.Id)) {
                for (Map<String, Object> c : chars.get(p.Id)) {
                    psc.add(new Map<String, Object>{ 'name' => c.get('name'), 'valueType' => c.get('valueType'),
                        'configurable' => c.get('configurable'), 'minCardinality' => c.get('minCardinality'), 'maxCardinality' => 1,
                        'productSpecCharacteristicValue' => c.get('productSpecCharacteristicValue') });
                }
            }
            out.add(new Map<String, Object>{
                'id' => p.Id, 'href' => AgenticTelco_Tmf.href('tmf620', 'productSpecification', p.Id), 'name' => p.Name,
                'productNumber' => p.ProductCode, 'description' => p.Description, 'isBundle' => p.Type == 'Bundle',
                'lifecycleStatus' => 'Active', 'version' => '1.0',
                'x-classification' => p.BasedOn == null ? null : p.BasedOn.Name,
                'productSpecCharacteristic' => psc, '@type' => 'ProductSpecification'
            });
        }
        return out;
    }

    public static Object categories(String id) {
        List<Map<String, Object>> out = new List<Map<String, Object>>();
        for (ProductCategory c : [
            SELECT Id, Name, Description, CatalogId, Catalog.Name, ParentCategoryId, IsNavigational
            FROM ProductCategory WHERE Catalog.Name LIKE :AgenticTelco_Tmf.CATALOG_PREFIX ORDER BY SortOrder LIMIT 200
        ]) {
            if (id != null && c.Id != id) continue;
            out.add(new Map<String, Object>{ 'id' => c.Id, 'href' => AgenticTelco_Tmf.href('tmf620', 'category', c.Id),
                'name' => c.Name, 'description' => c.Description, 'isRoot' => c.ParentCategoryId == null,
                'parentId' => c.ParentCategoryId, 'lifecycleStatus' => 'Active', '@type' => 'Category' });
        }
        if (id != null) return out.isEmpty() ? null : out[0];
        return out;
    }

    public static Object catalogs(String id) {
        List<Map<String, Object>> out = new List<Map<String, Object>>();
        for (ProductCatalog c : [
            SELECT Id, Name, CatalogType, EffectiveStartDate, EffectiveEndDate
            FROM ProductCatalog WHERE Name LIKE :AgenticTelco_Tmf.CATALOG_PREFIX LIMIT 20
        ]) {
            if (id != null && c.Id != id) continue;
            List<Object> cats = new List<Object>();
            for (ProductCategory pc : [SELECT Id, Name FROM ProductCategory WHERE CatalogId = :c.Id ORDER BY SortOrder]) cats.add(AgenticTelco_Tmf.ref(pc.Id, pc.Name, 'Category',
                AgenticTelco_Tmf.href('tmf620', 'category', pc.Id)));
            out.add(new Map<String, Object>{ 'id' => c.Id, 'href' => AgenticTelco_Tmf.href('tmf620', 'catalog', c.Id),
                'name' => c.Name, 'catalogType' => c.CatalogType, 'lifecycleStatus' => 'Active', 'category' => cats,
                'validFor' => new Map<String, Object>{ 'startDateTime' => c.EffectiveStartDate, 'endDateTime' => c.EffectiveEndDate },
                '@type' => 'Catalog' });
        }
        if (id != null) return out.isEmpty() ? null : out[0];
        return out;
    }
}
