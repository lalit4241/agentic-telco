package agentictelco.upgrade_test

import rego.v1

import data.agentictelco.upgrade

ctx := {
	"requester": {"name": "Sam", "authorisedContact": true, "role": "Decision Maker"},
	"currentBroadband": {"product": "AgenticTelco Fibre 150", "downloadSpeedMbps": 150},
	"contractMonthsLeft": {"value": 10},
	"availableAtSite": {"value": ["AgenticTelco Fibre 500", "AgenticTelco Fibre 900"]},
	"overdueBalance": {"value": false},
	"offerings": [
		{"id": "fibre-900", "name": "AgenticTelco Fibre 900", "downloadSpeedMbps": 900},
		{"id": "fibre-1600", "name": "AgenticTelco Fibre 1600", "downloadSpeedMbps": 1600},
		{"id": "fibre-150", "name": "AgenticTelco Fibre 150", "downloadSpeedMbps": 150},
	],
}

inp(c, to) := {"mode": "advisory", "context": c, "proposal": {"to": to}}

test_happy_path_allowed if {
	upgrade.allow with input as inp(ctx, "fibre-900")
}

test_binding_mode_same_answer if {
	upgrade.allow with input as object.union(inp(ctx, "fibre-900"), {"mode": "binding"})
}

test_business_user_not_authorised if {
	c := object.union(ctx, {"requester": {"name": "Alex", "authorisedContact": false, "role": "Business User"}})
	d := upgrade.decision with input as inp(c, "fibre-900")
	not d.allow
	d.deny == ["not_authorised"]
}

test_overdue_balance_denied if {
	c := object.union(ctx, {"overdueBalance": {"value": true}})
	d := upgrade.decision with input as inp(c, "fibre-900")
	d.deny == ["overdue_balance"]
	d.reasons == ["There is an overdue balance on the business account."]
}

test_not_available_at_site if {
	d := upgrade.decision with input as inp(ctx, "fibre-1600")
	d.deny == ["not_available_at_site"]
}

test_same_speed_mid_contract_denied if {
	c := object.union(ctx, {"availableAtSite": {"value": ["AgenticTelco Fibre 150"]}})
	d := upgrade.decision with input as inp(c, "fibre-150")
	d.deny == ["downgrade_mid_contract"]
}

test_same_speed_out_of_contract_allowed if {
	c := object.union(ctx, {"contractMonthsLeft": {"value": 0}, "availableAtSite": {"value": ["AgenticTelco Fibre 150"]}})
	upgrade.allow with input as inp(c, "fibre-150")
}

test_unknown_offering_denied if {
	not upgrade.allow with input as inp(ctx, "fibre-9999")
}

test_missing_requester_denied if {
	d := upgrade.decision with input as inp(object.remove(ctx, ["requester"]), "fibre-900")
	"not_authorised" in d.deny
}

test_multiple_reasons_sorted if {
	c := object.union(ctx, {"overdueBalance": {"value": true}, "requester": {"authorisedContact": false}})
	d := upgrade.decision with input as inp(c, "fibre-900")
	d.deny == ["not_authorised", "overdue_balance"]
}
