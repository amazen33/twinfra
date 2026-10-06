# ADR-0002: Kubernetes as the orchestration contract

**Status:** Proposed  
**Date:** 2026-10-05  
**Deciders:** vCloud platform owner and Principal Architect  
**Selection:** Kubernetes is required by Module 1.  
**Scope:** [SSoT and shared implementation contract](README.md).

## Context

vCloud needs the same application resource model across local infrastructure, EKS,
GKE and AKS, with CPU, GPU and batch workloads. The approved local host bootstrap
uses upstream Kubernetes through kubeadm. A portable API does not make provider load
balancers, storage, network routing or IAM interchangeable. See the
[Kubernetes architecture](https://kubernetes.io/docs/concepts/architecture/).

## Decision

- Retain Kubernetes **1.30+** as the minimum and preserve the exact approved local
  bootstrap version until its node inventory is reviewed for an upgrade. Use containerd,
  cgroup v2, Cilium native routing and the NVIDIA runtime for GPU nodes.
- Assign infrastructure, application and HPC ownership to the three core namespaces.
  Separate GPU/HPC node pools with labels, taints, resource quotas and priority policy.
  Use CSI storage classes per site; vetted Local PVs explicitly accept node-bound recovery.
- For the production target, use three control-plane members on separate failure domains
  and worker capacity sufficient for disruption budgets. The existing single-node host
  is a bootstrap/validation environment. Managed control planes have their own provider SLA.
- Git owns resource intent; Kubernetes and approved operators own runtime status and
  generated child resources. Scaling controllers own only expressly delegated fields.

## Options considered

| Option | Benefits | Costs and limits |
| --- | --- | --- |
| Upstream Kubernetes locally; managed Kubernetes in cloud | Common APIs and operator ecosystem | Site-specific CSI, identity and networking still need validation |
| Lightweight distribution as the permanent contract | Smaller initial footprint | Distribution defaults add parity and networking review work |
| VM-only scheduling | Direct host control | Loses requested operator, Knative and GitOps resource model |

## Trade-off analysis

Kubernetes provides the requested integration surface at the cost of controller,
certificate, storage and upgrade operations. Cloud parity means tested application
behavior and interfaces, not identical implementation or performance.

## Consequences

Production HA requires more hosts than Module -1. Cilium native PodCIDR routing must
be provided by the underlay or a separately configured routing control plane. Kubernetes
NetworkPolicy enforcement depends on the selected CNI; use identity-based allow rules
and default deny as described in the
[network policy documentation](https://kubernetes.io/docs/concepts/services-networking/network-policies/).

## Action items and acceptance

- [ ] Freeze a supported Kubernetes/operator matrix and schemas; use stable APIs such
  as `networking.k8s.io/v1` and `autoscaling/v2` where applicable.
- [ ] Prove denied cross-tenant traffic, allowed DNS/API traffic, CSI provisioning,
  GPU placement and route reachability on each site.
- [ ] Exercise node loss, control-plane quorum, etcd restore and staged upgrades.
- [ ] Apply restricted Pod Security; retain only the exact
  [approved node exception](../adr-0001-node-host-mounts.md).
