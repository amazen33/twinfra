# ADR-0012: OpenBao for secret lifecycle and workload credentials

**Status:** Proposed  
**Date:** 2026-10-05  
**Deciders:** vCloud platform owner and Principal Architect  
**Selection:** OpenBao is required by Module 1.  
**Scope:** [SSoT and shared implementation contract](README.md).

## Context

Database, registry and infrastructure credentials must not live in Git or long-lived
application images. OpenBao supports
[Kubernetes service-account authentication](https://openbao.org/docs/auth/kubernetes/)
and [dynamic PostgreSQL credentials](https://openbao.org/docs/secrets/databases/postgresql/).
These require explicit roles, TTLs and renewal/revocation behavior.

## Decision

- Run an HA OpenBao deployment in `platform-services` with integrated Raft storage,
  one CSI PVC per member, verified TLS, audit logging and separate failure domains.
  Use a release-supported non-root profile. Any capability or memory-lock requirement
  must be reviewed against the current security contract; no root/IPC_LOCK/hostPath
  exception is inferred. Host swap is disabled by the approved bootstrap.
- Bind each workload to exact service-account names, namespaces and token audiences
  using projected short-lived tokens. Scope OpenBao policies to its own secret paths.
  OpenBao's TokenReview identity gets only required review permissions and API egress.
  User Keycloak tokens are not substituted for Kubernetes workload identity.
- Issue short-lived database credentials for RAG/ingestion roles and rotate registry,
  gateway and CI credentials. Only OpenBao's database-management role can perform the
  approved credential lifecycle SQL; workloads cannot grant themselves privileges.
- Prefer a reviewed non-root agent/SDK integration with memory-backed files and explicit
  renewal/reload. A CSI secret integration, injector or synchronization operator is an
  additional component requiring its own pinned manifests and security inventory.
  Kubernetes Secrets are not the canonical secret store; any necessary materialization
  must be encrypted at rest and strictly scoped.
- Bootstrap trust, unseal/recovery material and emergency access outside Git and outside
  services that need OpenBao to start. Choose manual unseal or a separately reviewed
  external auto-unseal provider; do not place the sole unseal key inside this cluster.

## Options considered

| Option | Benefits | Costs and limits |
| --- | --- | --- |
| OpenBao with scoped workload auth | Central leases, rotation and audit | Recovery, quorum and token integration operations |
| Kubernetes Secrets only | Native consumption | Does not supply dynamic leases or the selected secret authority |
| Provider-specific secret service | Managed availability | Different local/cloud identity and portability model |

## Trade-off analysis

OpenBao separates secret administration from application deployment. That creates a
critical dependency which needs independent recovery and a tested outage policy.

## Consequences

Applications renew credentials and reconnect when leases change. Fail closed once
required credentials expire; do not invent static emergency credentials. Encrypted
Raft snapshots and audit records have independent retention and access controls. See
[integrated storage](https://openbao.org/docs/internals/integrated-storage/).

## Action items and acceptance

- [ ] Pin OpenBao/agents and prove the non-root storage/security profile.
- [ ] Test wrong namespace/audience, expiry, rotation, database reconnect and revocation.
- [ ] Exercise unseal, quorum loss and snapshot restore without application-database dependency.
- [ ] Prove secret values never enter Git, pipeline logs, traces or unrestricted ConfigMaps.
