# vCloud Development Roadmap

Reviewed on **2026-10-07**. Checked items have the scoped evidence linked below;
unchecked items remain planned or blocked. Passing local WSL checks does not
complete production or application acceptance. ISTQB-aligned test practices do
not imply ISTQB certification. All four GitHub release milestones remain open.

## Milestone 1: Local Zero-Trust Runtime & Networking

- [x] Provision the WSL2 K3s foundation and verify its Node, DNS and local network controls on the 20 GiB / six-CPU profile. — **[Flexibility, Reliability]**
- [x] Configure Cilium eBPF deny-all and record DNS, allowed-control HTTP, denied Service/Pod HTTP and matching policy-drop evidence for the lab test pair. — **[Security, Functional suitability]**
- [x] Restore the three platform health probes and Windows loopback Core dashboard with Host Firewall enabled; retain the local probe-port exception. — **[Reliability, Interaction capability]**
- [ ] Define and verify scoped host and Windows Firewall guards for required vCloud traffic; confirm unrelated traffic remains blocked. — **[Security, Reliability]**
- [ ] Retest WSL reboot recovery and complete application readiness before claiming the cluster supports all vCloud workloads. — **[Reliability, Functional suitability]**

Evidence: [correction review](docs/correction-review.md),
[dated runtime and test record](docs/correction-review-validation.json),
[probe runbook](deploy/network/platform-probes/README.md) and
[Windows service access](docs/service-access.md). The denied lab pair proves
the tested path; it does not establish a complete security audit or restriction
of the three health ports to kubelet traffic alone.

## Milestone 2: Declarative GitOps & Data Layer

- [ ] Restore the single-owner Argo CD controller discovery binding in `platform-services`; verify synchronization and recovery from a failed or interrupted sync. — **[Reliability, Functional suitability]**
- [ ] Deploy CloudNativePG with a Local PV bounded to 4 GiB; verify TLS, pgvector, bounded CPU/memory growth and persistence across pod restart and reconciliation. — **[Reliability, Performance efficiency]**
- [ ] Configure Keycloak role-based access control (RBAC) and verify representative authorized and denied access paths. — **[Security, Functional suitability]**
- [ ] Configure least-privilege OpenBao credentials and demonstrate credential rotation and revocation with access checks. — **[Security, Reliability]**

The current Application is `Healthy / Unknown` with a discovery `ComparisonError`;
the stale binding targets `argocd`. No CNPG Cluster or PVC is initialized. These
items remain open even though the controller/operator health probes pass.

## Milestone: Zero-Trust Streaming & GitOps Core

- [x] FIX: Enforce air-gapped imagePullPolicy: IfNotPresent and containerd path-rewrite rules (Issue #412).
- [ ] QA: Validate offline cluster bootstrap from cold CRI cache without internet egress.

The checked registry item covers implementation and automated policy, schema,
cache and API-path tests. Live mirror DNS/TLS, authenticated pulls and cold-cache
rollout remain open. Cold-cache QA requires vetted offline image imports or a
reachable internal mirror; no external runtime fallback is enabled. Issue #412
was supplied in the task and does not resolve in this repository at review time;
this entry does not claim a GitHub issue closure. See
[registry ADR-0020](docs/architecture/adr/ADR-0020-air-gapped-registry.md).

## Milestone 3: Quality Assurance & ISTQB Verification

- [ ] Enforce the `vCloud PR gate` in a reviewed GitHub ruleset; `main` is currently unprotected. — **[Security, Maintainability]**
- [ ] Produce traceable system integration testing (SIT) evidence linking requirements, test cases, results, and defects. — **[Functional suitability, Maintainability]**
- [ ] Conduct an authorized network-security audit, document findings, remediate them, and record retest results. — **[Security, Reliability]**
- [ ] Verify Argo CD drift detection and self-healing against a controlled configuration change; record expected and observed outcomes. — **[Reliability, Functional suitability]**
- [ ] Publish a release test record with scope, environment, results, exceptions, and sign-off status. — **[Maintainability, Functional suitability]**

GitHub CI runs the selected candidate and immutable merged PRs #1–#3, #5 and
#6. It performs offline validation without cluster credentials. The local
runtime review is recorded separately; neither result replaces full SIT or
release sign-off. See the [CI guide](docs/github-actions-tests.md).

## Milestone 4: Scalability & Public Release

- [ ] Run k6 load, stress, and soak tests; record workload, latency percentiles, errors, thresholds, and outcomes. — **[Performance efficiency, Reliability]**
- [ ] Exercise multi-node expansion and node-loss recovery, recording recovery behavior and service availability. — **[Flexibility, Reliability]**
- [ ] Prepare production runbooks for deployment, operation, troubleshooting, recovery, and security response. — **[Maintainability, Reliability]**
- [ ] Verify the MIT license, third-party notices, and release artifacts are complete and included with the public release. — **[Functional suitability, Maintainability]**

## ISO/IEC 25010:2023 tag key

Tags refer to product-quality characteristics: **Functional suitability** (required functions), **Performance efficiency** (performance and resource use), **Compatibility** (coexistence and interoperability), **Interaction capability** (user interaction), **Reliability** (consistent operation and recovery), **Security** (protection of systems and data), **Maintainability** (analysis, modification, and testing), **Flexibility** (adaptation, scalability, and installation), and **Safety** (freedom from unacceptable risk).
