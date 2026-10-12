# WO-30: 20 GiB disk per dev VM, and capacity checks that report instead of failing

> **Amendment 1 (2026-10-12, ADR-0048).**
> - **Target.** `cairo-1` now runs on bare metal (WO-31). This work order applies only to the Hyper-V **cold standby `cairo-2`** on the laptop.
> - **Moved to WO-31.** Scope items A4 (image pinning) and A5 (log caps) apply to every host, so WO-31 implements them. Skip them here.
> - **Unchanged.** Items A1–A3 (the 20 GiB disk and the 4 GiB PostgreSQL loop file) and sections B–D (plan reports, RAM checked at start, rounding) stay as written, but for `cairo-2`.
> - **Order.** Run this work order **after WO-31**.

**Status:** Proposed (architect, 2026-10-10); implement after the owner approves this order · **Phase:** 2
**Author:** Claude · **Implementer:** Codex · **Branch:** `codex/wo-30-dev-vm-sizing` · **Depends on:** WO-29 merged (PR #36, PR #38; `main` at `968f336`)
**Decisions:** ADR-0032, ADR-0046. The owner's sizing decision of 2026-10-10 is below. Amends WO-21 (VM disk size) and WO-29 scope item 3 (where the RAM guard runs).

## Why

**Owner decision (2026-10-10).** 20 GiB of disk per VM is enough for this pre-production product, so the VHDX goes from 100 GiB to **20 GiB**. RAM stays at 20 GiB, set by WO-29, with a 4 GiB host reserve. Vcpu stays at 8.

The owner's first real plan, run on 2026-10-10, failed:

```text
pwsh -File deploy/hyperv/New-TwinfraDev.ps1 -Plan
Exception: Insufficient free RAM: measured 20.8776245117188 GiB, require 24 GiB; close browsers/desktop apps and stop WSL or other guests yourself
```

The architect then checked the host, read-only:
- Free RAM was 17.9 GiB.
- No WSL distro was running.
- No Hyper-V partition was running.
- Desktop apps held the memory: Claude 2.5 GiB, ChatGPT 2.3 GiB, Edge 2.6 GiB.

The other findings, all on `origin/main` at `968f336`:

| Finding | Evidence | Effect |
| --- | --- | --- |
| The minimum disk size is 32 GiB. | `Twinfra.psm1:41`: `$DiskGB -lt 32` throws `Invalid VM sizing` | `-DiskGB 20` is refused. |
| The PostgreSQL Local PV and the CNPG cluster both declare **20Gi**. The PV is a plain directory on the root filesystem. | `deploy/environments/dev/cairo-1/platform/workloads.yaml:62277` (PV `capacity`) and `:62363` (CNPG `size`); runbook step 11 creates the directory with `install -d` | On a 20 GiB disk the claim equals the whole disk. Nothing enforces it, so PostgreSQL can fill the root filesystem and push the node into DiskPressure eviction. |
| Images are staged only, with no upstream fallback. | WO-29 Amendment 1 B; `imagePullPolicy: IfNotPresent` in the dev overlay | When usage passes 85%, kubelet image garbage collection deletes unused images. On a 20 GiB root that is 17 GiB. A deleted staged image can never be pulled again, so the next pod that needs it fails. |
| The RAM guard runs at plan and provisioning time. Provisioning leaves the VM **Off**, so it uses no RAM. | `Twinfra.psm1:118`; runbook step 6 is a bare `Start-VM` | The owner cannot create the VM until 24 GiB is free. When the VM actually starts, the 4 GiB host reserve is not checked. |
| `-Plan` throws on the first failed capacity check, before the plan is printed. | `Twinfra.psm1:118-119`; `Format-TwinfraPlan` runs only after `New-TwinfraPlan` returns (`New-TwinfraDev.ps1:63`) | The plan's "Free RAM measured / Required" line (`Twinfra.psm1:128`) is never shown in the case it was written for. |
| Measured values are printed unrounded. | `New-TwinfraDev.ps1:56` | The output shows `20.8776245117188 GiB`. |

## Scope

### A. A 20 GiB disk per VM (cairo-1 and cairo-2)

1. **Sizing.**
   - The default `-DiskGB` is **20** in both `New-TwinfraDev.ps1` and `New-TwinfraPlan`. The minimum becomes 20 (it was 32).
   - The E: guard stays `DiskGB + 10`, so it needs **30 GiB** free.
   - The disk stays a dynamic VHDX, resized to 20 GiB. The seed must grow the root partition and filesystem on first boot. Check that cloud-init `growpart` and `resize_rootfs` are enabled in the generated `user-data`, and add a test.
   - No VM exists yet, so the ownership stamp, which includes `DiskGB`, needs no migration.
2. **Disk budget.** Add a "Disk budget (20 GiB)" table to `docs/dev-environment.md`, next to the RAM table:
   - Ubuntu with kernel and apt cache.
   - Container images: both inventories, compressed content plus unpacked snapshots.
     - Compute the compressed sizes from the layer sizes in the locked manifests, using read-only registry queries.
     - State the multiplier used for unpacked size.
   - etcd.
   - Logs.
   - The PostgreSQL volume (item 3).
   - The kubelet eviction floor (`imagefs.available` 15% = 3 GiB on a single filesystem).
   - Headroom of **at least 2 GiB**.

   **If the budget does not fit in 20 GiB with that headroom, stop and report the numbers. Do not change the size.**
3. **PostgreSQL on a finite 4 GiB volume.**
   - Port the vetted pattern in `lab/wsl/prepare-storage.sh` to the dev seed:
     - one owned 4 GiB ext4 loop file, `/var/lib/twinfra/volumes/postgres-1.ext4`;
     - mounted at `/var/lib/twinfra/local-pv/postgres-1` with `loop,noatime,nodev,nosuid,noexec` through a systemd mount unit;
     - required by kubelet through `RequiresMountsFor`;
     - owner 26:26, mode 0700.
   - Like the WSL script, it records an ownership marker and refuses to adopt existing or unowned files, directories or symlinks.
   - Cloud-init creates it on first boot, and runbook step 11 drops its `install -d` command.
   - Set the PV `capacity` and the CNPG `storage.size` to **4Gi**, in both region overlays, through their generator.
4. **Staged images are never garbage-collected.**
   - Both staging paths label every staged image `io.cri-containerd.pinned=pinned`. The two paths are the bootstrap `stage_bootstrap_images` step and `tools/platform_dev.py stage-images`.
   - Their verification fails unless `crictl inspecti` reports the image as pinned.
   - Confirm that the containerd version installed on the dev VM honours the label with Kubernetes v1.36.5. If it does not, stop and report.
5. **Log caps.**
   - journald: `SystemMaxUse=500M`.
   - kubelet: `containerLogMaxSize: 10Mi` and `containerLogMaxFiles: 3`.

   These caps apply in the dev seed only. The production profile stays byte-identical.
6. **Rule for later work orders.**
   - Add one sentence to `docs/dev-environment.md`: any work order that stores data must fit it into this budget, or add its own data VHDX with owner approval.
   - This covers WO-10's log and metric stores, and WO-22's SeaweedFS and KubeVirt disks.

### B. Capacity checks are reported, not thrown

1. **`New-TwinfraPlan` returns checks instead of throwing for RAM or disk.**
   - It returns a `Checks` list. Each check has a name, a status (`PASS`, `WARN` or `SHORT`), the measured and required values, and a message.
   - **Disk** is `PASS` or `SHORT`, because provisioning consumes it.
   - **RAM** is `PASS` or `WARN`, labelled as "needed when the VM starts". `WARN` never blocks provisioning.
   - Every **safety refusal** still throws, with its message unchanged. That covers: not Administrator, Hyper-V missing, an invalid image lock, an unapproved region, a foreign or incomplete owned network, any overlap with an existing switch, NAT, route, address or VM CIDR, and an owned VM that differs from its stamp.
2. **`Format-TwinfraPlan` prints a `Checks:` block, one line per check.** Example line:
   `WARN  RAM to start the VM: 20.8 GiB free now, 24 GiB needed at start (20 VM + 4 host reserve); Start-TwinfraDev.ps1 checks again`.
3. **Exit codes and the refusal point.**
   - `-Plan` always prints the full plan and changes nothing.
   - It exits 0 when no check is `SHORT`, and 2 when any check is `SHORT`.
   - Without `-Plan`, a `SHORT` check stops provisioning **before the first write or download**, at the same point as today, with `Refusing: <check>; no changes made`.

### C. RAM checked when the VM starts

Add a new owner entry point: `deploy/hyperv/Start-TwinfraDev.ps1 [-Check] [-Region cairo-1]`.

1. **Preconditions.** It declares `#Requires -Version 7.4`, requires Administrator, and runs the same Hyper-V prerequisite checks as `New-TwinfraDev.ps1`.
2. **Inventory.** It uses the same host inventory as `New-TwinfraDev.ps1`. Move the collector into one shared function or file that both entry points use, with no second copy.
3. **Ownership.** It verifies `twinfra-dev-<region>` with exactly the checks `New-TwinfraPlan` applies to an existing owned VM: the stamp, the seed hash, a dynamic VHDX, CPU, static memory, nested virtualization, the switch and the owned network.
   - Extract these checks into one function used by both paths.
   - A missing, duplicate, unverified or foreign VM is refused with `no changes made`.
4. **State.**
   - `Running`: print `already Running` and exit 0 with no change.
   - `Off`: continue to the RAM check.
   - Any other state (Saved, Paused, Starting and so on): refuse, for the owner to resolve.
5. **RAM check.** Free RAM must be at least the VM's own static memory plus 4 GiB.
   - If it is short, print the measured and required values and the five process names using the most memory (summed working set per name, in GiB), then `close apps or stop other guests yourself; no changes made`, and exit 2.
   - Never stop, suspend or change any process, WSL distro or other VM.
6. **`-Check`** reports the result and exits 0 or 2 without starting anything.
7. **Start.** Otherwise run `Start-VM` on that VM only, then print its state and the free RAM after the start.
8. **Testable core.** Put the decision logic in a pure module function, `Test-TwinfraStart -Inventory -Region`. The entry point only gathers the inventory, calls the function and acts on the result.

### D. Rounding

- Show measured GiB values **rounded down** to 0.1, formatted with `InvariantCulture`. Comparisons keep the unrounded value.
- Rounding down keeps the display consistent with the result: 23.97 shows as 23.9 and is short of 24.

### E. Docs

- **`docs/dev-environment.md`:**
  - The capacity section: 20 GiB VHDX, 30 GiB free on E: at provisioning, and the RAM check at start.
  - The new disk budget table.
  - Step 2: `wsl --shutdown` is needed before the **start** step, not before the plan.
  - Step 3: the expected output has the `Checks:` block and the exit codes.
  - Step 6: replace the bare `Start-VM` with `Start-TwinfraDev.ps1 -Check`, then `Start-TwinfraDev.ps1`.
  - Step 11: no `install -d`; the PostgreSQL volume is 4 GiB and finite.
- **`deploy/hyperv/README.md`:** regenerate the fixture output, and document `Start-TwinfraDev.ps1`.
- The RAM budget table does not change.

### F. Tests

Offline and fixture-only, run by the existing gate.

- **Disk sizing:** the default is 20; `-DiskGB 20` is accepted and 19 is refused; 30 GiB free on E: is `PASS` and 29.9 is `SHORT`.
- **Plan, RAM short:** 20.9 GiB RAM and 113 GiB disk. The plan prints with RAM `WARN`, nothing is thrown, and the exit code is 0.
- **Plan, disk short:** 29 GiB disk. The plan prints with disk `SHORT` and exits 2. The provisioning path refuses before its first write.
- **Rewritten RAM tests:** the RAM tests at `test-plan.ps1:144` and `:154` become "plan with WARN". Every safety-refusal test stays unchanged and passes.
- **Rounding:** 20.8776245117188 shows as `20.8`. With 23.97 free and 24 required, the result is short and shows `23.9`.
- **`Test-TwinfraStart`:**
  - Off with 24.0 GiB free: start.
  - Off with 23.97 GiB free: short, exit 2, process list present.
  - Running: no-op.
  - Saved: refused.
  - Missing, duplicate, unverified or foreign VM: refused.
  - The required RAM comes from the VM's own static memory.
- **Rendered dev seed and overlays (both regions):**
  - growpart and resize_rootfs are on.
  - The loop-file mount unit is present, and an existing unowned file or directory is refused.
  - The PV and CNPG size is 4Gi.
  - The journald and kubelet log caps are present.
  - The production profile is byte-identical.
- **Pinning:** with a fake `ctr` and `crictl`, staging issues the pin label, and verification fails for an image that is not pinned.
- **Command inventory for `Start-TwinfraDev.ps1`,** using the same AST check as the existing reviewed list (`test-plan.ps1`, around line 31):
  - Allowed: the read-only inventory commands, `Get-Process` and `Start-VM`.
  - Rejected: `Stop-VM`, `Stop-Process`, `Suspend-VM`, `Set-VMMemory`, `wsl`, any `Remove-*` command and any DISM command.

## Out of scope

- RAM (20 GiB), the host reserve (4 GiB), vCPU (8) and the 10 GiB disk reserve on E:.
- Dynamic memory, and resizing an existing VM.
- Changes to any safety refusal.
- Stopping apps, WSL or guests automatically.
- The production profile.
- Data disks for later work orders.
- Running either script on the owner's host.

## Acceptance criteria

- The PR gate is green, including the licence gate and the six historical baselines.
- Fixture output is in the PR:
  - `-Plan` with 20.9 GiB RAM and 113 GiB disk: full plan, a 20 GiB VHDX, 30 GiB required, RAM `WARN`, exit 0.
  - `-Plan` with 29 GiB disk: disk `SHORT`, exit 2.
  - `Test-TwinfraStart` with 23.97 GiB: short.
- Live checks, by the owner after merge:
  1. `-Plan` prints the full plan, with measured values to 0.1 GiB.
  2. Provisioning creates `twinfra-dev-cairo-1` with a 20 GiB VHDX and leaves it Off, even while less than 24 GiB of RAM is free.
  3. `Start-TwinfraDev.ps1 -Check` reports the shortfall and the top processes.
  4. After the owner frees memory, the VM starts, and a second run reports `already Running`.
  5. Inside the VM, the root filesystem is about 19 GiB, and `/var/lib/twinfra/local-pv/postgres-1` is a 4 GiB mount.
  6. After the full bootstrap, every staged image is pinned, and the measured root usage is recorded against the budget.

  Record these in `docs/acceptance/dev-environment-<date>.md`, with the tester sign-off left Pending.

## Report back

The changed files, the disk budget and how it was computed, the three fixture outputs, the exit codes, the containerd version and its pin support, and the reviewed-command list for `Start-TwinfraDev.ps1`.
