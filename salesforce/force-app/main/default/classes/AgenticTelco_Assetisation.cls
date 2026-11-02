/**
 * Installed product (TMF637) after an AgenticTelco order: ONE writer, chosen at build time by
 * AgenticTelco_Fulfilment_Setting__mdt.Default.Assetisation_Route__c (never switched at run time, no fallback):
 *   CUSTOM_STEP  the AgenticTelco plan has step 'Record the installed product (TMF637)' (kind ASSETIZE), which calls
 *                record() below. If it fails, the step fails and the plan (and so the run) stops.
 *   BUILT_IN     the platform's built-in asset step writes the assets; the AgenticTelco plan has no asset step.
 * The L5 workflow only reads the result back through TMF637.
 * Result of record() on a Fibre 150 -> Fibre 900 upgrade (delete + add, or the older single modify line):
 *   - Fibre 150 Asset ends on the upgrade date (Status Obsolete, UsageEndDate = upgrade date); its components end too
 *   - new Fibre 900 Asset: Installed, price = the order line's monthly price (recurring, from the upgrade date),
 *     UsageEndDate = the contract end carried over from Fibre 150, same site, customer and user
 *   - AssetRelationship Fibre 150 -> Fibre 900, type Upgrade
 *   - the bundle's component lines (Wi-Fi 6 Router, Fibre Access Line) as child Assets (ParentId) of the new Fibre 900
 * Idempotent on the serial number AT-<order external id>: a re-run adds nothing twice. AgenticTelco Assets only.
 */
public with sharing class AgenticTelco_Assetisation {
    public static final String CUSTOM_STEP = 'CUSTOM_STEP';
    public static final String BUILT_IN = 'BUILT_IN';
    @TestVisible static AgenticTelco_Fulfilment_Setting__mdt testConfig;

    public static String route() {
        AgenticTelco_Fulfilment_Setting__mdt c = testConfig != null ? testConfig : AgenticTelco_Fulfilment_Setting__mdt.getInstance('Default');
        return c == null || c.Assetisation_Route__c == null ? CUSTOM_STEP : c.Assetisation_Route__c;
    }

    /** Short wording for the Dev View line, e.g. 'Assetisation done (TMF637) - custom step in the Salesforce plan'. */
    public static String routeLabel() { return route() == BUILT_IN ? 'built-in asset step' : 'custom step in the Salesforce plan'; }

    public class AssetisationException extends Exception {}

    public static String record(Id orderId) {
        if (route() != CUSTOM_STEP) throw new AssetisationException('Assetisation route is ' + route() + ': the built-in asset step writes the assets, so this step must not be in the plan');
        Order o = [SELECT Id, Name, OrderNumber, AccountId FROM Order WHERE Id = :orderId];
        if (!AgenticTelco_Tmf.isOurs(o.Name)) throw new AssetisationException('Not an AgenticTelco order: ' + o.OrderNumber);
        String serial = 'AT-' + (o.Name.startsWith('AgenticTelco PO ') ? o.Name.substringAfter('AgenticTelco PO ') : o.OrderNumber);
        Id oldId;
        OrderItem bundle;
        for (OrderItem oi : [SELECT Id, Product2Id, Product2.Name, UnitPrice, ServiceDate, EndDate, Description FROM OrderItem
                             WHERE OrderId = :orderId ORDER BY CreatedDate, Id]) {
            String act = AgenticTelco_TMF622.itemAction(oi.Description);
            Map<String, Object> p = AgenticTelco_TMF622.itemProduct(oi.Description);
            if (AgenticTelco_TMF622.isComponentLine(oi.Description)) continue;
            if ((act == 'delete' || act == 'modify') && p != null && oldId == null) oldId = Id.valueOf((String) p.get('id'));
            if (act != 'delete' && bundle == null) bundle = oi;
        }
        if (bundle == null) throw new AssetisationException('No add or modify product line on order ' + o.OrderNumber);
        if (oldId == null) throw new AssetisationException('No installed product (delete or modify line) on order ' + o.OrderNumber);
        List<Asset> olds = [SELECT Id, Name, AccountId, ContactId, LocationId, InstallDate, UsageEndDate, Status FROM Asset
                            WHERE Id = :oldId AND AccountId = :o.AccountId AND Name LIKE 'AgenticTelco%'];
        if (olds.isEmpty()) throw new AssetisationException('Installed product ' + oldId + ' is not an AgenticTelco Asset of this customer');
        Asset old = olds[0];
        Date live = bundle.ServiceDate == null ? Date.today() : bundle.ServiceDate;
        Date contractEnd = bundle.EndDate != null ? bundle.EndDate : old.UsageEndDate;
        String site = old.Name.contains(' – ') ? old.Name.substringAfter(' – ') : null;
        List<String> notes = new List<String>();

        Asset nw;
        for (Asset a : [SELECT Id, Name FROM Asset WHERE SerialNumber = :serial AND Name LIKE 'AgenticTelco%' AND ParentId = null LIMIT 1]) nw = a;
        if (nw == null) {
            nw = new Asset(Name = named(bundle.Product2.Name, site), AccountId = old.AccountId, ContactId = old.ContactId, LocationId = old.LocationId,
                Product2Id = bundle.Product2Id, SerialNumber = serial, Quantity = 1, Status = 'Installed', Price = bundle.UnitPrice,
                InstallDate = live, UsageEndDate = contractEnd,
                Description = ('AgenticTelco: upgraded from ' + old.Name.substringBefore(' – ') + ' by order ' + o.OrderNumber + '. '
                    + bundle.UnitPrice + ' a month from ' + live + '; contract end ' + contractEnd + ' carried over.').left(32000));
            insert nw;
            notes.add(bundle.Product2.Name.removeStart('AgenticTelco ') + ' active');
        }

        // components of the bundle line -> child Assets of the new bundle
        Set<Id> compLines = new Set<Id>();
        for (OrderItemRelationship r : [SELECT AssociatedOrderItemId FROM OrderItemRelationship WHERE MainOrderItemId = :bundle.Id]) compLines.add(r.AssociatedOrderItemId);
        Set<Id> haveChild = new Set<Id>();
        for (Asset c : [SELECT Product2Id FROM Asset WHERE ParentId = :nw.Id]) haveChild.add(c.Product2Id);
        List<Asset> kids = new List<Asset>();
        Integer k = 0;
        for (OrderItem c : [SELECT Id, Product2Id, Product2.Name, Description FROM OrderItem WHERE Id IN :compLines ORDER BY CreatedDate, Id]) {
            k++;
            if (haveChild.contains(c.Product2Id)) continue;
            Boolean kept = AgenticTelco_TMF622.itemAction(c.Description) == 'noChange';
            kids.add(new Asset(Name = named(c.Product2.Name, site), AccountId = old.AccountId, ContactId = old.ContactId, LocationId = old.LocationId,
                Product2Id = c.Product2Id, ParentId = nw.Id, SerialNumber = serial + '-' + k, Quantity = 1, Status = 'Installed', Price = 0,
                InstallDate = kept && old.InstallDate != null ? old.InstallDate : live, UsageEndDate = contractEnd,
                Description = 'AgenticTelco: component of ' + bundle.Product2.Name.removeStart('AgenticTelco ') + ' (' + (kept ? 'kept, no change' : 'new') + '), order ' + o.OrderNumber));
        }
        insert kids;
        if (!kids.isEmpty()) notes.add(kids.size() + ' components as children');

        // the installed product (and any components it had) ends on the upgrade date
        List<Asset> ending = new List<Asset>();
        if (old.Status != 'Obsolete' || old.UsageEndDate != live) ending.add(new Asset(Id = old.Id, Status = 'Obsolete', UsageEndDate = live));
        for (Asset c : [SELECT Id FROM Asset WHERE ParentId = :old.Id AND Status != 'Obsolete' AND Name LIKE 'AgenticTelco%']) ending.add(new Asset(Id = c.Id, Status = 'Obsolete', UsageEndDate = live));
        update ending;
        notes.add(old.Name.substringBefore(' – ').removeStart('AgenticTelco ') + ' ended ' + String.valueOf(live));

        if ([SELECT COUNT() FROM AssetRelationship WHERE AssetId = :old.Id AND RelatedAssetId = :nw.Id] == 0) {
            insert new AssetRelationship(AssetId = old.Id, RelatedAssetId = nw.Id, RelationshipType = 'Upgrade', FromDate = System.now());
            notes.add('Upgrade link');
        }
        return 'Installed product recorded (TMF637): ' + String.join(notes, ', ') + '. ' + bundle.Product2.Name.removeStart('AgenticTelco ')
            + ' ' + bundle.UnitPrice + '/month from ' + String.valueOf(live) + ', contract end ' + String.valueOf(contractEnd) + '.';
    }

    static String named(String productName, String site) { return (productName + (site == null ? '' : ' – ' + site)).left(255); }
}
