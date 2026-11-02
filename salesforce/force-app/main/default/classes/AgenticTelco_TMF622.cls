/**
 * TMF622 Product Ordering (v4/v5 resource shapes) – TMF facade within Salesforce (Apex).
 * The org's native Direct Access TMF622 v5 resource exists but every GET fails on this org (its internal GraphQL query
 * selects Order.PoNumber / Order.OrderReferenceNumber, which are not available here) so reads and AgenticTelco writes go
 * through this resource over the standard Order / OrderItem objects and the AgenticTelco EPC price book.
 *   GET   /agentictelco/tmf622/productOrder[/{id}]   ?state=acknowledged&limit=20&scope=all
 *   POST  /agentictelco/tmf622/productOrder          (idempotent on externalId)
 *   PATCH /agentictelco/tmf622/productOrder/{id}     {"state":"inProgress"|"cancelled"}  – AgenticTelco orders only
 *
 * Upgrade: the product-level change is sent as two linked items (delete + add), e.g. a Fibre 150 -> Fibre 900 upgrade:
 *   {"id":"1","action":"delete","product":{"id":<installed Fibre 150 Asset>}}
 *   {"id":"2","action":"add","productOffering":{"id":<Fibre 900>},"productOrderItemRelationship":[{"id":"1","relationshipType":"replaces"}]}
 * recorded natively as OrderAction Cancel/UpgradeFrom and Add/UpgradeTo. The add line starts on the upgrade date (new
 * monthly price from then) and keeps the contract end date of the product it replaces. "action":"modify" with
 * "product":{"id":<installed Asset id>} is still accepted (OrderAction Amend/UpgradeTo).
 * Mapping only, no business rules: whether the upgrade is allowed is decided outside Salesforce (OPA). The installed
 * product (TMF637) is written by ONE writer, chosen at build time (AgenticTelco_Assetisation): the plan step
 * 'Record the installed product (TMF637)' or the built-in asset step. The L5 workflow only reads it back.
 * Response shape: each productOrderItem's state follows the order (acknowledged -> inProgress -> completed); itemPrice
 * and orderTotalPrice carry priceType (recurring, recurringChargePeriod month / oneTime); productOrderItemRelationship
 * links each bundle component to its bundle line ('bundled') and the add line to the line it replaces ('replaces').
 * POST also adds the usage record the org's Custom Assetize Order flow expects (internal step, see ensureUsageRecord).
 *
 * Salesforce order orchestration (MVP build, route A): POST records the TMF action natively as an OrderAction
 * (delete -> Cancel, add -> Add, with Subtype UpgradeFrom/UpgradeTo when linked; modify -> Amend/UpgradeTo) and adds the
 * required component lines (access line, router) of the add (or modify) bundle line, never of the deleted line, with
 * their OrderItemRelationships, so the built-in decomposition can turn the order into customer facing services (CFS).
 * The component lines are commercial products, not CFS: each gets its own action code, derived from the installed base
 * (TMF637) the same way as the CFS codes, not inherited from the bundle (on a 150 -> 900 upgrade the Fibre Access Line
 * is noChange (OrderAction No Change) and the Wi-Fi 6 Router line is modify (OrderAction Amend)).
 * PATCH inProgress (sent only by the L5 workflow, after the go-ahead and the binding policy check) submits the order
 * to orchestration synchronously and returns x-orchestration {fulfillmentPlanId, status}; if no fulfilment plan is
 * created, x-orchestration.status is notSubmitted with an error, and the workflow stops the run (no fallback route).
 * GET by id returns x-orchestration: decomposition, plan steps, TMF641 service order and network calls.
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
        if (id != null && AgenticTelco_Tmf.isOurs(os[0].Name)) out[0].put('x-orchestration', AgenticTelco_Orchestration.view(os[0].Id));
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
        if (!existing.isEmpty()) {
            Map<String, Object> ex = serialize(existing)[0];
            if (existing[0].Status == 'Draft') ex.put('x-usageRecord', ensureUsageRecord(existing[0].Id));
            AgenticTelco_Tmf.respond(200, ex);
            return;
        }
        Account acc = AgenticTelco_Tmf.account(b.get('relatedParty'));
        if (acc == null) { AgenticTelco_Tmf.error(400, 'MISSING_CUSTOMER', 'relatedParty must reference a Salesforce Account id'); return; }
        Id pb = AgenticTelco_Tmf.pricebookId();
        if (pb == null) { AgenticTelco_Tmf.error(409, 'NO_PRICEBOOK', 'AgenticTelco Price Book not found – run seed/epc/seed_epc.py'); return; }
        List<Object> items = AgenticTelco_Tmf.toList(b.get('productOrderItem'));
        if (items.isEmpty()) { AgenticTelco_Tmf.error(400, 'NO_ITEMS', 'productOrderItem is empty'); return; }
        Map<String, Map<String, Object>> byItemId = new Map<String, Map<String, Object>>();
        Map<String, Asset> installed = new Map<String, Asset>();   // request item id -> installed Asset (delete / modify)
        for (Object it : items) {
            Map<String, Object> m = AgenticTelco_Tmf.toMap(it);
            String act = actionOf(m);
            if (act != 'add' && act != 'modify' && act != 'delete') { AgenticTelco_Tmf.error(400, 'BAD_ACTION', 'action must be add, modify or delete'); return; }
            byItemId.put(String.valueOf(m.get('id')), m);
            if (act == 'modify' || act == 'delete') {
                String pid = AgenticTelco_Tmf.str(AgenticTelco_Tmf.toMap(m.get('product')).get('id'));
                List<Asset> cur = String.isBlank(pid) ? new List<Asset>() : findAsset(pid, acc.Id);
                if (cur.isEmpty()) { AgenticTelco_Tmf.error(400, act.toUpperCase() + '_NEEDS_PRODUCT', 'action ' + act + ' needs product.id of an AgenticTelco Asset on this customer'); return; }
                installed.put(String.valueOf(m.get('id')), cur[0]);
                if (act == 'delete' && AgenticTelco_Tmf.toMap(m.get('productOffering')).get('id') == null) m.put('productOffering', new Map<String, Object>{ 'id' => cur[0].Product2Id });
            }
        }
        Map<String, String> replacedBy = new Map<String, String>();   // delete item id -> add item id
        for (Map<String, Object> m : byItemId.values()) {
            String rid = replacesOf(m);
            if (rid == null) continue;
            if (actionOf(m) != 'add' || !byItemId.containsKey(rid) || actionOf(byItemId.get(rid)) != 'delete') {
                AgenticTelco_Tmf.error(400, 'BAD_RELATIONSHIP', 'relationshipType replaces links an add item to a delete item of the same order'); return;
            }
            replacedBy.put(rid, String.valueOf(m.get('id')));
        }
        Set<Id> offerIds = new Set<Id>();
        for (Object o : items) {
            String oid = AgenticTelco_Tmf.str(AgenticTelco_Tmf.toMap(AgenticTelco_Tmf.toMap(o).get('productOffering')).get('id'));
            if (oid != null) offerIds.add(Id.valueOf(oid));
        }
        Map<Id, List<PricebookEntry>> prices = AgenticTelco_Tmf.pricesFor(offerIds, pb);
        Savepoint sp = Database.setSavepoint();
        try {
            List<String> notes = new List<String>();
            Order o = new Order(Name = name, AccountId = acc.Id, Pricebook2Id = pb, Status = 'Draft', EffectiveDate = Date.today(),
                                Description = 'AgenticTelco demo order via custom TMF622 API. ' + AgenticTelco_Tmf.str(b.get('description')));
            insert o;
            Map<String, OrderAction> actions = new Map<String, OrderAction>();
            for (Object it : items) {
                Map<String, Object> m = AgenticTelco_Tmf.toMap(it);
                String k = actionKey(m, replacedBy);
                if (actions.containsKey(k)) continue;
                String act = actionOf(m);
                actions.put(k, act == 'modify' ? new OrderAction(OrderId = o.Id, Type = 'Amend', Subtype = 'UpgradeTo')
                             : act == 'delete' ? new OrderAction(OrderId = o.Id, Type = 'Cancel', Subtype = k.endsWith('/up') ? 'UpgradeFrom' : null)
                             : new OrderAction(OrderId = o.Id, Type = 'Add', Subtype = k.endsWith('/up') ? 'UpgradeTo' : null));
            }
            insert actions.values();
            List<OrderItem> ois = new List<OrderItem>();
            List<Map<String, Object>> lineSpecs = new List<Map<String, Object>>();
            for (Object it : items) {
                Map<String, Object> m = AgenticTelco_Tmf.toMap(it);
                String oid = AgenticTelco_Tmf.str(AgenticTelco_Tmf.toMap(m.get('productOffering')).get('id'));
                Map<String, String> ch = AgenticTelco_Tmf.chars(AgenticTelco_Tmf.toMap(m.get('product')).get('productCharacteristic'));
                String term = ch.get('AgenticTelco Contract Term');
                String act = actionOf(m);
                String rid = replacesOf(m);
                Asset basis = act == 'add' ? (rid == null ? null : installed.get(rid)) : installed.get(String.valueOf(m.get('id')));
                // a replacement with no term given stays on the running contract (term-defined price, same end date)
                String priceTerm = term == null && basis != null && basis.UsageEndDate != null && basis.UsageEndDate >= Date.today() ? 'carry' : term;
                PricebookEntry e = oid == null ? null : AgenticTelco_Tmf.choosePrice(prices.get(Id.valueOf(oid)),
                    AgenticTelco_Tmf.str(AgenticTelco_Tmf.toMap(m.get('productOfferingPrice')).get('id')), priceTerm);
                if (e == null) throw new TmfException('No AgenticTelco price for productOffering ' + oid);
                Decimal qty = m.get('quantity') == null ? 1 : Decimal.valueOf(String.valueOf(m.get('quantity')));
                // the platform carries the quantity change on the line: a deleted line goes from 1 to 0 (Quantity -1)
                OrderItem oi = new OrderItem(OrderId = o.Id, PricebookEntryId = e.Id, Product2Id = e.Product2Id, Quantity = act == 'delete' ? -qty : qty,
                                             UnitPrice = e.UnitPrice, OrderActionId = actions.get(actionKey(m, replacedBy)).Id,
                                             Description = ('AgenticTelco item ' + m.get('id') + marker(m) + (rid == null ? '' : REPLACES_MARK + rid) + ' ' + JSON.serialize(ch)).left(255));
                if (act != 'add') oi.StartQuantity = qty;
                if (e.ProductSellingModel != null && e.ProductSellingModel.SellingModelType != 'OneTime') {
                    oi.ServiceDate = Date.today();   // the upgrade date: the new monthly price applies from here; a deleted line ends here
                    oi.PeriodBoundary = 'Anniversary';
                }
                if (e.ProductSellingModel != null && e.ProductSellingModel.SellingModelType == 'TermDefined') {
                    Integer months = term == null || !term.isNumeric() || term == '0' ? 12 : Integer.valueOf(term);
                    // the contract end date of the product being replaced (or deleted) carries over
                    oi.EndDate = basis != null && basis.UsageEndDate != null && basis.UsageEndDate >= Date.today() ? basis.UsageEndDate
                               : Date.today().addMonths(months).addDays(-1);
                }
                ois.add(oi);
                lineSpecs.add(new Map<String, Object>{ 'm' => m, 'e' => e, 'term' => term, 'basis' => basis == null ? null : String.valueOf(basis.Id) });
                notes.add(e.Product2.Name);
            }
            insert ois;
            addComponentLines(o.Id, pb, ois, lineSpecs, actions);
            Id usage = ensureUsageRecord(o.Id);
            Map<String, Object> created = serialize([SELECT Id, Name, OrderNumber, Status, Description, EffectiveDate, CreatedDate, AccountId,
                                                     Account.Name, TotalAmount FROM Order WHERE Id = :o.Id])[0];
            created.put('x-usageRecord', usage);
            AgenticTelco_Tmf.respond(201, created);
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
                Map<String, Object> orch = submitToOrchestration(o);
                Map<String, Object> res = serialize([SELECT Id, Name, OrderNumber, Status, Description, EffectiveDate, CreatedDate, AccountId,
                                                     Account.Name, TotalAmount FROM Order WHERE Id = :o.Id])[0];
                res.put('x-orchestration', orch);
                AgenticTelco_Tmf.respond(200, res);
                return;
            } else if (state == 'completed') {
                if (o.Description != null && o.Description.contains(CANCEL_MARK)) {
                    AgenticTelco_Tmf.error(409, 'ORDER_CANCELLED', 'A compensated (cancelled) order cannot be completed'); return;
                }
                if (o.Status == 'Activated') {   // already completed by the orchestration plan (step 7): idempotent
                    AgenticTelco_Tmf.respond(200, serialize(new List<Order>{ o })[0]);
                    return;
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
        Map<Id, List<OrderItem>> lines = new Map<Id, List<OrderItem>>();
        for (OrderItem i : [SELECT Id, OrderId, Product2Id, Product2.Name, Quantity, UnitPrice, TotalPrice, PricebookEntryId, ServiceDate, EndDate,
                                   ProductSellingModel.Name, ProductSellingModel.SellingModelType, PricebookEntry.ProductSellingModel.SellingModelType, Description FROM OrderItem WHERE OrderId IN :ids ORDER BY CreatedDate, Id]) {
            if (!lines.containsKey(i.OrderId)) lines.put(i.OrderId, new List<OrderItem>());
            lines.get(i.OrderId).add(i);
        }
        Map<Id, Id> bundleOf = new Map<Id, Id>();   // component line -> its bundle line
        for (OrderItemRelationship r : [SELECT MainOrderItemId, AssociatedOrderItemId FROM OrderItemRelationship WHERE MainOrderItem.OrderId IN :ids]) {
            bundleOf.put(r.AssociatedOrderItemId, r.MainOrderItemId);
        }
        List<Map<String, Object>> out = new List<Map<String, Object>>();
        for (Order o : os) {
            String st = state(o);
            Map<String, Id> sfIdOf = new Map<String, Id>();   // request item id -> OrderItem id
            List<OrderItem> ls = lines.containsKey(o.Id) ? lines.get(o.Id) : new List<OrderItem>();
            for (OrderItem i : ls) if (i.Description != null && i.Description.startsWith('AgenticTelco item ')) sfIdOf.put(i.Description.substringAfter('AgenticTelco item ').substringBefore(' '), i.Id);
            List<Object> items = new List<Object>();
            Decimal recurring = 0, oneTime = 0;
            for (OrderItem i : ls) {
                String act = itemAction(i.Description);
                String type = priceType(i);
                Decimal q = i.Quantity == null ? 0 : i.Quantity;
                if (act != 'delete' && q > 0 && i.UnitPrice != null) {
                    if (type == 'recurring') recurring += i.UnitPrice * q; else oneTime += i.UnitPrice * q;
                }
                List<Object> rels = new List<Object>();
                if (bundleOf.containsKey(i.Id)) rels.add(relationship(bundleOf.get(i.Id), 'bundled'));
                String rid = replacesId(i.Description);
                if (rid != null && sfIdOf.containsKey(rid)) rels.add(relationship(sfIdOf.get(rid), 'replaces'));
                Map<String, Object> product = itemProduct(i.Description);
                if (product == null && act == 'add' && (i.ServiceDate != null || i.EndDate != null)) {
                    product = new Map<String, Object>{ 'startDate' => i.ServiceDate, 'terminationDate' => i.EndDate, '@type' => 'Product' };
                }
                items.add(new Map<String, Object>{
                    'id' => i.Id, 'action' => act, 'product' => product, 'quantity' => act == 'delete' ? q.abs() : q, 'state' => st,
                    'x-bundleComponent' => isComponentLine(i.Description),
                    'productOffering' => AgenticTelco_Tmf.ref(i.Product2Id, i.Product2.Name, 'ProductOffering',
                        AgenticTelco_Tmf.href('tmf620', 'productOffering', i.Product2Id)),
                    'productOfferingPrice' => AgenticTelco_Tmf.ref(i.PricebookEntryId, i.ProductSellingModel == null ? null : i.ProductSellingModel.Name,
                        'ProductOfferingPrice', AgenticTelco_Tmf.href('tmf620', 'productOfferingPrice', i.PricebookEntryId)),
                    'itemPrice' => new List<Object>{ price(type, i.UnitPrice) },
                    'productOrderItemRelationship' => rels,
                    '@type' => 'ProductOrderItem' });
            }
            List<Object> total = new List<Object>{ price('recurring', recurring) };
            if (oneTime > 0) total.add(price('oneTime', oneTime));
            String ext = o.Name != null && o.Name.startsWith('AgenticTelco PO ') ? o.Name.substringAfter('AgenticTelco PO ') : null;
            out.add(new Map<String, Object>{
                'id' => o.Id, 'href' => AgenticTelco_Tmf.href('tmf622', 'productOrder', o.Id), 'externalId' => ext,
                'x-orderNumber' => o.OrderNumber, 'state' => st, 'x-sfStatus' => o.Status, 'orderDate' => o.CreatedDate,
                'requestedStartDate' => o.EffectiveDate, 'description' => o.Description,
                'relatedParty' => AgenticTelco_Tmf.party(o.AccountId == null ? null : new Account(Id = o.AccountId, Name = o.Account.Name)),
                'orderTotalPrice' => total,
                'productOrderItem' => items,
                'x-runtime' => AgenticTelco_Tmf.SOR_LABEL, '@type' => 'ProductOrder' });
        }
        return out;
    }

    /** recurring (monthly) unless the line's selling model is one-time. */
    @TestVisible static String priceType(OrderItem i) {
        String t = i.ProductSellingModel != null ? i.ProductSellingModel.SellingModelType
                 : i.PricebookEntry != null && i.PricebookEntry.ProductSellingModel != null ? i.PricebookEntry.ProductSellingModel.SellingModelType : null;
        return priceType(t);
    }

    @TestVisible static String priceType(String sellingModelType) {
        return sellingModelType == 'OneTime' ? 'oneTime' : 'recurring';
    }

    @TestVisible static Map<String, Object> price(String type, Decimal amount) {
        Map<String, Object> p = new Map<String, Object>{ 'priceType' => type, '@type' => 'OrderPrice',
            'price' => new Map<String, Object>{ 'taxIncludedAmount' => new Map<String, Object>{ 'unit' => AgenticTelco_Tmf.currencyCode(), 'value' => amount } } };
        if (type == 'recurring') p.put('recurringChargePeriod', 'month');
        return p;
    }

    static Map<String, Object> relationship(Id other, String type) {
        return new Map<String, Object>{ 'id' => other, 'relationshipType' => type, '@type' => 'OrderItemRelationship' };
    }

    /**
     * Internal step, never called by the stack directly: the org's 'Custom Assetize Order' flow expects a Subscription
     * Management usage record (AppUsageAssignment) on each order, and Salesforce only accepts it while the order is Draft.
     * The facade adds it when it creates the order, so the order can later be completed. The flow itself is untouched.
     */
    public static Id ensureUsageRecord(Id orderId) {
        // route BUILT_IN needs the Revenue Lifecycle Management usage for the built-in asset step (OrderToAsset); CUSTOM_STEP keeps the existing one
        String usage = AgenticTelco_Assetisation.route() == AgenticTelco_Assetisation.BUILT_IN ? 'RevenueLifecycleManagement' : 'SubscriptionManagement';
        List<AppUsageAssignment> have = [SELECT Id FROM AppUsageAssignment WHERE RecordId = :orderId AND AppUsageType = :usage LIMIT 1];
        if (!have.isEmpty()) return have[0].Id;
        AppUsageAssignment u = new AppUsageAssignment(RecordId = orderId, AppUsageType = usage);
        insert u;
        return u.Id;
    }

    static final String MODIFY_MARK = ' action=modify product=';
    static final String NOCHANGE_MARK = ' action=noChange product=';
    static final String COMPONENT_MARK = ' component of ';
    static final String DELETE_MARK = ' action=delete product=';
    static final String REPLACES_MARK = ' replaces=';

    /**
     * Submit to Salesforce order orchestration (synchronous submitOrder). Idempotent: an order that already has a plan is
     * not submitted again. Failure leaves the order Submitted with status notSubmitted and the error.
     */
    static Map<String, Object> submitToOrchestration(Order o) {
        Order cur = [SELECT Status, FulfillmentPlanId FROM Order WHERE Id = :o.Id];
        if (cur.Status == 'Draft') update new Order(Id = o.Id, Status = 'Submitted');
        if (cur.FulfillmentPlanId != null) return summary(o.Id, null);
        Savepoint sp = Database.setSavepoint();
        try {
            AgenticTelco_Orchestration.submit(o.Id);
            return summary(o.Id, null);
        } catch (Exception ex) {
            Database.rollback(sp);
            return summary(o.Id, ex.getTypeName() + ': ' + ex.getMessage());
        }
    }

    static Map<String, Object> summary(Id orderId, String error) {
        Order cur = [SELECT FulfillmentPlanId FROM Order WHERE Id = :orderId];
        Map<String, Object> r = new Map<String, Object>{ 'engine' => 'Salesforce order orchestration', 'fulfillmentPlanId' => cur.FulfillmentPlanId };
        if (cur.FulfillmentPlanId == null) { r.put('status', 'notSubmitted'); r.put('error', (error == null ? '' : error.left(400) + '. ') + AgenticTelco_Orchestration.NO_PLAN); return r; }
        Map<String, Object> v = AgenticTelco_Orchestration.view(orderId);
        r.put('status', v.get('status'));
        r.put('planState', v.get('planState'));
        r.put('steps', v.get('steps'));
        return r;
    }

    /** Required components of each bundle line (EPC ProductRelatedComponent), priced at 0 within the bundle price. */
    static void addComponentLines(Id orderId, Id pb, List<OrderItem> parents, List<Map<String, Object>> specs, Map<String, OrderAction> actions) {
        Map<Id, Integer> idx = new Map<Id, Integer>();   // components belong to the add / modify bundle line, never to a deleted line
        for (Integer i = 0; i < parents.size(); i++) if (actionOf((Map<String, Object>) specs[i].get('m')) != 'delete') idx.put(parents[i].Product2Id, i);
        List<ProductRelatedComponent> comps = [SELECT Id, ParentProductId, ChildProductId, ProductRelationshipTypeId FROM ProductRelatedComponent
                                               WHERE ParentProductId IN :idx.keySet() AND IsComponentRequired = true AND ChildProductId != null ORDER BY Id];
        if (comps.isEmpty()) return;
        Set<Id> childIds = new Set<Id>();
        for (ProductRelatedComponent c : comps) childIds.add(c.ChildProductId);
        Map<Id, List<PricebookEntry>> prices = AgenticTelco_Tmf.pricesFor(childIds, pb);
        List<OrderItem> lines = new List<OrderItem>();
        List<ProductRelatedComponent> used = new List<ProductRelatedComponent>();
        Map<Id, Integer> n = new Map<Id, Integer>();
        Map<String, String> compAction = componentActions(parents, specs, childIds, [SELECT AccountId FROM Order WHERE Id = :orderId].AccountId);
        List<OrderAction> extra = new List<OrderAction>();
        Set<String> needed = new Set<String>(compAction.values());
        for (Integer i : idx.values()) needed.add(actionOf((Map<String, Object>) specs[i].get('m')));   // components without their own code follow the bundle line
        for (String a : needed) if (!actions.containsKey(a) && !actions.containsKey(a + '/c')) {
            OrderAction oa = newAction(orderId, a);
            actions.put(a + '/c', oa);
            extra.add(oa);
        }
        insert extra;
        for (ProductRelatedComponent c : comps) {
            Integer pi = idx.get(c.ParentProductId);
            OrderItem parent = parents[pi];
            Map<String, Object> m = (Map<String, Object>) specs[pi].get('m');
            PricebookEntry pe = (PricebookEntry) specs[pi].get('e');
            PricebookEntry e = sameModel(prices.get(c.ChildProductId), pe.ProductSellingModel == null ? null : pe.ProductSellingModel.SellingModelType);
            if (e == null) continue;
            Integer k = n.containsKey(parent.Id) ? n.get(parent.Id) + 1 : 1;
            n.put(parent.Id, k);
            String ca = compAction.containsKey(pi + '>' + c.ChildProductId) ? compAction.get(pi + '>' + c.ChildProductId) : actionOf(m);
            // The platform carries the quantity change on the line: a No Change line has Quantity 0 (StartQuantity holds what is installed).
            OrderItem oi = new OrderItem(OrderId = orderId, PricebookEntryId = e.Id, Product2Id = e.Product2Id, Quantity = ca == 'noChange' ? 0 : parent.Quantity, UnitPrice = 0,
                OrderActionId = (actions.containsKey(ca) ? actions.get(ca) : actions.get(ca + '/c')).Id,
                Description = ('AgenticTelco item ' + m.get('id') + '.' + k + COMPONENT_MARK + m.get('id') + marker(ca, (String) specs[pi].get('basis'))).left(255));
            if (ca != 'add') oi.StartQuantity = 1;
            if (e.ProductSellingModel != null && e.ProductSellingModel.SellingModelType != 'OneTime') {
                oi.ServiceDate = parent.ServiceDate == null ? Date.today() : parent.ServiceDate;
                oi.PeriodBoundary = 'Anniversary';
                if (e.ProductSellingModel.SellingModelType == 'TermDefined') oi.EndDate = parent.EndDate == null ? Date.today().addMonths(12).addDays(-1) : parent.EndDate;
            }
            lines.add(oi);
            used.add(c);
        }
        if (lines.isEmpty()) return;
        insert lines;
        List<OrderItemRelationship> rels = new List<OrderItemRelationship>();
        for (Integer i = 0; i < lines.size(); i++) {
            rels.add(new OrderItemRelationship(MainOrderItemId = parents[idx.get(used[i].ParentProductId)].Id, AssociatedOrderItemId = lines[i].Id,
                ProductRelationshipTypeId = used[i].ProductRelationshipTypeId, ProductRelatedComponentId = used[i].Id,
                AssociatedOrderItemPricing = 'IncludedInBundlePrice', AssociatedQuantScaleMethod = 'Proportional'));
        }
        insert rels;
    }

    static PricebookEntry sameModel(List<PricebookEntry> es, String model) {
        if (es == null || es.isEmpty()) return null;
        for (PricebookEntry e : es) if (e.ProductSellingModel != null && e.ProductSellingModel.SellingModelType == model) return e;
        for (PricebookEntry e : es) if (e.ProductSellingModel != null && e.ProductSellingModel.SellingModelType == 'Evergreen') return e;
        return es[0];
    }

    public static Boolean isComponentLine(String description) {
        return description != null && description.contains(COMPONENT_MARK);
    }

    static String actionOf(Map<String, Object> m) {
        String a = AgenticTelco_Tmf.str(m.get('action'));
        return String.isBlank(a) ? 'add' : a;
    }

    /** Request item id this add item replaces (productOrderItemRelationship relationshipType 'replaces'), or null. */
    @TestVisible static String replacesOf(Map<String, Object> m) {
        for (Object r : AgenticTelco_Tmf.toList(m.get('productOrderItemRelationship'))) {
            Map<String, Object> x = AgenticTelco_Tmf.toMap(r);
            if (AgenticTelco_Tmf.str(x.get('relationshipType')) == 'replaces') return String.valueOf(x.get('id'));
        }
        return null;
    }

    /** One OrderAction per action and link: '<action>' or '<action>/up' (delete replaced by an add, or add replacing a delete). */
    static String actionKey(Map<String, Object> m, Map<String, String> replacedBy) {
        String a = actionOf(m);
        Boolean up = (a == 'add' && replacesOf(m) != null) || (a == 'delete' && replacedBy.containsKey(String.valueOf(m.get('id'))));
        return a + (up ? '/up' : '');
    }

    public static String replacesId(String description) {
        return description == null || !description.contains(REPLACES_MARK) ? null : description.substringAfter(REPLACES_MARK).substringBefore(' ');
    }

    static List<Asset> findAsset(String pid, Id accountId) {
        try {
            return [SELECT Id, Product2Id, UsageEndDate FROM Asset WHERE Id = :pid AND AccountId = :accountId AND Name LIKE 'AgenticTelco%' LIMIT 1];
        } catch (Exception e) {
            return new List<Asset>();
        }
    }

    static String marker(Map<String, Object> m) { return marker(actionOf(m), AgenticTelco_Tmf.str(AgenticTelco_Tmf.toMap(m.get('product')).get('id'))); }

    /** Records the action and the installed product (Asset id) it applies to on the OrderItem description. */
    static String marker(String act, String productId) {
        if (act == 'add' || productId == null) return '';
        return (act == 'noChange' ? NOCHANGE_MARK : act == 'delete' ? DELETE_MARK : MODIFY_MARK) + productId;
    }

    public static String itemAction(String description) {
        if (description == null) return 'add';
        return description.contains(MODIFY_MARK) ? 'modify' : description.contains(NOCHANGE_MARK) ? 'noChange' : description.contains(DELETE_MARK) ? 'delete' : 'add';
    }

    /**
     * Action code of each required component line of a modify item, from the installed base (TMF637): the installed asset
     * the item modifies (or, for an add item that replaces a deleted one, the deleted product) and the speeds of the old and
     * new bundle. Keyed by '<parent index>><child product id>'. Add items with no installed product are left out (their
     * components are add, like the bundle).
     */
    /** The OrderAction for a component line's own code (TMF622 noChange / modify / add). */
    @TestVisible static OrderAction newAction(Id orderId, String a) {
        if (a == 'noChange') return new OrderAction(OrderId = orderId, Type = 'No Change');
        if (a == 'modify') return new OrderAction(OrderId = orderId, Type = 'Amend', Subtype = 'UpgradeTo');
        return new OrderAction(OrderId = orderId, Type = 'Add');
    }

    @TestVisible static Map<String, String> componentActions(List<OrderItem> parents, List<Map<String, Object>> specs, Set<Id> childIds, Id accountId) {
        Map<String, String> out = new Map<String, String>();
        Map<Id, String> childCode = new Map<Id, String>();
        for (Product2 p : [SELECT Id, ProductCode FROM Product2 WHERE Id IN :childIds]) childCode.put(p.Id, p.ProductCode);
        for (Integer i = 0; i < parents.size(); i++) {
            Map<String, Object> m = (Map<String, Object>) specs[i].get('m');
            String basis = (String) specs[i].get('basis');
            if (actionOf(m) == 'delete' || basis == null) continue;
            Id oldProduct;
            for (Asset a : findAsset(basis, accountId)) oldProduct = a.Product2Id;
            Map<Id, Integer> sp = AgenticTelco_OrchestrationStep.speeds(new Set<Id>{ parents[i].Product2Id, oldProduct });
            for (Id child : childIds) {
                String code = childCode.get(child) == 'AT-ACCESS-LINE' ? AgenticTelco_OrchestrationStep.CFS_ACCESS
                            : childCode.get(child) == 'AT-ROUTER-WIFI6' ? AgenticTelco_OrchestrationStep.CFS_ROUTER : null;
                if (code == null) continue;
                out.put(i + '>' + child, AgenticTelco_OrchestrationStep.decideFor(code, null, oldProduct != null,
                    oldProduct == null ? null : sp.get(oldProduct), sp.get(parents[i].Product2Id))[0]);
            }
        }
        return out;
    }

    public static Map<String, Object> itemProduct(String description) {
        if (itemAction(description) == 'add') return null;
        String a = itemAction(description);
        String pid = description.substringAfter(a == 'modify' ? MODIFY_MARK : a == 'delete' ? DELETE_MARK : NOCHANGE_MARK).substringBefore(' ');
        return AgenticTelco_Tmf.ref(pid, null, 'Product', '/services/data/v68.0/connect/comms/productinventorymanagement/v5/productinventory/' + pid);
    }

    public class TmfException extends Exception {}
}
