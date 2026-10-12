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

## Amendment 2 (2026-10-12, architect): the first live bootstrap failed in Module -1; fix the BPF mount and allow a re-run

**Evidence from the Dell.** The bootstrap was `twinfra-bootstrap-cb3b0b124ec249d1b7a6fa7e34fc7a22`, run after the requested reboot; `result.json` shows `phase: containerd`, `status: failed`. The facts:
- systemd is 255.4-1ubuntu8.17, which logs: `sys-fs-bpf.mount: Cannot create mount unit for API file system /sys/fs/bpf. Refusing.`
- `Failed to restart containerd.service: Unit sys-fs-bpf.mount has a bad unit file setting.` That is `00-setup-ubuntu-host.sh` line 587.
- `/sys/fs/bpf` **is already mounted** by systemd itself (`bpf rw,nosuid,nodev,noexec,relatime,mode=700`).
- The script writes `/etc/systemd/system/sys-fs-bpf.mount` (lines 326–343) and enables it (line 342). Its containerd drop-in has `Requires=sys-fs-bpf.mount` and `After=sys-fs-bpf.mount` (lines 576–583).

Ubuntu 24.04's systemd treats `/sys/fs/bpf` as an API file system and refuses unit files for it. **This affects production too.** So this amendment allows changing the shared Module -1 and the production renders, **limited to the items below**.

### Fix in the shared `00-setup-ubuntu-host.sh`

1. **No mount unit.** Stop writing `sys-fs-bpf.mount`.
   - If `/sys/fs/bpf` is not `bpf`, run `mount -t bpf -o rw,nosuid,nodev,noexec,mode=700 bpffs /sys/fs/bpf`.
   - Keep the existing `findmnt` FSTYPE check. On systemd hosts, PID 1 already mounts it at boot.
2. **containerd drop-in.** Replace `Requires=`/`After=sys-fs-bpf.mount` with `RequiresMountsFor=/sys/fs/bpf`. It binds to systemd's own mount unit.
3. **Migration, with no adoption.** If `/etc/systemd/system/sys-fs-bpf.mount` exists **byte-identical** to the content the old script wrote, then:
   - `systemctl disable` it, which removes the `multi-user.target.wants` link;
   - delete the file;
   - `daemon-reload`.

   Keep the old content in the script as a constant for this comparison. If the file differs, or a `sys-fs-bpf.mount.vcloud-original` exists, stop with a clear message and change nothing.

### Fix in `deploy/common/host-admin.py`: allow a re-run with new inputs

The previous run left `/var/lib/twinfra/host-bootstrap/receipt.json` with the old input hashes. Fixing the script changes its hash, so `bootstrap_apply` would refuse with "different bootstrap staging". Replace the staging set with newly verified inputs **only** when all of these hold:
- the existing receipt is root-owned and valid;
- there is **no** `complete.json`;
- no `twinfra-bootstrap-*` unit is active;
- `result.json` is not `ready`.

A completed bootstrap with different inputs is still refused; upgrades are a later work order.

### Tests

- **Rendered script:** it writes no `.mount` unit for `/sys/fs/bpf`, and the containerd drop-in has `RequiresMountsFor=/sys/fs/bpf`. ShellCheck passes.
- **Migration with a fake `systemctl`:** the identical old file is disabled and removed; a different file is refused; a `.vcloud-original` backup is refused.
- **`host-admin.py`:** these are allowed or refused as follows:
  - an incomplete previous run with an owned receipt: replaced;
  - with `complete.json`: refused;
  - with an active unit: refused;
  - with an unowned receipt: refused.
- **Production render:** the diff against `main` is limited to the BPF and containerd drop-in blocks. Say so in the PR.

### Live (owner, after merge)

Don't change the Dell by hand: it keeps the failed state so the migration runs against the real host. After the merge:
1. Update `E:\vCloud` to `main`.
2. Run `host-bootstrap` again.
3. Expected: the old unit is removed, containerd starts, the bootstrap images are staged and `kubeadm init` completes.

## Amendment 3 (2026-10-12, architect): staged images named with both a tag and a digest are invisible to the CRI

**Evidence from the Dell.** Bootstrap `twinfra-bootstrap-868ae4c1c01843cc971a151f9b41473b` ran PR #41's code. The BPF migration worked: `Removed ".../multi-user.target.wants/sys-fs-bpf.mount"`, and containerd started. It then stopped at `phase: bootstrap-image-staging` with `CRI missing, digest mismatch or unpinned after staging: cilium`.
- The runtime is containerd **2.2.1** (Ubuntu `2.2.1-0ubuntu1~24.04.3`), with crictl v1.36.0.
- `crictl images -o json` shows the image staged correctly: `pinned: true`, and `repoDigests` contains `registry.twinfra.example.com/quay.io/cilium/cilium:v1.20.2@sha256:2939231d…`.
- `crictl inspecti` returns "no such image" for all three forms: `<repo>:v1.20.2@<digest>`, `<repo>@<digest>` and `<repo>:v1.20.2`.

**Cause.** The CRI resolves a reference with `ParseDockerRef`, which **drops the tag when a digest is present**. It therefore looks up `<repo>@<digest>`, and no image record has that name. **kubelet does the same lookup**, so at run time it would treat the Cilium images as missing and try to pull them. With no upstream fallback, Cilium would never start. This affects every lock entry whose canonical name has both a tag and a digest: the Cilium agent, operator and envoy. Tag-only entries work, and they verified and pinned on the Dell.

### Fix (`deploy/common/stage-images.py` and `tools/platform_image_staging.py`)

1. **Add the digest-only name.** For every entry whose canonical reference has both a tag and a digest, also `ctr images tag` it to the **normalised** name `<canonical repository>@<digest>`. Label it `io.cri-containerd.image=managed io.cri-containerd.pinned=pinned`. Keep the existing name.
2. **Verify the normalised name.** `crictl inspecti` uses `<repository>@<digest>` when there is a digest, otherwise the canonical name. It checks the digest and `pinned: true`.
3. **Re-run.** On a re-run, an existing correct `tag@digest` record with the digest-only name missing counts as *repairable* (add the name and pin it), not as a digest mismatch.
4. **Tests.** Use a fake `crictl` that resolves only the normalised form, as containerd does:
   - a `tag@digest` entry passes after staging;
   - a tag-only entry is unchanged;
   - an actual digest mismatch still fails;
   - `--check` makes no changes.

### Scope of render changes

Only the embedded `stage-images.py` in the `cairo-2` seed may change. Production renders only reference the agent's path, so they stay unchanged.

### Live (owner, after merge)

Run `host-bootstrap` again. Amendment 2 allows this because the previous run is incomplete.

Add to acceptance: on the Dell, `kubectl -n kube-system get events` shows **no `Pulling` events** for Cilium images, so kubelet resolved the staged images locally.

## Amendment 4 (2026-10-12, architect): the etcd kubeadm patch has no merge key

**Evidence from the Dell.** Bootstrap `twinfra-bootstrap-bfdaa1bcf84546329cdeef7667783fb7` ran merged `main` `4cb97b8`. Image staging **passed** (`{"status": "passed", "images": 11}`, `mirror_status: staged-verified`). Then the kubeadm **dry-run preview** (`00-setup-ubuntu-host.sh:2744-2745`) failed:

```text
could not apply the following patch of type "application/strategic-merge-patch+json" to target "etcd":
{"spec":{"containers":[{"name":"etcd","volumeMounts":[{"name":"etcd-certs","readOnly":true}]}]}}
: map: map[name:etcd-certs readOnly:true] does not contain declared merge key: mountPath
```

**Cause.** `render_etcd_patch` (lines 2705–2716; written to `$STATE_DIR/kubeadm-patches/etcd+strategic.yaml` at line 834) lists the volume mount by `name` only. Kubernetes declares `patchMergeKey: mountPath` for `volumeMounts`. This code dates from 2026-10-06 and had never run against kubeadm.

**Host state.** The failure came from the preview, so the Dell has no `/etc/kubernetes/manifests` files, no PKI, no `admin.conf` and no `/var/lib/etcd` data. **Nothing needs to be reset.**

### Fix (shared `00-setup-ubuntu-host.sh`; production renders may change only in this block and its derived checksums)

1. **Add the merge key.** The patch item must include `mountPath`. Take it from the rendered kubeadm configuration: `<certificatesDir>/etcd`, which by default is `/etc/kubernetes/pki/etcd`. Keep `name: etcd-certs` and `readOnly: true`.
2. **Check the result after the preview.** Confirm that the rendered `etcd.yaml` has exactly one `etcd-certs` mount at that path, with `readOnly: true`. Fail clearly otherwise.
3. **CI guard for this whole class of bug.** Three Module -1 defects reached the Dell only because nothing exercised the real tools.
   - Add a CI step that downloads **kubeadm v1.36.5** from `dl.k8s.io`, verified against its published SHA-256 (kubeadm is already a registered component, not a new tool).
   - It renders the dev and production kubeadm configurations and patches.
   - It runs `kubeadm init phase control-plane all --dry-run` and `kubeadm init phase etcd local --dry-run` with `KUBEADM_INIT_DRYRUN_DIR` set, then asserts the result from item 2.
   - If this can't run on the GitHub runner without anything beyond `sudo` and `dl.k8s.io`, stop and report rather than skipping it.

### Live (owner, after merge)

Pull `main` and run `host-bootstrap` again. Amendment 2's re-run rule applies.

## Amendment 5 (2026-10-12, architect): the final validation step uses a wrong `tkn` flag, and a half-finished bootstrap cannot resume

**Evidence from the Dell.** Bootstrap `twinfra-bootstrap-eaee89bc810f4f3dae4a5f4e6f41c507` (15:57 UTC) used PR #43's code. **`kubeadm init` succeeded**, and the cluster is healthy:
- node `twinfra-dev-cairo-1` is `Ready` with InternalIP 192.168.1.3 and containerd 2.2.1;
- etcd, the API server, controller-manager, scheduler, Cilium (agent, operator, envoy) and CoreDNS are all `Running`, with Cilium on the staged digest-only images;
- the SSoT namespaces and default-deny policies were applied.

The run then failed in the last phase, `validation`, at `00-setup-ubuntu-host.sh:3285`: `Error: unknown flag: --client`. That came from `tkn version --client`; tkn is pinned at v0.46.1. `result.json` therefore says `status: failed, phase: validation`.

**Then the next `host-bootstrap` was refused.** `host-check` saw `Reserved ports: BLOCK, occupied before verified bootstrap`. Amendment 1's two modes don't cover a cluster that kubeadm created but whose bootstrap didn't reach `ready`.

### Fix 1: the version line (shared script; production render may change only here and in derived checksums)

1. **The `tkn` call.** Replace `tkn version --client` with the form the pinned tkn v0.46.1 supports for client-only output. That is expected to be `tkn version --component client`; check it against the pinned binary's `--help`.
2. **Check every version call.** Review every other version call on lines 3284–3285 (and the HPC and GPU ones) against its pinned tool in the same way.
3. **CI guard.** Extend the Amendment 4 CI step:
   - Install the pinned CLI tools exactly as `install_cli` does (same URLs, same checksums) into a temporary directory.
   - Run the exact version commands from `validate_host`.
   - If that needs more than `sudo` and the pinned download hosts, stop and report.

### Fix 2: resume an incomplete bootstrap (`host-admin.py`, `host-check`)

1. **A third mode, `resume`.** It applies only when **all** of these are true:
   - `result.json` exists and is **not** `ready`;
   - `/etc/kubernetes/admin.conf` exists;
   - `kube-system/kubeadm-config` has `clusterName` `twinfra-dev-cairo-1` and `controlPlaneEndpoint` `api.dev.cairo-1.twinfra.example.com:6443`;
   - the node `twinfra-dev-cairo-1` has InternalIP `192.168.1.3`;
   - `ss` shows 6443 / 2379–2380 / 10250 owned by `kube-apiserver` / `etcd` / `kubelet`.

   If anything differs, it stays BLOCK.
2. **What the mode means.**
   - In `resume`, the ports report `PASS (bootstrap-owned cluster, incomplete)`, and `host-bootstrap` may run Module -1 again.
   - The acceptance item "`host-check` passes" still means the **post-bootstrap (`ready`)** mode.
3. **The re-run must not touch the existing cluster.** Confirm, and test, that Module -1 skips `kubeadm init` when the cluster already exists and is the expected one: the same identity checks as above. **If Module -1 would re-initialise, reset or overwrite the existing cluster, stop and report.** Never add an automatic `kubeadm reset`.
4. **Staging inputs.** The input-replacement rule from Amendment 2 still applies; the result is not `ready` and there's no `complete.json`.
5. **Tests (fake host):**
   - `resume` passes with everything matching;
   - a wrong cluster name, InternalIP or port owner blocks;
   - with no `admin.conf` and ports in use: blocked;
   - Module -1's skip-init path, with a fake `kubeadm` that fails if `init` is called.

### Live (owner, after merge, from merged `main` only)

1. Run `host-check`: the mode is `resume`. (Confirmed live 2026-10-12 with `main` `cf4b659`.)
2. Run `host-bootstrap`: it should finish with `ready`, then the dev log caps, the node labels and `complete.json`.
3. Run `host-check` again: mode `post-bootstrap`, status `passed`.

## Amendment 6 (2026-10-12, architect): `argocd` needs `HOME`, and a failure exit code collides with "reboot required"

**Evidence from the Dell.** Bootstrap `twinfra-bootstrap-0435eff9c22a47e0b82fab0fb654f366` ran merged `main` `cf4b659`. Resume mode worked, and the validation line now passes `tkn` (it printed `0.46.1`). The next command, `argocd version --client`, failed:

```text
time="2026-10-12T17:56:44Z" level=fatal msg="$HOME is not defined"
[vCloud] Failed in phase validation at line 3285 (exit 20). Inspect the journal; no automatic reset.
```

`host-admin.py` then reported `reboot-required`, but **no reboot is needed**:
- there is no `/var/run/reboot-required`;
- the running kernel is the only one installed;
- the boot command line already has the 2 MiB and 1 GiB hugepage settings, and both are allocated.

**Two defects.**
1. **No `HOME`.** Module -1 runs without `HOME` under the transient systemd unit, and in production under cloud-init it may have none either. The `argocd` CLI refuses to run without it. The CI step from Amendment 5 kept the runner's `HOME` (commit "preserve runner home during CLI validation"), which **hid this defect**.
2. **Exit code 20 is ambiguous.** The failure handler exits with the failing command's status. Argo CD's generic error is **20**, the same code Module -1 reserves for "reboot required" (`exit 20` after `write_result reboot-required`).

### Fix (shared script and `host-admin.py`; production render may change only in these blocks and derived checksums)

1. **`HOME` in Module -1.** The script already requires root, so set `HOME` near the start if it's missing: `: "${HOME:=/root}"; export HOME`. Don't change any tool's configuration.
2. **Reserve exit code 20.** The failure handler must exit with a fixed code (**1**) and **never** 20. Exit 20 comes only from the deliberate reboot-required path.
3. **Belt and braces in `host-admin.py`.** Report `reboot-required` only when the unit's exit code is 20 **and** `result.json` has `status: reboot-required`. Otherwise report `failed` and point to the journal.
4. **Make CI match the host.** The CLI validation step must run the version commands in a **minimal environment**, like the systemd unit: `env -i PATH=<pinned bin dir>:/usr/bin:/bin`, with no `HOME`. It must exercise the script's own `HOME` default. Remove the runner-`HOME` workaround.
5. **Tests:**
   - a fake `argocd` that fails without `HOME` passes once the script sets the default;
   - a failing command that exits 20 makes the script exit 1;
   - the reboot path still exits 20;
   - `host-admin` treats exit 20 with a non-reboot `result.json` as `failed`.

### Live (owner, after merge, from `E:\twinfra-live`)

Don't reboot. Run, in order:
1. `host-check`, expecting `resume`;
2. `host-bootstrap`, expecting `passed`;
3. `host-check`, expecting `post-bootstrap` / `passed`.

## Amendment 7 (2026-10-13, architect): the manifest-contract checker crashes on a single `List` object

**Evidence from the Dell.** Bootstrap `twinfra-bootstrap-ef50942ca1534590a73d925220e465d6` ran merged `main` `1f7d86f`.
- **Amendment 6 works:** every version command passed, and the failure exited with 1, not 20.
- **Cilium status is OK.**
- **It then failed at `00-setup-ubuntu-host.sh:3307-3308`:**
  ```text
  File "/var/lib/vcloud-host/check-manifest-contract.py", line 14, in flatten
      if obj.get('kind') == 'List':
  AttributeError: 'str' object has no attribute 'get'
  ```

**Cause.** `kubectl get daemonset/cilium daemonset/cilium-envoy deployment/cilium-operator -o json` returns **one** object of kind `List`. The checker's `main()` passes it straight to `flatten()`, which iterates the dictionary's keys. The other caller, `validate_manifests` (line 2703), wraps its input with `yq '[.]'`. This one doesn't, and neither does the GPU caller at line 3322.

**Pre-check on the live cluster (read-only).** Wrapping the same input with `jq -c '[.]'` and running the installed checker gave `SSoT contract: passed; 0 findings`. The remaining gates also hold:
- `kube-proxy-replacement` is `true`;
- node capacity is `hugepages-2Mi: 256Mi` and `hugepages-1Gi: 1Gi`, against 128 × 2 MiB and 1 × 1 GiB required;
- smoke tests are off for dev.

So this is expected to be the **last** validation defect before `ready`.

### Fix (shared script, inside the generated checker; production render may change only here and in derived checksums)

1. **Normalise input in the checker's `main()`.**
   - A top-level JSON object becomes a one-element list; a list is used as is.
   - Any element that is not an object is reported as a **violation**, never a traceback.
   - Keep `flatten()`'s handling of `kind: List`.
2. **Keep the callers as they are.** The fix is in one place and covers lines 3307 and 3322.
3. **Tests.** Run the checker on:
   - a single `kind: List` object, as `kubectl get a b c -o json` returns it: pass;
   - a list of objects: unchanged behaviour;
   - a bare string or number: a violation, exit 1, no traceback;
   - a real Cilium DaemonSet fixture with the dev node-exception policy: `0 findings`.

### Live (owner, after merge, from `E:\twinfra-live`)

Run `host-bootstrap`. Expected:
- `passed`, followed by the dev log caps (kubelet restarts once), the node labels and `complete.json`.

Then run `host-check`. Expected: `post-bootstrap` / `passed`.

## Amendment 8 (2026-10-13, architect): a skipped step "fails" under `set -e`

**Evidence from the Dell.** Bootstrap `twinfra-bootstrap-2681ad38646b4cde95166a129004336f` ran merged `main` `24b8bdb`. **Every validation gate passed**:
- the contract checker reported `passed; 0 findings` twice;
- Cilium was OK;
- the log says `Requested host and readiness gates passed`.

It then failed at line **3429**, `run_smoke_tests`, the last step before `write_result ready`.

**Cause.** Line 3230 is `[[ $BOOTSTRAP_K8S == true && $RUN_SMOKE_TESTS == true ]] || return`. When the test is false, as for dev with `RUN_SMOKE_TESTS=false`, a bare `return` returns the failed test's status, **1**. Under `set -Eeuo pipefail` with the ERR trap, that counts as a failure. The same pattern is at line **833** in `bootstrap_kubernetes`; it's harmless only while `BOOTSTRAP_K8S=true`.

### Fix (shared script; production render may change only in these lines and derived checksums)

1. Change both guards to `|| return 0`.
2. **Audit the whole script** for other early-return guards that return the failed test's status, such as `|| return` at the end of a line, `&& return` or `|| return;`. Fix every one that is meant as "skip". List them in the PR.
3. **Tests:**
   - Run `main`'s tail sequence (`validate_host` → `run_smoke_tests` → `write_result`) with the shell options and ERR trap used in production. Stub the cluster calls. Use `RUN_SMOKE_TESTS=false` and then `true`. Both must reach `write_result ready`.
   - Repeat for `bootstrap_kubernetes` with `BOOTSTRAP_K8S=false`.
   - Add a static test that fails on any `|| return` or `&& return` guard without an explicit status.

### Live (owner, after merge, from `E:\twinfra-live`)

`git pull` must show `00-setup-ubuntu-host.sh` changed. Then:
1. Run `host-bootstrap`. Expected: `passed`.
2. Run `host-check`. Expected: `post-bootstrap` / `passed`.
