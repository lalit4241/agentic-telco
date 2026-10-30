/**
 * TMF671 Promotion Management (v4 shapes, read-only) – TMF facade within Salesforce (Apex).
 * The native Direct Access TMF671 resource exists on sfcomms but returns HTTP 500 on this org's existing promotion data
 * ("rewardDetails is null"), so the demo reads promotions here.  GET /agentictelco/tmf671/promotion[/{id}]
 */
@RestResource(urlMapping='/agentictelco/tmf671/*')
global with sharing class AgenticTelco_TMF671 {
    @HttpGet
    global static void doGet() {
        List<String> seg = AgenticTelco_Tmf.segments();
        String id = seg.size() > 1 ? seg[1] : null;
        List<Promotion> ps = id != null
            ? [SELECT Id, Name, DisplayName, Description, IsActive, StartDateTime, EndDateTime, PromotionCode, ProductCatalogId FROM Promotion WHERE Id = :id]
            : [SELECT Id, Name, DisplayName, Description, IsActive, StartDateTime, EndDateTime, PromotionCode, ProductCatalogId FROM Promotion ORDER BY Name LIMIT 100];
        if (id != null && ps.isEmpty()) { AgenticTelco_Tmf.error(404, 'NOT_FOUND', 'promotion ' + id); return; }
        List<Object> out = new List<Object>();
        for (Promotion p : ps) {
            out.add(new Map<String, Object>{
                'id' => p.Id, 'href' => AgenticTelco_Tmf.href('tmf671', 'promotion', p.Id), 'name' => p.Name,
                'description' => p.Description == null ? p.DisplayName : p.Description,
                'lifecycleStatus' => p.IsActive ? 'active' : 'inactive', 'x-promotionCode' => p.PromotionCode,
                'validFor' => new Map<String, Object>{ 'startDateTime' => p.StartDateTime, 'endDateTime' => p.EndDateTime },
                'x-runtime' => AgenticTelco_Tmf.SOR_LABEL, '@type' => 'Promotion' });
        }
        AgenticTelco_Tmf.respond(200, id == null ? (Object) out : out[0]);
    }
}
