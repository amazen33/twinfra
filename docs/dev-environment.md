# Twinfra dev environment · cairo-1

[WO-29 and Amendment 1](work-orders/WO-29-make-dev-environment-runnable.md)
make the static WO-21 profile runnable without an existing registry or PKI.
Provisioning and browser acceptance remain **Pending** in
[the receipt](acceptance/dev-environment-2026-10-10.md). Codex has not run the
provisioner, installed software, created VMs or changed the live environment.
Read [WO-21](work-orders/WO-21-twinfra-dev-environment.md),
[ADR-0047](adr/0047-upstream-owned-resource-names.md) and the
[identifier inventory](dev-identifier-inventory.md) before owner execution.

## Capacity and download verification

One Generation 2 VM: `twinfra-dev-cairo-1`, **8 vCPU, 20 GiB static RAM**, 100 GiB
dynamic VHDX under `E:\Twinfra`, nested virtualization enabled, left Off after
provisioning. Guards require **24 GiB free RAM and 110 GiB free E: disk**.
The 10 GiB reserve covers conversion/cache/seed overhead. Only the script-owned
`canonical-base.vhd` is removed after successful `Convert-VHD`. A corrupt cached
image is never automatically deleted: inspect it, then follow the reported
`delete <path> and rerun` instruction yourself.

The [Canonical Ubuntu 24.04 image](https://cloud-images.ubuntu.com/noble/20260926/noble-server-cloudimg-amd64.img)
lock specifies build `20260926`, `noble-server-cloudimg-amd64.img`, 625612288 bytes,
SHA256 `6a81c37564db9b1ee84e141922625e1d7c5b389b99bb3c572e0243607d5bb4d2`.
Both the download and [published SHA256SUMS](https://cloud-images.ubuntu.com/noble/20260926/SHA256SUMS)
must match. Signed-checksum trust-key verification remains deferred. The generic
QCOW2 converter rejects unsupported features, backing files, encryption and bounds
violations before VM/network creation. Synthetic tests do not establish boot success.

Planning allowances total **20 GiB**, not measured utilization:

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
| Remaining VM headroom | **4.25 GiB** |

Compared with the 24 GiB plan, allowances shrink for the control plane (3→2.5),
Cilium (2→1.5), Argo (2→1.5), database (3→2.5), Keycloak (3→2.25) and MiniStack
(1→0.75); headroom shrinks from 5.25 to 4.25 GiB. Existing workload requests,
limits and replicas remain approved; measure actual use during acceptance.
No LocalStack, Grafana, Knative, GPU/vLLM or HPC modules are installed.
OpenBao stays sealed/uninitialized until WO-08.

## Two image inventories

Cloud-init embeds [bootstrap-images.lock.json](../deploy/common/bootstrap-images.lock.json)
at `/etc/twinfra/bootstrap-images.lock.json`. After containerd starts, dev-only
`IMAGE_STAGING=true` replaces the mirror probe and `crictl pull`. Staging uses
upstream digest references, linux/amd64 and an explicit empty `ctr --hosts-dir`;
it verifies targets, tags canonical names, marks them CRI-managed and verifies
all images with `crictl inspecti`. Status becomes `mirror_status: staged-verified`.
Missing/mismatched images stop bootstrap; reruns skip verified cached images.

The eleven bootstrap images are Kubernetes v1.36.5 API server/controller/scheduler,
etcd 3.6.8-0, CoreDNS v1.14.2, pause 3.10.1 and 3.10.2, Cilium v1.20.2, its operator
and locked Envoy, and busybox 1.37.0. Both pause tags are required: containerd's
approved sandbox uses 3.10.1; pinned kubeadm constants use 3.10.2. A custom kubeadm
repository flattens CoreDNS to `.../registry.k8s.io/coredns`. Dev disables kube-proxy
preparation as well as its install phase. Smoke flags are false, so no disabled
smoke images are staged. CI renders kubeadm/Cilium/containerd/smoke settings,
uses verified pinned kubeadm constants and compares both regions against the lock.

The later SSH command reads [images.lock.json](../deploy/common/images.lock.json):

| Method | Images |
| --- | --- |
| Verified upstream digest pull and canonical tag (8) | Argo CD, Valkey, CNPG operator, Keycloak, OpenBao, MiniStack, APISIX, Python |
| Verified local OCI import and canonical tag (2) | Twinfra console; PostgreSQL 18.6 with pgvector 0.8.2 |

The locks provide authoritative versions and digests. `--check` lists all missing
or mismatched canonical/CRI entries, exits nonzero if incomplete and changes
nothing. Normal staging refuses mismatches and validates local OCI graphs before
pulling. No `twinfra-registry-cred` is required. Canonical registry names are cache
aliases; workloads use `IfNotPresent`. `MIRROR_REQUIRED=true` stays mandatory:
CRI has no upstream fallback, including when a cache entry is absent. Staging
requires internet access and does not satisfy cold-cache offline acceptance.

Production rejects staging; default `IMAGE_STAGING=false`, mirror preflight,
profile values and nine saved rendered outputs remain unchanged. Generated
production user-data changes only because it embeds the guarded shared script.
Frozen node policy/inventory files stay unchanged. The dev validator remaps only
the canonical registry prefix in memory, retaining pins, mounts and security rules.

## Numbered owner procedure

Every command below is an **owner action**, after review/merge. Windows commands
run from `E:\vCloud` in PowerShell 7.4+. Use the registered Python, cryptography,
PyYAML, kubectl and OpenSSH tools. No step deletes WSL material, changes mirrored
networking, touches pCloud or modifies `iotee-nat`.

1. **Owner host action — PowerShell 7.** If `pwsh` is missing:

   ```powershell
   winget install --id Microsoft.PowerShell --source winget
   pwsh -NoProfile
   ```

   Expected: PowerShell 7.4+; `#Requires -Version 7.4` rejects 5.1. Provisioning
   also needs Administrator/Hyper-V tools; enable Hyper-V/reboot yourself if missing.

2. **Owner host action — stop WSL after coordination.** First stop Twinfra workloads
   and coordinate with pCloud/IOT-EE controllers sharing the distro:

   ```powershell
   wsl --shutdown
   ```

   Expected: WSL stopped, nothing unregistered. Do not run this VM concurrently
   with the 20 GiB WSL workload. Close browsers/apps and other guests yourself
   if less than 24 GiB RAM is free.

3. **Owner read-only action — review a real plan.**

   ```powershell
   .\deploy\hyperv\New-TwinfraDev.ps1 -Plan
   ```

   Expected: PLAN ONLY, 20 GiB RAM/100 GiB disk, measured free resources, required
   24 GiB RAM/110 GiB disk, verified collision/download details.
   [Fixture output](../deploy/hyperv/README.md) is not a host measurement.
   Resolve failures yourself; never bypass guards or adopt foreign objects.

4. **Owner host action — provision, leaving the VM Off.**

   ```powershell
   .\deploy\hyperv\New-TwinfraDev.ps1 -SshPublicKeyFile C:\operator\id_ed25519.pub
   ```

   Expected: verified image, owned network/disk/seed, VM Off. Only the exact tuple
   Internal `twinfra-nat`, NAT `10.50.0.0/24`, gateway `10.50.0.1/24` is reusable.
   Foreign/overlapping objects fail. Partial directories require owner recovery,
   never automatic deletion; unchanged verified reruns do nothing.

5. **Owner host action — create the temporary dev CA outside every Git tree.**

   ```powershell
   python tools/platform_dev_ca.py --out E:/Twinfra/secrets/dev-ca
   ```

   Expected: root and four TLS leaves ready, owner-only protected ACL applied
   before writing private files. Root: ten years, EC P-256; leaves: one year,
   serverAuth. Matching reruns preserve keys. Partial/expired output requires
   deliberate owner recovery. Never paste private keys or upload this directory.

   | Secret | DNS SANs |
   | --- | --- |
   | `twinfra-keycloak-tls` | `auth.dev.cairo-1.twinfra.example.com`, `twinfra-keycloak.twinfra-platform-services.svc.cluster.local` |
   | `twinfra-openbao-tls` | `twinfra-openbao.twinfra-platform-services.svc.cluster.local` |
   | `argocd-secret` TLS fields | `gitops.dev.cairo-1.twinfra.example.com`, `argocd-server.twinfra-platform-services.svc.cluster.local` |
   | `twinfra-gateway-tls` | `console.dev.cairo-1.twinfra.example.com` |

   `--region cairo-2` uses a separate directory and corresponding cairo-2 SANs.
   This dev PKI is replaced by WO-08; no OpenBao init or unseal occurs here.

6. **Owner host action — start the VM.**

   ```powershell
   Start-VM -Name twinfra-dev-cairo-1
   ```

   Expected: Running. Verify its SSH host-key fingerprint on the VM console
   before accepting it on Windows. Cloud-init account: `twinfra-operator`.
   Staging requires verified known_hosts and its passwordless `sudo -n`.

7. **Owner VM action — wait for bootstrap.**

   ```powershell
   ssh twinfra-operator@10.50.0.10 'sudo cloud-init status --wait --long'
   ssh twinfra-operator@10.50.0.10 'sudo cat /var/lib/vcloud-host/result.json'
   ```

   Expected: cloud-init complete, bootstrap success, `mirror_status: staged-verified`,
   Ready node `twinfra-node`, zone cairo-1a. If exit 20 reports reboot/deferred
   bootstrap, reboot the VM yourself and wait for `vcloud-host-bootstrap.service`,
   then recheck result.json. It uses `/etc/twinfra-host.env`. Never bypass this gate.
   Stable API: `api.dev.cairo-1.twinfra.example.com:6443`.

8. **Owner workstation action — copy kubeconfig securely.** Pre-create an
   operator-only `.kube` directory; never put this credential in Git or logs.

   ```powershell
   ssh twinfra-operator@10.50.0.10 'sudo cat /etc/kubernetes/admin.conf' > "$env:USERPROFILE/.kube/twinfra-dev-cairo-1.conf"
   $env:KUBECONFIG = "$env:USERPROFILE/.kube/twinfra-dev-cairo-1.conf"
   kubectl config get-contexts
   kubectl config rename-context kubernetes-admin@twinfra-dev-cairo-1 twinfra-dev-cairo-1
   ```

   Expected: explicit `twinfra-dev-cairo-1` context. Verify the generated context
   name before renaming; never print raw config. Native PowerShell 7.4 redirection
   preserves bytes. Add API hostname → `10.50.0.10` in the Windows hosts file now
   for kubectl; browser authorities map to loopback in step 13.

9. **Owner VM/workstation action — stage applications.** Prepare first-party OCI
   files using the existing builders, then stage them:

   ```powershell
   python tools/platform_pg_image.py --download-inputs --base .build/dev-images/postgres.tar --extension .build/dev-images/pgvector.tar --output .build/dev-images/postgresql-pgvector.tar --check
   # Reuse a verified console OCI artifact or follow the fresh build section below.
   python tools/platform_dev.py stage-images --context twinfra-dev-cairo-1 --ssh twinfra-operator@10.50.0.10 --archive-dir .build/dev-images
   python tools/platform_dev.py stage-images --context twinfra-dev-cairo-1 --ssh twinfra-operator@10.50.0.10 --check
   ```

   Expected: ten images, `status: passed`, `problems: []`. Default filenames:
   `console.oci.tar`, `postgresql-pgvector.tar`. Ignored, verified build artifacts
   can also be used with `--archive-dir .build/wo-21/images`; they are not shipped
   in Git. A missing archive fails before upstream staging; mismatches need review.

10. **Owner cluster action — apply dev TLS before platform deployment.** The
    bootstrap foundation already creates `twinfra-platform-services`.

    ```powershell
    python tools/platform_dev_ca.py --out E:/Twinfra/secrets/dev-ca --apply --context twinfra-dev-cairo-1
    ```

    Expected: four Secret names only; kubectl stdin carries private payloads.
    Existing Argo signing/admin fields are preserved. Console/gateway receive
    only public Keycloak CA trust; each server mounts only its own TLS private key.
    PostgreSQL CA remains CNPG-generated.

11. **Owner cluster/VM action — platform bootstrap and missing credentials.**

    ```powershell
    python tools/platform_dev.py check
    python deploy/common/prepare-secrets.py --context twinfra-dev-cairo-1
    python deploy/common/prepare-secrets.py --context twinfra-dev-cairo-1 --apply
    ssh twinfra-operator@10.50.0.10 'sudo install -d -o 26 -g 26 -m 0700 /var/lib/twinfra/local-pv/postgres-1'
    kubectl --context twinfra-dev-cairo-1 apply -k deploy/environments/dev/cairo-1/platform
    kubectl --context twinfra-dev-cairo-1 -n twinfra-platform-services rollout status deployment/argocd-repo-server --timeout=300s
    kubectl --context twinfra-dev-cairo-1 apply -k deploy/environments/dev/cairo-1/services
    ```

    Expected: render PASS; five credential Secrets created/preserved, platform
    and services created. If CRDs are establishing, wait and repeat apply.
    Confirm CNPG/PG/endpoints readiness. The retained 20 GiB vetted Local PV
    is disposable single-node dev data, not HA/backup/DR. Never reuse another
    workload's directory. Keycloak injects its client secret into realm-import
    tmpfs; import never overwrites an existing realm, so rotation needs coordination.

12. **Owner cluster action — protected-main GitOps after this PR merges.**

    ```powershell
    kubectl --context twinfra-dev-cairo-1 apply -f deploy/environments/dev/cairo-1/root.yaml
    kubectl --context twinfra-dev-cairo-1 -n twinfra-platform-services get applications
    ```

    Expected: `twinfra-root`, `twinfra-platform`, `twinfra-services` eventually
    Synced/Healthy; project `twinfra-dev`, pruning disabled. Upstream resource
    `argocd-redis` runs Valkey. Run WO-25 cache-auth/reconnect tests on the VM.

13. **Owner host/VM action — hosts and loopback tunnels.** Add these lines yourself
    to `%SystemRoot%\System32\drivers\etc\hosts`:

    ```text
    127.0.0.1 console.dev.cairo-1.twinfra.example.com auth.dev.cairo-1.twinfra.example.com gitops.dev.cairo-1.twinfra.example.com
    10.50.0.10 api.dev.cairo-1.twinfra.example.com
    ```

    On the VM, use three terminal sessions with its verified local kubeadm context
    (the workstation alias is not automatically copied back to the VM):

    ```bash
    sudo kubectl --kubeconfig /etc/kubernetes/admin.conf -n twinfra-platform-services port-forward --address 127.0.0.1 svc/twinfra-gateway 18444:9443
    sudo kubectl --kubeconfig /etc/kubernetes/admin.conf -n twinfra-platform-services port-forward --address 127.0.0.1 svc/twinfra-keycloak 18443:443
    sudo kubectl --kubeconfig /etc/kubernetes/admin.conf -n twinfra-platform-services port-forward --address 127.0.0.1 svc/argocd-server 18081:443
    ```

    On Windows, keep this tunnel running:

    ```powershell
    ssh -N -o ExitOnForwardFailure=yes -L 127.0.0.1:18444:127.0.0.1:18444 -L 127.0.0.1:18443:127.0.0.1:18443 -L 127.0.0.1:18081:127.0.0.1:18081 twinfra-operator@10.50.0.10
    ```

    Expected: forwards/tunnels listening only on loopback. No public ingress.

14. **Owner certificate-store action — trust and eventual removal.**

    ```powershell
    certutil -user -addstore Root E:\Twinfra\secrets\dev-ca\ca.crt
    ```

    Expected: public root added to **CurrentUser\Root**, not machine-wide. Get its
    public SHA1 thumbprint and remove only this root when retiring it:

    ```powershell
    python -c "from cryptography import x509; from cryptography.hazmat.primitives import hashes; from pathlib import Path; print(x509.load_pem_x509_certificate(Path('E:/Twinfra/secrets/dev-ca/ca.crt').read_bytes()).fingerprint(hashes.SHA1()).hex())"
    certutil -user -delstore Root <public-CA-thumbprint>
    ```

    Expected after removal: this dev root removed. Never disable TLS verification
    or replace unrelated roots. Keep private keys under their protected owner ACL.

15. **Owner browser/tester action — HTTPS acceptance.**

    - Portal: `https://console.dev.cairo-1.twinfra.example.com:18444/console/`
    - Keycloak: `https://auth.dev.cairo-1.twinfra.example.com:18443/admin/`
    - Argo: `https://gitops.dev.cairo-1.twinfra.example.com:18081/`

    Expected: trusted TLS without warnings; gateway exposes only TLS 9443.
    OIDC callback: `https://console.dev.cairo-1.twinfra.example.com:18444/console/callback`;
    origin/logout use the same HTTPS authority, and session cookies are Secure.
    Realm/client: `twinfra`/`twinfra-console`, PKCE and signed-token verification.
    Create a realm user with `console.admin` or `console.viewer`, require password
    update/TOTP, then test fresh login, MFA, roleless 403 and **Dev · cairo-1** badge.
    Retrieve initial admin credentials privately from Secrets; never paste them
    or callback/token URLs. Also verify node/Pods Ready, native routing/default deny,
    Argo Synced/Healthy, PG vector/TLS/persistence and Valkey authentication/reconnect.
    Record live results/failures in the Pending receipt; only the tester signs.

## Fresh workstation console artifact

Owner build preparation uses existing registered tools/hash-locked libraries;
it uses no retired WSL runtime or builder `--import` flag. With an approved build
environment and upstream access (create `.build/dev-images` first):

```powershell
npm ci --prefix console
npm run build --prefix console
python -m pip download --require-hashes --only-binary=:all: --platform manylinux_2_28_x86_64 --platform manylinux2014_x86_64 --python-version 314 --implementation cp --abi cp314 --abi abi3 -r console/requirements.txt -d .build/console/wheels
# Owner-only direct upstream export, not CRI fallback. Use a new empty hosts directory.
ssh twinfra-operator@10.50.0.10 'empty=$(mktemp -d); sudo ctr -n k8s.io images pull --local --platform linux/amd64 --hosts-dir "$empty" docker.io/library/python@sha256:b823ded4377ebb5ff1af5926702df2284e53cecbc6e3549e93a19d8632a1897e; r=$?; rmdir "$empty"; exit "$r"'
ssh twinfra-operator@10.50.0.10 'sudo ctr -n k8s.io images export --platform linux/amd64 - docker.io/library/python@sha256:b823ded4377ebb5ff1af5926702df2284e53cecbc6e3549e93a19d8632a1897e' > .build/dev-images/python.oci.tar
python tools/build_console_image.py --base .build/dev-images/python.oci.tar --output .build/dev-images/console.oci.tar --wheels .build/console/wheels
python tools/platform_dev.py check
```

Expected: console OCI matches the common lock. The existing generator rebuilds
its receipt; unexplained receipt/digest drift needs review, never hand-edited pins.
Keep only the four locked Linux wheels in the wheels directory. Codex did not
install packages, perform these upstream pulls, or import an image into a runtime.

## Later workers and static checks

The seed-only cairo-2 profile is a future rehearsal, not a second deployment.
It shares only the verified owned switch; VM/address/pod/service CIDRs are
independent. Reserved production/staging rows have no deployable profiles.
Before another PC joins, provide verified common L2 underlay: the Internal/NAT
network does not provide it across PCs. `deploy/common/join-worker.sh --plan`
refuses gateway-routed paths. Owner execution uses a root-owned 0600
JoinConfiguration in `/run/twinfra/`, a short-lived token/CA discovery hash and
stable API endpoint, then reviewed direct-node routes and repeated deny tests.
No token is read by its plan; multi-PC acceptance remains Pending.

```bash
pwsh -NoProfile -File deploy/hyperv/test-plan.ps1
python3 -m unittest discover -s tests -p test_dev_environment.py -v
python3 -m unittest discover -s tests -p test_dev_runnable.py -v
python3 tools/platform_dev.py check
python3 tools/platform_bootstrap_inventory.py --bash bash --helm helm
python3 tools/platform_validate.py --schemas .build/ci-tools/schemas
```

Only the pure fixture planner is exercised; the provisioning entry point is not
run. Naming/source checks keep upstream names and historical WSL references.
WSL deletion is WO-28. Health policies retain host/remote-node/health, without
porting the WSL world workaround. Production configuration and frozen approvals
remain unchanged. Cloudflare, OpenBao activation, observability and live
provisioning are outside WO-29.
