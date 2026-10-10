# Twinfra architecture decision log

This is the single ADR log. Numbers 0001–0036 are unique; the next free number is
**0045**. Module 3 delivery retains 0020; registry mirroring is 0028. The accepted
D1–D8 owner decisions are copied verbatim in 0029–0035. D9–D12 remain open.
Use the [work-order handoff](../work-orders/README.md) for implementation order.

## Status lifecycle and evidence

- **Proposed:** decision/integration still awaits scoped acceptance. Implemented
  code or static tests alone do not establish live acceptance.
- **Accepted (lab):** supported by a committed lab receipt, limited to the
  scope recorded below. It does not establish HA, cloud parity or production readiness.
- **Accepted (production):** requires a production receipt and owner sign-off;
  no record currently has this status.
- **Superseded:** a later decision replaces the indicated choice; retain the
  historical text and link its successors. Partial supersession affects only
  the explicitly named part, not identity, cookie or isolation decisions.
- **Constraint:** an additional classification for Module 1 requirement-driven
  selections, with no open comparison between components. It can accompany
  Proposed, Accepted or Superseded.

The pre-existing node approval and verbatim D1–D8 records use **Accepted (owner)**:
this records design authorization, not lab or production execution. These owner
decisions can subsequently receive scoped lab/production receipts. Merging WO-03
records the accepted D1–D8 decisions; the owner confirms the receipt/status mapping.

Historical validation JSON and the hash-frozen node approval/inventory remain
immutable evidence of their original revision, including old ADR paths. The
current SSoT and all Markdown links use this log. The old folder README files
only redirect here; no individual-file stubs remain.

## Decision index and acceptance mapping

| ADR | Status / classification | Acceptance receipt | Evidence scope / pending gates |
| --- | --- | --- | --- |
| [0001: node host mounts under SSoT v2.2](0001-node-host-mounts.md) | Accepted (owner) | None — owner design/static evidence only | 2026-10-05 node exception; no production acceptance |
| [0002: Kubernetes as the orchestration contract](0002-kubernetes.md) | Accepted (lab); Constraint | [wsl-2026-10-07.md](../acceptance/wsl-2026-10-07.md) | K3s local orchestration only; kubeadm/cloud parity pending |
| [0003: Knative Serving for HTTP application revisions](0003-knative-serving.md) | Accepted (lab); Constraint | [wsl-2026-10-07.md](../acceptance/wsl-2026-10-07.md) | CPU demo and activation route; AI/GPU pending |
| [0004: CloudNativePG for PostgreSQL lifecycle and bounded capacity](0004-cloudnativepg.md) | Accepted (lab); Constraint | [wsl-2026-10-07.md](../acceptance/wsl-2026-10-07.md) | TLS, retained data and restart; growth/HA/backups pending |
| [0005: pgvector as the application vector store](0005-pgvector.md) | Accepted (lab); Constraint | [wsl-2026-10-07.md](../acceptance/wsl-2026-10-07.md) | extension/vector query; application RAG pending |
| [0006: Apache APISIX as the external API gateway](0006-apisix.md) | Accepted (lab); Constraint | [wsl-2026-10-07.md](../acceptance/wsl-2026-10-07.md) | local CPU routing; production gateway acceptance pending |
| [0007: Argo CD as the Kubernetes deployment reconciler](0007-argocd.md) | Accepted (lab); Constraint | [wsl-2026-10-07.md](../acceptance/wsl-2026-10-07.md) | reconciliation and controlled drift repair |
| [0008: Tekton for CI and artifact provenance](0008-tekton.md) | Proposed; Constraint | None — owner design/static evidence only | No committed live receipt for this integration; static/reference work is not lab acceptance |
| [0009: Prometheus for metrics and service objectives](0009-prometheus.md) | Accepted (lab); Constraint | [wsl-2026-10-07.md](../acceptance/wsl-2026-10-07.md) | APISIX/CNPG/Knative targets up; durable metrics pending |
| [0010: Grafana for authenticated operational dashboards](0010-grafana.md) | Superseded; Constraint | [wsl-2026-10-07.md](../acceptance/wsl-2026-10-07.md) | Decision superseded; historical text retained |
| [0011: OpenTelemetry for instrumentation and telemetry transport](0011-opentelemetry.md) | Accepted (lab); Constraint | [wsl-2026-10-07.md](../acceptance/wsl-2026-10-07.md) | real span export to debug logs; durable backend pending |
| [0012: OpenBao for secret lifecycle and workload credentials](0012-openbao.md) | Accepted (lab); Constraint | [wsl-2026-10-07.md](../acceptance/wsl-2026-10-07.md) | restricted deployment and init gate only; sealed/uninitialized; leases pending |
| [0013: Keycloak for human identity and OIDC](0013-keycloak.md) | Accepted (lab); Constraint | [vcloud-console-2026-10-08.md](../acceptance/vcloud-console-2026-10-08.md) | portal PKCE/MFA, logout and roleless denial; cluster RBAC pending |
| [0014: Apache Kafka for durable asynchronous events](0014-kafka.md) | Proposed; Constraint | None — owner design/static evidence only | No committed live receipt for this integration; static/reference work is not lab acceptance |
| [0015: Strimzi for Kafka lifecycle on Kubernetes](0015-strimzi.md) | Proposed; Constraint | None — owner design/static evidence only | No committed live receipt for this integration; static/reference work is not lab acceptance |
| [0016: vLLM for private inference and embedding endpoints](0016-vllm.md) | Proposed; Constraint | None — owner design/static evidence only | No committed live receipt for this integration; static/reference work is not lab acceptance |
| [0017: LangChain inside the tenant-aware RAG application](0017-langchain.md) | Proposed; Constraint | None — owner design/static evidence only | No committed live receipt for this integration; static/reference work is not lab acceptance |
| [0018: Spinifex as an infrastructure provider for HPC capacity](0018-spinifex.md) | Superseded; Constraint | None — owner design/static evidence only | Decision superseded; historical text retained |
| [0019: Module 2 configuration ownership, local storage and resource growth](0019-module-2-bootstrap.md) | Proposed | None — owner design/static evidence only | No committed live receipt for this integration; static/reference work is not lab acceptance |
| [0020: trusted main builds and automatic digest promotion](0020-module-3-delivery.md) | Proposed | None — owner design/static evidence only | No committed live receipt for this integration; static/reference work is not lab acceptance |
| [0021: OpenBao dynamic database leases and CSI file delivery](0021-openbao-dynamic-secrets.md) | Proposed | None — owner design/static evidence only | No committed live receipt for this integration; static/reference work is not lab acceptance |
| [0022: Separate Keycloak API and Kubernetes identity contracts](0022-keycloak-gateway-rbac.md) | Proposed | None — owner design/static evidence only | No committed live receipt for this integration; static/reference work is not lab acceptance |
| [0023: Bounded DeepSeek planning and disabled Spinifex GPU bursting](0023-module-5b-hybrid-hpc.md) | Proposed | None — owner design/static evidence only | No committed live receipt for this integration; static/reference work is not lab acceptance |
| [0024: WSL2 lab host-routing compatibility exception](0024-wsl-host-routing.md) | Accepted (lab) | [wsl-2026-10-07.md](../acceptance/wsl-2026-10-07.md) | scoped routing/policy validation; unattended recovery pending |
| [0025: Restricted LocalStack AWS API validation on WSL](0025-localstack-api-lab.md) | Superseded | [localstack-wsl-2026-10-07.md](../acceptance/localstack-wsl-2026-10-07.md) | Decision superseded; historical text retained |
| [0026: Unified vCloud console with gated identity and permissive views](0026-unified-vcloud-console.md) | Accepted (lab); partly superseded by 0035 (read-only only) | [vcloud-console-wsl-2026-10-07.md](../acceptance/vcloud-console-wsl-2026-10-07.md) | backend/reference staging only; public reference OIDC remains gated |
| [0027: Native vCloud portal with isolated realm identity](0027-native-control-plane-portal.md) | Accepted (lab); partly superseded by 0035 (read-only only) | [vcloud-console-2026-10-08.md](../acceptance/vcloud-console-2026-10-08.md) | native portal identity/browser acceptance |
| [0028: Air-Gapped Registry Mirroring and Image Pull Policy Standards](0028-air-gapped-registry.md) | Accepted (owner) | None — owner design/static evidence only | Implementation approval; offline cold-cache/mirror live acceptance pending |
| [0029: vCloud is an AWS-compatible enterprise simulator](0029-aws-compatible-enterprise-simulator.md) | Accepted (owner) | None — owner design/static evidence only | D1-D8 design approved 2026-10-08; implementation/live acceptance not implied |
| [0030: Licence policy, MIT-first](0030-licence-policy.md) | Accepted (owner) | None — owner design/static evidence only | D1-D8 design approved 2026-10-08; implementation/live acceptance not implied |
| [0031: Crossplane as the internal provisioning engine (vCloud Platform API)](0031-crossplane-platform-api.md) | Accepted (owner) | None — owner design/static evidence only | D1-D8 design approved 2026-10-08; implementation/live acceptance not implied |
| [0032: One environment model; the always-on lab moves to an Ubuntu VM](0032-environment-model-and-vm-lab.md) | Accepted (owner) | None — owner design/static evidence only | D1-D8 design approved 2026-10-08; implementation/live acceptance not implied |
| [0033: AWS sandbox account and parity testing](0033-aws-sandbox-and-parity-testing.md) | Accepted (owner) | None — owner design/static evidence only | D1-D8 design approved 2026-10-08; implementation/live acceptance not implied |
| [0034: Observability baseline (Apache-2.0) and managed observability on AWS](0034-observability-baseline.md) | Accepted (owner) | None — owner design/static evidence only | D1-D8 design approved 2026-10-08; implementation/live acceptance not implied |
| [0035: Self-service console through the vCloud API](0035-console-self-service.md) | Accepted (owner) | None — owner design/static evidence only | D1-D8 design approved 2026-10-08; implementation/live acceptance not implied |
| [0036: The product is named Twinfra (formerly vCloud)](0036-product-name-twinfra.md) | Accepted (owner) | None — owner decision 2026-10-09 | [WO-20](../work-orders/WO-20-rename-to-twinfra.md) Stage A branding; repository references and technical identifiers remain staged; no live acceptance implied |
| [0042: Build-time tools and reference-only artifacts (amends ADR-0030)](0042-build-time-tools-and-reference-only-artifacts.md) | Accepted (owner) | None — owner decision 2026-10-09 | WO-02 static licence governance; no live acceptance implied |
| [0043: Time-boxed runtime exceptions for the Module 5a RAG image (amends ADR-0042 decision 4)](0043-module-5a-runtime-exceptions.md) | Accepted (owner) | None — owner decision 2026-10-09 | WO-02 static licence governance; no live acceptance implied |
| [0044: Licence gate scope, SPDX evaluation and the remaining classes (amends ADR-0030, ADR-0042, ADR-0043)](0044-licence-gate-scope-and-classes.md) | Accepted (owner) | None — owner decision 2026-10-09 | WO-02 static licence governance; decision 5 implemented by [WO-25](../work-orders/WO-25-redis-to-valkey.md); live Valkey acceptance pending WO-21 |

ADR numbers **0037–0041** are reserved for other approved work orders.

## Shared contract for every ADR

- Host: Ubuntu **24.04 LTS**, kernel **6.8+**, cgroup v2, containerd with systemd
  cgroups, Cilium eBPF with native routing. Kubernetes minimum **1.30** is a floor,
  not a claim that every newer component supports every release above it.
- Cluster identity: **vCloud-prod-01**; DNS-safe derivative: **vcloud-prod-01**;
  base domain: **vcloud.example.com**; GitOps repository: **amazen33/twinfra**;
  image registry: **registry.vcloud.example.com**.
- Core namespaces: **platform-services**, **workload-apps**, **hpc-compute**.
  Infrastructure is intended for `platform-services`, applications for `workload-apps`,
  and inference/HPC workloads for `hpc-compute`. A release that needs its own system
  namespace requires a recorded placement decision and the same default-deny controls;
  namespace rewriting and upstream chart compatibility are not assumed.
- Default deny applies to ingress **and** egress. Allow only reviewed identities,
  destinations and ports from the topology matrix. Explicit DNS, Kubernetes API,
  health-check and operator/webhook rules are dependencies, not implicit bypasses.
- Application pods run as non-root, drop capabilities, disallow privilege escalation
  and use the restricted Pod Security profile. Persist data through CSI PVCs or vetted
  Local PVs. Ephemeral scratch can use `emptyDir`; application `hostPath` is forbidden.
  The approved kubeadm/Cilium/NVIDIA node exception grants no exception to new operators,
  storage drivers, collectors, image builders or Spinifex hypervisor services.
- Use currently served, non-deprecated APIs and strict `kubeconform` validation on
  **all rendered manifests**. Supply release-matched schemas for CRDs; missing schemas
  fail the gate. An alpha/beta name on a supported CRD is not, by itself, evidence of
  deprecation. Never substitute deprecated Kubernetes APIs such as legacy Ingress APIs.
- Pin every chart/operator/application image and transitive init/sidecar image by
  exact semantic version or digest; prefer digests. Stage OCI images in the canonical
  registry. Pin model revisions and Python dependencies as well. No floating image tags
  or unversioned installation URLs may enter a deployment.
- Preserve the approved Module -1 bootstrap profile. These ADRs do not change its
  Kubernetes/Cilium/NVIDIA pins or its hashed node allowlist. Choose and record compatible
  releases for the new components before generating deployable manifests.
- Use TLS with verified peer identity across trust boundaries and application-layer
  authorization. Network isolation does not itself establish encryption, tenant access
  control, cloud IAM equivalence or production readiness.

## Implementation order and completion gates

1. Record a compatible component version matrix, image digests, CRD schemas, namespace
   placement, CSI class and site routes. Validate manifests and the existing host policy.
2. Establish certificate issuance/trust, OpenBao recovery procedures and narrowly scoped
   service accounts. Bootstrap trust and unseal/recovery material must be provisioned
   outside Git and outside the database that those secrets unlock.
3. Establish PostgreSQL backups and restore drills, Keycloak, Kafka/Strimzi, metrics and
   telemetry. Each service gets limits, disruption policy and failure-domain placement.
4. Configure APISIX and Knative's supported networking adapter; deploy the LangChain
   service and separate vLLM generation/embedding endpoints. Admit only the required flows.
5. Connect Tekton artifact verification to Argo CD reconciliation. Test OIDC failures,
   tenant isolation, streaming, rollback, secret rotation and unavailable dependencies.
6. Implement and prove the Spinifex capacity adapter with explicit quotas, data transfer,
   job ownership and cleanup before enabling automatic bursting.

The topology identifies additional implementation dependencies: certificate automation,
CSI/object storage, a PostgreSQL capacity controller/metrics adapter, a trace backend,
artifact verification, and an HPC admission/capacity adapter. Their names and versions
are not silently selected by this module. Failure/recovery and SLO targets require measured
acceptance criteria before production operation. A single-node bootstrap cannot supply
the failure-domain redundancy specified by these production designs.

## Codex implementation instruction

> Read `vcloud-ssot.yaml`, `docs/adr/0001-node-host-mounts.md`, this index, the selected
> component ADR and `docs/module-1-topology.md` before implementation. Preserve existing
> user-approved constraints. Resolve every release/dependency gate explicitly; create
> manifests only with concrete compatible pins, release-matched CRD schemas and reviewed
> traffic rules. Run strict kubeconform and the applicable host/security policy checks
> before apply. Report static checks separately from live acceptance evidence. Implement
> only the selected task; these documents do not authorize production deployment,
> external messages or additional node privilege exceptions.

Recruiter summary: [copy-ready bullet](../module-1-summary.md).
Local documentation checks: [Module 1 validation evidence](../module-1-validation.json).
These checks cover ADR structure/coverage, local links, SSoT identity, approved node-policy
integrity and Mermaid parsing; they do not establish deployment or live readiness.
