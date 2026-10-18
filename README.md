# Twinfra platform bootstrap and architecture

Twinfra (pronounced *twin-infra*) — *your AWS twin, on your own infrastructure* — an AWS-compatible API subset; see [capabilities](docs/capabilities.md).

## Current capability and readiness

**v0.1.0 is the drafted dev release; no candidate tag or stable release is published.**
The accepted environment is `twinfra-dev-cairo-1`: one Ubuntu 24.04 bare-metal
Dell node. The [release notes](docs/release-notes/0.1.0.md) distinguish actual
running versions, Accepted scope, known limitations and the remaining rc gates.

| Dev-verified item | Accepted evidence and exact scope |
| --- | --- |
| Single-node host and platform baseline | [WO-31](docs/acceptance/dev-environment-2026-10-13.md): bootstrap, host/manifest checks, two full acceptance passes and the owner-approved 12-hour post-reboot soak; no production or HA claim |
| Console signed tokens and browser access | [WO-04](docs/acceptance/console-token-verification-2026-10-10.md): TOTP sign-in/out, emulator read views, role denial and token negatives 401/401/401/403 |
| LocalStack removal / sole MiniStack emulator | [WO-06](docs/acceptance/localstack-removal-2026-10-10.md): no LocalStack resources/images, MiniStack health and S3/EC2/DynamoDB read views; APIs remain emulated |
| Argo CD / Valkey cache | [WO-25](docs/acceptance/valkey-2026-10-09.md): authentication, measured cache hits, all three clients reconnect after the authorized restart, fresh healthy reconciliation |
| CoreDNS / etcd maintenance | [Accepted WO-34 P2 live receipt](docs/acceptance/wo34-p2-2026-10-15.json) and [WO-31 runtime acceptance](docs/acceptance/dev-environment-2026-10-13.md): CoreDNS 1.14.7 / etcd 3.6.15 and their locked digests |
| Static node address / router-loss resilience | [WO-36](docs/acceptance/host-network-2026-10-15.md): .3 retained through a 40-second router outage; zero DHCP lease losses or post-boot pod/control-plane restarts |
| Safe static-netplan transaction qualification | [WO-36a](docs/acceptance/host-network-fix-2026-10-15.md): real Ubuntu VM apply/refusal/rollback, maximum gap 0.245504 s; current owned profile adoption checked on cairo-1 |

These signed results do not establish Dell rollback, staging-failure recovery,
Foundation 1.0 or whole-platform/production acceptance. WO-31 accepts a
**12-hour dev soak by owner exception**, not a 24-hour or rc-window soak.
The subsequent eno1 link-flap warning is tracked separately in that receipt.
The [17:08 UTC baseline](docs/acceptance/release-0.1.0-2026-10-17.md) and
[22:24 UTC post-reboot pass](docs/acceptance/dev-environment-2026-10-13.md#live-verification-and-soak-2026-10-17-and-2026-10-18-recorded-by-the-architect)
are distinct from the still-Pending
[consolidated rc receipt](docs/acceptance/release-0.1.0-2026-10-16.md).
The owner-run [acceptance procedure](docs/runbooks/release-acceptance.md) governs
that window. This release-readiness PR runs no live suite.

[ADR-0052](docs/adr/0052-evidence-first-foundation-1-0.md) gates Foundation 1.0
on signed live evidence. Static implementation and owner observations are
reported separately in the [capability table](docs/capabilities.md).
Modules 5a and 5b stay disabled. The supported environment is kubeadm on
Ubuntu 24.04, bare metal or VM; no other environment is supported.
High availability, multi-tenancy, compliance and production readiness are not claimed.

WSL is retired; see [ADR-0045](docs/adr/0045-wsl-retirement.md).

[The ADR log](docs/adr/README.md) contains <!-- adr-count:start -->50 records<!-- adr-count:end -->,
including the 17 historical Module 1 component decisions. The count is generated
from its index by `python tools/ci/check_capabilities.py --write`.
The [Mermaid/ASCII topology](docs/module-1-topology.md) and
[recruiter summary](docs/module-1-summary.md) are design references, not evidence
of running services. Original [Module 1 checks](docs/module-1-validation.json)
remain historical static evidence.

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

Use the [cairo-1 tunnel and browser procedure](docs/dev-environment.md#part-1-cairo-1-on-bare-metal)
for <https://console.dev.cairo-1.twinfra.example.com:18444/console/>.
Keep the laptop loopback forwards open and trust the public, name-constrained
dev CA. The console uses realm `twinfra`, client `twinfra-console` and a dedicated
user with `console.admin`; this is separate from Keycloak master-realm
administration. The realm import contains no users. Follow the runbook's
private first-user/password/TOTP procedure; never print credentials.

`kubectl`, **`jq`**, `curl` and `ip` (from `iproute2`) are mandatory for node-level
cluster diagnostics, including the platform health-probe verification script.
Ubuntu host provisioning installs `jq`; `kubectl` is supplied by the
selected Kubernetes bootstrap. See [prerequisites](docs/prerequisites.md) for
installation and verification commands on existing nodes.

## Module -1: Ubuntu host preparation

Ubuntu 24.04 host preparation and a single-node **upstream Kubernetes** bootstrap using
kubeadm, system containerd and Cilium native routing. The production SSoT v2.2
profile retains the literal identity
`vCloud-prod-01`, domain `vcloud.example.com`, repository `amazen33/twinfra` and registry
`registry.vcloud.example.com`. The current dev profile uses `twinfra-dev-cairo-1`
and the region-specific names in the [dev runbook](docs/dev-environment.md).
HugePages remain **128 × 2 MiB + 1 × 1 GiB**.

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

Module 2 is available in the [infrastructure runbook](module-2/README.md),
with [rendered reference YAML](module-2/manifests/README.md),
[Helm chart](module-2/chart/Chart.yaml), [Cilium overrides](module-2/values/cilium.yaml),
the [Makefile](Makefile), and [static validation evidence](docs/module-2-validation.json).
It presents Twinfra with the existing `amazen33/twinfra` repository reference;
physical and live acceptance remain explicit gates.

The [pre-push validation record](docs/pre-push-validation.json) preserves the Module
-1/1/2 checks for commit `8615b0c` (PR #1). Live Ubuntu, GPU and cluster acceptance
is still pending; the Module 3 reference has a separate validation record below.

## Module 3: implemented delivery reference (live acceptance pending)

The [Module 3 runbook](module-3/README.md) retains implemented Tekton Tasks,
Pipeline, PipelineRun and push-trigger references, Argo CD Applications and
Prometheus hooks. Their [validation record](docs/module-3-validation.json)
is static evidence; end-to-end delivery is not Dev-verified.
[ADR-0052 decision 5](docs/adr/0052-evidence-first-foundation-1-0.md) supersedes
the Tekton/delivery choice with GitHub Actions, GHCR using `GITHUB_TOKEN`, signed
provenance and verification of the expected signer/provenance before deployment.
That deployment-verification work remains pending; this documentation change
does not remove Tekton or implement the replacement.

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

## Reference designs (disabled)

### Module 5a: vLLM and pgvector RAG

The Module 5a reference provides the [vLLM/pgvector RAG runbook](module-5a/README.md),
a private one-GPU Knative Service and a CPU LangChain retrieval pipeline using
CNPG and paired OpenBao CSI credentials. The examples stay outside live GitOps;
RAG is disabled and its Jobs are suspended until GPU, storage, TLS, secrets and
database acceptance pass. Run `make module5a-validate module5a-test`; see the
[validation record](docs/module-5a-validation.json).

### Module 5b: disabled hybrid GPU reference

[Module 5b](module-5b/README.md) adds DeepSeek planning, a private Knative/vLLM
example, Kueue/MultiKueue queues and a feature-gated Spinifex SigV4 capacity bridge.
Region `vcloud-hpc-1` and `vcloud.io/offload-target` preserve the platform identity.
Offloading stays disabled, quotas and deployment replicas stay zero, and live
GPU/site acceptance remains pending. See [ADR 0023](docs/adr/0023-module-5b-hybrid-hpc.md)
and the [hybrid flow](module-5b/docs/hybrid-topology.md).

These deferred designs return only with a new owner decision under
[ADR-0052](docs/adr/0052-evidence-first-foundation-1-0.md). Their manifests and
tests establish reference behavior only; they provide no GPU/HPC runtime claim.
