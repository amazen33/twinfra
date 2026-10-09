# ADR-0013: Keycloak for human identity and OIDC

**Status:** Accepted (lab) — [vcloud-console-2026-10-08.md](../acceptance/vcloud-console-2026-10-08.md); portal PKCE/MFA, logout and roleless denial; cluster RBAC pending.
**Date:** 2026-10-05  
**Deciders:** vCloud platform owner and Principal Architect  
**Selection:** Keycloak is required by Module 1.  
**Classification:** Constraint — selection required by Module 1; alternatives assess implementation, not an open component competition.
**Scope:** [SSoT and shared implementation contract](README.md).

## Context

Users and operators need a consistent login and application-role contract across sites.
Keycloak exposes OIDC discovery, authorization, token and key endpoints. Client token
validation must check the intended audience and issuer. See
[OIDC application integration](https://www.keycloak.org/securing-apps/oidc-layers).

## Decision

- Run non-root Keycloak in `platform-services`, using a dedicated PostgreSQL database
  and role. Use stable HTTPS issuer `auth.vcloud.example.com` with an explicit hostname,
  trusted proxy configuration and verified TLS. Keep administrative interfaces private.
  Separate public realm paths from API routes that require bearer tokens.
- Define a vCloud realm, controlled tenant/group membership and application roles.
  Use authorization code with PKCE for interactive clients, short token lifetimes and
  MFA for administrators. Disable obsolete/unsafe grant flows unless a separately
  justified integration requires them. Configure redirects and allowed origins explicitly.
- APISIX validates tokens and API permissions. The RAG service validates its audience
  and derives tenant identity from verified claims before accessing documents. A tenant
  request parameter cannot override membership. Grafana/Argo CD use separate OIDC clients
  and least-privilege role mappings.
- Kubernetes RBAC/service-account tokens, OpenBao workload policies and Spinifex/cloud
  IAM remain separate authorization domains. Human federation does not automatically
  confer cluster-admin, secret access or cloud provisioning permissions.
- Configure the selected Keycloak release's supported HA/cache discovery and database
  migration process; explicitly admit cluster traffic rather than broad intra-namespace
  networking. See [production configuration](https://www.keycloak.org/server/configuration-production).

## Options considered

| Option | Benefits | Costs and limits |
| --- | --- | --- |
| Keycloak OIDC | Common identity/role surface across sites | Database, HA and issuer availability operations |
| Provider-native identity per site | Managed identity features | Different local/cloud federation and role contracts |
| Custom authentication inside each app | Local control | Duplicates sensitive identity and session implementation |

## Trade-off analysis

Central identity reduces duplicated login code. Authorization remains local to each
resource domain; a valid login is insufficient to access every tenant document or HPC job.

## Consequences

Existing locally validated tokens may remain valid until expiry during an IdP outage;
login/refresh and unavailable key lookup fail closed. Do not promise immediate JWT
revocation without an explicit introspection/revocation design.

## Action items and acceptance

- [ ] Pin Keycloak, configure HA/schema upgrades and protect bootstrap administrator secrets.
- [ ] Test wrong issuer/audience, expiry, disabled users, signing-key rotation and IdP outage.
- [ ] Verify tenant boundaries and distinct Argo/Grafana operator role mappings.
- [ ] Restore realm/database state and verify the issuer remains stable.
