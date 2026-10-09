# Twinfra handoff pack: Wave 1

Prepared 2026-10-08 by Claude (platform architecture and software engineering lead) for Codex,
the only implementer. Owner approval: D1-D8 approved on 2026-10-08; D9-D12 still open.
Plan: https://claude.ai/artifact/PGbvxpbveSfJDTr2PBbFyY (private; the owner shares it).

Nothing in this pack has been written to the Twinfra repository. Codex adds it there in WO-03.

## Contents

| Path | What it is |
| --- | --- |
| [ADRs 0029–0035](../adr/README.md) | Accepted decision records for D1-D8 |
| [WO-01](WO-01-repository-governance.md) to [WO-11](WO-11-console-roles-csrf-audit.md) | Wave 1 work orders (Phases 0 and 1), approved for implementation |
| [WO-20](WO-20-rename-to-twinfra.md) | Staged product rename under [ADR-0036](../adr/0036-product-name-twinfra.md); Stage A branding precedes the owner's Stage B repository rename; technical identifiers wait for Stage C |
| [WO-25](WO-25-redis-to-valkey.md) | Redis to digest-pinned Valkey cache replacement, including owner-approved Amendment 1 |

ADR-0028 is reserved. The registry decision currently numbered ADR-0020 gets 0028 when WO-03
removes the duplicate number.

## Order and dependencies

1. WO-01 repository governance. The owner then applies the GitHub ruleset.
2. WO-03 one ADR log. It also commits this pack: the ADRs go into [docs/adr/](../adr/README.md), the work orders into [docs/work-orders/](README.md).
3. WO-02 licence register and CI gate.
4. WO-04 (token verification) and WO-06 (remove LocalStack), in parallel.
5. WO-05 admission policies: audit first, then enforcement once the owner approves.
6. WO-07 Perses replaces Grafana.
7. WO-08 OpenBao, External Secrets, cert-manager. Needs the owner's key ceremony.
8. WO-09 off-node backups and restore drill. Needs a backup target from the owner.
9. WO-10 observability stack v1. Needs WO-02 and WO-07, plus the owner's node-exception approvals.
10. WO-11 console roles, forgery protection and audit.

## Codex working rules (apply to every work order)

- One work order per branch, named `codex/wo-NN-<slug>`. Keep PRs small, and fill in the PR template from WO-01.
- The "vCloud PR gate" must pass. CI re-tests the merged PRs listed in
  `tools/ci/pr-baselines.json` using the current CI scripts, so a removal or move must keep
  those older revisions passing. Handle a missing path in old revisions; never edit the baselines.
- Generated files are changed through their generator, never by hand: for example
  `tools/wsl_endpoints_gitops.py`, `tools/wsl_console.py`, `tools/vcloud_console.py` and
  `tools/render_module*.py`. Commit the regenerated output from the same PR.
- Pin images by digest and stage them in the canonical registry path, as the repo already does. Every new or changed
  third-party component gets a licence-register entry once WO-02 lands.
  The licence policy is ADR-0030.
- No secrets, private keys, tokens or passwords in Git, logs, test output or PR text.
- Live lab changes (apply, delete, restart) need the owner's approval in the PR or task.
  Report static checks separately from live results, and record live results as a dated receipt
  in `docs/acceptance/`.
- Do not change unrelated files. If a work order is wrong or cannot be met, stop and report the
  deviation with evidence. Do not redesign silently.
- Report back with the PR link, the tests run with their results, the receipt path, deviations,
  and any open owner actions.

## Roles, tester sign-off and Definition of Done

See [roles and Definition of Done](../governance/roles.md) and the
[acceptance receipt template and tester sign-off](../acceptance/README.md).
Codex records live receipts as Pending; only the tester changes their result.

## Review

Claude reviews each PR against its work order before the owner merges. No agent approves its own work.
