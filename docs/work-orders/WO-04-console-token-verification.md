# WO-04: Console backend verifies signed tokens

**Status:** Approved for implementation (owner, 2026-10-08) · **Phase:** 1 · **Author:** Claude · **Implementer:** Codex
**Branch:** `codex/wo-04-console-jwt` · **Review finding:** R6

## Goal

The console backend accepts an identity only after it has cryptographically verified the token itself.
It stops relying on the network path alone.

## Verified context

- `console/server.py` lines 3-7 say the backend "does NOT independently verify" the gateway's
  base64 JSON `X-ID-Token`. `identity()` (line 38 onward) decodes it and checks roles.
- In `deploy/console/apisix-routes.yaml`, the `openid-connect` plugin has `set_id_token_header: true` and
  `set_access_token_header: false`. A guard (around line 30) strips client-supplied `X-ID-Token`,
  `X-Access-Token`, `X-Userinfo`, `X-Refresh-Token` and `X-Raw-ID-Token`.
- ADR-0027: confidential client, PKCE S256, validated TLS backchannel to Keycloak, and roles
  `console.viewer` and `console.admin` from `resource_access[<client>].roles`.

## Scope

1. In the route (and its generator, `tools/vcloud_console.py`), forward the signed access token in
   `X-Access-Token`. Keep stripping client-supplied identity headers. Stop using `X-ID-Token`.
2. In the backend, verify the access token on every request:
   - **Signature:** RS256 or ES256 only. Reject `none` and every HS* algorithm.
   - **Keys:** fetch Keycloak's JWKS over the existing validated private TLS backchannel. Cache it. Refetch on an unknown `kid`,
     rate-limited to at most once a minute.
   - **Claims:** `iss` must match exactly. `aud` or `azp` must identify the console client; add a Keycloak audience
     mapper if needed, through `tools/configure_console_identity.py`. `exp` and `nbf` are checked with at most 60 seconds of leeway.
   - **Roles:** read from `resource_access[<client>].roles`, as today.
3. Responses: a missing or invalid token gets 401 and the existing JSON error shape. A valid token without a role gets 403.
   Never log the token value.
4. Library: PyJWT with `cryptography`, pinned with hashes in the console requirements, with entries
   in the licence register (MIT; Apache-2.0 or BSD).
5. Update ADR-0027's consequences paragraph: "trusts gateway signature validation" becomes
   "verifies the access token independently". Update `console/README.md`.

## Out of scope

Write endpoints, which stay 405. Changing the login flow or session cookies.

## Acceptance criteria

- Unit tests in `tests/test_vcloud_console.py` cover:
  - accept: a valid token.
  - 401: a forged signature, an unknown `kid`, an expired token, a not-yet-valid token, a wrong issuer, a wrong audience,
    `alg: none`, an HS256 token signed with the public key as secret, a malformed header, and a missing header.
  - 403: no console role.
- Browser acceptance (`console/browser-acceptance.mjs`) passes in the lab: login, both emulator reads, logout, roleless denial.
- A live negative test: a request that reaches the backend directly with a hand-made header is refused.
- Receipt: `docs/acceptance/console-token-verification-<date>.md`.

## Owner actions

Approve the live redeploy of the console in the lab.

## Report back

The library versions and hashes, the Keycloak mapper change (if any), and the test matrix results.
