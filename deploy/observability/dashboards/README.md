# Dashboard definitions retained for WO-10

These plain JSON files are not Kubernetes resources and are not applied by any
Kustomization, Argo CD Application, Helm release or deployment script. WO-07a
deploys neither Perses nor Prometheus. [WO-10 Amendment 1](../../../docs/work-orders/WO-10-observability-stack-v1.md)
owns their future deployment, after Prometheus, behind Keycloak SSO through APISIX,
read-only from Git with no anonymous access and eligible, scanned releases.

| File | Panels | Source |
| --- | ---: | --- |
| [twinfra-delivery.json](twinfra-delivery.json) | 4 | Pipeline runs, duration p95, Argo CD sync/health and delivery alerts |
| [twinfra-health.json](twinfra-health.json) | 3 | Platform health queries |

Both Dashboard objects are copied unchanged from
[PR #39 at 48d3a0a](https://github.com/amazen33/twinfra/blob/48d3a0a05477a88ebb3115fca9f19fcebde2f974/deploy/observability/perses/dashboards.json).
No Project, Datasource, Operator, CRD, image or `PersesDashboard` resource is copied.
All panels and PromQL remain identical to those ported definitions. PR #39 stays
unchanged; the owner closes it after WO-07a merges.

The [provenance receipt](../../../docs/acceptance/grafana-removal-2026-10-15.json)
pins the full source file and each copied Dashboard object's canonical JSON hash.
CI verifies every field and panel against those hashes without depending on an
unmerged PR branch surviving a squash merge or owner deletion.
