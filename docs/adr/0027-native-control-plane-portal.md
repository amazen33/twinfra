# ADR-0027: Native vCloud portal with isolated realm identity

**Status:** Accepted for local WSL implementation and live acceptance
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
HttpOnly session and scrubs spoofed headers. The read-only Python BFF repeats
claims/roles checks and is reachable only from APISIX under Cilium. It trusts
gateway signature validation; its decoded identity header is not a separately
signed token. Expose no JWT/cookie/emulator credential to browser code.

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

Static CI and live browser acceptance are separate. Negative role access,
spoofed headers and post-logout rejection are required. Endpoint reconciliation
is paused only for the candidate and restored after publication. Portal GitOps
is opt-in and excludes private/bootstrap resources. See the
[runbook](../../../console/README.md) and
[acceptance record](../../acceptance/vcloud-console-2026-10-08.md).
