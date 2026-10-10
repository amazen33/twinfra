# Twinfra repository rename acceptance receipt — 2026-10-10

## Scope and authorization

- Work order: [WO-20, PR 2 / Stage B](../work-orders/WO-20-rename-to-twinfra.md), under [ADR-0036](../adr/0036-product-name-twinfra.md).
- Repository / branch: `amazen33/twinfra`, `codex/wo-20-twinfra-rename`.
- Owner confirmation: "done", after the request to merge Stage A and rename the repository.
- Read-only GitHub verification: [PR #33](https://github.com/amazen33/twinfra/pull/33) is merged; canonical repository is `amazen33/twinfra`.
- Environment: static repository validation only. No deployment or WSL lab operations are authorized in this task.
- Tested head SHA / workflow / timestamps: recorded in the Stage B PR and its exact-revision validation artifacts.
- Tester / witness: Codex implements and reports static evidence; Ahmed Mazen signs live acceptance.
- Live QoS target: every relevant Argo CD Application is Synced and Healthy using the new repository URL, on VM lab `lab-1` after WO-21 and explicit owner authorization.

## Static evidence

Stage B updates repository references, their generators, the SSoT `gitOpsRepository`,
local `origin`, current documentation links and CI revision selection. The six
baseline PR numbers and immutable commit SHAs remain unchanged. PR metadata for
PRs 1–6 must resolve through the renamed repository to those same merge commits.
The PR records the full candidate, licence gate and historical matrix results.

Historical ADRs 0001–0035, existing acceptance receipts, validation JSON and
hash-frozen node policy artifacts retain their original content. ADR-0036 and
WO-20 retain the owner's original decision wording. Those records explain the
old name; active GitOps and CI references use the canonical repository.

## Live evidence

| Check | Expected outcome | Observed outcome | Evidence |
| --- | --- | --- | --- |
| Re-point VM lab Argo CD Applications | Approved Applications reference `https://github.com/amazen33/twinfra.git` | Pending; not executed | VM lab `lab-1`, after WO-21 and owner authorization |
| Reconcile from renamed repository | Every relevant Application is Synced and Healthy | Pending; not executed | No live Argo CD evidence collected |

## Pending gates, deviations and owner actions

- Static work does not establish live GitOps acceptance. No `kubectl apply`, restart, sync or repository-settings change was performed.
- Live execution is deferred by the owner's static-only instruction and WSL retirement; it must run on the VM lab after WO-21.
- Claude reviews the Stage B PR before the owner merges it.
- Stage C needs its separate work order: SSoT cluster identity, node/profile names, domains, registry and image paths, realm/client IDs, labels, resource names and configuration/session identifiers remain unchanged.
- The local folder remains `E:\vCloud`; region naming remains open (D10).

## Tester sign-off

Tester: Ahmed Mazen (@amazen33), enterprise and cloud tester; QoS tester
Result: Pending
Date (UTC):
QoS targets checked:
Notes:
