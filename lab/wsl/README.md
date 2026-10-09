# Local vCloud validation on WSL2

For local browser access, run `sudo bash lab/wsl/access.sh start` inside WSL.
The [endpoint profile](endpoints/README.md) adds CPU-only applications and
observability; OpenBao initialization remains gated on operator public keys.
The [service access runbook](../../docs/service-access.md) lists tested URLs,
Windows verification and the services that are not deployed.
The [LocalStack profile](localstack/README.md) adds a restricted Community AWS
API emulator and APISIX route-controller prerequisites; it supplies no AWS GUI.

See the [WSL setup and troubleshooting guide](../../docs/WSL_SETUP_GUIDE.md) for
Windows adapter detection/firewall scope and Argo CD namespace ordering.

This profile implements the user's requested Ubuntu WSL2 K3s bootstrap with a
20 GB memory ceiling, six CPUs and mirrored networking. It is a separate
development cluster named `vcloud-wsl-local`. Production `vCloud-prod-01`, its
Ubuntu 24.04/kubeadm profile and frozen node exception remain separate inputs.

The first stage installs K3s **v1.36.5+k3s1**, Ubuntu's signed **containerd 2.x**
package with systemd cgroups, and the locked **Cilium 1.20.2** chart. Flannel,
kube-proxy, K3s network policy, Traefik, ServiceLB, metrics-server, the bundled
Helm controller and Local Path Provisioner are disabled. A non-root CoreDNS
deployment supplies cluster DNS. Three restricted namespaces retain default
deny-all, with narrow DNS and test-client allowances.

The pinned Rancher CoreDNS binary has a `NET_BIND_SERVICE` file capability, which
cannot execute in a container with all capabilities dropped. The local OCI builder
copies its verified binary bytes into a deterministic non-root layer, removes that
file xattr and imports `coredns:1.14.7-vcloud-wsl.1`. It grants no new capability.
The source manifest, unchanged binary SHA and derivative digest are recorded in
`.tools/wsl-lab/coredns-image.json`.

## Run inside WSL

```bash
cd /mnt/e/vCloud
bash lab/wsl/bootstrap.sh --plan
sudo bash lab/wsl/bootstrap.sh --apply
sudo bash lab/wsl/bootstrap.sh --validate
sudo kubectl get nodes -o wide
sudo kubectl get pods -A
```

Equivalent Make targets are `wsl-lab-plan`, `wsl-lab-apply`, `wsl-lab-validate`
and `wsl-lab-test`. The first three targets require WSL, not Git Bash.

Preflight rejects an unmanaged Kubernetes/container runtime, an occupied API
port, overlapping Pod/Service CIDRs, insufficient resources and a mismatched
ownership checkpoint. The script reserves at least 20 GiB free in the Linux
filesystem. WSL's reported virtual free disk does not establish backing Windows
disk capacity; inspect both before staging more images or data.

The private Linux kubeconfig is `/etc/vcloud-wsl/kubeconfig.yaml`, mode `0600`.
Its context is `vcloud-wsl-local`. No kubeconfig, client certificate, join token
or Secret value is copied into Git or the Windows Docker Desktop kubeconfig.
Root is explicitly required for the K3s/containerd services and their host
network/BPF setup. Application Pods and CoreDNS use UID/GID 65532, restricted
security contexts, zero added capabilities and read-only roots. Cilium's actual
Helm output passes the existing frozen node audit before installation.

## Networking and image staging

The dedicated [routing overlay](values/cilium-routing.yaml) selects legacy
**host** routing for the measured WSL GitHub-fetch workaround. Native CNI,
BPF masquerading and kube-proxy replacement remain enabled; socket LB is
explicit in this local overlay. Base/production keeps legacy routing disabled.
The [validation runbook](../../docs/WSL_SETUP_GUIDE.md#3-wsl-host-routing-ebpf-validation-and-the-production-boundary)
and [ADR-0024](../../docs/adr/0024-wsl-host-routing.md)
describe render/CI checks, live status expectations and separate SPIFFE gates.

The API binds the actual WSL node address on port **16443**, avoiding Windows'
excluded mirrored port 6443 and unreliable wildcard/localhost self-bootstrap. The private
kubeconfig uses this address with verified TLS and client authentication.
Its dedicated IPv4/IPv6 INPUT chain permits
loopback and, for IPv4, the local PodCIDR; other inbound sources are dropped.
Kubernetes Service endpoints use the same node address.
This local rule is distinct from acceptance of Cilium host-firewall policies.
The systemd service reinstalls the scoped rule and BPF mount before starting.
No global firewall chain, Windows firewall setting or WSL resource setting is
flushed or changed. Native routing/eBPF replacement, Bandwidth Manager and Host
Firewall features stay enabled in Cilium; workload bandwidth limits and host
deny-policy enforcement require their own later acceptance.

CoreDNS listens on unprivileged TCP/UDP 1053, behind Service port 53. Local
namespace policy permits only that backend in `kube-system`; it grants no
external DNS forwarding. Production DNS policies are unchanged.

Connected staging downloads exact SHA-256-locked K3s artifacts and tools and
pulls the already approved Cilium digests. The verified K3s airgap bundle is
imported into the local runtime. Images are aliased under
`registry.vcloud.example.com` and all deployed Pods use those names with pinned
versions/digests. CRI registry configuration permits only the canonical private
registry. Missing cached images fail; the runtime has no upstream fallback.
The staging CLI uses public upstream sources explicitly; this is a connected
local bootstrap and does **not** prove a private registry's DNS/TLS or an
air-gapped package mirror. Cache paths contain public artifacts, not credentials.

## Acceptance boundary

The 2026-10-06 local run passed on Ubuntu 26.04 WSL2 with 19.53 GiB visible RAM,
six CPUs and mirrored networking. Seven Pods were Ready, including the non-root
DNS backend and three policy probes. The successful apply was followed by an
independent `--validate` run. Sanitized results are saved in
[`docs/wsl-local-acceptance.json`](../../docs/wsl-local-acceptance.json).
This records a point-in-time result; rerun validation after changing the host.

A successful run writes `.build/wsl-lab/live-acceptance.json` with a Ready node,
active eBPF kube-proxy replacement, cluster DNS, allowed cross-namespace HTTP and
denied cross-namespace HTTP. It also inspects deployed image names and excludes
GPU/HPC/inference workloads. Initial evidence does not establish restart
recovery, CSI persistence, backup/restore or the full application stack.

vLLM/DeepSeek 32B, GPU device plugins, Spinifex, Kueue/Volcano jobs, PostgreSQL and
its autoscaler are not applied. Spinifex's production/reference feature flag is
unchanged at `false`. HugePage pools, GRUB, swap allocation and NVIDIA drivers
are not changed. The existing 6 GiB RTX A3000 is a later small-model development
option; no CUDA container execution is claimed by these checks.

Stop the owned services with `sudo systemctl stop k3s containerd` if a runtime
gate fails. Inspect the saved phase logs before resuming. The script has no
automatic uninstall, disk deletion, container pruning or production promotion.

The follow-on [GitOps/database stage](PLATFORM.md) has its own controller-health,
finite Local PV, SQL and reconciliation gates. The first-stage evidence above
does not establish those later outcomes.

Official references: [K3s custom CNI](https://docs.k3s.io/networking/basic-network-options),
[K3s server options](https://docs.k3s.io/cli/server),
[Cilium on K3s](https://docs.cilium.io/en/stable/installation/k3s/),
[NVIDIA WSL driver requirements](https://docs.nvidia.com/cuda/wsl-user-guide/).
