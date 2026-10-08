# vCloud acceptance receipts

Record live results as dated receipts in this directory, separate from static
CI results. Use `<scope>-YYYY-MM-DD.md`; governance blocked-merge evidence uses
`governance-YYYY-MM-DD.md`. State the environment, authorized scope, tested
revision and observed results. Keep credentials, tokens and private configuration
out of commands, evidence and receipts.

Follow the [roles and Definition of Done](../governance/roles.md). Codex writes
`Result: Pending`; only Ahmed Mazen (@amazen33), acting as enterprise and cloud
tester; QoS tester, changes it to `Accepted` or `Rejected`, with the UTC date,
QoS targets checked and notes. A rejection reopens the work order with the
tester's notes. Static checks and an unsigned receipt do not establish live acceptance.

For governance, follow the [owner blocked-merge procedure](../governance/branch-protection.md).
Record the owner-provided test PR URL, ruleset ID, head SHA, run URL, UTC timestamp
and observed merge block. Until those details exist, leave the governance receipt
and the Milestone 3 ruleset checkbox pending. A passing CI run alone does not
prove that GitHub blocks a failing merge.

## Copy-paste receipt template

Replace placeholders with observed evidence. Mark fields outside the authorized
scope `Not applicable` and list incomplete checks under Pending gates. The
receipt must end with the Tester sign-off block; Codex leaves its result Pending.

```markdown
# <Scope> acceptance receipt — YYYY-MM-DD

## Scope and authorization

- Work order / PR URL:
- Environment / namespace / node:
- Owner authorization reference and scope:
- Test start and end (UTC):
- Tested head SHA:
- Tester / witness:
- QoS targets agreed before testing:

## Static evidence

- Commands and results:
- GitHub run URL / vCloud PR gate result / historical baseline results:
- Checks that could not run locally:

## Live evidence

| Check / command | Expected outcome / QoS target | Observed outcome | Evidence reference / UTC timestamp |
| --- | --- | --- | --- |
| <authorized check> | <expected> | <observed or Pending> | <sanitized evidence> |

## Governance evidence (when applicable)

- Activation stage:
- Test PR URL:
- Ruleset ID and effective rule values:
- Author and reviewer identities:
- Head SHA:
- Workflow run URL and failed vCloud PR gate:
- Observation timestamp (UTC):
- Observed blocked-merge state and reason:
- Branch current with main / required reviews satisfied for this stage:
- Test PR closed without merging:

## Pending gates, deviations and owner actions

- Pending checks / unavailable evidence:
- Approved deviations and authorization:
- Restoration / rollback and evidence:
- Owner actions still required:

## Tester sign-off
Tester: Ahmed Mazen (@amazen33), enterprise and cloud tester; QoS tester
Result: Pending
Date (UTC):
QoS targets checked:
Notes:
```
