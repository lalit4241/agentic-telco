/**
 * The network order adapter as seen from Salesforce order orchestration. Salesforce makes ONE outbound network
 * interaction: TMF641 Service Ordering (POST the service order, then GET its state). Reservation, resource inventory and
 * service inventory are the network's own work behind TMF641 (they come back as data in the TMF641 response), and
 * Salesforce only updates its own product inventory (TMF637, by the L5 workflow). Every orchestration step talks to the
 * network through this interface only; AgenticTelco_NetworkAdapters picks the implementation from the
 * AgenticTelco_Network_Adapter__mdt 'Default' record: Mock (AgenticTelco_MockNetworkAdapter, simulated inside Salesforce
 * for this demo) or Callout (AgenticTelco_CalloutNetworkAdapter, HTTP through a named credential).
 */
public interface AgenticTelco_NetworkOrderAdapter {
    /** 'Mock' or 'Callout'. */
    String mode();
    /** TMF641 Service Ordering: POST /tmf-api/serviceOrdering/v4/serviceOrder */
    String submitServiceOrder(String serviceOrderJson);
    /** TMF641 Service Ordering: GET /tmf-api/serviceOrdering/v4/serviceOrder/{id} */
    String getServiceOrder(String serviceOrderId);
}
