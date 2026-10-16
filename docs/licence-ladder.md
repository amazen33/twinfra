# ADR-0054 runtime admission and legacy evidence backfill

The [licence ladder](adr/0054-licence-ladder-and-enterprise-grade-gate.md)
applies to new or changed runtime entries from WO-09 onward. The owner approved
the following transition on 2026-10-16; it does not re-evaluate the existing
register as part of WO-09.

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

The two exact cert-manager CRD inputs under `backup-schemas.lock.json` are
validation schemas only; they install no runtime and are not WO-08 admission.
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
