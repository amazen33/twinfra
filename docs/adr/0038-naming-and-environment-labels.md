# ADR-0038: Environment-neutral names; the environment lives in labels and configuration

Amended by [ADR-0047](0047-upstream-owned-resource-names.md).

**Status:** Accepted (owner, 2026-10-09)
**Author:** Claude (platform architecture). **Decider:** Ahmed Mazen, Owner and Product Owner.

## Context

The WSL lab built its environment into resource names: `vcloud-wsl-postgres`, `vcloud-wsl-keycloak`,
`vcloud-wsl-openbao`, `vcloud-wsl-console`, `vcloud-wsl-db-scaler`, `vcloud-wsl-endpoints-writer` and more.
The console header even shows the cluster name `vcloud-wsl-local`. This breaks ADR-0032, which says
environments differ only in overlays. It also hard-codes the old product name (ADR-0036).

## Decision

1. **Names describe the component, never the environment or the host.** The format is `twinfra-<component>[-<role>]`,
   for example `twinfra-postgres`, `twinfra-keycloak`, `twinfra-console`, `twinfra-gateway`.
   No `wsl`, `vm`, `lab`, `prod` or `vcloud` in resource names, namespaces, Secret names or image names.
2. **The environment is a label and a configuration value.** Use these labels:
   - `twinfra.io/environment`: `dev`, `staging` or `production`
   - `twinfra.io/region`: the region name (D10)
   - `twinfra.io/component`

   Kubernetes recommended labels (`app.kubernetes.io/*`) are kept as well.
3. **The console shows the environment as a badge** read from configuration ("Dev", "Staging", "Production"), plus the region.
   It never shows a cluster or host name.
4. **Cluster contexts are environment-specific by nature** (for example `twinfra-dev-cairo-1`). They appear only in
   kubeconfig and runbooks, never in workload names.
5. **Migration.** New names apply from the dev environment build (WO-21) onward. The WSL lab is not renamed in place; it
   becomes a short-lived dev box and is retired when the dev environment passes acceptance. Historical receipts and ADRs keep the old
   names, because they are history.

## Consequences

The same manifests render for every environment, and only overlays differ. Admission policies (WO-05) can
require the labels. Renaming becomes a one-time cost, paid during the rebuild instead of as a risky migration in place.
