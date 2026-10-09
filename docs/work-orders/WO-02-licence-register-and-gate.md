# WO-02: Licence register and CI licence gate

**Status:** Approved for implementation (owner, 2026-10-08) · **Phase:** 0 · **Author:** Claude · **Implementer:** Codex
**Branch:** `codex/wo-02-licence-gate` · **Decision:** ADR-0030

## Goal

Every third-party component has a recorded SPDX licence and class, and CI fails on anything
unlisted or blocked.

## Verified context

Components are pinned in these places:
- **Lock files:** `lab/wsl/platform-artifacts.lock.json`, `lab/wsl/endpoints/artifacts.lock.json`,
  `lab/wsl/console/artifacts.lock.json`, `lab/wsl/localstack/artifacts.lock.json`,
  `deploy/registry-images.lock.json` and `console/image.lock.json`.
- **Package manifests:** `console/package-lock.json` (npm) and the pip requirement files under `tools/ci/` and `module-5a/`.
- **Vendored charts:** `module-*/vendor/`.

Upstream licence files already vendored include `module-*/vendor/LICENSE-Apache-2.0.txt`.

## Scope

1. `security/licence-policy.json`:
   - allowed SPDX IDs: MIT, MIT-0, Apache-2.0, BSD-2-Clause, BSD-3-Clause, ISC, 0BSD, PostgreSQL;
   - the exception list: OpenBao, MPL-2.0, ADR-0030;
   - the blocked list: AGPL-*, GPL-*, LGPL-*, SSPL-1.0, BUSL-1.1, Elastic-2.0, and "account-gated".
2. `security/licence-register.json` with a JSON Schema (`security/licence-register.schema.json`). Each entry records:
   - `ecosystem` (oci-image, helm-chart, manifest, npm, pip, github-action, tool), `name`, `version` and `spdx`;
   - `class` (allowed, exception, blocked, pending-removal) and `licenceSource` (a URL to the LICENSE file at that version);
   - `verifiedOn`, plus `adr` and `expires` when the class is exception or pending-removal.
3. `tools/ci/check_licences.py`. It runs offline and enumerates components from the files above:
   - **npm:** read the per-package `license` field in `package-lock.json`.
   - **Images, charts and manifests:** read the lock files.
   - **pip:** read pinned names and versions.

   It fails when a component has no register entry, the class is blocked, a pending-removal entry has
   passed its `expires` date, or an SPDX ID is outside the policy. Its output is a JSON report for the CI evidence artifact.
4. Initial classes:
   - Grafana: pending-removal (WO-07).
   - LocalStack: pending-removal (WO-06).
   - OpenBao: exception (ADR-0030).
   - Spinifex references in Module 5b: blocked, marked reference-only and not deployed.

   Expiry is 60 days for both pending-removal entries.
5. Wire the check into `tools/ci/run_checks.py` for the **candidate revision only**. Historical
   baselines in `tools/ci/pr-baselines.json` predate the policy and must still pass.
6. Add unit tests in `tools/ci/tests/` covering a missing entry, a blocked class, an expired
   pending-removal, a disallowed SPDX ID, and the npm and lock-file parsing.

## Out of scope

Network lookups in CI (the register is the authority). Removing components, which is done in WO-06 and WO-07.

## Acceptance criteria

- The PR gate is green, and the report artifact lists every component with its class.
- Test fixtures prove each failure mode.
- `README.md` links to the register and the policy.

## Owner actions

Review and approve the initial register in the PR.

## Report back

The component count by ecosystem and class, any component whose licence could not be verified
(mark it `pending-removal` or ask), and deviations.
