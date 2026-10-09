# WO-03: One ADR log, plus the accepted D1-D8 records

**Status:** Approved for implementation (owner, 2026-10-08) · **Phase:** 0 · **Author:** Claude · **Implementer:** Codex
**Branch:** `codex/wo-03-adr-log` · **Review finding:** R7

## Goal

One ADR folder with unique numbers and meaningful statuses. This PR also commits this handoff pack.

## Verified context

- ADRs live in three places:
  - `docs/adr-0001-node-host-mounts.md` and `docs/adr-0019` to `docs/adr-0023`;
  - `docs/adrs/0002` to `docs/adrs/0018`, plus `README.md`;
  - `docs/architecture/adr/ADR-0020`, `ADR-0024` to `ADR-0027`, plus `README.md`.
- The number 0020 is used twice: `docs/adr-0020-module-3-delivery.md` and `docs/architecture/adr/ADR-0020-air-gapped-registry.md`.
- The component ADRs 0002-0018 all say "Proposed", although several components run in the lab.
- `tools/ci/check_docs.py` validates Module 1 documentation and links.

## Scope

1. Create `docs/adr/` as the single log and move every ADR there with `git mv`, so history is kept:
   - Keep the numbers 0001-0019 and 0021-0027.
   - The module-3 delivery ADR keeps 0020.
   - The air-gapped registry ADR becomes **0028**. Update its title, every link to it, and the "Issue #412" references in `MILESTONES.md`.
2. Add this pack's ADRs as `docs/adr/0029` to `docs/adr/0035`, and the work orders as `docs/work-orders/WO-01` to `WO-11`
   with `docs/work-orders/README.md` (the pack README). Copy them verbatim, except for fixing relative links.
3. `docs/adr/README.md` becomes the index. It defines the status lifecycle: Proposed, Accepted (lab), Accepted (production),
   Superseded, and Constraint (a requirement-driven choice with no comparison of alternatives).
   It lists every ADR with its status and acceptance-receipt link, and gives the next free number.
4. Status updates:
   - Components with lab acceptance receipts become "Accepted (lab)", with a link to the receipt. Codex derives this from
     `docs/acceptance/` and `MILESTONES.md` and lists each mapping in the PR.
   - ADRs whose selection was "required by Module 1" also carry "Constraint".
   - ADR-0010 is superseded by 0034. ADR-0018 is superseded by 0029 and 0030. ADR-0025 is superseded by 0030 and WO-06.
     ADR-0026 and ADR-0027 are partly superseded by 0035 (the read-only decision only).
   - Superseded files keep their text, with a status line and a pointer added at the top.
5. Leave a one-line stub `README.md` in `docs/adrs/` and `docs/architecture/adr/` pointing to `docs/adr/`.
   Do not leave stubs for individual files. Update every repository link instead.
6. Update `README.md`, `MILESTONES.md`, `docs/module-1-topology.md` and any other link sources found by search.
   Update `tools/ci/check_docs.py` so the candidate revision is validated against `docs/adr/` while
   **historical baselines with the old layout still pass**.

## Out of scope

Changing the substance of any decision, other than the status lines listed above.

## Acceptance criteria

- No ADR number appears twice. Every Markdown link resolves.
- The docs checks and the full PR gate pass, including the historical baselines.
- `git log --follow` shows history for the moved files.

## Owner actions

Confirm the status mappings in the PR. Merging this PR records ADR-0029 to ADR-0035 as accepted.

## Report back

The mapping table (old path to new path to status), the link-fix count, and the changes to `check_docs.py`.
