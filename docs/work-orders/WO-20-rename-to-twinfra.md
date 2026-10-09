# WO-20: Rename the product to Twinfra (Stages A and B)

**Status:** Approved for implementation (owner, 2026-10-09) · **Phase:** 0 · **Author:** Claude · **Implementer:** Codex
**Branch:** `codex/wo-20-twinfra-rename` · **Decision:** ADR-0036 · **Depends on:** WO-03 merged

## Goal

The product is presented as Twinfra everywhere current, and the repository is renamed without breaking CI,
GitOps or the live lab. Technical identifiers (Stage C) are out of scope.

## Scope

**PR 1, Stage A (branding):**
1. Add `docs/adr/0036-product-name-twinfra.md` verbatim from `E:\vcloud-handoff\adr\ADR-0036-product-name-twinfra.md`,
   and add it to the ADR index as Accepted (owner). Add this work order to `docs/work-orders/`.
2. In current docs (README, MILESTONES, `docs/governance/*`, `docs/work-orders/README.md`, module and lab READMEs),
   replace the product name "vCloud" with "Twinfra". Add "formerly vCloud" once, near the top of README.
3. Console UI: change only the visible product-name text (title, header, footer, About) to Twinfra.
   Keep the realm, client IDs, routes and labels unchanged; those are Stage C.
4. **Do not change:** ADRs 0001-0035, `docs/acceptance/*` receipts, `docs/*-validation.json`, identifiers,
   the hash-frozen files, or `tools/ci/pr-baselines.json`.

**Owner action between PR 1 and PR 2:** rename the repository to `amazen33/twinfra` in GitHub settings.

**PR 2, Stage B (references), after the owner confirms the rename:**
5. Update hard-coded repository references to `https://github.com/amazen33/twinfra(.git)`:
   - Argo CD Application `repoURL` values and their generators (`tools/wsl_platform.py`, `tools/vcloud_console.py`,
     `tools/wsl_endpoints_gitops.py` and any others found by search);
   - SSoT `gitOpsRepository`;
   - the `repository` field in `tools/ci/pr-baselines.json`. Commit SHAs stay unchanged.
     Confirm `tools/ci/revisions.py` still resolves the historical PRs.
6. Update the local `origin` remote and docs links. GitHub's redirect covers anything missed, but do not rely on it for Argo CD.
7. Live: after owner approval, re-point the lab's Argo CD Applications and confirm every Application is Synced and Healthy.

## Out of scope

Stage C identifiers, the local folder name `E:\vCloud` (the owner may rename it later), and region names (D10).

## Acceptance criteria

- **PR 1:** the CI gate is green, historical baselines included. A search finds no "vCloud" product-name text in
  current docs or the UI, outside history and identifiers. Browser acceptance still passes.
- **PR 2:** CI is green, and `revisions.py` resolves PRs 1-6 against the renamed repository.
  The lab's Argo CD Applications are Synced and Healthy from the new URL.
  Receipt: `docs/acceptance/twinfra-rename-<date>.md`, with the tester sign-off left Pending.

## Report back

Files changed per PR, the identifier list deliberately left for Stage C, and the Argo CD sync evidence.
