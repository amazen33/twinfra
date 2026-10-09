# ADR-0003: Knative Serving for HTTP application revisions

**Status:** Proposed  
**Date:** 2026-10-05  
**Deciders:** vCloud platform owner and Principal Architect  
**Selection:** Knative Serving is required by Module 1.  
**Scope:** [SSoT and shared implementation contract](README.md).

## Context

The RAG API needs controlled revision rollout, bounded concurrency and elastic CPU
capacity. Knative's request path includes an ingress adapter, an optional Activator,
queue-proxy and the application; bypassing that path breaks scale-from-zero behavior.
See [Serving architecture](https://knative.dev/docs/serving/architecture/).

## Decision

- Run the non-root LangChain HTTP service as a Knative Service in `workload-apps`.
  Keep PostgreSQL, Kafka, OpenBao and GPU inference outside Knative's scale-to-zero policy.
- Select **Kourier** as the supported Knative ingress adapter, private behind APISIX.
  Cilium supplies Pod networking and enforcement; it does not replace the Knative ingress
  adapter. Infrastructure placement targets `platform-services`, subject to the pinned
  release's supported namespace/RBAC configuration.
- APISIX forwards to Kourier, setting the reviewed Knative route Host header. Kourier
  forwards through Activator when needed, then queue-proxy to the selected revision.
  Expose the application Route only within the cluster; external clients use APISIX.
- Set measured concurrency, maximum replicas, request/stream timeouts and rollout
  traffic splits. Allow scale-to-zero for the CPU API only when the cold-start SLO permits
  it; otherwise keep a warm minimum. Argo CD owns Service intent, Knative owns revisions.

## Options considered

| Option | Benefits | Costs and limits |
| --- | --- | --- |
| Knative Serving with Kourier | Revision routing and request-aware scaling | Additional controller, gateway and queue-proxy dependencies |
| Deployment with HPA | Fewer components | Application rollout and scale-from-zero require other mechanisms |
| APISIX directly to revision pods | Shorter apparent path | Bypasses Knative routing/activation semantics; rejected |

## Trade-off analysis

Knative is justified for the HTTP application, while warm GPU Deployments avoid coupling
interactive requests to model download and GPU startup. Kourier and APISIX have distinct
ownership: Knative revisions versus external authentication and API policy.

## Consequences

Default-deny rules must admit gateway, Activator and queue-proxy traffic, probes and
controller/webhook communication. Enable and verify the selected release's internal
TLS mechanisms; TLS termination at APISIX alone does not encrypt the rest of the path.
Knative currently labels cluster-local and system-internal TLS experimental, and its
encryption overview identifies remaining unencrypted control traffic. Kourier encryption
is therefore a **production acceptance gate**, not an established zero-trust guarantee.
Pin and test certificate issuance/trust rotation and review the remaining control paths
before deployment; change the networking design by ADR if the selected release cannot
meet the threat model. See
[Serving encryption](https://knative.dev/docs/serving/encryption/encryption-overview/).

## Action items and acceptance

- [ ] Pin Serving/Kourier/queue-proxy images and validate `serving.knative.dev/v1`
  resources against their release schemas.
- [ ] Verify non-root gateway and sidecar profiles; inventory any new capability need
  separately rather than extending the approved Cilium exception implicitly.
- [ ] Test scale-from-zero, Host routing, private-service access, stream cancellation,
  timeouts and revision rollback through APISIX.
