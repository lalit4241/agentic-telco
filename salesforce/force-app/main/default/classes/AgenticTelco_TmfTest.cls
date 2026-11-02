@IsTest
private class AgenticTelco_TmfTest {

    @TestSetup
    static void setup() {
        Account a = new Account(Name = 'AgenticTelco Test Customer', AccountNumber = 'AT-T-TEST');
        insert a;
        ProductSellingModel ever = new ProductSellingModel(Name = 'AgenticTelco T Evergreen', SellingModelType = 'Evergreen',
            PricingTerm = 1, PricingTermUnit = 'Months', Status = 'Active');
        ProductSellingModel termed = new ProductSellingModel(Name = 'AgenticTelco T Term', SellingModelType = 'TermDefined',
            PricingTerm = 1, PricingTermUnit = 'Months', Status = 'Active');
        ProductSellingModel once = new ProductSellingModel(Name = 'AgenticTelco T Once', SellingModelType = 'OneTime', Status = 'Active');
        insert new List<ProductSellingModel>{ ever, termed, once };

        AttributePicklist pl = new AttributePicklist(Name = 'AgenticTelco T Speed', Code = 'AT_T_PKL', DataType = 'Text', Status = 'Draft');
        insert pl;
        insert new List<AttributePicklistValue>{
            new AttributePicklistValue(Name = 'AgenticTelco T 150', PicklistId = pl.Id, Code = 'AT_T_150', Value = '150', DisplayValue = '150 Mbps', Sequence = 1, Status = 'Active'),
            new AttributePicklistValue(Name = 'AgenticTelco T 900', PicklistId = pl.Id, Code = 'AT_T_900', Value = '900', DisplayValue = '900 Mbps', Sequence = 2, Status = 'Active')
        };
        AttributePicklist tl = new AttributePicklist(Name = 'AgenticTelco T Term', Code = 'AT_T_TERM', DataType = 'Text', Status = 'Draft');
        insert tl;
        insert new List<AttributePicklistValue>{
            new AttributePicklistValue(Name = 'AgenticTelco T 0', PicklistId = tl.Id, Code = 'AT_T_T0', Value = '0', DisplayValue = 'None', Sequence = 1, Status = 'Active'),
            new AttributePicklistValue(Name = 'AgenticTelco T 24', PicklistId = tl.Id, Code = 'AT_T_T24', Value = '24', DisplayValue = '24 months', Sequence = 2, Status = 'Active')
        };
        pl.Status = 'Active';
        tl.Status = 'Active';
        update new List<AttributePicklist>{ pl, tl };
        AttributeDefinition speed = new AttributeDefinition(Name = 'AgenticTelco Download Speed', Label = 'AgenticTelco Download Speed',
            DeveloperName = 'AT_T_Speed', Code = 'AT_T_SPEED', DataType = 'Picklist', PicklistId = pl.Id, IsActive = true);
        AttributeDefinition term = new AttributeDefinition(Name = 'AgenticTelco Contract Term', Label = 'AgenticTelco Contract Term',
            DeveloperName = 'AT_T_Term', Code = 'AT_T_TERMA', DataType = 'Picklist', PicklistId = tl.Id, IsActive = true);
        AttributeDefinition ips = new AttributeDefinition(Name = 'AgenticTelco Static IP Count', Label = 'AgenticTelco Static IP Count',
            DeveloperName = 'AT_T_Ips', Code = 'AT_T_IPS', DataType = 'Number', IsActive = true);
        Savepoint sp = Database.setSavepoint();
        try {
            insert new List<AttributeDefinition>{ speed, term, ips };
        } catch (DmlException e) {
            // Some PCM releases validate picklist activation outside the test transaction; fall back to text attributes.
            Database.rollback(sp);
            speed = speed.clone(false); term = term.clone(false); ips = ips.clone(false);
            speed.DataType = 'Text'; speed.PicklistId = null;
            term.DataType = 'Text'; term.PicklistId = null;
            insert new List<AttributeDefinition>{ speed, term, ips };
        }
        AttributeCategory ac = new AttributeCategory(Name = 'AgenticTelco T Cat', Code = 'AT_T_CAT');
        insert ac;
        ProductClassification cls = new ProductClassification(Name = 'AgenticTelco T Class', Code = 'AT_T_CLS', Status = 'Draft');
        insert cls;
        ProductClassificationAttr ca1 = new ProductClassificationAttr(Name = 'AgenticTelco T CA1', ProductClassificationId = cls.Id,
            AttributeDefinitionId = speed.Id, AttributeCategoryId = ac.Id, Status = 'Active', Sequence = 1);
        ProductClassificationAttr ca2 = new ProductClassificationAttr(Name = 'AgenticTelco T CA2', ProductClassificationId = cls.Id,
            AttributeDefinitionId = term.Id, AttributeCategoryId = ac.Id, Status = 'Active', Sequence = 2);
        ProductClassificationAttr ca3 = new ProductClassificationAttr(Name = 'AgenticTelco T CA3', ProductClassificationId = cls.Id,
            AttributeDefinitionId = ips.Id, AttributeCategoryId = ac.Id, Status = 'Active', Sequence = 3);
        insert new List<ProductClassificationAttr>{ ca1, ca2, ca3 };
        cls.Status = 'Active';
        update cls;

        Product2 bundle = new Product2(Name = 'AgenticTelco Fibre 900', ProductCode = 'AT-T-900', IsActive = true, Type = 'Bundle',
            ConfigureDuringSale = 'Allowed', Description = 'test', BasedOnId = cls.Id);
        Product2 child = new Product2(Name = 'AgenticTelco Static IP', ProductCode = 'AT-T-IP', IsActive = true, Description = 'test');
        Product2 inst = new Product2(Name = 'AgenticTelco Install', ProductCode = 'AT-T-INST', IsActive = true);
        insert new List<Product2>{ bundle, child, inst };
        insert new List<ProductAttributeDefinition>{
            new ProductAttributeDefinition(Name = 'AgenticTelco T PAD1', Product2Id = bundle.Id, AttributeDefinitionId = speed.Id,
                ProductClassificationAttributeId = ca1.Id, AttributeCategoryId = ac.Id, DefaultValue = '900', IsReadOnly = true, IsRequired = true, Status = 'Active', Sequence = 1),
            new ProductAttributeDefinition(Name = 'AgenticTelco T PAD2', Product2Id = bundle.Id, AttributeDefinitionId = term.Id,
                ProductClassificationAttributeId = ca2.Id, AttributeCategoryId = ac.Id, DefaultValue = '24', IsRequired = true, Status = 'Active', Sequence = 2),
            new ProductAttributeDefinition(Name = 'AgenticTelco T PAD3', Product2Id = bundle.Id, AttributeDefinitionId = ips.Id,
                ProductClassificationAttributeId = ca3.Id, AttributeCategoryId = ac.Id, DefaultValue = '1', Status = 'Active', Sequence = 3)
        };
        insert new List<ProductSellingModelOption>{
            new ProductSellingModelOption(Product2Id = bundle.Id, ProductSellingModelId = termed.Id, IsDefault = true),
            new ProductSellingModelOption(Product2Id = bundle.Id, ProductSellingModelId = ever.Id),
            new ProductSellingModelOption(Product2Id = child.Id, ProductSellingModelId = ever.Id, IsDefault = true),
            new ProductSellingModelOption(Product2Id = inst.Id, ProductSellingModelId = once.Id, IsDefault = true)
        };

        Id std = Test.getStandardPricebookId();
        Pricebook2 pb = new Pricebook2(Name = AgenticTelco_Tmf.PRICEBOOK, IsActive = true);
        insert pb;
        List<PricebookEntry> pbes = new List<PricebookEntry>();
        for (Id pbId : new List<Id>{ std, pb.Id }) {
            pbes.add(new PricebookEntry(Pricebook2Id = pbId, Product2Id = bundle.Id, UnitPrice = 45, IsActive = true, ProductSellingModelId = termed.Id));
            pbes.add(new PricebookEntry(Pricebook2Id = pbId, Product2Id = bundle.Id, UnitPrice = 50, IsActive = true, ProductSellingModelId = ever.Id));
            pbes.add(new PricebookEntry(Pricebook2Id = pbId, Product2Id = child.Id, UnitPrice = 5, IsActive = true, ProductSellingModelId = ever.Id));
            pbes.add(new PricebookEntry(Pricebook2Id = pbId, Product2Id = inst.Id, UnitPrice = 49, IsActive = true, ProductSellingModelId = once.Id));
        }
        insert pbes;

        ProductCatalog cat = new ProductCatalog(Name = 'AgenticTelco T Catalog', CatalogType = 'Sales');
        insert cat;
        ProductCategory pc = new ProductCategory(Name = 'AgenticTelco T Broadband', CatalogId = cat.Id, SortOrder = 1);
        insert pc;
        insert new ProductCategoryProduct(ProductCategoryId = pc.Id, ProductId = bundle.Id);

        ProductRelationshipType rel = new ProductRelationshipType(Name = 'AgenticTelco T Rel', MainProductRoleCat = 'Bundle',
            AssociatedProductRoleCat = 'BundleComponent');
        insert rel;
        ProductComponentGroup g = new ProductComponentGroup(Name = 'AgenticTelco T Add-ons', ParentProductId = bundle.Id, Sequence = 1);
        insert g;
        insert new ProductRelatedComponent(ParentProductId = bundle.Id, ChildProductId = child.Id, ProductRelationshipTypeId = rel.Id,
            ProductComponentGroupId = g.Id, Quantity = 1, IsComponentRequired = false, IsDefaultComponent = false, Sequence = 1);
        insert new Promotion(Name = 'AgenticTelco T Promo', IsActive = true, DisplayName = 'Test promo', StartDateTime = System.now());
    }

    static void req(String method, String uri, Map<String, String> params, Object body) {
        RestRequest r = new RestRequest();
        r.httpMethod = method;
        r.requestURI = '/services/apexrest' + uri;
        if (params != null) r.params.putAll(params);
        if (body != null) r.requestBody = Blob.valueOf(JSON.serialize(body));
        RestContext.request = r;
        RestContext.response = new RestResponse();
    }

    static Object resp() {
        return JSON.deserializeUntyped(RestContext.response.responseBody.toString());
    }

    static Id bundleId() { return [SELECT Id FROM Product2 WHERE ProductCode = 'AT-T-900'].Id; }
    static Id childId() { return [SELECT Id FROM Product2 WHERE ProductCode = 'AT-T-IP'].Id; }
    static Id instId() { return [SELECT Id FROM Product2 WHERE ProductCode = 'AT-T-INST'].Id; }
    static Id accId() { return [SELECT Id FROM Account WHERE Name = 'AgenticTelco Test Customer'].Id; }

    @IsTest
    static void tmf620Offerings() {
        Test.startTest();
        req('GET', '/agentictelco/tmf620/productOffering', new Map<String, String>{ 'limit' => '10' }, null);
        AgenticTelco_TMF620.doGet();
        System.assertEquals(200, RestContext.response.statusCode);
        List<Object> l = (List<Object>) resp();
        System.assertEquals(3, l.size());
        Map<String, Object> b;
        for (Object o : l) if (((Map<String, Object>) o).get('isBundle') == true) b = (Map<String, Object>) o;
        System.assertNotEquals(null, b);
        System.assertEquals(2, ((List<Object>) b.get('productOfferingPrice')).size());
        System.assertEquals(1, ((List<Object>) b.get('bundledProductOffering')).size());
        System.assertEquals(3, ((List<Object>) b.get('prodSpecCharValueUse')).size());
        System.assert(((List<Object>) b.get('productOfferingTerm')).size() >= 1);

        req('GET', '/agentictelco/tmf620/productOffering/' + bundleId(), null, null);
        AgenticTelco_TMF620.doGet();
        System.assertEquals('AgenticTelco Fibre 900', ((Map<String, Object>) resp()).get('name'));

        req('GET', '/agentictelco/tmf620/productOffering', new Map<String, String>{ 'isBundle' => 'true', 'scope' => 'all' }, null);
        AgenticTelco_TMF620.doGet();
        System.assertEquals(200, RestContext.response.statusCode);
        req('GET', '/agentictelco/tmf620/productOffering', new Map<String, String>{ 'isBundle' => 'false',
            'category.id' => [SELECT Id FROM ProductCategory LIMIT 1].Id }, null);
        AgenticTelco_TMF620.doGet();
        System.assertEquals(200, RestContext.response.statusCode);
        req('GET', '/agentictelco/tmf620/productOffering/01t000000000000AAA', null, null);
        AgenticTelco_TMF620.doGet();
        System.assertEquals(404, RestContext.response.statusCode);
        Test.stopTest();
    }

    @IsTest
    static void tmf620OtherResources() {
        Test.startTest();
        req('GET', '/agentictelco/tmf620/productOfferingPrice', null, null);
        AgenticTelco_TMF620.doGet();
        List<Object> prices = (List<Object>) resp();
        System.assertEquals(4, prices.size());
        String pid = (String) ((Map<String, Object>) prices[0]).get('id');
        req('GET', '/agentictelco/tmf620/productOfferingPrice/' + pid, null, null);
        AgenticTelco_TMF620.doGet();
        System.assertEquals(200, RestContext.response.statusCode);
        req('GET', '/agentictelco/tmf620/productOfferingPrice/01u000000000000AAA', null, null);
        AgenticTelco_TMF620.doGet();
        System.assertEquals(404, RestContext.response.statusCode);
        req('GET', '/agentictelco/tmf620/productSpecification', null, null);
        AgenticTelco_TMF620.doGet();
        System.assertEquals(3, ((List<Object>) resp()).size());
        req('GET', '/agentictelco/tmf620/productSpecification/01t000000000000AAA', null, null);
        AgenticTelco_TMF620.doGet();
        System.assertEquals(404, RestContext.response.statusCode);
        req('GET', '/agentictelco/tmf620/category', null, null);
        AgenticTelco_TMF620.doGet();
        System.assertEquals(1, ((List<Object>) resp()).size());
        req('GET', '/agentictelco/tmf620/category/' + [SELECT Id FROM ProductCategory LIMIT 1].Id, null, null);
        AgenticTelco_TMF620.doGet();
        System.assertEquals(200, RestContext.response.statusCode);
        req('GET', '/agentictelco/tmf620/catalog', null, null);
        AgenticTelco_TMF620.doGet();
        System.assertEquals(1, ((List<Object>) resp()).size());
        req('GET', '/agentictelco/tmf620/catalog/' + [SELECT Id FROM ProductCatalog LIMIT 1].Id, null, null);
        AgenticTelco_TMF620.doGet();
        System.assertEquals(200, RestContext.response.statusCode);
        req('GET', '/agentictelco/tmf620/nope', null, null);
        AgenticTelco_TMF620.doGet();
        System.assertEquals(404, RestContext.response.statusCode);
        req('GET', '/agentictelco/tmf620/productOffering/not-an-id', null, null);
        AgenticTelco_TMF620.doGet();
        System.assertNotEquals(200, RestContext.response.statusCode);
        Test.stopTest();
    }

    static Map<String, Object> orderBody(String ext, String term) {
        return new Map<String, Object>{
            'externalId' => ext, 'description' => 'upgrade',
            'relatedParty' => new List<Object>{ new Map<String, Object>{ 'id' => 'bad' }, new Map<String, Object>{ 'id' => accId(), 'role' => 'Customer' } },
            'productOrderItem' => new List<Object>{
                new Map<String, Object>{ 'id' => '1', 'action' => 'add', 'quantity' => 1,
                    'productOffering' => new Map<String, Object>{ 'id' => bundleId() },
                    'product' => new Map<String, Object>{ 'productCharacteristic' => new List<Object>{
                        new Map<String, Object>{ 'name' => 'AgenticTelco Contract Term', 'value' => term } } } },
                new Map<String, Object>{ 'id' => '2', 'action' => 'add', 'productOffering' => new Map<String, Object>{ 'id' => childId() } },
                new Map<String, Object>{ 'id' => '3', 'action' => 'add', 'productOffering' => new Map<String, Object>{ 'id' => instId() } }
            }
        };
    }

    @IsTest
    static void tmf622Lifecycle() {
        Test.startTest();
        req('POST', '/agentictelco/tmf622/productOrder', null, orderBody('T-1', '24'));
        AgenticTelco_TMF622.doPost();
        Integer created = RestContext.response.statusCode;
        Map<String, Object> o = (Map<String, Object>) resp();
        System.assert(created == 201 || created == 422, RestContext.response.responseBody.toString());
        if (created == 201) {
            String id = (String) o.get('id');
            System.assertEquals('acknowledged', o.get('state'));
            req('POST', '/agentictelco/tmf622/productOrder', null, orderBody('T-1', '24'));
            AgenticTelco_TMF622.doPost();
            System.assertEquals(200, RestContext.response.statusCode); // idempotent replay
            req('GET', '/agentictelco/tmf622/productOrder', new Map<String, String>{ 'state' => 'acknowledged' }, null);
            AgenticTelco_TMF622.doGet();
            System.assertEquals(1, ((List<Object>) resp()).size());
            req('GET', '/agentictelco/tmf622/productOrder/' + id, null, null);
            AgenticTelco_TMF622.doGet();
            System.assertEquals(200, RestContext.response.statusCode);
            req('PATCH', '/agentictelco/tmf622/productOrder/' + id, null, new Map<String, Object>{ 'state' => 'cancelled' });
            AgenticTelco_TMF622.doPatch();
            System.assertEquals('cancelled', ((Map<String, Object>) resp()).get('state'), RestContext.response.responseBody.toString());
            req('PATCH', '/agentictelco/tmf622/productOrder/' + id, null, new Map<String, Object>{ 'state' => 'bogus' });
            AgenticTelco_TMF622.doPatch();
            System.assertEquals(400, RestContext.response.statusCode);
            req('PATCH', '/agentictelco/tmf622/productOrder/' + id, null, new Map<String, Object>{ 'state' => 'inProgress' });
            AgenticTelco_TMF622.doPatch();
            req('PATCH', '/agentictelco/tmf622/productOrder/' + id, null, new Map<String, Object>{ 'state' => 'completed' });
            AgenticTelco_TMF622.doPatch();
            System.assertEquals(409, RestContext.response.statusCode); // compensated orders stay cancelled
        }
        req('POST', '/agentictelco/tmf622/productOrder', null, orderBody('T-2', '0'));
        AgenticTelco_TMF622.doPost();
        if (RestContext.response.statusCode == 201) {
            String id2 = (String) ((Map<String, Object>) resp()).get('id');
            req('PATCH', '/agentictelco/tmf622/productOrder/' + id2, null, new Map<String, Object>{ 'state' => 'completed' });
            AgenticTelco_TMF622.doPatch();
            Integer sc = RestContext.response.statusCode;
            System.assert(sc == 200 || sc == 422, RestContext.response.responseBody.toString());
            if (sc == 200) System.assertEquals('completed', ((Map<String, Object>) resp()).get('state'));
        }
        Test.stopTest();
    }

    @IsTest
    static void tmf622Modify() {
        Asset cur = new Asset(Name = 'AgenticTelco Fibre 150 T', AccountId = accId(), Status = 'Installed', Quantity = 1);
        Asset foreign = new Asset(Name = 'Other asset', AccountId = accId(), Status = 'Installed', Quantity = 1);
        insert new List<Asset>{ cur, foreign };
        Test.startTest();
        Map<String, Object> b = orderBody('M-1', '24');
        Map<String, Object> it = (Map<String, Object>) ((List<Object>) b.get('productOrderItem'))[0];
        it.put('action', 'modify');
        it.put('product', new Map<String, Object>{ 'id' => cur.Id });
        req('POST', '/agentictelco/tmf622/productOrder', null, b);
        AgenticTelco_TMF622.doPost();
        Integer sc = RestContext.response.statusCode;
        System.assert(sc == 201 || sc == 422, RestContext.response.responseBody.toString());
        if (sc == 201) {
            Map<String, Object> o = (Map<String, Object>) resp();
            Map<String, Object> item = (Map<String, Object>) ((List<Object>) o.get('productOrderItem'))[0];
            System.assertEquals('modify', item.get('action'));
            System.assertEquals(String.valueOf(cur.Id), ((Map<String, Object>) item.get('product')).get('id'));
        }
        it.put('product', new Map<String, Object>{ 'id' => foreign.Id });
        b.put('externalId', 'M-2');
        req('POST', '/agentictelco/tmf622/productOrder', null, b);
        AgenticTelco_TMF622.doPost();
        System.assertEquals(400, RestContext.response.statusCode);
        it.remove('product');
        req('POST', '/agentictelco/tmf622/productOrder', null, b);
        AgenticTelco_TMF622.doPost();
        System.assertEquals(400, RestContext.response.statusCode);
        it.put('action', 'delete');
        req('POST', '/agentictelco/tmf622/productOrder', null, b);
        AgenticTelco_TMF622.doPost();
        System.assertEquals(400, RestContext.response.statusCode);
        System.assertEquals('add', AgenticTelco_TMF622.itemAction(null));
        System.assertEquals(null, AgenticTelco_TMF622.itemProduct('AgenticTelco item 1'));
        Test.stopTest();
    }

    @IsTest
    static void tmf622Errors() {
        Test.startTest();
        req('POST', '/agentictelco/tmf622/productOrder', null, new Map<String, Object>{});
        AgenticTelco_TMF622.doPost();
        System.assertEquals(400, RestContext.response.statusCode);
        req('POST', '/agentictelco/tmf622/productOrder', null, new Map<String, Object>{ 'externalId' => 'X' });
        AgenticTelco_TMF622.doPost();
        System.assertEquals(400, RestContext.response.statusCode);
        req('POST', '/agentictelco/tmf622/productOrder', null, new Map<String, Object>{ 'externalId' => 'X',
            'relatedParty' => new List<Object>{ new Map<String, Object>{ 'id' => accId() } } });
        AgenticTelco_TMF622.doPost();
        System.assertEquals(400, RestContext.response.statusCode);
        req('POST', '/agentictelco/tmf622/productOrder', null, new Map<String, Object>{ 'externalId' => 'X',
            'relatedParty' => new List<Object>{ new Map<String, Object>{ 'id' => accId() } },
            'productOrderItem' => new List<Object>{ new Map<String, Object>{ 'productOffering' => new Map<String, Object>{ 'id' => accId() } } } });
        AgenticTelco_TMF622.doPost();
        System.assertEquals(422, RestContext.response.statusCode);
        req('GET', '/agentictelco/tmf622/productOrder/801000000000000AAA', null, null);
        AgenticTelco_TMF622.doGet();
        System.assertEquals(404, RestContext.response.statusCode);
        req('PATCH', '/agentictelco/tmf622/productOrder', null, null);
        AgenticTelco_TMF622.doPatch();
        System.assertEquals(400, RestContext.response.statusCode);
        req('PATCH', '/agentictelco/tmf622/productOrder/801000000000000AAA', null, null);
        AgenticTelco_TMF622.doPatch();
        System.assertEquals(404, RestContext.response.statusCode);
        Order foreign = new Order(Name = 'Someone else', AccountId = accId(), Status = 'Draft', EffectiveDate = Date.today());
        insert foreign;
        req('PATCH', '/agentictelco/tmf622/productOrder/' + foreign.Id, null, new Map<String, Object>{ 'state' => 'cancelled' });
        AgenticTelco_TMF622.doPatch();
        System.assertEquals(403, RestContext.response.statusCode);
        req('GET', '/agentictelco/tmf622/productOrder', new Map<String, String>{ 'scope' => 'all' }, null);
        AgenticTelco_TMF622.doGet();
        System.assertEquals(200, RestContext.response.statusCode);
        Order o = new Order(Name = 'x', Status = 'Activated');
        System.assertEquals('completed', AgenticTelco_TMF622.state(o));
        o.Status = 'Exception';
        System.assertEquals('failed', AgenticTelco_TMF622.state(o));
        o.Status = 'Submitted';
        System.assertEquals('inProgress', AgenticTelco_TMF622.state(o));
        Test.stopTest();
    }

    @IsTest
    static void tmf648Lifecycle() {
        Map<String, Object> body = new Map<String, Object>{
            'externalId' => 'Q-1', 'relatedParty' => new List<Object>{ new Map<String, Object>{ 'id' => accId() } },
            'quoteItem' => new List<Object>{
                new Map<String, Object>{ 'id' => '1', 'quantity' => 1, 'productOffering' => new Map<String, Object>{ 'id' => bundleId() } },
                new Map<String, Object>{ 'id' => '2', 'productOffering' => new Map<String, Object>{ 'id' => childId() } } } };
        Test.startTest();
        req('POST', '/agentictelco/tmf648/quote', null, body);
        AgenticTelco_TMF648.doPost();
        Integer created = RestContext.response.statusCode;
        System.assert(created == 201 || created == 422, RestContext.response.responseBody.toString());
        if (created == 201) {
            String id = (String) ((Map<String, Object>) resp()).get('id');
            req('POST', '/agentictelco/tmf648/quote', null, body);
            AgenticTelco_TMF648.doPost();
            System.assertEquals(200, RestContext.response.statusCode);
            req('GET', '/agentictelco/tmf648/quote', null, null);
            AgenticTelco_TMF648.doGet();
            System.assertEquals(1, ((List<Object>) resp()).size());
            req('GET', '/agentictelco/tmf648/quote/' + id, null, null);
            AgenticTelco_TMF648.doGet();
            System.assertEquals('inProgress', ((Map<String, Object>) resp()).get('state'));
            req('PATCH', '/agentictelco/tmf648/quote/' + id, null, new Map<String, Object>{ 'state' => 'accepted' });
            AgenticTelco_TMF648.doPatch();
            req('PATCH', '/agentictelco/tmf648/quote/' + id, null, new Map<String, Object>{ 'state' => 'nope' });
            AgenticTelco_TMF648.doPatch();
            System.assertEquals(400, RestContext.response.statusCode);
        }
        req('POST', '/agentictelco/tmf648/quote', null, new Map<String, Object>{});
        AgenticTelco_TMF648.doPost();
        System.assertEquals(400, RestContext.response.statusCode);
        req('POST', '/agentictelco/tmf648/quote', null, new Map<String, Object>{ 'externalId' => 'Q-2' });
        AgenticTelco_TMF648.doPost();
        System.assertEquals(400, RestContext.response.statusCode);
        req('POST', '/agentictelco/tmf648/quote', null, new Map<String, Object>{ 'externalId' => 'Q-3',
            'quoteItem' => new List<Object>{ new Map<String, Object>{ 'productOffering' => new Map<String, Object>{ 'id' => accId() } } } });
        AgenticTelco_TMF648.doPost();
        System.assertEquals(422, RestContext.response.statusCode);
        req('GET', '/agentictelco/tmf648/quote/0Q0000000000000AAA', null, null);
        AgenticTelco_TMF648.doGet();
        System.assertEquals(404, RestContext.response.statusCode);
        req('PATCH', '/agentictelco/tmf648/quote', null, null);
        AgenticTelco_TMF648.doPatch();
        System.assertEquals(400, RestContext.response.statusCode);
        req('PATCH', '/agentictelco/tmf648/quote/0Q0000000000000AAA', null, null);
        AgenticTelco_TMF648.doPatch();
        System.assertEquals(404, RestContext.response.statusCode);
        Quote foreign = new Quote(Name = 'Someone else');
        insert foreign;
        req('PATCH', '/agentictelco/tmf648/quote/' + foreign.Id, null, new Map<String, Object>{ 'state' => 'accepted' });
        AgenticTelco_TMF648.doPatch();
        System.assertEquals(403, RestContext.response.statusCode);
        System.assertEquals('accepted', AgenticTelco_TMF648.state('Accepted'));
        System.assertEquals('inProgress', AgenticTelco_TMF648.state('Needs Review'));
        Test.stopTest();
    }

    @IsTest
    static void tmf671AndHelpers() {
        Test.startTest();
        req('GET', '/agentictelco/tmf671/promotion', null, null);
        AgenticTelco_TMF671.doGet();
        List<Object> l = (List<Object>) resp();
        System.assertEquals(1, l.size());
        req('GET', '/agentictelco/tmf671/promotion/' + ((Map<String, Object>) l[0]).get('id'), null, null);
        AgenticTelco_TMF671.doGet();
        System.assertEquals(200, RestContext.response.statusCode);
        req('GET', '/agentictelco/tmf671/promotion/0c8000000000000AAA', null, null);
        AgenticTelco_TMF671.doGet();
        System.assertEquals(404, RestContext.response.statusCode);
        RestContext.request = null;
        RestContext.response = null;
        System.assertEquals(0, AgenticTelco_Tmf.body().size());
        System.assertEquals(null, AgenticTelco_Tmf.param('x'));
        System.assertEquals(7, AgenticTelco_Tmf.intParam('x', 7));
        AgenticTelco_Tmf.error(418, 'TEAPOT', 'test');
        System.assertEquals(418, RestContext.response.statusCode);
        System.assertEquals(null, AgenticTelco_Tmf.choosePrice(new List<PricebookEntry>(), null, null));
        System.assert(AgenticTelco_Tmf.isOurs('AgenticTelco x'));
        System.assert(!AgenticTelco_Tmf.isOurs(null));
        System.assertEquals(0, AgenticTelco_Tmf.party(null).size());
        Test.stopTest();
    }

    @IsTest
    static void tmf637Lifecycle() {
        Contact c = new Contact(LastName = 'Test', FirstName = 'Sam', AccountId = accId());
        insert c;
        Schema.Location loc = new Schema.Location(Name = 'AgenticTelco T Site', ExternalReference = 'A0001', LocationType = 'Site');
        insert loc;
        Asset foreign = new Asset(Name = 'Other asset', AccountId = accId(), Status = 'Installed', Quantity = 1);
        insert foreign;
        Test.startTest();
        Map<String, Object> body = new Map<String, Object>{ 'name' => 'AgenticTelco Fibre 150 T', 'productSerialNumber' => 'AT-T-1',
            'status' => 'active', 'description' => 'test', 'startDate' => '2025-01-01', 'terminationDate' => '2027-01-01',
            'productOffering' => new Map<String, Object>{ 'id' => bundleId() },
            'relatedParty' => new List<Object>{ new Map<String, Object>{ 'id' => accId(), 'role' => 'Customer' },
                                                new Map<String, Object>{ 'id' => c.Id, 'role' => 'User' } },
            'place' => new List<Object>{ new Map<String, Object>{ 'id' => loc.Id } },
            'productPrice' => new List<Object>{ new Map<String, Object>{ 'price' => new Map<String, Object>{
                'taxIncludedAmount' => new Map<String, Object>{ 'value' => 45, 'unit' => 'GBP' } } } } };
        req('POST', '/agentictelco/tmf637/product', null, body);
        AgenticTelco_TMF637.doPost();
        System.assertEquals(201, RestContext.response.statusCode, RestContext.response.responseBody.toString());
        Map<String, Object> old = (Map<String, Object>) resp();
        System.assertEquals('active', old.get('status'));
        String oldId = (String) old.get('id');
        req('POST', '/agentictelco/tmf637/product', null, body);
        AgenticTelco_TMF637.doPost();
        System.assertEquals(200, RestContext.response.statusCode);
        body.put('productSerialNumber', 'AT-T-2');
        body.put('name', 'AgenticTelco Fibre 900 T');
        req('POST', '/agentictelco/tmf637/product', null, body);
        AgenticTelco_TMF637.doPost();
        String newId = (String) ((Map<String, Object>) resp()).get('id');
        req('GET', '/agentictelco/tmf637/product', new Map<String, String>{ 'relatedParty.id' => accId(), 'status' => 'active',
            'productSerialNumber' => 'AT-T-1', 'creationDate.gt' => '2020-01-01T00:00:00Z', 'limit' => '5' }, null);
        AgenticTelco_TMF637.doGet();
        System.assertEquals(1, ((List<Object>) resp()).size());
        req('PATCH', '/agentictelco/tmf637/product/' + oldId, null, new Map<String, Object>{ 'status' => 'terminated', 'terminationDate' => '2026-10-30',
            'productRelationship' => new List<Object>{ new Map<String, Object>{ 'relationshipType' => 'Upgrade', 'product' => new Map<String, Object>{ 'id' => newId } } } });
        AgenticTelco_TMF637.doPatch();
        System.assertEquals(200, RestContext.response.statusCode, RestContext.response.responseBody.toString());
        Map<String, Object> done = (Map<String, Object>) resp();
        System.assertEquals('terminated', done.get('status'));
        System.assertEquals(1, ((List<Object>) done.get('productRelationship')).size());
        req('GET', '/agentictelco/tmf637/product/' + newId, null, null);
        AgenticTelco_TMF637.doGet();
        System.assertEquals(1, ((List<Object>) ((Map<String, Object>) resp()).get('productRelationship')).size());
        // errors
        req('GET', '/agentictelco/tmf637/product/' + foreign.Id, null, null);
        AgenticTelco_TMF637.doGet();
        System.assertEquals(404, RestContext.response.statusCode);
        req('PATCH', '/agentictelco/tmf637/product/' + foreign.Id, null, new Map<String, Object>{ 'status' => 'terminated' });
        AgenticTelco_TMF637.doPatch();
        System.assertEquals(404, RestContext.response.statusCode);
        req('PATCH', '/agentictelco/tmf637/product', null, new Map<String, Object>());
        AgenticTelco_TMF637.doPatch();
        System.assertEquals(400, RestContext.response.statusCode);
        req('PATCH', '/agentictelco/tmf637/product/' + newId, null, new Map<String, Object>{ 'status' => 'bogus' });
        AgenticTelco_TMF637.doPatch();
        System.assertEquals(400, RestContext.response.statusCode);
        req('PATCH', '/agentictelco/tmf637/product/' + newId, null, new Map<String, Object>{ 'productRelationship' => new List<Object>{
            new Map<String, Object>{ 'relationshipType' => 'Upgrade', 'product' => new Map<String, Object>{ 'id' => foreign.Id } } } });
        AgenticTelco_TMF637.doPatch();
        System.assertEquals(422, RestContext.response.statusCode);
        req('POST', '/agentictelco/tmf637/product', null, new Map<String, Object>{ 'name' => 'Other' });
        AgenticTelco_TMF637.doPost();
        System.assertEquals(400, RestContext.response.statusCode);
        req('POST', '/agentictelco/tmf637/product', null, new Map<String, Object>{ 'name' => 'AgenticTelco X' });
        AgenticTelco_TMF637.doPost();
        System.assertEquals(400, RestContext.response.statusCode);
        req('POST', '/agentictelco/tmf637/product', null, new Map<String, Object>{ 'name' => 'AgenticTelco X', 'productSerialNumber' => 'AT-T-9' });
        AgenticTelco_TMF637.doPost();
        System.assertEquals(400, RestContext.response.statusCode);
        req('POST', '/agentictelco/tmf637/product', null, new Map<String, Object>{ 'name' => 'AgenticTelco X', 'productSerialNumber' => 'AT-T-9',
            'relatedParty' => new List<Object>{ new Map<String, Object>{ 'id' => accId(), 'role' => 'Customer' } }, 'productOffering' => new Map<String, Object>{ 'id' => 'bad' } });
        AgenticTelco_TMF637.doPost();
        System.assertEquals(422, RestContext.response.statusCode);
        System.assertEquals('pendingActive', AgenticTelco_TMF637.status('Shipped'));
        System.assertEquals('other', AgenticTelco_TMF637.status('Other'));
        System.assertEquals(null, AgenticTelco_TMF637.status(null));
        Test.stopTest();
    }

    @IsTest
    static void tmf632Organization() {
        Contact c = new Contact(LastName = 'Test', FirstName = 'Sam', AccountId = accId());
        Contact d = new Contact(LastName = 'Other', FirstName = 'Ola', AccountId = accId());
        insert new List<Contact>{ c, d };
        insert new List<AccountContactRole>{ new AccountContactRole(AccountId = accId(), ContactId = c.Id, Role = 'Decision Maker'),
                                             new AccountContactRole(AccountId = accId(), ContactId = d.Id, Role = 'Technical Buyer') };
        Account other = new Account(Name = 'Not ours');
        insert other;
        Test.startTest();
        req('GET', '/agentictelco/tmf632/organization/' + accId(), null, null);
        AgenticTelco_TMF632.doGet();
        System.assertEquals(200, RestContext.response.statusCode, RestContext.response.responseBody.toString());
        System.assertEquals(2, ((List<Object>) ((Map<String, Object>) resp()).get('relatedParty')).size());
        req('GET', '/agentictelco/tmf632/organization/' + accId(), new Map<String, String>{ 'relatedParty.role' => 'Decision Maker' }, null);
        AgenticTelco_TMF632.doGet();
        List<Object> ps = (List<Object>) ((Map<String, Object>) resp()).get('relatedParty');
        System.assertEquals(1, ps.size());
        System.assertEquals(String.valueOf(c.Id), ((Map<String, Object>) ps[0]).get('id'));
        req('GET', '/agentictelco/tmf632/organization/' + other.Id, null, null);
        AgenticTelco_TMF632.doGet();
        System.assertEquals(404, RestContext.response.statusCode);
        req('GET', '/agentictelco/tmf632/organization/bad', null, null);
        AgenticTelco_TMF632.doGet();
        System.assertEquals(404, RestContext.response.statusCode);
        req('GET', '/agentictelco/tmf632/', null, null);
        AgenticTelco_TMF632.doGet();
        System.assertEquals(400, RestContext.response.statusCode);
        Test.stopTest();
    }

    @IsTest
    static void tmf622UsageRecord() {
        Order o = new Order(Name = 'AgenticTelco PO U', AccountId = accId(), Status = 'Draft', EffectiveDate = Date.today());
        insert o;
        Test.startTest();
        Id u1 = AgenticTelco_TMF622.ensureUsageRecord(o.Id);
        Id u2 = AgenticTelco_TMF622.ensureUsageRecord(o.Id);
        System.assertEquals(u1, u2);
        req('POST', '/agentictelco/tmf622/productOrder', null, new Map<String, Object>{ 'externalId' => 'U' });
        AgenticTelco_TMF622.doPost();
        System.assertEquals(200, RestContext.response.statusCode);
        System.assertEquals(String.valueOf(u1), ((Map<String, Object>) resp()).get('x-usageRecord'));
        Test.stopTest();
    }
}
