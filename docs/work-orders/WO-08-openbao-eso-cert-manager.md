# WO-08: OpenBao activation, External Secrets Operator, cert-manager

**Status:** Approved for implementation (owner, 2026-10-08) · **Phase:** 1 · **Author:** Claude · **Implementer:** Codex
**Branch:** `codex/wo-08-secrets-and-certs` · **Review finding:** R3 · **Decision:** ADR-0030 (OpenBao exception)

## Goal

Workloads get short-lived secrets from OpenBao through External Secrets Operator, and
certificates renew themselves.

## Verified context

- OpenBao is deployed in `platform-services` with PostgreSQL storage. It is uninitialized and sealed, waiting for four
  operator PGP public keys (`MILESTONES.md`; `docs/acceptance/wsl-2026-10-07.md`).
- The tooling exists: `lab/wsl/openbao-init.sh`, `tools/openbao_pgp_init.py`, and the Makefile target `wsl-openbao-init`.
- ADR 0021 (`docs/adr-0021-openbao-dynamic-secrets.md`) designs dynamic database credentials, and `module-4a/` holds the reference configuration.
- Lab serving certificates last 30 days and are created by hand (`lab/wsl/prepare-tls.sh`; `lab/wsl/PLATFORM.md`).

## Scope

1. **Key ceremony support.** Write a checklist in `docs/runbooks/openbao-key-ceremony.md`:
   - who holds which share, and that only public PGP keys are ever submitted;
   - verification steps, and storage of the encrypted shares outside Git and outside the database OpenBao unlocks;
   - the unseal and recovery drill.

   The owner runs the ceremony. Codex runs only the scripted steps, after approval, and never handles private keys.
2. **External Secrets Operator.** The latest release at least 14 days old (2.12.0 was published on 2026-10-06, so pick the previous
   release or wait). Digest-pinned. A ClusterSecretStore for OpenBao using Kubernetes auth, with policies scoped by namespace
   and service account.
3. **Dynamic database credentials** (ADR 0021): the OpenBao database engine with a role for one workload,
   either the demo app or a new test workload. Lease TTL and rotation configured. ESO syncs the credential, and the workload reconnects after rotation.
4. **cert-manager** v1.21.x (latest patch). Start with an OpenBao PKI issuer, or a lab CA issuer as an
   interim step with OpenBao PKI in the same PR if time allows; record the choice. Move the console, APISIX and Keycloak
   backchannel certificates and the Argo repo-server certificate to cert-manager, one at a time. Each move gets a check that verification still works.
5. Network policies for every new component, kept default-deny, with exact allow rules. Add licence-register entries.

## Out of scope

KMS, Secrets Manager and SSM APIs (Phase 3), and production key custody.

## Acceptance criteria

- OpenBao is initialized with PGP-encrypted shares, and no plaintext share exists anywhere. A seal and unseal drill passes.
- An ESO-synced secret appears. The database credential rotates during a test window, and the workload stays healthy.
- A test certificate with a 1-hour duration renews automatically. Migrated endpoints still pass their TLS verification checks.
- Receipt: `docs/acceptance/secrets-and-certs-<date>.md`.

## Owner actions

Supply the four public PGP keys and run the ceremony. Approve each live step.

## Report back

Versions and digests, the issuer chosen, which certificates moved, and the rotation evidence.
