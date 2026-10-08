# vCloud main branch governance — WO-01

The repository owner applies this runbook after reviewing and merging WO-01.
The implementation adds documentation and review ownership; it does not activate
GitHub enforcement. Leave the Milestone 3 ruleset item unchecked until the
owner's blocked-merge test is recorded in a follow-up PR.

## Prerequisites and review identities

- Repository: `amazen33/vCloud`; target branch: `main`.
- The owner has repository administration access and an authenticated `gh` CLI
  for read-only verification. Do not include credentials in receipts or logs.
- `.github/CODEOWNERS` and the existing workflow must be present on `main`.
  The completed check must have the exact name `vCloud PR gate`.
- The named code owner is `@amazen33`. Normal PRs must have an author identity
  distinct from that account so it can supply the required code-owner approval.
  GitHub prohibits an author from approving their own PR. The current Codex
  connection created PR #26 as `amazen33`; an external Claude review alone
  does not satisfy GitHub's required approving review. Resolve the PR-opening
  identity before activating the ruleset. The owner approved proceeding with
  WO-01's specified ownership after this constraint was reported on 2026-10-08;
  approval to implement does not waive the ruleset's review requirement.

See GitHub's [approval rules](https://docs.github.com/en/pull-requests/how-tos/review-pull-requests/approving-a-pull-request-with-required-reviews)
and [CODEOWNERS requirements](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/about-code-owners).

## Exact owner-applied ruleset

Open **Settings → Rules → Rulesets → New ruleset → New branch ruleset** in
`amazen33/vCloud`. Use the following configuration:

| Setting | Required value |
|---|---|
| Ruleset name | `vcloud-main-governance` |
| Target | Branch |
| Enforcement | Active |
| Target branches | Include by pattern: `main` (`refs/heads/main` in the API); no exclusions |
| Bypass list | Empty during normal operation, including administrators and apps |
| Require a pull request before merging | Enabled |
| Required approvals | 1 |
| Dismiss stale pull request approvals when new commits are pushed | Enabled |
| Require review from Code Owners | Enabled |
| Require approval of the most recent reviewable push | Disabled; WO-01 specifies stale-review dismissal instead |
| Require conversation resolution | Disabled; not a WO-01 rule |
| Require status checks to pass before merging | Enabled |
| Required status check | Exactly `vCloud PR gate`; add the existing workflow check, not an individual matrix job |
| Require branches to be up to date before merging | Enabled |
| Restrict deletions | Enabled |
| Block force pushes | Enabled |

The rule types are `pull_request`, `required_status_checks`, `deletion` and
`non_fast_forward`. Save with **Create**. Active rules apply immediately;
complete the identity prerequisite first. Keep the workflow logic and
`tools/ci/pr-baselines.json` unchanged.

GitHub documents the [creation procedure](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-rulesets/creating-rulesets-for-a-repository)
and [rule semantics](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-rulesets/available-rules-for-rulesets).

## Read-only verification

These commands only read GitHub state. Run them as the owner after saving:

```bash
gh api --paginate repos/amazen33/vCloud/rulesets \
  --jq '.[] | {id, name, target, enforcement, source_type, source}'

# Use the id returned for vcloud-main-governance.
RULESET_ID=12345
gh api "repos/amazen33/vCloud/rulesets/$RULESET_ID" \
  --jq '{name, target, enforcement, bypass_actors, conditions, rules}'

# Check the rules that actually apply to main, including inherited rulesets.
gh api --paginate repos/amazen33/vCloud/rules/branches/main \
  --jq '.[] | {type, parameters, ruleset_id, ruleset_source_type, ruleset_source}'
```

Replace the example ID with the observed ID. Confirm `enforcement: active`,
`target: branch`, conditions including only `refs/heads/main`, and an empty
`bypass_actors` array. Inspect each rule's parameters:

```json
{
  "pull_request": {
    "required_approving_review_count": 1,
    "dismiss_stale_reviews_on_push": true,
    "require_code_owner_review": true,
    "require_last_push_approval": false,
    "required_review_thread_resolution": false
  },
  "required_status_checks": {
    "required_status_checks": [{"context": "vCloud PR gate"}],
    "strict_required_status_checks_policy": true
  },
  "additional_rule_types": ["deletion", "non_fast_forward"]
}
```

This is a projection of the expected response fields, not an API write payload.
The GitHub UI may include an integration ID with the selected status check.
Record the effective values returned by GitHub. A rule that is merely Disabled
or Evaluate does not meet acceptance. API inspection is necessary but does not
replace the blocked-merge test. See the [REST rules API](https://docs.github.com/en/rest/repos/rules).

## Owner blocked-merge acceptance test

1. From an author account distinct from `amazen33`, open a disposable test PR
   targeting `main`. Introduce an intentional failure in an already validated
   fixture or manifest. Do not edit workflow logic, baselines or deployment
   state. Identify it clearly as a governance test and never merge its failing
   contents.
2. Have `amazen33` review and approve as the code owner, with the branch current
   with `main`. Wait for the actual `vCloud PR gate` to conclude `failure`.
   In the merge box confirm the gate is required and merge is blocked. Recording
   only a missing approval or an out-of-date branch does not prove check enforcement.
3. Record the test PR URL, author and reviewer identities, head SHA, workflow
   run URL, failed gate, ruleset ID, UTC timestamp and observed blocked merge
   state in `docs/acceptance/governance-YYYY-MM-DD.md`. Do not attempt a merge
   API call: a mistaken configuration could merge deliberately failing changes.
   Close the disposable PR without merging.
4. Through a reviewed follow-up PR, commit the receipt and tick only the
   Milestone 3 ruleset item in `MILESTONES.md`. This is owner acceptance after
   enforcement, not part of WO-01's implementation PR.

For review enforcement, push a harmless update after approval and confirm that
GitHub dismisses the stale approval. For branch currency, inspect the merge box
when `main` advances. Verify deletion and force-push restrictions from the
effective rule response; do not probe them destructively on `main`.

## Owner emergency procedure and restoration

Normal operation has no bypass actors. A routine author/reviewer identity
conflict is not an emergency. Only the owner may authorize an exceptional,
time-bounded bypass for a documented incident:

1. Record the incident, necessity, exact PR/head SHA, owner authorization,
   reviewer outcome and start/end deadline. Review the diff and CI evidence.
2. The owner may temporarily add **Repository admins → For pull requests only**
   to this ruleset's bypass list. This grants that role a temporary exception;
   record every affected administrator. Keep enforcement Active and the rules
   intact. Agents do not perform this settings change or approve their own work.
3. The owner uses the exception only for the recorded incident PR. Immediately
   remove the bypass entry afterward, including after an unsuccessful attempt.
   Run the read-only verification again and confirm `bypass_actors` is empty.
4. Record restoration and retrospective review in a dated acceptance/incident
   receipt. Recheck the blocked-merge behavior after restoration.

If enforcement disrupts planned work, stop the merge and escalate to the owner
to correct the author/reviewer setup. Normal rollback is to revert WO-01's files
through a reviewed PR; file rollback alone does not remove an active ruleset.
Changes to enforcement or emergency restoration remain owner settings actions.
