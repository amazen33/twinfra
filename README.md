# Twinfra platform bootstrap and architecture

Twinfra (formerly vCloud) — *your AWS twin, on your own infrastructure.*

[ADR-0036](docs/adr/0036-product-name-twinfra.md) and
[WO-20](docs/work-orders/WO-20-rename-to-twinfra.md) define the staged rename.
Stage A introduced the branding. The owner renamed the repository to
[`amazen33/twinfra`](https://github.com/amazen33/twinfra); Stage B updates its references.
The `vcloud` realm, client IDs,
labels, resource names, domains and SSoT identity stay unchanged until Stage C's
separate work order and Ubuntu VM rebuild. Historical records retain their original names.

[The ADR log](docs/adr/README.md) contains 39 records, including 17 Module 1 component ADRs,
the [complete Mermaid/ASCII topology](docs/module-1-topology.md), and a
[recruiter-friendly summary](docs/module-1-summary.md). Component choices follow the
user's requirements. The log distinguishes receipt-backed lab acceptance, proposed
integration gates and superseding owner decisions; production acceptance remains open.
See the [original Module 1 documentation checks](docs/module-1-validation.json) for historical static evidence.

## Repository governance

The offline [licence policy](security/licence-policy.json),
[component register](security/licence-register.json), and
[dated evidence baseline](security/licence-baseline.json) implement WO-02.
See the [licence gate runbook](security/LICENSING.md) for classes, expiry dates,
disabled-module guards and the candidate-only historical CI boundary.

The [roles and Definition of Done](docs/governance/roles.md) define product ownership,
architecture review, implementation and tester acceptance. The owner applies the
[staged branch ruleset](docs/governance/branch-protection.md). Live results use the
[acceptance receipt template](docs/acceptance/README.md); only the tester signs acceptance.

## Node diagnostic prerequisites

The [Twinfra control-plane portal](console/README.md) provides native health,
storage, MiniStack AWS emulator, DynamoDB, GitOps and identity views at
<http://localhost:18080/console/> in the owned WSL lab. Its dedicated
`vcloud/vcloud-admin` account and private first-login procedure are separate
from master administration. See the [acceptance record](docs/acceptance/vcloud-console-2026-10-08.md).

`kubectl`, **`jq`**, `curl` and `ip` (from `iproute2`) are mandatory for node-level
cluster diagnostics, including the platform health-probe verification script.
Both Ubuntu host and WSL provisioning install `jq`; `kubectl` is supplied by the
selected Kubernetes bootstrap. See [prerequisites](docs/prerequisites.md) for
installation and verification commands on existing nodes.

## Module -1: Ubuntu host preparation

Ubuntu 24.04 host preparation and a single-node **upstream Kubernetes** bootstrap using
kubeadm, system containerd and Cilium native routing. SSoT v2.2 fixes the identity to
`vCloud-prod-01`, domain `vcloud.example.com`, repository `amazen33/twinfra` and registry
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
Production Ubuntu/kubeadm, GPU passthrough and HPC fabric acceptance remain pending.
The separate WSL lab has a live Kubernetes foundation and Ready platform
controllers; its current limits are recorded in the local validation section.

Module 2 is available in the [infrastructure runbook](module-2/README.md),
with [rendered reference YAML](module-2/manifests/README.md),
[Helm chart](module-2/chart/Chart.yaml), [Cilium overrides](module-2/values/cilium.yaml),
the [Makefile](Makefile), and [static validation evidence](docs/module-2-validation.json).
It presents Twinfra with the existing `amazen33/twinfra` repository reference;
physical and live acceptance remain explicit gates.

The [pre-push validation record](docs/pre-push-validation.json) preserves the Module
-1/1/2 checks for commit `8615b0c` (PR #1). Live Ubuntu, GPU and cluster acceptance
is still pending; Module 3 has its own current validation record below.

## Module 3: end-to-end GitOps

The [Module 3 runbook](module-3/README.md) provides complete Tekton Tasks, Pipeline,
PipelineRun and authenticated push triggers, Argo CD Applications, Prometheus scrape
and alert hooks, and a Perses dashboard behind APISIX SSO. Protected-main builds promote source tags
and immutable digests to `gitops/prod`; Argo reconciles the new `vcloud-api` workload.
Restricted CI Pods use an external mTLS builder and per-run CSI workspaces.
Run `make module3-validate module3-test module3-alerts`; see
[validation evidence](docs/module-3-validation.json).

## Module 4a: OpenBao secrets

The [OpenBao runbook](module-4a/README.md) provides database/KV backend configuration,
scoped Kubernetes authentication, paired CSI file mounts, an optional static Secret
cache, and a three-step curl/psql lease/revocation test. Run
`make module4a-validate module4a-test`; see [evidence](docs/module-4a-validation.json).
CSI node installation requires its own reviewed approval; live integration remains pending.

## Module 4b: Keycloak IAM and API security

The [IAM runbook](module-4b/README.md) provides a public Keycloak realm/client reference,
APISIX OIDC plugin and identity ingress, an owned-route integration patch, API-server
OIDC arguments and narrow group RBAC. Run `make module4b-validate module4b-test`; see
[evidence](docs/module-4b-validation.json). Live import, login and cluster acceptance remain pending.

## GitHub Actions tests

Pull requests and main-branch pushes run the [CI workflow](.github/workflows/pr-tests.yaml), including regressions of immutable merged PRs #1–#3, #5 and #6. The [CI guide](docs/github-actions-tests.md) explains historical PR reruns, module coverage and evidence artifacts.

## Module 5a: vLLM and pgvector RAG

Module 5a now provides the [vLLM/pgvector RAG runbook](module-5a/README.md),
a private one-GPU Knative Service and a CPU LangChain retrieval pipeline using
CNPG and paired OpenBao CSI credentials. The examples stay outside live GitOps;
RAG is disabled and its Jobs are suspended until GPU, storage, TLS, secrets and
database acceptance pass. Run `make module5a-validate module5a-test`; see the
[validation record](docs/module-5a-validation.json).

## Module 5b: disabled hybrid GPU reference

[Module 5b](module-5b/README.md) adds DeepSeek planning, a private Knative/vLLM
example, Kueue/MultiKueue queues and a feature-gated Spinifex SigV4 capacity bridge.
Region `vcloud-hpc-1` and `vcloud.io/offload-target` preserve the platform identity.
Offloading stays disabled, quotas and deployment replicas stay zero, and live
GPU/site acceptance remains pending. See [ADR 0023](docs/adr/0023-module-5b-hybrid-hpc.md)
and the [hybrid flow](module-5b/docs/hybrid-topology.md).

## WSL local validation

The separate [WSL K3s profile](lab/wsl/README.md) follows the requested 20 GB / six
CPU mirrored-network development environment. It bootstraps a single-node
`vcloud-wsl-local` cluster with Cilium, restricted namespaces and DNS/policy
smoke tests. Heavy AI/HPC profiles stay disabled. It does not replace the
production Ubuntu/kubeadm profile. GitHub CI includes its offline safety and
schema checks when the profile is present; host execution is opt-in on WSL.

The [correction review](docs/correction-review.md) maps registry, probe, DNS-mark
and browser-access repairs to [milestones](MILESTONES.md), with explicit evidence
and remaining gates. Use the [service access runbook](docs/service-access.md)
for tested Windows URLs. GitOps controller RBAC, database initialization and
the full application stack remain pending; working health probes and a dashboard
do not establish those outcomes.

The new Hyper-V development environment is prepared statically in [the cairo-1 runbook](docs/dev-environment.md); [live acceptance](docs/acceptance/dev-environment-2026-10-10.md) remains Pending. Existing WSL material is preserved until WO-28.
