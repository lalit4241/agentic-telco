package zg.inference_test

import rego.v1

import data.zg.inference

test_local_small_customer_extraction_allowed if {
	inference.allow with input as {"model": "zg-local-small", "dataClass": "customer", "taskClass": "extraction", "callerLayer": "L2"}
}

test_us_saas_denied_residency if {
	not inference.allow with input as {"model": "us-frontier-saas", "dataClass": "public", "taskClass": "reasoning", "callerLayer": "L2"}
}

test_customer_data_not_to_non_sovereign if {
	r := inference.reasons with input as {"model": "us-frontier-saas", "dataClass": "customer", "taskClass": "reasoning", "callerLayer": "L2"}
	"customer data may only go to local/sovereign models (UK GDPR)" in r
}

test_l5_may_not_call_models if {
	not inference.allow with input as {"model": "zg-local-small", "dataClass": "public", "taskClass": "extraction", "callerLayer": "L5"}
}

test_l4_may_not_call_models if {
	not inference.allow with input as {"model": "zg-local-small", "dataClass": "public", "taskClass": "classification", "callerLayer": "L4"}
}

test_wrong_task_class_denied if {
	not inference.allow with input as {"model": "zg-local-small", "dataClass": "public", "taskClass": "reasoning", "callerLayer": "L2"}
}
