/** Picks the AgenticTelco_NetworkOrderAdapter implementation from custom metadata (AgenticTelco_Network_Adapter__mdt.Default). */
public with sharing class AgenticTelco_NetworkAdapters {
    public static final String MOCK = 'Mock';
    public static final String CALLOUT = 'Callout';
    @TestVisible static AgenticTelco_Network_Adapter__mdt testConfig;

    public static AgenticTelco_Network_Adapter__mdt config() {
        if (testConfig != null) return testConfig;
        return AgenticTelco_Network_Adapter__mdt.getInstance('Default');
    }

    public static String mode() {
        AgenticTelco_Network_Adapter__mdt c = config();
        return c == null || c.Mode__c != CALLOUT ? MOCK : CALLOUT;
    }

    public static String namedCredential() {
        AgenticTelco_Network_Adapter__mdt c = config();
        return c == null ? null : c.Named_Credential__c;
    }

    public static AgenticTelco_NetworkOrderAdapter current() {
        if (mode() == CALLOUT) return new AgenticTelco_CalloutNetworkAdapter(namedCredential());
        return new AgenticTelco_MockNetworkAdapter();
    }

    public class AdapterException extends Exception {}
}
