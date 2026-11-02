/**
 * Salesforce order orchestration for AgenticTelco: hand-off of an approved order to the native decomposition and plan
 * (submitOrder through the AgenticTelco_Submit_Order_To_Orchestration flow), and the read model the TMF622 facade
 * returns as x-orchestration (decomposition, plan steps with dependencies and timestamps, the TMF641 service order and
 * its state history, network calls). Salesforce makes one outbound network interaction, TMF641; the network's own
 * reservation and inventory work comes back as data in the TMF641 response. Salesforce never starts an order itself: only the TMF622 PATCH inProgress from
 * the L5 workflow, after the go-ahead and the binding policy check, calls submit().
 */
public with sharing class AgenticTelco_Orchestration {
    public static final String SUBMIT_FLOW = 'AgenticTelco_Submit_Order_To_Orchestration';
    public static final String GROUP_NAME = 'AgenticTelco Fibre Upgrade Fulfilment';
    public static final List<String> KINDS = new List<String>{ 'VALIDATE_RESERVE', 'SUBMIT', 'AWAIT', 'PONR', 'SERVICES', 'NOTIFY', 'COMPLETE' };
    public static final Map<String, String> STEP_NAMES = new Map<String, String>{
        'VALIDATE_RESERVE' => 'AgenticTelco 1. Validate and set action codes (installed base, TMF637)',
        'SUBMIT' => 'AgenticTelco 2. Send network service order (TMF641)',
        'AWAIT' => 'AgenticTelco 3. Wait for network activation (TMF641)',
        'PONR' => 'AgenticTelco 4. Point of no return',
        'SERVICES' => 'AgenticTelco 5. Record the network result (TMF641 response)',
        'NOTIFY' => 'AgenticTelco 6. Notify the customer',
        'COMPLETE' => 'AgenticTelco 7. Complete (order Activated)' };
    public static final Map<String, String> STEP_FLOWS = new Map<String, String>{
        'VALIDATE_RESERVE' => 'AgenticTelco_Step_Validate_Reserve',
        'SUBMIT' => 'AgenticTelco_Step_Send_Service_Order',
        'AWAIT' => 'AgenticTelco_Step_Await_Activation',
        'SERVICES' => 'AgenticTelco_Step_Update_Services',
        'NOTIFY' => 'AgenticTelco_Step_Notify_Customer',
        'COMPLETE' => 'AgenticTelco_Step_Complete_Order' };

    public static final String CODES_NOTE = 'Action codes are derived from the installed base (TMF637), not by the built-in decomposition.';
    public static final String NETWORK_NOTE = 'RFS and resources are the network\'s own breakdown (x-action extension fields in the TMF641 response).';
    public static final String NO_PLAN = 'No fulfilment plan was created for this order, so the run stops here (no fallback route).';
    public static final String ASSET_NOTE = 'Installed product (TMF637) has one writer: the L5 workflow\'s TMF637 update. The plan has no assetization step.';

    public static String stepName(String kind) { return STEP_NAMES.containsKey(kind) ? STEP_NAMES.get(kind) : kind; }

    @TestVisible static Boolean skipFlowInTest = false;

    /** Synchronous submitOrder; returns the fulfillment plan id (null if the platform did not create one). */
    public static Id submit(Id orderId) {
        String plan;
        if (!(Test.isRunningTest() && skipFlowInTest)) {
            Flow.Interview fi = Flow.Interview.createInterview(SUBMIT_FLOW, new Map<String, Object>{ 'orderId' => (String) orderId });
            fi.start();
            plan = (String) fi.getVariableValue('fulfillmentPlanId');
        }
        if (String.isBlank(plan)) plan = [SELECT FulfillmentPlanId FROM Order WHERE Id = :orderId].FulfillmentPlanId;
        return String.isBlank(plan) ? null : Id.valueOf(plan);
    }

    // ------------------------------------------------------------------------------------------------- read model
    public static Map<String, Object> view(Id orderId) {
        Order o = [SELECT Id, OrderNumber, Status, FulfillmentPlanId, OrchestrationSbmsStatus FROM Order WHERE Id = :orderId];
        Map<String, Object> v = new Map<String, Object>{ 'engine' => 'Salesforce order orchestration',
            'adapterMode' => AgenticTelco_NetworkAdapters.mode(),
            'adapterNote' => AgenticTelco_NetworkAdapters.mode() == AgenticTelco_NetworkAdapters.MOCK
                ? 'The TMF641 request and response are simulated inside Salesforce for this demo.' : 'TMF calls go to the network through a named credential.',
            'idempotencyKey' => AgenticTelco_OrchestrationStep.idempotencyKey(o), 'actionCodesNote' => CODES_NOTE, 'networkBreakdownNote' => NETWORK_NOTE,
            'productInventory' => new Map<String, Object>{ 'writer' => 'L5 workflow (TMF637)', 'note' => ASSET_NOTE, 'platformStatus' => o.OrchestrationSbmsStatus } };
        if (o.FulfillmentPlanId == null) {
            v.put('status', 'notSubmitted'); v.put('error', NO_PLAN); v.put('steps', new List<Object>()); v.put('decomposition', new List<Object>()); return v;
        }
        FulfillmentPlan p = [SELECT Id, Name, State FROM FulfillmentPlan WHERE Id = :o.FulfillmentPlanId];
        v.put('fulfillmentPlanId', p.Id);
        v.put('planName', p.Name);
        v.put('planState', p.State);
        List<FulfillmentStep> steps = [SELECT Id, Name, StepType, State, JeopardyStatus, ExecutionMessage, ActualStartDate, ActualCompletionDate, CreatedDate
                                       FROM FulfillmentStep WHERE FulfillmentPlanId = :p.Id ORDER BY Name];
        Map<Id, List<String>> deps = new Map<Id, List<String>>();
        for (FulfillmentStepDependency d : [SELECT DependentStepId, DependsOnStep.Name FROM FulfillmentStepDependency WHERE DependentStep.FulfillmentPlanId = :p.Id]) {
            if (!deps.containsKey(d.DependentStepId)) deps.put(d.DependentStepId, new List<String>());
            deps.get(d.DependentStepId).add(d.DependsOnStep.Name);
        }
        List<Object> sl = new List<Object>();
        Integer done = 0;
        Boolean failed = false;
        for (FulfillmentStep s : steps) {
            if (s.State == 'Completed') done++;
            if (s.State == 'Failed' || s.State == 'Fatally Failed' || s.State == 'FatallyFailed') failed = true;
            sl.add(new Map<String, Object>{ 'id' => s.Id, 'name' => s.Name, 'type' => s.StepType, 'state' => s.State, 'jeopardy' => s.JeopardyStatus,
                'message' => s.ExecutionMessage, 'startedAt' => iso(s.ActualStartDate), 'completedAt' => iso(s.ActualCompletionDate),
                'dependsOn' => deps.containsKey(s.Id) ? deps.get(s.Id) : new List<String>() });
        }
        v.put('steps', sl);
        v.put('status', failed ? 'failed' : (!steps.isEmpty() && done == steps.size()) ? 'completed' : done > 0 ? 'inProgress' : 'planned');

        // network calls (oldest first) and the latest TMF641 service order
        Map<String, Object> holder = new Map<String, Object>();
        List<Object> nc = networkCalls(orderId, holder);
        Map<String, Object> so = (Map<String, Object>) holder.get('serviceOrder');
        v.put('networkCalls', nc);
        if (so != null) v.put('serviceOrder', new Map<String, Object>{ 'id' => so.get('id'), 'state' => so.get('state'), 'externalId' => so.get('externalId'),
            'stateChange' => so.get('x-stateChange'), 'items' => soItems(so), 'networkFulfilment' => so.get('x-networkFulfilment') });

        // decomposition: product order items (bundle and its components, TMF622 codes) -> CFS (built-in decomposition creates the
        // lines; the codes come from the installed base) -> RFS / resources (the network's own breakdown, from the TMF641 response)
        List<Object> dec = new List<Object>();
        for (OrderItem oi : [SELECT Product2.Name, Description, OrderAction.Type, OrderAction.Subtype FROM OrderItem WHERE OrderId = :orderId ORDER BY CreatedDate, Id]) {
            Boolean comp = AgenticTelco_TMF622.isComponentLine(oi.Description);
            String nat = oi.OrderAction.Type == null ? '' : ' (OrderAction ' + oi.OrderAction.Type + (oi.OrderAction.Subtype == null ? '' : '/' + oi.OrderAction.Subtype) + ')';
            dec.add(row(comp ? 'Product component' : 'Product', oi.Product2.Name.removeStart('AgenticTelco '), AgenticTelco_TMF622.itemAction(oi.Description),
                (comp ? 'Bundle component (commercial product), TMF622 code' : 'TMF622 product order item') + nat, 'Salesforce (TMF622)'));
        }
        Map<String, Map<String, Object>> soByCfs = new Map<String, Map<String, Object>>();
        if (so != null) for (Object x : AgenticTelco_Tmf.toList(so.get('serviceOrderItem'))) {
            Map<String, Object> it = AgenticTelco_Tmf.toMap(x);
            soByCfs.put(AgenticTelco_Tmf.str(AgenticTelco_Tmf.toMap(AgenticTelco_Tmf.toMap(it.get('service')).get('serviceSpecification')).get('id')), it);
        }
        for (FulfillmentOrderLineItem l : [SELECT Action, Description, Product2.Name, Product2.ProductCode FROM FulfillmentOrderLineItem
                                           WHERE FulfillmentOrder.OrderId = :orderId AND Product2.ProductCode LIKE 'AgenticTelco_CFS%' ORDER BY Product2.ProductCode]) {
            String tmf = AgenticTelco_OrchestrationStep.TO_TMF.get(l.Action);
            String why = 'Not yet set (step 1 sets it from the installed base)';
            if (l.Description != null && l.Description.startsWith('tmf=')) {
                tmf = l.Description.substringBetween('tmf=', ';');
                why = l.Description.substringAfter('why=');
            }
            String cfs = AgenticTelco_OrchestrationStep.cfsLabel(l.Product2.ProductCode);
            dec.add(row('CFS', cfs, tmf, why + ' (installed base, TMF637)', 'Salesforce (built-in decomposition line; code from the installed base)'));
            Map<String, Object> it = soByCfs.get(l.Product2.ProductCode);
            if (it == null) continue;
            Map<String, Object> svc = AgenticTelco_Tmf.toMap(it.get('service'));
            for (Object r : AgenticTelco_Tmf.toList(svc.get('supportingService'))) {
                Map<String, Object> m = AgenticTelco_Tmf.toMap(r);
                dec.add(row('RFS', AgenticTelco_Tmf.str(m.get('name')), AgenticTelco_Tmf.str(m.get('x-action')), 'Network\'s own breakdown of ' + cfs, 'Network (mocked), x-action extension'));
            }
            for (Object r : AgenticTelco_Tmf.toList(svc.get('supportingResource'))) {
                Map<String, Object> m = AgenticTelco_Tmf.toMap(r);
                dec.add(row('Resource', AgenticTelco_Tmf.str(m.get('name')), AgenticTelco_Tmf.str(m.get('x-action')), 'Network\'s own breakdown of ' + cfs, 'Network (mocked), x-action extension'));
            }
        }
        v.put('decomposition', dec);
        return v;
    }

    static List<Object> soItems(Map<String, Object> so) {
        List<Object> out = new List<Object>();
        for (Object x : AgenticTelco_Tmf.toList(so.get('serviceOrderItem'))) {
            Map<String, Object> it = AgenticTelco_Tmf.toMap(x);
            Map<String, Object> svc = AgenticTelco_Tmf.toMap(it.get('service'));
            out.add(new Map<String, Object>{ 'id' => it.get('id'), 'action' => it.get('action'), 'state' => it.get('state'),
                'service' => svc.get('name'), 'serviceId' => svc.get('id') });
        }
        return out;
    }

    /** Network calls the plan made through the network order adapter, oldest first; the latest TMF641 response goes into holder.serviceOrder. */
    @TestVisible static List<Object> networkCalls(Id orderId, Map<String, Object> holder) {
        List<Object> nc = new List<Object>();
        for (AgenticTelco_Network_Call__c c : [SELECT Name, Step__c, Api__c, Operation__c, State__c, Network_Id__c, Adapter_Mode__c, Status_Code__c, Request__c, Response__c, CreatedDate
                                               FROM AgenticTelco_Network_Call__c WHERE Order__c = :orderId ORDER BY CreatedDate, Name]) {
            nc.add(new Map<String, Object>{ 'name' => c.Name, 'step' => c.Step__c, 'api' => c.Api__c, 'operation' => c.Operation__c, 'state' => c.State__c,
                'networkId' => c.Network_Id__c, 'mode' => c.Adapter_Mode__c, 'statusCode' => c.Status_Code__c, 'at' => iso(c.CreatedDate) });
            // the one TMF641 POST carries its full request and response, so the Dev View can show the payload
            if (c.Api__c == 'TMF641' && c.Operation__c != null && c.Operation__c.startsWith('POST')) {
                Map<String, Object> last = (Map<String, Object>) nc[nc.size() - 1];
                last.put('request', parse(c.Request__c));
                last.put('response', parse(c.Response__c));
            }
            if (c.Api__c == 'TMF641' && c.Response__c != null) holder.put('serviceOrder', JSON.deserializeUntyped(c.Response__c));
        }
        return nc;
    }

    static Object parse(String body) {
        if (String.isBlank(body)) return null;
        try { return JSON.deserializeUntyped(body); } catch (Exception e) { return body; }
    }

    static Map<String, Object> row(String level, String item, String action, String why, String origin) {
        return new Map<String, Object>{ 'level' => level, 'item' => item, 'action' => action, 'why' => why, 'where' => origin };
    }

    static String iso(Datetime d) { return d == null ? null : d.formatGmt('yyyy-MM-dd\'T\'HH:mm:ss.SSS\'Z\''); }
}
