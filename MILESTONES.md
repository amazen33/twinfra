# Twinfra Development Roadmap

Reviewed on **2026-10-07**. Checked items have the scoped evidence linked below;
unchecked items remain planned or blocked. Passing local WSL checks does not
complete production or application acceptance. ISTQB-aligned test practices do
not imply ISTQB certification. All four GitHub release milestones remain open.

## Milestone 1: Local Zero-Trust Runtime & Networking

- [x] Provision the WSL2 K3s foundation and verify its Node, DNS and local network controls on the 20 GiB / six-CPU profile. — **[Flexibility, Reliability]**
- [x] Configure Cilium eBPF deny-all and record DNS, allowed-control HTTP, denied Service/Pod HTTP and matching policy-drop evidence for the lab test pair. — **[Security, Functional suitability]**
- [x] Codify the WSL-only host-routing overlay; validate lab/base Helm renders and CI rejection of production/staging/Argo enablement. — **[Compatibility, Security]**
- [x] Refresh live native/legacy routing, BPF masquerade and effective socket LB status; repeat GitHub fetch, deny-all and ten endpoint gates. — **[Security, Reliability]**
- [x] Reconcile the explicit lab socket LB ConfigMap value through the owned Helm release; validate manual recovery after WSL changed the active routing interface. — **[Compatibility, Reliability]**
- [ ] Validate unattended WSL restart/interface recovery; SPIFFE attestation requires separate deployment/validation. — **[Security, Reliability]**
- [x] Restore the three platform health probes and Windows loopback Core dashboard with Host Firewall enabled; retain the local probe-port exception. — **[Reliability, Interaction capability]**
- [ ] Define and verify scoped host and Windows Firewall guards for required Twinfra traffic; confirm unrelated traffic remains blocked. — **[Security, Reliability]**
- [ ] Retest WSL reboot recovery and complete application readiness before claiming the cluster supports all Twinfra workloads. — **[Reliability, Functional suitability]**

Evidence: [correction review](docs/correction-review.md),
[dated runtime and test record](docs/correction-review-validation.json),
[probe runbook](deploy/network/platform-probes/README.md) and
[Windows service access](docs/service-access.md). The denied lab pair proves
the tested path; it does not establish a complete security audit or restriction
of the three health ports to kubelet traffic alone.

## Milestone 2: Declarative GitOps & Data Layer

- [x] Restore the single-owner Argo CD controller discovery binding in `platform-services`; verify synchronization and recovery from a failed or interrupted sync. — **[Reliability, Functional suitability]**
- [ ] Deploy CloudNativePG with a Local PV bounded to 4 GiB; verify TLS, pgvector, bounded CPU/memory growth and persistence across pod restart and reconciliation. — **[Reliability, Performance efficiency]**
- [ ] Configure Keycloak role-based access control (RBAC) and verify representative authorized and denied access paths. — **[Security, Functional suitability]**
- [ ] Configure least-privilege OpenBao credentials and demonstrate credential rotation and revocation with access checks. — **[Security, Reliability]**

The 2026-10-07 repair restored the discovery binding and missing Git DNS
Deployment; the Application is now `Synced / Healthy`. CNPG PostgreSQL 18.6 with
pgvector 0.8.2 passed verified TLS and retained-data checks across a Pod restart.
Bounded automatic growth under load remains separate acceptance work, so the
full database item stays open. OpenBao is deployed with durable PostgreSQL
storage but remains uninitialized/sealed behind the operator PGP-key gate.

## Milestone: Zero-Trust Streaming & GitOps Core

- [x] FIX: Enforce air-gapped imagePullPolicy: IfNotPresent and containerd path-rewrite rules (Issue #412; ADR-0028).
- [ ] QA: Validate offline cluster bootstrap from cold CRI cache without internet egress.

The checked registry item covers implementation and automated policy, schema,
cache and API-path tests. Live mirror DNS/TLS, authenticated pulls and cold-cache
rollout remain open. Cold-cache QA requires vetted offline image imports or a
reachable internal mirror; no external runtime fallback is enabled. Issue #412
was supplied in the task and does not resolve in this repository at review time;
this entry does not claim a GitHub issue closure. See
[registry ADR-0028](docs/adr/0028-air-gapped-registry.md).

## Milestone 3: Quality Assurance & ISTQB Verification

- [ ] Enforce the `vCloud PR gate` in a reviewed GitHub ruleset; `main` is currently unprotected. — **[Security, Maintainability]**
- [ ] Produce traceable system integration testing (SIT) evidence linking requirements, test cases, results, and defects. — **[Functional suitability, Maintainability]**
- [ ] Conduct an authorized network-security audit, document findings, remediate them, and record retest results. — **[Security, Reliability]**
- [x] Verify Argo CD drift detection and self-healing against a controlled configuration change; record expected and observed outcomes. — **[Reliability, Functional suitability]**
- [ ] Publish a release test record with scope, environment, results, exceptions, and sign-off status. — **[Maintainability, Functional suitability]**

GitHub CI runs the selected candidate and immutable merged PRs #1–#6.
It performs offline validation without cluster credentials. The local
runtime review is recorded separately; neither result replaces full SIT or
release sign-off. See the [CI guide](docs/github-actions-tests.md).

## Milestone 4: Scalability & Public Release

- [ ] Run k6 load, stress, and soak tests; record workload, latency percentiles, errors, thresholds, and outcomes. — **[Performance efficiency, Reliability]**
- [ ] Exercise multi-node expansion and node-loss recovery, recording recovery behavior and service availability. — **[Flexibility, Reliability]**
- [ ] Prepare production runbooks for deployment, operation, troubleshooting, recovery, and security response. — **[Maintainability, Reliability]**
- [ ] Verify the MIT license, third-party notices, and release artifacts are complete and included with the public release. — **[Functional suitability, Maintainability]**

## Local WSL stages M3–M5 (separate from release milestones)

- [x] M3 endpoints: restricted OpenBao/Keycloak, APISIX and Knative CPU demo deployed; APISIX Host route returned HTTP 200 from WSL and Windows.
- [x] M4 observability: APISIX, CNPG and Knative Prometheus targets present/up; real demo span exported by OpenTelemetry; Grafana application health and Keycloak verified TLS/discovery passed.
- [x] M5 local acceptance: ten live gates passed with zero failures, including generated PodSecurity and GPU/Spinifex disabled constraints.
- [ ] OpenBao activation: provide the four operator public keys, execute the PGP-only initialization, then complete operator unseal and secrets-engine acceptance.
- [x] M5 hosted publication: candidate and exact-head GitHub gates passed; `vcloud-wsl-endpoints` Synced/Healthy at the tested revision, followed by zero-failure acceptance.
- [x] Local AWS API extension: restricted LocalStack Community 4.14.0 deployed; S3/EC2/IAM/DynamoDB running, four signed API calls and APISIX ingress returned HTTP 200 from the validated lab; existing ten platform gates passed.
- [x] Local URL recovery: restored port 4566 after forward restart-limit exhaustion, added delayed retries and a health gate, and verified scoped forward-failure recovery; Keycloak discovery HTTP 200 and OpenBao uninitialized status documented. See [recovery acceptance](docs/acceptance/local-url-recovery-2026-10-07.md).
- [x] Local WSL restart recovery: reconciled Cilium with the observed interface, rolled back failed automatic selection, and restored Linux/Windows localhost routing plus owned forwards; ten platform gates, three probes and deny-all passed. See [2026-10-08 receipt](docs/acceptance/wsl-restart-recovery-2026-10-08.md). Unattended reboot recovery remains open.
- [x] Local Keycloak administrator: created `vcloud-admin`, verified password authentication and authorized master-realm administration over validated TLS, removed the temporary recovery account, and verified idempotent rerun without password reset. Private retrieval and operator MFA/password custody remain in the [admin runbook](docs/keycloak-admin-access.md).
- [x] Unified Twinfra console reference: controller-managed prefix routes, MIT navigation/read-only S3 and DynamoDB views, immutable dual-emulator profile and fail-closed OIDC activation gate implemented. See [console runbook](lab/wsl/console/README.md).
- [x] Native unified portal: restricted React/TypeScript + Tailwind Deployment, same-origin APISIX paths, read-only native health/storage/EC2/DynamoDB/GitOps/IAM views, and isolated `vcloud/vcloud-admin` mapped to `console.admin`; temporary password only in encrypted Kubernetes Secret.
- [x] Native portal identity acceptance: validated private TLS backchannel, actual PKCE/MFA login, both emulator reads, desktop/mobile navigation, logout and roleless denial at `localhost:18080/console/`. See [2026-10-08 portal receipt](docs/acceptance/vcloud-console-2026-10-08.md).
- [x] Portal login recovery: fail-closed missing/malformed callback session page, enabled temporary-password required-action provider, complete browser first/returning MFA login and preserved operator credentials; WSL restart repair and deny-all retested. See [login recovery receipt](docs/acceptance/portal-login-recovery-2026-10-08.md).
- [ ] Optional earlier hostname/socket profile: explicitly activate and test `console.vcloud.local:18080` and any real WebSocket backend before claiming those paths work.
- [ ] Spinifex/OpenBao console integration: supply vetted Services/images and base-path/TLS configuration; disabled references do not count as deployed UIs or enable HPC offloading.

Evidence and executable procedures: [local stages runbook](docs/wsl-local-milestones-3-5.md).
The [dated acceptance record](docs/acceptance/wsl-2026-10-07.md) records the final
checks, approved WSL routing workaround and remaining production gates.
The controlled drift test changed only the existing GitOps marker ConfigMap;
Argo restored `managed-by-github`. HTTP 200 and telemetry are local acceptance,
not production release, persistent observability, OIDC authorization or HPC proof.
The [LocalStack acceptance record](docs/acceptance/localstack-wsl-2026-10-07.md)
records the AWS API extension and its separate limitations. No AWS Web Console,
actual EC2 VM provisioning or Spinifex offloading is implied by emulator acceptance.

## ISO/IEC 25010:2023 tag key

Tags refer to product-quality characteristics: **Functional suitability** (required functions), **Performance efficiency** (performance and resource use), **Compatibility** (coexistence and interoperability), **Interaction capability** (user interaction), **Reliability** (consistent operation and recovery), **Security** (protection of systems and data), **Maintainability** (analysis, modification, and testing), **Flexibility** (adaptation, scalability, and installation), and **Safety** (freedom from unacceptable risk).

## WO-21 · Dev environment (cairo-1)

- [x] Static provisioning: shared Module -1 NoCloud seed, Hyper-V planner, checksum guard and offline collision/idempotence tests.
- [x] Dev GitOps profile, neutral reusable helpers and ADR-0047 upstream-name register/check.
- [ ] Owner provisioning and live Ready/deny-all/GitOps/PostgreSQL/PKCE-MFA acceptance.
- [ ] Tester sign-off: [dev receipt](docs/acceptance/dev-environment-2026-10-10.md), Result: Pending.
- [ ] WSL material deletion belongs to WO-28 after Accepted; no WSL retirement mutation in WO-21.

[Owner runbook and production-profile deviations](docs/dev-environment.md).

## WO-29 · Runnable dev profile

- [x] Static 20 GiB sizing, PowerShell 7.4 requirement and 110 GiB disk guard, with offline plan fixtures.
- [x] Dev-only bootstrap/application digest staging and temporary dev CA; gateway HTTPS 9443 through loopback tunnel 18444.
- [x] Generated manifests, inventory equality checks, staging/CA/HTTPS tests and production-render preservation guard.
- [ ] Owner real plan, VM boot/staging, trusted HTTPS login and live platform acceptance.
- [ ] Tester sign-off: [dev receipt](docs/acceptance/dev-environment-2026-10-10.md), Result: Pending.

Staging uses upstream access during preparation; cold-cache offline QA remains
open. No provisioning, software installation, WSL deletion or Cloudflare change
is performed by this work order. See [WO-29](docs/work-orders/WO-29-make-dev-environment-runnable.md).
