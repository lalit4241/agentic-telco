/**
 * TMF632 Party Management (v5 resource shapes) – TMF facade within Salesforce (Apex).
 * Returns an organization with its contacts as relatedParty, each with the role they hold on the account
 * (AccountContactRole). Mapping only: which role may order is decided outside Salesforce (semantic model + OPA).
 *   GET /agentictelco/tmf632/organization/{accountId}   ?relatedParty.role=<role>   AgenticTelco accounts only
 */
@RestResource(urlMapping='/agentictelco/tmf632/*')
global with sharing class AgenticTelco_TMF632 {
    @HttpGet
    global static void doGet() {
        List<String> seg = AgenticTelco_Tmf.segments();
        if (seg.size() < 2 || seg[0] != 'organization') { AgenticTelco_Tmf.error(400, 'MISSING_ID', 'GET needs /organization/{id}'); return; }
        String id = seg[1];
        List<Account> a;
        try {
            a = [SELECT Id, Name FROM Account WHERE Id = :id AND Name LIKE 'AgenticTelco%' LIMIT 1];
        } catch (Exception e) {
            a = new List<Account>();
        }
        if (a.isEmpty()) { AgenticTelco_Tmf.error(404, 'NOT_FOUND', 'organization ' + id); return; }
        String role = AgenticTelco_Tmf.param('relatedParty.role');
        List<Object> parties = new List<Object>();
        for (AccountContactRole r : [SELECT Id, ContactId, Contact.Name, Contact.FirstName, Contact.LastName, Role, IsPrimary
                                     FROM AccountContactRole WHERE AccountId = :a[0].Id ORDER BY Contact.Name]) {
            if (role != null && r.Role != role) continue;
            parties.add(new Map<String, Object>{ 'id' => r.ContactId, 'name' => r.Contact.Name, 'role' => r.Role,
                'x-givenName' => r.Contact.FirstName, 'x-isPrimary' => r.IsPrimary, '@referredType' => 'Individual', '@type' => 'RelatedPartyRefOrPartyRoleRef' });
        }
        AgenticTelco_Tmf.respond(200, new Map<String, Object>{
            'id' => a[0].Id, 'href' => AgenticTelco_Tmf.href('tmf632', 'organization', a[0].Id), 'name' => a[0].Name,
            'tradingName' => a[0].Name.replace('AgenticTelco – ', ''), 'relatedParty' => parties,
            'x-runtime' => AgenticTelco_Tmf.SOR_LABEL, '@type' => 'Organization' });
    }
}
