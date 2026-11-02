/** Callout implementation of AgenticTelco_NetworkOrderAdapter: TMF641 JSON over HTTP through a named credential (the only network API Salesforce calls). */
public with sharing class AgenticTelco_CalloutNetworkAdapter implements AgenticTelco_NetworkOrderAdapter {
    final String nc;
    public AgenticTelco_CalloutNetworkAdapter(String namedCredential) {
        if (String.isBlank(namedCredential)) throw new AgenticTelco_NetworkAdapters.AdapterException('Callout mode needs Named_Credential__c');
        nc = namedCredential;
    }
    public String mode() { return AgenticTelco_NetworkAdapters.CALLOUT; }
    public String submitServiceOrder(String body) { return send('POST', '/tmf-api/serviceOrdering/v4/serviceOrder', body); }
    public String getServiceOrder(String id) { return send('GET', '/tmf-api/serviceOrdering/v4/serviceOrder/' + EncodingUtil.urlEncode(id, 'UTF-8'), null); }

    String send(String method, String path, String body) {
        HttpRequest r = new HttpRequest();
        r.setEndpoint('callout:' + nc + path);
        r.setMethod(method);
        r.setTimeout(60000);
        r.setHeader('Accept', 'application/json');
        if (body != null) { r.setHeader('Content-Type', 'application/json'); r.setBody(body); }
        HttpResponse res = new Http().send(r);
        if (res.getStatusCode() >= 300) {
            throw new AgenticTelco_NetworkAdapters.AdapterException(method + ' ' + path + ' -> ' + res.getStatusCode() + ' ' + String.valueOf(res.getBody()).left(300));
        }
        return res.getBody();
    }
}
