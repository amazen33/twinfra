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

## Network boundary

[WO-31 Amendment 10](work-orders/WO-31-bare-metal-cairo-1.md) records the
owner's read-only exposure check at main `9c33d0c`. The rendered overlay had no
NodePort/LoadBalancer Service, external IP, host-network or host-port workload;
CRD schema text is not a deployed workload. Live Services were ClusterIP.
The Cilium check reported:

| Setting | Observed value |
| --- | --- |
| `kube-proxy-replacement` | `true` |
| `enable-host-firewall` | `false` |
| `routing-mode` | `native` |
| `enable-bpf-masquerade` | `true` |
| `bpf-lb-external-clusterip` | `false` |

The `inet twinfra_host` nftables table protects **host-bound ports only**.
Cilium's tc programs on `eno1` can handle node-exposed or pod-bound traffic
**before netfilter**. The table cannot enforce the pod boundary against
NodePort, LoadBalancer, hostPort or a LAN client with a route to the pod CIDR.
The existing prerouting rule is additional filtering, not proof of pod isolation.

The CI contract in [platform_network_boundary.py](../tools/platform_network_boundary.py)
therefore rejects NodePort/LoadBalancer Services, nonempty `externalIPs`,
explicit `nodePort`, `hostNetwork: true` and any `hostPort` in Twinfra namespaces.
The only named node exceptions are `kube-system` DaemonSets `cilium` and
`cilium-envoy`, and Deployment `cilium-operator`; their pinned-source identity
and approved node projection are also checked. Each Twinfra namespace requires
a namespace-wide ingress default-deny NetworkPolicy. Separate explicit Cilium
allows admit the gateway, Argo CD, CNPG, DNS and control-plane edges. The check
includes all three SSoT dev namespaces and the shared bootstrap foundation.

Cilium host firewall (`enable-host-firewall`) with a host-scoped
`CiliumClusterwideNetworkPolicy` is a **later hardening step**, requiring its own
review and acceptance. This change enables neither. Narrowing host TCP 6443
from `192.168.1.0/24` to the laptop's reserved address is an optional owner
decision; the current LAN rule stays unchanged, and API access requires client
certificates. Owner-reported LAN checks and GitHub egress are recorded in the
[Pending acceptance receipt](acceptance/dev-environment-2026-10-13.md).

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
   One prerouting rule, after conntrack and before DNAT, matches **new** traffic
   from `eno1` addressed to the SSoT dev pod/service CIDRs (`10.110.0.0/16`,
   `10.111.0.0/16`). Cilium's earlier tc processing can bypass this rule; the
   Network boundary contract above supplies pod isolation. The owner reported
   Argo CD fetching GitHub through the confirmed firewall in the dated receipt.
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

8. **Owner: application images.** Build the frontend explicitly, then assemble
   both digest-verified OCI archives on Windows or Linux without WSL or a
   container runtime. `--download-inputs` opts into public, pinned registry
   exports and hash-locked Linux amd64 CPython 3.14 wheel downloads; it installs
   nothing. With cached inputs, omit the flag for an offline build.

   ```powershell
   cd console
   npm ci
   npm test
   npm run build
   cd ..
   python tools/platform_dev.py build-images --download-inputs
   python tools/platform_dev.py stage-images --context twinfra-dev-cairo-1 --archive-dir .build/dev-images
   python tools/platform_dev.py stage-images --context twinfra-dev-cairo-1 --check
   ```

   Expected build: `status: passed`, `repositoryWrites: false`, `runtimeImport: false`.
   Expected digests come from this checkout's lock, never from a copied receipt:

   ```powershell
   python -c "import json; from pathlib import Path; images=json.loads(Path('deploy/common/images.lock.json').read_text())['images']; print('\n'.join(name+': '+images[name]['canonical'] for name in ('console','postgresql')))"
   ```

   Any digest, wheel hash or source mismatch stops the build; the command never
   updates repository locks or receipts. The rebuilt image title is
   `twinfra-console`. Cache directories are `.build/console/` and
   `.build/dev-images/inputs/`; outputs are `.build/dev-images/`.

   **Before merging an image-changing PR:** stage from its branch, run the
   readonly `stage-images --check` above, then add the exact line
   `Staging: PASS (stage-images --check, YYYY-MM-DD)` to the PR body using the
   actual UTC date. Extra staged images do not change running workloads. The
   lightweight `staging-check` fails on changed common locks or rendered dev
   image references until that owner attestation exists. It never stages images
   or treats an attestation as automated live evidence.

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

   **Live acceptance (Pending):** Amendment 9 records owner-reported bootstrap
   completion at main `3b6ec82`. After merge, update `E:\twinfra-live`, build and
   stage the two archives above. Record the normalized CRI digest/pin checks and
   the Cilium event evidence:

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
    kubectl --context twinfra-dev-cairo-1 apply --server-side --force-conflicts -k deploy/environments/dev/cairo-1/platform
    kubectl --context twinfra-dev-cairo-1 apply --server-side --force-conflicts -k deploy/environments/dev/cairo-1/services
    kubectl --context twinfra-dev-cairo-1 apply -f deploy/environments/dev/cairo-1/root.yaml
    ```

    Expected: create-only credential Secrets; CNPG/PostgreSQL, identity/gateway/
    console services Ready; Argo reconciles protected `main`. Server-side apply
    avoids the 262144-byte last-applied annotation limit on large CRDs. The first
    run can report `no matches for kind Cluster/Database` before the CRDs are
    established; wait for establishment, then repeat the **same commands**.
    Verify the finite LV is mounted before applying the
    platform; never create a plain root-filesystem PV directory instead.

    **CNPG initdb recovery after WO-31 Amendments 13–13b (owner, after merge).**
    Wait for Argo CD to sync the corrected operator Deployment, then verify its
    rollout and `OPERATOR_IMAGE_NAME`. The generator preserves the vendor's
    `1.30.1` tag and pins the staged canonical operator repository/digest, so
    the init container resolves to the existing CRI image without re-staging.

    ```powershell
    kubectl --context twinfra-dev-cairo-1 -n twinfra-platform-services rollout status deployment/cnpg-controller-manager --timeout=180s
    kubectl --context twinfra-dev-cairo-1 -n twinfra-platform-services get deployment cnpg-controller-manager -o jsonpath='{.spec.template.spec.containers[0].env[?(@.name=="OPERATOR_IMAGE_NAME")].value}'
    kubectl --context twinfra-dev-cairo-1 -n twinfra-platform-services delete job -l cnpg.io/cluster=twinfra-postgres,cnpg.io/jobRole=initdb
    kubectl --context twinfra-dev-cairo-1 -n twinfra-platform-services get clusters.postgresql.cnpg.io,pods,applications
    ```

    Delete only the stuck initdb Job for this empty dev bootstrap, after the
    fixed operator is available. Keep the Cluster, PVC and PV. CNPG recreates
    the Job with the corrected bootstrap-controller image. Expected: the
    primary `twinfra-postgres-1` is Running, the Cluster is healthy, Keycloak and
    OpenBao are Running, and all applications are Synced and Healthy. Record
    this live acceptance with tester sign-off **Pending**; no recovery action
    is run by the static CI guard.

    **Live firewall acceptance (Pending):** with the owned firewall confirmed
    and enabled, request a fresh GitHub fetch and wait for the automated sync:

    ```powershell
    kubectl --context twinfra-dev-cairo-1 -n twinfra-platform-services annotate application twinfra-root argocd.argoproj.io/refresh=hard --overwrite
    kubectl --context twinfra-dev-cairo-1 -n twinfra-platform-services get applications -o custom-columns=NAME:.metadata.name,REPO:.spec.source.repoURL,REVISION:.status.sync.revision,SYNC:.status.sync.status,HEALTH:.status.health.status
    ```

    Record a successful fetch of `https://github.com/amazen33/twinfra.git`, the
    actual synced revision and Synced/Healthy status in the acceptance receipt.
    Cached manifests alone do not pass this gate.

    **Dev reconciliation after Amendment 14:** all three generated Applications
    keep `ServerSideApply=true` and set
    `argocd.argoproj.io/compare-options: ServerSideDiff=true,IncludeMutationWebhook=true`.
    The shared Application factory applies both options to `twinfra-root`,
    `twinfra-platform` and `twinfra-services` for both dev regions. Cairo-2 remains
    a cold seed; its workload deployment/recovery belongs to WO-23. Do not rely
    on the global controller setting alone: mutation-webhook comparison is a
    per-Application option. Server-side dry-run comparison includes CNPG webhook
    defaults without hiding actual drift with `ignoreDifferences`.
    **Server-Side Diff is not performed on initial creation**; it compares
    resources after they exist. See the pinned
    [Argo CD v3.5.3 diff documentation](https://github.com/argoproj/argo-cd/blob/v3.5.3/docs/user-guide/diff-strategies.md).
    The dev runtime generator omits the unsupported OpenBao
    `disable_mlock` field. After the amended profile syncs, record
    `twinfra-platform` **Synced/Healthy** and absence of that warning in OpenBao
    logs. The existing Healthy/OutOfSync observation remains in the receipt.

    For an existing installation, apply the updated `root.yaml` with the step
    10 command so the root Application also gets both comparison options;
    Argo CD reconciles the child Applications. Once the services ConfigMap is
    synced, the owner restarts only OpenBao to regenerate its tmpfs HCL through
    the init container. Updating a ConfigMap does not re-run that init container:

    ```powershell
    kubectl --context twinfra-dev-cairo-1 -n twinfra-platform-services rollout restart deployment/twinfra-openbao
    kubectl --context twinfra-dev-cairo-1 -n twinfra-platform-services rollout status deployment/twinfra-openbao --timeout=180s
    ```

    This is an owner action after merge, not a CI action. It performs no
    initialization or unseal ceremony; those remain under WO-08.

11. **Owner: laptop loopback forwards and browser checks.** The primary method
    runs kubectl **on the laptop** through the API on 6443. Keep each forward in
    its own foreground PowerShell terminal:

    ```powershell
    kubectl --context twinfra-dev-cairo-1 -n twinfra-platform-services port-forward --address 127.0.0.1 svc/twinfra-gateway 18444:9443
    kubectl --context twinfra-dev-cairo-1 -n twinfra-platform-services port-forward --address 127.0.0.1 svc/twinfra-keycloak 18443:443
    kubectl --context twinfra-dev-cairo-1 -n twinfra-platform-services port-forward --address 127.0.0.1 svc/argocd-server 18081:443
    ```

    Add these browser names to the laptop hosts file, then trust only the public
    dev `ca.crt` in the browser/OS trust store:

    ```text
    127.0.0.1 console.dev.cairo-1.twinfra.example.com auth.dev.cairo-1.twinfra.example.com gitops.dev.cairo-1.twinfra.example.com
    ```

    Expected: trusted HTTPS console on 18444, Keycloak on 18443, Argo CD on 18081;
    `/console/callback` uses HTTPS. Start a fresh browser session at
    <https://console.dev.cairo-1.twinfra.example.com:18444/console/>. Keep the
    forwards open; Ctrl-C stops each session. Every local listener binds only
    to `127.0.0.1`, and no admin service is exposed on the LAN.

    **Sign-in (owner only):** copy the Keycloak bootstrap admin password directly
    from its Secret to the clipboard. The username is `twinfra-admin`; open
    <https://auth.dev.cairo-1.twinfra.example.com:18443/admin/master/console/>.
    The command prints no password and writes no credential file:

    ```powershell
    kubectl --context twinfra-dev-cairo-1 -n twinfra-platform-services get secret twinfra-keycloak-admin -o jsonpath='{.data.password}' |
      ForEach-Object { [System.Text.Encoding]::UTF8.GetString([System.Convert]::FromBase64String($_)) } |
      Set-Clipboard
    ```

    Copy Argo CD's initial admin password to the clipboard immediately before
    opening <https://gitops.dev.cairo-1.twinfra.example.com:18081/> as `admin`:

    ```powershell
    kubectl --context twinfra-dev-cairo-1 -n twinfra-platform-services get secret argocd-initial-admin-secret -o jsonpath='{.data.password}' |
      ForEach-Object { [System.Text.Encoding]::UTF8.GetString([System.Convert]::FromBase64String($_)) } |
      Set-Clipboard
    ```

    Initial credentials apply only until rotated; use the owner's existing
    credential after rotation. `argocd-secret` contains a password hash, not the
    cleartext login password. Do not print credentials or place them in shell
    transcripts, screenshots, Git or evidence. Clear the clipboard when finished
    with `Set-Clipboard -Value ''`.

    **First console user:** the realm import has no users. In Keycloak's admin
    console select realm `twinfra`, add the owner's dedicated console username,
    enable it and set a temporary password using the owner's password manager.
    In that user's Role mapping, filter client roles and assign
    `twinfra-console` / `console.admin`. This is a console role, not master-realm
    administration. Leave the configured TOTP enrollment action enabled and
    complete password change and TOTP enrollment from a fresh console sign-in.
    Keep passwords and OTP seeds out of Git, logs and receipts.

    **Alternative:** retain the Dell-side loopback forwards plus an SSH tunnel.
    Use this instead of the laptop forwards, so the same laptop ports are free.
    On the Dell, in separate foreground sessions:

    ```bash
    sudo kubectl --kubeconfig /etc/kubernetes/admin.conf -n twinfra-platform-services port-forward --address 127.0.0.1 svc/twinfra-gateway 18444:9443
    sudo kubectl --kubeconfig /etc/kubernetes/admin.conf -n twinfra-platform-services port-forward --address 127.0.0.1 svc/twinfra-keycloak 18443:443
    sudo kubectl --kubeconfig /etc/kubernetes/admin.conf -n twinfra-platform-services port-forward --address 127.0.0.1 svc/argocd-server 18081:443
    ```

    On the laptop keep this tunnel in its own terminal:

    ```powershell
    ssh -N -o BatchMode=yes -o StrictHostKeyChecking=yes -o ExitOnForwardFailure=yes -L 127.0.0.1:18444:127.0.0.1:18444 -L 127.0.0.1:18443:127.0.0.1:18443 -L 127.0.0.1:18081:127.0.0.1:18081 twinfra-operator@192.168.1.3
    ```

    Use the same browser authorities and name-constrained CA trust above.
    Keep the forwards/tunnel open; Ctrl-C stops each session. See
    [service access](service-access.md) for the configured UI paths.

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

### Module -1 CLI validation review

WO-31 Amendment 5 replaces only `tkn version --client` with
`tkn version --component client`. The v0.46.1 published-digest-verified binary's
help lists `--component`, and client output is `0.46.1`. The nine unconditional
calls (`kubectl`, `kubeadm`, `helm`, `cilium`, `kubeconform`, `tkn`, `argocd`, `yq`,
`jq`) are executed against the pinned binaries in the required CI step, with
their actual help captured. No cluster credentials are used by these calls.

Amendment 6 runs every CLI help/version call under `env -i` with only the pinned
binary directories and `/usr/bin:/bin` in PATH. HOME is absent at entry; the
shared script's `load_config` defaults and exports it as `/root`. This matches
the transient systemd unit instead of inheriting the CI runner's HOME. Help and
version calls use `sudo -n` on the disposable runner, matching the root host
process; no provisioner entry point or CLI configuration changes run. Existing
nonempty HOME values are preserved; no CLI configuration is modified.

Conditional calls were reviewed without changing the approved provisioning:

| Existing call | Review source / execution boundary |
| --- | --- |
| `mpirun --version` | [Open MPI 4.1 manual](https://www.open-mpi.org/doc/v4.1/man1/mpirun.1.php); version output exits without launching an MPI job |
| `ucx_info -v` | [UCX 1.16 help source](https://github.com/openucx/ucx/blob/v1.16.0/src/tools/info/ucx_info.c); version flag |
| `apptainer --version` | [Apptainer 1.4 help](https://apptainer.org/docs/user/1.4/quick_start.html); global version flag |
| `srun --version` | [Slurm manual](https://slurm.schedmd.com/srun.html); prints version and exits |
| `nvidia-ctk --version` | [Pinned toolkit v1.20.1 CLI source](https://github.com/NVIDIA/nvidia-container-toolkit/blob/v1.20.1/cmd/nvidia-ctk/main.go); CLI version output |
| `nvidia-smi` and driver query | [NVIDIA CLI reference](https://docs.nvidia.com/deploy/nvidia-smi/index.html); default summary and `--query-gpu=driver_version --format=csv,noheader` require a loaded NVIDIA driver/GPU |

The HPC packages come from Ubuntu/APT and the existing Apptainer PPA without
exact package-version pins; the driver is the approved auto-selection with a
550+ floor. These are source/help reviews, not claims of matching pinned
HPC/driver binaries or hardware acceptance. `INSTALL_HPC=false` and GPU disabled
remain the dev profile. CI installs only the pinned host CLI suite; it does not
install optional HPC packages, drivers or enable GPU/HPC workloads.

### Resume after a validation failure (owner, after merge)

`host-check` now has `pre-bootstrap`, `resume`, and `post-bootstrap` modes.
`resume` requires a non-ready result, owned `admin.conf`, the exact kubeadm
cluster name/API endpoint, node name/InternalIP and kube-apiserver/etcd/kubelet
listener owners. Wrong identities or occupied ports without `admin.conf` block.
It reports `PASS (bootstrap-owned cluster, incomplete)`; it is not completed
bootstrap acceptance. Amendment 2's input replacement rules remain unchanged.

From merged `main`, the owner runs `host-check`, then `host-bootstrap`, then
`host-check` again. Expected modes are `resume`, followed by a bootstrap result
`ready`, then `post-bootstrap`. Module -1's unchanged existing-cluster branch
skips `kubeadm init`; fake tests make any init/reset call fail and verify static
Pod, PKI and admin.conf bytes remain unchanged. Dev log caps, labels and
`complete.json` follow successful validation. No automatic reset is added.

Amendment 6 fixes the owner-reported Argo CD `$HOME is not defined` failure on
merged main `cf4b659`. A trapped command failure now records `failed` and exits
1, retaining its original code in the journal. Exit 20 is reserved for the
deliberate reboot path. The host agent also requires an owned result with
`status: reboot-required` before interpreting unit exit 20 as a reboot request;
missing, invalid, unowned or non-reboot results report failure with journal
guidance. Offline tests cover both failure and deliberate reboot paths.

For this validation failure, **do not reboot**. After review and merge, from
the owner's `E:\twinfra-live` checkout of updated main, run `host-check`
(expect `resume`), `host-bootstrap` (expect `passed`), then `host-check`
(expect `post-bootstrap` / `passed`). Live acceptance remains Pending.

WO-31 Amendment 7 fixes the subsequent checker failure reported on merged main
`1f7d86f`: a direct `kubectl get ... -o json` returns one `kind: List` object.
The generated checker's `main()` now wraps a single object, preserves existing
arrays, and reports non-object entries (including nested List items) as violations
with exit 1. `flatten()`, policy decisions and the kubectl/yq callers are unchanged.
Tests run the generated CLI against actual pinned Cilium chart output with the
dev node-exception policy; single DaemonSet, array and kubectl List inputs pass,
while an unapproved mount still fails. Production renders may change only in
the generated checker block and derived checksums/gzip.

After review and merge, update the owner's `E:\twinfra-live` checkout and run
`host-bootstrap`, then `host-check`. Expected: bootstrap `passed`, dev log caps
(one kubelet restart), labels and `complete.json`, then `post-bootstrap` / `passed`.
Record the result in the [2026-10-13 Pending receipt](acceptance/dev-environment-2026-10-13.md).

Amendment 8 fixes the next owner-reported failure on main `24b8bdb`: validation
passed, but a disabled smoke step returned the failed guard's status under
`set -Eeuo pipefail` and the ERR trap. Kubernetes/smoke skip guards now explicitly
return 0. The audit also makes the CLI-cache and GPU skips explicitly successful;
staging completion and main dispatch preserve their previous status with
`return $?`. All seven audited lines are listed in the PR. Policy-error returns
remain explicit and unchanged. Tests execute the real main tail with smoke
off/on, bootstrap off, and a real mocked smoke failure; only successful/skipped
steps may reach `write_result ready`. A static test bans status-less returns.

After review and merge, `git pull` in `E:\twinfra-live` must show the shared
bootstrap script changed. Run `host-bootstrap` (expect `passed`), then
`host-check` (expect `post-bootstrap` / `passed`). Live acceptance remains Pending.

WO-31 Amendment 4 makes the shared etcd strategic patch use Kubernetes' `mountPath`
merge key from the rendered kubeadm `certificatesDir` (default
`/etc/kubernetes/pki/etcd`). The preview rejects a missing, duplicated, writable
or misplaced certificate mount before `kubeadm init` can proceed. CI also runs
the real, checksum-verified v1.36.5 control-plane and local-etcd dry-run phases
for dev and production; this is manifest validation, not host acceptance.
After review/merge, the owner pulls `main` and repeats `host-bootstrap` under
Amendment 2's incomplete-run guard. Amendment 4 reports that the previous preview
failed before PKI, static Pods or etcd data existed; do not reset the node.

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

## WO-36: Dell address plan and safe network changes

The owner-approved `siteNetwork` section of `vcloud-ssot.yaml` records:

| Address | Use |
| --- | --- |
| 192.168.1.1 | Router, gateway and primary DNS |
| 192.168.1.2–192.168.1.99 | Fixed range, excluded from DHCP after the static change |
| 192.168.1.3/24 | `twinfra-dev-cairo-1`, `eno1`, MAC `64:00:6a:86:5c:4f` |
| 192.168.1.10 | Future WO-33 control-plane VIP, not assigned by WO-36 |
| 192.168.1.11–192.168.1.13 | Future nodes, not assigned by WO-36 |
| 192.168.1.100–192.168.1.254 | Router DHCP pool after owner changes it |

DNS order is `192.168.1.1`, then `1.1.1.1`. CGNAT provides no inbound internet
path; UIs remain accessible through trusted HTTPS over laptop tunnels.

**Owner only, after merge; live acceptance Pending:**

```powershell
python tools/platform_dev.py host-network --context twinfra-dev-cairo-1 --check
python tools/platform_dev.py host-network --context twinfra-dev-cairo-1 --apply
python tools/platform_dev.py host-network --context twinfra-dev-cairo-1 --check
python tools/platform_dev.py host-check --context twinfra-dev-cairo-1
```

An initial `--check` may fail because the address is still dynamic. All commands
require the same exact ready cluster identity, node IP/listeners, Secure Boot and
kernel lockdown `[integrity]` checks as WO-31. The NIC MAC must also match.
`--check` reads only. A successful JSON report has this shape (illustrative,
not live evidence):

```json
{"status":"passed","mode":"static-check","network":{"address":"192.168.1.3","present":true,"static":true,"prefixLength":24,"mac":"64:00:6a:86:5c:4f","gateways":["192.168.1.1"],"dns":["192.168.1.1","1.1.1.1"],"nodeInternalIP":["192.168.1.3"]},"integrity":{"status":"PASS","detail":"Owned network files verified (apply)"}}
```

The owned netplan also sets `ignore-carrier: true`: Netplan emits
`ConfigureWithoutCarrier=yes`, which makes systemd 255 retain configuration on
carrier loss. A static lease replacement alone does not establish that behavior.
See the [Netplan networkd generator](https://github.com/canonical/netplan/blob/1.0/src/networkd.c)
and [systemd 255 network contract](https://github.com/systemd/systemd/blob/v255/man/systemd.network.xml).

The root-owned transaction lives under `/var/lib/twinfra/host-network/`. It saves
an exact mode-preserving snapshot and a copy of `50-cloud-init.yaml`, writes
`/etc/netplan/60-twinfra-static.yaml` and
`/etc/cloud/cloud.cfg.d/99-twinfra-disable-network-config.cfg`, then removes the
old cloud-init netplan from the active directory. Existing unowned destinations,
modified owned files or a concurrent transaction are refused. A detached
`twinfra-network-<id>` systemd unit survives an SSH disconnect. Its worker invokes
`netplan try --timeout 120`, keeping stdin open. Only after a new key-only SSH
login, matching effective static address/route/DNS/InternalIP, and TLS-verified
`https://192.168.1.3:6443/readyz` (`kubectl` using the existing trusted admin
kubeconfig) does it confirm. It requires netplan's explicit acceptance message,
its exit code and post-checks; exit zero alone can mean rollback.

If verification/login fails or the controller disappears, netplan's timeout
restores runtime and the detached worker restores the original on-disk files.
Inspect `journalctl -u twinfra-network-<id>` and the JSON result. An unexpectedly
killed worker or a failure after acceptance is reported as failure requiring
local inspection; never reboot into an unverified on-disk configuration. The
implementation follows the [netplan try confirmation and rollback contract](https://github.com/canonical/netplan/blob/1.0/netplan_cli/cli/commands/try_command.py).
It never re-initializes/resets Kubernetes or rotates certificates.

Rollback uses the same detached try/fresh-login/TLS confirmation sequence:

```powershell
python tools/platform_dev.py host-network --context twinfra-dev-cairo-1 --rollback
```

It restores the saved DHCP configuration. It must retain `.3` and the saved
route/DNS to confirm; after changing the DHCP pool, arrange the optional `.3`
reservation before attempting rollback, or the attempt will safely time out.
A failed rollback restores the preceding static files. `--check` is a static
configuration check, so it intentionally fails after a successful DHCP rollback.

Only after static `--check` passes, the owner sets the router pool start `.100`,
end `.254`. Optional reservation: `64:00:6a:86:5c:4f` to `.3`. The laptop (formerly
at `.9`) renews into that pool; nothing depends on its address. A router/Dell UPS
is optional. The optional owner test disconnects router power for 60 seconds and
records unchanged `.3`/node InternalIP and no control-plane restarts.

Host-check adds owned-network-file integrity to the existing kernel lockdown
check. Unconfigured static ownership warns; tampering blocks. Since-boot `eno1`
carrier/DHCP lease losses warn, as do retained CRI control-plane restart attempts.
Restart counts are a lower bound because CRI garbage collection removes history;
unavailable journal/CRI history warns rather than hiding an observation gap.
The Prometheus link-loss alert remains a WO-10 follow-up.

### Dev update strategies

| Workload | Strategy | Reason |
| --- | --- | --- |
| twinfra-console | RollingUpdate, unavailable 0 / surge 1 | Stateless backend |
| twinfra-gateway | RollingUpdate, unavailable 0 / surge 1 | Stateless APISIX, shared OIDC configuration |
| twinfra-ministack | RollingUpdate, unavailable 0 / surge 1 | Disposable local API validation; no durable data |
| twinfra-keycloak | Recreate | Current `cache=local` does not share authentication sessions; clustered cache is WO-33 / ADR-0050 |
| twinfra-openbao | Recreate | Single active process with PostgreSQL storage, no HA coordination; Raft is WO-08 |

The generator uses `deploy/common/dev-update-strategies.json` for the two
Recreate reasons; tests reject an undocumented Recreate or unsafe stateless
rolling parameters. Upstream controller strategies and StatefulSets are unchanged.
An unstaged new image leaves the old stateless pod Ready; resource pressure may
leave the new pod Pending and the rollout incomplete. Staging remains mandatory
for all image changes, including the two single-process services.
