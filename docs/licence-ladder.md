# ADR-0054 runtime admission and legacy evidence backfill

The [licence ladder](adr/0054-licence-ladder-and-enterprise-grade-gate.md)
applies to new or changed runtime entries from the WO-09a split onward. The owner approved
the following transition on 2026-10-16; it does not re-evaluate the existing
register as part of this governance split.

Each unchanged legacy runtime entry has a tier and an `enterpriseGrade` record
with `status: legacy-pending` and a fixed `due` date. The licence policy freezes
its earlier approval fingerprint. The fingerprint excludes only the newly added
tier/backfill fields; changing its version, digest, class or other approval
metadata requires full ADR-0054 records. Its deadline cannot be extended by
editing the register. A deadline is exclusive: the gate fails on that date.

| Legacy runtime cohort | Backfill deadline | Evidence owner |
| --- | --- | --- |
| Tier 3/4, including OpenBao/MPL units, LGPL exceptions and existing distribution image copyleft | 2027-01-14 | Foundation 1.0 evidence work order; owner review |
| Tier 1/2 | 2027-04-16 | Foundation 1.0 evidence work order; owner review |

The gate reports counts by deadline in its CLI/Actions summary and enumerates
identities, tiers and dates in `legacyBackfill` in the JSON report. It preserves
existing shorter exception/evidence expiry dates; this backfill renews none of
them. Build-only tools, inactive reference modules and operator-pulled proprietary
images retain their existing ADR-0042/0044 boundaries. Runtime inventory is
conservative: all remaining registered ecosystems except GitHub actions receive
the dated backfill, including dependencies used in both runtime and CI.

New records may carry `status: pending` and per-criterion pending/fail results for
draft review. Such a record fails admission; it grants no temporary approval.

New runtime admissions need all six enterprise-grade criteria to pass, each with
a dated HTTPS evidence link. Tiers 3/4 additionally need component owner approval,
an unmodified separate unit, notices/source offer and rejected more-permissive
candidates with their failed criteria. Re-evaluation is due at every minor
upgrade or within six calendar months. Tier 4 requires an exception. Never
licences cannot be admitted through a runtime exception or a legacy baseline.

Licence approval does not approve vulnerability exceptions. Supply-chain results,
image-staging attestation and live restore acceptance remain independent gates.
No certification or production-readiness claim follows from the records.

The one-time migration is reproducible with
`python tools/ci/refresh_licence_ladder.py --check`. It compares all 581 original
component records; no version, hash, class, expiry or permission is renewed.

## Toolchain-wave review

[ADR-0049 Amendments 1/1a](adr/amendments/0049-amendment-1-toolchain-wave.md)
qualify findings by package and scanner-reported fix, never by a growing ID list.
The reviewed snapshot in `security/toolchain-wave-policy.json` names Go-team
modules and the newest patch of each supported Go minor line. Unknown modules,
unknown lines, non-Go libraries and OS packages fail closed. Updating this
snapshot is reviewed policy work; it does not approve any exception.

`tools/ci/toolchain_wave.py` prepares one entry per image, package and CVE with
`approvedBy: ""`. Keep these proposals outside the active register. Empty
approval fails the existing gate. Only the owner sets `amazen33` after reviewing
the batch, upstream release eligibility and isolation controls. Critical entries
last at most 30 days; High entries at most 60. No eligible fixed upstream release
may exist, and KEV always blocks. The normal gate checks a recorded wave entry
against the current finding, pinned scanner, exact fixes and controls. Its
upstream eligibility evidence needs review at least every 14 days; refresh
within 14 days after a fixed release becomes eligible, or escalate immediately
if KEV lists the advisory. No upstream binary is rebuilt by this policy.

The `requiredScanner` record identifies the admitted Linux scanner required by
the PR scan job; it is not a claim that a proposal's preliminary scan ran on
Linux. Keep the actual scan platform, coverage, database and digest evidence
with the batch. Preliminary filesystem matching never replaces complete OCI
scanning by the admission PR.
