# ADR-0015: Strimzi for Kafka lifecycle on Kubernetes

**Status:** Proposed  
**Date:** 2026-10-05  
**Deciders:** vCloud platform owner and Principal Architect  
**Selection:** Strimzi is required by Module 1.  
**Scope:** [SSoT and shared implementation contract](README.md).

## Context

Kafka needs repeatable broker/controller configuration, certificate handling and
safe upgrades. Strimzi reconciles those resources through Kubernetes. Operator, Kafka
and Kubernetes support ranges must be selected together; see
[the release support matrix](https://strimzi.io/downloads/).

## Decision

- Run the Strimzi Cluster Operator with namespace-scoped responsibilities in
  `platform-services`. Select a pinned release compatible with the approved Kubernetes
  version and a supported Kafka release; do not select an old operator solely because
  it satisfies the Kubernetes 1.30 minimum.
- Use supported **`kafka.strimzi.io/v1`** resources for Kafka, KafkaNodePool, KafkaTopic
  and KafkaUser in the selected release. The v1 API was introduced in Strimzi 0.49;
  that historical API milestone is not a version recommendation. See the
  [v1 API announcement](https://strimzi.io/blog/2025/11/21/what-is-new-in-strimzi-0.49.0/).
  Use KRaft node pools; do not introduce a legacy ZooKeeper topology.
- Argo CD owns Kafka/node-pool/topic/user intent. Strimzi owns generated pods, services,
  certificates and status. OpenBao owns application credential lifecycle where integrated;
  select one writer for each credential and document any necessary Kubernetes Secret
  materialization. Never let two secret controllers overwrite the same object.
- Configure CSI storage, failure-domain placement, TLS listeners, ACLs and bounded
  maintenance/disruption behavior. Review all generated images/init containers and
  permissions against SSoT. Strimzi operators and broker containers gain no privilege
  exception from the Cilium/NVIDIA node allowlist.

## Options considered

| Option | Benefits | Costs and limits |
| --- | --- | --- |
| Strimzi-managed Kafka | Declarative lifecycle with operator health/status | CRD compatibility and controller ownership need discipline |
| Hand-written StatefulSets | Direct configuration control | Team must implement certificates, maintenance and upgrade sequencing |
| Managed Kafka per cloud | Outsourced broker operations | Different local/provider security and provisioning model |

## Trade-off analysis

The operator reduces repeated lifecycle code while adding a release-critical control
plane dependency. Schema validation must include its CRDs and generated workload audits,
not simply skip unknown kinds.

## Consequences

Deleting a Kafka custom resource can trigger destructive consequences; storage retention
and Argo pruning policies must be explicit. Broker expansion requires partition
reassignment, not just extra pods. See
[deployment and management](https://strimzi.io/docs/operators/latest/deploying.html).

## Action items and acceptance

- [ ] Freeze the operator/Kafka/Kubernetes matrix and release-matched v1 schemas.
- [ ] Strictly validate both custom resources and rendered/generated Pod security profiles.
- [ ] Test certificate rotation, rolling upgrades, operator restart and storage retention.
- [ ] Demonstrate broker replacement/rebalance without violating topic durability or ACLs.
