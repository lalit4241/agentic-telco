/**
 * AgenticTelco – shared helpers for the custom TMF Open API resources on Salesforce.
 * Custom TMF API on Salesforce (not OOTB). Records written by these APIs always carry the AgenticTelco prefix;
 * existing org records are only read. There is deliberately no DELETE anywhere.
 */
public with sharing class AgenticTelco_Tmf {
    public static final String PREFIX = 'AgenticTelco';
    public static final String PRICEBOOK = 'AgenticTelco Price Book';
    public static final String CATALOG_PREFIX = 'AgenticTelco%';
    public static final String SOR_LABEL = 'custom TMF API on Salesforce';

    public static void respond(Integer status, Object body) {
        RestResponse res = RestContext.response;
        if (res == null) {
            res = new RestResponse();
            RestContext.response = res;
        }
        res.statusCode = status;
        res.addHeader('Content-Type', 'application/json');
        res.addHeader('X-AgenticTelco-Runtime', SOR_LABEL);
        res.responseBody = Blob.valueOf(JSON.serialize(body, true));
    }

    public static void error(Integer status, String code, String reason) {
        respond(status, new Map<String, Object>{
            '@type' => 'Error', 'code' => code, 'reason' => reason, 'status' => String.valueOf(status)
        });
    }

    /** Path segments after /agentictelco/tmfNNN/ , e.g. ['productOffering', '01t...']. */
    public static List<String> segments() {
        RestRequest req = RestContext.request;
        String uri = req == null || req.requestURI == null ? '' : req.requestURI;
        Integer i = uri.indexOfIgnoreCase('/agentictelco/');
        String tail = i < 0 ? uri : uri.substring(i + '/agentictelco/'.length());
        List<String> out = new List<String>();
        for (String s : tail.split('/')) {
            if (String.isNotBlank(s)) out.add(s);
        }
        if (!out.isEmpty()) out.remove(0); // tmfNNN
        return out;
    }

    public static String param(String k) {
        RestRequest req = RestContext.request;
        return req == null || req.params == null ? null : req.params.get(k);
    }

    public static Integer intParam(String k, Integer dflt) {
        String v = param(k);
        return String.isBlank(v) || !v.isNumeric() ? dflt : Integer.valueOf(v);
    }

    public static Map<String, Object> body() {
        RestRequest req = RestContext.request;
        if (req == null || req.requestBody == null || req.requestBody.size() == 0) return new Map<String, Object>();
        Object o = JSON.deserializeUntyped(req.requestBody.toString());
        return o instanceof Map<String, Object> ? (Map<String, Object>) o : new Map<String, Object>();
    }

    public static String href(String tmf, String resource, String id) {
        return '/services/apexrest/agentictelco/' + tmf + '/' + resource + (id == null ? '' : '/' + id);
    }

    public static Id pricebookId() {
        List<Pricebook2> l = [SELECT Id FROM Pricebook2 WHERE Name = :PRICEBOOK AND IsActive = true LIMIT 1];
        return l.isEmpty() ? null : l[0].Id;
    }

    public static String currencyCode() {
        return UserInfo.getDefaultCurrency();
    }

    public static Boolean isOurs(String name) {
        return name != null && name.startsWith(PREFIX);
    }

    public static Map<String, Object> ref(String id, String name, String referredType, String href) {
        return new Map<String, Object>{ 'id' => id, 'name' => name, 'href' => href, '@referredType' => referredType };
    }

    public static String str(Object o) {
        return o == null ? null : String.valueOf(o);
    }

    public static List<Object> toList(Object o) {
        return o instanceof List<Object> ? (List<Object>) o : new List<Object>();
    }

    public static Map<String, Object> toMap(Object o) {
        return o instanceof Map<String, Object> ? (Map<String, Object>) o : new Map<String, Object>();
    }

    /** Characteristic list [{name,value}] -> map. */
    public static Map<String, String> chars(Object o) {
        Map<String, String> m = new Map<String, String>();
        for (Object c : toList(o)) {
            Map<String, Object> cm = toMap(c);
            if (cm.get('name') != null) m.put(str(cm.get('name')), str(cm.get('value')));
        }
        return m;
    }

    /** Pick the price-book entry for an offering: explicit price id > term model when a contract term is chosen > evergreen > first. */
    public static PricebookEntry choosePrice(List<PricebookEntry> entries, String priceId, String term) {
        if (entries == null || entries.isEmpty()) return null;
        PricebookEntry evergreen;
        PricebookEntry termed;
        for (PricebookEntry e : entries) {
            if (priceId != null && (e.Id == priceId || String.valueOf(e.Id).left(15) == priceId.left(15))) return e;
            String t = e.ProductSellingModel == null ? null : e.ProductSellingModel.SellingModelType;
            if (t == 'TermDefined' && termed == null) termed = e;
            if (t == 'Evergreen' && evergreen == null) evergreen = e;
        }
        Boolean wantsTerm = term != null && term != '0';
        if (wantsTerm && termed != null) return termed;
        if (!wantsTerm && evergreen != null) return evergreen;
        return termed != null ? termed : (evergreen != null ? evergreen : entries[0]);
    }

    public static Map<Id, List<PricebookEntry>> pricesFor(Set<Id> productIds, Id pb) {
        Map<Id, List<PricebookEntry>> m = new Map<Id, List<PricebookEntry>>();
        for (PricebookEntry e : [
            SELECT Id, Product2Id, Product2.Name, UnitPrice, ProductSellingModelId, ProductSellingModel.Name,
                   ProductSellingModel.SellingModelType, ProductSellingModel.PricingTermUnit
            FROM PricebookEntry
            WHERE Pricebook2Id = :pb AND Product2Id IN :productIds AND IsActive = true
            ORDER BY UnitPrice DESC
        ]) {
            if (!m.containsKey(e.Product2Id)) m.put(e.Product2Id, new List<PricebookEntry>());
            m.get(e.Product2Id).add(e);
        }
        return m;
    }

    public static Map<String, Object> price(PricebookEntry e) {
        String model = e.ProductSellingModel == null ? null : e.ProductSellingModel.SellingModelType;
        Boolean oneTime = model == 'OneTime';
        Map<String, Object> m = new Map<String, Object>{
            'id' => e.Id,
            'href' => href('tmf620', 'productOfferingPrice', e.Id),
            'name' => e.Product2.Name + (e.ProductSellingModel == null ? '' : ' – ' + e.ProductSellingModel.Name),
            'priceType' => oneTime ? 'oneTime' : 'recurring',
            'price' => new Map<String, Object>{ 'unit' => currencyCode(), 'value' => e.UnitPrice },
            'lifecycleStatus' => 'Active',
            'isBundle' => false,
            'x-sellingModel' => e.ProductSellingModel == null ? null : e.ProductSellingModel.Name,
            '@type' => 'ProductOfferingPrice'
        };
        if (!oneTime) {
            m.put('recurringChargePeriodType', 'month');
            m.put('recurringChargePeriodLength', 1);
        }
        if (model == 'TermDefined') {
            m.put('productOfferingTerm', new List<Object>{
                new Map<String, Object>{ 'name' => 'Minimum term (12 or 24 months, chosen via AgenticTelco Contract Term)',
                    'duration' => new Map<String, Object>{ 'amount' => 12, 'units' => 'month' } }
            });
        }
        return m;
    }

    public static Account account(Object relatedParty) {
        for (Object o : toList(relatedParty)) {
            Map<String, Object> p = toMap(o);
            String id = str(p.get('id'));
            if (id == null) continue;
            try {
                List<Account> a = [SELECT Id, Name FROM Account WHERE Id = :id LIMIT 1];
                if (!a.isEmpty()) return a[0];
            } catch (Exception e) {
                // not an Account id – try the next party
            }
        }
        return null;
    }

    public static List<Object> party(Account a) {
        return a == null ? new List<Object>() : new List<Object>{
            new Map<String, Object>{ 'id' => a.Id, 'name' => a.Name, 'role' => 'Customer', '@referredType' => 'Customer' }
        };
    }
}
