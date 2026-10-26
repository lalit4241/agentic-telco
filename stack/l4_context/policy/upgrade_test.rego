package zg.upgrade_test

import data.zg.upgrade
import rego.v1

pol := {"version": 1, "creditMin": 620, "consentRule": "explicit-digital", "networkMaxUtilisation": 0.85, "aiGuardrail": {"llmMayDecide": false}}
ctx(score, ch, util) := {"credit": {"score": score}, "consent": {"granted": true, "channel": ch}, "network": {"utilisation": util}}

test_blocked_on_credit if {
	d := upgrade.decision with input as {"context": ctx(598, "digital", 0.6)} with data.zg.policy as pol
	not d.allow
	d.reasons == {"credit"}
}

test_allowed_after_threshold_change if {
	d := upgrade.decision with input as {"context": ctx(598, "digital", 0.6)} with data.zg.policy as object.union(pol, {"creditMin": 580})
	d.allow
}

test_verbal_consent_blocked_under_explicit_digital if {
	d := upgrade.decision with input as {"context": ctx(700, "verbal", 0.6)} with data.zg.policy as pol
	d.reasons == {"consent"}
}

test_verbal_consent_ok_under_any if {
	d := upgrade.decision with input as {"context": ctx(700, "verbal", 0.6)} with data.zg.policy as object.union(pol, {"consentRule": "any"})
	d.allow
}

test_network_guard if {
	d := upgrade.decision with input as {"context": ctx(700, "digital", 0.9)} with data.zg.policy as pol
	d.reasons == {"network"}
}

test_model_cannot_decide if {
	d := upgrade.decision with input as {"context": ctx(700, "digital", 0.6), "decidedByModel": true} with data.zg.policy as pol
	"ai-guardrail" in d.reasons
}
