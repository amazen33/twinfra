package twinfra_backup

import rego.v1

# The owner-approved WO-09 node exception is an exact PodSpec, not a namespace
# exemption. Any extra mount, token, root process, command or image fails.
deny contains "Unapproved node backup identity or PodSpec" if {
    input.kind == "CronJob"
    expected := data.backupNodeException
    not approved(expected)
}

approved(expected) if {
    input.metadata.name == expected.name
    input.metadata.namespace == expected.namespace
    input.spec.jobTemplate.spec.template.spec == expected.podSpec
}
