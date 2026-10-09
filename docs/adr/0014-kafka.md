# ADR-0014: Apache Kafka for durable asynchronous events

**Status:** Proposed  
**Date:** 2026-10-05  
**Deciders:** vCloud platform owner and Principal Architect  
**Selection:** Apache Kafka is required by Module 1.  
**Classification:** Constraint — selection required by Module 1; alternatives assess implementation, not an open component competition.
**Scope:** [SSoT and shared implementation contract](README.md).

## Context

Document ingestion, embedding batches and HPC job status need buffering, replay and
independent consumers. Kafka supplies a partitioned event log. Kafka transactions do
not automatically make writes to PostgreSQL or job submission exactly-once; those
destinations must cooperate. See [delivery semantics](https://kafka.apache.org/41/design/design/).

## Decision

- Run a pinned, Strimzi-supported **KRaft** Kafka release in `platform-services`.
  Use dedicated controller and broker node pools for the production target, each with
  three members across failure domains. Use CSI storage, verified TLS, scoped client
  identities and topic/group ACLs; do not expose anonymous or plaintext listeners.
- Define versioned event envelopes containing event ID, tenant/job/document ID,
  schema version, authorized object reference and trace correlation. Avoid raw prompts,
  credentials and large document payloads. Define schema compatibility and size limits
  before consumers are deployed; a schema-registry product is not implicitly selected.
- Use proposed topics `vcloud.documents.v1`, `vcloud.hpc.jobs.v1` and
  `vcloud.hpc.status.v1`, with owned retry/dead-letter handling and retention per data
  classification. Namespace prefixes alone do not enforce tenant isolation; apply ACLs
  and consumer authorization, using separate topics where required.
- Production defaults target replication factor 3, minimum in-sync replicas 2,
  `acks=all` and idempotent producers. Treat consumption as at-least-once; commit offsets
  only after durable effects and deduplicate by event/operation ID. Use a transactional
  PostgreSQL outbox and an explicitly implemented publisher where state change and event
  emission must stay consistent.
- Keep interactive RAG requests on the HTTP path; Kafka serves ingestion and asynchronous
  HPC workflows. Consumers have bounded concurrency, retry budgets and backpressure.

## Options considered

| Option | Benefits | Costs and limits |
| --- | --- | --- |
| Kafka event log | Replay, consumer groups and durable buffering | Quorum/storage operations and idempotent consumers |
| Synchronous HTTP for all work | Fewer asynchronous components | Long-running jobs couple retries and availability to callers |
| Simple work queue only | Simpler job dispatch | Different replay/streaming contract from the required Kafka layer |

## Trade-off analysis

Kafka decouples demand from execution, at the cost of event schemas, duplicate handling
and retention policy. Durability settings favor correctness over accepting writes after
an insufficient-replica failure.

## Consequences

Job state remains durable in PostgreSQL; a Kafka offset is not a user-visible job record.
Broker replication is not an independent recovery archive. Document deletion must cover
retained payloads and downstream indexes according to the data-retention policy.

## Action items and acceptance

- [ ] Pin Kafka/client compatibility and implement outbox, schema evolution and ACLs.
- [ ] Inject broker loss, duplicate delivery, consumer crash and partial job-submission failure.
- [ ] Prove replay cannot duplicate vector chunks or billable infrastructure jobs.
- [ ] Exercise retention, lag alerts and disaster recovery with tenant isolation intact.
