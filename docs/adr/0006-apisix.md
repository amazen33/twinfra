# ADR-0006: Apache APISIX as the external API gateway

**Status:** Accepted (lab) — [wsl-2026-10-07.md](../acceptance/wsl-2026-10-07.md); local CPU routing; production gateway acceptance pending.
**Date:** 2026-10-05  
**Deciders:** vCloud platform owner and Principal Architect  
**Selection:** APISIX Gateway is required by Module 1.  
**Classification:** Constraint — selection required by Module 1; alternatives assess implementation, not an open component competition.
**Scope:** [SSoT and shared implementation contract](README.md).

## Context

External clients need authenticated access, bounded requests and stable API routes.
APISIX supports Keycloak through its
[OpenID Connect plugin](https://apisix.apache.org/docs/apisix/plugins/openid-connect/).
Knative still needs its own supported revision-routing adapter.

## Decision

- Run non-root APISIX replicas in `platform-services`, listening on unprivileged
  container ports. Publish HTTPS `api.vcloud.example.com` through a site-specific load
  balancer; preserve private access for admin and observability endpoints.
- Select file-driven **standalone mode**, reconciled from Git through Argo CD. This
  avoids an additional APISIX etcd dependency and an independently writable Admin API.
  Non-secret route templates live in Git; a reviewed non-root runtime renderer reads
  scoped OpenBao secrets and writes final configuration into a memory-backed volume.
  Never place client/session secrets in Git or a public ConfigMap. See
  [deployment modes](https://apisix.apache.org/docs/apisix/deployment-modes/).
- Validate issuer, signature, expiry, audience and required scopes/roles. API requests
  use bearer-token enforcement and fail closed; browser login uses authorization code
  with PKCE where applicable. Configure TLS verification explicitly and a fixed redirect
  URI for browser flows. Strip untrusted identity headers; the application independently
  enforces tenant and document permissions.
- Forward RAG routes to private Kourier with the correct Knative route Host and path.
  Use reviewed [proxy rewriting](https://apisix.apache.org/docs/apisix/plugins/proxy-rewrite/).
  Configure streaming timeouts, size/concurrency limits and cancellation propagation.
  Do not blindly retry non-idempotent submissions or interrupted generation streams.
  Declare whether rate limits are per replica or global: global enforcement requires
  a reviewed shared-state/quota integration, rather than an assumed in-memory counter
  shared across gateway replicas.
- If the gateway publishes Keycloak at `auth.vcloud.example.com`, only the intended
  public realm/OIDC paths bypass API bearer enforcement; admin paths remain private.

## Options considered

| Option | Benefits | Costs and limits |
| --- | --- | --- |
| Standalone APISIX in front of Kourier | Clear Git ownership and common API policies | Runtime secret rendering and two routing layers |
| APISIX with separate etcd/control plane | Dynamic administrative API | Another quorum service and configuration writer |
| Expose Knative gateway directly | Fewer hops | Does not provide the selected centralized API contract |

## Trade-off analysis

Declarative gateway configuration fits GitOps; Kourier retains revision/activation
ownership. Gateway authentication cannot replace authorization inside the RAG service.

## Consequences

TLS must continue through the reviewed internal request path. Secret rotation needs
atomic config generation and rollback to a valid configuration, without reverting revoked
credentials. Keep gateway admin APIs disabled or private and narrowly authenticated.

## Action items and acceptance

- [ ] Pin APISIX/plugins and validate configuration as well as Kubernetes manifests.
- [ ] Test invalid issuer/audience, JWKS rotation, IdP outage and forged identity headers.
- [ ] Test Kourier Host routing, streaming, rate limiting and secret rotation on all replicas.
- [ ] Prove only HTTPS/public OIDC routes are externally reachable; no internal inference bypass.
