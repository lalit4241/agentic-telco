/**
 * Idempotent setup of the AgenticTelco records for Salesforce order orchestration (new AgenticTelco_ records only;
 * nothing existing is edited):
 *   - CFS technical products (customer facing services) and the built-in decomposition rules from the commercial products
 *       AT-FIBRE-* (bundle)   -> AgenticTelco CFS Fibre Broadband
 *       AT-ACCESS-LINE        -> AgenticTelco CFS Fibre Access
 *       AT-ROUTER-WIFI6       -> AgenticTelco CFS Managed Router
 *       AT-INSTALL            -> AgenticTelco CFS Installation (only when installation is on the order)
 *   - step group 'AgenticTelco Fibre Upgrade Fulfilment': 7 plan-scope steps chained by dependencies, step 4 a milestone
 *     (point of no return), a jeopardy rule on the activation wait, and a fulfilment scenario (Add;Amend) for the CFS_NAMES.
 * Run: sf apex run -o sfcomms  with  System.debug(AgenticTelco_OrchestrationSetup.run());
 */
public with sharing class AgenticTelco_OrchestrationSetup {
    public static final Map<String, String> CFS_NAMES = new Map<String, String>{
        AgenticTelco_OrchestrationStep.CFS_BB => 'AgenticTelco CFS Fibre Broadband',
        AgenticTelco_OrchestrationStep.CFS_ACCESS => 'AgenticTelco CFS Fibre Access',
        AgenticTelco_OrchestrationStep.CFS_ROUTER => 'AgenticTelco CFS Managed Router',
        AgenticTelco_OrchestrationStep.CFS_INSTALL => 'AgenticTelco CFS Installation' };
    public static final String CLS_CODE = 'AgenticTelco_CLS_CFS_BB';
    public static final String SCENARIO = 'AgenticTelco Fibre Upgrade Scenario';

    public static String run() {
        List<String> log = new List<String>();
        // CFS products
        Map<String, Product2> cfsProducts = new Map<String, Product2>();
        for (Product2 p : [SELECT Id, ProductCode FROM Product2 WHERE ProductCode IN :CFS_NAMES.keySet()]) cfsProducts.put(p.ProductCode, p);
        Id clsId = speedClassification(log);
        List<Product2> newCfs = new List<Product2>();
        for (String code : CFS_NAMES.keySet()) if (!cfsProducts.containsKey(code)) {
            Product2 p = new Product2(Name = CFS_NAMES.get(code), ProductCode = code, IsActive = true, IsAssetizable = false,
                Description = 'AgenticTelco customer facing service (CFS) technical product, used by Salesforce order orchestration');
            if (code == AgenticTelco_OrchestrationStep.CFS_BB && clsId != null) p.BasedOnId = clsId;
            newCfs.add(p);
            cfsProducts.put(code, p);
        }
        insert newCfs;
        log.add('CFS products created: ' + newCfs.size());
        speedAttribute(cfsProducts.get(AgenticTelco_OrchestrationStep.CFS_BB).Id, clsId, log);

        // decomposition rules from the commercial products
        Map<String, String> src = new Map<String, String>();   // commercial ProductCode -> CFS code
        Map<Id, String> srcName = new Map<Id, String>();
        List<Product2> commercial = [SELECT Id, Name, ProductCode FROM Product2 WHERE ProductCode LIKE 'AT-FIBRE-%' OR ProductCode IN ('AT-ACCESS-LINE', 'AT-ROUTER-WIFI6', 'AT-INSTALL')];
        Set<String> haveRule = new Set<String>();
        for (ProductFulfillmentDecompRule r : [SELECT SourceProductId, DestinationProductId FROM ProductFulfillmentDecompRule WHERE Name LIKE 'AgenticTelco%']) haveRule.add(r.SourceProductId + '>' + r.DestinationProductId);
        List<ProductFulfillmentDecompRule> rules = new List<ProductFulfillmentDecompRule>();
        for (Product2 c : commercial) {
            String code = c.ProductCode.startsWith('AT-FIBRE-') ? AgenticTelco_OrchestrationStep.CFS_BB
                        : c.ProductCode == 'AT-ACCESS-LINE' ? AgenticTelco_OrchestrationStep.CFS_ACCESS
                        : c.ProductCode == 'AT-ROUTER-WIFI6' ? AgenticTelco_OrchestrationStep.CFS_ROUTER : AgenticTelco_OrchestrationStep.CFS_INSTALL;
            Id dest = cfsProducts.get(code).Id;
            if (haveRule.contains(c.Id + '>' + dest)) continue;
            rules.add(new ProductFulfillmentDecompRule(Name = ('AgenticTelco ' + c.ProductCode + ' to ' + CFS_NAMES.get(code).removeStart('AgenticTelco ')).left(80),
                SourceProductId = c.Id, DestinationProductId = dest, Priority = code == AgenticTelco_OrchestrationStep.CFS_BB ? 1 : code == AgenticTelco_OrchestrationStep.CFS_ACCESS ? 2 : code == AgenticTelco_OrchestrationStep.CFS_ROUTER ? 3 : 4));
        }
        insert rules;
        log.add('decomposition rules created: ' + rules.size());

        // step group, steps, dependencies
        List<FulfillmentStepDefinitionGroup> gs = [SELECT Id FROM FulfillmentStepDefinitionGroup WHERE Name = :AgenticTelco_Orchestration.GROUP_NAME LIMIT 1];
        FulfillmentStepDefinitionGroup g;
        if (gs.isEmpty()) { g = new FulfillmentStepDefinitionGroup(Name = AgenticTelco_Orchestration.GROUP_NAME, UsageType = 'Fulfillment'); insert g; log.add('step group created'); }
        else g = gs[0];
        Map<String, FulfillmentStepDefinition> defs = new Map<String, FulfillmentStepDefinition>();
        List<FulfillmentStepDefinition> renamed = new List<FulfillmentStepDefinition>();
        Map<String, String> nameByFlow = new Map<String, String>();
        for (String k : AgenticTelco_Orchestration.STEP_FLOWS.keySet()) nameByFlow.put(AgenticTelco_Orchestration.STEP_FLOWS.get(k), AgenticTelco_Orchestration.stepName(k));
        for (FulfillmentStepDefinition d : [SELECT Id, Name, FlowDefinitionName FROM FulfillmentStepDefinition WHERE StepDefinitionGroupId = :g.Id]) {
            String want = nameByFlow.get(d.FlowDefinitionName);
            if (want != null && want != d.Name) { d.Name = want; renamed.add(d); }   // our own steps, renamed when a step's job changes
            defs.put(d.Name, d);
        }
        update renamed;
        if (!renamed.isEmpty()) log.add('step definitions renamed: ' + renamed.size());
        List<FulfillmentStepDefinition> newDefs = new List<FulfillmentStepDefinition>();
        for (String k : AgenticTelco_Orchestration.KINDS) {
            String n = AgenticTelco_Orchestration.stepName(k);
            if (defs.containsKey(n)) continue;
            FulfillmentStepDefinition d = new FulfillmentStepDefinition(Name = n, StepDefinitionGroupId = g.Id, Scope = 'Plan', UsageType = 'Fulfillment',
                StepType = k == 'PONR' ? 'Milestone' : 'AutoTask', FlowDefinitionName = AgenticTelco_Orchestration.STEP_FLOWS.get(k),
                Description = k == 'PONR' ? 'Point of no return: after network activation the order can no longer be cancelled' : 'AgenticTelco step ' + k);
            newDefs.add(d);
            defs.put(n, d);
        }
        insert newDefs;
        log.add('step definitions created: ' + newDefs.size());
        Set<String> haveDep = new Set<String>();
        for (FulfillmentStepDependencyDef d : [SELECT FulfillmentStepDefinitionId, DependsOnStepDefinitionId FROM FulfillmentStepDependencyDef WHERE FulfillmentStepDefinition.StepDefinitionGroupId = :g.Id]) {
            haveDep.add(d.FulfillmentStepDefinitionId + '>' + d.DependsOnStepDefinitionId);
        }
        List<FulfillmentStepDependencyDef> deps = new List<FulfillmentStepDependencyDef>();
        for (Integer i = 1; i < AgenticTelco_Orchestration.KINDS.size(); i++) {
            FulfillmentStepDefinition cur = defs.get(AgenticTelco_Orchestration.stepName(AgenticTelco_Orchestration.KINDS[i]));
            FulfillmentStepDefinition prev = defs.get(AgenticTelco_Orchestration.stepName(AgenticTelco_Orchestration.KINDS[i - 1]));
            if (haveDep.contains(cur.Id + '>' + prev.Id)) continue;
            deps.add(new FulfillmentStepDependencyDef(Name = ('AgenticTelco step ' + (i + 1) + ' after step ' + i), FulfillmentStepDefinitionId = cur.Id,
                DependsOnStepDefinitionId = prev.Id, DependencyScope = 'Plan'));
        }
        insert deps;
        log.add('step dependencies created: ' + deps.size());

        // jeopardy rule on the activation wait
        String awaitFlow = AgenticTelco_Orchestration.STEP_FLOWS.get('AWAIT');
        if ([SELECT COUNT() FROM FulfillmentStepJeopardyRule WHERE FlowDefinition = :awaitFlow] == 0) {
            insert new FulfillmentStepJeopardyRule(StepType = 'AutoTask', FlowDefinition = awaitFlow, EstimatedDuration = 2, EstimatedDurationUnit = 'Days',
                JeopardyThreshold = 1, JeopardyThresholdUnit = 'Days');
            log.add('jeopardy rule created');
        }
        // scenario: the CFS Fibre Broadband (one per order) brings in the step group
        if ([SELECT COUNT() FROM ProductFulfillmentScenario WHERE Name = :SCENARIO] == 0) {
            insert new ProductFulfillmentScenario(Name = SCENARIO, FulfillmentStepDefnGroupId = g.Id, ProductId = cfsProducts.get(AgenticTelco_OrchestrationStep.CFS_BB).Id,
                Action = 'Add;Amend', UsageType = 'Fulfillment');
            log.add('scenario created');
        }
        return String.join(log, '; ');
    }

    static Id speedClassification(List<String> log) {
        for (ProductClassification c : [SELECT Id FROM ProductClassification WHERE Code = :CLS_CODE LIMIT 1]) return c.Id;
        List<AttributeDefinition> ad = [SELECT Id FROM AttributeDefinition WHERE Code = :AgenticTelco_OrchestrationStep.SPEED_CODE LIMIT 1];
        if (ad.isEmpty()) return null;
        ProductClassification c = new ProductClassification(Name = 'AgenticTelco CFS Fibre Broadband', Code = CLS_CODE, Status = 'Active');
        insert c;
        insert new ProductClassificationAttr(Name = 'Download speed (Mbps)', ProductClassificationId = c.Id, AttributeDefinitionId = ad[0].Id, Status = 'Active');
        log.add('CFS classification created');
        return c.Id;
    }

    static void speedAttribute(Id productId, Id clsId, List<String> log) {
        if (clsId == null || [SELECT COUNT() FROM ProductAttributeDefinition WHERE Product2Id = :productId] > 0) return;
        ProductClassificationAttr pca = [SELECT Id, AttributeDefinitionId FROM ProductClassificationAttr WHERE ProductClassificationId = :clsId LIMIT 1];
        insert new ProductAttributeDefinition(Name = 'Download speed (Mbps)', Product2Id = productId, AttributeDefinitionId = pca.AttributeDefinitionId,
            ProductClassificationAttributeId = pca.Id, Status = 'Active');
        log.add('CFS speed attribute created');
    }
}
