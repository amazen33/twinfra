package twinfra_platform

import rego.v1

# Workload templates include Knative Services; CRD schema objects have no Pod
# template and are deliberately excluded. Generated Pods are checked live too.
pod := input.spec.template.spec if { input.spec.template.spec.containers }
pod := input.spec if { input.kind == "Pod" }
pod := input.spec if { input.kind == "Prometheus" }

containers contains c if { some c in pod.containers }
containers contains c if { some c in object.get(pod, "initContainers", []) }

deny contains msg if {
    some c in containers
    object.get(c.securityContext, "allowPrivilegeEscalation", true) != false
    msg := sprintf("%s/%s: privilege escalation must be disabled", [input.kind, c.name])
}
deny contains msg if {
    some c in containers
    object.get(c.securityContext, "runAsNonRoot", object.get(object.get(pod, "securityContext", {}), "runAsNonRoot", false)) != true
    msg := sprintf("%s/%s: non-root execution required", [input.kind, c.name])
}
deny contains msg if {
    some c in containers
    not "ALL" in object.get(object.get(c.securityContext, "capabilities", {}), "drop", [])
    msg := sprintf("%s/%s: all capabilities must be dropped", [input.kind, c.name])
}
deny contains msg if {
    some c in containers
    count(object.get(object.get(c.securityContext, "capabilities", {}), "add", [])) > 0
    msg := sprintf("%s/%s: added capabilities prohibited", [input.kind, c.name])
}
deny contains msg if {
    some c in containers
    object.get(c.securityContext, "privileged", false)
    msg := sprintf("%s/%s: privileged container prohibited", [input.kind, c.name])
}
deny contains msg if {
    some c in containers
    sc := object.get(c.securityContext, "seccompProfile", object.get(object.get(pod, "securityContext", {}), "seccompProfile", {}))
    object.get(sc, "type", "") != "RuntimeDefault"
    msg := sprintf("%s/%s: RuntimeDefault seccomp required", [input.kind, c.name])
}
deny contains msg if {
    some c in containers
    object.get(c, "imagePullPolicy", "") != "IfNotPresent"
    msg := sprintf("%s/%s: explicit IfNotPresent required", [input.kind, c.name])
}
deny contains "hostPath prohibited in endpoint profile" if {
    some v in object.get(pod, "volumes", [])
    v.hostPath
}
deny contains "host namespace prohibited in endpoint profile" if {
    some field in ["hostNetwork", "hostPID", "hostIPC"]
    object.get(pod, field, false)
}
