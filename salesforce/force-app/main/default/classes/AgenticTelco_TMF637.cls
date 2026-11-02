/**
 * TMF637 Product Inventory (v5 resource shapes) – TMF facade within Salesforce (Apex).
 * Salesforce's own TMF637 resource (connect/comms/productinventorymanagement/v5/productinventory) answers GET by id only
 * (POST returns 405), so listing by party, creating and updating installed products go through this facade over the
 * standard Asset / AssetRelationship objects. Mapping only, no business rules. AgenticTelco records only; no DELETE.
 *   GET   /agentictelco/tmf637/product[/{id}]   ?relatedParty.id=&status=&productSerialNumber=&creationDate.gt=&limit=
 *   POST  /agentictelco/tmf637/product          (idempotent on productSerialNumber)
 *   PATCH /agentictelco/tmf637/product/{id}     {status, terminationDate, productRelationship:[{relationshipType, product:{id}}]}
 */
@RestResource(urlMapping='/agentictelco/tmf637/*')
global with sharing class AgenticTelco_TMF637 {
    static final String FIELDS = 'SELECT Id, Name, Status, Description, SerialNumber, Price, InstallDate, UsageEndDate, CreatedDate, AccountId, '
        + 'Account.Name, ContactId, Contact.Name, Product2Id, Product2.Name, LocationId, Location.Name, Location.ExternalReference, '
        + 'Location.VisitorAddress.Street, Location.VisitorAddress.City, Location.VisitorAddress.PostalCode FROM Asset';
    static final Map<String, String> TO_TMF = new Map<String, String>{
        'Installed' => 'active', 'Obsolete' => 'terminated', 'Purchased' => 'created', 'Shipped' => 'pendingActive', 'Registered' => 'active' };
    static final Map<String, String> TO_SF = new Map<String, String>{
        'active' => 'Installed', 'terminated' => 'Obsolete', 'created' => 'Purchased', 'pendingActive' => 'Shipped' };

    @HttpGet
    global static void doGet() {
        List<String> seg = AgenticTelco_Tmf.segments();
        String id = seg.size() > 1 ? seg[1] : null;
        if (id != null) {
            List<Asset> a = byId(id);
            if (a.isEmpty()) { AgenticTelco_Tmf.error(404, 'NOT_FOUND', 'product ' + id); return; }
            AgenticTelco_Tmf.respond(200, serialize(a)[0]);
            return;
        }
        Integer lim = Math.min(AgenticTelco_Tmf.intParam('limit', 20), 100);
        String party = AgenticTelco_Tmf.param('relatedParty.id');
        String serial = AgenticTelco_Tmf.param('productSerialNumber');
        String st = TO_SF.get(AgenticTelco_Tmf.param('status'));
        String after = AgenticTelco_Tmf.param('creationDate.gt');
        Datetime afterDt = String.isBlank(after) ? null : (Datetime) JSON.deserialize('"' + after + '"', Datetime.class);
        String q = FIELDS + ' WHERE Name LIKE \'AgenticTelco%\'';
        if (party != null) q += ' AND AccountId = :party';
        if (serial != null) q += ' AND SerialNumber = :serial';
        if (st != null) q += ' AND Status = :st';
        if (afterDt != null) q += ' AND CreatedDate > :afterDt';
        q += ' ORDER BY CreatedDate DESC LIMIT :lim';
        AgenticTelco_Tmf.respond(200, serialize(Database.query(q)));
    }

    @HttpPost
    global static void doPost() {
        Map<String, Object> b = AgenticTelco_Tmf.body();
        String name = AgenticTelco_Tmf.str(b.get('name'));
        String serial = AgenticTelco_Tmf.str(b.get('productSerialNumber'));
        if (!AgenticTelco_Tmf.isOurs(name)) { AgenticTelco_Tmf.error(400, 'NOT_AGENTICTELCO', 'name must start with AgenticTelco'); return; }
        if (String.isBlank(serial)) { AgenticTelco_Tmf.error(400, 'MISSING_SERIAL', 'productSerialNumber is required (idempotency key)'); return; }
        List<Asset> existing = Database.query(FIELDS + ' WHERE SerialNumber = :serial AND Name LIKE \'AgenticTelco%\' LIMIT 1');
        if (!existing.isEmpty()) { AgenticTelco_Tmf.respond(200, serialize(existing)[0]); return; }
        Account acc = AgenticTelco_Tmf.account(b.get('relatedParty'));
        if (acc == null) { AgenticTelco_Tmf.error(400, 'MISSING_CUSTOMER', 'relatedParty must reference a Salesforce Account id'); return; }
        try {
            Asset a = new Asset(Name = name.left(255), AccountId = acc.Id, SerialNumber = serial, Quantity = 1,
                Status = TO_SF.containsKey(AgenticTelco_Tmf.str(b.get('status'))) ? TO_SF.get(AgenticTelco_Tmf.str(b.get('status'))) : 'Installed',
                Description = AgenticTelco_Tmf.str(b.get('description')),
                Product2Id = AgenticTelco_Tmf.str(AgenticTelco_Tmf.toMap(b.get('productOffering')).get('id')),
                ContactId = partyId(b.get('relatedParty'), 'User'),
                LocationId = placeId(b.get('place')),
                Price = amount(b.get('productPrice')),
                InstallDate = day(b.get('startDate')), UsageEndDate = day(b.get('terminationDate')));
            insert a;
            AgenticTelco_Tmf.respond(201, serialize(byId(a.Id))[0]);
        } catch (Exception ex) {
            AgenticTelco_Tmf.error(422, 'PRODUCT_REJECTED', ex.getTypeName() + ': ' + ex.getMessage());
        }
    }

    @HttpPatch
    global static void doPatch() {
        List<String> seg = AgenticTelco_Tmf.segments();
        if (seg.size() < 2) { AgenticTelco_Tmf.error(400, 'MISSING_ID', 'PATCH needs /product/{id}'); return; }
        List<Asset> l = byId(seg[1]);
        if (l.isEmpty()) { AgenticTelco_Tmf.error(404, 'NOT_FOUND', 'product ' + seg[1]); return; }
        if (!AgenticTelco_Tmf.isOurs(l[0].Name)) { AgenticTelco_Tmf.error(403, 'NOT_AGENTICTELCO', 'Only AgenticTelco demo products can be changed'); return; }
        Map<String, Object> b = AgenticTelco_Tmf.body();
        Savepoint sp = Database.setSavepoint();
        try {
            Asset u = new Asset(Id = l[0].Id);
            Boolean dirty = false;
            String st = AgenticTelco_Tmf.str(b.get('status'));
            if (st != null) {
                if (!TO_SF.containsKey(st)) { AgenticTelco_Tmf.error(400, 'BAD_STATUS', 'status must be active, terminated, created or pendingActive'); return; }
                u.Status = TO_SF.get(st); dirty = true;
            }
            if (b.containsKey('terminationDate')) { u.UsageEndDate = day(b.get('terminationDate')); dirty = true; }
            if (dirty) update u;
            for (Object o : AgenticTelco_Tmf.toList(b.get('productRelationship'))) {
                Map<String, Object> r = AgenticTelco_Tmf.toMap(o);
                String other = AgenticTelco_Tmf.str(AgenticTelco_Tmf.toMap(r.get('product')).get('id'));
                String type = AgenticTelco_Tmf.str(r.get('relationshipType'));
                if (byId(other).isEmpty()) throw new TmfException('productRelationship needs an AgenticTelco product id');
                if ([SELECT Id FROM AssetRelationship WHERE AssetId = :u.Id AND RelatedAssetId = :other LIMIT 1].isEmpty()) {
                    insert new AssetRelationship(AssetId = u.Id, RelatedAssetId = other, RelationshipType = type, FromDate = System.now());
                }
            }
            AgenticTelco_Tmf.respond(200, serialize(byId(u.Id))[0]);
        } catch (Exception ex) {
            Database.rollback(sp);
            AgenticTelco_Tmf.error(422, 'PRODUCT_UPDATE_REJECTED', ex.getTypeName() + ': ' + ex.getMessage());
        }
    }

    static List<Asset> byId(String id) {
        try {
            return Database.query(FIELDS + ' WHERE Id = :id AND Name LIKE \'AgenticTelco%\' LIMIT 1');
        } catch (Exception e) {
            return new List<Asset>();
        }
    }

    static String partyId(Object parties, String role) {
        for (Object o : AgenticTelco_Tmf.toList(parties)) {
            Map<String, Object> p = AgenticTelco_Tmf.toMap(o);
            if (AgenticTelco_Tmf.str(p.get('role')) == role) return AgenticTelco_Tmf.str(p.get('id'));
        }
        return null;
    }

    static String placeId(Object places) {
        List<Object> l = AgenticTelco_Tmf.toList(places);
        return l.isEmpty() ? null : AgenticTelco_Tmf.str(AgenticTelco_Tmf.toMap(l[0]).get('id'));
    }

    static Decimal amount(Object prices) {
        List<Object> l = AgenticTelco_Tmf.toList(prices);
        if (l.isEmpty()) return null;
        Object v = AgenticTelco_Tmf.toMap(AgenticTelco_Tmf.toMap(AgenticTelco_Tmf.toMap(l[0]).get('price')).get('taxIncludedAmount')).get('value');
        return v == null ? null : Decimal.valueOf(String.valueOf(v));
    }

    static Date day(Object v) {
        String s = AgenticTelco_Tmf.str(v);
        return String.isBlank(s) ? null : Date.valueOf(s.left(10));
    }

    public static String status(String sf) {
        return TO_TMF.containsKey(sf) ? TO_TMF.get(sf) : (sf == null ? null : sf.toLowerCase());
    }

    public static List<Map<String, Object>> serialize(List<Asset> assets) {
        Set<Id> ids = new Map<Id, Asset>(assets).keySet();
        Map<Id, List<Object>> rels = new Map<Id, List<Object>>();
        for (AssetRelationship r : [SELECT Id, AssetId, RelatedAssetId, RelatedAsset.Name, RelationshipType, FromDate
                                    FROM AssetRelationship WHERE AssetId IN :ids OR RelatedAssetId IN :ids ORDER BY CreatedDate]) {
            Boolean fwd = ids.contains(r.AssetId);
            Id self = fwd ? r.AssetId : r.RelatedAssetId, other = fwd ? r.RelatedAssetId : r.AssetId;
            if (!rels.containsKey(self)) rels.put(self, new List<Object>());
            rels.get(self).add(new Map<String, Object>{ 'id' => r.Id, 'relationshipType' => fwd ? r.RelationshipType : r.RelationshipType + ' (from)',
                'validFor' => new Map<String, Object>{ 'startDateTime' => r.FromDate },
                'product' => AgenticTelco_Tmf.ref(other, fwd ? r.RelatedAsset.Name : null, 'Product', AgenticTelco_Tmf.href('tmf637', 'product', other)),
                '@type' => 'ProductRelationship' });
        }
        List<Map<String, Object>> out = new List<Map<String, Object>>();
        for (Asset a : assets) {
            List<Object> parties = new List<Object>{ new Map<String, Object>{ 'id' => a.AccountId, 'name' => a.Account.Name, 'role' => 'Customer', '@referredType' => 'Organization' } };
            if (a.ContactId != null) parties.add(new Map<String, Object>{ 'id' => a.ContactId, 'name' => a.Contact.Name, 'role' => 'User', '@referredType' => 'Individual' });
            List<Object> place = new List<Object>();
            if (a.LocationId != null) place.add(new Map<String, Object>{ 'id' => a.LocationId, 'name' => a.Location.Name, 'role' => 'installationSite',
                '@type' => 'GeographicSite', 'externalIdentifier' => new List<Object>{ new Map<String, Object>{ 'id' => a.Location.ExternalReference, 'externalIdentifierType' => 'addressKey' } },
                'geographicAddress' => new Map<String, Object>{ 'streetName' => a.Location.VisitorAddress == null ? null : a.Location.VisitorAddress.Street,
                    'city' => a.Location.VisitorAddress == null ? null : a.Location.VisitorAddress.City,
                    'postcode' => a.Location.VisitorAddress == null ? null : a.Location.VisitorAddress.PostalCode } });
            out.add(new Map<String, Object>{
                'id' => a.Id, 'href' => AgenticTelco_Tmf.href('tmf637', 'product', a.Id), 'name' => a.Name, 'description' => a.Description,
                'status' => status(a.Status), 'x-sfStatus' => a.Status, 'productSerialNumber' => a.SerialNumber,
                'startDate' => a.InstallDate, 'terminationDate' => a.UsageEndDate, 'creationDate' => a.CreatedDate,
                'productOffering' => a.Product2Id == null ? null : AgenticTelco_Tmf.ref(a.Product2Id, a.Product2.Name, 'ProductOffering',
                    AgenticTelco_Tmf.href('tmf620', 'productOffering', a.Product2Id)),
                'productPrice' => new List<Object>{ new Map<String, Object>{ 'priceType' => 'recurring', 'recurringChargePeriod' => 'month',
                    'price' => new Map<String, Object>{ 'taxIncludedAmount' => new Map<String, Object>{ 'unit' => AgenticTelco_Tmf.currencyCode(), 'value' => a.Price } },
                    '@type' => 'ProductPrice' } },
                'relatedParty' => parties, 'place' => place,
                'productRelationship' => rels.containsKey(a.Id) ? rels.get(a.Id) : new List<Object>(),
                'x-runtime' => AgenticTelco_Tmf.SOR_LABEL, '@type' => 'Product' });
        }
        return out;
    }

    public class TmfException extends Exception {}
}
