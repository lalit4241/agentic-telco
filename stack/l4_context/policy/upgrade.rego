# L4 · Enterprise Context – operator-owned cross-domain policy for broadband upgrades.
# Lives in OUR layer (OPA), not in Salesforce. Values come from data.zg.policy, edited live via /zg/context/v1/policy.
package zg.upgrade

import rego.v1

default allow := false

default credit_ok := false

default consent_ok := false

default network_ok := false

default ai_ok := false

p := data.zg.policy

credit_ok if input.context.credit.score >= p.creditMin

consent_ok if {
	input.context.consent.granted
	p.consentRule == "any"
}

consent_ok if {
	input.context.consent.granted
	p.consentRule == "explicit-digital"
	input.context.consent.channel == "digital"
}

network_ok if input.context.network.utilisation <= p.networkMaxUtilisation

ai_ok if not input.decidedByModel

ai_ok if {
	input.decidedByModel
	p.aiGuardrail.llmMayDecide
}

allow if {
	credit_ok
	consent_ok
	network_ok
	ai_ok
}

checks := [
	{"id": "credit", "domain": "Finance / risk", "pass": credit_ok, "detail": sprintf("score %v vs creditMin %v", [input.context.credit.score, p.creditMin])},
	{"id": "consent", "domain": "Privacy / regulatory", "pass": consent_ok, "detail": sprintf("channel %v vs rule %v", [input.context.consent.channel, p.consentRule])},
	{"id": "network", "domain": "Network safety", "pass": network_ok, "detail": sprintf("utilisation %v vs max %v", [input.context.network.utilisation, p.networkMaxUtilisation])},
	{"id": "ai-guardrail", "domain": "AI governance", "pass": ai_ok, "detail": "the eligibility decision is made by policy, never by the model"},
]

reasons contains c.id if {
	some c in checks
	not c.pass
}

decision := {"allow": allow, "checks": checks, "reasons": reasons, "policyVersion": p.version}
