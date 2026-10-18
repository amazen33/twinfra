# Changelog

All notable changes to this project are documented here.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and versions follow [Semantic Versioning](https://semver.org/spec/v2.0.0.html).
See [RELEASING.md](RELEASING.md) for the release streams. Twinfra has no earlier releases or tags.

## [Unreleased]

### Changed

- WO-40b: draft v0.1.0 release notes, compatibility and exception disclosure;
  run the vCloud PR gate on release branches and align readiness/capabilities
  with Accepted receipts. Reword only WO-04's static-scope line to distinguish
  it from the current signed live evidence. No runtime, tag or release change.

## [0.1.0]

**Draft; no release date or tag.** Single-node dev use only. The rc window and
consolidated tester acceptance remain Pending. See the
[release notes](docs/release-notes/0.1.0.md) for actual running versions,
installation/update procedures and the path to 0.2.0.

The changes below were drafted from [Unreleased]; their original per-change
Pending/static statements describe when each change landed. Current signed
scope is in the [capability statement](docs/capabilities.md).

### Changed

- Record the tester sign-off (Accepted, 2026-10-18) for WO-04 (console token verification) and
  WO-06 (LocalStack removal) on `twinfra-dev-cairo-1`.

- Record the tester sign-off (Accepted, 2026-10-18) for WO-31 on `twinfra-dev-cairo-1`: all
  live gates verified, the Amendment 15 remediation confirmed and a 12-hour soak by owner decision.

- WO-31 Amendment 15: owned, reversible nouveau/nvidiafb display-driver blacklist
  and running-kernel initramfs verification, gated dev bootstrap integration and
  count-only kernel health checks. Reboot and fresh soak remain owner actions.

- Record the tester sign-off (Accepted, 2026-10-17) for WO-25 (Valkey cache) and the
  WO-34 P2 live part (etcd 3.6.15, CoreDNS 1.14.7) on `twinfra-dev-cairo-1`.

- Record the WO-40a v0.1.0 baseline acceptance evidence for `twinfra-dev-cairo-1`
  (2026-10-17, commit a89de0a, status passed with the owner-authorized restart).
  The tester sign-off stays Pending; the template is unchanged.

- WO-40e: query every Ready replica for component-version consensus; record
  sanitized version failures while continuing the requested restart and final
  checks. Reports retain parsed versions only, never raw probe output.

- WO-40d: accept locked runtime digests without resolving expired import names;
  report failed CRI lookups as sanitized deployed-image problems. Emit sorted
  kubeadm YAML in maintenance ConfigMap replacements and rollback patches so
  host identity checks continue to read the cluster name and API endpoint.

- Add the owner-run WO-40a dev acceptance suite, sanitized receipt fragments and
  consolidated Pending receipt; reflect only the signed WO-36/36a network scope
  as Dev-verified. Fail exception expiry within 7 days and warn within 21 days.
  Release workflow, VERSION, image pins and deployed manifests are unchanged.

- Record the tester sign-off (Accepted, 2026-10-16) for the WO-36 and WO-36a host-network receipts: the first Dev-verified item on `twinfra-dev-cairo-1`.
### Added

- WO-40c: pinned-kubeadm default normalisation before the strict two-tag
  comparison, exact-candidate validation and image-only etcd preview; canonical
  staged CoreDNS tag, bounded API recovery and explicit root kubeconfig. Add
  owner-only backup/rollback/cleanup and WAL p99 < 10 ms verification against
  the 4 ms baseline. No lock, acceptance-suite or live receipt changes.

- WO-09a: standalone licence ladder, enterprise qualification and dated legacy
  backfill, plus package/fix-version toolchain-wave exception review. Existing
  component pins and active vulnerability exceptions are unchanged.

### Removed

- Remove Grafana deployment inputs and its pending-removal licence entry (WO-07a). Keep the two ported dashboard definitions as plain data for WO-10; no Perses deployment.

### Security

- Record two owner-approved, per-CVE interim Argo CD 3.5.3 exceptions through
  2026-11-02 (WO-34e / WO-40 Amendment 1); preserve all other risk clocks and
  require the scheduled 3.5.5 remediation. No image or live configuration changes.

- Fix IPv4 DNS confirmation, adopt the exact owner-recovered legacy static
  profile, and refuse network transactions without a fallback retaining `.3`.
  Prove apply/refusal/rollback with real Ubuntu netplan in CI; document the
  owner-only Intel AMT address and isolation procedure (WO-36 Amendment 1).

- Add an owned, rollback-protected static network transaction for the Dell dev
  host, since-boot network/restart warnings, safe stateless rolling updates and
  a lightweight image-staging attestation gate (WO-36). Live acceptance is Pending.

- Promote dev CoreDNS to 1.14.7 and etcd to 3.6.15-0 with pinned digests,
  close 16 fixed Critical exceptions and carry six approvals without extending
  their expiry; preserve component/package/vulnerability age across image changes (WO-34 3a).

- Run WO-34 console reproduction and complete image comparisons only in the
  paths-filtered WO-34 workflow; unrelated PRs retain changed-input supply-chain
  validation without rebuilding the console or forcing an image inventory rescan.
- Align the dev CRI sandbox with kubeadm’s already pinned pause 3.10.2,
  preserving production and retained WSL bytes; report MiniStack 1.5.18 as blocked
  by its unchanged Critical/High findings after complete comparison (WO-34 P3).
  Run P3 comparisons and their artifacts in the paths-filtered WO-34 workflow;
  keep the required PR gate targeting main without image rebuild steps.

- Refresh the console to CPython 3.14.8 and a reproducible Twinfra image; eliminate
  23 fixable Critical and 118 fixable High findings, close 23 superseded exceptions,
  and add pinned Go binary triage with complete before/after image evidence (WO-34 P1).

### Added

- Record the owner's 2026-10-15/16 host-network check, router-cycle recovery,
  platform health and required staging-check evidence; retain Pending tester
  sign-off and distinguish carrier downtime from netplan transaction gaps.

- Publish the evidence-first capability statement and ADR-0050–0053; downgrade
  retired WSL acceptance, defer AI/HPC/event references and enforce Accepted
  tester receipts for live capability claims in CI (WO-37).

- Release streams (Dev, Candidate, Stable): `RELEASING.md`, this changelog, `VERSION`
  (next release: 0.1.0), `compatibility.yaml`, the `release-checks` and `release` workflows
  (releases attach the image locks and the licence register), and the rulesets in
  `.github/rulesets/`.

### Known limitations

- One bare-metal dev node, one failure domain; no production profile or HA.
- AWS-compatible **emulated read subset** only: MiniStack S3 bucket/object lists,
  EC2 DescribeInstances and DynamoDB ListTables/DescribeTable. Persistence is disabled;
  no real compute/storage provisioning or AWS parity.
- No accepted backups/PITR/DR, multi-tenancy, secrets management, durable
  observability retention, compliance or Foundation 1.0.
- OpenBao 2.7.1 is deployed; initialization, unseal and dynamic leases are not
  claimed. PostgreSQL 18.6 runs, but pgvector extension activation is separate.
- WO-31 accepts a 12-hour dev soak by explicit owner decision; neither the
  original 24-hour target nor the 48-hour rc window is thereby completed.
  The subsequent eno1 link-flap warning remains tracked separately.
- Valkey and MiniStack image SBOM/notice reviews remain due 2027-01-07.
- Security exceptions below are time-bounded risk acceptance, not remediation.
  Argo CD 3.5.3 is the evidenced baseline, not the planned 3.5.5 promotion.

### Exception table

Snapshot of [the active vulnerability policy](security/vulnerability-exceptions.json)
at the WO-40b base on 2026-10-18: 62 entries (61 Critical,
1 High), approved by GitHub `amazen33`. This is a disclosure,
not a fresh vulnerability scan or an extension of any expiry. The
[baseline calendar](docs/acceptance/release-0.1.0-2026-10-17.md#exception-calendar)
recorded two Argo CD warnings. The interim Argo CD entries expire 2026-11-02;
the other 60 entries expire 2026-11-12. WO-40 Amendment 1 requires the Argo CD
promotion and exception renewal before the release cut; re-evaluate with fresh
scan data and the acceptance calendar (fail expired/<=7 days, warn <=21 days).
Do not cut a release on the strength of this dated table alone.

| Severity | Image / immutable target | Package / version | CVE | Expires |
| --- | --- | --- | --- | --- |
| High | `quay.io/argoproj/argocd@sha256:dd3f47d5a5e4da563a7a398506e892481b358a7cec50abdf320c71aa55904bfa` | `github.com/argoproj/argo-cd/v3 v3.5.3+dirty` | CVE-2026-55797 | 2026-11-02 |
| Critical | `quay.io/argoproj/argocd@sha256:dd3f47d5a5e4da563a7a398506e892481b358a7cec50abdf320c71aa55904bfa` | `github.com/argoproj/argo-cd/v3 v3.5.3+dirty` | CVE-2026-77459 | 2026-11-02 |
| Critical | `docker.io/apache/apisix@sha256:9a7e45dc943fbf10ec916d1232bae4cda9302ae28a4696cfb83c2da01d261141` | `perl-base 5.36.0-7+deb12u3` | CVE-2026-12087 | 2026-11-12 |
| Critical | `docker.io/apache/apisix@sha256:9a7e45dc943fbf10ec916d1232bae4cda9302ae28a4696cfb83c2da01d261141` | `perl-base 5.36.0-7+deb12u3` | CVE-2026-13221 | 2026-11-12 |
| Critical | `docker.io/apache/apisix@sha256:9a7e45dc943fbf10ec916d1232bae4cda9302ae28a4696cfb83c2da01d261141` | `perl-base 5.36.0-7+deb12u3` | CVE-2026-42496 | 2026-11-12 |
| Critical | `docker.io/apache/apisix@sha256:9a7e45dc943fbf10ec916d1232bae4cda9302ae28a4696cfb83c2da01d261141` | `perl-base 5.36.0-7+deb12u3` | CVE-2026-57433 | 2026-11-12 |
| Critical | `docker.io/apache/apisix@sha256:9a7e45dc943fbf10ec916d1232bae4cda9302ae28a4696cfb83c2da01d261141` | `perl-base 5.36.0-7+deb12u3` | CVE-2026-8376 | 2026-11-12 |
| Critical | `docker.io/ministackorg/ministack@sha256:11d7308bfc75029d55625b9525e84a2401431ed1ff2148c6311800ff5009ae9c` | `python 3.13.15` | CVE-2026-19445 | 2026-11-12 |
| Critical | `docker.io/openbao/openbao@sha256:6d2b93856e3fcf7b18ad855a0b51eaba474dc8b79cf554379ea32034797d2acf` | `golang.org/x/net v0.58.0` | CVE-2026-78663 | 2026-11-12 |
| Critical | `docker.io/openbao/openbao@sha256:6d2b93856e3fcf7b18ad855a0b51eaba474dc8b79cf554379ea32034797d2acf` | `stdlib go1.27.1` | CVE-2026-56857 | 2026-11-12 |
| Critical | `docker.io/openbao/openbao@sha256:6d2b93856e3fcf7b18ad855a0b51eaba474dc8b79cf554379ea32034797d2acf` | `stdlib go1.27.1` | CVE-2026-78663 | 2026-11-12 |
| Critical | `ghcr.io/cloudnative-pg/cloudnative-pg@sha256:923c267ec29636db3bee20f993d0ec4973fa22998e1adad37da79e4d32b5bc07` | `golang.org/x/net v0.58.0` | CVE-2026-78663 | 2026-11-12 |
| Critical | `ghcr.io/cloudnative-pg/cloudnative-pg@sha256:923c267ec29636db3bee20f993d0ec4973fa22998e1adad37da79e4d32b5bc07` | `stdlib go1.27.1` | CVE-2026-56857 | 2026-11-12 |
| Critical | `ghcr.io/cloudnative-pg/cloudnative-pg@sha256:923c267ec29636db3bee20f993d0ec4973fa22998e1adad37da79e4d32b5bc07` | `stdlib go1.27.1` | CVE-2026-78663 | 2026-11-12 |
| Critical | `quay.io/argoproj/argocd@sha256:dd3f47d5a5e4da563a7a398506e892481b358a7cec50abdf320c71aa55904bfa` | `golang.org/x/crypto v0.36.0` | CVE-2026-39830 | 2026-11-12 |
| Critical | `quay.io/argoproj/argocd@sha256:dd3f47d5a5e4da563a7a398506e892481b358a7cec50abdf320c71aa55904bfa` | `golang.org/x/crypto v0.36.0` | CVE-2026-39831 | 2026-11-12 |
| Critical | `quay.io/argoproj/argocd@sha256:dd3f47d5a5e4da563a7a398506e892481b358a7cec50abdf320c71aa55904bfa` | `golang.org/x/crypto v0.36.0` | CVE-2026-39832 | 2026-11-12 |
| Critical | `quay.io/argoproj/argocd@sha256:dd3f47d5a5e4da563a7a398506e892481b358a7cec50abdf320c71aa55904bfa` | `golang.org/x/crypto v0.36.0` | CVE-2026-39833 | 2026-11-12 |
| Critical | `quay.io/argoproj/argocd@sha256:dd3f47d5a5e4da563a7a398506e892481b358a7cec50abdf320c71aa55904bfa` | `golang.org/x/crypto v0.36.0` | CVE-2026-39834 | 2026-11-12 |
| Critical | `quay.io/argoproj/argocd@sha256:dd3f47d5a5e4da563a7a398506e892481b358a7cec50abdf320c71aa55904bfa` | `golang.org/x/crypto v0.36.0` | CVE-2026-42508 | 2026-11-12 |
| Critical | `quay.io/argoproj/argocd@sha256:dd3f47d5a5e4da563a7a398506e892481b358a7cec50abdf320c71aa55904bfa` | `golang.org/x/crypto v0.36.0` | CVE-2026-46595 | 2026-11-12 |
| Critical | `quay.io/argoproj/argocd@sha256:dd3f47d5a5e4da563a7a398506e892481b358a7cec50abdf320c71aa55904bfa` | `golang.org/x/net v0.38.0` | CVE-2026-78663 | 2026-11-12 |
| Critical | `quay.io/argoproj/argocd@sha256:dd3f47d5a5e4da563a7a398506e892481b358a7cec50abdf320c71aa55904bfa` | `golang.org/x/net v0.40.0` | CVE-2026-78663 | 2026-11-12 |
| Critical | `quay.io/argoproj/argocd@sha256:dd3f47d5a5e4da563a7a398506e892481b358a7cec50abdf320c71aa55904bfa` | `golang.org/x/net v0.55.0` | CVE-2026-78663 | 2026-11-12 |
| Critical | `quay.io/argoproj/argocd@sha256:dd3f47d5a5e4da563a7a398506e892481b358a7cec50abdf320c71aa55904bfa` | `golang.org/x/net v0.56.0` | CVE-2026-78663 | 2026-11-12 |
| Critical | `quay.io/argoproj/argocd@sha256:dd3f47d5a5e4da563a7a398506e892481b358a7cec50abdf320c71aa55904bfa` | `stdlib go1.24.0` | CVE-2025-22871 | 2026-11-12 |
| Critical | `quay.io/argoproj/argocd@sha256:dd3f47d5a5e4da563a7a398506e892481b358a7cec50abdf320c71aa55904bfa` | `stdlib go1.24.0` | CVE-2025-68121 | 2026-11-12 |
| Critical | `quay.io/argoproj/argocd@sha256:dd3f47d5a5e4da563a7a398506e892481b358a7cec50abdf320c71aa55904bfa` | `stdlib go1.24.0` | CVE-2026-56857 | 2026-11-12 |
| Critical | `quay.io/argoproj/argocd@sha256:dd3f47d5a5e4da563a7a398506e892481b358a7cec50abdf320c71aa55904bfa` | `stdlib go1.24.0` | CVE-2026-78663 | 2026-11-12 |
| Critical | `quay.io/argoproj/argocd@sha256:dd3f47d5a5e4da563a7a398506e892481b358a7cec50abdf320c71aa55904bfa` | `stdlib go1.25.3` | CVE-2025-68121 | 2026-11-12 |
| Critical | `quay.io/argoproj/argocd@sha256:dd3f47d5a5e4da563a7a398506e892481b358a7cec50abdf320c71aa55904bfa` | `stdlib go1.25.3` | CVE-2026-56857 | 2026-11-12 |
| Critical | `quay.io/argoproj/argocd@sha256:dd3f47d5a5e4da563a7a398506e892481b358a7cec50abdf320c71aa55904bfa` | `stdlib go1.25.3` | CVE-2026-78663 | 2026-11-12 |
| Critical | `quay.io/argoproj/argocd@sha256:dd3f47d5a5e4da563a7a398506e892481b358a7cec50abdf320c71aa55904bfa` | `stdlib go1.26.2` | CVE-2026-56857 | 2026-11-12 |
| Critical | `quay.io/argoproj/argocd@sha256:dd3f47d5a5e4da563a7a398506e892481b358a7cec50abdf320c71aa55904bfa` | `stdlib go1.26.2` | CVE-2026-78663 | 2026-11-12 |
| Critical | `quay.io/argoproj/argocd@sha256:dd3f47d5a5e4da563a7a398506e892481b358a7cec50abdf320c71aa55904bfa` | `stdlib go1.26.4` | CVE-2026-56857 | 2026-11-12 |
| Critical | `quay.io/argoproj/argocd@sha256:dd3f47d5a5e4da563a7a398506e892481b358a7cec50abdf320c71aa55904bfa` | `stdlib go1.26.4` | CVE-2026-78663 | 2026-11-12 |
| Critical | `quay.io/cilium/cilium-envoy@sha256:af7382699576b9e65e9184efa52eeca0b58aea70ad6e511bf260c91d9f740463` | `golang.org/x/net v0.58.0` | CVE-2026-78663 | 2026-11-12 |
| Critical | `quay.io/cilium/cilium-envoy@sha256:af7382699576b9e65e9184efa52eeca0b58aea70ad6e511bf260c91d9f740463` | `stdlib go1.27.1` | CVE-2026-56857 | 2026-11-12 |
| Critical | `quay.io/cilium/cilium-envoy@sha256:af7382699576b9e65e9184efa52eeca0b58aea70ad6e511bf260c91d9f740463` | `stdlib go1.27.1` | CVE-2026-78663 | 2026-11-12 |
| Critical | `quay.io/cilium/cilium@sha256:2939231d0d3e3ebddcd80fffa168b7ddcc78fdf0dc864d1c8c126ff523c54f01` | `golang.org/x/net v0.56.0` | CVE-2026-78663 | 2026-11-12 |
| Critical | `quay.io/cilium/cilium@sha256:2939231d0d3e3ebddcd80fffa168b7ddcc78fdf0dc864d1c8c126ff523c54f01` | `stdlib go1.26.5` | CVE-2026-56857 | 2026-11-12 |
| Critical | `quay.io/cilium/cilium@sha256:2939231d0d3e3ebddcd80fffa168b7ddcc78fdf0dc864d1c8c126ff523c54f01` | `stdlib go1.26.5` | CVE-2026-78663 | 2026-11-12 |
| Critical | `quay.io/cilium/cilium@sha256:2939231d0d3e3ebddcd80fffa168b7ddcc78fdf0dc864d1c8c126ff523c54f01` | `stdlib go1.26.8` | CVE-2026-56857 | 2026-11-12 |
| Critical | `quay.io/cilium/cilium@sha256:2939231d0d3e3ebddcd80fffa168b7ddcc78fdf0dc864d1c8c126ff523c54f01` | `stdlib go1.26.8` | CVE-2026-78663 | 2026-11-12 |
| Critical | `quay.io/cilium/operator-generic@sha256:64d8798350e8569b8e7622563fed6e44dce2625f311e4651b774816516c744fc` | `golang.org/x/net v0.56.0` | CVE-2026-78663 | 2026-11-12 |
| Critical | `quay.io/cilium/operator-generic@sha256:64d8798350e8569b8e7622563fed6e44dce2625f311e4651b774816516c744fc` | `stdlib go1.26.8` | CVE-2026-56857 | 2026-11-12 |
| Critical | `quay.io/cilium/operator-generic@sha256:64d8798350e8569b8e7622563fed6e44dce2625f311e4651b774816516c744fc` | `stdlib go1.26.8` | CVE-2026-78663 | 2026-11-12 |
| Critical | `registry.k8s.io/coredns/coredns@sha256:7efd3c635b03efd68c4e8398fc45f0d993d0e9ab016f72c1cefb0fd6d01aa286` | `golang.org/x/net v0.57.0` | CVE-2026-78663 | 2026-11-12 |
| Critical | `registry.k8s.io/coredns/coredns@sha256:7efd3c635b03efd68c4e8398fc45f0d993d0e9ab016f72c1cefb0fd6d01aa286` | `stdlib go1.26.6` | CVE-2026-56857 | 2026-11-12 |
| Critical | `registry.k8s.io/coredns/coredns@sha256:7efd3c635b03efd68c4e8398fc45f0d993d0e9ab016f72c1cefb0fd6d01aa286` | `stdlib go1.26.6` | CVE-2026-78663 | 2026-11-12 |
| Critical | `registry.k8s.io/etcd@sha256:5ed4e32061aa061f970d6500629213e8579ef17571dcf9789074966acb9afad1` | `golang.org/x/net v0.58.0` | CVE-2026-78663 | 2026-11-12 |
| Critical | `registry.k8s.io/etcd@sha256:5ed4e32061aa061f970d6500629213e8579ef17571dcf9789074966acb9afad1` | `stdlib go1.26.8` | CVE-2026-56857 | 2026-11-12 |
| Critical | `registry.k8s.io/etcd@sha256:5ed4e32061aa061f970d6500629213e8579ef17571dcf9789074966acb9afad1` | `stdlib go1.26.8` | CVE-2026-78663 | 2026-11-12 |
| Critical | `registry.k8s.io/kube-apiserver@sha256:4b3e69973a1d58d3c1f670d3477a9b9f14a03a271823113e8e0c9a333eb84f48` | `golang.org/x/net v0.56.0` | CVE-2026-78663 | 2026-11-12 |
| Critical | `registry.k8s.io/kube-apiserver@sha256:4b3e69973a1d58d3c1f670d3477a9b9f14a03a271823113e8e0c9a333eb84f48` | `stdlib go1.26.8` | CVE-2026-56857 | 2026-11-12 |
| Critical | `registry.k8s.io/kube-apiserver@sha256:4b3e69973a1d58d3c1f670d3477a9b9f14a03a271823113e8e0c9a333eb84f48` | `stdlib go1.26.8` | CVE-2026-78663 | 2026-11-12 |
| Critical | `registry.k8s.io/kube-controller-manager@sha256:2d717af134451db77ea053c3426bc82edc0e55415eb36e1260313c636ebe9a4d` | `golang.org/x/net v0.56.0` | CVE-2026-78663 | 2026-11-12 |
| Critical | `registry.k8s.io/kube-controller-manager@sha256:2d717af134451db77ea053c3426bc82edc0e55415eb36e1260313c636ebe9a4d` | `stdlib go1.26.8` | CVE-2026-56857 | 2026-11-12 |
| Critical | `registry.k8s.io/kube-controller-manager@sha256:2d717af134451db77ea053c3426bc82edc0e55415eb36e1260313c636ebe9a4d` | `stdlib go1.26.8` | CVE-2026-78663 | 2026-11-12 |
| Critical | `registry.k8s.io/kube-scheduler@sha256:3804f66442962cefbe11fcd5330d5e7a797bfb3dc8535c322d005637b404a85f` | `golang.org/x/net v0.56.0` | CVE-2026-78663 | 2026-11-12 |
| Critical | `registry.k8s.io/kube-scheduler@sha256:3804f66442962cefbe11fcd5330d5e7a797bfb3dc8535c322d005637b404a85f` | `stdlib go1.26.8` | CVE-2026-56857 | 2026-11-12 |
| Critical | `registry.k8s.io/kube-scheduler@sha256:3804f66442962cefbe11fcd5330d5e7a797bfb3dc8535c322d005637b404a85f` | `stdlib go1.26.8` | CVE-2026-78663 | 2026-11-12 |
