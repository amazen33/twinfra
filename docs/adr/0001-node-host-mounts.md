# ADR 0001: node host mounts under SSoT v2.2

Status: **Accepted by the user on 2026-10-05: “Approve the documented node exception.”**

SSoT v2.2 now records this narrow amendment in `security.nodeHostMountException`.
The machine-readable scope is [node-exceptions.json](../security/node-exceptions.json),
with a SHA256 recorded in the SSoT. It pins component identity, images, executables,
container layout, security contexts, host paths and mount modes. There is no global
hostPath, root or privileged-container bypass.

The user's hard prohibition is: **“ALL host paths must use explicit CSI mounts or vetted
Local Persistent Volumes.”** This applies to Kubernetes host volumes. APT, sysctl,
kernel mounts and kubeadm PKI configuration require root host administration by design.
Host-only preparation remains available with `BOOTSTRAP_K8S=false`.

Upstream kubeadm static control-plane pods and the requested Cilium/NVIDIA node agents
use direct node mounts. CSI-backed application storage does not replace kernel pseudo
filesystems, CNI installation directories or device-plugin registration sockets. A Local
PV/PVC facade would change scheduling and bootstrap dependencies; it does not demonstrate
safe access to these node interfaces. Neither substitution has been implemented or
represented as vetted. See [Kubernetes volume guidance](https://kubernetes.io/docs/concepts/storage/volumes/)
and [Cilium system requirements](https://docs.cilium.io/en/stable/operations/system_requirements/).

The approved scope is restricted to the pinned bootstrap components below.
The exact rendered Cilium/NVIDIA containers, capabilities, paths, read-only flags and
images are recorded in [node-agent-inventory.json](node-agent-inventory.json). That file
is the original inspection evidence, retained with its original pre-amendment findings;
its hash is part of the approval record. [node-agent-audit.json](node-agent-audit.json)
records the current allowlist evaluation. Chart changes require a new inventory and review.

| Component | Required access and justification |
| --- | --- |
| Cilium agent and init containers, `kube-system/cilium` | Root and kernel capabilities for BPF attachment, network namespaces, sysctls, state cleanup and installing CNI binaries; node BPF/cgroup/proc views and CNI/runtime directories |
| Cilium Envoy, `kube-system/cilium-envoy` | Node proxy sockets/artifacts and the upstream network capabilities for transparent proxy integration |
| NVIDIA device plugin, `kube-system/nvidia-device-plugin` | Registration with the root-owned kubelet device-plugin socket directory, CDI definitions and chart runtime directories; root is retained for node registration |
| kubeadm control plane, `kube-system` static pods | Read-only PKI, trust stores and controller/scheduler kubeconfigs; local etcd needs writable host data and read-only certificates |

The Cilium operator has no node mounts and is configured with UID/GID 65532,
`runAsNonRoot=true`, no privilege escalation and all capabilities dropped. The upstream
NVIDIA chart emits a privileged MPS DaemonSet even without an MPS sharing configuration;
the post-renderer removes it. MPS, GFD and NFD are outside this profile. No remaining
rendered Cilium/NVIDIA container sets `privileged: true`. Their root/capability needs
still require the justifications above; a successful schema check is not security approval.

The kubeadm source specifies `/etc/kubernetes/pki`, `/etc/ssl/certs`,
`/etc/kubernetes/controller-manager.conf`, `/etc/kubernetes/scheduler.conf`,
`/etc/kubernetes/pki/etcd`, and `/var/lib/etcd`. Additional trust-store directories are
conditional on the target filesystem: `/etc/ca-certificates`,
`/usr/share/ca-certificates`, `/usr/local/share/ca-certificates`, `/etc/pki/ca-trust`
and `/etc/pki/tls/certs`. This is a source-derived scope; no real kubeadm static pod
manifests were generated on Ubuntu here. Export and review the actual manifests on the
target before accepting readiness. Sources:
[control-plane volumes at v1.36.5](https://github.com/kubernetes/kubernetes/blob/v1.36.5/cmd/kubeadm/app/phases/controlplane/volumes.go),
[local etcd at v1.36.5](https://github.com/kubernetes/kubernetes/blob/v1.36.5/cmd/kubeadm/app/phases/etcd/local.go).

The accepted decision is a narrowly scoped SSoT amendment for these bootstrap node
interfaces. Application data remains restricted to explicit CSI volumes or vetted Local
PVs with node affinity. The three core namespaces enforce restricted Pod Security and
deny all ingress/egress until workload-specific allow policies are reviewed. No general
namespace, service-account or privileged-container exemption is proposed.

Alternatives are to retain the prohibition and prepare only the Ubuntu host, or redesign
the control plane/network/device registration arrangement. A managed EKS/GKE/AKS
control plane removes local control-plane static pods, but does not itself establish
compliance of the selected node CNI/GPU components.

Default bootstrap is enabled for Kubernetes v1.36.5, Cilium 1.20.2 and NVIDIA device
plugin 0.20.1. Version drift fails before host mutation with exit 42. The standalone script
embeds the exact policy and the shared dependency-free checker. Helm post-renderers run
strict kubeconform plus the policy check, and filter out the privileged MPS DaemonSet.
Foundation and validation workloads pass both checks before kubectl applies them.

Before real kubeadm initialization, dry-run manifest-generation phases write the four
static Pods into a temporary directory outside kubelet's watched directory. Both schema
and policy checks must pass there. The script applies an etcd strategic merge patch that
makes `/etc/kubernetes/pki/etcd` read-only: upstream kubeadm otherwise renders that
certificate mount writable. The generated and installed static Pods are checked, and
`--validate` also audits the current Cilium/NVIDIA objects and policy/checker integrity.
See [kubeadm's static-Pod generation phases](https://kubernetes.io/docs/reference/setup-tools/kubeadm/generated/kubeadm_init/kubeadm_init_phase_control-plane_all/).

Unknown mounts, chart drift, added capabilities, executable substitutions and application
hostPath volumes fail. Rootless operator, native routing, real dry-run output, GPU scheduling
and storage checks on Ubuntu remain live acceptance gates. The local tests use independent
source-derived static-Pod fixtures and mocked kubeadm commands; they do not establish a real
Ubuntu dry-run or deployment. This module is a single-node bootstrap, not evidence of
production HA, zero-trust completeness or cloud bursting.
