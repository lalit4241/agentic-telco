/**
 * TMF622 Product Ordering (v4/v5 resource shapes) – custom TMF API on Salesforce.
 * The org's native Direct Access TMF622 v5 resource exists but every GET fails on this org (its internal GraphQL query
 * selects Order.PoNumber / Order.OrderReferenceNumber, which are not available here) so reads and AgenticTelco writes go
 * through this resource over the standard Order / OrderItem objects and the AgenticTelco EPC price book.
 *   GET   /agentictelco/tmf622/productOrder[/{id}]   ?state=acknowledged&limit=20&scope=all
 *   POST  /agentictelco/tmf622/productOrder          (idempotent on externalId)
 *   PATCH /agentictelco/tmf622/productOrder/{id}     {"state":"inProgress"|"cancelled"}  – AgenticTelco orders only
 *
 * Upgrade (MVP build item 1): a productOrderItem may carry "action":"modify" with "product":{"id":<installed Asset id>}.
 * Mapping only, no business rules: the action and the installed product it modifies are recorded on the OrderItem
 * and returned in TMF622 shape. Whether the upgrade is allowed is decided outside Salesforce (OPA), and the asset
 * change is done by the L5 workflow through standard sObject REST.
 */
@RestResource(urlMapping='/agentictelco/tmf622/*')
global with sharing class AgenticTelco_TMF622 {
    static final String CANCEL_MARK = '[AgenticTelco compensation: cancelled]';

    @HttpGet
    global static void doGet() {
        List<String> seg = AgenticTelco_Tmf.segments();
        String id = seg.size() > 1 ? seg[1] : null;
        Integer lim = Math.min(AgenticTelco_Tmf.intParam('limit', 20), 100);
        Boolean all = AgenticTelco_Tmf.param('scope') == 'all';
        String q = 'SELECT Id, Name, OrderNumber, Status, Description, EffectiveDate, CreatedDate, AccountId, Account.Name, TotalAmount FROM Order';
        q += id != null ? ' WHERE Id = :id' : (all ? '' : ' WHERE Name LIKE \'AgenticTelco%\'');
        q += ' ORDER BY CreatedDate DESC LIMIT :lim';
        List<Order> os = Database.query(q);
        if (id != null && os.isEmpty()) { AgenticTelco_Tmf.error(404, 'NOT_FOUND', 'productOrder ' + id); return; }
        List<Map<String, Object>> out = serialize(os);
        String state = AgenticTelco_Tmf.param('state');
        if (state != null) {
            List<Map<String, Object>> f = new List<Map<String, Object>>();
            for (Map<String, Object> o : out) if (o.get('state') == state) f.add(o);
            out = f;
        }
        AgenticTelco_Tmf.respond(200, id == null ? (Object) out : (Object) out[0]);
    }

    @HttpPost
    global static void doPost() {
        Map<String, Object> b = AgenticTelco_Tmf.body();
        String ext = AgenticTelco_Tmf.str(b.get('externalId'));
        if (String.isBlank(ext)) { AgenticTelco_Tmf.error(400, 'MISSING_EXTERNAL_ID', 'externalId is required (idempotency key)'); return; }
        String name = (AgenticTelco_Tmf.PREFIX + ' PO ' + ext).left(80);
        List<Order> existing = [SELECT Id, Name, OrderNumber, Status, Description, EffectiveDate, CreatedDate, AccountId, Account.Name, TotalAmount
                                FROM Order WHERE Name = :name LIMIT 1];
        if (!existing.isEmpty()) { AgenticTelco_Tmf.respond(200, serialize(existing)[0]); return; }
        Account acc = AgenticTelco_Tmf.account(b.get('relatedParty'));
        if (acc == null) { AgenticTelco_Tmf.error(400, 'MISSING_CUSTOMER', 'relatedParty must reference a Salesforce Account id'); return; }
        Id pb = AgenticTelco_Tmf.pricebookId();
        if (pb == null) { AgenticTelco_Tmf.error(409, 'NO_PRICEBOOK', 'AgenticTelco Price Book not found – run seed/epc/seed_epc.py'); return; }
        List<Object> items = AgenticTelco_Tmf.toList(b.get('productOrderItem'));
        if (items.isEmpty()) { AgenticTelco_Tmf.error(400, 'NO_ITEMS', 'productOrderItem is empty'); return; }
        Set<Id> offerIds = new Set<Id>();
        for (Object o : items) {
            String oid = AgenticTelco_Tmf.str(AgenticTelco_Tmf.toMap(AgenticTelco_Tmf.toMap(o).get('productOffering')).get('id'));
            if (oid != null) offerIds.add(Id.valueOf(oid));
        }
        Map<Id, List<PricebookEntry>> prices = AgenticTelco_Tmf.pricesFor(offerIds, pb);
        for (Object it : items) {
            Map<String, Object> m = AgenticTelco_Tmf.toMap(it);
            String act = actionOf(m);
            if (act != 'add' && act != 'modify') { AgenticTelco_Tmf.error(400, 'BAD_ACTION', 'action must be add or modify'); return; }
            if (act == 'modify') {
                String pid = AgenticTelco_Tmf.str(AgenticTelco_Tmf.toMap(m.get('product')).get('id'));
                List<Asset> cur = String.isBlank(pid) ? new List<Asset>() : findAsset(pid, acc.Id);
                if (cur.isEmpty()) { AgenticTelco_Tmf.error(400, 'MODIFY_NEEDS_PRODUCT', 'action modify needs product.id of an AgenticTelco Asset on this customer'); return; }
            }
        }
        Savepoint sp = Database.setSavepoint();
        try {
            List<String> notes = new List<String>();
            Order o = new Order(Name = name, AccountId = acc.Id, Pricebook2Id = pb, Status = 'Draft', EffectiveDate = Date.today(),
                                Description = 'AgenticTelco demo order via custom TMF622 API. ' + AgenticTelco_Tmf.str(b.get('description')));
            insert o;
            List<OrderItem> ois = new List<OrderItem>();
            for (Object it : items) {
                Map<String, Object> m = AgenticTelco_Tmf.toMap(it);
                String oid = AgenticTelco_Tmf.str(AgenticTelco_Tmf.toMap(m.get('productOffering')).get('id'));
                Map<String, String> ch = AgenticTelco_Tmf.chars(AgenticTelco_Tmf.toMap(m.get('product')).get('productCharacteristic'));
                String term = ch.get('AgenticTelco Contract Term');
                PricebookEntry e = oid == null ? null : AgenticTelco_Tmf.choosePrice(prices.get(Id.valueOf(oid)),
                    AgenticTelco_Tmf.str(AgenticTelco_Tmf.toMap(m.get('productOfferingPrice')).get('id')), term);
                if (e == null) throw new TmfException('No AgenticTelco price for productOffering ' + oid);
                Decimal qty = m.get('quantity') == null ? 1 : Decimal.valueOf(String.valueOf(m.get('quantity')));
                OrderItem oi = new OrderItem(OrderId = o.Id, PricebookEntryId = e.Id, Product2Id = e.Product2Id, Quantity = qty,
                                             UnitPrice = e.UnitPrice, 
                                             Description = ('AgenticTelco item ' + m.get('id') + marker(m) + ' ' + JSON.serialize(ch)).left(255));
                if (e.ProductSellingModel != null && e.ProductSellingModel.SellingModelType != 'OneTime') {
                    oi.ServiceDate = Date.today();
                    oi.PeriodBoundary = 'Anniversary';
                }
                if (e.ProductSellingModel != null && e.ProductSellingModel.SellingModelType == 'TermDefined') {
                    Integer months = term == null || !term.isNumeric() || term == '0' ? 12 : Integer.valueOf(term);
                    oi.EndDate = Date.today().addMonths(months).addDays(-1);
                }
                ois.add(oi);
                notes.add(e.Product2.Name);
            }
            insert ois;
            AgenticTelco_Tmf.respond(201, serialize([SELECT Id, Name, OrderNumber, Status, Description, EffectiveDate, CreatedDate, AccountId,
                                                     Account.Name, TotalAmount FROM Order WHERE Id = :o.Id])[0]);
        } catch (Exception ex) {
            Database.rollback(sp);
            AgenticTelco_Tmf.error(422, 'ORDER_REJECTED', ex.getTypeName() + ': ' + ex.getMessage());
        }
    }

    @HttpPatch
    global static void doPatch() {
        List<String> seg = AgenticTelco_Tmf.segments();
        if (seg.size() < 2) { AgenticTelco_Tmf.error(400, 'MISSING_ID', 'PATCH needs /productOrder/{id}'); return; }
        String id = seg[1];
        List<Order> os = [SELECT Id, Name, OrderNumber, Status, Description, EffectiveDate, CreatedDate, AccountId, Account.Name, TotalAmount
                          FROM Order WHERE Id = :id LIMIT 1];
        if (os.isEmpty()) { AgenticTelco_Tmf.error(404, 'NOT_FOUND', 'productOrder ' + id); return; }
        Order o = os[0];
        if (!AgenticTelco_Tmf.isOurs(o.Name)) { AgenticTelco_Tmf.error(403, 'NOT_AGENTICTELCO', 'Only AgenticTelco demo orders can be changed'); return; }
        String state = AgenticTelco_Tmf.str(AgenticTelco_Tmf.body().get('state'));
        try {
            if (state == 'cancelled') {
                if (o.Description == null || !o.Description.contains(CANCEL_MARK)) {
                    o.Description = (CANCEL_MARK + ' ' + (o.Description == null ? '' : o.Description)).left(32000);
                }
                if (o.Status == 'Draft') o.Status = 'Exception';
            } else if (state == 'inProgress') {
                o.Status = 'Submitted';
            } else if (state == 'completed') {
                if (o.Description != null && o.Description.contains(CANCEL_MARK)) {
                    AgenticTelco_Tmf.error(409, 'ORDER_CANCELLED', 'A compensated (cancelled) order cannot be completed'); return;
                }
                o.Status = 'Activated';
            } else {
                AgenticTelco_Tmf.error(400, 'BAD_STATE', 'state must be inProgress, completed or cancelled'); return;
            }
            update new Order(Id = o.Id, Status = o.Status, Description = o.Description);
            AgenticTelco_Tmf.respond(200, serialize([SELECT Id, Name, OrderNumber, Status, Description, EffectiveDate, CreatedDate, AccountId,
                                                     Account.Name, TotalAmount FROM Order WHERE Id = :o.Id])[0]);
        } catch (Exception ex) {
            AgenticTelco_Tmf.error(422, 'STATE_CHANGE_REJECTED', ex.getMessage());
        }
    }

    public static String state(Order o) {
        if (o.Description != null && o.Description.contains(CANCEL_MARK)) return 'cancelled';
        if (o.Status == 'Draft') return 'acknowledged';
        if (o.Status == 'Submitted') return 'inProgress';
        if (o.Status == 'Activated') return 'completed';
        return 'failed';
    }

    public static List<Map<String, Object>> serialize(List<Order> os) {
        Set<Id> ids = new Map<Id, Order>(os).keySet();
        Map<Id, List<Object>> items = new Map<Id, List<Object>>();
        for (OrderItem i : [SELECT Id, OrderId, Product2Id, Product2.Name, Quantity, UnitPrice, TotalPrice, PricebookEntryId,
                                   ProductSellingModel.Name, Description FROM OrderItem WHERE OrderId IN :ids ORDER BY CreatedDate]) {
            if (!items.containsKey(i.OrderId)) items.put(i.OrderId, new List<Object>());
            items.get(i.OrderId).add(new Map<String, Object>{
                'id' => i.Id, 'action' => itemAction(i.Description), 'product' => itemProduct(i.Description), 'quantity' => i.Quantity, 'state' => 'acknowledged',
                'productOffering' => AgenticTelco_Tmf.ref(i.Product2Id, i.Product2.Name, 'ProductOffering',
                    AgenticTelco_Tmf.href('tmf620', 'productOffering', i.Product2Id)),
                'productOfferingPrice' => AgenticTelco_Tmf.ref(i.PricebookEntryId, i.ProductSellingModel == null ? null : i.ProductSellingModel.Name,
                    'ProductOfferingPrice', AgenticTelco_Tmf.href('tmf620', 'productOfferingPrice', i.PricebookEntryId)),
                'itemPrice' => new List<Object>{ new Map<String, Object>{ 'price' => new Map<String, Object>{
                    'taxIncludedAmount' => new Map<String, Object>{ 'unit' => AgenticTelco_Tmf.currencyCode(), 'value' => i.UnitPrice } } } },
                '@type' => 'ProductOrderItem' });
        }
        List<Map<String, Object>> out = new List<Map<String, Object>>();
        for (Order o : os) {
            String ext = o.Name != null && o.Name.startsWith('AgenticTelco PO ') ? o.Name.substringAfter('AgenticTelco PO ') : null;
            out.add(new Map<String, Object>{
                'id' => o.Id, 'href' => AgenticTelco_Tmf.href('tmf622', 'productOrder', o.Id), 'externalId' => ext,
                'x-orderNumber' => o.OrderNumber, 'state' => state(o), 'x-sfStatus' => o.Status, 'orderDate' => o.CreatedDate,
                'requestedStartDate' => o.EffectiveDate, 'description' => o.Description,
                'relatedParty' => AgenticTelco_Tmf.party(o.AccountId == null ? null : new Account(Id = o.AccountId, Name = o.Account.Name)),
                'orderTotalPrice' => new List<Object>{ new Map<String, Object>{ 'price' => new Map<String, Object>{
                    'taxIncludedAmount' => new Map<String, Object>{ 'unit' => AgenticTelco_Tmf.currencyCode(), 'value' => o.TotalAmount } } } },
                'productOrderItem' => items.containsKey(o.Id) ? items.get(o.Id) : new List<Object>(),
                'x-runtime' => AgenticTelco_Tmf.SOR_LABEL, '@type' => 'ProductOrder' });
        }
        return out;
    }

    static final String MODIFY_MARK = ' action=modify product=';

    static String actionOf(Map<String, Object> m) {
        String a = AgenticTelco_Tmf.str(m.get('action'));
        return String.isBlank(a) ? 'add' : a;
    }

    static List<Asset> findAsset(String pid, Id accountId) {
        try {
            return [SELECT Id FROM Asset WHERE Id = :pid AND AccountId = :accountId AND Name LIKE 'AgenticTelco%' LIMIT 1];
        } catch (Exception e) {
            return new List<Asset>();
        }
    }

    static String marker(Map<String, Object> m) {
        if (actionOf(m) != 'modify') return '';
        return MODIFY_MARK + AgenticTelco_Tmf.str(AgenticTelco_Tmf.toMap(m.get('product')).get('id'));
    }

    public static String itemAction(String description) {
        return description != null && description.contains(MODIFY_MARK) ? 'modify' : 'add';
    }

    public static Map<String, Object> itemProduct(String description) {
        if (itemAction(description) != 'modify') return null;
        String pid = description.substringAfter(MODIFY_MARK).substringBefore(' ');
        return AgenticTelco_Tmf.ref(pid, null, 'Product', '/services/data/v68.0/connect/comms/productinventorymanagement/v5/productinventory/' + pid);
    }

    public class TmfException extends Exception {}
}
