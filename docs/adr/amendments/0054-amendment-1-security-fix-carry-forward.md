# ADR-0054 Amendment 1: security-fix carry-forward for legacy-pending records

**Status:** Accepted (design; owner O-5 approval in the R12 instruction, 2026-10-28). Individual carries still require owner approval in the PR batch.
**Author:** Claude. **Decider:** Ahmed Mazen. **Amends:** ADR-0054 (licence ladder and enterprise-grade gate). The gate code is `tools/ci/licence_ladder.py`.

## Context

- **ADR-0054 and its gate:**
  - They admit about 526 existing components through an owner-approved, dated **legacy backfill** (`legacy-pending`, fingerprint-locked, due 2027-01-14 or 2027-04-16).
  - Any change to a legacy entry, including its version, requires **full, verified enterprise-grade records** at once (`validate()`: "Changed legacy runtime requires full ADR-0054 records").
- **R12 (WO-40 Amendment 10) must patch three such components:**

  | Component | Change | Why |
  | --- | --- | --- |
  | MiniStack | 1.5.17 → 1.5.33 | Brotli KEV and `certifi` Critical |
  | `certifi` | 2026.7.22 → ≥ 2026.10.18 | Critical: the eMudhra CA compromise |
  | DOMPurify | 3.4.16 → 3.4.17 | Critical |

- **Their full records can't be completed this week:**
  - MiniStack declares "Beta" (maturity).
  - Governance and support evidence is unverified for MiniStack and `certifi`, and governance for DOMPurify.
  - `certifi` and DOMPurify are tier 3, so they also need owner component approvals and climbing records.
- **The flaw:** the rule as written makes a security fix to a grandfathered component *harder* than keeping the vulnerable version. The vulnerable version may stay until its backfill date, while the fixed one can't enter. That is the opposite of ADR-0049's intent.
- **Separately found (not changed here):**
  - The register classes components by licence, not by where they run. 171 CI-only and about 80 Module 5 components are treated as runtime. DOMPurify is used only by the Mermaid CI tool, and `certifi` only by the disabled Module 5a and a CI tool.
  - `tier_for` takes the most restrictive tier of an `OR` expression. ADR-0044 says "A OR B passes if any alternative passes", so DOMPurify (MPL-2.0 OR Apache-2.0) should be tier 2.
  - Both are follow-ups (decision 4).

## Decision (owner-approved O-5)

1. **Security-fix carry-forward.** A `legacy-pending` record may move to a new version **without** full records only when **all** of these hold:
   - **Same component, same line.** Same upstream project, same major.minor line. Calendar-versioned packages such as `certifi` qualify on any newer release.
   - **Security-driven.** The change is needed to clear a KEV, a Critical, or a High that the ADR-0049 gate blocks. It passes the net-improvement rule (WO-34 Amendment 3a).
   - **Licence unchanged.** The licence is re-verified from the primary source for the exact new version. If the SPDX expression or the tier changes, full records are required.
   - **No extension.** The backfill **due date is unchanged**, and the status stays `legacy-pending`. Every obligation still falls due on the original date: criteria, tier-3 approval and climbing record.
   - **Approved by the owner.** Each carry-forward is listed in the PR (component, old → new version, advisories cleared, unchanged due date) and approved by the owner with that PR's batch.
2. **Recording.**
   - The legacy map entry for the new version records `carriedFrom` (the old ID), the advisories it clears and its approval date.
   - The predecessor's entry is removed.
   - An append-only carry log keeps each component's **original** due date.
   - Tests prove that a carried entry's due date equals the original, that a second carry can't move it, and that `never` licences and changed tiers are refused.
3. **Scope.**
   - It applies to R12 (MiniStack, `certifi`, DOMPurify) and to later security promotions under ADR-0049, including WO-46's KEV duty for Argo CD.
   - It never applies to a new component, a minor or major upgrade, or a licence change.
4. **Follow-ups after v0.1.0** (a work order to be written; they don't block R12):
   - Classify components by **where they run**: CI-only becomes `build-tool` (ADR-0042), and disabled modules become `disabled-module`. ADR-0054's runtime criteria then apply only to what is deployed.
   - Make `tier_for` honour ADR-0044's `OR` rule, so an expression's tier is its most permissive alternative.
   - **MiniStack's maturity:** it declares Beta and may never pass ADR-0054's maturity criterion. Before 2027-04-16, the owner decides between a replacement emulator and an ADR-0058 class for Emulated, dev-only components.

## Consequences

- Security fixes for grandfathered components ship at once. The backfill evidence is still due on the same dates, with no extension.
- The gate stays strict for new components and real upgrades.
- Two modelling issues are recorded instead of being worked around inside the freeze week.
