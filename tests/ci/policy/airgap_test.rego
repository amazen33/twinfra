package main
import rego.v1

test_explicit_policy_accepted if {
    count(deny) == 0 with input as {"kind":"Pod", "metadata":{"name":"ok"}, "spec":{"containers":[{"name":"app","imagePullPolicy":"IfNotPresent"}]}}
}
test_always_rejected if {
    count(deny) == 1 with input as {"kind":"Deployment", "metadata":{"name":"bad"}, "spec":{"template":{"spec":{"containers":[{"name":"app","imagePullPolicy":"Always"}]}}}}
}
test_missing_policy_rejected if {
    count(deny) == 1 with input as {"kind":"StatefulSet", "metadata":{"name":"bad"}, "spec":{"template":{"spec":{"containers":[{"name":"app"}]}}}}
}
test_init_policy_rejected if {
    count(deny) == 1 with input as {"kind":"Deployment", "metadata":{"name":"bad"}, "spec":{"template":{"spec":{"initContainers":[{"name":"init","imagePullPolicy":"Always"}],"containers":[{"name":"app","imagePullPolicy":"IfNotPresent"}]}}}}
}
test_cronjob_rejected if {
    count(deny) == 1 with input as {"kind":"CronJob", "metadata":{"name":"bad"}, "spec":{"jobTemplate":{"spec":{"template":{"spec":{"containers":[{"name":"app"}]}}}}}}
}
test_knative_rejected if {
    count(deny) == 1 with input as {"kind":"Service", "metadata":{"name":"bad"}, "spec":{"template":{"spec":{"containers":[{"name":"app","imagePullPolicy":"Never"}]}}}}
}
test_configmap_ignored if {
    count(deny) == 0 with input as {"kind":"ConfigMap", "metadata":{"name":"config"},"data":{}}
}
