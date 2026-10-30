# AgenticTelco MVP · L4 policy: one rule, run twice (advisory by the context service, binding by the L5 workflow).
# The input carries mode: advisory | binding for the audit only; the rule is identical. Versioned, tested with `opa test`.
package agentictelco.upgrade

import rego.v1

version := "mvp-2026-10-30.1"

default allow := false

allow if count(deny) == 0

deny contains "not_authorised" if not input.context.requester.authorisedContact

deny contains "overdue_balance" if input.context.overdueBalance.value

deny contains "not_available_at_site" if not available

deny contains "downgrade_mid_contract" if {
	input.context.contractMonthsLeft.value > 0
	target.downloadSpeedMbps <= input.context.currentBroadband.downloadSpeedMbps
}

available if {
	some n in input.context.availableAtSite.value
	n == target.name
}

target := o if {
	some o in input.context.offerings
	o.id == input.proposal.to
}

# Plain-English reasons, shown on screen and given to the agent to explain (wording, not rules).
reason := {
	"not_authorised": "Only an authorised contact (Decision Maker) can order for this business.",
	"overdue_balance": "There is an overdue balance on the business account.",
	"not_available_at_site": "That product is not available at this site.",
	"downgrade_mid_contract": "Mid-contract changes must be upgrades.",
}

decision := {
	"allow": allow,
	"deny": sort([d | some d in deny]),
	"reasons": [reason[d] | some d in sort([x | some x in deny])],
	"mode": input.mode,
	"policyVersion": version,
}
