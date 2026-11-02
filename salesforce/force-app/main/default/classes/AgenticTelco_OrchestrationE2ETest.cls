/**
 * End to end over the org's real EPC catalogue and Salesforce order orchestration (SeeAllData: the AgenticTelco
 * products, prices and bundle components; everything this test creates is rolled back).
 * TMF622 POST delete Fibre 150 + add Fibre 900 (replaces) -> PATCH inProgress (submitOrder, built-in decomposition, plan)
 * -> each plan step through the network order adapter (Mock), including 'Record the installed product (TMF637)' for
 * route CUSTOM_STEP -> GET with x-orchestration (item states completed, recurring prices, relationships) -> PATCH completed.
 */
@IsTest(SeeAllData=true)
private class AgenticTelco_OrchestrationE2ETest {
    static Object call(String method, String uri, Object body) {
        RestRequest r = new RestRequest();
        r.httpMethod = method;
        r.requestURI = '/services/apexrest' + uri;
        if (body != null) r.requestBody = Blob.valueOf(JSON.serialize(body));
        RestContext.request = r;
        RestContext.response = new RestResponse();
        if (method == 'POST') AgenticTelco_TMF622.doPost();
        else if (method == 'PATCH') AgenticTelco_TMF622.doPatch();
        else AgenticTelco_TMF622.doGet();
        return JSON.deserializeUntyped(RestContext.response.responseBody.toString());
    }

    @IsTest static void upgradeIsDecomposedAndOrchestrated() {
        AgenticTelco_NetworkAdapters.testConfig = new AgenticTelco_Network_Adapter__mdt(Mode__c = 'Mock');
        String first = AgenticTelco_OrchestrationSetup.run();
        String again = AgenticTelco_OrchestrationSetup.run();
        System.assert(again.contains('CFS products created: 0') && again.contains('decomposition rules created: 0') && again.contains('step definitions created: 0'), first + ' / ' + again);

        Map<String, Id> p = new Map<String, Id>();
        for (Product2 x : [SELECT Id, ProductCode FROM Product2 WHERE ProductCode IN ('AT-FIBRE-150', 'AT-FIBRE-900')]) p.put(x.ProductCode, x.Id);
        Account a = new Account(Name = 'AgenticTelco Orchestration E2E');
        insert a;
        Date contractEnd = Date.today().addDays(299);
        Asset cur = new Asset(Name = 'AgenticTelco Fibre 150 – E2E site', AccountId = a.Id, Product2Id = p.get('AT-FIBRE-150'), Status = 'Installed', Quantity = 1,
            Price = 27, InstallDate = Date.today().addDays(-430), UsageEndDate = contractEnd);
        insert cur;

        // upgrade as two linked items: delete Fibre 150, add Fibre 900 (replaces item 1)
        Map<String, Object> created = (Map<String, Object>) call('POST', '/agentictelco/tmf622/productOrder', new Map<String, Object>{
            'externalId' => 'E2E-' + Crypto.getRandomInteger(), 'relatedParty' => new List<Object>{ new Map<String, Object>{ 'id' => a.Id, 'role' => 'Customer' } },
            'productOrderItem' => new List<Object>{
                new Map<String, Object>{ 'id' => '1', 'action' => 'delete', 'quantity' => 1, 'product' => new Map<String, Object>{ 'id' => cur.Id } },
                new Map<String, Object>{ 'id' => '2', 'action' => 'add', 'quantity' => 1, 'productOffering' => new Map<String, Object>{ 'id' => p.get('AT-FIBRE-900') },
                    'productOrderItemRelationship' => new List<Object>{ new Map<String, Object>{ 'id' => '1', 'relationshipType' => 'replaces' } } } } });
        System.assertEquals(201, RestContext.response.statusCode, JSON.serialize(created));
        Id orderId = (Id) created.get('id');
        List<Object> items = (List<Object>) created.get('productOrderItem');
        System.assert(items.size() >= 4, 'delete line, add line and the add line\'s required components: ' + JSON.serialize(items));
        Map<String, String> lineAct = new Map<String, String>();
        Map<String, OrderItem> line = new Map<String, OrderItem>();
        for (OrderItem oi : [SELECT Id, Product2.ProductCode, OrderAction.Type, OrderAction.Subtype, Quantity, ServiceDate, EndDate FROM OrderItem WHERE OrderId = :orderId]) {
            lineAct.put(oi.Product2.ProductCode, oi.OrderAction.Type + (oi.OrderAction.Subtype == null ? '' : '/' + oi.OrderAction.Subtype));
            line.put(oi.Product2.ProductCode, oi);
        }
        System.assertEquals('Cancel/UpgradeFrom', lineAct.get('AT-FIBRE-150'), JSON.serialize(lineAct));
        System.assertEquals('Add/UpgradeTo', lineAct.get('AT-FIBRE-900'), JSON.serialize(lineAct));
        System.assertEquals('No Change', lineAct.get('AT-ACCESS-LINE'), 'component lines do not inherit the bundle action: ' + JSON.serialize(lineAct));
        System.assertEquals('Amend/UpgradeTo', lineAct.get('AT-ROUTER-WIFI6'), JSON.serialize(lineAct));
        System.assertEquals(Date.today(), line.get('AT-FIBRE-900').ServiceDate, 'new monthly price from the upgrade date');
        System.assertEquals(contractEnd, line.get('AT-FIBRE-900').EndDate, 'contract end carried over');
        System.assertEquals(4, line.size(), 'components hang off the add line only: ' + JSON.serialize(lineAct));

        Map<String, Object> started = (Map<String, Object>) call('PATCH', '/agentictelco/tmf622/productOrder/' + orderId, new Map<String, Object>{ 'state' => 'inProgress' });
        Map<String, Object> orch = (Map<String, Object>) started.get('x-orchestration');
        System.assertNotEquals(null, orch.get('fulfillmentPlanId'), JSON.serialize(orch));
        System.assertEquals(AgenticTelco_Orchestration.kinds().size(), ((List<Object>) orch.get('steps')).size(), JSON.serialize(orch));
        System.assert(JSON.serialize(orch.get('steps')).contains('Record the installed product (TMF637)') == (AgenticTelco_Assetisation.route() == AgenticTelco_Assetisation.CUSTOM_STEP), JSON.serialize(orch));
        // a second inProgress does not submit again
        Map<String, Object> replay = (Map<String, Object>) call('PATCH', '/agentictelco/tmf622/productOrder/' + orderId, new Map<String, Object>{ 'state' => 'inProgress' });
        System.assertEquals(orch.get('fulfillmentPlanId'), ((Map<String, Object>) replay.get('x-orchestration')).get('fulfillmentPlanId'));

        // fresh governor limits for the steps; no stopTest, so the plan's own async step flows are not run here
        Test.startTest();
        for (String k : AgenticTelco_Orchestration.kinds()) {
            if (k == 'PONR') continue;
            System.assertNotEquals(null, AgenticTelco_OrchestrationStep.run(orderId, k), k);
        }
        Map<String, String> act = new Map<String, String>();
        Integer bb = 0;
        for (FulfillmentOrderLineItem l : [SELECT Action, Product2.ProductCode FROM FulfillmentOrderLineItem WHERE FulfillmentOrder.OrderId = :orderId]) {
            act.put(l.Product2.ProductCode, l.Action);
            if (l.Product2.ProductCode == AgenticTelco_OrchestrationStep.CFS_BB) bb++;
        }
        System.assertEquals(1, bb, 'one broadband CFS line for delete + add: ' + JSON.serialize(act));
        System.assertEquals('AMEND', act.get(AgenticTelco_OrchestrationStep.CFS_BB), JSON.serialize(act));
        System.assertEquals('NOCHANGE', act.get(AgenticTelco_OrchestrationStep.CFS_ACCESS), JSON.serialize(act));
        System.assertEquals('AMEND', act.get(AgenticTelco_OrchestrationStep.CFS_ROUTER), JSON.serialize(act));
        System.assertEquals('Activated', [SELECT Status FROM Order WHERE Id = :orderId].Status);

        if (AgenticTelco_Assetisation.route() == AgenticTelco_Assetisation.CUSTOM_STEP) {
            Asset old = [SELECT Status, UsageEndDate FROM Asset WHERE Id = :cur.Id];
            System.assertEquals('Obsolete', old.Status);
            System.assertEquals(Date.today(), old.UsageEndDate, 'Fibre 150 ends on the upgrade date');
            Asset nw = [SELECT Id, Name, Status, Price, UsageEndDate, Product2.ProductCode FROM Asset WHERE AccountId = :a.Id AND ParentId = null AND Id != :cur.Id];
            System.assertEquals('AT-FIBRE-900', nw.Product2.ProductCode);
            System.assertEquals('Installed', nw.Status);
            System.assertEquals(line.get('AT-FIBRE-900').EndDate, nw.UsageEndDate);
            System.assert(nw.Name.endsWith(' – E2E site'), nw.Name);
            System.assertEquals(2, [SELECT COUNT() FROM Asset WHERE ParentId = :nw.Id], 'router and access line as children');
            System.assertEquals(1, [SELECT COUNT() FROM AssetRelationship WHERE AssetId = :cur.Id AND RelatedAssetId = :nw.Id AND RelationshipType = 'Upgrade']);
        }

        Map<String, Object> got = (Map<String, Object>) call('GET', '/agentictelco/tmf622/productOrder/' + orderId, null);
        Map<String, Object> v = (Map<String, Object>) got.get('x-orchestration');
        String dec = JSON.serialize(v.get('decomposition'));
        System.assert(dec.contains('"level":"CFS"') && dec.contains('"level":"RFS"') && dec.contains('"level":"Resource"') && dec.contains('"action":"delete"'), dec);
        System.assert(dec.contains('"level":"Product component"') && dec.contains('Fibre Access service (CFS)') && dec.contains('RFS Router configuration') && !dec.contains('nativeAction'), dec);
        System.assertEquals(0, [SELECT COUNT() FROM AgenticTelco_Network_Call__c WHERE Order__c = :orderId AND Api__c != 'TMF641' AND Api__c != 'Notify'], 'TMF641 is the only network API');
        Map<String, Object> so = (Map<String, Object>) v.get('serviceOrder');
        System.assertEquals('completed', so.get('state'));
        System.assertEquals(3, ((List<Object>) so.get('stateChange')).size());
        System.assert(((Map<String, Object>) so.get('networkFulfilment')).containsKey('serviceInventory'), JSON.serialize(so));
        System.assertEquals('completed', got.get('state'));
        String gotItems = JSON.serialize(got.get('productOrderItem'));
        System.assert(!gotItems.contains('"state":"acknowledged"') && gotItems.contains('"state":"completed"'), gotItems);
        System.assert(gotItems.contains('"relationshipType":"bundled"') && gotItems.contains('"relationshipType":"replaces"'), gotItems);
        System.assert(JSON.serialize(got.get('orderTotalPrice')).contains('"recurringChargePeriod":"month"'), JSON.serialize(got.get('orderTotalPrice')));
        call('PATCH', '/agentictelco/tmf622/productOrder/' + orderId, new Map<String, Object>{ 'state' => 'completed' });
        System.assertEquals(200, RestContext.response.statusCode, RestContext.response.responseBody.toString());
    }
}
