/**
 * The AgenticTelco steps of the Salesforce order orchestration plan (DRO step group 'AgenticTelco Fibre Upgrade
 * Fulfilment'). Each AutoTask step runs an AgenticTelco_ autolaunched flow, which calls this invocable with the order id
 * (planSourceIdentifierId) and the step kind. Salesforce makes ONE outbound network interaction, TMF641 (POST plus
 * status reads), through AgenticTelco_NetworkOrderAdapter only (AgenticTelco_NetworkAdapters.current()), never to an
 * implementation directly. Every call is logged in AgenticTelco_Network_Call__c, written after the step's calls so that
 * Callout mode never has uncommitted work. Reservation, resource inventory and service inventory are the network's own
 * work behind TMF641 and come back as data in the TMF641 response (x-networkFulfilment).
 *   VALIDATE_RESERVE  validate the order and set the action codes on the CFS lines, derived from the installed base
 *                     (TMF637 product inventory). The built-in decomposition creates the lines; it does not set these codes.
 *                     No network call.
 *   SUBMIT            one TMF641 service order with the CFS items (idempotency key from the order number)
 *   AWAIT             TMF641 state until completed (acknowledged -> inProgress -> completed)
 *   SERVICES          record the network result from the completed TMF641 response (the network keeps its own resource
 *                     and service inventories, TMF639 and TMF638). No network call.
 *   ASSETIZE          record the installed product (TMF637): the one writer of the Assets, only in the plan for assetisation
 *                     route CUSTOM_STEP (AgenticTelco_Assetisation). Fails the step (and stops the run) on any error.
 *   NOTIFY            the customer notification (recorded on the order)
 *   COMPLETE          order Activated
 */
public with sharing class AgenticTelco_OrchestrationStep {
    public static final String SPEED_CODE = 'AT_ATT_DL_SPEED';
    public static final String CFS_BB = 'AgenticTelco_CFS_Fibre_Broadband';
    public static final String CFS_ACCESS = 'AgenticTelco_CFS_Fibre_Access';
    public static final String CFS_ROUTER = 'AgenticTelco_CFS_Managed_Router';
    public static final String CFS_INSTALL = 'AgenticTelco_CFS_Installation';
    public static final Map<String, String> TO_TMF = new Map<String, String>{ 'ADD' => 'add', 'AMEND' => 'modify', 'NOCHANGE' => 'noChange', 'CANCEL' => 'delete', 'RENEW' => 'modify' };
    public static final Map<String, String> TO_NATIVE = new Map<String, String>{ 'add' => 'ADD', 'modify' => 'AMEND', 'noChange' => 'NOCHANGE', 'delete' => 'CANCEL' };

    public class Request {
        @InvocableVariable(required=true label='Order Id') public String orderId;
        @InvocableVariable(required=true label='Step kind') public String stepKind;
    }
    public class Result {
        @InvocableVariable(label='Summary') public String summary;
    }

    @InvocableMethod(label='AgenticTelco orchestration step' description='Runs one AgenticTelco fulfilment step through the network order adapter interface' category='AgenticTelco')
    public static List<Result> invoke(List<Request> reqs) {
        List<Result> out = new List<Result>();
        for (Request r : reqs) {
            Result x = new Result();
            x.summary = run(Id.valueOf(r.orderId), r.stepKind);
            out.add(x);
        }
        return out;
    }

    // ---------------------------------------------------------------------------------------------------------------
    List<AgenticTelco_Network_Call__c> calls = new List<AgenticTelco_Network_Call__c>();
    final AgenticTelco_NetworkOrderAdapter net;
    final Order ord;
    final String key;
    final String stepName;
    final Id assetId;
    final Integer oldSpeed;
    final Integer newSpeed;
    final String bundleName;

    AgenticTelco_OrchestrationStep(Id orderId, String kind) {
        net = AgenticTelco_NetworkAdapters.current();
        ord = [SELECT Id, Name, OrderNumber, Status, AccountId, Account.Name, FulfillmentPlanId FROM Order WHERE Id = :orderId];
        key = idempotencyKey(ord);
        stepName = AgenticTelco_Orchestration.stepName(kind);
        Id newProduct;
        Id oldProduct;
        Id aId;
        String bName;
        for (OrderItem oi : [SELECT Product2Id, Product2.Name, Description FROM OrderItem WHERE OrderId = :orderId ORDER BY CreatedDate, Id]) {
            Map<String, Object> p = AgenticTelco_TMF622.itemProduct(oi.Description);
            if (newProduct == null && !AgenticTelco_TMF622.isComponentLine(oi.Description) && AgenticTelco_TMF622.itemAction(oi.Description) != 'delete') { newProduct = oi.Product2Id; bName = oi.Product2.Name; }
            if (p != null && aId == null) aId = Id.valueOf((String) p.get('id'));
        }
        if (aId != null) for (Asset a : [SELECT Product2Id FROM Asset WHERE Id = :aId]) oldProduct = a.Product2Id;
        Map<Id, Integer> sp = speeds(new Set<Id>{ newProduct, oldProduct });
        assetId = aId;
        bundleName = bName;
        newSpeed = sp.get(newProduct);
        oldSpeed = oldProduct == null ? null : sp.get(oldProduct);
    }

    public static String run(Id orderId, String kind) {
        AgenticTelco_OrchestrationStep s = new AgenticTelco_OrchestrationStep(orderId, kind);
        String out;
        try {
            if (kind == 'VALIDATE_RESERVE') out = s.validateAndReserve();
            else if (kind == 'SUBMIT') out = s.submit();
            else if (kind == 'AWAIT') out = s.awaitActivation();
            else if (kind == 'SERVICES') out = s.services();
            else if (kind == 'ASSETIZE') out = AgenticTelco_Assetisation.record(orderId);
            else if (kind == 'NOTIFY') out = s.notifyCustomer();
            else if (kind == 'COMPLETE') out = s.complete();
            else throw new AgenticTelco_NetworkAdapters.AdapterException('Unknown AgenticTelco step kind ' + kind);
        } finally {
            if (!s.calls.isEmpty()) insert s.calls;
        }
        return out;
    }

    public static String idempotencyKey(Order o) { return 'AgenticTelco-' + o.OrderNumber; }

    // --------------------------------------------------------------------------------------------- 1 validate + action codes
    String validateAndReserve() {
        List<FulfillmentOrderLineItem> folis = folis();
        if (folis.isEmpty()) throw new AgenticTelco_NetworkAdapters.AdapterException('No decomposed CFS lines on order ' + ord.OrderNumber);
        List<String> notes = new List<String>();
        List<FulfillmentOrderLineItem> changes = new List<FulfillmentOrderLineItem>();
        for (FulfillmentOrderLineItem l : folis) {
            String[] d = decide(l.Product2.ProductCode, l.Action);
            l.Action = TO_NATIVE.get(d[0]);
            l.Description = ('tmf=' + d[0] + '; why=' + d[1]).left(255);
            changes.add(new FulfillmentOrderLineItem(Id = l.Id, Action = l.Action, Description = l.Description));
            notes.add(l.Product2.Name + ' ' + d[0]);
        }
        update changes;
        return 'Action codes (from the installed base, TMF637): ' + String.join(notes, ', ');
    }

    /** TMF action code for one CFS, from the installed base. Returns [tmfAction, why]. */
    String[] decide(String code, String current) { return decideFor(code, current, assetId != null, oldSpeed, newSpeed); }

    public static String[] decideFor(String code, String current, Boolean installed, Integer oldSpeed, Integer newSpeed) {
        if (code == CFS_BB) {
            if (!installed) return new String[]{ 'add', 'New broadband service at ' + newSpeed + ' Mbps' };
            if (oldSpeed != newSpeed) return new String[]{ 'modify', 'Speed ' + oldSpeed + ' to ' + newSpeed + ' Mbps on the installed product (TMF637)' };
            return new String[]{ 'noChange', 'Speed already ' + newSpeed + ' Mbps' };
        }
        if (code == CFS_ACCESS) {
            return installed ? new String[]{ 'noChange', 'FTTP access line already in place at the site' } : new String[]{ 'add', 'New FTTP access line' };
        }
        if (code == CFS_ROUTER) {
            if (!installed) return new String[]{ 'add', 'New managed router (CPE)' };
            if (oldSpeed == null || newSpeed == null || newSpeed > oldSpeed) return new String[]{ 'modify', 'Managed Router (CPE): current router is not ' + newSpeed + '-capable, so the network swaps it' };
            return new String[]{ 'noChange', 'Current router supports ' + newSpeed + ' Mbps' };
        }
        String t = TO_TMF.containsKey(current) ? TO_TMF.get(current) : 'add';
        return new String[]{ t, 'From the decomposition' };
    }

    // --------------------------------------------------------------------------------------------- 2 TMF641 submit
    String submit() {
        AgenticTelco_Network_Call__c prior = lastServiceOrder(ord.Id);
        if (prior != null) return 'TMF641 ' + prior.Network_Id__c + ' already sent (idempotent on ' + key + ')';
        List<Object> items = new List<Object>();
        Integer n = 0;
        String s = assetId == null ? null : String.valueOf(assetId).right(8);
        for (FulfillmentOrderLineItem l : folis()) {
            n++;
            String act = TO_TMF.containsKey(l.Action) ? TO_TMF.get(l.Action) : 'add';
            String code = l.Product2.ProductCode;
            Map<String, Object> svc = new Map<String, Object>{ 'name' => cfsLabel(code), '@type' => 'CustomerFacingService',
                'serviceSpecification' => new Map<String, Object>{ 'id' => code, 'name' => l.Product2.Name, '@referredType' => 'CustomerFacingServiceSpecification' },
                'serviceCharacteristic' => characteristics(code, newSpeed, oldSpeed) };
            if (act != 'add' && s != null) svc.put('id', abbr(code) + '-' + s);
            items.add(new Map<String, Object>{ 'id' => String.valueOf(n), 'action' => act, 'quantity' => 1, '@type' => 'ServiceOrderItem', 'service' => svc,
                'x-fulfillmentOrderLineItem' => new Map<String, Object>{ 'id' => l.Id, 'action' => l.Action } });
        }
        Map<String, Object> so = new Map<String, Object>{ 'externalId' => key, '@type' => 'ServiceOrder', 'category' => 'AgenticTelco fibre upgrade',
            'description' => 'Network service order for ' + ord.OrderNumber + ' (' + bundleName + ')', 'priority' => '4',
            'requestedStartDate' => Datetime.now().formatGmt('yyyy-MM-dd\'T\'HH:mm:ss\'Z\''),
            'externalReference' => new List<Object>{ new Map<String, Object>{ 'externalReferenceType' => 'ProductOrder', 'name' => ord.OrderNumber, 'id' => ord.Id } },
            'relatedParty' => customer(), 'serviceOrderItem' => items };
        String rq = JSON.serialize(so);
        Map<String, Object> r = call('TMF641', 'POST /tmf-api/serviceOrdering/v4/serviceOrder', rq, net.submitServiceOrder(rq), 'state');
        return 'TMF641 ' + r.get('id') + ' ' + r.get('state') + ' (' + n + ' CFS items)';
    }

    @TestVisible static List<Object> characteristics(String code, Integer newSpeed, Integer oldSpeed) {
        if (code == CFS_BB) return new List<Object>{ new Map<String, Object>{ 'name' => 'downloadSpeedMbps', 'valueType' => 'integer', 'value' => newSpeed, 'x-previousValue' => oldSpeed } };
        if (code == CFS_ACCESS) return new List<Object>{ new Map<String, Object>{ 'name' => 'accessTechnology', 'value' => 'FTTP' } };
        if (code == CFS_ROUTER) return new List<Object>{ new Map<String, Object>{ 'name' => 'cpeModel', 'value' => 'Managed Router Wi-Fi 6' },
                                                         new Map<String, Object>{ 'name' => 'maxThroughputMbps', 'valueType' => 'integer', 'value' => newSpeed } };
        return new List<Object>();
    }

    static String abbr(String code) {
        return code == CFS_BB ? 'CFS-BB' : code == CFS_ACCESS ? 'CFS-ACC' : code == CFS_ROUTER ? 'CFS-CPE' : 'CFS';
    }

    // --------------------------------------------------------------------------------------------- 3 TMF641 await
    String awaitActivation() {
        AgenticTelco_Network_Call__c last = lastServiceOrder(ord.Id);
        if (last == null) throw new AgenticTelco_NetworkAdapters.AdapterException('No TMF641 service order sent for ' + ord.OrderNumber);
        String state = last.State__c;
        List<String> seen = new List<String>();
        for (Integer i = 0; i < 5 && state != 'completed'; i++) {
            Map<String, Object> r = call('TMF641', 'GET /tmf-api/serviceOrdering/v4/serviceOrder/' + last.Network_Id__c, null, net.getServiceOrder(last.Network_Id__c), 'state');
            state = AgenticTelco_Tmf.str(r.get('state'));
            seen.add(state);
            if (state == 'failed' || state == 'rejected') throw new AgenticTelco_NetworkAdapters.AdapterException('TMF641 ' + last.Network_Id__c + ' ' + state);
        }
        if (state != 'completed') throw new AgenticTelco_NetworkAdapters.AdapterException('TMF641 ' + last.Network_Id__c + ' still ' + state + ': retry');
        return 'TMF641 ' + last.Network_Id__c + ': ' + String.join(seen, ' -> ');
    }

    // --------------------------------------------------------------------------------------------- 5 network result
    /** Reads the completed TMF641 response: the network's own breakdown and its inventory updates. Salesforce makes no call here. */
    String services() {
        AgenticTelco_Network_Call__c last = lastServiceOrder(ord.Id);
        if (last == null || last.State__c != 'completed') throw new AgenticTelco_NetworkAdapters.AdapterException('TMF641 not completed for ' + ord.OrderNumber);
        Map<String, Object> so = (Map<String, Object>) JSON.deserializeUntyped(last.Response__c);
        List<String> done = new List<String>();
        for (Object o : AgenticTelco_Tmf.toList(so.get('serviceOrderItem'))) {
            Map<String, Object> it = AgenticTelco_Tmf.toMap(o);
            done.add(AgenticTelco_Tmf.toMap(it.get('service')).get('name') + ' ' + it.get('action'));
        }
        Map<String, Object> nf = AgenticTelco_Tmf.toMap(so.get('x-networkFulfilment'));
        Integer res = AgenticTelco_Tmf.toList(AgenticTelco_Tmf.toMap(nf.get('resourceInventory')).get('updated')).size();
        Integer svc = AgenticTelco_Tmf.toList(AgenticTelco_Tmf.toMap(nf.get('serviceInventory')).get('updated')).size();
        return 'Network result (TMF641 ' + so.get('id') + ' completed): ' + String.join(done, ', ') + '. The network updated its own inventories: '
            + svc + ' services (TMF638), ' + res + ' resources (TMF639).';
    }

    /** Display name of a CFS, distinct from the commercial bundle components (e.g. 'Fibre Access Line' product vs 'Fibre Access service (CFS)'). */
    public static String cfsLabel(String code) {
        return code == CFS_BB ? 'Fibre Broadband service (CFS)' : code == CFS_ACCESS ? 'Fibre Access service (CFS)'
             : code == CFS_ROUTER ? 'Managed Router service (CFS)' : code == CFS_INSTALL ? 'Installation service (CFS)' : code;
    }

    // --------------------------------------------------------------------------------------------- 6 notify, 7 complete
    String notifyCustomer() {
        String msg = 'Your ' + bundleName + ' is live: ' + newSpeed + ' Mbps' + (oldSpeed == null ? '' : ' (was ' + oldSpeed + ' Mbps)') + '.';
        calls.add(new AgenticTelco_Network_Call__c(Order__c = ord.Id, Step__c = stepName, Api__c = 'Notify', Operation__c = 'Customer notification (recorded on the order)',
            Request__c = JSON.serialize(new Map<String, Object>{ 'to' => ord.Account.Name, 'message' => msg }), State__c = 'sent',
            Idempotency_Key__c = key, Adapter_Mode__c = net.mode(), Status_Code__c = 200));
        return msg;
    }

    String complete() {
        if (ord.Status != 'Activated') update new Order(Id = ord.Id, Status = 'Activated');
        return 'Order ' + ord.OrderNumber + ' Activated';
    }

    // --------------------------------------------------------------------------------------------- helpers
    Map<String, Object> call(String api, String op, String request, String response, String stateField) {
        Map<String, Object> r = (Map<String, Object>) JSON.deserializeUntyped(response);
        calls.add(new AgenticTelco_Network_Call__c(Order__c = ord.Id, Step__c = stepName, Api__c = api, Operation__c = op.left(255),
            Request__c = request, Response__c = response, State__c = AgenticTelco_Tmf.str(r.get(stateField)), Idempotency_Key__c = key,
            Network_Id__c = AgenticTelco_Tmf.str(r.get('id')), Adapter_Mode__c = net.mode(), Status_Code__c = op.startsWith('POST') ? 201 : 200));
        return r;
    }

    List<Object> customer() {
        return new List<Object>{ new Map<String, Object>{ 'id' => ord.AccountId, 'name' => ord.Account.Name, 'role' => 'Customer', '@referredType' => 'Organization' } };
    }

    List<FulfillmentOrderLineItem> folis() {
        return [SELECT Id, Action, Description, Product2Id, Product2.Name, Product2.ProductCode, OrderItemId FROM FulfillmentOrderLineItem
                WHERE FulfillmentOrder.OrderId = :ord.Id AND Product2.ProductCode LIKE 'AgenticTelco_CFS%' ORDER BY Product2.ProductCode];
    }

    public static AgenticTelco_Network_Call__c lastServiceOrder(Id orderId) {
        for (AgenticTelco_Network_Call__c c : [SELECT Network_Id__c, State__c, Response__c FROM AgenticTelco_Network_Call__c
                                               WHERE Order__c = :orderId AND Api__c = 'TMF641' ORDER BY CreatedDate DESC, Name DESC LIMIT 1]) return c;
        return null;
    }

    public static Map<Id, Integer> speeds(Set<Id> productIds) {
        Map<Id, Integer> out = new Map<Id, Integer>();
        for (ProductAttributeDefinition d : [SELECT Product2Id, DefaultValue FROM ProductAttributeDefinition
                                             WHERE Product2Id IN :productIds AND AttributeDefinition.Code = :SPEED_CODE]) {
            if (d.DefaultValue != null && d.DefaultValue.isNumeric()) out.put(d.Product2Id, Integer.valueOf(d.DefaultValue));
        }
        for (Product2 p : [SELECT Id, Name FROM Product2 WHERE Id IN :productIds]) {
            if (!out.containsKey(p.Id)) {
                String digits = p.Name.replaceAll('[^0-9]', '');
                if (digits.length() > 0) out.put(p.Id, Integer.valueOf(digits.left(5)));
            }
        }
        return out;
    }
}
