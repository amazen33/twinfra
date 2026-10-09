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

## Amendment 1 (2026-10-09, architect; effective when the owner approves ADR-0042)

Codex stopped on three policy conflicts. ADR-0042 resolves them, so this work order changes as follows.

1. **Policy file.** In `security/licence-policy.json`:
   - add `BlueOak-1.0.0` and `CC0-1.0` to the permitted SPDX IDs;
   - add the class `build-tool` (permitted: the permitted list plus `MPL-2.0`, `LGPL-*`, `GPL-*`; AGPL, SSPL, BUSL-1.1, Elastic-2.0 and account-gated stay blocked);
   - add the class `reference-only` with `referenceOnlyPaths: ["module-5b/"]` and a 60-day maximum expiry.
2. **Register entries.**
   - ShellCheck 0.11.0: `build-tool`, GPL-3.0, from `tools/ci/toolchain.lock.json`. Do the same for any other CI binary: classify it as `allowed` or `build-tool`.
   - The 24 `lightningcss*` packages: `build-tool`, MPL-2.0. `lru-cache` is `allowed` (BlueOak-1.0.0) and `mdn-data` is `allowed` (CC0-1.0).
   - Spinifex in `module-5b/artifacts.lock.json` and `module-5b/vendor/spinifex.toml.gz`: `reference-only`, AGPL-3.0, expires 60 days from merge.
3. **Gate rules to add to `tools/ci/check_licences.py`:**
   - an npm `build-tool` entry must have `dev: true` and must not be reachable from the production dependency tree (`react`, `react-dom`);
   - a binary `build-tool` entry must appear only in `toolchain.lock.json`;
   - fail when a `reference-only` artifact is outside `referenceOnlyPaths` or is referenced by a deployable lock, manifest, image list or GitOps source;
   - fail on any blocked licence in the `build-tool` class (AGPL, SSPL, BUSL, Elastic, account-gated).
4. **Do not register mentions.** The word "spinifex" in prose, profiles or disabled switches is not a component. Register only things pinned in a lock file, image, chart, manifest, package or vendored file.
5. **Docs.** Add `docs/adr/0042-build-time-tools-and-reference-only-artifacts.md` (copy from `E:\vcloud-handoff\adr\ADR-0042-build-time-tools-and-reference-only-artifacts.md`, fixing relative links) and add it to the ADR index as Accepted (owner). ADR numbers 0036-0041 are reserved for records that other work orders add; do not renumber. Add an "Amended by ADR-0042" line at the top of ADR-0030, as ADR-0010 does for ADR-0034.
6. **Tests.** Add cases for: a build-tool npm entry that is not dev-only (fail); a GPL tool in the production class (fail); AGPL as a build-tool (fail); a reference-only entry outside `module-5b/` (fail); and a valid entry for each class (pass).
7. **Follow-up (separate work order, not in this PR):** remove `module-5b/vendor/spinifex.toml.gz` and the Spinifex pin from Module 5b.

## Amendment 2 (2026-10-09, architect; effective when the owner approves ADR-0043)

Codex found four runtime packages in the Module 5a image that no class allows. ADR-0043 handles them as time-boxed exceptions.

1. **Register four exceptions**, class `exception`, `adr: 0043`:
   - E-1 `psycopg` 3.3.6, E-2 `psycopg-binary` 3.3.6, E-3 `psycopg-pool` 3.3.3 (all LGPL-3.0-only);
   - E-4 `certifi` 2026.7.22 (MPL-2.0).

   Each has `expires` set to the earlier of 120 days from merge and the enabling of Module 5a.
2. **Gate rule.** Fail when `module-5a/config/rag.yaml` has `enabled: true` while E-1, E-2 or E-3 is still in the register.
   Add a test with `enabled: false` (pass) and `enabled: true` (fail).
3. **Image obligations.** Add a licence notice to the Module 5a image build: package, version, licence and source URL for each of the four,
   plus the full licence texts under `/usr/share/licenses/`. Keep the image offline-buildable, as it is today.
4. **Docs.** Add `docs/adr/0043-module-5a-runtime-exceptions.md` (copy from
   `E:/vcloud-handoff/adr/ADR-0043-module-5a-runtime-exceptions.md`, fixing relative links) to the ADR index as Accepted (owner).
   Add an "Amended by ADR-0043" line at the top of ADR-0042.
5. **Do not replace `langchain-postgres` in this PR.** That is a separate follow-up work order, before Module 5a is enabled.
6. **Scope reminder.** All work is in the Twinfra repository (`E:/vCloud`). IOT-EE is suspended and out of scope.

## Amendment 3 (2026-10-09, architect; effective when the owner approves ADR-0044)

Codex's consolidated audit (`E:/vCloud/.build/wo-02-audit/REPORT.md`) found conflicts that Amendments 1 and 2 did not cover.
ADR-0044 decides all of them. Implement the following, **superseding any earlier rule it contradicts**.

1. **Policy file** (`security/licence-policy.json`):
   - SPDX evaluation with OR, AND and WITH as in ADR-0044 decision 1; permitted exceptions `GCC-exception-3.1` and `LLVM-exception`.
   - Add to the permitted list: `PSF-2.0`, `Python-2.0`, `CNRI-Python`, `Zlib`, `Unlicense`, `BSL-1.0`, `BSD-3-Clause-Open-MPI`, `ICU`
     (plus BlueOak-1.0.0 and CC0-1.0 from Amendment 1). `BSL-1.0` is Boost, not `BUSL-1.1`: keep them distinct.
   - Classes: `allowed`, `build-tool`, `weak-copyleft` (unmodified MPL-2.0 only), `base-os`, `operator-pulled`, `disabled-module`,
     `exception` (ADR-0030 and ADR-0043), `pending-removal`, `blocked`.
   - Replace `referenceOnlyPaths` with `disabledModules`: `module-5a/` (switch: `enabled` in `module-5a/config/rag.yaml`) and
     `module-5b/` (switch: offloading, quotas and replicas in `module-5b/reference-profile.json`).
2. **Register entries**, using exact pinned versions and the evidence in the audit report:
   - the nine Module 5a distributions: `typing-extensions`, `greenlet`, `regex` and `torch` evaluate to `allowed` under decision 2;
     `orjson`, `tqdm` and `certifi` are `weak-copyleft`; `numpy`, `scipy` and `scikit-learn` are `disabled-module` (bundled LGPL-2.1 and GCC-exception libraries);
   - psycopg, psycopg-binary, psycopg-pool: `exception` (ADR-0043, unchanged);
   - Redis 8.2.3: `pending-removal`, expires 60 days from merge, with the three places it is pinned; WO-25 replaces it with Valkey;
   - BusyBox 1.37.0 and other distribution base images: `base-os`; apt packages installed into shipped images: `base-os` with a baseline finding for exact version pins;
   - CUDA 12.4.1 base image: `operator-pulled`, with a gate rule that fails if the GPU switch defaults to on;
   - OpenBao server, Helm chart 0.30.2 and CSI provider 2.0.3: `weak-copyleft` (the existing OpenBao exception stays recorded);
   - `robust-predicates` (Unlicense), CPython 3.14.1 (PSF), jq 1.8.2 (build-tool, with its incorporated terms): `allowed` or `build-tool` as appropriate;
   - every pinned Spinifex artifact (`spinifex.toml`, `awsgw.toml`, `spinifex-daemon.service`, `definitions.go`,
     `run_instances_clienttoken_test.go`, `LICENSE`): `disabled-module`, AGPL-3.0, listed for removal by WO-26.
3. **Register boundary** (ADR-0044 decision 8): register locked or rendered deployment inputs only. Vendored defaults that site
   configuration disables or overrides are baseline entries (`inert-default`), not components, until they appear in rendered output.
4. **Baseline** (`security/licence-baseline.json`, ADR-0044 decision 9): create it for the items that cannot be closed in this PR
   (exact apt pins, image SBOM evidence, version-resolved licence sources for the `master`-URL Kubernetes schemas, inert vendored defaults).
   Every entry has an owner, the evidence needed, and `expires` within 90 days. It may never contain a known AGPL, SSPL, BUSL,
   Elastic or EULA licence in a deployed component, except Redis under decision 5.
5. **Gate behaviour** in `tools/ci/check_licences.py`:
   - fail on any finding absent from the register or baseline, on an expired entry, on a blocked licence in a deployed component, and on
     a build-tool or weak-copyleft entry that breaks its conditions;
   - for `disabled-module` entries: report them in the evidence artifact and pass, but **fail if the module's switch is on while any of them is open**;
   - print the open baseline and `pending-removal` entries and their expiry dates in the CI summary.
6. **Tests:** SPDX OR, AND and WITH cases (including `MPL-2.0 AND (Apache-2.0 OR MIT)` passing only as `weak-copyleft`); a new unregistered
   component (fail); an expired baseline entry (fail); a disabled module with its switch on (fail) and off (pass); the GPU default on (fail);
   Redis registered as `pending-removal` passing before expiry and failing after; AGPL in a deployed image (fail).
7. **Docs:** add `docs/adr/0044-licence-gate-scope-and-classes.md` (copy from `E:/vcloud-handoff/adr/ADR-0044-licence-gate-scope-and-classes.md`,
   fixing relative links) to the ADR index as Accepted (owner); add "Amended by ADR-0044" lines at the top of ADR-0030, ADR-0042 and ADR-0043.
8. **New stop rule for this work order:** do not stop for a finding that fits an existing class or the baseline rules above.
   Record it and keep going, and list it in the PR. Stop only for a **known AGPL, SSPL, BUSL, Elastic or EULA licence in a deployed
   component that is not named in ADR-0044**, or for anything that would change an owner decision.
9. **Not in this PR:** WO-25 (Redis to Valkey), WO-26 (remove Spinifex), WO-27 (`langchain-postgres` replacement). Do not change those components here.
10. **Scope reminder.** All work is in the Twinfra repository (`E:/vCloud`). IOT-EE is suspended and out of scope.
