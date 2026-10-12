# WO-31: Bring up `cairo-1` on the bare-metal Dell (`twinfra-dev-cairo-1`, 192.168.1.3)

**Status:** Approved for implementation (owner, 2026-10-12) · **Phase:** 2 (replaces WO-21's Hyper-V build as the way `cairo-1` is created)
**Author:** Claude · **Implementer:** Codex · **Branch:** `codex/wo-31-bare-metal-cairo-1` · **Depends on:** WO-29 merged (PR #36, #38), ADR-0048
**Decisions:** ADR-0048 (this host), ADR-0032, ADR-0038, ADR-0040, ADR-0044 (nftables is class `base-os`), ADR-0046, ADR-0047

## Why

ADR-0048 moves `cairo-1` from a Hyper-V VM on the laptop to bare-metal Ubuntu 24.04 on a Dell OptiPlex 9020. The host is installed and reachable (facts in ADR-0048), but the repository only knows how to build `cairo-1` as a VM. Four things in the repository assume a VM:
- a NoCloud seed with `NODE_IP=10.50.0.10` (`deploy/environments/dev/cairo-1/seed/user-data:84`);
- `stage-images --ssh <user>@10.50.0.10`;
- tunnels to `10.50.0.10`;
- `New-TwinfraDev.ps1` defaulting to `cairo-1`.

## Scope

### A. A bare-metal host profile for `cairo-1` (generated, never hand-edited)

1. **Bare-metal profile from the SSoT.** Render `cairo-1` as a bare-metal host profile instead of a NoCloud seed:
   - `NODE_IP=192.168.1.3`, interface `eno1`;
   - `CONTROL_PLANE_ENDPOINT=api.dev.cairo-1.twinfra.example.com:6443`;
   - Pods `10.110.0.0/16`, Services `10.111.0.0/16`, `PLATFORM_PROFILE=dev-cairo-1`, `IMAGE_STAGING=true`.

   The output is a generated environment file next to the overlay. `cairo-2` keeps its Hyper-V NoCloud seed unchanged. **The production profile stays byte-identical.**
2. **Address validation.** The generator refuses any pod or service range that overlaps `192.168.1.0/24` (now the node network), `10.20.0.0/24` or `10.50.0.0/24`. Add tests.
3. **One bootstrap script.** The host bootstrap is the existing `00-setup-ubuntu-host.sh` with the same pinned versions, the same `stage_bootstrap_images` step and the same verification. **Do not fork the bootstrap logic for bare metal.** The only differences are the inputs and how they are delivered.

### B. `tools/platform_dev.py`: new host actions over SSH

Default `--ssh twinfra-operator@192.168.1.3`; strict host-key checking; never a password.

1. **`host-check --context twinfra-dev-cairo-1`, read-only preflight.** It checks and reports:
   - Ubuntu 24.04, x86-64, VT-x, `/dev/kvm`;
   - RAM ≥ 24 GiB and the free space in the root filesystem and the volume group;
   - swap state, time sync, the node IP on `eno1`;
   - ports 6443, 2379-2380 and 10250 not yet in use;
   - the Secure Boot state, and the lockdown mode (`/sys/kernel/security/lockdown`);
   - the sshd effective settings (`sshd -T`).

   It changes nothing and exits non-zero on a blocking finding.
2. **`host-bootstrap --context twinfra-dev-cairo-1 [--check]`.**
   - Copies the generated environment file, `00-setup-ubuntu-host.sh` and `deploy/common/bootstrap-images.lock.json` to a root-owned staging directory on the host, verifying their SHA-256 after copying.
   - Runs the bootstrap with `sudo -n`.
   - It is idempotent: a rerun on a healthy node changes nothing.
   - `--check` runs only the bootstrap's own preflight.
3. **`stage-images`.** It now defaults to the host above instead of `10.50.0.10`. Nothing else changes.

### C. Host hardening: generated files plus one guarded apply step

1. **SSH.** Install `/etc/ssh/sshd_config.d/10-twinfra-hardening.conf` with:
   ```text
   PasswordAuthentication no
   KbdInteractiveAuthentication no
   PermitRootLogin no
   ```
   - **The `10-` prefix is required.** sshd keeps the *first* value it reads, and the installer's `50-cloud-init.conf` sets `PasswordAuthentication yes`.
   - Validate with `sshd -t`, reload, then confirm with `sshd -T`.
   - **Refuse to apply** unless the operator key login has just succeeded in the same run.
2. **Host firewall (nftables, `base-os`).** Write your own table `inet twinfra_host`, loaded by its own systemd unit from `/etc/twinfra/host-firewall.nft`.
   - **Never use `flush ruleset`, and never enable the stock `nftables.service`.** Its `/etc/nftables.conf` flushes everything, including Cilium's and kube-proxy's iptables-nft tables.
   - Rules filter **only traffic arriving on `eno1`**:
     - accept established and related connections, ICMP, and DHCP replies;
     - accept TCP 22 and 6443 from `192.168.1.0/24`;
     - drop everything else arriving on `eno1`.
   - Loopback and Cilium interfaces (`cilium_*`, `lxc*`) are never filtered.
   - **Lock-out guard.** Before loading, schedule a rollback (`systemd-run --on-active=120 nft delete table inet twinfra_host`). Cancel it only after a fresh SSH connection succeeds.
3. **Finite volume for PostgreSQL: `host-storage --apply`.**
   - Creates logical volume `ubuntu-vg/twinfra-postgres-1`, 20 GiB, ext4.
   - Mounts it at `/var/lib/twinfra/local-pv/postgres-1` through an fstab entry by UUID with `nodev,nosuid,noexec,noatime`. Owner 26:26, mode 0700.
   - kubelet gets a drop-in with `RequiresMountsFor=` that path.
   - It refuses if the volume group would keep less than 20 GiB free, or if the volume or directory already exists without the ownership marker. This is the same no-adoption rule as `lab/wsl/prepare-storage.sh`.
   - The PV and CNPG manifests stay at 20Gi; they don't change.
4. **Two items moved here from WO-30 (A4, A5), because they apply to every host:**
   - **Image pinning.** Both staging paths label every staged image `io.cri-containerd.pinned=pinned`, and verification fails unless `crictl inspecti` reports it pinned. Confirm that the containerd version installed by Module -1 honours the label; stop and report if it doesn't.
   - **Log caps.** journald `SystemMaxUse=500M`; kubelet `containerLogMaxSize: 10Mi`, `containerLogMaxFiles: 3`. Dev profile only.

### D. The Hyper-V path becomes `cairo-2` only

1. `deploy/hyperv/New-TwinfraDev.ps1` and `New-TwinfraPlan` default to `-Region cairo-2`.
2. `cairo-1` is refused with: `cairo-1 runs on bare metal (ADR-0048); no changes made`.
3. Update the fixtures and tests. Every other behaviour is unchanged.

### E. Docs

- **`docs/dev-environment.md`:**
  - **Part 1, "`cairo-1` on bare metal":** a numbered runbook (section F below).
  - **Part 2, "`cairo-2` cold standby on Hyper-V":** the existing VM procedure, relabelled.
  - **Tunnels and the hosts file:** they now target `192.168.1.3`.
- **`deploy/hyperv/README.md`:** relabel it for `cairo-2`.
- **`docs/work-orders/`:** copy in this work order and ADR-0048, plus the amendments to WO-21, WO-23, WO-24 and WO-30 from the handoff pack.

### F. Runbook for `cairo-1` (owner actions are marked; each step lists its command and expected output)

1. **Owner, at the Dell or over SSH as `twinfra`: create the automation account.**
   ```bash
   sudo adduser --disabled-password --gecos "" twinfra-operator
   sudo install -d -m 700 -o twinfra-operator -g twinfra-operator /home/twinfra-operator/.ssh
   sudo install -m 600 -o twinfra-operator -g twinfra-operator ~/.ssh/authorized_keys /home/twinfra-operator/.ssh/authorized_keys
   echo 'twinfra-operator ALL=(ALL) NOPASSWD:ALL' | sudo tee /etc/sudoers.d/90-twinfra-operator
   sudo chmod 440 /etc/sudoers.d/90-twinfra-operator && sudo visudo -cf /etc/sudoers.d/90-twinfra-operator
   ```
   Once `twinfra-operator` works, the owner may remove `/etc/sudoers.d/90-twinfra`, so the personal account needs a password for sudo again.
2. **Owner, on the laptop as administrator: map the API name.** Add `192.168.1.3 api.dev.cairo-1.twinfra.example.com` to the Windows hosts file.
3. **Read-only preflight:** `host-check`.
4. **Hardening:** SSH first, then the firewall.
5. **Storage:** `host-storage --apply`.
6. **Bootstrap:** `host-bootstrap`, which also stages the bootstrap images.
7. **kubeconfig:** copy it to the laptop; the context is `twinfra-dev-cairo-1`.
8. **Application images:** `stage-images`.
9. **Dev CA:** `platform_dev_ca.py --apply`.
10. **Platform:** secrets and the platform apply, then Argo CD.
11. **Tunnels and the browser:** check over HTTPS.

### G. Tests (offline)

- **Profile:** the bare-metal profile renders with the values in A.1.
- **Address overlaps:** `192.168.1.0/24`, `10.20.0.0/24` and `10.50.0.0/24` are refused.
- **Production:** the profile is byte-identical.
- **Host actions with a fake `ssh`/`scp`:**
  - `host-check` makes no changes;
  - `host-bootstrap` verifies hashes and refuses if `sudo -n` fails;
  - a rerun is a no-op.
- **sshd:** the drop-in is named `10-…` and contains exactly the three settings. Apply is refused when the key-login probe fails.
- **Firewall:**
  - the rendered file has no `flush ruleset`;
  - every rule is limited to `iifname "eno1"`;
  - the rollback timer is scheduled before the load.
- **Storage:** existing data is refused, the volume-group reserve is enforced, and the fstab options are correct.
- **Image pinning:** the label is issued, and verification fails for an unpinned image.
- **Hyper-V:** `cairo-1` is refused and `cairo-2` is the default.

## Out of scope

- A separate VLAN, a UPS, kube-vip or HA, a second node, and a warm `cairo-2` (WO-24).
- WO-30's Hyper-V sizing and checks, which now apply to `cairo-2` only.
- Running anything on the host. That is the owner's job, or the owner may ask Claude to run it over SSH.

## Acceptance criteria

**Static:** the PR gate is green, including the licence gate and the six historical baselines.

**Live checks, by the owner after merge:**
1. **Hardware stability.**
   - Dell ePSA **Thorough** memory test passes (F12 → Diagnostics).
   - After bootstrap, a **24-hour soak** with every pod Running and no freeze.
   - `journalctl -k` shows no machine-check or hung-task errors.
2. **Host checks.**
   - `host-check` passes.
   - `sshd -T` shows password login off and root login off.
   - `/sys/kernel/security/lockdown` shows `[integrity]`.
3. **Firewall, tested from the laptop.** 22 and 6443 answer. 10250 and 2379 do not.
4. **Cluster.**
   - The node is Ready.
   - Cilium is healthy under lockdown (`cilium-dbg status`).
   - Every staged image is pinned.
   - `/var/lib/twinfra/local-pv/postgres-1` is a 20 GiB mount.
   - All dev overlay pods are Running.
5. **etcd disk latency.** Record the WAL fsync p99 from etcd's own metric (`etcd_disk_wal_fsync_duration_seconds`). The target is under 10 ms. Report the value even if it misses.
6. **From the laptop:**
   - `kubectl --context twinfra-dev-cairo-1 get nodes` works through the API name;
   - the console and Keycloak load over HTTPS through the tunnels.

**Receipt:** `docs/acceptance/dev-environment-<date>.md`, with the tester sign-off left Pending.

## Report back

The changed files, the rendered bare-metal profile, the `host-check` output against a fixture, the firewall ruleset, the containerd version and whether it supports pinning, and any deviation.

## Amendment 1 (2026-10-12, architect): resolves Codex's two stops

### 1. Which rendered files may change, and how much

A.1 ("`cairo-2` keeps its seed unchanged") and "production stays byte-identical" meant **no change to region values or behaviour**. They did not forbid shared, guarded code. `tools/platform_dev.py:252` embeds the shared `deploy/common/stage-images.py` into every seed, and the production `user-data.yaml` embeds it too. So C.4 must change those renders. The allowed changes are:

| Render | Allowed diff against `main` | Nothing else may change |
| --- | --- | --- |
| `cairo-2` Hyper-V seed | (a) the embedded `stage-images.py` (the pin label and its verification); (b) the dev log caps (journald and kubelet), rendered as dev-profile values | Node IP, CIDRs, names, versions, every other line |
| Production `user-data.yaml` (and `user-data-remote.yaml` if it embeds the agent) | Only the embedded `stage-images.py` | Everything else, byte for byte. Log caps are **dev-only** values and must not appear in production |

**Why the production change is safe.** The staging agent runs only when `IMAGE_STAGING=true`, and production refuses that setting (WO-29 Amendment 1 B, already tested). So production behaviour does not change. This is the same allowance WO-29 Amendment 1 B.3 gave for the guarded dev step.

**Tests:**
- For each render, mask the allowed blocks, then compare with the render from `main`. They must be identical.
- The existing test still passes: production with `IMAGE_STAGING=true` is refused.
- Say in the PR which renders changed and why.

### 2. `host-check` before and after bootstrap

`host-check` decides its mode from the node's state.

- **Before bootstrap.** There is no bootstrap result, or it isn't `ready`. Ports 6443, 2379–2380 and 10250 must be free; any listener on them is a blocking finding.
- **After bootstrap.** This mode applies only when **all** of these are true. If any fails, it's a blocking finding:
  1. `/var/lib/vcloud-host/result.json`, written by `write_result` in `00-setup-ubuntu-host.sh`, has `status` `ready`. Its `kubernetes` value equals the pinned version, and its `mirror_status` is `staged-verified`.
  2. Run read-only with `sudo -n` and `/etc/kubernetes/admin.conf`. The `kube-system/kubeadm-config` ConfigMap has `clusterName` `twinfra-dev-cairo-1` and `controlPlaneEndpoint` `api.dev.cairo-1.twinfra.example.com:6443`. The node's `InternalIP` is `192.168.1.3`.
  3. `ss -ltnpH` shows the listeners owned by exactly the expected processes:
     - 6443 → `kube-apiserver`;
     - 2379–2380 → `etcd`;
     - 10250 → `kubelet`.

  When all three hold, those ports are reported `PASS (bootstrap-owned cluster verified)`.

The live acceptance item "`host-check` passes" means this after-bootstrap mode. `host-check` stays read-only in both modes.

**Tests (fake `ssh`):**
- Before bootstrap with a port taken: blocking.
- After bootstrap with everything matching: PASS.
- `result.json` not `ready`: blocking.
- Wrong `clusterName` or `InternalIP`: blocking.
- 6443 owned by another process: blocking.
