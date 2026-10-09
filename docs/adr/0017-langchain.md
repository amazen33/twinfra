# ADR-0017: LangChain inside the tenant-aware RAG application

**Status:** Proposed  
**Date:** 2026-10-05  
**Deciders:** vCloud platform owner and Principal Architect  
**Selection:** LangChain is required by Module 1.  
**Classification:** Constraint — selection required by Module 1; alternatives assess implementation, not an open component competition.
**Scope:** [SSoT and shared implementation contract](README.md).

## Context

The application must combine identity, retrieval and generation without exposing
private documents to another tenant. LangChain is an application library, not a new
cluster-wide server or scheduler. Its PostgreSQL vector integration is documented in
[PGVectorStore](https://docs.langchain.com/oss/python/integrations/vectorstores/pgvectorstore).

## Decision

- Package pinned LangChain and `langchain-postgres` dependencies inside a non-root
  HTTP RAG service deployed through Knative in `workload-apps`. Use a simple explicit
  retrieval chain; do not grant an autonomous agent arbitrary SQL, shell or cloud tools.
- Implement the request sequence: validate user/tenant claims; obtain a query embedding
  from the private embedding endpoint; retrieve authorized chunks from pgvector; compose
  a bounded prompt with citations; call private vLLM generation; stream the answer through
  Knative/APISIX. vLLM does not fetch from pgvector; the RAG application owns that step.
- Query through parameterized, tenant-constrained retrieval and a least-privilege DB
  role. Do not treat a client-supplied metadata filter as authorization. Verify the
  selected vector-store wrapper preserves SQL/RLS semantics and connection-pool tenant
  isolation; implement a reviewed custom retriever where it does not.
- Treat retrieved documents as untrusted data. Keep them separate from system policy,
  disable arbitrary tool execution, cap context/tokens and prohibit secrets in prompts.
  Return source references authorized for the caller. Use versioned prompts and a
  representative evaluation set for correctness, grounding and refusal behavior.
- A separate asynchronous ingestion worker chunks authorized documents, calls the same
  pinned embedding model, and writes idempotent vectors/ACL metadata from Kafka events.
  Record model/dimension revision. Do not run corpus ingestion inside an interactive request.

## Options considered

| Option | Benefits | Costs and limits |
| --- | --- | --- |
| Explicit LangChain retrieval chain | Reusable integration with visible data/permission steps | Dependency churn and wrapper semantics need tests |
| Direct SQL and inference-client application | Fewer abstraction layers | Team implements retrieval/prompt integration itself |
| Unrestricted agentic retrieval/tools | Flexible exploratory behavior | Larger authorization/prompt-injection surface; not selected |

## Trade-off analysis

LangChain helps compose the RAG workflow but cannot supply tenant isolation by itself.
The application remains responsible for identity, schema, query constraints and output
authorization. The primary trust boundary is the retrieval step, before generation.

## Consequences

Maintain OpenTelemetry spans around retrieval and inference without prompt/secret
payloads. Database or embedding failures return a controlled error; they do not fall
back to unrestricted documents or an external model provider.

## Action items and acceptance

- [ ] Lock library/client/model versions and verify the vLLM OpenAI-compatible contract.
- [ ] Test tenant spoofing, pooled-session reuse, malicious documents and unauthorized citations.
- [ ] Evaluate retrieval recall, grounded answers, token budgets and stream cancellation.
- [ ] Prove ingestion replay/deletion and embedding-model migration preserve authorization.
