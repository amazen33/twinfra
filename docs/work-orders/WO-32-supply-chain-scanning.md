# WO-32: Supply-chain vulnerability scanning in CI: PR gate, nightly re-scan, weekly upstream watch

**Status:** Approved for implementation (owner, 2026-10-13) · **Phase:** 2
**Author:** Claude · **Implementer:** Codex · **Branch:** `codex/wo-32-supply-chain-scanning` · **Decision:** ADR-0049 (add it to `docs/adr/` in this PR)
**Depends on:** WO-31 merged through PR #48. Doesn't touch the Dell.

## Why

See ADR-0049. A baseline scan run on 2026-10-13 outside CI found:
- **Lockfiles:** 12 findings, all in `tools/ci/mermaid/package-lock.json` (`lodash-es` 4.17.21, with one High at CVSS 8.1; `mermaid` 11.12.0; `katex`). The console's npm and pip lockfiles, `tests/`, `module-5a` and `module-5b` were clean.
- **Images:** the per-image results are reported separately; they seed the first exception list.

## Scope

1. **Tooling.**
   - Pin Grype v0.119.0, Syft v1.52.0 and OSV-Scanner v2.6.0 (`linux_amd64`) in `tools/ci/toolchain.lock.json`, by SHA-256, verified against each release's checksum file.
   - Add licence-register entries: Apache-2.0, build-tool class.
   - Don't use any Aqua/Trivy action or image.
2. **`tools/ci/supply_chain.py`: one entry point with subcommands `inventory`, `sbom`, `scan`, `evaluate`, `report` and `watch`.**
   - **Inventory:** every image in `deploy/common/bootstrap-images.lock.json` and `deploy/common/images.lock.json`, scanned as `linux/amd64` by digest, plus the two built images.
     - Scan the built images from their reproducible archives (`oci-archive:`) when `.build/dev-images/` exists.
     - Otherwise scan their pinned inputs: the Python base, the CNPG PostgreSQL base and pgvector.
   - **Lockfiles:** all of them in the repository, with OSV-Scanner `--no-resolve`.
   - **SBOMs:** Syft per digest, cached by digest (`actions/cache`), with a CycloneDX copy attached as a run artefact. No SBOM is committed.
   - **Evaluation (ADR-0049 section 3):**
     - **KEV:** download CISA's KEV JSON with checksum logging and match by CVE alias.
     - **Fix state:** from Grype and OSV.
     - **First-seen dates:** read from the previous state of the tracking issue, with a fallback when the issue is missing.
   - **Exceptions:** `security/vulnerability-exceptions.json` with a schema and expiry of 90 days at most. An expired or malformed entry fails.
3. **Workflows.** Extend `.github/workflows/pr-tests.yaml` or add `supply-chain.yaml`. Every third-party action is pinned by full commit SHA.

   | Job | Trigger | Permissions | What it does |
   | --- | --- | --- | --- |
   | `scan-pr` | `pull_request` (never `pull_request_target`) | `contents: read`, no secrets | Scans the changed locks, receipts and lockfiles (all of them if the policy or tooling changed), evaluates the gate, writes the job summary |
   | `scan-nightly` | `schedule` (02:30 UTC) and manual dispatch | `contents: read` | Full inventory with a fresh database; uploads the report artefact |
   | `report-issue` | after `scan-nightly` | `issues: write` only | Creates or **edits in place** one issue, "Supply-chain scan: open findings" (label `security`), from the artefact. Runs no scanner |
   | `watch-weekly` | `schedule` (Monday 03:00 UTC) and manual dispatch | `contents: read`, then a separate `issues: write` reporting job | For each pinned image and CI tool, finds the newest release at least 14 days old, scans it, and lists "current versus candidate" findings in one issue, "Upstream updates available". **Doesn't** edit locks or open PRs yet; lock updates go through work orders, because renders and checksums depend on them |
4. **First exception list.** No blanket waiver (ADR-0049 section 4, as revised 2026-10-13). Generate `security/vulnerability-exceptions.json` from the first full run, for every finding that would block:
   - **Critical:** one entry per vulnerability per image. Each has its own reason (fix version, exposure in dev, the plan), `owner: "amazen33"`, and an expiry of **2026-11-12** (30 days). The reason references **WO-34**.
   - **High:** may be grouped per image and package, with the reason "patched by WO-34" and an expiry of **2026-12-12** (60 days).
   - The schema enforces the maximum expiry per severity: Critical 30 days, High 60, other 90.
   - Every entry starts with `approvedBy: "pending-owner"`. The PR lists them grouped by image. The owner approves by changing `approvedBy` in review. Until then, the gate treats `pending-owner` as valid only on this PR's branch.

   **Issue content and reproducibility** (ADR-0049 section 5):
   - Each issue update shows the timestamp, the scanner versions, the vulnerability database's build time, the scanned digests, the summary, new findings, resolved findings and exceptions expiring within 14 days.
   - Each run uploads a reproducibility JSON with the digests, tool versions and checksums, the database timestamp and the configuration.
   - The PR gate compares the PR head with its base: introduced findings count as new.
5. **ADR-0044.** Add the line `Amended by ADR-0049 (supply-chain scanning replaces the "ADR-0014" reference).` at the top of `docs/adr/0044-…`, and add ADR-0049 to the ADR index.
6. **Docs.** `docs/supply-chain-scanning.md` covers:
   - how to read the issue;
   - how to add an exception;
   - how to run locally on Linux or WSL (Syft can't pull images on Windows);
   - the gate policy table.
7. **Tests (offline, with fixtures):**
   - **Gate:**
     - a KEV finding blocks even without a fix;
     - a Critical with a fix blocks;
     - a High with a fix: a PR-introduced one blocks, and a pre-existing one blocks after 14 days;
     - a finding with no fix only reports;
     - an expired exception fails;
     - a malformed exception fails.
   - **Inventory:** it covers every lock entry, and built images fall back to their inputs.
   - **Workflow linting (actionlint):**
     - permissions are as in the table;
     - no `pull_request_target`;
     - every `uses:` is pinned to a 40-hex SHA;
     - scanner jobs reference no secrets.
   - **Tool verification:** a tampered binary fails its checksum.
   - **Exceptions:**
     - a Critical exception with an expiry over 30 days is rejected; a High over 60 days is rejected;
     - a grouped Critical exception is rejected;
     - an exception for a fixable finding without a work-order reference is rejected.
   - **Issue body:** "new" and "resolved" are computed correctly between two fixture runs.

## Out of scope

Scanning inside the cluster, CVEs in the Dell's host OS, publishing images to GHCR, and automatic lock-update PRs.

## Acceptance criteria

- **Gate:** the PR gate is green, including the licence gate and the six historical baselines.
- **Scan run:** the first full run on the PR produces the report and the exception list.
- **After merge:**
  - a manual `scan-nightly` dispatch creates the "open findings" issue, and a second dispatch **edits the same issue**;
  - a manual `watch-weekly` dispatch creates the "upstream updates" issue.

## Report back

The changed files, the full findings table per image, the proposed exception list, the issue links after the manual dispatches, and any deviation.
