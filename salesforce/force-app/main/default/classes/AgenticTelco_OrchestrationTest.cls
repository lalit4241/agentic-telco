@IsTest
private class AgenticTelco_OrchestrationTest {
    class HttpOk implements HttpCalloutMock {
        Integer code;
        HttpOk(Integer code) { this.code = code; }
        public HttpResponse respond(HttpRequest r) {
            System.assert(r.getEndpoint().startsWith('callout:AgenticTelco_NC/tmf-api/'), r.getEndpoint());
            HttpResponse res = new HttpResponse();
            res.setStatusCode(code);
            res.setBody('{"id":"X1","state":"acknowledged","method":"' + r.getMethod() + '"}');
            return res;
        }
    }

    static Order newOrder() {
        Account a = new Account(Name = 'AgenticTelco Orch Unit');
        insert a;
        Order o = new Order(Name = 'AgenticTelco PO UNIT-1', AccountId = a.Id, Status = 'Draft', EffectiveDate = Date.today());
        insert o;
        return [SELECT Id, OrderNumber FROM Order WHERE Id = :o.Id];
    }

    static void logSo(Id orderId, String id, Map<String, Object> so) {
        so.put('id', id);
        insert new AgenticTelco_Network_Call__c(Order__c = orderId, Api__c = 'TMF641', Network_Id__c = id, State__c = (String) so.get('state'),
            Response__c = JSON.serialize(so));
    }

    @IsTest static void viewCarriesTheTmf641Payload() {
        Order o = newOrder();
        insert new List<AgenticTelco_Network_Call__c>{
            new AgenticTelco_Network_Call__c(Order__c = o.Id, Api__c = 'TMF641', Operation__c = 'POST /serviceOrder', Network_Id__c = 'SO-A',
                State__c = 'acknowledged', Request__c = '{"externalId":"E1"}', Response__c = '{"id":"SO-A","state":"acknowledged"}'),
            new AgenticTelco_Network_Call__c(Order__c = o.Id, Api__c = 'TMF641', Operation__c = 'POST /serviceOrder', Network_Id__c = 'SO-B',
                State__c = 'acknowledged', Request__c = 'not json', Response__c = null),
            new AgenticTelco_Network_Call__c(Order__c = o.Id, Api__c = 'TMF641', Operation__c = 'GET /serviceOrder/SO-A', Network_Id__c = 'SO-A', State__c = 'completed') };
        Map<String, Object> holder = new Map<String, Object>();
        List<Object> nc = AgenticTelco_Orchestration.networkCalls(o.Id, holder);
        System.assertEquals('SO-A', ((Map<String, Object>) holder.get('serviceOrder')).get('id'));
        System.assertEquals(3, nc.size());
        Map<String, Object> posted = null, raw = null;
        for (Object x : nc) {
            Map<String, Object> m = (Map<String, Object>) x;
            if (m.get('networkId') == 'SO-A' && m.containsKey('request')) posted = m;
            if (m.get('networkId') == 'SO-B') raw = m;
        }
        System.assertEquals('E1', ((Map<String, Object>) posted.get('request')).get('externalId'));
        System.assertEquals('not json', raw.get('request'));
        System.assertEquals(null, raw.get('response'));
    }

    @IsTest static void factoryPicksImplementationFromMetadata() {
        System.assert(AgenticTelco_NetworkAdapters.current() instanceof AgenticTelco_MockNetworkAdapter, 'Default record is Mock');
        AgenticTelco_NetworkAdapters.testConfig = new AgenticTelco_Network_Adapter__mdt(Mode__c = 'Callout', Named_Credential__c = 'AgenticTelco_NC');
        System.assertEquals('Callout', AgenticTelco_NetworkAdapters.mode());
        AgenticTelco_NetworkOrderAdapter a = AgenticTelco_NetworkAdapters.current();
        System.assertEquals('Callout', a.mode());
        AgenticTelco_NetworkAdapters.testConfig = new AgenticTelco_Network_Adapter__mdt(Mode__c = 'Callout');
        try { AgenticTelco_NetworkAdapters.current(); System.assert(false); } catch (AgenticTelco_NetworkAdapters.AdapterException e) { System.assert(e.getMessage().contains('Named_Credential')); }
        AgenticTelco_NetworkAdapters.testConfig = new AgenticTelco_Network_Adapter__mdt(Mode__c = 'Mock');
        System.assertEquals('Mock', AgenticTelco_NetworkAdapters.current().mode());
    }

    @IsTest static void calloutAdapterUsesNamedCredential() {
        AgenticTelco_CalloutNetworkAdapter a = new AgenticTelco_CalloutNetworkAdapter('AgenticTelco_NC');
        Test.setMock(HttpCalloutMock.class, new HttpOk(201));
        Test.startTest();
        System.assert(a.submitServiceOrder('{}').contains('POST'));
        System.assert(a.getServiceOrder('SO-1').contains('GET'));
        Test.setMock(HttpCalloutMock.class, new HttpOk(503));
        try { a.getServiceOrder('SO-1'); System.assert(false); } catch (AgenticTelco_NetworkAdapters.AdapterException e) { System.assert(e.getMessage().contains('503')); }
        Test.stopTest();
    }

    @IsTest static void mockAdapterSimulatesNetwork() {
        AgenticTelco_MockNetworkAdapter m = new AgenticTelco_MockNetworkAdapter();
        System.assertEquals('Mock', m.mode());
        String so = JSON.serialize(new Map<String, Object>{ 'externalId' => 'AgenticTelco-00000999', 'serviceOrderItem' => new List<Object>{
            item('1', 'modify', AgenticTelco_OrchestrationStep.CFS_BB, true),
            item('2', 'noChange', AgenticTelco_OrchestrationStep.CFS_ACCESS, false),
            item('3', 'modify', AgenticTelco_OrchestrationStep.CFS_ROUTER, false),
            item('4', 'add', AgenticTelco_OrchestrationStep.CFS_ROUTER, false),
            item('5', 'delete', 'Other', false) } });
        Map<String, Object> s1 = (Map<String, Object>) JSON.deserializeUntyped(m.submitServiceOrder(so));
        System.assertEquals('SO-00000999', s1.get('id'));
        System.assertEquals('acknowledged', s1.get('state'));
        Map<String, Object> s2 = (Map<String, Object>) JSON.deserializeUntyped(m.submitServiceOrder(so));
        System.assertEquals(s1.get('id'), s2.get('id'), 'idempotent on externalId');
        System.assertEquals(String.valueOf(s1.get('orderDate')), String.valueOf(s2.get('orderDate')), 'same stored order returned');
        String raw = JSON.serialize(s1);
        System.assert(raw.contains('RFS Bandwidth profile') && raw.contains('"x-action":"delete"') && raw.contains('RES-ONT-') && raw.contains('RFS Router configuration'), raw);
        Map<String, Object> nf0 = (Map<String, Object>) s1.get('x-networkFulfilment');
        System.assertEquals('RSV-00000999', ((Map<String, Object>) nf0.get('reservation')).get('id'));
        System.assert(!nf0.containsKey('resourceInventory'), 'inventory updates only once completed');
        System.assertEquals('inProgress', ((Map<String, Object>) JSON.deserializeUntyped(m.getServiceOrder('SO-00000999'))).get('state'));
        Map<String, Object> done = (Map<String, Object>) JSON.deserializeUntyped(m.getServiceOrder('SO-00000999'));
        System.assertEquals('completed', done.get('state'));
        System.assertEquals(3, ((List<Object>) done.get('x-stateChange')).size());
        Map<String, Object> nf = (Map<String, Object>) done.get('x-networkFulfilment');
        System.assert(nf.containsKey('resourceInventory') && nf.containsKey('serviceInventory'), JSON.serialize(nf));
        String doneRaw = JSON.serialize(done);
        System.assert(doneRaw.contains('"resourceStatus":"removed"') && doneRaw.contains('"resourceStatus":"installed"') && doneRaw.contains('"resourceStatus":"inUse"'), doneRaw);
        System.assertEquals('completed', ((Map<String, Object>) JSON.deserializeUntyped(m.getServiceOrder('SO-00000999'))).get('state'));
        try { m.getServiceOrder('SO-NOPE'); System.assert(false); } catch (AgenticTelco_NetworkAdapters.AdapterException e) { System.assert(e.getMessage().contains('404')); }
        System.assertEquals('0', AgenticTelco_MockNetworkAdapter.suffix(null));
        System.assertEquals('ABC', AgenticTelco_MockNetworkAdapter.suffix('a-b-c'));
    }

    static Map<String, Object> item(String id, String action, String spec, Boolean speed) {
        Map<String, Object> svc = new Map<String, Object>{ 'serviceSpecification' => new Map<String, Object>{ 'id' => spec } };
        if (speed) svc.put('serviceCharacteristic', new List<Object>{ new Map<String, Object>{ 'name' => 'other', 'value' => 1 },
                                                                      new Map<String, Object>{ 'name' => 'downloadSpeedMbps', 'value' => 900 } });
        return new Map<String, Object>{ 'id' => id, 'action' => action, 'service' => svc };
    }

    @IsTest static void actionCodesFollowTheInstalledBase() {
        String bb = AgenticTelco_OrchestrationStep.CFS_BB, acc = AgenticTelco_OrchestrationStep.CFS_ACCESS, rt = AgenticTelco_OrchestrationStep.CFS_ROUTER;
        System.assertEquals('modify', AgenticTelco_OrchestrationStep.decideFor(bb, 'ADD', true, 150, 900)[0]);
        System.assertEquals('noChange', AgenticTelco_OrchestrationStep.decideFor(bb, 'ADD', true, 900, 900)[0]);
        System.assertEquals('add', AgenticTelco_OrchestrationStep.decideFor(bb, 'ADD', false, null, 900)[0]);
        System.assertEquals('noChange', AgenticTelco_OrchestrationStep.decideFor(acc, 'ADD', true, 150, 900)[0]);
        System.assertEquals('add', AgenticTelco_OrchestrationStep.decideFor(acc, 'ADD', false, null, 900)[0]);
        System.assertEquals('modify', AgenticTelco_OrchestrationStep.decideFor(rt, 'ADD', true, 150, 900)[0]);
        System.assertEquals('noChange', AgenticTelco_OrchestrationStep.decideFor(rt, 'ADD', true, 900, 500)[0]);
        System.assertEquals('add', AgenticTelco_OrchestrationStep.decideFor(rt, 'ADD', false, null, 900)[0]);
        System.assertEquals('delete', AgenticTelco_OrchestrationStep.decideFor('X', 'CANCEL', true, 1, 2)[0]);
        System.assertEquals('add', AgenticTelco_OrchestrationStep.decideFor('X', null, true, 1, 2)[0]);
    }

    @IsTest static void componentLinesCarryTheirOwnOrderAction() {
        System.assertEquals('No Change', AgenticTelco_TMF622.newAction(null, 'noChange').Type);
        System.assertEquals('UpgradeTo', AgenticTelco_TMF622.newAction(null, 'modify').Subtype);
        System.assertEquals('Add', AgenticTelco_TMF622.newAction(null, 'add').Type);
    }

    @IsTest static void stepsGuardAndLog() {
        Order o = newOrder();
        for (String k : new List<String>{ 'VALIDATE_RESERVE', 'AWAIT', 'SERVICES', 'BOGUS' }) {
            try { AgenticTelco_OrchestrationStep.run(o.Id, k); System.assert(false, k); } catch (AgenticTelco_NetworkAdapters.AdapterException e) { System.assert(e.getMessage() != null); }
        }
        AgenticTelco_OrchestrationStep.Request rq = new AgenticTelco_OrchestrationStep.Request();
        rq.orderId = o.Id;
        rq.stepKind = 'NOTIFY';
        System.assert(AgenticTelco_OrchestrationStep.invoke(new List<AgenticTelco_OrchestrationStep.Request>{ rq })[0].summary.contains('is live'));
        System.assert(AgenticTelco_OrchestrationStep.run(o.Id, 'SUBMIT').contains('TMF641 SO-'));
        System.assert(AgenticTelco_OrchestrationStep.run(o.Id, 'SUBMIT').contains('already sent'));
        System.assert(AgenticTelco_OrchestrationStep.run(o.Id, 'AWAIT').contains('completed'));
        System.assert(AgenticTelco_OrchestrationStep.run(o.Id, 'SERVICES').startsWith('Network result'));
        System.assertEquals(2, [SELECT COUNT() FROM AgenticTelco_Network_Call__c WHERE Order__c = :o.Id AND Operation__c LIKE 'GET%']);
        System.assertEquals(0, [SELECT COUNT() FROM AgenticTelco_Network_Call__c WHERE Order__c = :o.Id AND Api__c IN ('TMF685', 'TMF639', 'TMF638')], 'TMF641 is the only network API');
        Map<String, Object> v = AgenticTelco_Orchestration.view(o.Id);
        System.assertEquals('notSubmitted', v.get('status'));
        System.assertEquals(AgenticTelco_Orchestration.NO_PLAN, v.get('error'));
        System.assertEquals('Fibre Access service (CFS)', AgenticTelco_OrchestrationStep.cfsLabel(AgenticTelco_OrchestrationStep.CFS_ACCESS));
        System.assertEquals('Installation service (CFS)', AgenticTelco_OrchestrationStep.cfsLabel(AgenticTelco_OrchestrationStep.CFS_INSTALL));
        System.assertEquals('X', AgenticTelco_OrchestrationStep.cfsLabel('X'));
        System.assertEquals('AgenticTelco 4. Point of no return', AgenticTelco_Orchestration.stepName('PONR'));
        System.assertEquals('X', AgenticTelco_Orchestration.stepName('X'));
        AgenticTelco_Orchestration.skipFlowInTest = true;
        System.assertEquals(null, AgenticTelco_Orchestration.submit(o.Id));
        System.assertEquals(0, AgenticTelco_OrchestrationStep.characteristics(AgenticTelco_OrchestrationStep.CFS_INSTALL, 900, 150).size());
        System.assertEquals(2, AgenticTelco_OrchestrationStep.characteristics(AgenticTelco_OrchestrationStep.CFS_ROUTER, 900, 150).size());
        Product2 named = new Product2(Name = 'AgenticTelco Fibre 500 test', ProductCode = 'AT-TEST-500');
        Product2 unnamed = new Product2(Name = 'AgenticTelco Fibre', ProductCode = 'AT-TEST-X');
        insert new List<Product2>{ named, unnamed };
        Map<Id, Integer> sp = AgenticTelco_OrchestrationStep.speeds(new Set<Id>{ named.Id, unnamed.Id });
        System.assertEquals(500, sp.get(named.Id));
        System.assert(!sp.containsKey(unnamed.Id));
        // a BB modify without a speed characteristic still decomposes
        String raw = new AgenticTelco_MockNetworkAdapter().submitServiceOrder(JSON.serialize(new Map<String, Object>{ 'externalId' => 'AgenticTelco-00000998',
            'serviceOrderItem' => new List<Object>{ item('1', 'modify', AgenticTelco_OrchestrationStep.CFS_BB, false) } }));
        System.assert(raw.contains('SO-00000998'), raw);
    }

    @IsTest static void awaitAndServicesHandleNetworkStates() {
        Order o = newOrder();
        logSo(o.Id, 'SO-F', new Map<String, Object>{ 'state' => 'failed' });
        try { AgenticTelco_OrchestrationStep.run(o.Id, 'AWAIT'); System.assert(false); } catch (AgenticTelco_NetworkAdapters.AdapterException e) { System.assert(e.getMessage().contains('failed')); }
        logSo(o.Id, 'SO-H', new Map<String, Object>{ 'state' => 'held' });
        try { AgenticTelco_OrchestrationStep.run(o.Id, 'AWAIT'); System.assert(false); } catch (AgenticTelco_NetworkAdapters.AdapterException e) { System.assert(e.getMessage().contains('still held')); }
        try { AgenticTelco_OrchestrationStep.run(o.Id, 'SERVICES'); System.assert(false); } catch (AgenticTelco_NetworkAdapters.AdapterException e) { System.assert(e.getMessage().contains('not completed')); }
        logSo(o.Id, 'SO-C', new Map<String, Object>{ 'state' => 'completed', 'x-networkFulfilment' => new Map<String, Object>{
                'resourceInventory' => new Map<String, Object>{ 'updated' => new List<Object>{ 1, 2 } }, 'serviceInventory' => new Map<String, Object>{ 'updated' => new List<Object>{ 1 } } },
            'serviceOrderItem' => new List<Object>{
            new Map<String, Object>{ 'action' => 'modify', 'service' => new Map<String, Object>{ 'id' => 'CFS-BB-1', 'name' => 'BB' } },
            new Map<String, Object>{ 'action' => 'noChange', 'service' => new Map<String, Object>{ 'id' => 'CFS-ACC-1', 'name' => 'ACC' } },
            new Map<String, Object>{ 'action' => 'delete', 'service' => new Map<String, Object>{ 'id' => 'CFS-X-1', 'name' => 'X' } } } });
        String s = AgenticTelco_OrchestrationStep.run(o.Id, 'SERVICES');
        System.assert(s.contains('BB modify') && s.contains('ACC noChange') && s.contains('X delete') && s.contains('1 services (TMF638), 2 resources (TMF639)'), s);
        System.assert(AgenticTelco_OrchestrationStep.run(o.Id, 'AWAIT').contains(': '));
    }
}
