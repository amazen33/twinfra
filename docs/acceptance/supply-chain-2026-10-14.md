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
issue-idempotence fixtures pass. The first full hosted PR scan
([run 38470489316](https://github.com/amazen33/twinfra/actions/runs/38470489316))
completed 21 pinned image inputs and 10 lockfiles with 2,452 findings:
103 Critical, 754 High, 924 Medium, 289 Low, 256 Negligible and 126 Unknown.
No KEV alias matches were found. Its gate correctly blocked 99 Critical
findings with fixes; all 99 proposals were copied from the generated artifact
into the exception register, with pending-owner and expiry 2026-12-31.
The other four Critical findings had no fix and remained report-only.
The unpublished console/PostgreSQL builds used explicitly reported input
fallbacks. This hosted scan does not claim complete built-image coverage.

The candidate's first run also exposed two cumulative WO-31 receipt tests
that compared today's growing licence register/tool lock with an older work
order's result. Those original assertions now read frozen merged `3b6ec82`;
WO-32 fixtures separately require every previous licence term/artifact to
remain unchanged and allow only the three scanners, two actions and their
scheduled-workflow locations. All six historical revisions already passed
that initial run; their immutable pins remain untouched.

The real 2,452-record report was also passed through the stdlib issue writer
with the HTTP transport mocked: its 63,800-character body fits the single-issue
limit and all full SHA256 identities/dates round-trip losslessly. Resolved
identities remain in subsequent state. No record or identifier is shortened.
An untrusted public issue cannot seed or reset the first-seen clock; the reader
and writer require the security-labelled owner/GitHub Actions tracking issue.
No issue was created or edited during these fixtures.
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
