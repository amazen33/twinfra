# Licence register and offline gate

[Policy](licence-policy.json) · [Register](licence-register.json) ·
[Dated evidence baseline](licence-baseline.json) · [Product notices](licences/NOTICE.md)

ADR-0044 and WO-02 Amendment 3 govern the register. A component is an exact
ecosystem/name/version identity. OCI tag and mirror spellings resolve through
the existing locks to the same digest identity. Manifest artifacts are counted
individually; npm/pip distributions are deduplicated by name and version.

Run `python tools/ci/check_licences.py --report .build/licences.json` from the
repository root. CI calls it from its control checkout before the module gates,
so only the candidate inventory is subject to this policy. Historical revisions
continue through their complete original module gates without retrospective
licence classification. The baseline revision list is unchanged.

The gate reads both npm locks, pinned pip requirements, action SHAs, tool and
artifact locks, source-rendered manifests, image lists, Dockerfile bases, active
site values, and vendored chart headers. It never contacts a registry or executes
third-party code. Generated manifest drift, Helm renders and schemas remain
separate mandatory gates. `--rendered FILE` additionally checks images from an
explicit render against the same register; it cannot authorize an unknown image.

APISIX's disabled etcd/ingress subcharts and overridden upstream image defaults
are inert-default baseline findings. The Python <3.11 fallback dependency is
also inert on the pinned Python 3.14 target. If a default enters a render it must
be registered; baseline entries do not register components.

SPDX `OR` accepts an allowed alternative; `AND` requires every term; `WITH`
requires an allowed base licence and a listed exception. Boost `BSL-1.0` and
Business Source `BUSL-1.1` remain distinct. Unverified sources use `NOASSERTION`
only with an explicit per-component evidence baseline; a known blocked licence
cannot be admitted that way. Baselines never override class validation.

Every baseline records its owner, required evidence and fixed expiry. Existing
unpinned image references are recorded as image-digest evidence gaps; they are
not described as digest-verified. SBOM/notice verification, exact apt versions,
version-resolved schema sources and inert defaults are reported separately.
Changed baseline inputs and unregistered identities fail the gate. Do not extend
dates or change classes automatically: review the evidence with the owner.
To close an image SBOM finding, commit the reviewed evidence, record its relative
`path` and SHA256 in that component's `imageSBOM` object, and remove the finding
in the same reviewed PR. Missing or changed evidence fails; the gate does not
infer a licence clearance merely from the existence of an SBOM.

The initial dates use the owner approval on **2026-10-09**, conservatively:

- Grafana (WO-07), LocalStack (WO-06): **2026-12-08**.
- Open baseline evidence: **2027-01-07** (90 days).
- psycopg, psycopg-binary and psycopg-pool (WO-27): **2027-02-06**, or before
  Module 5a is enabled. Certifi is now weak-copyleft under Amendment 3.

These dates do not slide with each CI run or a delayed merge. If the merge date
differs, these are earlier deadlines than the maximum merge-relative windows;
any later date requires an explicit reviewed update.

[WO-25 Amendment 1](../docs/work-orders/WO-25-redis-to-valkey.md) removes the
Redis register entry and pending-removal authorization. Valkey 8.1.10-alpine is
`allowed` (BSD-3-Clause), pinned to its multi-platform digest. Its complete
image SBOM remains a dated evidence gap, expiring **2027-01-07**.
The preserved Argo CD full/Core archives and generated upstream base retain
the original cache image as inert-default evidence. This exclusion applies
only to the exact upstream reference at those three source paths while the
base transformer matches the locked Valkey digest. Removing/changing that
transform re-enumerates the upstream image and fails the licence gate.
The candidate gate also scans real base, overlay and WSL renders; an upstream
image appearing there is never exempt. Unrelated baseline dates are unchanged.

Module 5a's `enabled` flag and Module 5b's profile flags, generated replicas and
queue quotas must remain off while their disabled-module findings are open.
Quotas/replicas are generated files, not fields currently present in the Module
5b profile; the gate checks both the profile and those generated files.
Spinifex's six pinned artifacts remain recorded until WO-26 removes all of them.

No deployment, library replacement or runtime image rebuild is performed by
WO-02. Module -1 retains `ENABLE_GPU=auto` for driver/runtime provisioning;
`GPU_SMOKE_TEST=false` gates only the proprietary CUDA smoke job and its image.
Regenerated Cloud-Init preserves both defaults.
The RAG Dockerfile copies the reviewed licence bundle offline; actual image
assembly still requires the already-pinned wheel mirror/cache.
