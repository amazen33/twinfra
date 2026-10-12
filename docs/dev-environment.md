# Twinfra dev environment

[ADR-0048](adr/0048-cairo-1-on-bare-metal-host.md) makes the Dell the primary
`twinfra-dev-cairo-1`. The laptop is the operator workstation and hosts the
`cairo-2` cold standby. [WO-31 Amendment 1](work-orders/WO-31-bare-metal-cairo-1.md)
defines the permitted render differences and post-bootstrap ownership checks.
All live acceptance is **Pending**. Codex ran only static/fixture checks.

## Part 1: `cairo-1` on bare metal

Ubuntu 24.04, x86-64, at least 24 GiB RAM, VT-x and `/dev/kvm`, Secure Boot and
lockdown `[integrity]`, synchronized time, and `192.168.1.3/24` on `eno1` are
required. The Dell's 100 GiB root LV holds the OS/containerd/etcd; PostgreSQL uses
a separate **20 GiB** LV in `ubuntu-vg`, which must retain **20 GiB free**.
The cluster's stable API is `api.dev.cairo-1.twinfra.example.com:6443`.
Pods use `10.110.0.0/16`, services `10.111.0.0/16`. No router forwarding.

The generated [host.env](../deploy/environments/dev/cairo-1/host.env) replaces
cairo-1's NoCloud seed. The exact shared [Module -1](../00-setup-ubuntu-host.sh)
remains the only bootstrap, with its existing version pins and checks.
Linux hostname is `twinfra-dev-cairo-1`; the kubelet's approved node identifier
is `twinfra-dev-cairo-1`, taken from the SSoT and matching the Local PV affinity.
GPU/vLLM, HPC and Spinifex remain disabled; OpenBao remains sealed until WO-08.
Planning allowances total **20 GiB**, not measured use:

| Component | Budget |
| --- | --- |
| Ubuntu, containerd and filesystem cache | 2 GiB |
| kubeadm control plane, etcd, kubelet, CoreDNS | 2.5 GiB |
| Cilium and Envoy | 1.5 GiB |
| Argo CD controller/repo/API and Valkey | 1.5 GiB |
| CNPG operator and PostgreSQL 18/pgvector | 2.5 GiB |
| Keycloak | 2.25 GiB |
| OpenBao, sealed | 0.5 GiB |
| APISIX standalone gateway | 0.5 GiB |
| Twinfra console | 0.5 GiB |
| MiniStack | 0.75 GiB |
| HugePages: 128 × 2 MiB + 1 × 1 GiB | 1.25 GiB |
| Budget headroom | **4.25 GiB** |

### Numbered owner runbook

These commands are for the **owner after review/merge**, not executed by Codex.
Run workstation commands from `E:/vCloud` with the registered Python, PyYAML,
cryptography, kubectl and OpenSSH tools. Verify the Dell SSH host-key fingerprint
at its console before recording it in known_hosts; never bypass host-key checks.
No step touches pCloud, `iotee-nat`, IOT-EE or the WSL controller distro.

1. **Owner at the Dell, as `twinfra`: create the automation account.**

   ```bash
   sudo adduser --disabled-password --gecos "" twinfra-operator
   sudo install -d -m 700 -o twinfra-operator -g twinfra-operator /home/twinfra-operator/.ssh
   sudo install -m 600 -o twinfra-operator -g twinfra-operator ~/.ssh/authorized_keys /home/twinfra-operator/.ssh/authorized_keys
   echo 'twinfra-operator ALL=(ALL) NOPASSWD:ALL' | sudo tee /etc/sudoers.d/90-twinfra-operator
   sudo chmod 440 /etc/sudoers.d/90-twinfra-operator
   sudo visudo -cf /etc/sudoers.d/90-twinfra-operator
   ```

   Expected: sudoers syntax OK. From the laptop verify a key-only connection:

   ```powershell
   ssh -o BatchMode=yes -o StrictHostKeyChecking=yes twinfra-operator@192.168.1.3 'sudo -n true'
   ```

   Expected: exit 0 without prompts. Only after this succeeds, the owner may
   remove `/etc/sudoers.d/90-twinfra` to restore password-required personal sudo.

2. **Owner, Administrator PowerShell: map the API name.** Add this line to
   `C:/Windows/System32/drivers/etc/hosts`:

   ```text
   192.168.1.3 api.dev.cairo-1.twinfra.example.com
   ```

   Expected: `Resolve-DnsName api.dev.cairo-1.twinfra.example.com` resolves to
   `192.168.1.3`. Browser authorities below map to loopback, not the Dell.

3. **Read-only preflight on the laptop.**

   ```powershell
   python tools/platform_dev.py host-check --context twinfra-dev-cairo-1
   python tools/platform_dev.py host-bootstrap --context twinfra-dev-cairo-1 --check
   ```

   Expected: `status: passed`, mode `pre-bootstrap`; reserved ports free.
   `--check` streams only the unchanged Module -1 preflight, with no copies,
   APT, runtime or configuration writes. SSH defaults to
   `twinfra-operator@192.168.1.3`, strict host keys, public-key authentication,
   no password/keyboard prompts and no connection multiplexing.
   After bootstrap, host-check passes only with the exact ready/version/staged
   result, kubeadm cluster name/endpoint, node InternalIP and all expected `ss`
   process owners; any mismatch blocks. Active swap is reported before bootstrap;
   Module -1 disables it. Free root/VG space and effective SSH settings are reported.

4. **Owner hardening: SSH first, then the firewall.** Ubuntu's base-os nftables
   package must be installed by the owner if absent (`sudo apt-get install nftables`).
   Existing LVM/ext4 tools come from the installed Ubuntu system.

   ```powershell
   python tools/platform_dev.py host-ssh --context twinfra-dev-cairo-1 --apply
   python tools/platform_dev.py host-firewall --context twinfra-dev-cairo-1 --apply
   ```

   Expected: fresh key login succeeds before each apply; SSH writes exactly
   `PasswordAuthentication no`, `KbdInteractiveAuthentication no`,
   `PermitRootLogin no` to `10-twinfra-hardening.conf`, validates/reloads and
   confirms `sshd -T`. The `10-` prefix wins before installer's `50-cloud-init.conf`.
   The generated [firewall](../deploy/environments/dev/cairo-1/host/host-firewall.nft)
   atomically replaces only `inet twinfra_host`, filtering `eno1` host ingress.
   It allows established/related, ICMP, DHCP replies, and LAN TCP 22/6443;
   other host ingress on that interface drops. There is no forward chain.
   One prerouting rule, after conntrack and before DNAT, drops **new** traffic
   from `eno1` addressed to the SSoT dev pod/service CIDRs (`10.110.0.0/16`,
   `10.111.0.0/16`). GitHub responses to pod-initiated connections remain allowed.
   Other interfaces use accept policy.
   A 120-second rollback is armed before load and cancelled only after a fresh
   SSH connection succeeds. On connection failure, leave the timer armed and
   recover at the Dell console. Only after that fresh login and timer cancellation
   is `twinfra-host-firewall.service` enabled. The rollback deletes the owned table
   and disables that service, even if table deletion fails;
   the stock service is never enabled, and existing enabled/active stock service
   or unowned table/configuration is refused. Foreign tables are untouched.

5. **Owner storage action.**

   ```powershell
   python tools/platform_dev.py host-storage --context twinfra-dev-cairo-1 --apply
   ```

   Expected: `ubuntu-vg/twinfra-postgres-1`, 20 GiB, ext4 UUID mount at
   `/var/lib/twinfra/local-pv/postgres-1`, fstab options
   `nodev,nosuid,noexec,noatime,nofail,x-systemd.device-timeout=30s`,
   owner 26:26, mode 0700. Kubelet gets `RequiresMountsFor=`. No adoption of
   unmarked existing data, LVs, directories or links. At least 20 GiB remains
   free in the VG. The vetted PV and CNPG cluster remain **20Gi**, unchanged.
   Partial storage operations require owner inspection before retrying.

6. **Owner bootstrap action.**

   ```powershell
   python tools/platform_dev.py host-bootstrap --context twinfra-dev-cairo-1
   ```

   Expected: SHA-256 verified copies in root-owned `/var/lib/twinfra/host-bootstrap`,
   root-owned env/lock/staging-agent delivery, then the original bootstrap via
   a transient `twinfra-bootstrap-<id>.service`, started using `sudo -n` and
   `systemd-run --no-block`. PID 1 owns the process, with no start/runtime timeout;
   it survives an SSH disconnect. A root-owned lock covers staging/unit creation,
   and another run is refused while a bootstrap unit is active. The client polls
   state and exit code over fresh key-only connections every five seconds.
   Follow logs on the Dell with `sudo journalctl -fu twinfra-bootstrap-<id>.service`
   (the actual unit name is printed). If the client disconnects, inspect that unit
   before rerunning; do not start a second bootstrap while it is running.
   The Dell also receives the same local API-name mapping as the
   NoCloud path; a conflicting existing hosts entry is refused. The same dev
   `stage_bootstrap_images` stages eleven bootstrap images
   before kubeadm. Exit 0 permits dev log caps, node labels and `complete.json`;
   any other failure stops those post-bootstrap steps and points to the journal.
   Exit 20 means the owner reboots the Dell and reruns this command;
   there is no automatic reboot. A healthy verified rerun performs no transfers,
   APT or configuration writes. Dev post-bootstrap caps are journald 500M and
   kubelet 10Mi per log / 3 files. [WO-31 Amendment 2](work-orders/WO-31-bare-metal-cairo-1.md)
   changes the shared bootstrap only for systemd 255 BPF filesystem compatibility:
   use the existing API mount (mount bpffs only when absent), remove only the
   exact legacy mount unit, and give containerd `RequiresMountsFor=/sys/fs/bpf`.
   A different legacy file or `.vcloud-original` backup stops BPF migration.

   **Failed first-run recovery:** after merge, update the operator checkout to
   protected `main` and rerun `host-bootstrap`. Leave the Dell's failed state
   untouched so the guarded migration runs against it. New inputs replace an
   old staging set only with a valid root-owned receipt and matching old bytes,
   no `complete.json`, no active bootstrap unit, and a result that is not `ready`.
   Completed/ready bootstraps with different inputs are refused; upgrades are
   outside this work order. Live acceptance remains Pending.

7. **Owner: retrieve kubeconfig into an operator-only directory outside Git.**

   ```powershell
   ssh -o BatchMode=yes -o StrictHostKeyChecking=yes twinfra-operator@192.168.1.3 'sudo cat /etc/kubernetes/admin.conf' > "$env:USERPROFILE/.kube/twinfra-dev-cairo-1.conf"
   $env:KUBECONFIG = "$env:USERPROFILE/.kube/twinfra-dev-cairo-1.conf"
   kubectl config rename-context kubernetes-admin@twinfra-dev-cairo-1 twinfra-dev-cairo-1
   kubectl --context twinfra-dev-cairo-1 get nodes
   ```

   Expected: explicit context; node `twinfra-dev-cairo-1` Ready, zone cairo-1a.
   Verify the existing context name before renaming; never print raw kubeconfig.

8. **Owner: application images.** Prepare verified OCI archives with the existing
   console builder and `tools/platform_pg_image.py` (see each tool's `--help`).

   ```powershell
   python tools/platform_dev.py stage-images --context twinfra-dev-cairo-1 --archive-dir .build/dev-images
   python tools/platform_dev.py stage-images --context twinfra-dev-cairo-1 --check
   ```

   Expected: ten application images, `problems: []`, canonical digest matches and
   CRI `pinned: true`. Archive names: `console.oci.tar`, `postgresql-pgvector.tar`.
   Both staging paths label `io.cri-containerd.pinned=pinned` alongside CRI-managed;
   a missing/false pin fails verification. Cached matching images are pinned
   without repulling; wrong digests are refused. These dev staging pulls are
   explicit, upstream-by-digest actions; kubelet retains mirror-only configuration
   (`MIRROR_REQUIRED=true`). Production refuses `IMAGE_STAGING=true`.

   [WO-31 Amendment 3](work-orders/WO-31-bare-metal-cairo-1.md) retains each
   `repository:tag@digest` name and adds `repository@digest` for CRI/kubelet
   lookup. Both records are managed and pinned; verification uses the digest-only
   name. Missing aliases for correct cached images are repaired without another
   pull/import or local archive. Tag-only names are unchanged; a digest mismatch
   on either record stops staging. `--check` only reads the cache and CRI.

   **Live acceptance (Pending):** after merge, update `main` and rerun
   `host-bootstrap` for the incomplete first run. Record the normalized CRI
   digest/pin checks and the Cilium event evidence:

   ```powershell
   kubectl --context twinfra-dev-cairo-1 -n kube-system get events
   ```

   No `Pulling` events for Cilium agent/operator/envoy images may appear in the
   acceptance interval; capture the interval and events before retention expires.

9. **Owner: dev CA and TLS.**

   ```powershell
   python tools/platform_dev_ca.py --out E:/Twinfra/secrets/dev-ca
   python tools/platform_dev_ca.py --out E:/Twinfra/secrets/dev-ca --apply --context twinfra-dev-cairo-1
   ```

   Expected: four TLS Secret names only. Private keys stay outside Git with
   owner-only ACLs and flow to kubectl through stdin. Existing Argo signing/admin
   fields are preserved. The root is name-constrained: the critical extension
   permits only `twinfra.example.com` and `twinfra-platform-services.svc.cluster.local`,
   without excluded subtrees. Trusting it in the browser cannot authenticate other
   websites. An old unconstrained CA requires deliberate owner replacement.
   This temporary PKI is replaced by WO-08; OpenBao is not initialized here.

10. **Owner: secrets, platform and Argo CD.**

    ```powershell
    python tools/platform_dev.py check
    python deploy/common/prepare-secrets.py --context twinfra-dev-cairo-1 --apply
    kubectl --context twinfra-dev-cairo-1 apply -k deploy/environments/dev/cairo-1/platform
    kubectl --context twinfra-dev-cairo-1 apply -k deploy/environments/dev/cairo-1/services
    kubectl --context twinfra-dev-cairo-1 apply -f deploy/environments/dev/cairo-1/root.yaml
    ```

    Expected: create-only credential Secrets; CNPG/PostgreSQL, identity/gateway/
    console services Ready; Argo reconciles protected `main`. Wait for CRDs and
    repeat apply if needed. Verify the finite LV is mounted before applying the
    platform; never create a plain root-filesystem PV directory instead.

    **Live firewall acceptance (Pending):** with the owned firewall confirmed
    and enabled, request a fresh GitHub fetch and wait for the automated sync:

    ```powershell
    kubectl --context twinfra-dev-cairo-1 -n twinfra-platform-services annotate application twinfra-root argocd.argoproj.io/refresh=hard --overwrite
    kubectl --context twinfra-dev-cairo-1 -n twinfra-platform-services get applications -o custom-columns=NAME:.metadata.name,REPO:.spec.source.repoURL,REVISION:.status.sync.revision,SYNC:.status.sync.status,HEALTH:.status.health.status
    ```

    Record a successful fetch of `https://github.com/amazen33/twinfra.git`, the
    actual synced revision and Synced/Healthy status in the acceptance receipt.
    Cached manifests alone do not pass this gate.

11. **Owner: loopback forwards, tunnels and browser checks.** On the Dell, in
    separate foreground sessions, run each forward:

    ```bash
    sudo kubectl --kubeconfig /etc/kubernetes/admin.conf -n twinfra-platform-services port-forward --address 127.0.0.1 svc/twinfra-gateway 18444:9443
    sudo kubectl --kubeconfig /etc/kubernetes/admin.conf -n twinfra-platform-services port-forward --address 127.0.0.1 svc/twinfra-keycloak 18443:443
    sudo kubectl --kubeconfig /etc/kubernetes/admin.conf -n twinfra-platform-services port-forward --address 127.0.0.1 svc/argocd-server 18081:443
    ```

    On the laptop keep this tunnel in its own terminal:

    ```powershell
    ssh -N -o BatchMode=yes -o StrictHostKeyChecking=yes -o ExitOnForwardFailure=yes -L 127.0.0.1:18444:127.0.0.1:18444 -L 127.0.0.1:18443:127.0.0.1:18443 -L 127.0.0.1:18081:127.0.0.1:18081 twinfra-operator@192.168.1.3
    ```

    Add these browser names to the laptop hosts file, then trust only the public
    dev `ca.crt` in the browser/OS trust store:

    ```text
    127.0.0.1 console.dev.cairo-1.twinfra.example.com auth.dev.cairo-1.twinfra.example.com gitops.dev.cairo-1.twinfra.example.com
    ```

    Expected: HTTPS console on 18444, Keycloak on 18443, Argo CD on 18081;
    `/console/callback` uses HTTPS. Test with a fresh browser session from
    [service access](service-access.md). Keep forwards/tunnel open; Ctrl-C stops
    each session. No admin service binds publicly on the LAN.

### Runtime pin evidence and render boundary

Module -1 installs Ubuntu's `containerd` package and supports 1.7+ / 2.x; it does
not lock an APT package version. Ubuntu noble currently advertises **2.2.1**
([package](https://packages.ubuntu.com/noble/containerd)). Its upstream
[image store](https://github.com/containerd/containerd/blob/v2.2.1/internal/cri/store/image/image.go)
reads the pin label and [ImageStatus](https://github.com/containerd/containerd/blob/v2.2.1/internal/cri/server/images/image_status.go)
exports the CRI pinned field. This is source-level verification, not a claim
about the Dell's installed runtime. Record `containerd --version` and real
`crictl inspecti` pin values in live acceptance; unsupported/unpinned results block.

The production bootstrap/env/render remain byte-identical in this PR: production
user-data does not embed the staging agent. Cairo-2's masked byte comparison
permits only its embedded shared agent plus dev log-cap entries/command.
Its original IP, CIDRs, names, versions and all remaining bytes are retained.
No licence expiry or historical baseline is changed. nftables is Ubuntu base-os
under ADR-0044; no new third-party tool or Python library is introduced.

## Part 2: `cairo-2` cold standby on Hyper-V

The existing Hyper-V procedure is now only for `cairo-2`. Defaults: 8 vCPU,
20 GiB static RAM, 100 GiB dynamic VHDX; 24 GiB free RAM and 110 GiB free E: disk.
WO-30's proposed 20 GiB VM disk sizing is separate and has **not** been implemented.
The [Hyper-V runbook](../deploy/hyperv/README.md) retains the approved checksum,
network overlap, ownership, no-adoption and PowerShell 7.4 guards. Cairo-1 is
refused before host inventory reads with the ADR-0048 message.

1. **Owner on the laptop:** verify Hyper-V and capacity, review the real plan:

   ```powershell
   pwsh -NoProfile -File deploy/hyperv/New-TwinfraDev.ps1 -Plan
   ```

   Expected: cairo-2, 10.50.0.11, Pods 10.120.0.0/16, Services 10.121.0.0/16;
   no files/downloads/VM/network changes. Fixture output is not host inventory.
   Close apps or stop guests yourself if RAM is short; never change WSL or pCloud
   merely to run a plan. The Dell can remain running on its separate hardware.

2. **Owner:** supply the public key, provision and explicitly start:

   ```powershell
   pwsh -NoProfile -File deploy/hyperv/New-TwinfraDev.ps1 -SshPublicKeyFile C:/operator/id_ed25519.pub
   Start-VM -Name twinfra-dev-cairo-2
   ```

   Expected: verified Canonical Ubuntu build 20260926 (625612288 bytes, SHA256
   `6a81c37564db9b1ee84e141922625e1d7c5b389b99bb3c572e0243607d5bb4d2`),
   Generation 2 VM created Off, then Running only on owner start. No automatic
   stop of apps/guests or alteration of foreign networks. Existing owned network
   is reused only with its exact Internal switch/NAT/gateway tuple.

3. **Owner:** verify the VM host key at its console, map
   `api.dev.cairo-2.twinfra.example.com` to 10.50.0.11, then check seed bootstrap:

   ```powershell
   ssh -o BatchMode=yes -o StrictHostKeyChecking=yes twinfra-operator@10.50.0.11 'sudo cloud-init status --wait --long'
   ssh -o BatchMode=yes -o StrictHostKeyChecking=yes twinfra-operator@10.50.0.11 'sudo cat /var/lib/vcloud-host/result.json'
   ```

   Expected: staged-verified, correct cairo-2 endpoint and CIDRs, dev log caps.
   Exit 20 requires owner reboot and the existing bootstrap service retry.
   This is only the cold-standby provisioning path. WO-23 supplies actual recovery,
   cairo-2 application configuration and measured RPO/RTO; WO-24 awaits another
   physical host for warm standby. Keep cold drills cold: stop the Dell before
   restoring, even though the regions can run on separate machines.

## Static checks and acceptance

```bash
python3 -m unittest discover -s tests -p test_bare_metal.py -v
python3 -m unittest discover -s tests -p test_dev_environment.py -v
python3 -m unittest discover -s tests -p test_dev_runnable.py -v
pwsh -NoProfile -File deploy/hyperv/test-plan.ps1
python3 tools/platform_dev.py check
python3 tools/platform_bootstrap_inventory.py --bash bash --helm helm
python3 tools/platform_validate.py --schemas .build/ci-tools/schemas
```

Only fixture code is executed. Live Dell ePSA Thorough memory diagnostics, the
24-hour soak, kernel machine-check/hung-task log review, LAN port tests, Cilium
under integrity lockdown, finite mount, image pins, API/browser acceptance and
etcd WAL fsync p99 (<10 ms target, report even a miss) remain
[Pending](acceptance/dev-environment-2026-10-12.md). Only the tester signs acceptance.
WSL material remains until WO-28; no WSL, laptop, Dell or GitHub-settings changes
were performed by this work order.
