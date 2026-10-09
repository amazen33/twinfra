# ADR-0005: pgvector as the application vector store

**Status:** Accepted (lab) — [wsl-2026-10-07.md](../acceptance/wsl-2026-10-07.md); extension/vector query; application RAG pending.
**Date:** 2026-10-05  
**Deciders:** vCloud platform owner and Principal Architect  
**Selection:** PostgreSQL with pgvector is required by Module 1.  
**Classification:** Constraint — selection required by Module 1; alternatives assess implementation, not an open component competition.
**Scope:** [SSoT and shared implementation contract](README.md).

## Context

RAG needs durable embeddings, document metadata and tenant authorization together.
pgvector supplies PostgreSQL similarity search, including exact search and approximate
HNSW/IVFFlat indexes. Approximate indexes trade recall and resource use for query cost;
filtering can reduce returned candidates. See the
[pgvector project documentation](https://github.com/pgvector/pgvector).

## Decision

- Install a reviewed pgvector version in the immutable PostgreSQL image managed by
  CloudNativePG. Enable extensions through a controlled migration; the application
  role cannot install extensions or change security policy.
- Store chunk text or an authorized object reference, document/chunk IDs, tenant ID,
  ACL metadata, embedding vector, dimensions and embedding-model revision. Pin the
  embedding model independently from the generation model. Reject dimension/revision
  mismatches and re-index through a versioned migration when the model changes.
- LangChain's RAG application performs parameterized, tenant-filtered queries and
  prepares the context sent to vLLM. vLLM does not receive database credentials or issue
  SQL. Apply database grants and row-level security as defense in depth, using a role
  that neither owns the tables nor bypasses RLS. Tenant context must come from validated
  identity and be reset correctly by the connection pool.
- Begin with exact search for a benchmark baseline; adopt HNSW when measured corpus
  size/latency justify it. Evaluate recall after ACL filtering, index memory, vacuum
  and ingestion contention. Use idempotent chunk IDs for Kafka-driven ingestion.

## Options considered

| Option | Benefits | Costs and limits |
| --- | --- | --- |
| pgvector within PostgreSQL | Shared transactions, authorization and backup tooling | Vector indexes compete with relational workload resources |
| Separate vector database | Independent vector capacity | Additional operations and cross-store consistency/security |
| Embeddings in application memory | Minimal initial service count | No required durable, shared retrieval store |

## Trade-off analysis

The initial design favors one transactional data platform. A separate vector service
needs a later ADR if measured corpus scale or retrieval SLO exceeds this architecture.

## Consequences

CloudNativePG backups protect vectors and metadata together. A read replica may return
stale context; recently ingested documents use primary reads when freshness matters.
Database RLS requires explicit schema/role design and tests; see
[PostgreSQL row security](https://www.postgresql.org/docs/current/ddl-rowsecurity.html).

## Action items and acceptance

- [ ] Pin PostgreSQL/pgvector compatibility and record migrations and model dimensions.
- [ ] Test forged tenant filters, pooled-connection reuse and cross-tenant denial.
- [ ] Measure recall, latency and index size on a representative labeled corpus.
- [ ] Prove ingestion replay, document deletion and restore preserve ACLs and vector revisions.
