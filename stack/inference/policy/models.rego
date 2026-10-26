# L4 · model allow-list for the shared inference service (our extension of the Zero Gravity framework).
# OPA in L4 decides which models may be used: UK data residency; customer data only to local/sovereign models;
# deterministic layers (L4 policy, L5 execution) may never call a model.
package zg.inference

import rego.v1

default allow := false

cat := data.zg.modelcatalog

pol := data.zg.inference_policy

model := cat[input.model]

known if cat[input.model]

residency_ok if model.residency in pol.allowedResidency

data_ok if input.dataClass != "customer"

data_ok if {
	input.dataClass == "customer"
	model.sovereign
}

caller_ok if not input.callerLayer in pol.forbiddenCallerLayers

class_ok if input.taskClass in model.classes

allow if {
	known
	residency_ok
	data_ok
	caller_ok
	class_ok
}

reasons contains "model not in catalogue" if not known

reasons contains sprintf("residency %s not allowed (UK only)", [model.residency]) if {
	known
	not residency_ok
}

reasons contains "customer data may only go to local/sovereign models (UK GDPR)" if {
	known
	not data_ok
}

reasons contains sprintf("%s may never call a model (deterministic layer)", [input.callerLayer]) if not caller_ok

reasons contains sprintf("model not approved for task class %s", [input.taskClass]) if {
	known
	not class_ok
}

decision := {"allow": allow, "reasons": reasons, "model": input.model}
