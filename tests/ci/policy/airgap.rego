package main
import rego.v1

podspec := input.spec if { input.kind == "Pod" }
podspec := input.spec.jobTemplate.spec.template.spec if { input.kind == "CronJob" }
podspec := input.spec.template.spec if { input.kind != "Pod"; input.kind != "CronJob" }

deny contains message if {
    spec := podspec
    some group in {"containers", "initContainers", "ephemeralContainers"}
    some container in object.get(spec, group, [])
    object.get(container, "imagePullPolicy", "") != "IfNotPresent"
    message := sprintf("%s/%s: %s %s must explicitly set imagePullPolicy: IfNotPresent", [input.kind, input.metadata.name, group, container.name])
}
