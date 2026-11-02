# Decision: how the installed product is recorded (assetisation)

Status: decided 2 Nov 2026, route A (Lalit: "fix OOTB if you can, otherwise custom Apex"). Read-only findings from the
`sfcomms` org, 2 Nov 2026 (UK time, GMT).

## What runs today

The installed product (TMF637) is written once, by the AgenticTelco plan step "6. Record the installed product (TMF637)"
(`AgenticTelco_Assetisation`, route `CUSTOM_STEP` in `AgenticTelco_Fulfilment_Setting__mdt`). The L5 workflow only reads it
back (TMF637 GET). The Dev View shows only "Assetisation done (TMF637)", with no route named.

## Why the built-in assetisation is not used

Salesforce still runs its own OrderToAsset after the plan completes, and it fails on every AgenticTelco order, so the
order shows `OrchestrationSbmsStatus = AssetizationFailed` and `SalesTransactionFulfillReq.AssetizationStatus = Failed`.
It writes nothing.

| Order | Error log | Category / code | Exact message |
|---|---|---|---|
| 00000176 (`801QH00002LmDh4YAF`) | RTE-000000034, 22:17 | OrderToAsset / AssetizationFailed | INVALID_INPUT (http 403): "We couldn't process the request. The order must have a related Application Usage Assignment with an Application Usage Type of RevenueLifecycleManagement or SubscriptionManagement." |
| 00000177 (`801QH00002LmZPlYAN`) | RTE-000000035, 23:30 | OrderToAsset / AssetizationFailed | same message |

Both orders do have a `SubscriptionManagement` AppUsageAssignment (176: `0j8QH000005dPenYAE`, 177: `0j8QH000005dSBFYA2`),
created by the TMF622 facade while the order is Draft. Neither has a `RevenueLifecycleManagement` one. The built-in step
rejects the order at this usage check, so it never reaches the asset field mapping. The same error is logged for 00000175
and one earlier order (4 in total; the only other entry in `RevenueTransactionErrorLog` is a ConfiguratorAPI one).

## What was checked

- **Usage record (RLM config):** `AppUsageAssignment` per order, as above. The SubscriptionManagement record is there on
  purpose: the org's existing record-triggered flow "Custom Assetize Order" (v3) looks only for SubscriptionManagement and,
  if it is missing, calls the create-or-update-asset action itself (see `docs/api/org-capabilities.md`).
- **Asset field mapping and context:** not reached by the built-in step on 176/177 (it stops at the usage check). In an
  earlier build-time test of the `BUILT_IN` route, the platform also rejected the test data with "You can't specify EndDate
  for one-time order products" (the router line is one-time; the bundle carries the contract end date).
- **Per-order or per-product switch (read-only):** none found. The OrderToAsset run after plan completion is platform
  behaviour (Dynamic Revenue Orchestrator); `SalesTransactionFulfillReq` only reports its status, and no Order, OrderItem,
  Product2 or AgenticTelco-scoped field or setting turns it off. Stopping it cleanly needs org-level revenue/orchestration
  configuration, which is outside the AgenticTelco_ scope.

## Why route B (built-in) needs changes outside the rules

- The order would need a RevenueLifecycleManagement usage record. Then "Custom Assetize Order" (which keys on
  SubscriptionManagement) would have to change, or it would assetise a second time: an edit to an existing flow.
- The asset mapping and context for bundles, one-time lines and the delete+add upgrade (ending Fibre 150, carrying the
  contract end, linking Upgrade) are RLM configuration, not AgenticTelco_ metadata.
- Both are non-AgenticTelco_ org changes, which need Lalit's approval.

TODO: Fix OOTB assetisation later (needs Custom Assetize Order flow and RLM changes; Lalit to approve).
