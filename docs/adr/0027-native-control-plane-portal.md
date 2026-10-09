# ADR-0027: Native vCloud portal with isolated realm identity

**Status:** Accepted (lab) — [vcloud-console-2026-10-08.md](../acceptance/vcloud-console-2026-10-08.md); native portal identity/browser acceptance. Partly superseded by [ADR-0035](0035-console-self-service.md) for the read-only decision only; identity, cookie and isolation decisions remain in force.
**Date:** 2026-10-08

## Context and decision

The gated console reference does not establish a working browser login.
Rewriting arbitrary admin UIs cannot reliably fix absolute assets, callbacks,
cookies or CSP. The operator approved a separate `vcloud-admin` account in
the `vcloud` realm, with a temporary password stored only in Kubernetes Secret.

Deploy a responsive React/TypeScript + Tailwind portal under
`http://localhost:18080/console/` through the existing APISIX controller.
Native views expose namespace health, dual-emulator S3/EC2/DynamoDB, Argo status
and Keycloak identity. Keep full third-party administration at supported
separate endpoints. Retain SAMEORIGIN and CSP; optional original MIT legacy
views support explicit proxy prefixes. The previous `console.vcloud.local`
reference remains gated and is not this implementation's activated hostname.

Use confidential code flow, PKCE S256, exact callback and validated TLS,
signature, issuer, audience and client roles. APISIX owns the encrypted
HttpOnly session and scrubs spoofed headers. The read-only Python BFF verifies
the access token independently and is reachable only from APISIX under Cilium.
APISIX forwards the signed `X-Access-Token`; the BFF verifies RS256/ES256 against
cached Keycloak JWKS over the validated private TLS backchannel, exact issuer,
console audience or authorized party, time claims and client roles. Expose no
JWT/cookie/emulator credential to browser code.

`console.viewer` and `console.admin` grant portal access only. The dedicated
realm account receives `console.admin`, required password change and MFA,
without master-realm, realm-management or Kubernetes admin authority. Private
values remain in RAM and encrypted Kubernetes Secrets; no Git, host plaintext,
environment/argv credentials or private logs.

Keycloak's dynamic TLS backchannel preserves its canonical browser issuer.
APISIX mounts only the public lab certificate and uses
`apisix.ssl.ssl_trusted_certificate`. URI-only logs exclude OAuth query values.
HTTP cookie settings are a loopback lab exception; production requires HTTPS,
Secure cookies and separate acceptance.

## Alternatives and consequences

| Option | Assessment |
| --- | --- |
| Blind iframe proxies with deleted CSP | Fragile callbacks/assets and excess admin exposure; rejected |
| Master administrator for portal sessions | Mixed identity boundaries and excess authority; rejected |
| Native views and constrained BFF | Selected; consistent navigation and explicit read-only contracts |

The portal is MIT; upstream projects retain their licenses. Emulator state is
ephemeral. No real VM provisioning, MinIO server, Spinifex offload or OpenBao
unseal is implied. Strict PSS, immutable digest/cache-first images, no host
mounts, bounded responses and fixed backends are enforced and tested.

WO-04 removes reliance on gateway signature validation alone. Missing/invalid
tokens receive 401; independently verified roleless tokens receive 403. Unknown
key IDs can refresh the cache at most once per minute; stale keys and TLS/fetch
failures fail closed. The BFF mounts only the existing public Keycloak certificate
and gains only scoped Keycloak TLS egress. This adds hash-pinned PyJWT,
cryptography and their registered dependencies; no login/cookie or write API
change is included. WO-04's browser and direct-backend live acceptance remain
Pending on VM `lab-1` after WO-21; the earlier WSL receipt is historical evidence.

Static CI and live browser acceptance are separate. Negative role access,
spoofed headers and post-logout rejection are required. Endpoint reconciliation
is paused only for the candidate and restored after publication. Portal GitOps
is opt-in and excludes private/bootstrap resources. See the
[runbook](../../console/README.md) and
[acceptance record](../acceptance/vcloud-console-2026-10-08.md).
