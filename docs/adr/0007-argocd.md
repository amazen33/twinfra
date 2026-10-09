# ADR-0007: Argo CD as the Kubernetes deployment reconciler

**Status:** Accepted (lab) — [wsl-2026-10-07.md](../acceptance/wsl-2026-10-07.md); reconciliation and controlled drift repair.
**Date:** 2026-10-05  
**Deciders:** vCloud platform owner and Principal Architect  
**Selection:** Argo CD is required by Module 1.  
**Classification:** Constraint — selection required by Module 1; alternatives assess implementation, not an open component competition.
**Scope:** [SSoT and shared implementation contract](README.md).

## Context

Production resources need auditable desired state and predictable reconciliation.
Argo CD can reconcile Git changes without giving the CI pipeline direct deployment
access. Automatic pruning and self-healing are configurable rather than unconditional.
See [automated sync](https://argo-cd.readthedocs.io/en/stable/user-guide/auto_sync/).

## Decision

- Run Argo CD in `platform-services`, authenticated with Keycloak and scoped AppProjects.
  `amazen33/vCloud` owns reviewed Kubernetes desired state. Restrict allowed repositories,
  cluster destinations, namespaces and resource kinds; separate infrastructure and tenant
  projects. Access to stateful infrastructure is reserved for platform maintainers.
- Tekton builds/verifies artifacts and proposes digest changes through a reviewed Git
  pull request. Argo CD is the sole application deployment reconciler. Pipeline identities
  cannot patch production Deployments or invoke a deployment bypass.
- Use explicit sync ordering for CRDs, operators, dependent resources and policies,
  with health checks for custom resources. Wave ordering does not prove a database,
  gateway or application is ready. Pin chart versions, Git revisions and every rendered
  image; verify provenance before production synchronization.
- Enable self-healing only with declared ownership. For the database capacity controller,
  ignore only `spec.instances` on the specific Cluster and configure sync to respect
  that difference; the remaining fields remain Git-controlled. Knative/operators own
  generated children. See [diff customization](https://argo-cd.readthedocs.io/en/stable/user-guide/diffing/).
- Gate production changes with reviewed commits and sync windows. Disable automatic
  pruning of database/PVC/backup resources until retention and deletion protections are
  proven. Do not enable empty-application deletion as a convenience.

## Options considered

| Option | Benefits | Costs and limits |
| --- | --- | --- |
| Argo CD pull reconciliation | Auditable intent and drift reporting | Field ownership and controller health require configuration |
| CI pushes directly with kubectl | Simple first deployment | Broad production credentials and competing deployment writers |
| Manual cluster administration | Flexible emergency access | Poor repeatability without a reconciled Git update |

## Trade-off analysis

GitOps reduces long-lived deployment credentials in CI, but destructive declarative
changes still need review. Automation must respect stateful deletion and autoscaler
ownership instead of forcing every live field back to Git.

## Consequences

Emergency changes require documented break-glass access and subsequent Git reconciliation.
Rollback restores a previous digest/manifest only when database migrations remain compatible.
Repository credentials come from OpenBao via a separately reviewed integration; no secrets
are committed to Git.

## Action items and acceptance

- [ ] Pin Argo CD and its supported CRD schemas; validate rendered applications.
- [ ] Prove project RBAC, secret isolation, image verification and blocked cross-namespace writes.
- [ ] Test drift repair, autoscaler delegation, sync dependency failures and safe pruning.
- [ ] Demonstrate application rollback and separately tested database recovery.
