# WO-11: Console roles, forgery protection and audit

**Status:** Approved for implementation (owner, 2026-10-08) · **Phase:** 1 · **Author:** Claude · **Implementer:** Codex
**Branch:** `codex/wo-11-console-foundation` · **Decision:** ADR-0035 · **Depends on:** WO-04

## Goal

Lay the groundwork for a self-service console without enabling writes yet. The write path arrives with the
vCloud gateway in Phase 3, so no temporary write path is built here.

## Verified context

- `console/server.py` lines 175-181 return `405 Read-only API` for POST, PUT, PATCH and DELETE.
- ADR-0027 defines the roles `console.viewer` and `console.admin`. The Keycloak client is configured through
  `deploy/console/keycloak-client.json` and `tools/configure_console_identity.py`.
- ADR-0035 (accepted) adds `console.operator` and the guardrails.

## Scope

1. **Roles.** Add `console.operator` to the client configuration. Implement a single role-to-capability table
   in the backend and in `console/README.md`:
   - viewer: read only;
   - operator: create and change in own account (disabled until Phase 3);
   - admin: everything, including approvals (disabled until Phase 3).
2. **Feature switch.** `CONSOLE_WRITES_ENABLED`, default `false`. While it is off, state-changing methods keep returning 405.
   While it is on (tests only in this work order), they go through the checks below and then return
   `501 Not Implemented` until Phase 3.
3. **Forgery protection** for every state-changing request: `Origin` (or `Sec-Fetch-Site`) must be
   same-origin, and a per-session token must be sent in a header (double-submit or a server-held session value). Session cookies
   stay HttpOnly and SameSite. HTTP cookies remain the documented loopback-lab exception from ADR-0027.
4. **Audit trail.** One structured JSON event per state-changing attempt, with: time, subject, roles, action, target,
   result, reason and correlation ID. No token, cookie or secret values. Events go out through the logs pipeline from WO-10
   when it is present, and to stdout otherwise.
5. **ADR text.** Make sure ADR-0026 and ADR-0027 carry their partial-supersession status lines (done in WO-03 if that merges first).

## Out of scope

Any real create, change or delete operation; the STS sign-in; the AWS SDK for JavaScript. All of these are Phase 3.

## Acceptance criteria

- Tests with the switch off: every write method returns 405.
- Tests with the switch on:
  - a viewer write gets 403 and is audited;
  - a request with a missing or wrong token, or a cross-origin `Origin`, gets 403 and is audited;
  - an operator write that passes the checks gets 501 and is audited.
- `kubectl auth can-i --list` for the console service account shows no write verbs. Attach the output as evidence.
- Browser acceptance still passes. Receipt: `docs/acceptance/console-foundation-<date>.md`.

## Owner actions

Approve the Keycloak client change and the lab redeploy.

## Report back

The capability table, the forgery-protection design chosen, and sample audit events with values redacted.
