# WO-32 supply-chain scanning · 2026-10-14

Work order: [WO-32](../work-orders/WO-32-supply-chain-scanning.md).
Decision: [ADR-0049](../adr/0049-supply-chain-vulnerability-scanning.md).
Scope: static CI implementation; no Dell or live platform changes.

## Static evidence

The three approved scanner releases and their Linux amd64 archives were
verified against official checksum files. Extracted binaries have separate
SHA256 pins. Exact-version licences are Apache-2.0; the cache/download actions
have immutable commit pins and verified MIT licences. The existing schema-source
licence baseline refresh changes only its CI tool-lock fingerprint: all old
schema/tool pins, owner, reason, date and expiry remain unchanged.

Offline gate, inventory, binary/cache integrity, workflow permission/pin and
issue-idempotence fixtures pass. The first full hosted PR scan and its proposed
exception list are required evidence before static implementation is complete.
No SBOM or vulnerability database is committed. Run links and full findings
are reported in the PR; subsequent scanner data is expected to change over time.

## Owner approval and after-merge acceptance

| Gate | Result | Required evidence |
| --- | --- | --- |
| First exception approvals | Pending | Owner reviews each proposed blocking finding, completes its mitigation/removal reason and replaces pending-owner before merge |
| First nightly reporting dispatch on main | Pending | Full scan report and link to the security-labelled open-findings issue |
| Second nightly reporting dispatch on main | Pending | Same issue number edited in place, preserving first-seen state |
| Weekly upstream watch dispatch on main | Pending | Current-versus-candidate report and the single upstream-updates issue; unavailable publication evidence recorded, no lock edits or update PRs |

The issue-write job creates the `security` issue label if absent. No issue,
label or repository setting is changed during this static implementation task.
Owner approval of exceptions is separate from passing the WO-32 branch's
temporary pending-owner bootstrap rule. That rule rejects main, schedules,
manual dispatches, forks and other branches.

## Tester sign-off

Tester: Ahmed Mazen (@amazen33), enterprise and cloud tester; QoS tester
Result: Pending
Date (UTC):
QoS targets checked:
Notes:
