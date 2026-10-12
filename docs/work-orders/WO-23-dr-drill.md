# WO-23: Disaster-recovery drill (`cairo-1` → `cairo-2`, cold standby)

**Status:** Approved for implementation (owner, 2026-10-09) · **Phase:** 3 (Sprint 3, after WO-09) · **Author:** Claude · **Implementer:** Codex
**Branch:** `codex/wo-23-dr-drill` · **Decision:** ADR-0040 · **Depends on:** WO-21 (dev environment), WO-09 (off-site backups), WO-08 (OpenBao)

## Goal

Prove that the region `cairo-1` can be recovered as `cairo-2` from Git and off-site backups alone, and measure the real
RPO and RTO. This is the rehearsal for the production pair `cairo-1` / `cairo-2`.

## Scope

1. **SSoT.** Declare the regions `cairo-1` (primary) and `cairo-2` (DR, cold standby, `drPartner: cairo-1`), and the planned
   production pair `cairo-1` / `cairo-2` with status `planned`. Region values flow into labels (ADR-0038), endpoints and the console badge.
2. **Runbook** `docs/runbooks/region-failover.md`:
   - declare the disaster;
   - stop `cairo-1`, which simulates the loss of the site;
   - provision `cairo-2` with the WO-21 script, using another VM name and IP;
   - bootstrap from Git;
   - restore PostgreSQL to a point in time from the off-site backups, including OpenBao storage;
   - unseal OpenBao with the separately held material;
   - verify the services and switch DNS or access;
   - fail back.
3. **Drill tooling.** Scripts that time each step and check data correctness (checksums on sample tables and objects).
   They record the results to the receipt template.
4. **Drill.** Run it once with the owner present (`cairo-1` and `cairo-2` never run at the same time, because of host RAM).

## Out of scope

Warm standby, live cross-site replication and automatic failover. These need the second production site (`cairo-2`).

## Acceptance criteria

- `cairo-2` serves the console sign-in, the platform services and the restored data. Checksums match the backup point.
- The measured RPO and RTO are recorded against the targets the QoS tester approved before the drill.
- Failback to `cairo-1` works.
- Receipt: `docs/acceptance/dr-drill-<date>.md`, with the tester sign-off left Pending.

## Owner actions

Approve the RPO and RTO targets as QoS tester, run the VM script as administrator for `cairo-2`, hold and enter the
unseal material, witness the drill, and sign off.

## Amendment 1 (2026-10-12, ADR-0048)

**`cairo-1` is the bare-metal Dell; `cairo-2` is the Hyper-V VM on the laptop**, built with `deploy/hyperv/` for `cairo-2` only (WO-30 sizing).
- **Running at the same time.** The two regions are on different machines, so they *can* run together. Keep the drill cold anyway: stop `cairo-1` before restoring into `cairo-2`.
- **Free RAM.** The laptop needs 24 GiB free while `cairo-2` runs, so close desktop apps for the drill.
- **Failback** targets the Dell.
