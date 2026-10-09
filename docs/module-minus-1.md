# Module -1 runbook

SSoT v2.2 is authoritative in `vcloud-ssot.yaml`. The user approved the narrow node
exception in [ADR 0001](adr/0001-node-host-mounts.md) on 2026-10-05. The exact allowlist
is `security/node-exceptions.json`; application hostPath volumes and privileged containers
remain prohibited. Default bootstrap is enabled for the approved pinned versions; drift
returns 42 before host mutation. `BOOTSTRAP_K8S=false` prepares only the host.

The literal cluster identity is `vCloud-prod-01`; the Cilium DNS-safe name is its lowercase
derivative `vcloud-prod-01`. Domain `vcloud.example.com` and GitOps repository
`amazen33/vCloud` are metadata/configuration only; this module creates no DNS zone,
repository, Argo CD Application or cloud resources. Regenerate identity/foundation with
`python3 tools/render_ssot.py`, then Cloud-Init with `python3 tools/render_cloud_init.py`.

This package prepares a fresh Ubuntu runtime host and initializes one upstream Kubernetes
control plane with kubeadm. The single node schedules workloads as well as the control
plane. System containerd owns CRI configuration and Cilium owns pod networking, service
load balancing and NetworkPolicy enforcement.

## Provisioning contract

| Item | Required configuration |
| --- | --- |
| OS | Ubuntu 24.04 LTS only (SSoT v2.2) |
| Kernel/boot | Running kernel â‰¥6.8; GRUB for persisted cgroup/HugeTLB arguments |
| CPU | At least two cores; four recommended; amd64 or arm64 with suitable page sizes |
| RAM | 8 GiB recommended for bootstrap; requested pools reserve 1.25 GiB, plus a 4 GiB normal-RAM floor |
| Disk | At least 20 GiB currently free under `/var/lib`; size for images, etcd and workload storage separately |
| Network | Assigned, stable IPv4 node address, working DNS/NTP and outbound HTTPS to package/image sources |
| HugePages | VM CPU exposes `pdpe1gb` on amd64; ARM must expose the requested 2 MiB/1 GiB HugeTLB sizes |
| GPU | GPU visible in guest PCI topology; NVIDIA driver â‰¥550 compatible with the actual GPU |
| KVM | Optional `ENABLE_KVM=true`; parent hypervisor exposes VMX/SVM and nested virtualization |

Allocate fixed guest RAM and expose the host CPU model where possible. Avoid ballooning
and memory overcommit against the reserved HugeTLB pools. Guest pools do not require the
hypervisor's VM memory backend itself to use hugepages. A guest cannot enable PCI
passthrough, expose hidden CPU features, or configure its parent's IOMMU/VFIO bindings.

For KVM/libvirt, use a cloud image and NoCloud seed (for example `cloud-localds seed.img
user-data.yaml meta-data`), a virtio disk/NIC, and host CPU passthrough. Supply a unique
instance ID and hostname in `meta-data`; clone guests with unique identities. Attach a
passed-through GPU only after configuring the parent IOMMU, device grouping and guest
firmware. These parent-host operations are outside this script's execution scope.

For Proxmox, store the generated YAML in storage that supports snippets and attach it to
the **VM** using `qm set VMID --cicustom 'user=local:snippets/user-data.yaml'`. The VM needs
an attached cloud-init drive, a host-compatible CPU model, fixed RAM and sufficient disk.
Supply SSH access in your custom user-data: custom snippets replace provider-generated
user configuration. Reusing a VMID or applying these commands to an existing VM is a
separate operator action. See [Proxmox Cloud-Init support](https://pve.proxmox.com/wiki/Cloud-Init_Support).

Use a fresh guest, rather than an LXC container. A Spinifex guest needs nested KVM only
if that guest will launch additional VMs; a Kubernetes workload node does not need KVM
for ordinary pods. Keep external VM networking ownership separate from Cilium's pod
networking. The optional QEMU/KVM packages do not install or initialize Spinifex services.

## Configuration and versions

Install `host.env.example` to `/etc/vcloud-host.env` with root ownership and mode `0600`.
This trusted shell configuration is read after process environment variables and persists
over reboot. For Cloud-Init, edit its matching `write_files` entry before provisioning.

| Setting | Default | Effect |
| --- | --- | --- |
| `KUBERNETES_VERSION` | `v1.36.5` | Exact upstream kubeadm/kubelet/kubectl version; packages are held |
| `CILIUM_VERSION` | `1.20.2` | Tested profile: Kubernetes minors 1.33â€“1.36 |
| `HUGEPAGES_2M` / `HUGEPAGES_1G` | `128` / `1` | Counts, not byte sizes; both are persisted as boot reservations |
| `MIN_NORMAL_RAM_MIB` | `4096` | RAM that must remain outside the pools |
| `ENABLE_GPU` | `auto` | `auto`, `true` (fail if absent), or `false` |
| `NVIDIA_DRIVER_PACKAGE` | `auto` | Ubuntu's recommended compatible package, branch â‰¥550 |
| `NVIDIA_TOOLKIT_VERSION` | `1.20.1-1` | Exact version of all four toolkit/libnvidia packages |
| `ENABLE_KVM` | `false` | QEMU/KVM dependencies and virtualization validation |
| `INSTALL_HPC` | `true` | MPI, UCX, PMIx, RDMA tools, Apptainer and Slurm client/development libraries |
| `BOOTSTRAP_K8S` | `true` | Initialize this single node; `false` prepares host/packages only |
| `RUN_SMOKE_TESTS` | `true` | Temporary DNS/policy/HugePage/GPU acceptance workloads |
| `REGISTRY_MIRROR` | `https://registry.vcloud.example.com` | Trusted pull-through mirror authority |
| `MIRROR_REQUIRED` | `true` | Fixed by SSoT; upstream fallback is disabled |
| `REGISTRY_CA_FILE` | empty | Optional absolute PEM CA path; never disables TLS verification |
| `NODE_IP` / `NODE_NAME` | detected | Set explicitly for multi-NIC hosts and stable DHCP/static identities |
| `POD_CIDR` / `SERVICE_CIDR` | `10.42.0.0/16` / `10.43.0.0/16` | Must not overlap each other, host NIC/VPN routes or the node IP |

The CLI pins are Helm 3.22.0, Cilium CLI 0.20.1, kubeconform 0.8.0, Tekton CLI 0.46.1,
Argo CD CLI 3.5.3, yq 4.54.1 and crictl 1.36.0. `jq`, containerd and HPC dependencies come
from signed Ubuntu/PPA repositories. These APT dependencies follow their enabled
repository candidates; this is not a complete immutable OS/package lock. Successful
apply records `/var/lib/vcloud-host/package-versions.tsv` for reproducibility/audit.

Binary CLI assets require published SHA-256 digests; Helm uses its published checksum
file. Digests retrieved over HTTPS detect download corruption and mismatched artifacts;
they are not independent publisher signature verification. CLI stamps include the installed
binary hash and selected version to detect drift. GitHub's unauthenticated API rate limit
can affect first-time downloads; retry after its reset rather than bypassing digest checks.

Kubernetes 1.36 is in Cilium 1.20's tested compatibility range. Exact supported patch
versions can be overridden, but the profile rejects unreviewed minor combinations.
The node exception additionally pins Kubernetes v1.36.5, Cilium 1.20.2 and NVIDIA device
plugin 0.20.1. A compatible version override still requires a reviewed exception update;
the script rejects it before apply. Changing versions on an initialized cluster requires the separate kubeadm upgrade
procedure. See [Cilium Kubernetes compatibility](https://docs.cilium.io/en/stable/network/kubernetes/compatibility/)
and [upstream kubeadm installation](https://kubernetes.io/docs/setup/production-environment/tools/kubeadm/install-kubeadm/).

## Apply stages and convergence

1. Preflight rejects unsupported OS/architecture, inadequate RAM/disk/CPU, hidden 1 GiB
   page features, CIDR overlap, conflicting distributions and unmanaged active runtimes.
2. Kernel preparation installs the supported 24.04 kernel if needed, verifies eBPF/BTF/overlay/HugeTLB features,
   loads modules and persists bpffs as a systemd mount required by containerd.
3. Persist cgroup v2 and both HugeTLB pools with GRUB. Apply network/memory/file/inotify
   sysctls. Disable swap entries and mask current swap units. All original edited files
   receive one `.vcloud-original` backup; subsequent identical writes preserve content/mtime.
4. Install GPU drivers/toolkit when a GPU is selected. Install signed Kubernetes packages,
   verified CLI binaries, and the selected HPC/KVM dependencies.
5. If reboot is needed, write a pending result and exit **20** before CRI configuration,
   kubeadm initialization or workload validation. Same-boot reruns remain pending.
6. After boot, configure the system containerd socket with overlayfs and `SystemdCgroup`
   for every runtime, including `nvidia`. Configure the containerd `certs.d/_default`
   mirror and perform an actual CRI image pull.
7. Initialize kubeadm without its kube-proxy addon. Kubeadm installs no default Flannel
   or network-policy controller, so the K3s-specific `--flannel-backend=none` and
   `--disable-network-policy` switches do not apply. Install Cilium with
   `kubeProxyReplacement=true`, Kubernetes IPAM and matching CNI directories. See
   [kubeadm init phases](https://kubernetes.io/docs/reference/setup-tools/kubeadm/kubeadm-init/)
   and [Cilium kube-proxy replacement](https://docs.cilium.io/en/stable/network/kubernetes/kubeproxy-free/).
8. Install the NVIDIA RuntimeClass/device plugin when selected. Wait for node, DNS,
   Cilium and GPU resource readiness. Run temporary acceptance jobs, then write `ready`
   and `/var/lib/vcloud-host/complete` only when requested gates succeed.

Cilium uses `routingMode: native`, `ipv4NativeRoutingCIDR` equal to the pod CIDR,
`ipam: kubernetes` and full kube-proxy replacement. Underlay routes must reach every
remote node's PodCIDR. `autoDirectNodeRoutes=false` avoids assuming a shared L2; configure
BGP/cloud routes for each site before adding nodes. This does not build the hybrid network.
See [Cilium native routing](https://docs.cilium.io/en/stable/network/concepts/routing/).

The three core namespaces receive restricted Pod Security and default-deny ingress and
egress policies from `manifests/foundation.yaml`. These policies allow nothing, including
DNS or API access, until workload-specific allowances are reviewed. System networking and
static control-plane components remain in `kube-system`; default-deny policies do not claim
to isolate hostNetwork traffic. The temporary smoke namespace supplies explicit DNS and
server allowances to test policy enforcement.

The script reuses its own successful kubeadm initialization. It never invokes `kubeadm
reset`, upgrades an initialized cluster, repartitions disks, disables the host firewall,
or rebinds PCI devices. Restarting containerd occurs only when its owned configuration
or systemd override changes. Mirror host files are read by containerd without a restart.
Application/HPC service deployment is not part of bootstrap convergence.

## Registry contract

`certs.d/_default/hosts.toml` affects the **system containerd CRI** used by kubelet.
The mirror must support containerd's upstream namespace query (`?ns=registry.k8s.io`,
`?ns=quay.io`, etc.) and the image repositories required by this profile. A Harbor proxy
project with a path prefix is not automatically a universal mirror; supply compatible
per-registry endpoints in a reviewed extension. Explicit existing namespace host files
override `_default`; use a fresh host to avoid unintended legacy overrides.

SSoT requires `MIRROR_REQUIRED=true`; the default server is the trusted central registry
and upstream fallback is disabled. All generated workload/agent images also refer to
`registry.vcloud.example.com` explicitly, using their upstream authority as a repository
prefix: `docker.io/library/busybox`, `docker.io/library/python`, `docker.io/nvidia/cuda`,
`quay.io/cilium/cilium`, `quay.io/cilium/cilium-envoy`, `quay.io/cilium/operator-generic`,
and `nvcr.io/nvidia/k8s-device-plugin`. Preserve the upstream manifest digests for Cilium.
Populate Kubernetes images at the exact paths emitted by
`kubeadm config images list --config /var/lib/vcloud-host/kubeadm.yaml`, including its
CoreDNS repository layout, and stage `registry.k8s.io/pause:3.10.1`. This naming convention
requires registry provisioning; it is not proof that a pull-through service exists.
TLS verification remains enabled; no registry or remote pull was tested here.
Use workload `imagePullSecrets` for private image authentication; no registry password
is embedded in user-data. Control-plane/private mirror bootstrap requires anonymous
read access or separately provisioned node credentials. See
[containerd host configuration](https://github.com/containerd/containerd/blob/main/docs/hosts.md).

## HugePages, GPU and HPC integration

Both explicit HugeTLB sizes are reserved separately. `vm.nr_hugepages` only controls the
default pool and is therefore not used to configure the 1 GiB pool. Boot reservations
avoid fragmentation; missing allocation after reboot fails with an actionable message.
Running pools are not shrunk by an apply. Changing configured counts rewrites boot
reservations and requires a maintenance reboot. Host consumers get `/dev/hugepages-2M` and
`/dev/hugepages-1G`; the default host mounts are restricted to their owning group. Assign
a site-controlled group/access policy before giving HPC users access. Kubelet mounts its
own HugePages emptyDir volumes. See [Linux HugeTLB semantics](https://docs.kernel.org/admin-guide/mm/hugetlbpage.html).

CloudNativePG/PostgreSQL must request/limit the relevant `hugepages-2Mi` capacity and
configure PostgreSQL memory/huge_pages accordingly in its deployment module. vLLM's
GPU VRAM, CUDA compatibility and tensor-parallel settings are separate from host
HugeTLB pools. These pools alone do not prove either application's performance.

NVIDIA setup uses the Ubuntu-recommended package â‰¥550 and the signed NVIDIA toolkit
repository, retaining runc as the default runtime. The named `nvidia` handler is selected
through a RuntimeClass and a Kubernetes device plugin exposes `nvidia.com/gpu` resources.
The GPU probe requests one GPU and runs `nvidia-smi` inside a CUDA container. Secure
Boot/MOK enrollment or unsupported passthrough can block loading; a second failed boot
fails rather than repeating reboot requests indefinitely. See
[NVIDIA containerd integration](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/install-guide.html).

OpenMPI, UCX, hwloc, PMIx, RDMA utilities, non-setuid Apptainer and Slurm client/development
libraries prepare the workload dependency layer. Version checks do not establish fabric
throughput, multi-node MPI, GPU-aware MPI or Slurm scheduler connectivity. Keep Slurm
client ABI/version compatible with the actual controller. Ubuntu AppArmor/user-namespace
policy remains enabled; site policy and package profiles must permit Apptainer for the
intended service user. See [Apptainer Ubuntu installation](https://apptainer.org/docs/admin/latest/installation.html).

The upstream [Mulga Spinifex](https://github.com/mulgadc/spinifex) project is a QEMU/OVN
AWS-compatible cloud platform. The requested MPI/UCX/Slurm libraries are HPC workload
dependencies, not proof of a Spinifex agent/controller installation. This module does not
configure Spinifex services, OVN, storage backends, credentials, an HPC controller or an
RDMA fabric. If your named Spinifex integration refers to a different agent/controller,
its project/version and service contract must be supplied before that layer is installed.

## Cloud-Init use

`user-data.yaml` embeds the complete annotated script and a one-shot resume unit.
It needs no script host. It enables the resume unit for the next boot, runs the first
apply directly, and reboots once if a pending marker exists. Starting a unit ordered
after `cloud-final.service` from inside that service would deadlock, so it is deliberately
not started by `runcmd`. On the next boot the unit resumes after cloud-final/network-online.
An unresolved later reboot request remains visible as status `reboot-required`; inspect
the journal and remedy the cause. Cloud-Init success by itself is not node readiness.

EC2 limits raw user data to 16 KiB. The full inline YAML and its gzip representation
exceed that limit; use the generated `user-data-remote.yaml` instead. First publish the
exact script to a site-controlled HTTPS artifact URL, then generate the small variant:

```bash
python3 tools/render_cloud_init.py \
  --artifact-url https://YOUR-ARTIFACT-HOST/vcloud/00-setup-ubuntu-host.sh
```

That variant downloads the artifact over HTTPS, verifies the SHA-256 embedded by the
generator, installs it as root and uses the same apply/resume flow. Its default
`artifacts.example.com` URL is a placeholder and must be replaced. Publishing the
artifact is a separate provisioning prerequisite. See
[EC2 user-data limits](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/user-data.html)
and [Cloud-Init reboot behavior](https://docs.cloud-init.io/en/latest/reference/modules.html#power-state-change).

After any source edit, regenerate both variants and check they match:

```bash
python3 tools/render_cloud_init.py
python3 tools/render_cloud_init.py --check
```

Preserve the selected `--artifact-url` when regenerating/checking a customized remote
variant. No SSH key, password or cloud credential is embedded by this package; provide
the provider's normal access policy before booting the VM.

## Acceptance and recovery

`--validate` checks existing readiness without creating resources, installing packages,
pulling images or modifying host files. The apply-only smoke suite creates an owned
`vcloud-host-validation` namespace, checks a healthy server/DNS, proves authorized
HTTP succeeds and unauthorized HTTP fails, uses `mmap` against each requested HugeTLB
size, and runs the GPU container when hardware is present. Cleanup removes only that
dedicated namespace. Artifacts/logs remain under `/var/lib/vcloud-host` for inspection.

```bash
sudo cat /var/lib/vcloud-host/result.json
sudo cat /var/lib/vcloud-host/reboot-required  # only if pending
sudo journalctl -u vcloud-host-bootstrap.service -b
sudo journalctl -u containerd -u kubelet -b
sudo env KUBECONFIG=/etc/kubernetes/admin.conf cilium status
```

| Gate | Passing evidence |
| --- | --- |
| Host | Running kernel/config, cgroup2fs, bpffs, overlayfs, swap off, exact sysctls |
| Memory | Both sysfs totals and kubelet-advertised HugePage resources meet configured counts |
| CRI | Active containerd, `RuntimeReady=true`, all runtimes use systemd cgroups, CRI image pull succeeds |
| Kubernetes/CNI | API `/readyz`, node Ready, CoreDNS/Cilium ready, no kube-proxy/Flannel daemonsets |
| Policy | Positive HTTP control and denied HTTP job both complete successfully |
| HugeTLB use | Job maps/touches one page from each requested size |
| GPU, if selected | Driver â‰¥550, allocatable GPU, NVIDIA RuntimeClass/device plugin and GPU job pass |
| Mirror-only, if required | Mirror endpoint trusted/reachable and CRI pull succeeds with fallback disabled |

The kubeadm admin kubeconfig remains root-readable (`0600`); create scoped access for
users separately. The single-node lab does not provide EKS/GKE/AKS cloud load balancers,
managed IAM/OIDC integrations, managed storage/CSI, HA/DR or production hardening.
Configure host/cloud firewalls for TCP 6443/10250 and, when adding peers, etcd traffic and
native PodCIDR routes and Cilium health/proxy ports required by the enabled features on
trusted peer networks. The native profile needs no VXLAN port. Do not expose these
ports indiscriminately; this script preserves firewall rules. HA, ingress, observability,
secrets, storage, CloudNativePG, vLLM and live Spinifex jobs require subsequent modules.

For a failed/partial kubeadm init, inspect `/etc/kubernetes/manifests`, certificates, the
kubelet journal and API readiness. Do not delete these blindly. The script does not
attempt an automatic reset or upgrade. Correct package/mirror/network problems and
rerun with the same configuration. For a disposable fresh guest, recreating it from its
original image is the cleanest rollback. On a retained host, restore reviewed individual
`.vcloud-original` files, remove owned overrides deliberately, run `update-grub`, and
reboot as appropriate; package installations and live kernel reservations are not undone
by copying a config backup.
