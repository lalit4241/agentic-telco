/**
 * Setup on an empty catalogue (no SeeAllData): creates the CFS products, the CFS classification and speed attribute,
 * the built-in decomposition rules, the 7-step group with dependencies, the jeopardy rule and the scenario, then a
 * second run creates nothing (idempotent).
 */
@IsTest
private class AgenticTelco_OrchestrationSetupTest {
    @IsTest static void createsEverythingOnceThenNothing() {
        insert new AttributeDefinition(Name = 'AgenticTelco Download Speed Test', Label = 'AgenticTelco Download Speed Test',
            Code = AgenticTelco_OrchestrationStep.SPEED_CODE, DataType = 'Text', IsActive = true);
        insert new List<Product2>{
            new Product2(Name = 'AgenticTelco Fibre 900 Test', ProductCode = 'AT-FIBRE-900', IsActive = true),
            new Product2(Name = 'AgenticTelco Access Line Test', ProductCode = 'AT-ACCESS-LINE', IsActive = true),
            new Product2(Name = 'AgenticTelco Router Test', ProductCode = 'AT-ROUTER-WIFI6', IsActive = true),
            new Product2(Name = 'AgenticTelco Install Test', ProductCode = 'AT-INSTALL', IsActive = true) };
        Test.startTest();
        String first = AgenticTelco_OrchestrationSetup.run();
        String again = AgenticTelco_OrchestrationSetup.run();
        Test.stopTest();
        System.assert(first.contains('CFS products created: 4') && first.contains('decomposition rules created: 4') && first.contains('step definitions created: 7')
            && first.contains('CFS classification created') && first.contains('CFS speed attribute created') && first.contains('jeopardy rule created')
            && first.contains('scenario created') && first.contains('step group created'), first);
        System.assert(again.contains('CFS products created: 0') && again.contains('decomposition rules created: 0') && again.contains('step definitions created: 0')
            && again.contains('step dependencies created: 0') && !again.contains('scenario created'), again);
        System.assertEquals(6, [SELECT COUNT() FROM FulfillmentStepDependencyDef WHERE FulfillmentStepDefinition.StepDefinitionGroup.Name = :AgenticTelco_Orchestration.GROUP_NAME]);
    }
}
