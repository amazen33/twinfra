# ADR-0020: trusted main builds and automatic digest promotion

**Status:** Proposed — implemented/statically validated; full integration live acceptance pending.
**Date:** 2026-10-06
**Deciders:** vCloud platform owner and Principal Architect

## Context

Module 3 requires repository-push builds, tests and automatic manifest updates in
`amazen33/vCloud`, with continuous Argo CD reconciliation and Prometheus/Grafana hooks.
The restricted/non-root contract, namespace deny-all, private registry and approved
node policy remain in force. A same-repository bot commit must not trigger endless
rebuilds or let slower old builds roll back newer deployment intent.

## Decision

Authenticate GitHub push events through the pinned Tekton GitHub interceptor, then
accept only protected `main` pushes for the exact repository, nonzero source SHA,
and non-deleted/non-forced refs. Pipeline Task inputs are environment data validated
before subprocess calls; no source parameter is interpolated into shell scripts.

Build the new `vcloud-api` workload with a non-root BuildKit client communicating
over mTLS to an isolated rootless builder VM. Standard Dockerfile execution needs
filesystem/user-namespace facilities outside the Kubernetes restricted profile;
an external builder avoids any privilege, socket or node mount exception in CI Pods.
Root is required only during connected tooling-image preparation for OS-package
installation. Runtime Tasks have UID 65532, RuntimeDefault seccomp and no API token.

After tests, immutable OCI push and final strict schema/security validation, update
only the image and source annotation on `gitops/prod`. This automatic environment
promotion replaces ADR 0008's proposed per-image PR flow for this workload, as requested
by Module 3. Human source/configuration changes continue through protected `main`.
The source digest and environment branch are separate audit identities. Branches are
deliberately moving reconciliation references; OCI references contain immutable digests.

Credential-bearing publisher code lives in the reviewed CI image, not the checkout.
Only its Task mounts the GitHub App token. Tests get no publishing/build credentials.
Main-tip checks reject observed stale builds; ordinary push and bounded retry preserve
competing commits. The source and promotion ref checks are not a cross-ref atomic lock.

Argo applications/projects separate CI infrastructure and the new delivery workload.
Module 2's existing function/database/PVs retain their owners. No automatic pruning
or empty application deletion is enabled. Tekton's auxiliary `tekton-pipelines`
namespace follows upstream placement and avoids Knative ConfigMap name collisions;
the three core SSoT namespaces retain their roles. Per-run workspaces require reviewed
dynamic CSI, not the static Module 2 Local PV class.

Use native Tekton/Argo Prometheus scrape metrics, histogram duration, bounded labels,
Prometheus alert rules and a Grafana dashboard. Controller configuration changes use
narrow merge patches, preserving upstream fields. External notifications, image signing,
SBOM/provenance and admission verification remain separate integration gates.

## Options considered

| Option | Outcome |
| --- | --- |
| Restricted client + isolated rootless BuildKit VM | Selected; needs external builder and mTLS acceptance |
| Privileged Docker-in-Docker / node Docker socket | Rejected by the current host/privilege contract |
| Rootless daemon Pod with unconfined security | Broadens the Kubernetes security profile; not selected |
| Update deployment manifests on main | Creates trigger-loop and source-authority risk |
| One human PR per image digest | Earlier proposal; does not implement the selected automatic promotion flow |
| CI invokes kubectl apply | Competes with Argo and introduces production deployment authority |

## Consequences and acceptance

Credential rotation, branch protection, reviewed CSI and external builder operations
become prerequisites. Static validation and local Git/HTTP tests cannot prove Kubernetes
admission, GitHub webhook verification, OCI build, certificate issuance or telemetry
delivery. Accept those paths and the outstanding artifact-trust gates before describing
the platform as production-ready. See the [runbook](../../module-3/README.md),
[manifests](../../module-3/manifests/) and [evidence](../module-3-validation.json).

## Action items

- [ ] Publish the reviewed source and seed/protect the promotion branch.
- [ ] Stage the tooling image, reviewed controllers, CSI and short-lived OpenBao credentials.
- [ ] Accept builder mTLS/OCI push, actual webhook verification and Argo drift repair.
- [ ] Confirm observed scrape targets, dashboard and Alertmanager routing.
- [ ] Add image signing, SBOM/provenance and admission verification before production artifact-trust claims.
