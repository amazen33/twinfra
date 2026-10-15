# Twinfra architecture decision log

This is the single ADR log. The next free number is **0054**.
The [work-order handoff](../work-orders/README.md) controls implementation order.
The current status is recorded in this index; individual decision texts and
their original status headers remain historical snapshots of their decisions.

## Status lifecycle and evidence

[ADR-0052](0052-evidence-first-foundation-1-0.md) defines exactly one current status per ADR:

- **Proposed:** a design not yet decided.
- **Accepted (design):** owner-approved; live tester acceptance is not established.
- **Dev-verified:** live on cairo-1, with an Accepted tester receipt.
- **Production-accepted:** live production evidence and Accepted tester receipt; none today.
- **Deferred (reference design):** off the roadmap until a new owner decision.
- **Superseded:** replaced by the named successor; original text is retained.

Constraint remains a classification of Module 1 requirement-driven choices,
not an additional lifecycle status. Partial supersession affects only its named
scope. Retired WSL evidence is **Historical (retired environment)** and cannot
establish current acceptance. Static checks, owner-reported observations and
Pending tester receipts also cannot establish Dev-verified status.

No current receipt has Accepted tester sign-off. The WO-31 bootstrap and
24-hour soak observations, WO-36 network evidence and WO-36a disposable-VM proof
are linked below with their Pending outcomes. The soak has no completed verdict.
Historical validation JSON and the hash-frozen node approval/inventory remain
immutable evidence of their original revisions, including old paths.

## Decision index and acceptance mapping

| ADR | Status | Acceptance receipt | Evidence scope / pending gates |
| --- | --- | --- | --- |
| [0001: node host mounts under SSoT v2.2](0001-node-host-mounts.md) | Accepted (design) | None — owner design/static evidence only; [WO-31 bootstrap/platform/soak observations](../acceptance/dev-environment-2026-10-13.md) (tester Pending; soak Pending) | 2026-10-05 node exception; no production acceptance |
| [0002: Kubernetes as the orchestration contract](0002-kubernetes.md) | Accepted (design) | [Historical (retired environment)](../acceptance/wsl-2026-10-07.md); [WO-31 bootstrap/platform/soak observations](../acceptance/dev-environment-2026-10-13.md) (tester Pending; soak Pending); [WO-36 network](../acceptance/host-network-2026-10-15.md) / [WO-36a VM proof](../acceptance/host-network-fix-2026-10-15.md) (tester Pending; Dell acceptance Pending) | Constraint. K3s local orchestration only; kubeadm/cloud parity pending |
| [0003: Knative Serving for HTTP application revisions](0003-knative-serving.md) | Accepted (design) | [Historical (retired environment)](../acceptance/wsl-2026-10-07.md) | Constraint. CPU demo and activation route; AI/GPU pending |
| [0004: CloudNativePG for PostgreSQL lifecycle and bounded capacity](0004-cloudnativepg.md) | Accepted (design) | [Historical (retired environment)](../acceptance/wsl-2026-10-07.md); [WO-31 bootstrap/platform/soak observations](../acceptance/dev-environment-2026-10-13.md) (tester Pending; soak Pending) | Constraint. TLS, retained data and restart; growth/HA/backups pending |
| [0005: pgvector as the application vector store](0005-pgvector.md) | Accepted (design) | [Historical (retired environment)](../acceptance/wsl-2026-10-07.md); [WO-31 bootstrap/platform/soak observations](../acceptance/dev-environment-2026-10-13.md) (tester Pending; soak Pending) | Constraint. extension/vector query; application RAG pending |
| [0006: Apache APISIX as the external API gateway](0006-apisix.md) | Accepted (design) | [Historical (retired environment)](../acceptance/wsl-2026-10-07.md); [WO-31 bootstrap/platform/soak observations](../acceptance/dev-environment-2026-10-13.md) (tester Pending; soak Pending) | Constraint. local CPU routing; production gateway acceptance pending |
| [0007: Argo CD as the Kubernetes deployment reconciler](0007-argocd.md) | Accepted (design) | [Historical (retired environment)](../acceptance/wsl-2026-10-07.md); [WO-31 bootstrap/platform/soak observations](../acceptance/dev-environment-2026-10-13.md) (tester Pending; soak Pending) | Constraint. reconciliation and controlled drift repair |
| [0008: Tekton for CI and artifact provenance](0008-tekton.md) | Superseded | None — owner design/static evidence only | Constraint. Superseded by [ADR-0052 decision 5](0052-evidence-first-foundation-1-0.md): GitHub Actions + GHCR + signed provenance verified before deploy; implementation/acceptance pending |
| [0009: Prometheus for metrics and service objectives](0009-prometheus.md) | Accepted (design) | [Historical (retired environment)](../acceptance/wsl-2026-10-07.md) | Constraint. APISIX/CNPG/Knative targets up; durable metrics pending |
| [0010: Grafana for authenticated operational dashboards](0010-grafana.md) | Superseded | [Historical (retired environment)](../acceptance/wsl-2026-10-07.md) | Constraint. Superseded by [ADR-0034](0034-observability-baseline.md); historical text retained |
| [0011: OpenTelemetry for instrumentation and telemetry transport](0011-opentelemetry.md) | Accepted (design) | [Historical (retired environment)](../acceptance/wsl-2026-10-07.md) | Constraint. real span export to debug logs; durable backend pending |
| [0012: OpenBao for secret lifecycle and workload credentials](0012-openbao.md) | Accepted (design) | [Historical (retired environment)](../acceptance/wsl-2026-10-07.md) | Constraint. restricted deployment and init gate only; sealed/uninitialized; leases pending |
| [0013: Keycloak for human identity and OIDC](0013-keycloak.md) | Accepted (design) | [Historical (retired environment)](../acceptance/vcloud-console-2026-10-08.md); [WO-31 bootstrap/platform/soak observations](../acceptance/dev-environment-2026-10-13.md) (tester Pending; soak Pending) | Constraint. portal PKCE/MFA, logout and roleless denial; cluster RBAC pending |
| [0014: Apache Kafka for durable asynchronous events](0014-kafka.md) | Deferred (reference design) | None — owner design/static evidence only | Constraint. Off roadmap under [ADR-0052](0052-evidence-first-foundation-1-0.md); new owner decision required; Modules 5a/5b remain disabled |
| [0015: Strimzi for Kafka lifecycle on Kubernetes](0015-strimzi.md) | Deferred (reference design) | None — owner design/static evidence only | Constraint. Off roadmap under [ADR-0052](0052-evidence-first-foundation-1-0.md); new owner decision required; Modules 5a/5b remain disabled |
| [0016: vLLM for private inference and embedding endpoints](0016-vllm.md) | Deferred (reference design) | None — owner design/static evidence only | Constraint. Off roadmap under [ADR-0052](0052-evidence-first-foundation-1-0.md); new owner decision required; Modules 5a/5b remain disabled |
| [0017: LangChain inside the tenant-aware RAG application](0017-langchain.md) | Deferred (reference design) | None — owner design/static evidence only | Constraint. Off roadmap under [ADR-0052](0052-evidence-first-foundation-1-0.md); new owner decision required; Modules 5a/5b remain disabled |
| [0018: Spinifex as an infrastructure provider for HPC capacity](0018-spinifex.md) | Superseded | None — owner design/static evidence only | Constraint. Superseded by [ADR-0029](0029-aws-compatible-enterprise-simulator.md); historical text retained |
| [0019: Module 2 configuration ownership, local storage and resource growth](0019-module-2-bootstrap.md) | Proposed | None — owner design/static evidence only | No committed live receipt for this integration; static/reference work is not lab acceptance |
| [0020: trusted main builds and automatic digest promotion](0020-module-3-delivery.md) | Superseded | None — owner design/static evidence only | Superseded by [ADR-0052 decision 5](0052-evidence-first-foundation-1-0.md): GitHub Actions + GHCR + signed provenance verified before deploy; implementation/acceptance pending |
| [0021: OpenBao dynamic database leases and CSI file delivery](0021-openbao-dynamic-secrets.md) | Proposed | None — owner design/static evidence only | No committed live receipt for this integration; static/reference work is not lab acceptance |
| [0022: Separate Keycloak API and Kubernetes identity contracts](0022-keycloak-gateway-rbac.md) | Proposed | None — owner design/static evidence only | No committed live receipt for this integration; static/reference work is not lab acceptance |
| [0023: Bounded DeepSeek planning and disabled Spinifex GPU bursting](0023-module-5b-hybrid-hpc.md) | Deferred (reference design) | None — owner design/static evidence only | Off roadmap under [ADR-0052](0052-evidence-first-foundation-1-0.md); new owner decision required; Modules 5a/5b remain disabled |
| [0024: WSL2 lab host-routing compatibility exception](0024-wsl-host-routing.md) | Accepted (design) | [Historical (retired environment)](../acceptance/wsl-2026-10-07.md); [WO-36 network](../acceptance/host-network-2026-10-15.md) / [WO-36a VM proof](../acceptance/host-network-fix-2026-10-15.md) (tester Pending; Dell acceptance Pending) | scoped routing/policy validation; unattended recovery pending |
| [0025: Restricted LocalStack AWS API validation on WSL](0025-localstack-api-lab.md) | Superseded | [Historical (retired environment)](../acceptance/localstack-wsl-2026-10-07.md) | Superseded by [ADR-0030](0030-licence-policy.md); historical text retained |
| [0026: Unified vCloud console with gated identity and permissive views](0026-unified-vcloud-console.md) | Accepted (design) | [Historical (retired environment)](../acceptance/vcloud-console-wsl-2026-10-07.md); [WO-31 bootstrap/platform/soak observations](../acceptance/dev-environment-2026-10-13.md) (tester Pending; soak Pending) | backend/reference staging only; public reference OIDC remains gated; [ADR-0035](0035-console-self-service.md) supersedes the read-only decision only |
| [0027: Native vCloud portal with isolated realm identity](0027-native-control-plane-portal.md) | Accepted (design) | [Historical (retired environment)](../acceptance/vcloud-console-2026-10-08.md); [WO-31 bootstrap/platform/soak observations](../acceptance/dev-environment-2026-10-13.md) (tester Pending; soak Pending) | native portal identity/browser acceptance; [ADR-0035](0035-console-self-service.md) supersedes the read-only decision only |
| [0028: Air-Gapped Registry Mirroring and Image Pull Policy Standards](0028-air-gapped-registry.md) | Accepted (design) | None — owner design/static evidence only; [WO-31 bootstrap/platform/soak observations](../acceptance/dev-environment-2026-10-13.md) (tester Pending; soak Pending) | Implementation approval; offline cold-cache/mirror live acceptance pending |
| [0029: vCloud is an AWS-compatible enterprise simulator](0029-aws-compatible-enterprise-simulator.md) | Accepted (design) | None — owner design/static evidence only | D1-D8 design approved 2026-10-08; implementation/live acceptance not implied |
| [0030: Licence policy, MIT-first](0030-licence-policy.md) | Accepted (design) | None — owner design/static evidence only | D1-D8 design approved 2026-10-08; implementation/live acceptance not implied |
| [0031: Crossplane as the internal provisioning engine (vCloud Platform API)](0031-crossplane-platform-api.md) | Accepted (design) | None — owner design/static evidence only | D1-D8 design approved 2026-10-08; implementation/live acceptance not implied |
| [0032: One environment model; the always-on lab moves to an Ubuntu VM](0032-environment-model-and-vm-lab.md) | Accepted (design) | None — owner design/static evidence only; [WO-31 bootstrap/platform/soak observations](../acceptance/dev-environment-2026-10-13.md) (tester Pending; soak Pending); [WO-36 network](../acceptance/host-network-2026-10-15.md) / [WO-36a VM proof](../acceptance/host-network-fix-2026-10-15.md) (tester Pending; Dell acceptance Pending) | D1-D8 design approved 2026-10-08; implementation/live acceptance not implied |
| [0033: AWS sandbox account and parity testing](0033-aws-sandbox-and-parity-testing.md) | Accepted (design) | None — owner design/static evidence only | D1-D8 design approved 2026-10-08; implementation/live acceptance not implied |
| [0034: Observability baseline (Apache-2.0) and managed observability on AWS](0034-observability-baseline.md) | Accepted (design) | None — owner design/static evidence only | D1-D8 design approved 2026-10-08; implementation/live acceptance not implied |
| [0035: Self-service console through the vCloud API](0035-console-self-service.md) | Accepted (design) | None — owner design/static evidence only | D1-D8 design approved 2026-10-08; implementation/live acceptance not implied |
| [0036: The product is named Twinfra (formerly vCloud)](0036-product-name-twinfra.md) | Accepted (design) | None — owner decision 2026-10-09 | Owner design decision; technical identifiers remain literal implementation contracts; no live acceptance implied |
| [0038: environment-neutral names](0038-naming-and-environment-labels.md) | Accepted (design) | None; [WO-31 bootstrap/platform/soak observations](../acceptance/dev-environment-2026-10-13.md) (tester Pending; soak Pending); [WO-36 network](../acceptance/host-network-2026-10-15.md) / [WO-36a VM proof](../acceptance/host-network-fix-2026-10-15.md) (tester Pending; Dell acceptance Pending) | WO-21 rebuild; live acceptance Pending |
| [0042: Build-time tools and reference-only artifacts (amends ADR-0030)](0042-build-time-tools-and-reference-only-artifacts.md) | Accepted (design) | None — owner decision 2026-10-09 | WO-02 static licence governance; no live acceptance implied |
| [0043: Time-boxed runtime exceptions for the Module 5a RAG image (amends ADR-0042 decision 4)](0043-module-5a-runtime-exceptions.md) | Accepted (design) | None — owner decision 2026-10-09 | WO-02 static licence governance; no live acceptance implied |
| [0044: Licence gate scope, SPDX evaluation and the remaining classes (amends ADR-0030, ADR-0042, ADR-0043)](0044-licence-gate-scope-and-classes.md) | Accepted (design) | None — owner decision 2026-10-09 | Static licence governance; [WO-25](../work-orders/WO-25-redis-to-valkey.md) replacement implemented; [Valkey live acceptance](../acceptance/valkey-2026-10-09.md) Pending |
| [0045: WSL retirement](0045-wsl-retirement.md) | Accepted (design) | None; [WO-36 network](../acceptance/host-network-2026-10-15.md) / [WO-36a VM proof](../acceptance/host-network-fix-2026-10-15.md) (tester Pending; Dell acceptance Pending) | WO-28 gated on dev acceptance |
| [0046: environment and region names](0046-naming-dev-environment-and-regions.md) | Accepted (design) | None; [WO-31 bootstrap/platform/soak observations](../acceptance/dev-environment-2026-10-13.md) (tester Pending; soak Pending); [WO-36 network](../acceptance/host-network-2026-10-15.md) / [WO-36a VM proof](../acceptance/host-network-fix-2026-10-15.md) (tester Pending; Dell acceptance Pending) | VM, contexts and conformance names |
| [0047: upstream-owned names](0047-upstream-owned-resource-names.md) | Accepted (design) | None; [WO-31 bootstrap/platform/soak observations](../acceptance/dev-environment-2026-10-13.md) (tester Pending; soak Pending) | WO-21 static naming inventory; live acceptance Pending |
| [0048: cairo-1 on a dedicated bare-metal host](0048-cairo-1-on-bare-metal-host.md) | Accepted (design) | None; [WO-31 bootstrap/platform/soak observations](../acceptance/dev-environment-2026-10-13.md) (tester Pending; soak Pending); [WO-36 network](../acceptance/host-network-2026-10-15.md) / [WO-36a VM proof](../acceptance/host-network-fix-2026-10-15.md) (tester Pending; Dell acceptance Pending) | Amends 0032 and 0046; Dell primary, laptop operator/cairo-2 cold standby; [WO-31](../work-orders/WO-31-bare-metal-cairo-1.md); live acceptance Pending |
| [0049: supply-chain vulnerability scanning](0049-supply-chain-vulnerability-scanning.md) | Accepted (design) | [WO-32 static evidence](../acceptance/supply-chain-2026-10-14.md) (tester Pending) | [WO-32](../work-orders/WO-32-supply-chain-scanning.md); pinned scanners, PR gate and scheduled reporting; after-merge issue acceptance Pending |
| [0050: Make `cairo-1` multi-node ready before EdgePulse (HA when nodes arrive)](0050-cairo-1-high-availability.md) | Accepted (design) | None — no Accepted live receipt | WO-33 readiness and WO-33b later join/HA acceptance; one node today |
| [0051: Real DNS names under `twinfra.amazen33.dev`](0051-real-dns-zone-twinfra-amazen33-dev.md) | Accepted (design) | None — no Accepted live receipt | Owner DNS and WO-33 certificate work; no DNS change or public UI exposure in this work order |
| [0052: Evidence first — the evidence model and the Foundation 1.0 gate](0052-evidence-first-foundation-1-0.md) | Accepted (design) | None — no Accepted live receipt | Foundation 1.0 evidence gate; decision 5 supersedes ADR-0008/0020; provenance verification not yet implemented |
| [0053: Tenancy model — AWS-style accounts and IAM map to tenants](0053-tenancy-model-accounts-and-iam.md) | Proposed | None — no Accepted live receipt | Design only; tenancy implementation and cross-account denial matrix await Foundation 1.0 and WO-22/Wave 2 |

ADR numbers **0037** and **0039–0041** are reserved for other approved work orders.

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

[Foundation 1.0](0052-evidence-first-foundation-1-0.md) is the current gate:
host/network, backups/PITR, size-one availability and soak, secrets, identity,
observability, policy, supply-chain verification and current acceptance evidence.
No new product feature is authorized before its acceptance. The historical
Module 1 topology remains a design reference, including deferred Kafka, AI and
HPC flows; it is not a description of deployed capability. Multi-node readiness
and later HA follow [ADR-0050](0050-cairo-1-high-availability.md), with WO-09
backups preceding API endpoint changes. There is no HA or production claim.

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
