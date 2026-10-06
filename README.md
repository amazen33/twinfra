# vCloud platform bootstrap and architecture

[Module 1](docs/adrs/README.md) contains 17 component ADRs for the requested platform,
the [complete Mermaid/ASCII topology](docs/module-1-topology.md), and a
[recruiter-friendly summary](docs/module-1-summary.md). Component choices follow the
user's requirements; their integration contracts are proposed designs with explicit
release, security and live acceptance gates.
See the [Module 1 documentation checks](docs/module-1-validation.json) for validation evidence.

## Module -1: Ubuntu host preparation

Ubuntu 24.04 host preparation and a single-node **upstream Kubernetes** bootstrap using
kubeadm, system containerd and Cilium native routing. SSoT v2.2 fixes the identity to
`vCloud-prod-01`, domain `vcloud.example.com`, repository `amazen33/vCloud` and registry
`registry.vcloud.example.com`. HugePages remain **128 × 2 MiB + 1 × 1 GiB**.

**The documented node exception is approved.** Only the pinned kubeadm/Cilium/NVIDIA
components may use their listed node mounts and root/capability settings. The allowlist
is in `security/node-exceptions.json`; schema and policy checks run before applying
manifests. Unapproved version drift returns **42 before host changes**. Application
hostPath volumes and privileged containers, including the MPS daemon, remain prohibited.

| Deliverable | Purpose |
| --- | --- |
| `00-setup-ubuntu-host.sh` | Annotated, convergent host preparation, bootstrap and validation |
| `user-data.yaml` | Self-contained Cloud-Init with the exact script and post-reboot resume |
| `user-data-remote.yaml` | Smaller Cloud-Init; requires publication of the script at an HTTPS URL |
| `host.env.example` | Persistent configuration for manual installation |
| `docs/module-minus-1.md` | Provisioning, configuration, acceptance and recovery runbook |
| `docs/validation.md` | Local validation evidence and outstanding live gates |
| `vcloud-ssot.yaml` | Canonical platform identity and security contract |
| `manifests/foundation.yaml` | Three restricted namespaces and deny-all policies |
| `tools/render_ssot.py` | Generate contract-derived defaults and detect drift |
| `tools/check_manifest_contract.py` | Check pinned registry images, root and host-volume requirements |
| `security/node-exceptions.json` | Exact approved node scope and approval evidence |

On a fresh **Ubuntu 24.04 LTS VM/bare-metal host** with GRUB, two or more CPU cores,
8 GiB RAM recommended, and at least 20 GiB free under `/var/lib`:

```bash
sudo install -m 0600 -o root -g root host.env.example /etc/vcloud-host.env
# Optional: BOOTSTRAP_K8S=false prepares the host without initializing Kubernetes.
# Configure static NODE_IP, GPU/KVM switches and site networks; identity is SSoT-fixed.
sudoedit /etc/vcloud-host.env
bash 00-setup-ubuntu-host.sh --plan
sudo bash 00-setup-ubuntu-host.sh --apply
```

Exit **20** means reboot and rerun `--apply`. After successful Kubernetes bootstrap:

```bash
sudo bash 00-setup-ubuntu-host.sh --validate
sudo cat /var/lib/vcloud-host/result.json
sudo env KUBECONFIG=/etc/kubernetes/admin.conf kubectl get nodes -o wide
```

Cloud-Init handles the initial reboot and resumes. Supply
your provider's SSH key/user access and network configuration alongside this snippet.
The embedded YAML is larger than EC2's 16 KiB user-data limit, including its gzip version;
use `user-data-remote.yaml` there after setting a real artifact URL and hosting the exact
script. The remote variant pins its SHA-256 and fails if the artifact differs.

The registry requires actual DNS/TLS and staged images at the documented repository paths;
upstream fallback is disabled. A private registry requires appropriate pull credentials.
`platform-services`, `workload-apps` and `hpc-compute` receive deny-all policies without
implicit DNS/API allowances. Add reviewed workload-specific allow rules before deployment.
Native routing requires underlay routes to remote node PodCIDRs.

Local syntax, configuration, schema and Helm checks are documented in `docs/validation.md`.
No Ubuntu VM, live Kubernetes cluster, GPU passthrough or HPC fabric was deployed here.

Module 2 is available in the [infrastructure runbook](module-2/README.md),
with [rendered reference YAML](module-2/manifests/README.md),
[Helm chart](module-2/chart/Chart.yaml), [Cilium overrides](module-2/values/cilium.yaml),
the [Makefile](Makefile), and [static validation evidence](docs/module-2-validation.json).
It uses vCloud / amazen33/vCloud throughout; physical and live acceptance remain explicit gates.

The [pre-push validation record](docs/pre-push-validation.json) records the complete
2026-10-06 artifact checks. Live Ubuntu, GPU and cluster acceptance is still pending.

## GitHub Actions tests

Pull requests and main-branch pushes run the [CI workflow](.github/workflows/pr-tests.yaml), including a regression of merged PR #1. The [CI guide](docs/github-actions-tests.md) explains historical PR reruns, module coverage and evidence artifacts.
