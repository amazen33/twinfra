# Rendered reference manifests

These copy-ready YAML files come from `site-values.example.yaml`, a single-VM
reference profile with documentation addresses and **automatic GitOps sync disabled**.
Inspect them alongside the annotated chart templates. Configure the real site and use
`make validate`, fresh `make host-check` reports, `make prepare`, and `make apply`
according to the [runbook](../README.md). The checked-in reference files do not supply
physical storage vetting, controller installations, credentials or published Git refs.

| File | Resources |
| --- | --- |
| [storage.yaml](storage.yaml) | StorageClass, exact retained Local PVs |
| [network.yaml](network.yaml) | Namespace deny-all/allow policies and reviewed host policy |
| [database.yaml](database.yaml) | CNPG Cluster, VPA, non-root resource scaler and scoped RBAC |
| [function.yaml](function.yaml) | Secure Knative function, PVC, APISIX route/upstream/public TLS |
| [gitops-root.yaml](gitops-root.yaml) | Root Application and AppProject |
| [gitops-children.yaml](gitops-children.yaml) | Four child Applications |
| [apisix-dependency.yaml](apisix-dependency.yaml) | Optional separately installed gateway profile |

Render source of truth: `module-2/chart`, the site overlay and pinned local charts.
Generated runtime output goes to `.build/module-2`; do not edit generated files.
