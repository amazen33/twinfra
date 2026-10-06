# ADR-0019: Module 2 configuration ownership, local storage and resource growth

**Status:** Implemented and statically validated; live acceptance pending  
**Date:** 2026-10-06  
**Scope:** vCloud SSoT v2.2 and the existing approved node exception.

## Context

Module 2 requires APISIX Kubernetes routes, scale-to-zero persistent functions and
CPU/memory autoscaling for CloudNativePG. The selected controllers must coexist with
restricted namespaces, deny-all policies and an offline bootstrap. The earlier
[APISIX ADR](adrs/0006-apisix.md) proposed a file watcher, while
[database ADR](adrs/0004-cloudnativepg.md) left resource changes under operator ownership.

## Decision

Use API-driven standalone APISIX (traditional role, YAML provider), without APISIX
etcd. Argo owns ApisixRoute/Upstream/Tls; the ingress controller is the sole gateway
configuration writer through private authenticated TLS administration. This replaces
the file-watcher proposal for Module 2. Gateway and Knative stay in the same namespace
for backend resolution. Kourier retains Knative activation/revision routing. Upstream
CA verification is explicit; a client TLS Secret alone is insufficient.

Use static, prebound, retained Local PVs in the exact documented directories, with
physical mount/ownership/capacity inspection before any bootstrap mutation. There is
no dynamic hostPath provisioner or widening of the approved node mount allowlist.
One-node database/function examples are acceptance profiles. Three database instances
require three nodes; node-bound volumes do not substitute for backup or disaster recovery.

Use VPA recommendations and a bounded non-root resource growth adapter that updates
CNPG `spec.resources`. CloudNativePG keeps sole ownership of Pod updates. Direct VPA
Pod resizing/eviction and generic replica HPA are excluded. This implements the requested
CPU/RAM growth while keeping reduction under reviewed maintenance. One object-scoped
Role permits the adapter to read recommendations and patch the Cluster. Argo ignores
only those resource fields and its timestamp. Repeated bootstrap adopts current sizes
and uses an optimistic database resourceVersion rather than restoring initial sizes.

Install narrow controller network allowances before controller startup. Validate local
schemas first, then real admission and the actual Helm node projection before mutation.
Host Firewall enforcement is a per-node opt-in after console/audit checks. SR-IOV
coexistence does not authorize privileged device agents or claim secondary-fabric policy.

## Alternatives and consequences

| Alternative | Reason not selected for this module |
| --- | --- |
| File-watcher APISIX plus CRD controller | Conflicting writers; does not implement the selected API route ownership |
| VPA Auto/Recreate on database Pods | Bypasses CNPG update sequencing and changes resources outside Cluster intent |
| HPA on database replica count | Does not autoscale write capacity or CPU/memory of a PostgreSQL primary |
| Dynamic hostPath storage | Violates the application host-path contract |
| Unreviewed node-wide deny immediately | Can sever administration and cluster peer routes |

The custom scaler adds operational ownership and may trigger restarts/switchover. Its
tests establish algorithm/contract behavior, not scheduler headroom or database recovery.
SR-IOV and experimental Knative internal TLS need separate live evidence. Offline
artifacts need connected staging and publication before GitOps can consume them.

## Validation and acceptance

See the [Module 2 runbook](../module-2/README.md),
[validation evidence](module-2-validation.json), and
[guardrail tests](../tests/test_module2.py). Relevant primary references are
[APISIX modes](https://apisix.apache.org/docs/apisix/deployment-modes/) and
[CNPG resource management](https://cloudnative-pg.io/docs/1.28/resource_management/).
No Ubuntu host, GPU workload, controller installation or live cluster acceptance
was performed during this implementation.
