/**
 * TMF648 Quote Management (v4 resource shapes) – TMF facade within Salesforce (Apex).
 * The sfcomms org exposes no TMF648 resource (Direct Access and managed-package paths return 404).
 *   GET   /agentictelco/tmf648/quote[/{id}]
 *   POST  /agentictelco/tmf648/quote            (idempotent on externalId)
 *   PATCH /agentictelco/tmf648/quote/{id}       {"state":"approved"|"accepted"|"cancelled"} – AgenticTelco quotes only
 */
@RestResource(urlMapping='/agentictelco/tmf648/*')
global with sharing class AgenticTelco_TMF648 {
    static final Map<String, String> TO_SF = new Map<String, String>{
        'inProgress' => 'Draft', 'pending' => 'Presented', 'approved' => 'Approved', 'accepted' => 'Accepted',
        'cancelled' => 'Denied', 'rejected' => 'Rejected' };

    @HttpGet
    global static void doGet() {
        List<String> seg = AgenticTelco_Tmf.segments();
        String id = seg.size() > 1 ? seg[1] : null;
        Integer lim = Math.min(AgenticTelco_Tmf.intParam('limit', 20), 100);
        List<Quote> qs = id != null
            ? [SELECT Id, Name, Status, Description, CreatedDate, ExpirationDate, AccountId, Account.Name, TotalPrice FROM Quote WHERE Id = :id LIMIT 1]
            : [SELECT Id, Name, Status, Description, CreatedDate, ExpirationDate, AccountId, Account.Name, TotalPrice FROM Quote
               WHERE Name LIKE 'AgenticTelco%' ORDER BY CreatedDate DESC LIMIT :lim];
        if (id != null && qs.isEmpty()) { AgenticTelco_Tmf.error(404, 'NOT_FOUND', 'quote ' + id); return; }
        List<Map<String, Object>> out = serialize(qs);
        AgenticTelco_Tmf.respond(200, id == null ? (Object) out : (Object) out[0]);
    }

    @HttpPost
    global static void doPost() {
        Map<String, Object> b = AgenticTelco_Tmf.body();
        String ext = AgenticTelco_Tmf.str(b.get('externalId'));
        if (String.isBlank(ext)) { AgenticTelco_Tmf.error(400, 'MISSING_EXTERNAL_ID', 'externalId is required (idempotency key)'); return; }
        String name = (AgenticTelco_Tmf.PREFIX + ' Quote ' + ext).left(80);
        List<Quote> existing = [SELECT Id, Name, Status, Description, CreatedDate, ExpirationDate, AccountId, Account.Name, TotalPrice
                                FROM Quote WHERE Name = :name LIMIT 1];
        if (!existing.isEmpty()) { AgenticTelco_Tmf.respond(200, serialize(existing)[0]); return; }
        Account acc = AgenticTelco_Tmf.account(b.get('relatedParty'));
        Id pb = AgenticTelco_Tmf.pricebookId();
        if (pb == null) { AgenticTelco_Tmf.error(409, 'NO_PRICEBOOK', 'AgenticTelco Price Book not found – run seed/epc/seed_epc.py'); return; }
        List<Object> items = AgenticTelco_Tmf.toList(b.get('quoteItem'));
        if (items.isEmpty()) { AgenticTelco_Tmf.error(400, 'NO_ITEMS', 'quoteItem is empty'); return; }
        Set<Id> offerIds = new Set<Id>();
        for (Object o : items) {
            String oid = AgenticTelco_Tmf.str(AgenticTelco_Tmf.toMap(AgenticTelco_Tmf.toMap(o).get('productOffering')).get('id'));
            if (oid != null) offerIds.add(Id.valueOf(oid));
        }
        Map<Id, List<PricebookEntry>> prices = AgenticTelco_Tmf.pricesFor(offerIds, pb);
        Savepoint sp = Database.setSavepoint();
        try {
            Quote q = new Quote(Name = name, Pricebook2Id = pb, Status = 'Draft', ExpirationDate = Date.today().addDays(30),
                                Description = 'AgenticTelco demo quote via custom TMF648 API. ' + AgenticTelco_Tmf.str(b.get('description')));
            if (acc != null) {
                // Quote.AccountId is derived from the opportunity, so link the quote to an AgenticTelco demo opportunity
                Opportunity opp = new Opportunity(Name = name.replace('Quote', 'Opportunity').left(120), AccountId = acc.Id,
                                                  StageName = stage(), CloseDate = Date.today().addDays(30), Pricebook2Id = pb);
                insert opp;
                q.OpportunityId = opp.Id;
            }
            insert q;
            List<QuoteLineItem> lines = new List<QuoteLineItem>();
            for (Object it : items) {
                Map<String, Object> m = AgenticTelco_Tmf.toMap(it);
                String oid = AgenticTelco_Tmf.str(AgenticTelco_Tmf.toMap(m.get('productOffering')).get('id'));
                Map<String, String> ch = AgenticTelco_Tmf.chars(AgenticTelco_Tmf.toMap(m.get('product')).get('productCharacteristic'));
                PricebookEntry e = oid == null ? null : AgenticTelco_Tmf.choosePrice(prices.get(Id.valueOf(oid)), null, ch.get('AgenticTelco Contract Term'));
                if (e == null) throw new AgenticTelco_TMF622.TmfException('No AgenticTelco price for productOffering ' + oid);
                Decimal qty = m.get('quantity') == null ? 1 : Decimal.valueOf(String.valueOf(m.get('quantity')));
                lines.add(new QuoteLineItem(QuoteId = q.Id, PricebookEntryId = e.Id, Product2Id = e.Product2Id, Quantity = qty,
                                            UnitPrice = e.UnitPrice, 
                                            Description = ('AgenticTelco ' + JSON.serialize(ch)).left(255)));
            }
            insert lines;
            AgenticTelco_Tmf.respond(201, serialize([SELECT Id, Name, Status, Description, CreatedDate, ExpirationDate, AccountId, Account.Name,
                                                     TotalPrice FROM Quote WHERE Id = :q.Id])[0]);
        } catch (Exception ex) {
            Database.rollback(sp);
            AgenticTelco_Tmf.error(422, 'QUOTE_REJECTED', ex.getTypeName() + ': ' + ex.getMessage());
        }
    }

    @HttpPatch
    global static void doPatch() {
        List<String> seg = AgenticTelco_Tmf.segments();
        if (seg.size() < 2) { AgenticTelco_Tmf.error(400, 'MISSING_ID', 'PATCH needs /quote/{id}'); return; }
        String id = seg[1];
        List<Quote> qs = [SELECT Id, Name, Status, Description, CreatedDate, ExpirationDate, AccountId, Account.Name, TotalPrice
                          FROM Quote WHERE Id = :id LIMIT 1];
        if (qs.isEmpty()) { AgenticTelco_Tmf.error(404, 'NOT_FOUND', 'quote ' + id); return; }
        if (!AgenticTelco_Tmf.isOurs(qs[0].Name)) { AgenticTelco_Tmf.error(403, 'NOT_AGENTICTELCO', 'Only AgenticTelco demo quotes can be changed'); return; }
        String state = AgenticTelco_Tmf.str(AgenticTelco_Tmf.body().get('state'));
        if (!TO_SF.containsKey(state)) { AgenticTelco_Tmf.error(400, 'BAD_STATE', 'unsupported state ' + state); return; }
        try {
            update new Quote(Id = qs[0].Id, Status = TO_SF.get(state));
            AgenticTelco_Tmf.respond(200, serialize([SELECT Id, Name, Status, Description, CreatedDate, ExpirationDate, AccountId, Account.Name,
                                                     TotalPrice FROM Quote WHERE Id = :qs[0].Id])[0]);
        } catch (Exception ex) {
            AgenticTelco_Tmf.error(422, 'STATE_CHANGE_REJECTED', ex.getMessage());
        }
    }

    static String stage() {
        for (Schema.PicklistEntry e : Opportunity.StageName.getDescribe().getPicklistValues()) {
            if (e.isActive()) return e.getValue();
        }
        return 'Prospecting';
    }

    public static String state(String sf) {
        for (String k : TO_SF.keySet()) if (TO_SF.get(k) == sf) return k;
        return 'inProgress';
    }

    public static List<Map<String, Object>> serialize(List<Quote> qs) {
        Set<Id> ids = new Map<Id, Quote>(qs).keySet();
        Map<Id, List<Object>> items = new Map<Id, List<Object>>();
        for (QuoteLineItem i : [SELECT Id, QuoteId, Product2Id, Product2.Name, Quantity, UnitPrice, PricebookEntryId, ProductSellingModel.Name
                                FROM QuoteLineItem WHERE QuoteId IN :ids ORDER BY LineNumber]) {
            if (!items.containsKey(i.QuoteId)) items.put(i.QuoteId, new List<Object>());
            items.get(i.QuoteId).add(new Map<String, Object>{
                'id' => i.Id, 'action' => 'add', 'quantity' => i.Quantity, 'state' => 'inProgress',
                'productOffering' => AgenticTelco_Tmf.ref(i.Product2Id, i.Product2.Name, 'ProductOffering',
                    AgenticTelco_Tmf.href('tmf620', 'productOffering', i.Product2Id)),
                'quoteItemPrice' => new List<Object>{ new Map<String, Object>{
                    'priceType' => i.ProductSellingModel == null ? null : i.ProductSellingModel.Name,
                    'price' => new Map<String, Object>{ 'taxIncludedAmount' => new Map<String, Object>{
                        'unit' => AgenticTelco_Tmf.currencyCode(), 'value' => i.UnitPrice } } } },
                '@type' => 'QuoteItem' });
        }
        List<Map<String, Object>> out = new List<Map<String, Object>>();
        for (Quote q : qs) {
            out.add(new Map<String, Object>{
                'id' => q.Id, 'href' => AgenticTelco_Tmf.href('tmf648', 'quote', q.Id),
                'externalId' => q.Name != null && q.Name.startsWith('AgenticTelco Quote ') ? q.Name.substringAfter('AgenticTelco Quote ') : null,
                'state' => state(q.Status), 'x-sfStatus' => q.Status, 'quoteDate' => q.CreatedDate, 'description' => q.Description,
                'validFor' => new Map<String, Object>{ 'endDateTime' => q.ExpirationDate },
                'relatedParty' => AgenticTelco_Tmf.party(q.AccountId == null ? null : new Account(Id = q.AccountId, Name = q.Account.Name)),
                'quoteTotalPrice' => new List<Object>{ new Map<String, Object>{ 'price' => new Map<String, Object>{
                    'taxIncludedAmount' => new Map<String, Object>{ 'unit' => AgenticTelco_Tmf.currencyCode(), 'value' => q.TotalPrice } } } },
                'quoteItem' => items.containsKey(q.Id) ? items.get(q.Id) : new List<Object>(),
                'x-runtime' => AgenticTelco_Tmf.SOR_LABEL, '@type' => 'Quote' });
        }
        return out;
    }
}
