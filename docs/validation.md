# Local validation evidence

Revalidated on **2026-10-06** in `E:\vCloud` on the Windows workspace host. This is artifact
validation, not evidence of a deployed Ubuntu/Kubernetes/GPU environment.

| Check | Result |
| --- | --- |
| Bash syntax | Passed using Git for Windows Bash 5.3.15 |
| ShellCheck | Passed with ShellCheck 0.11.0, through style severity |
| Offline tests | **42 passed**, zero failures/skips |
| Cloud-Init schema | Both YAML variants pass the upstream Cloud-Init Draft-4 JSON schema snapshot |
| Embedded source | Full YAML matches the script exactly; gzip expands to that same YAML |
| Remote source pin | Current script SHA-256 embedded; downloader parses as Bash; YAML fits 16 KiB |
| Cilium Helm chart | 1.20.2 linted strictly and rendered with the generated profile on Helm 3.22.0 |
| NVIDIA device plugin Helm chart | 0.20.1 linted strictly and rendered in `kube-system` with the NVIDIA RuntimeClass |
| SSoT identity generation | Contract-derived defaults, namespace manifest and Cloud-Init environment agree |
| Core workload contract | Passed: pinned registry images, non-root validation pods and no hostPath volumes |
| Node-agent contract | Passed: four reviewed node-agent resources match the user-approved allowlist; zero findings |
| Helm post-renderers | Real yq removes MPS; real kubeconform and the shared policy checker gate the output |
| Static-Pod preview contract | Mocked kubeadm phases with independent source-derived fixtures pass; unauthorized paths, writable certificates and extra static Pods fail |
| Kubernetes schemas | kubeconform 0.8.0: **46 valid**, 0 invalid, 0 errors, 0 skipped across 9 files, targeting 1.36.5 |

The offline tests exercise malformed configuration rejection, CIDR/IP overlap, compatible
version selection, registry TLS and mandatory mirror modes, containerd 1.x/2.0/2.1+ config rendering,
GRUB argument preservation and deduplication, unchanged file writes and original backup
retention, kubeadm/Cilium settings, policy positive/negative controls, HugeTLB mmap jobs,
the NVIDIA runtime/resource contract, and exact Cloud-Init source/hash consistency.

Two apply-order tests replace **every host operation** with mocks. They demonstrate
that a pending reboot returns 20 without runtime/cluster actions, retains ownership of
the APT-installed runtime across reboot, and writes completion only after validation/smoke.
They do not execute the actual host setup or establish live convergence after a real reboot.

Charts were downloaded from their upstream release locations. kubeconform uses the
generated Kubernetes schemas from `yannh/kubernetes-json-schema`; Cloud-Init schema
validation uses `canonical/cloud-init`'s schema snapshot. Cilium's runtime-created CRDs,
the kernel datapath, GPU allocation and the kubeadm API config are subject to the live
checks; no runtime CRD or live `kubeadm config validate` success is claimed here.

The NVIDIA chart's recommendation to add an icon is informational; strict lint reports
zero failed charts. The profile is rendered in `kube-system`, avoiding the chart's default
namespace restriction.

## Reproduce artifact checks

On Ubuntu with Bash, ShellCheck, Helm 3.22.0, kubeconform 0.8.0 and Python 3.10 or newer:

```bash
python3 -m venv .tools/test-venv
. .tools/test-venv/bin/activate
pip install -r tests/requirements.txt
mkdir -p .tools/rendered .tools/schema-cache
curl -fSL https://raw.githubusercontent.com/canonical/cloud-init/main/cloudinit/config/schemas/schema-cloud-config-v1.json \
  -o .tools/cloud-config-schema.json
python3 tools/render_ssot.py --check
python3 tools/render_cloud_init.py --check
bash -n 00-setup-ubuntu-host.sh
shellcheck --severity=style 00-setup-ubuntu-host.sh
python3 tests/test_bootstrap.py --render-dir .tools/rendered --render-only

helm pull cilium --repo https://helm.cilium.io/ --version 1.20.2 --destination .tools
helm pull nvidia-device-plugin --repo https://nvidia.github.io/k8s-device-plugin \
  --version 0.20.1 --destination .tools
helm lint .tools/cilium-1.20.2.tgz --strict --namespace kube-system \
  --values .tools/rendered/cilium-values.yaml --kube-version 1.36.5
helm template cilium .tools/cilium-1.20.2.tgz --namespace kube-system \
  --values .tools/rendered/cilium-values.yaml --kube-version 1.36.5 \
  > .tools/rendered/cilium-rendered.yaml
helm lint .tools/nvidia-device-plugin-0.20.1.tgz --strict --namespace kube-system \
  --set runtimeClassName=nvidia --set gfd.enabled=false --set nfd.enabled=false \
  --set image.repository=registry.vcloud.example.com/nvcr.io/nvidia/k8s-device-plugin \
  --set image.tag=v0.20.1 --kube-version 1.36.5
helm template nvidia-device-plugin .tools/nvidia-device-plugin-0.20.1.tgz --namespace kube-system \
  --set runtimeClassName=nvidia --set gfd.enabled=false --set nfd.enabled=false \
  --set image.repository=registry.vcloud.example.com/nvcr.io/nvidia/k8s-device-plugin \
  --set image.tag=v0.20.1 --kube-version 1.36.5 \
  > .tools/rendered/nvidia-raw.yaml
yq eval 'select(.kind != "DaemonSet" or .metadata.name != "nvidia-device-plugin-mps-control-daemon")' \
  .tools/rendered/nvidia-raw.yaml > .tools/rendered/nvidia-rendered.yaml
python3 tests/test_bootstrap.py --cloud-schema .tools/cloud-config-schema.json \
  --yq "$(command -v yq)" --kubeconform "$(command -v kubeconform)"
kubeconform -strict -summary -kubernetes-version 1.36.5 -cache .tools/schema-cache \
  manifests/foundation.yaml .tools/rendered/cilium-rendered.yaml .tools/rendered/nvidia-rendered.yaml \
  .tools/rendered/smoke-base.yaml .tools/rendered/smoke-allowed.yaml \
  .tools/rendered/smoke-denied.yaml .tools/rendered/smoke-hugepages.yaml \
  .tools/rendered/smoke-gpu.yaml .tools/rendered/runtimeclass.yaml
```

Do not pass `kubeadm.yaml` or `user-data.yaml` to kubeconform: those are kubeadm/Cloud-Init
configurations, not Kubernetes API resources. The kubeadm document is validated by
`kubeadm config validate` on the actual target before init. If you change the remote
artifact URL, pass that same `--artifact-url` when checking generated Cloud-Init.

Windows tools downloaded for this run are isolated under `.tools`; no Ubuntu host
preparation was run on Windows. The pure Python jsonschema backend is used because
this host's application-control policy blocks a newly downloaded native dependency of
newer jsonschema versions. These test dependencies do not affect the Ubuntu runtime.

## Approved node exception and enforcement

The user approved the documented exception on 2026-10-05. See
[ADR 0001](adr-0001-node-host-mounts.md), the hash-locked
[node policy](../security/node-exceptions.json), and the passing
[node-agent audit](node-agent-audit.json). The original pre-amendment inventory is retained
unchanged as approval evidence; its old findings do not describe the amended contract.

All four node-agent resources match the approved identity, pinned image, executable,
container layout, security context, host paths and mount modes. Tests reject additional
capabilities, privileged mode, a different namespace, substituted commands/images, changed
paths/mount modes, unknown containers and a revoked exception. Policy hash drift fails.
The application hostPath and root restrictions remain active. Local PV annotations alone
do not approve a host directory; paths, node affinity and access settings must match a
separately vetted storage allowlist. No application Local PV is approved by this node exception. The version gate returns 42
before preflight only for unapproved bootstrap version drift.

The host script embeds the exact policy and the same dependency-free Python engine used
by offline checks. Host checks convert YAML to JSON with yq, so they need no Python YAML
package. Both Helm output and kubectl-applied manifests pass schema and contract checks.
Read-only host validation verifies checker/policy bytes, local static Pods and live agents.

The static control-plane test uses four independent source-derived synthetic Pods and
**mocked kubeadm commands**. It exercises temporary dry-run output, all-four-resource
validation, rejection of unauthorized paths/writable etcd certificates and rejection of a
fifth static Pod. It is not a real kubeadm dry-run. On Ubuntu, the bootstrap runs kubeadm's
manifest-generation dry-run phases and checks their actual output before init; it applies
an etcd certificate read-only patch and checks the installed static Pods afterward.
`render_etcd_patch` emits a merge fragment; validate the resulting Pod, not that fragment,
with kubeconform. Live phase generation and patch application remain acceptance gates.

```bash
python3 tools/check_manifest_contract.py manifests/foundation.yaml \
  .tools/rendered/smoke-base.yaml .tools/rendered/smoke-allowed.yaml \
  .tools/rendered/smoke-denied.yaml .tools/rendered/smoke-hugepages.yaml \
  .tools/rendered/smoke-gpu.yaml .tools/rendered/runtimeclass.yaml \
  .tools/rendered/cilium-rendered.yaml .tools/rendered/nvidia-rendered.yaml
# On the Ubuntu target after installation:
sudo yq eval-all -o=json -I=0 '[.]' \
  /etc/kubernetes/manifests/kube-apiserver.yaml \
  /etc/kubernetes/manifests/kube-controller-manager.yaml \
  /etc/kubernetes/manifests/kube-scheduler.yaml \
  /etc/kubernetes/manifests/etcd.yaml | \
  sudo python3 /var/lib/vcloud-host/check-manifest-contract.py \
    --policy /var/lib/vcloud-host/node-exceptions.json --mode control-plane
# The host script additionally checks schemas and rejects extra static-directory entries.
```

## Live gates still required

Provision the intended Ubuntu VM/bare-metal host, supply DNS/TLS and SSH access,
and run both apply phases with the same persistent configuration. Then establish:

- Real package repository/installation success on Ubuntu 24.04 LTS.
- A real reboot into kernel 6.8 or newer, active cgroup v2/bpffs, persistent HugeTLB pools and mounts.
- Loaded NVIDIA driver, Secure Boot/MOK status and real VM PCI passthrough where selected.
- CRI RuntimeReady and mirror-only pull evidence if `MIRROR_REQUIRED=true`.
- Live kubeadm validation/init, node/API/DNS/Cilium readiness, runtime-created CRDs and policy datapath tests.
- Real HugeTLB mmap and GPU scheduling/container probe completion.
- MPI/UCX/Apptainer execution under the intended service account, RDMA/fabric checks and remote Slurm interoperability.
- Actual CloudNativePG/vLLM/Spinifex deployment and workload/performance validation in subsequent modules.

No EKS/GKE/AKS cloud-resource parity, HA/DR, production performance, live fabric or application
deployment claim follows from these local checks.
