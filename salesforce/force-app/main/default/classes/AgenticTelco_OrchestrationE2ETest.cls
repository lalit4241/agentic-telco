/**
 * End to end over the org's real EPC catalogue and Salesforce order orchestration (SeeAllData: the AgenticTelco
 * products, prices and bundle components; everything this test creates is rolled back).
 * TMF622 POST modify (Fibre 150 -> Fibre 900) -> PATCH inProgress (submitOrder, built-in decomposition, plan)
 * -> each plan step through the network order adapter (Mock) -> GET with x-orchestration -> PATCH completed.
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
        Asset cur = new Asset(Name = 'AgenticTelco Fibre 150 E2E', AccountId = a.Id, Product2Id = p.get('AT-FIBRE-150'), Status = 'Installed', Quantity = 1);
        insert cur;

        Map<String, Object> created = (Map<String, Object>) call('POST', '/agentictelco/tmf622/productOrder', new Map<String, Object>{
            'externalId' => 'E2E-' + Crypto.getRandomInteger(), 'relatedParty' => new List<Object>{ new Map<String, Object>{ 'id' => a.Id, 'role' => 'Customer' } },
            'productOrderItem' => new List<Object>{ new Map<String, Object>{ 'id' => '1', 'action' => 'modify', 'quantity' => 1,
                'product' => new Map<String, Object>{ 'id' => cur.Id }, 'productOffering' => new Map<String, Object>{ 'id' => p.get('AT-FIBRE-900') } } } });
        System.assertEquals(201, RestContext.response.statusCode, JSON.serialize(created));
        Id orderId = (Id) created.get('id');
        List<Object> items = (List<Object>) created.get('productOrderItem');
        System.assert(items.size() >= 3, 'bundle line plus required components: ' + JSON.serialize(items));
        Map<String, String> lineAct = new Map<String, String>();
        for (OrderItem oi : [SELECT Product2.ProductCode, OrderAction.Type FROM OrderItem WHERE OrderId = :orderId]) lineAct.put(oi.Product2.ProductCode, oi.OrderAction.Type);
        System.assertEquals('Amend', lineAct.get('AT-FIBRE-900'), JSON.serialize(lineAct));
        System.assertEquals('No Change', lineAct.get('AT-ACCESS-LINE'), 'component lines do not inherit the bundle action: ' + JSON.serialize(lineAct));
        System.assertEquals('Amend', lineAct.get('AT-ROUTER-WIFI6'), JSON.serialize(lineAct));

        Map<String, Object> started = (Map<String, Object>) call('PATCH', '/agentictelco/tmf622/productOrder/' + orderId, new Map<String, Object>{ 'state' => 'inProgress' });
        Map<String, Object> orch = (Map<String, Object>) started.get('x-orchestration');
        System.assertNotEquals(null, orch.get('fulfillmentPlanId'), JSON.serialize(orch));
        System.assertEquals(7, ((List<Object>) orch.get('steps')).size(), JSON.serialize(orch));
        // a second inProgress does not submit again
        Map<String, Object> replay = (Map<String, Object>) call('PATCH', '/agentictelco/tmf622/productOrder/' + orderId, new Map<String, Object>{ 'state' => 'inProgress' });
        System.assertEquals(orch.get('fulfillmentPlanId'), ((Map<String, Object>) replay.get('x-orchestration')).get('fulfillmentPlanId'));

        // fresh governor limits for the steps; no stopTest, so the plan's own async step flows are not run here
        Test.startTest();
        for (String k : new List<String>{ 'VALIDATE_RESERVE', 'SUBMIT', 'AWAIT', 'SERVICES', 'NOTIFY', 'COMPLETE' }) {
            System.assertNotEquals(null, AgenticTelco_OrchestrationStep.run(orderId, k), k);
        }
        Map<String, String> act = new Map<String, String>();
        for (FulfillmentOrderLineItem l : [SELECT Action, Product2.ProductCode FROM FulfillmentOrderLineItem WHERE FulfillmentOrder.OrderId = :orderId]) act.put(l.Product2.ProductCode, l.Action);
        System.assertEquals('AMEND', act.get(AgenticTelco_OrchestrationStep.CFS_BB), JSON.serialize(act));
        System.assertEquals('NOCHANGE', act.get(AgenticTelco_OrchestrationStep.CFS_ACCESS), JSON.serialize(act));
        System.assertEquals('AMEND', act.get(AgenticTelco_OrchestrationStep.CFS_ROUTER), JSON.serialize(act));
        System.assertEquals('Activated', [SELECT Status FROM Order WHERE Id = :orderId].Status);

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
        call('PATCH', '/agentictelco/tmf622/productOrder/' + orderId, new Map<String, Object>{ 'state' => 'completed' });
        System.assertEquals(200, RestContext.response.statusCode, RestContext.response.responseBody.toString());
    }
}
