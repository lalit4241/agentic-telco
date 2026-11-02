/**
 * Mock implementation of AgenticTelco_NetworkOrderAdapter. It stands in for the network side (service and resource
 * orchestration, reservation, resource and service inventories), which in the target architecture sits OUTSIDE
 * Salesforce: here it is simulated inside Salesforce for this demo. Salesforce's only network interaction is TMF641
 * (POST plus status reads). The network's own work behind TMF641 comes back as DATA in the TMF641 response:
 *   - its own breakdown of each customer facing service (CFS) into resource facing services (RFS, supportingService)
 *     and resources (supportingResource), each with an x-action extension field (the network's own breakdown);
 *   - x-networkFulfilment: the reservation it made (TMF685 on the network side), and the resource inventory (TMF639)
 *     and service inventory (TMF638) updates it made when the order completed. Salesforce does not call those APIs.
 * A service order moves acknowledged -> inProgress -> completed,
 * one state per getServiceOrder call. Its state is read back from the AgenticTelco_Network_Call__c log (plus an
 * in-transaction cache), so it survives across orchestration steps.
 */
public with sharing class AgenticTelco_MockNetworkAdapter implements AgenticTelco_NetworkOrderAdapter {
    public static final String NOTE = 'Mocked network adapter: simulated inside Salesforce for this demo';
    static Map<String, String> latest = new Map<String, String>();   // serviceOrder id -> last JSON returned
    static final List<String> FLOW = new List<String>{ 'acknowledged', 'inProgress', 'completed' };

    public String mode() { return AgenticTelco_NetworkAdapters.MOCK; }

    public String submitServiceOrder(String body) {
        Map<String, Object> so = (Map<String, Object>) JSON.deserializeUntyped(body);
        String key = AgenticTelco_Tmf.str(so.get('externalId'));
        String id = 'SO-' + suffix(key);
        String prior = stored(id);
        if (prior != null) return prior;   // idempotent on externalId
        so.put('id', id);
        so.put('href', '/tmf-api/serviceOrdering/v4/serviceOrder/' + id);
        so.put('state', 'acknowledged');
        so.put('orderDate', now());
        so.put('x-stateChange', new List<Object>{ new Map<String, Object>{ 'state' => 'acknowledged', 'changeDate' => now() } });
        so.put('x-simulated', NOTE);
        so.put('@type', 'ServiceOrder');
        for (Object o : AgenticTelco_Tmf.toList(so.get('serviceOrderItem'))) {
            Map<String, Object> it = AgenticTelco_Tmf.toMap(o);
            it.put('state', 'acknowledged');
            Map<String, Object> svc = AgenticTelco_Tmf.toMap(it.get('service'));
            if (svc.get('id') == null) svc.put('id', 'CFS-' + suffix(key) + '-' + it.get('id'));
            decompose(svc, AgenticTelco_Tmf.str(it.get('action')), key);
        }
        so.put('x-networkFulfilment', networkFulfilment(so, key, false));
        String out = JSON.serialize(so);
        latest.put(id, out);
        return out;
    }

    public String getServiceOrder(String id) {
        String prior = stored(id);
        if (prior == null) throw new AgenticTelco_NetworkAdapters.AdapterException('TMF641 serviceOrder ' + id + ' not found (404)');
        Map<String, Object> so = (Map<String, Object>) JSON.deserializeUntyped(prior);
        Integer i = FLOW.indexOf(AgenticTelco_Tmf.str(so.get('state')));
        if (i >= 0 && i < FLOW.size() - 1) {
            String next = FLOW[i + 1];
            so.put('state', next);
            List<Object> hist = AgenticTelco_Tmf.toList(so.get('x-stateChange'));
            hist.add(new Map<String, Object>{ 'state' => next, 'changeDate' => now() });
            so.put('x-stateChange', hist);
            for (Object o : AgenticTelco_Tmf.toList(so.get('serviceOrderItem'))) {
                Map<String, Object> it = AgenticTelco_Tmf.toMap(o);
                it.put('state', next);
                if (next == 'completed') {
                    Map<String, Object> svc = AgenticTelco_Tmf.toMap(it.get('service'));
                    svc.put('state', it.get('action') == 'delete' ? 'terminated' : 'active');
                    for (Object r : AgenticTelco_Tmf.toList(svc.get('supportingResource'))) {
                        Map<String, Object> rm = AgenticTelco_Tmf.toMap(r);
                        rm.put('resourceStatus', rm.get('x-action') == 'delete' ? 'removed' : rm.get('x-action') == 'add' ? 'installed' : 'inUse');
                    }
                }
            }
            if (next == 'inProgress') so.put('startDate', now());
            if (next == 'completed') {
                so.put('completionDate', now());
                so.put('x-networkFulfilment', networkFulfilment(so, AgenticTelco_Tmf.str(so.get('externalId')), true));
            }
        }
        String out = JSON.serialize(so);
        latest.put(id, out);
        return out;
    }

    /** The network's own decomposition: CFS -> RFS (supportingService) and resources (supportingResource), each with an action code. */
    static void decompose(Map<String, Object> svc, String action, String key) {
        String spec = AgenticTelco_Tmf.str(AgenticTelco_Tmf.toMap(svc.get('serviceSpecification')).get('id'));
        String s = suffix(key);
        List<Object> rfs = new List<Object>();
        List<Object> res = new List<Object>();
        if (spec == 'AgenticTelco_CFS_Fibre_Broadband') {
            rfs.add(mkRfs('RFS-BW-' + s, 'RFS Bandwidth profile', action == 'noChange' ? 'noChange' : action, 'profile', speedOf(svc) == null ? 'FTTP' : 'FTTP-' + speedOf(svc)));
            res.add(mkRes('RES-PORT-' + s, 'Fibre port (OLT/GPON)', 'noChange', 'PhysicalResource'));
        } else if (spec == 'AgenticTelco_CFS_Fibre_Access') {
            rfs.add(mkRfs('RFS-ACC-' + s, 'RFS Access line', action, 'technology', 'FTTP'));
            res.add(mkRes('RES-ONT-' + s, 'ONT (optical network terminal)', action, 'PhysicalResource'));
            res.add(mkRes('RES-PORT-' + s, 'Fibre port (OLT/GPON)', action, 'PhysicalResource'));
        } else if (spec == 'AgenticTelco_CFS_Managed_Router') {
            rfs.add(mkRfs('RFS-RCFG-' + s, 'RFS Router configuration', action, 'wifiProfile', 'Wi-Fi 6'));
            if (action == 'modify') {
                res.add(mkRes('RES-RTR-OLD-' + s, 'Router (Wi-Fi 5, up to 300 Mbps): removed', 'delete', 'PhysicalResource'));
                res.add(mkRes('RES-RTR-WIFI6-' + s, 'Router (Wi-Fi 6, 900-capable): installed', 'add', 'PhysicalResource'));
            } else {
                res.add(mkRes('RES-RTR-WIFI6-' + s, 'Router (Wi-Fi 6, 900-capable)', action, 'PhysicalResource'));
            }
        }
        if (!rfs.isEmpty()) svc.put('supportingService', rfs);
        if (!res.isEmpty()) svc.put('supportingResource', res);
    }

    static Map<String, Object> mkRfs(String id, String name, String action, String ch, String value) {
        return new Map<String, Object>{ 'id' => id, 'name' => name, 'x-action' => action, '@type' => 'ResourceFacingService',
            'serviceCharacteristic' => new List<Object>{ new Map<String, Object>{ 'name' => ch, 'value' => value } } };
    }

    static Map<String, Object> mkRes(String id, String name, String action, String type) {
        return new Map<String, Object>{ 'id' => id, 'name' => name, 'x-action' => action, '@referredType' => type,
            'resourceStatus' => action == 'delete' ? 'inUse' : 'reserved', 'href' => '/tmf-api/resourceInventoryManagement/v4/resource/' + id };
    }

    /** The network's own work behind TMF641, reported as data: reservation (TMF685) and, once completed, the inventory updates (TMF639, TMF638). */
    static Map<String, Object> networkFulfilment(Map<String, Object> so, String key, Boolean done) {
        List<Object> reserved = new List<Object>();
        List<Object> resUpd = new List<Object>();
        List<Object> svcUpd = new List<Object>();
        Set<String> seen = new Set<String>();
        for (Object o : AgenticTelco_Tmf.toList(so.get('serviceOrderItem'))) {
            Map<String, Object> it = AgenticTelco_Tmf.toMap(o);
            Map<String, Object> svc = AgenticTelco_Tmf.toMap(it.get('service'));
            if (it.get('action') != 'noChange') svcUpd.add(new Map<String, Object>{ 'id' => svc.get('id'), 'state' => 'active', 'x-action' => it.get('action') });
            for (Object r : AgenticTelco_Tmf.toList(svc.get('supportingService')))
                if (AgenticTelco_Tmf.toMap(r).get('x-action') != 'noChange') svcUpd.add(new Map<String, Object>{ 'id' => AgenticTelco_Tmf.toMap(r).get('id'), 'state' => 'active', 'x-action' => AgenticTelco_Tmf.toMap(r).get('x-action') });
            for (Object r : AgenticTelco_Tmf.toList(svc.get('supportingResource'))) {
                Map<String, Object> rm = AgenticTelco_Tmf.toMap(r);
                String rid = AgenticTelco_Tmf.str(rm.get('id'));
                if (seen.contains(rid) || rm.get('x-action') == 'noChange') continue;
                seen.add(rid);
                if (rm.get('x-action') == 'add') reserved.add(new Map<String, Object>{ 'id' => rid, 'name' => rm.get('name') });
                resUpd.add(new Map<String, Object>{ 'id' => rid, 'x-action' => rm.get('x-action'), 'resourceStatus' => rm.get('x-action') == 'delete' ? 'removed' : 'installed' });
            }
        }
        Map<String, Object> nf = new Map<String, Object>{
            'note' => 'The network\'s own work behind TMF641 (simulated inside Salesforce for this demo); Salesforce does not call these APIs',
            'reservation' => new Map<String, Object>{ 'api' => 'TMF685 (network side)', 'id' => 'RSV-' + suffix(key), 'reservationState' => 'completed', 'resource' => reserved } };
        if (done) {
            nf.put('resourceInventory', new Map<String, Object>{ 'api' => 'TMF639 (network side)', 'updated' => resUpd });
            nf.put('serviceInventory', new Map<String, Object>{ 'api' => 'TMF638 (network side)', 'updated' => svcUpd });
        }
        return nf;
    }

    static String speedOf(Map<String, Object> svc) {
        for (Object o : AgenticTelco_Tmf.toList(svc.get('serviceCharacteristic'))) {
            Map<String, Object> c = AgenticTelco_Tmf.toMap(o);
            if (c.get('name') == 'downloadSpeedMbps') return AgenticTelco_Tmf.str(c.get('value'));
        }
        return null;
    }

    static String stored(String id) {
        if (latest.containsKey(id)) return latest.get(id);
        for (AgenticTelco_Network_Call__c c : [SELECT Response__c FROM AgenticTelco_Network_Call__c WHERE Api__c = 'TMF641' AND Network_Id__c = :id
                                               ORDER BY CreatedDate DESC, Name DESC LIMIT 1]) return c.Response__c;
        return null;
    }

    public static String suffix(String key) {
        if (String.isBlank(key)) return '0';
        String d = key.replaceAll('[^0-9]', '');
        return d.length() > 0 ? d.right(8) : key.replaceAll('[^A-Za-z0-9]', '').right(12).toUpperCase();
    }

    static String now() { return Datetime.now().formatGmt('yyyy-MM-dd\'T\'HH:mm:ss.SSS\'Z\''); }
}
