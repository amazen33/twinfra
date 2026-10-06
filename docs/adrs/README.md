# Module 1: vCloud architecture decision records

These records specify the requested component choices and their implementation contracts.
Copy an individual Markdown record into a Codex task together with the shared contract
below. **Status: Proposed** refers to the integration design; the component selections
are requirements supplied by the user. No Module 1 component has been deployed or tested
on a live cluster here. The previously approved node exception remains accepted in
[ADR 0001](../adr-0001-node-host-mounts.md).

Date: **2026-10-05**. Deciders: **vCloud platform owner and Principal Architect**.
The authoritative inputs are [SSoT v2.2](../../vcloud-ssot.yaml) and Module 1.
Use the [complete topology and traffic contract](../module-1-topology.md) alongside
these records. Documentation URLs identify sources, not deployable version pins.

## Decision index

| ADR | Component | Responsibility |
| --- | --- | --- |
| [0002](0002-kubernetes.md) | Kubernetes | Scheduling, reconciliation and portability |
| [0003](0003-knative-serving.md) | Knative Serving | HTTP revisions, traffic splitting and CPU service autoscaling |
| [0004](0004-cloudnativepg.md) | CloudNativePG | PostgreSQL lifecycle, replication, failover and capacity policy |
| [0005](0005-pgvector.md) | pgvector | Transactional vector storage and similarity retrieval |
| [0006](0006-apisix.md) | Apache APISIX | External API entry, authentication and traffic controls |
| [0007](0007-argocd.md) | Argo CD | GitOps deployment and drift reconciliation |
| [0008](0008-tekton.md) | Tekton | Build, verification and artifact provenance |
| [0009](0009-prometheus.md) | Prometheus | Metrics, service objectives and alert rules |
| [0010](0010-grafana.md) | Grafana | Authenticated dashboards and cross-signal investigation |
| [0011](0011-opentelemetry.md) | OpenTelemetry | Instrumentation, context propagation and telemetry export |
| [0012](0012-openbao.md) | OpenBao | Secret lifecycle and workload authentication |
| [0013](0013-keycloak.md) | Keycloak | Human identity, OIDC and application roles |
| [0014](0014-kafka.md) | Apache Kafka | Durable asynchronous events and replay |
| [0015](0015-strimzi.md) | Strimzi | Kafka operations through Kubernetes controllers |
| [0016](0016-vllm.md) | vLLM | Private GPU generation and embedding endpoints |
| [0017](0017-langchain.md) | LangChain | Tenant-aware retrieval and prompt orchestration |
| [0018](0018-spinifex.md) | Spinifex | Cloud infrastructure capacity for admitted HPC workloads |

## Shared contract for every ADR

- Host: Ubuntu **24.04 LTS**, kernel **6.8+**, cgroup v2, containerd with systemd
  cgroups, Cilium eBPF with native routing. Kubernetes minimum **1.30** is a floor,
  not a claim that every newer component supports every release above it.
- Cluster identity: **vCloud-prod-01**; DNS-safe derivative: **vcloud-prod-01**;
  base domain: **vcloud.example.com**; GitOps repository: **amazen33/vCloud**;
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

> Read `vcloud-ssot.yaml`, `docs/adr-0001-node-host-mounts.md`, this index, the selected
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
