# WO-01: Repository governance

**Status:** Approved for implementation (owner, 2026-10-08) · **Phase:** 0 · **Author:** Claude · **Implementer:** Codex
**Branch:** `codex/wo-01-repository-governance` · **Review finding:** R1

## Goal

Make the "vCloud PR gate" binding and give every change a named reviewer.

## Verified context

- `MILESTONES.md` (Milestone 3) states that `main` is currently unprotected.
- `.github/` contains only `workflows/pr-tests.yaml`. The final job, `required`, is named **vCloud PR gate**.
- There is no CODEOWNERS file and no PR template.

## Scope

1. Add `.github/CODEOWNERS`. The default owner is `@amazen33`. Name the owner explicitly for
   `vcloud-ssot.yaml`, `security/`, `.github/`, `tools/ci/`, `deploy/`, `lab/`, and the ADR folders
   (`docs/adr*`, `docs/architecture/adr/`).
2. Add `.github/pull_request_template.md` with sections for:
   - the work order ID and link, scope, and out-of-scope items;
   - tests run and their results, kept static and live separate;
   - the evidence receipt path;
   - licence-register changes, deviations from the work order, and owner actions needed.
3. Add `docs/governance/branch-protection.md`, a runbook giving the exact ruleset the owner applies:
   - **Target:** `main`.
   - **Pull requests:** required, with 1 approval; stale approvals dismissed on push; review from code owners required.
   - **Status check:** "vCloud PR gate" must pass, and branches must be up to date.
   - **Branch safety:** force pushes blocked and deletion restricted.
   - **Bypass:** none, except a documented owner emergency procedure.
   - **Verification:** how to check with `gh api repos/amazen33/vCloud/rulesets`.
4. Add a line to `docs/github-actions-tests.md` that points to the runbook.

## Out of scope

Changing repository settings. Codex must not call the GitHub settings API with write access; the owner applies the ruleset.
Do not change the workflow logic.

## Acceptance criteria

- The files exist. `actionlint` and the docs checks pass. The PR gate is green, including the historical baselines.
- After the owner applies the ruleset, the owner opens a test PR with a deliberately failing check and
  confirms it cannot merge. Record this in `docs/acceptance/governance-<date>.md`, then tick the
  Milestone 3 ruleset item in `MILESTONES.md` in a follow-up PR.

## Owner actions

Apply the ruleset from the runbook, and confirm the blocked test PR.

## Report back

PR link; checks run; whether `tools/ci/check_docs.py` needed a change for the new docs file.
