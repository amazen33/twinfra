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

## Amendment 1 (2026-10-16, architect; APPROVED by the owner 2026-10-16: threshold "2-of-3"): cairo-1, ADR-0054 and the toolchain-wave rule

The original text predates `cairo-1`, ADR-0046, ADR-0052, ADR-0054 and ADR-0049 Amendment 1. Where it says "lab", `platform-services` or `wsl`, read the dev environment `twinfra-dev-cairo-1` and namespace `twinfra-platform-services`. Names follow ADR-0038/0047.

1. **Order.** WO-08 comes first, because the Barman backup plugin (WO-09) needs cert-manager. Part 4 (cert-manager) is delivered first as its own PR so WO-09 can proceed; the rest follow.
2. **Verified context now.**
   - OpenBao (Deployment `twinfra-openbao`, PostgreSQL storage) is **uninitialised and sealed** on `cairo-1`.
   - The tooling is still the WSL-era `lab/wsl/openbao-init.sh` and `tools/openbao_pgp_init.py`. Port what is reusable to neutral locations (WO-28 deletes the WSL files).
   - Serving certificates come from the owner's name-constrained dev CA (WO-29), created by hand.
3. **Key ceremony.** Keep PGP-encrypted shares (the owner holds the private keys offline). Dev uses a **2-of-3 threshold** (owner decision 2026-10-16): the owner supplies **three public PGP keys**, any two unseal. Codex never handles private keys or shares.
   Store the three private keys in separate offline places, so one loss never locks the cluster. The runbook includes the recovery steps if one share is lost (rekey with the remaining two).
4. **cert-manager.**
   - **Issuer:** start with a CA issuer backed by the existing **name-constrained dev root CA** (the owner loads the CA key pair into a Secret, outside Git). OpenBao PKI becomes the issuer in a later PR after the ceremony.
   - Move certificates one at a time (Keycloak, OpenBao, the gateway, Argo CD) with a verification check after each. Keep the name constraints.
5. **Licences, vulnerabilities and tiers.**
   - cert-manager (Apache-2.0, CNCF Graduated), External Secrets (Apache-2.0, CNCF Incubating) and OpenBao (MPL-2.0, tier 3, recorded exception) are registered with `enterpriseGrade` records and climbing records per ADR-0054.
   - Pick the **newest eligible release** (at least 14 days old) with the best scan. If the only blocking findings are listed toolchain-wave advisories, use the ADR-0049 Amendment 1 rule: per-image entries (30 days Critical, 60 days High) approved by the owner as a batch in the PR, with the controls listed (cluster-internal, no Service exposed outside the namespace, egress limited).
   - If other findings remain, stop and report. Do not invent exceptions.
6. **Acceptance additions:** `host-check`-style checks that OpenBao is initialised and unsealed, a seal and unseal drill the owner witnesses, and a certificate with a 1-hour duration that renews on its own.
7. **Static first.** Codex prepares manifests, generators, tests, runbook and PRs without touching the Dell. The owner runs live steps after review: the ceremony, `stage-images --check` for new images (PR attestation required by `staging-check`), and the applies.

## Amendment 2 (2026-10-16, architect; effective when the owner approves ADR-0049 Amendment 1a): unblock the admission gate

Codex stopped because cert-manager v1.21.2 carries five stdlib Highs fixed in Go 1.26.9 (GO-2026-6605, 6607, 6608, 6609, 6613) that the narrow ID list did not name. They are the same wave.
1. **First, a standalone PR** (branch `codex/wo-09a-ladder-gate`, taken from your preserved work in draft PR #65 and its tests): ADR-0054 and ADR-0049 Amendment 1 and 1a into `docs/adr/` (Accepted for 0054 and Amendment 1; Amendment 1a once the owner approves), the licence policy and register schema for the tiers, `enterpriseGrade` and climbing records, the dated legacy backfill, and the toolchain-wave rule in the gate, with their tests. No Barman, backup or runtime change. Merge this first.
2. **Then cert-manager:** re-evaluate v1.21.2 under Amendment 1a. If every blocking finding qualifies, prepare the per-image, per-CVE entries as a batch for the owner (`approvedBy` empty), with the controls: cluster-internal, no Service outside the namespace, egress only to the API server. If any finding does not qualify, stop and report only those.
3. The rest of Amendment 1 stands. ESO and OpenBao follow as a separate PR.
