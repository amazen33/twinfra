# ADR-0004: CloudNativePG for PostgreSQL lifecycle and bounded capacity

**Status:** Proposed  
**Date:** 2026-10-05  
**Deciders:** vCloud platform owner and Principal Architect  
**Selection:** CloudNativePG is required by Module 1.  
**Scope:** [SSoT and shared implementation contract](README.md).

## Context

The application needs transactional data and pgvector with backup, failover and a
defined scaling policy. CloudNativePG manages a primary and standby instances. Its
scale subresource permits changing instance count, but generic HPA CPU averages are
unsuitable for the mixed primary/replica workload. Upstream recommends VPA in
recommendation-only mode and discourages ordinary HPA for PostgreSQL. See
[resource management and autoscaler constraints](https://cloudnative-pg.io/docs/1.28/resource_management/).

## Decision

- Run the operator and managed database clusters in `platform-services` with scoped
  RBAC. Use a pinned PostgreSQL image containing the reviewed pgvector extension.
  Application, Keycloak and Grafana databases use separate credentials and ownership;
  split their database clusters when failure isolation or capacity requires it.
- Production application data has one writable primary and at least two standbys
  across failure domains, TLS, CSI PVCs and bounded connection pooling. Route writes
  and read-after-write operations to the primary; use replica reads only where lag is
  acceptable. Replicas add read capacity, not primary write capacity or automatic sharding.
- Define **automatic read-capacity scaling** as a separately implemented bounded
  controller/metrics-adapter integration using replica load, read latency and lag.
  An initial proposed envelope is 3–6 total instances, with minimum at least
  `max(3, maxSyncReplicas + 1)` and maximum subject to storage/node quota. Pause scale-down
  during failover, excessive lag, backup/recovery or capacity instability. This adapter
  and its safety behavior require implementation and load testing before activation.
- Delegate only `spec.instances` to that controller. Argo CD must respect that field
  during sync, while Git continues to own bounds, PostgreSQL settings and storage intent.
  Keep VPA in `Off` mode; apply approved recommendations to Cluster resources through Git.
- Size primary CPU/RAM and grow CSI volumes through planned changes. Reserve HugePages
  explicitly per workload against the host's **128 × 2 MiB + 1 × 1 GiB** pools; reservation
  alone does not configure PostgreSQL to consume them.

## Options considered

| Option | Benefits | Costs and limits |
| --- | --- | --- |
| CloudNativePG plus guarded read-capacity policy | Operator lifecycle and explicit scaling ownership | Additional metrics/controller work; single-primary write ceiling |
| Fixed replica count with manual tuning | Simplest operational baseline | Does not automatically follow read demand |
| Generic CPU HPA on the Cluster | Easy to configure | Misleading metric, quorum/lag hazards and no write relief; rejected |

## Trade-off analysis

The requested autoscaling is constrained to safe read capacity. Write throughput
requires tuning, vertical capacity or a separate data-partitioning decision; it is not
made elastic merely by installing an operator.

## Consequences

Implement off-cluster WAL/base-backup storage through the pinned release's supported
backup integration, retention and scheduled restore drills. Replication is not a backup.
OpenBao rotates scoped application credentials; its recovery must not depend on this
database being available. See [CloudNativePG recovery](https://cloudnative-pg.io/docs/1.28/recovery/).

## Action items and acceptance

- [ ] Validate `postgresql.cnpg.io/v1` and release-matched backup/Pooler schemas.
- [ ] Prove replication, failover, pooling, tenant permissions, PITR and application reconnects.
- [ ] Implement read-only scaling metrics, quorum/lag guards and Argo field delegation;
  demonstrate both scale-up and safe scale-down under load.
- [ ] Benchmark vector queries, primary write saturation and HugePage allocation before sizing.
