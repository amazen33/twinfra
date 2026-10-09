# ADR-0044: Licence gate scope, SPDX evaluation and the remaining classes (amends ADR-0030, ADR-0042, ADR-0043)

**Status:** Accepted (owner, 2026-10-09).
**Author:** Claude (platform architecture). **Decider:** Ahmed Mazen, Owner and Product Owner.
**Source:** Codex's consolidated audit, `E:/vCloud/.build/wo-02-audit/REPORT.md`. This record answers every finding in it.

## Principles

- **Never relax the promise for what runs.** Anything deployed stays permissive, with the named exceptions below.
- **Say what is blocked.** Findings we cannot close now go into a dated baseline. The gate prints them, fails on new ones,
  and fails when one expires. Nothing is silently passed or silently exempt.
- **The gate checks what ships or runs**, not every file that mentions a name.

## Decisions

1. **SPDX expressions are evaluated, not string-matched.**
   - `A OR B` passes if any alternative passes. `A AND B` passes only if every conjunct passes.
   - `X WITH Y` passes only if `X` passes and `Y` is on the permitted-exception list: `GCC-exception-3.1`, `LLVM-exception`.
   - Evidence comes from the exact pinned version (release metadata or the packaged licence file), never from a branch-head URL.
2. **Permitted list additions:** `PSF-2.0`, `Python-2.0`, `CNRI-Python`, `Zlib`, `Unlicense`, `BSL-1.0` (Boost, not BUSL-1.1),
   `BSD-3-Clause-Open-MPI`, `ICU`, plus the BlueOak-1.0.0 and CC0-1.0 entries from ADR-0042.
   This covers `typing-extensions`, `greenlet` (the PSF half), `regex`, `robust-predicates`, CPython, `torch`'s Boost terms and jq's incorporated terms.
3. **Unmodified MPL-2.0 is allowed at runtime**, as a recorded class `weak-copyleft`. The package must be unmodified,
   hash-pinned, and imported or deployed as a separate unit, with a notice in the image. Its obligations attach to modifying MPL files.
   This covers `orjson`, `tqdm`, `certifi`, the OpenBao Helm chart 0.30.2 and the OpenBao CSI provider 2.0.3, and the OpenBao server.
   **LGPL and GPL are not covered by this class.** ADR-0043's four exceptions stay as written.
4. **Disabled modules (replaces the "reference-only" paths of ADR-0042 and the enable rule of ADR-0043).**
   `module-5a/` and `module-5b/` are disabled references.
   - Components used only inside a disabled module are recorded with their real licence and class `disabled-module`.
     The gate reports them and does not fail on them while the module is off.
   - The module is off when `enabled: false` in `module-5a/config/rag.yaml`, and offloading, quotas and replicas are zero in
     `module-5b/reference-profile.json`.
   - **The gate fails as soon as a switch turns on while any open finding in that module remains.**
   - This covers `numpy`, `scipy` and `scikit-learn` (their wheels bundle LGPL-2.1 `libquadmath`, GPL-3 with the GCC runtime exception for
     `libgomp` and `libgfortran`), `torch`, and all Spinifex artifacts. Before enabling the module the owner reviews each one:
     replace it, or approve an explicit exception with its notice obligations.
5. **Redis 8.2.3 is blocked (RSAL, SSPL or AGPL) and is replaced by Valkey** (BSD-3-Clause, Linux Foundation, Redis-protocol
   compatible), pinned by digest, in a follow-up work order (WO-25). Do **not** fall back to Redis 7.2.x: it is the last BSD
   version and no longer gets security fixes.
   Until WO-25 merges, Redis is a `pending-removal` entry (Argo CD base, `deploy/registry-images.lock.json`, the WSL image list), expiring in 60 days.
6. **Base-OS images and packages.** Images whose content is an operating-system distribution (BusyBox, Alpine, Debian, Ubuntu,
   `python:*-slim`) and packages installed into our images from that distribution by its package manager (bash, git, make, curl)
   are class `base-os`, taken from a pinned digest or an apt snapshot and used unmodified.
   Copyleft components in them, such as BusyBox GPL-2.0-only, are separate programs aggregated in one image, so they do not affect Twinfra's code.
   They are recorded at image level with the image's declared licence summary, not package by package.
   AGPL, SSPL, BUSL, Elastic and proprietary EULA terms are never `base-os`.
   An image SBOM and exact apt version pins arrive with ADR-0014 supply-chain scanning. Until then they are baseline findings (decision 9).
7. **Proprietary GPU images (NVIDIA CUDA EULA).** Allowed only as an `operator-pulled` reference: referenced by name, disabled by default
   (the GPU switch near `00-setup-ubuntu-host.sh:43`), never baked into a Twinfra image, and listed in the product notice.
   The operator pulls it under their own acceptance of NVIDIA's terms. The gate fails if the GPU switch defaults to on. Enabling
   GPU for a deployment needs the owner's explicit acceptance of the EULA.
8. **Register boundary.** The register covers **locked or rendered deployment inputs**: lock files, images, rendered manifests,
   packages and vendored files that are used.
   - Vendored upstream defaults that site configuration overrides or disables (for example the APISIX `busybox` and `etcd:latest`
     values, and Kourier's `envoy:v1.37-latest`) are **inert defaults**. They are baseline findings, not components, until they appear in rendered output.
   - Anything that appears in rendered output must be digest-pinned and registered. The existing rule against floating tags applies.
9. **Baseline and ratchet.** `security/licence-baseline.json` holds findings that cannot be closed in the PR. Each entry has an `id`,
   reason, owner, required evidence, and an `expires` date no more than 90 days away.
   - The gate fails on any finding not in the baseline and on any expired entry.
   - **A baseline may contain only unverified or evidence-pending items**, such as exact apt pins, version-resolved schema licences
     and inert defaults. It may **never** hold a known AGPL, SSPL, BUSL, Elastic or EULA licence in a deployed component, except Redis
     under decision 5.
   - The Kubernetes JSON Schema inputs that use `master` URLs are baseline entries until their licence source is resolved to the commit SHA used.
10. **Spinifex removal scope (WO-26).** All pinned Spinifex artifacts leave Module 5b: `spinifex.toml`, `awsgw.toml`,
    `spinifex-daemon.service`, `definitions.go`, `run_instances_clienttoken_test.go` and `LICENSE`, plus the lock entries and
    references. KubeVirt and Cluster API replace the capacity bridge (ADR-0029).

## Follow-up work orders

WO-25 Redis to Valkey (priority: Sprint 1) · WO-26 remove all Spinifex artifacts · WO-27 replace `langchain-postgres` with an
`asyncpg` and `pgvector-python` store (ADR-0043) · later: image SBOMs and exact apt pins (ADR-0014).

## Consequences

The gate can pass today and still tells the truth: it reports open baseline items, blocks new problems and expiring ones, and stops
a disabled module from being switched on while it is unresolved. The owner's permissive-only promise stays intact for the running
platform, with Redis the one known gap and a dated plan to close it. Legal review of the LGPL, MPL and base-OS positions happens before any commercial release (ADR-0030).
