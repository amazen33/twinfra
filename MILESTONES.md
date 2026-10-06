# vCloud (pCloudx) Development Roadmap

Checklist items below are planned work, not claims of completed implementation or verification. Tests aligned with ISTQB practices provide verification evidence; they do not imply ISTQB certification.

## Milestone 1: Local Zero-Trust Runtime & Networking

- [ ] Provision a WSL2-hosted K3s node and verify the cluster is ready for the vCloud workloads. — **[Flexibility, Reliability]**
- [ ] Configure Cilium eBPF deny-all network policy and capture explicit allowed- and denied-traffic probe results. — **[Security, Functional suitability]**
- [ ] Define and verify scoped host and Windows Firewall guards for required vCloud traffic; confirm unrelated traffic remains blocked. — **[Security, Reliability]**

## Milestone 2: Declarative GitOps & Data Layer

- [ ] Verify Argo CD repo-server synchronization, then exercise and record recovery from a failed or interrupted sync. — **[Reliability, Functional suitability]**
- [ ] Deploy CloudNativePG with a Local PV bounded to 4 GiB and verify data persists across pod restart and reconciliation. — **[Reliability, Performance efficiency]**
- [ ] Configure Keycloak role-based access control (RBAC) and verify representative authorized and denied access paths. — **[Security, Functional suitability]**
- [ ] Configure least-privilege OpenBao credentials and demonstrate credential rotation and revocation with access checks. — **[Security, Reliability]**

## Milestone 3: Quality Assurance & ISTQB Verification

- [ ] Produce traceable system integration testing (SIT) evidence linking requirements, test cases, results, and defects. — **[Functional suitability, Maintainability]**
- [ ] Conduct an authorized network-security audit, document findings, remediate them, and record retest results. — **[Security, Reliability]**
- [ ] Verify Argo CD drift detection and self-healing against a controlled configuration change; record expected and observed outcomes. — **[Reliability, Functional suitability]**
- [ ] Publish a release test record with scope, environment, results, exceptions, and sign-off status. — **[Maintainability, Functional suitability]**

## Milestone 4: Scalability & Public Release

- [ ] Run k6 load, stress, and soak tests; record workload, latency percentiles, errors, thresholds, and outcomes. — **[Performance efficiency, Reliability]**
- [ ] Exercise multi-node expansion and node-loss recovery, recording recovery behavior and service availability. — **[Flexibility, Reliability]**
- [ ] Prepare production runbooks for deployment, operation, troubleshooting, recovery, and security response. — **[Maintainability, Reliability]**
- [ ] Verify the MIT license, third-party notices, and release artifacts are complete and included with the public release. — **[Functional suitability, Maintainability]**

## ISO/IEC 25010:2023 tag key

Tags refer to product-quality characteristics: **Functional suitability** (required functions), **Performance efficiency** (performance and resource use), **Compatibility** (coexistence and interoperability), **Interaction capability** (user interaction), **Reliability** (consistent operation and recovery), **Security** (protection of systems and data), **Maintainability** (analysis, modification, and testing), **Flexibility** (adaptation, scalability, and installation), and **Safety** (freedom from unacceptable risk).
