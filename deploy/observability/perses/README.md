# Perses dashboards (WO-07)

Perses **0.54.0** (2026-07-29) and Perses Operator **0.5.0** (2026-08-04)
meet the 14-day rule. Both are Apache-2.0. Exact source licences, OCI index
digests and CRD hashes are in [artifacts.lock.json](artifacts.lock.json) and the
[licence register](../../../security/licence-register.json).

`tools/perses.py` produces project, datasource and dashboard JSON. The dev
generator consumes it and installs the operator and `perses.dev/v1alpha2`
instance in `twinfra-platform-services`. This version is served and not
deprecated in the pinned operator; the older deprecated alpha version is not
used. Original CRD archives are checksum-verified upstream sources. Retained
WSL generators use the same implementation until WO-28; WSL is not the live target.

## Authentication and isolation

Every `/console/metrics` path uses the existing APISIX `openid-connect` pattern:
Keycloak session, verified issuer/audience, RS256, PKCE and `console.viewer` or
`console.admin` role claims. The dev cookie is HTTPS-only and HttpOnly. Caller
token headers are cleared before OIDC and credentials stripped before forwarding.
Perses keeps `api_prefix`; APISIX does not strip this prefix.

Perses delegates authentication to APISIX (`enable_auth: false` in the private
backend). No direct browser forward is published. Default-deny allows APISIX
ingress and node GET probes on the exact health path, excluding dashboard APIs.
Server egress allows DNS and the selected Prometheus Pod on TCP 9090. Operator
egress allows DNS/Kubernetes API and node health probes on 8081.

`readonly: true` blocks HTTP resource edits, including for admins. Mounted Git
ConfigMaps provision project, datasource and dashboards. A content hash rolls
the generated Pod on configuration changes. The bounded emptyDir database is
rebuilt from Git; no PVC or host mount is needed.

The operator and instance use non-root execution and RuntimeDefault seccomp.
The upstream generated server container drops ALL capabilities, disallows
privilege escalation and uses IfNotPresent. Namespace restricted PSS applies.
Upstream v0.5.0 does not mark the generated server root filesystem read-only;
restricted PSS does not require it.

v0.5.0 has cluster-wide informers with no namespace-watch flag. Its ClusterRole
grants only get/list/watch, including Secret reads required by those informers.
Mutation permissions are namespace-scoped, exclude Secret writes, and webhooks
are disabled. Consider this read scope before multi-tenant rollout; the operator
is not namespace-isolated. `prepare-secrets.py` creates `twinfra-perses-key`
through the existing in-memory, create-only flow. No key is committed.

## Dashboard mapping

| Previous dashboard/panel | Perses dashboard/panel | Migration |
| --- | --- | --- |
| vcloud-delivery / Pipeline runs | twinfra-delivery / Pipeline runs | Unchanged PromQL |
| vcloud-delivery / Pipeline duration p95 | twinfra-delivery / Pipeline duration p95 | Unchanged PromQL |
| vcloud-delivery / Argo CD sync and health | twinfra-delivery / Argo CD sync and health | Unchanged PromQL |
| vcloud-delivery / Delivery alerts | twinfra-delivery / Delivery alerts | Unchanged PromQL |
| No tracked health dashboard | twinfra-health / Scrape targets, PostgreSQL instances, Platform alerts | New `up`, `cnpg_collector_up`, `ALERTS` panels |

**No panels are unported.** The inventory contained a four-panel Module 3
dashboard and a WSL datasource, but no separate health dashboard definition.
The Module 3 ConfigMap now contains `twinfra-delivery.json` Perses JSON.
Existing delivery metric labels are preserved. The generated provisioning
folder already includes that dashboard and the new health dashboard.

The dev datasource targets
`http://twinfra-prometheus.twinfra-platform-services.svc.cluster.local:9090`.
The minimal dev profile does not yet deploy Prometheus; WO-10 supplies it.
Retained WSL output targets its existing `prometheus` Service. Empty panels
caused by missing producers/scrapes are not acceptance evidence.

## Verification

`python tools/perses.py --check` verifies deterministic JSON, CRDs and upstream
amd64/arm64 SPDX statements through the pinned OCI index and blob digests.
Compressed evidence preserves upstream NOASSERTION fields. This verifies
digests, not signatures or complete transitive-licence clearance. Upstream
Dockerfiles copy `/LICENSE`. The inventories include separate Debian OS
packages (including netbase GPL-2.0-only), covered as unmodified OS aggregation
under ADR-0044; not every file inside the image is Apache-2.0.

CI verifies schemas/PSS, queries, authenticated routes, network/RBAC boundaries
and removal mutations. Live data, viewer permissions, actual generated Pods
and obsolete-resource removal remain **Pending** in
[the dev receipt](../../../docs/acceptance/perses-2026-10-10.md).
No live image pull, deployment, cleanup, Secret creation or tunnel ran here.
