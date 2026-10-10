# Twinfra dev environment · cairo-1

WO-21 supplies static provisioning and GitOps inputs. Nothing has been provisioned
or deployed by this PR. Live acceptance and tester sign-off remain Pending in
[the receipt](acceptance/dev-environment-2026-10-10.md).
Read [WO-21 and its four amendments](work-orders/WO-21-twinfra-dev-environment.md),
[ADR-0047](adr/0047-upstream-owned-resource-names.md) and the
[identifier inventory](dev-identifier-inventory.md) before owner execution.

## Capacity and download approval

One Generation 2 VM: `twinfra-dev-cairo-1`, 8 vCPU, 24 GiB static RAM, a 100 GiB
dynamic VHDX under `E:\Twinfra`, nested virtualization enabled. It remains Off
after provisioning. The script requires at least 28 GiB free RAM and 135 GiB free
disk before creating it: full VHDX growth plus a conservative 35 GiB conversion,
cache and seed reserve. The previously recorded 115 GB on E: is insufficient;
the owner must free space first. These are guards, not measurements of this host.

Review the exact download in `-Plan` before execution:

- [Canonical generic Ubuntu 24.04 image](https://cloud-images.ubuntu.com/noble/20260926/noble-server-cloudimg-amd64.img)
- `noble-server-cloudimg-amd64.img`, **625612288 bytes**, build `20260926`.
- SHA256: `6a81c37564db9b1ee84e141922625e1d7c5b389b99bb3c572e0243607d5bb4d2`.
- [Published SHA256SUMS](https://cloud-images.ubuntu.com/noble/20260926/SHA256SUMS).

The pinned hash and size are checked against both the download and the published
checksum entry. Changing the lock requires review. A signed-checksum trust-key
workflow is deferred; the hash lock plus HTTPS is the implemented verification.
The generic QCOW2 image supports NoCloud; the Azure-specific VHD is not used.
The MIT, standard-library converter writes a fixed VHD without mounting or
booting it; Windows `Convert-VHD` makes the dynamic VHDX. Unsupported QCOW2
features, backing files, encryption and bounds violations fail before VM/network
creation. The converter's synthetic fixtures do not prove a Hyper-V boot.

Planning RAM budgets, **not measured utilization**:

| Component | Budget |
| --- | --- |
| Ubuntu, containerd and filesystem cache | 2 GiB |
| kubeadm control plane, etcd, kubelet, CoreDNS | 3 GiB |
| Cilium and Envoy | 2 GiB |
| Argo CD controller/repo/API and Valkey cache | 2 GiB |
| CNPG operator and PostgreSQL 18/pgvector | 3 GiB |
| Keycloak | 3 GiB |
| OpenBao, sealed | 0.5 GiB |
| APISIX standalone gateway | 0.5 GiB |
| Twinfra console | 0.5 GiB |
| MiniStack | 1 GiB |
| HugePage pools: 128 × 2 MiB + 1 × 1 GiB | 1.25 GiB |
| Remaining VM headroom | 5.25 GiB |

No LocalStack, Grafana, Knative, GPU/vLLM or HPC modules are installed. WO-05 audit
policies are added only when that work order is merged; this branch has no WO-05
implementation to activate. Production profile pins and the frozen node approval
and inventory files remain unchanged.

The dev validator derives the approved node policy in memory, remapping only
its canonical registry prefix to `registry.twinfra.example.com`. It records the
source policy SHA256 and leaves every image version/digest, mount, capability
and security constraint intact. The production policy output stays byte-identical.

## Owner provisioning procedure

Use Administrator **PowerShell 7**, Hyper-V management tools, Python 3 and the
repository CLIs. Enable Hyper-V/reboot yourself if the script reports it missing.
Do not run the VM concurrently with the 20 GiB WSL workload. Stop the Twinfra
workloads before stopping their distro; coordinate with pCloud/IOT-EE because
the same distro is their controller. A ≤4 GiB WSL profile is allowed only if the
RAM guard still passes. Do not unregister the distro, change mirrored networking,
delete WSL files or change `iotee-nat`.

```powershell
# Read-only real host inventory; Codex has NOT run this entry point.
.\deploy\hyperv\New-TwinfraDev.ps1 -Plan
# After reviewing collisions, free resources and download details:
.\deploy\hyperv\New-TwinfraDev.ps1 -SshPublicKeyFile C:\operator\id_ed25519.pub
# Script leaves the VM Off. Owner explicitly starts it:
Start-VM -Name twinfra-dev-cairo-1
```

The only owned network is the exact joint tuple: Internal `twinfra-nat`, NAT
`10.50.0.0/24`, and `vEthernet (twinfra-nat)` with only `10.50.0.1/24`. It never
modifies/adopts/deletes foreign objects. Exact verified reruns do nothing. Wrong
ownership, extra addresses, overlapping host prefixes/specific routes/NATs/switches,
another VM's address/CIDRs or duplicate planned ranges fail. Only Amendment 3's
five route classes are excluded. A partial failed directory is refused on rerun;
the owner inspects it and chooses recovery, rather than an automatic deletion.

The second-region seed is a future rehearsal template, not a second deployment:

```powershell
.\deploy\hyperv\New-TwinfraDev.ps1 -Plan -Region cairo-2 -Cpu 4 -MemoryGB 12 `
  -IpAddress 10.50.0.11 -PodCidr 10.120.0.0/16 -ServiceCidr 10.121.0.0/16
```

It shares only the verified owned switch; its cluster, CIDRs and VM are independent.
Reserved production/staging rows in `vcloud-ssot.yaml` have no deployable profiles.

## Shared bootstrap and initial GitOps

Cloud-init embeds the **shared** Module -1 script with `BOOTSTRAP_K8S=true`,
kubeadm and Cilium, using a dev-only environment file. Stable API authority is
`api.dev.cairo-1.twinfra.example.com:6443`, resolved to `10.50.0.10` on the first
node. Future HA needs a real DNS/VIP update; it is not supplied by a single VM.
The node is `twinfra-node`, zone `cairo-1a`. The shared kubeadm profile already initializes `taints: []`, permitting single-node scheduling; this PR preserves that behavior. Review cloud-init/bootstrap logs and
any exit 20 reboot/deferred-bootstrap gate before continuing; do not bypass it.

Owner prerequisites before bootstrap: reachable trusted registry mirror
`registry.twinfra.example.com`, its DNS/certificate/authentication, and the locked
images staged under the canonical paths in `deploy/common/images.lock.json`.
Supply the namespace's `twinfra-registry-cred` pull Secret outside Git before
starting private-image workloads; it is referenced by controllers, services and CNPG.
The public example domain is not a deployed registry. No secret is included in
the seed. Host private-registry credentials follow the existing Module -1
credential-file procedure. Local OCI builds are static artifacts; they were not
imported into a running container runtime.

The neutral image builder is reproducible without WSL, Docker or a privileged
build Pod. On a build workstation (download flag needs upstream access):

```bash
python3 tools/platform_pg_image.py --download-inputs --base .build/dev-images/postgres.tar \
  --extension .build/dev-images/pgvector.tar --output .build/dev-images/postgresql-pgvector.tar --check
```

Use `tools/build_console_image.py` with the pinned Python OCI export and verified
console wheels after `npm ci --prefix console && npm run build --prefix console`.
Neither builder imports into a runtime by default. Stage and retag the resulting
OCI manifests to the canonical references in `deploy/common/images.lock.json`.

```bash
python3 tools/platform_dev.py check
# Copy kubeconfig securely and use context twinfra-dev-cairo-1.
# Owner bootstrap, once kubeadm/Cilium are healthy:
kubectl --context twinfra-dev-cairo-1 apply -k deploy/environments/dev/cairo-1/platform
python3 deploy/common/prepare-secrets.py --context twinfra-dev-cairo-1
python3 deploy/common/prepare-secrets.py --context twinfra-dev-cairo-1 --apply
```

Supply `twinfra-keycloak-tls` and `twinfra-openbao-tls` through the owner's PKI,
outside Git. Both contain `tls.crt`, `tls.key` and public `ca.crt`; Keycloak SANs
cover `auth.dev.cairo-1.twinfra.example.com` and
`twinfra-keycloak.twinfra-platform-services.svc.cluster.local`. OpenBao's SAN
includes `twinfra-openbao.twinfra-platform-services.svc.cluster.local`.
Trust the public CA in the browser. Do not disable TLS verification. The console
and gateway mount **only public CA trust** from `twinfra-keycloak-tls`; the private
key is mounted only into Keycloak. `twinfra-postgres-ca` is CNPG-generated.

The credential helper creates missing Secrets through API stdin and prints names
only. Existing values are preserved. The Keycloak init container inserts the
mounted client secret into the realm import on memory-backed storage so APISIX
and Keycloak agree. Passwords/private runtime configuration never enter Git,
argv, environment variables, logs or a persistent host file. Subsequent client
secret rotations require coordination with Keycloak; import does not overwrite
an existing realm. OpenBao remains sealed/uninitialized until WO-08.

```bash
kubectl --context twinfra-dev-cairo-1 apply -k deploy/environments/dev/cairo-1/services
kubectl --context twinfra-dev-cairo-1 apply -f deploy/environments/dev/cairo-1/root.yaml
```

Argo reads protected `main`. The initial bootstrap before this PR merges can use
the review branch's local manifests; continuous reconciliation becomes valid
after merge. Root/children are `twinfra-root`, `twinfra-platform` and
`twinfra-services`; AppProject is `twinfra-dev`. Deletion is deliberately not
automatic. Argo's **upstream cache name `argocd-redis` runs Valkey**, never Redis.

Local storage is explicitly vetted: `twinfra-local`, a retained 20 GiB Local PV
at `/var/lib/twinfra/local-pv/postgres-1`, on node `twinfra-node`. The owner creates
that dedicated empty directory as PostgreSQL UID/GID 26 before the PVC binds.
Never reuse another workload's directory. This is single-node disposable dev
data, not HA, backup or a DR claim. CNPG uses zone anti-affinity for later nodes.

## Access and acceptance

Use the VM address for SSH. For browser testing, run loopback `kubectl port-forward`
on the VM and SSH tunnels from Windows; do not expose unrestricted port forwards:

```bash
kubectl -n twinfra-platform-services port-forward svc/twinfra-gateway 18080:9080
kubectl -n twinfra-platform-services port-forward svc/twinfra-keycloak 18443:443
kubectl -n twinfra-platform-services port-forward svc/argocd-server 18081:443
```

From Windows, tunnel ports 18080, 18443 and 18081 to those VM loopback ports with
SSH. Resolve `console.dev.cairo-1.twinfra.example.com` ,
`auth.dev.cairo-1.twinfra.example.com` and `gitops.dev.cairo-1.twinfra.example.com` to **127.0.0.1** on the operator workstation
for this tunnel arrangement. These DNS names are fixed OIDC authorities.

- Portal: `http://console.dev.cairo-1.twinfra.example.com:18080/console/`
- Identity: `https://auth.dev.cairo-1.twinfra.example.com:18443/admin/`
- Argo: `https://gitops.dev.cairo-1.twinfra.example.com:18081/`; owner supplies the matching TLS certificate in upstream `argocd-secret` and browser CA trust.

The portal uses the `twinfra` realm, `twinfra-console` client, PKCE and signed-token
verification. Owner creates a realm user, grants `console.admin` or
`console.viewer`, and requires password update/TOTP enrollment. Test fresh-browser
login, MFA and roleless 403; the header must say **Dev · cairo-1**, with no host
name. HTTP portal cookies are a local tunnel-only dev deviation; production needs
HTTPS and secure cookies. Keep browser callback/token URLs out of evidence logs.

Default-deny ingress/egress remains active. Health checks allow only host,
remote-node and health entities; the WSL `world` workaround is not ported. GitHub
egress is constrained to repo-server TCP 443 and explicit DNS. Validate denied
cross-namespace traffic, Argo Synced/Healthy from main, PostgreSQL pgvector/TLS
and persistence after restart, and Valkey authenticated/unauthenticated ping and
Argo reconnect after cache restart. Record results in the Pending receipt.

## Adding a worker later

Before joining another PC, the worker and existing node must have verified common
L2 underlay connectivity. **The initial Internal/NAT network does not provide that
across PCs.** The owner must first provide the routed/common-L2 site topology;
the helper refuses gateway-routed paths instead of silently changing switches.
Keep pod/service CIDRs and stable API DNS unchanged. Prepare the new worker with
shared Module -1 and `BOOTSTRAP_K8S=false`, using the same pinned versions.

On the new worker, run `deploy/common/join-worker.sh --plan` with
`CONTROL_PLANE_ENDPOINT`, `CONTROL_PLANE_IP`, `WORKER_IP` and a `twinfra-` node
name. The plan reads no token. For owner execution, provide a root-owned 0600
JoinConfiguration in `/run/twinfra/` with a short-lived bootstrap token and CA
discovery hash. Use the stable API endpoint, never unsafe discovery. The helper
passes only the config **path** to kubeadm. Then label `cairo-1a`, enable Cilium
direct node routes through reviewed Helm values on the verified common L2, and
repeat Ready/native-route/deny tests. Live multi-PC conformance remains Pending.

## Static verification and preserved material

```bash
pwsh -NoProfile -File deploy/hyperv/test-plan.ps1
python3 -m unittest discover -s tests -p test_dev_environment.py -v
python3 tools/platform_dev.py check
python3 tools/platform_validate.py --schemas .build/ci-tools/schemas
```

The CI naming check covers every rebuilt deployable profile under
`deploy/environments/*/*/root.yaml`. ADR-0038's migration clause preserves existing
WSL/reference profiles; reserved CIDR rows and the seed-only cairo-2 template are
not falsely reported as deployments. Upstream names are checked against verified
pinned sources, while Kustomize/Helm apply environment labels without selector
mutation. No WSL material is deleted. Neutral resource/apply/source/OCI/pgvector,
runtime configuration and AWS view helpers permit WO-28 to remove WSL code later.
Cloudflare, OpenBao activation, observability, a second region and live deployment
are outside this work order.
