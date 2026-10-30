# Changelog

All notable changes to this project are documented here.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and versions follow [Semantic Versioning](https://semver.org/spec/v2.0.0.html).
See [RELEASING.md](RELEASING.md) for the release streams. Twinfra has no earlier releases or tags.

## [Unreleased]

### Changed

- WO-40b / R3b: refresh v0.1.0 release notes and compatibility on post-R12
  main 7cf2ba8; disclose all 420 approved exception rows and their unchanged
  calendar. Record the owner's 2026-10-29 all-17-check acceptance pass and the
  resolved network-equipment power incident. Keep console maintenance deferred
  to post-release WO-47. Run the vCloud PR gate on release branches and align
  readiness/capabilities with Accepted receipts; retain the approved WO-04
  static-scope wording correction. No runtime, console, tag or release change.

## [0.1.0]

**Draft; no release date or tag.** Single-node dev use only. The rc window and
consolidated tester acceptance remain Pending. See the
[release notes](docs/release-notes/0.1.0.md) for actual running versions,
installation/update procedures and the path to 0.2.0.

The changes below were drafted from [Unreleased]; their original per-change
Pending/static statements describe when each change landed. Current signed
scope is in the [capability statement](docs/capabilities.md).

### Changed

- R12c: anchor approval tests to the committed proposal/carry-log SHA-256 and
  approved scope, retaining row equality, mutation refusal and deadline checks.
  Reject unreachable Git commit dependencies in tests/tools; retire the one-shot
  R12 activation entry point under WO-40 Amendments 10g/10h. No approval, policy,
  image, console or workflow changes.

- R12 October security wave: promote digest-pinned Argo CD 3.5.5, MiniStack
  1.5.33 and Keycloak 26.8.1; refresh the certifi and DOMPurify locks under O-1.
  Add anchored, append-only security-fix licence carries with unchanged original
  backfill deadlines under ADR-0054 Amendment 1. Activate the exact 420-row
  exception batch and three licence carries approved by the owner on 2026-10-29
  at PR #82 head 86d4318; preserve every other row field. Image staging and live
  acceptance remain owner actions. Close three fixed prior exception rows and
  publish the per-image scan ledger, immutable approval hashes, original-date
  licence carry log and release-window calendar; keep every gate enforced.

- Fix Syft cataloging of pinned CI binaries by applying platform selection only
  to image sources. Add a real actionlint extraction/SBOM/Grype CI regression
  and restricted, redacted diagnostics for verified local tool files; pinned-tool
  failures remain blocking.

- Isolate weekly upstream candidate scans, retry scanner failures once, and report
  unavailable candidates with sanitized target/tool identities; pinned-input scans
  remain blocking and failed candidates cannot claim vulnerability resolutions.

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
- Valkey and MiniStack image SBOM/notice reviews remain due 2027-01-07.
- Security exceptions below are time-bounded risk acceptance, not remediation.
  R12 Argo CD 3.5.5 is accepted for dev use with its retained libbrotli1 KEV
  exception and WO-46 checkpoint; passing the gate does not mean zero findings.
- Console test-only undici maintenance is deferred until after v0.1.0 under
  WO-40 Amendment 10f / WO-47. The console image and its inputs are unchanged;
  vulnerability scanning and the 14-day High rule remain enforced.

### Exception table

Snapshot of [the active vulnerability policy](security/vulnerability-exceptions.json)
at post-R12 main `7cf2ba8354b960567c61601945806130016b9cdd`, reviewed for
R3b on 2026-10-30: **420 entries: 59 Critical, 360 High and one Medium KEV**.
All are owner-approved by `amazen33` and reference WO-46. This is a complete
per-package/immutable-target disclosure, not a new scan or an expiry extension.
Reasons, controls, fix evidence and approvals remain in the unchanged registry.

PR #82 closed the two interim Argo CD 3.5.3 rows (CVE-2026-55797 and
CVE-2026-77459) and the fixed MiniStack Python Critical. It activated the
59 individually approved Critical renewals, 360 High entries and one Argo CD
3.5.5 libbrotli1 KEV row (CVE-2026-111497). The KEV expiry is **2026-11-24**
with a **2026-11-13 checkpoint**; Critical renewals expire **2026-11-27**;
High entries expire **2026-12-27**. No active row expires November 2 or 12.
The owner's October 29 post-promotion acceptance passed all 17 checks at
`7cf2ba8`, including the 420-entry calendar; see the
[release evidence](docs/release-notes/0.1.0.md#evidence-and-actual-running-versions).

| Severity | Image / immutable target | Package / version | CVE / advisory | Expires |
| --- | --- | --- | --- | --- |
| Critical | `docker.io/apache/apisix@sha256:9a7e45dc943fbf10ec916d1232bae4cda9302ae28a4696cfb83c2da01d261141` | `perl-base 5.36.0-7+deb12u3` | CVE-2026-12087 | 2026-11-27 |
| Critical | `docker.io/apache/apisix@sha256:9a7e45dc943fbf10ec916d1232bae4cda9302ae28a4696cfb83c2da01d261141` | `perl-base 5.36.0-7+deb12u3` | CVE-2026-13221 | 2026-11-27 |
| Critical | `docker.io/apache/apisix@sha256:9a7e45dc943fbf10ec916d1232bae4cda9302ae28a4696cfb83c2da01d261141` | `perl-base 5.36.0-7+deb12u3` | CVE-2026-42496 | 2026-11-27 |
| Critical | `docker.io/apache/apisix@sha256:9a7e45dc943fbf10ec916d1232bae4cda9302ae28a4696cfb83c2da01d261141` | `perl-base 5.36.0-7+deb12u3` | CVE-2026-57433 | 2026-11-27 |
| Critical | `docker.io/apache/apisix@sha256:9a7e45dc943fbf10ec916d1232bae4cda9302ae28a4696cfb83c2da01d261141` | `perl-base 5.36.0-7+deb12u3` | CVE-2026-8376 | 2026-11-27 |
| Critical | `docker.io/openbao/openbao@sha256:6d2b93856e3fcf7b18ad855a0b51eaba474dc8b79cf554379ea32034797d2acf` | `golang.org/x/net v0.58.0` | CVE-2026-78663 | 2026-11-27 |
| Critical | `docker.io/openbao/openbao@sha256:6d2b93856e3fcf7b18ad855a0b51eaba474dc8b79cf554379ea32034797d2acf` | `stdlib go1.27.1` | CVE-2026-56857 | 2026-11-27 |
| Critical | `docker.io/openbao/openbao@sha256:6d2b93856e3fcf7b18ad855a0b51eaba474dc8b79cf554379ea32034797d2acf` | `stdlib go1.27.1` | CVE-2026-78663 | 2026-11-27 |
| Critical | `ghcr.io/cloudnative-pg/cloudnative-pg@sha256:923c267ec29636db3bee20f993d0ec4973fa22998e1adad37da79e4d32b5bc07` | `golang.org/x/net v0.58.0` | CVE-2026-78663 | 2026-11-27 |
| Critical | `ghcr.io/cloudnative-pg/cloudnative-pg@sha256:923c267ec29636db3bee20f993d0ec4973fa22998e1adad37da79e4d32b5bc07` | `stdlib go1.27.1` | CVE-2026-56857 | 2026-11-27 |
| Critical | `ghcr.io/cloudnative-pg/cloudnative-pg@sha256:923c267ec29636db3bee20f993d0ec4973fa22998e1adad37da79e4d32b5bc07` | `stdlib go1.27.1` | CVE-2026-78663 | 2026-11-27 |
| Critical | `quay.io/argoproj/argocd@sha256:13db7b10db23283b1b36f855046602e18539a8a8204c9f6f039e8896c8897518` | `golang.org/x/crypto v0.36.0` | CVE-2026-39830 | 2026-11-27 |
| Critical | `quay.io/argoproj/argocd@sha256:13db7b10db23283b1b36f855046602e18539a8a8204c9f6f039e8896c8897518` | `golang.org/x/crypto v0.36.0` | CVE-2026-39831 | 2026-11-27 |
| Critical | `quay.io/argoproj/argocd@sha256:13db7b10db23283b1b36f855046602e18539a8a8204c9f6f039e8896c8897518` | `golang.org/x/crypto v0.36.0` | CVE-2026-39832 | 2026-11-27 |
| Critical | `quay.io/argoproj/argocd@sha256:13db7b10db23283b1b36f855046602e18539a8a8204c9f6f039e8896c8897518` | `golang.org/x/crypto v0.36.0` | CVE-2026-39833 | 2026-11-27 |
| Critical | `quay.io/argoproj/argocd@sha256:13db7b10db23283b1b36f855046602e18539a8a8204c9f6f039e8896c8897518` | `golang.org/x/crypto v0.36.0` | CVE-2026-39834 | 2026-11-27 |
| Critical | `quay.io/argoproj/argocd@sha256:13db7b10db23283b1b36f855046602e18539a8a8204c9f6f039e8896c8897518` | `golang.org/x/crypto v0.36.0` | CVE-2026-42508 | 2026-11-27 |
| Critical | `quay.io/argoproj/argocd@sha256:13db7b10db23283b1b36f855046602e18539a8a8204c9f6f039e8896c8897518` | `golang.org/x/crypto v0.36.0` | CVE-2026-46595 | 2026-11-27 |
| Critical | `quay.io/argoproj/argocd@sha256:13db7b10db23283b1b36f855046602e18539a8a8204c9f6f039e8896c8897518` | `golang.org/x/net v0.38.0` | CVE-2026-78663 | 2026-11-27 |
| Critical | `quay.io/argoproj/argocd@sha256:13db7b10db23283b1b36f855046602e18539a8a8204c9f6f039e8896c8897518` | `golang.org/x/net v0.40.0` | CVE-2026-78663 | 2026-11-27 |
| Critical | `quay.io/argoproj/argocd@sha256:13db7b10db23283b1b36f855046602e18539a8a8204c9f6f039e8896c8897518` | `golang.org/x/net v0.55.0` | CVE-2026-78663 | 2026-11-27 |
| Critical | `quay.io/argoproj/argocd@sha256:13db7b10db23283b1b36f855046602e18539a8a8204c9f6f039e8896c8897518` | `golang.org/x/net v0.59.0` | CVE-2026-78663 | 2026-11-27 |
| Critical | `quay.io/argoproj/argocd@sha256:13db7b10db23283b1b36f855046602e18539a8a8204c9f6f039e8896c8897518` | `stdlib go1.24.0` | CVE-2025-22871 | 2026-11-27 |
| Critical | `quay.io/argoproj/argocd@sha256:13db7b10db23283b1b36f855046602e18539a8a8204c9f6f039e8896c8897518` | `stdlib go1.24.0` | CVE-2025-68121 | 2026-11-27 |
| Critical | `quay.io/argoproj/argocd@sha256:13db7b10db23283b1b36f855046602e18539a8a8204c9f6f039e8896c8897518` | `stdlib go1.24.0` | CVE-2026-56857 | 2026-11-27 |
| Critical | `quay.io/argoproj/argocd@sha256:13db7b10db23283b1b36f855046602e18539a8a8204c9f6f039e8896c8897518` | `stdlib go1.24.0` | CVE-2026-78663 | 2026-11-27 |
| Critical | `quay.io/argoproj/argocd@sha256:13db7b10db23283b1b36f855046602e18539a8a8204c9f6f039e8896c8897518` | `stdlib go1.25.3` | CVE-2025-68121 | 2026-11-27 |
| Critical | `quay.io/argoproj/argocd@sha256:13db7b10db23283b1b36f855046602e18539a8a8204c9f6f039e8896c8897518` | `stdlib go1.25.3` | CVE-2026-56857 | 2026-11-27 |
| Critical | `quay.io/argoproj/argocd@sha256:13db7b10db23283b1b36f855046602e18539a8a8204c9f6f039e8896c8897518` | `stdlib go1.25.3` | CVE-2026-78663 | 2026-11-27 |
| Critical | `quay.io/argoproj/argocd@sha256:13db7b10db23283b1b36f855046602e18539a8a8204c9f6f039e8896c8897518` | `stdlib go1.26.2` | CVE-2026-56857 | 2026-11-27 |
| Critical | `quay.io/argoproj/argocd@sha256:13db7b10db23283b1b36f855046602e18539a8a8204c9f6f039e8896c8897518` | `stdlib go1.26.2` | CVE-2026-78663 | 2026-11-27 |
| Critical | `quay.io/argoproj/argocd@sha256:13db7b10db23283b1b36f855046602e18539a8a8204c9f6f039e8896c8897518` | `stdlib go1.26.4` | CVE-2026-56857 | 2026-11-27 |
| Critical | `quay.io/argoproj/argocd@sha256:13db7b10db23283b1b36f855046602e18539a8a8204c9f6f039e8896c8897518` | `stdlib go1.26.4` | CVE-2026-78663 | 2026-11-27 |
| Critical | `quay.io/cilium/cilium-envoy@sha256:af7382699576b9e65e9184efa52eeca0b58aea70ad6e511bf260c91d9f740463` | `golang.org/x/net v0.58.0` | CVE-2026-78663 | 2026-11-27 |
| Critical | `quay.io/cilium/cilium-envoy@sha256:af7382699576b9e65e9184efa52eeca0b58aea70ad6e511bf260c91d9f740463` | `stdlib go1.27.1` | CVE-2026-56857 | 2026-11-27 |
| Critical | `quay.io/cilium/cilium-envoy@sha256:af7382699576b9e65e9184efa52eeca0b58aea70ad6e511bf260c91d9f740463` | `stdlib go1.27.1` | CVE-2026-78663 | 2026-11-27 |
| Critical | `quay.io/cilium/cilium@sha256:2939231d0d3e3ebddcd80fffa168b7ddcc78fdf0dc864d1c8c126ff523c54f01` | `golang.org/x/net v0.56.0` | CVE-2026-78663 | 2026-11-27 |
| Critical | `quay.io/cilium/cilium@sha256:2939231d0d3e3ebddcd80fffa168b7ddcc78fdf0dc864d1c8c126ff523c54f01` | `stdlib go1.26.5` | CVE-2026-56857 | 2026-11-27 |
| Critical | `quay.io/cilium/cilium@sha256:2939231d0d3e3ebddcd80fffa168b7ddcc78fdf0dc864d1c8c126ff523c54f01` | `stdlib go1.26.5` | CVE-2026-78663 | 2026-11-27 |
| Critical | `quay.io/cilium/cilium@sha256:2939231d0d3e3ebddcd80fffa168b7ddcc78fdf0dc864d1c8c126ff523c54f01` | `stdlib go1.26.8` | CVE-2026-56857 | 2026-11-27 |
| Critical | `quay.io/cilium/cilium@sha256:2939231d0d3e3ebddcd80fffa168b7ddcc78fdf0dc864d1c8c126ff523c54f01` | `stdlib go1.26.8` | CVE-2026-78663 | 2026-11-27 |
| Critical | `quay.io/cilium/operator-generic@sha256:64d8798350e8569b8e7622563fed6e44dce2625f311e4651b774816516c744fc` | `golang.org/x/net v0.56.0` | CVE-2026-78663 | 2026-11-27 |
| Critical | `quay.io/cilium/operator-generic@sha256:64d8798350e8569b8e7622563fed6e44dce2625f311e4651b774816516c744fc` | `stdlib go1.26.8` | CVE-2026-56857 | 2026-11-27 |
| Critical | `quay.io/cilium/operator-generic@sha256:64d8798350e8569b8e7622563fed6e44dce2625f311e4651b774816516c744fc` | `stdlib go1.26.8` | CVE-2026-78663 | 2026-11-27 |
| Critical | `registry.k8s.io/coredns/coredns@sha256:7efd3c635b03efd68c4e8398fc45f0d993d0e9ab016f72c1cefb0fd6d01aa286` | `golang.org/x/net v0.57.0` | CVE-2026-78663 | 2026-11-27 |
| Critical | `registry.k8s.io/coredns/coredns@sha256:7efd3c635b03efd68c4e8398fc45f0d993d0e9ab016f72c1cefb0fd6d01aa286` | `stdlib go1.26.6` | CVE-2026-56857 | 2026-11-27 |
| Critical | `registry.k8s.io/coredns/coredns@sha256:7efd3c635b03efd68c4e8398fc45f0d993d0e9ab016f72c1cefb0fd6d01aa286` | `stdlib go1.26.6` | CVE-2026-78663 | 2026-11-27 |
| Critical | `registry.k8s.io/etcd@sha256:5ed4e32061aa061f970d6500629213e8579ef17571dcf9789074966acb9afad1` | `golang.org/x/net v0.58.0` | CVE-2026-78663 | 2026-11-27 |
| Critical | `registry.k8s.io/etcd@sha256:5ed4e32061aa061f970d6500629213e8579ef17571dcf9789074966acb9afad1` | `stdlib go1.26.8` | CVE-2026-56857 | 2026-11-27 |
| Critical | `registry.k8s.io/etcd@sha256:5ed4e32061aa061f970d6500629213e8579ef17571dcf9789074966acb9afad1` | `stdlib go1.26.8` | CVE-2026-78663 | 2026-11-27 |
| Critical | `registry.k8s.io/kube-apiserver@sha256:4b3e69973a1d58d3c1f670d3477a9b9f14a03a271823113e8e0c9a333eb84f48` | `golang.org/x/net v0.56.0` | CVE-2026-78663 | 2026-11-27 |
| Critical | `registry.k8s.io/kube-apiserver@sha256:4b3e69973a1d58d3c1f670d3477a9b9f14a03a271823113e8e0c9a333eb84f48` | `stdlib go1.26.8` | CVE-2026-56857 | 2026-11-27 |
| Critical | `registry.k8s.io/kube-apiserver@sha256:4b3e69973a1d58d3c1f670d3477a9b9f14a03a271823113e8e0c9a333eb84f48` | `stdlib go1.26.8` | CVE-2026-78663 | 2026-11-27 |
| Critical | `registry.k8s.io/kube-controller-manager@sha256:2d717af134451db77ea053c3426bc82edc0e55415eb36e1260313c636ebe9a4d` | `golang.org/x/net v0.56.0` | CVE-2026-78663 | 2026-11-27 |
| Critical | `registry.k8s.io/kube-controller-manager@sha256:2d717af134451db77ea053c3426bc82edc0e55415eb36e1260313c636ebe9a4d` | `stdlib go1.26.8` | CVE-2026-56857 | 2026-11-27 |
| Critical | `registry.k8s.io/kube-controller-manager@sha256:2d717af134451db77ea053c3426bc82edc0e55415eb36e1260313c636ebe9a4d` | `stdlib go1.26.8` | CVE-2026-78663 | 2026-11-27 |
| Critical | `registry.k8s.io/kube-scheduler@sha256:3804f66442962cefbe11fcd5330d5e7a797bfb3dc8535c322d005637b404a85f` | `golang.org/x/net v0.56.0` | CVE-2026-78663 | 2026-11-27 |
| Critical | `registry.k8s.io/kube-scheduler@sha256:3804f66442962cefbe11fcd5330d5e7a797bfb3dc8535c322d005637b404a85f` | `stdlib go1.26.8` | CVE-2026-56857 | 2026-11-27 |
| Critical | `registry.k8s.io/kube-scheduler@sha256:3804f66442962cefbe11fcd5330d5e7a797bfb3dc8535c322d005637b404a85f` | `stdlib go1.26.8` | CVE-2026-78663 | 2026-11-27 |
| High | `docker.io/apache/apisix@sha256:9a7e45dc943fbf10ec916d1232bae4cda9302ae28a4696cfb83c2da01d261141` | `libpcre2-8-0 10.42-1+deb12u1` | CVE-2026-103111 | 2026-12-27 |
| High | `docker.io/apache/apisix@sha256:9a7e45dc943fbf10ec916d1232bae4cda9302ae28a4696cfb83c2da01d261141` | `libssl3 3.0.22-1~deb12u1` | CVE-2026-84782 | 2026-12-27 |
| High | `docker.io/apache/apisix@sha256:9a7e45dc943fbf10ec916d1232bae4cda9302ae28a4696cfb83c2da01d261141` | `openssl 3.0.22-1~deb12u1` | CVE-2026-84782 | 2026-12-27 |
| High | `docker.io/apache/apisix@sha256:9a7e45dc943fbf10ec916d1232bae4cda9302ae28a4696cfb83c2da01d261141` | `perl-base 5.36.0-7+deb12u3` | CVE-2026-42497 | 2026-12-27 |
| High | `docker.io/apache/apisix@sha256:9a7e45dc943fbf10ec916d1232bae4cda9302ae28a4696cfb83c2da01d261141` | `perl-base 5.36.0-7+deb12u3` | CVE-2026-48959 | 2026-12-27 |
| High | `docker.io/apache/apisix@sha256:9a7e45dc943fbf10ec916d1232bae4cda9302ae28a4696cfb83c2da01d261141` | `perl-base 5.36.0-7+deb12u3` | CVE-2026-48962 | 2026-12-27 |
| High | `docker.io/apache/apisix@sha256:9a7e45dc943fbf10ec916d1232bae4cda9302ae28a4696cfb83c2da01d261141` | `perl-base 5.36.0-7+deb12u3` | CVE-2026-57432 | 2026-12-27 |
| High | `docker.io/apache/apisix@sha256:9a7e45dc943fbf10ec916d1232bae4cda9302ae28a4696cfb83c2da01d261141` | `perl-base 5.36.0-7+deb12u3` | CVE-2026-7017 | 2026-12-27 |
| High | `docker.io/openbao/openbao@sha256:6d2b93856e3fcf7b18ad855a0b51eaba474dc8b79cf554379ea32034797d2acf` | `github.com/go-jose/go-jose/v4 v4.1.4` | CVE-2026-116587 | 2026-12-27 |
| High | `docker.io/openbao/openbao@sha256:6d2b93856e3fcf7b18ad855a0b51eaba474dc8b79cf554379ea32034797d2acf` | `golang.org/x/net v0.58.0` | CVE-2026-78659 | 2026-12-27 |
| High | `docker.io/openbao/openbao@sha256:6d2b93856e3fcf7b18ad855a0b51eaba474dc8b79cf554379ea32034797d2acf` | `golang.org/x/net v0.58.0` | CVE-2026-78660 | 2026-12-27 |
| High | `docker.io/openbao/openbao@sha256:6d2b93856e3fcf7b18ad855a0b51eaba474dc8b79cf554379ea32034797d2acf` | `golang.org/x/net v0.58.0` | CVE-2026-78669 | 2026-12-27 |
| High | `docker.io/openbao/openbao@sha256:6d2b93856e3fcf7b18ad855a0b51eaba474dc8b79cf554379ea32034797d2acf` | `golang.org/x/net v0.58.0` | CVE-2026-97032 | 2026-12-27 |
| High | `docker.io/openbao/openbao@sha256:6d2b93856e3fcf7b18ad855a0b51eaba474dc8b79cf554379ea32034797d2acf` | `stdlib go1.27.1` | CVE-2026-56866 | 2026-12-27 |
| High | `docker.io/openbao/openbao@sha256:6d2b93856e3fcf7b18ad855a0b51eaba474dc8b79cf554379ea32034797d2acf` | `stdlib go1.27.1` | CVE-2026-78659 | 2026-12-27 |
| High | `docker.io/openbao/openbao@sha256:6d2b93856e3fcf7b18ad855a0b51eaba474dc8b79cf554379ea32034797d2acf` | `stdlib go1.27.1` | CVE-2026-78660 | 2026-12-27 |
| High | `docker.io/openbao/openbao@sha256:6d2b93856e3fcf7b18ad855a0b51eaba474dc8b79cf554379ea32034797d2acf` | `stdlib go1.27.1` | CVE-2026-78667 | 2026-12-27 |
| High | `docker.io/openbao/openbao@sha256:6d2b93856e3fcf7b18ad855a0b51eaba474dc8b79cf554379ea32034797d2acf` | `stdlib go1.27.1` | CVE-2026-78669 | 2026-12-27 |
| High | `docker.io/openbao/openbao@sha256:6d2b93856e3fcf7b18ad855a0b51eaba474dc8b79cf554379ea32034797d2acf` | `stdlib go1.27.1` | CVE-2026-94439 | 2026-12-27 |
| High | `docker.io/openbao/openbao@sha256:6d2b93856e3fcf7b18ad855a0b51eaba474dc8b79cf554379ea32034797d2acf` | `stdlib go1.27.1` | CVE-2026-94440 | 2026-12-27 |
| High | `docker.io/openbao/openbao@sha256:6d2b93856e3fcf7b18ad855a0b51eaba474dc8b79cf554379ea32034797d2acf` | `stdlib go1.27.1` | CVE-2026-97031 | 2026-12-27 |
| High | `docker.io/openbao/openbao@sha256:6d2b93856e3fcf7b18ad855a0b51eaba474dc8b79cf554379ea32034797d2acf` | `stdlib go1.27.1` | CVE-2026-97032 | 2026-12-27 |
| High | `docker.io/openbao/openbao@sha256:6d2b93856e3fcf7b18ad855a0b51eaba474dc8b79cf554379ea32034797d2acf` | `zlib 1.3.2-r0` | CVE-2026-85091 | 2026-12-27 |
| High | `docker.io/valkey/valkey@sha256:081c2f5cb575efc901aa80ff9cdbd1ec6a301682fd35e1ebb4b0990a4a4a8507` | `zlib 1.3.2-r0` | CVE-2026-85091 | 2026-12-27 |
| High | `ghcr.io/cloudnative-pg/cloudnative-pg@sha256:923c267ec29636db3bee20f993d0ec4973fa22998e1adad37da79e4d32b5bc07` | `golang.org/x/net v0.58.0` | CVE-2026-78659 | 2026-12-27 |
| High | `ghcr.io/cloudnative-pg/cloudnative-pg@sha256:923c267ec29636db3bee20f993d0ec4973fa22998e1adad37da79e4d32b5bc07` | `golang.org/x/net v0.58.0` | CVE-2026-78660 | 2026-12-27 |
| High | `ghcr.io/cloudnative-pg/cloudnative-pg@sha256:923c267ec29636db3bee20f993d0ec4973fa22998e1adad37da79e4d32b5bc07` | `golang.org/x/net v0.58.0` | CVE-2026-78669 | 2026-12-27 |
| High | `ghcr.io/cloudnative-pg/cloudnative-pg@sha256:923c267ec29636db3bee20f993d0ec4973fa22998e1adad37da79e4d32b5bc07` | `golang.org/x/net v0.58.0` | CVE-2026-97032 | 2026-12-27 |
| High | `ghcr.io/cloudnative-pg/cloudnative-pg@sha256:923c267ec29636db3bee20f993d0ec4973fa22998e1adad37da79e4d32b5bc07` | `stdlib go1.27.1` | CVE-2026-56866 | 2026-12-27 |
| High | `ghcr.io/cloudnative-pg/cloudnative-pg@sha256:923c267ec29636db3bee20f993d0ec4973fa22998e1adad37da79e4d32b5bc07` | `stdlib go1.27.1` | CVE-2026-78659 | 2026-12-27 |
| High | `ghcr.io/cloudnative-pg/cloudnative-pg@sha256:923c267ec29636db3bee20f993d0ec4973fa22998e1adad37da79e4d32b5bc07` | `stdlib go1.27.1` | CVE-2026-78660 | 2026-12-27 |
| High | `ghcr.io/cloudnative-pg/cloudnative-pg@sha256:923c267ec29636db3bee20f993d0ec4973fa22998e1adad37da79e4d32b5bc07` | `stdlib go1.27.1` | CVE-2026-78667 | 2026-12-27 |
| High | `ghcr.io/cloudnative-pg/cloudnative-pg@sha256:923c267ec29636db3bee20f993d0ec4973fa22998e1adad37da79e4d32b5bc07` | `stdlib go1.27.1` | CVE-2026-78669 | 2026-12-27 |
| High | `ghcr.io/cloudnative-pg/cloudnative-pg@sha256:923c267ec29636db3bee20f993d0ec4973fa22998e1adad37da79e4d32b5bc07` | `stdlib go1.27.1` | CVE-2026-94439 | 2026-12-27 |
| High | `ghcr.io/cloudnative-pg/cloudnative-pg@sha256:923c267ec29636db3bee20f993d0ec4973fa22998e1adad37da79e4d32b5bc07` | `stdlib go1.27.1` | CVE-2026-94440 | 2026-12-27 |
| High | `ghcr.io/cloudnative-pg/cloudnative-pg@sha256:923c267ec29636db3bee20f993d0ec4973fa22998e1adad37da79e4d32b5bc07` | `stdlib go1.27.1` | CVE-2026-97031 | 2026-12-27 |
| High | `ghcr.io/cloudnative-pg/cloudnative-pg@sha256:923c267ec29636db3bee20f993d0ec4973fa22998e1adad37da79e4d32b5bc07` | `stdlib go1.27.1` | CVE-2026-97032 | 2026-12-27 |
| High | `quay.io/argoproj/argocd@sha256:13db7b10db23283b1b36f855046602e18539a8a8204c9f6f039e8896c8897518` | `github.com/go-jose/go-jose/v4 v4.1.4` | CVE-2026-116587 | 2026-12-27 |
| High | `quay.io/argoproj/argocd@sha256:13db7b10db23283b1b36f855046602e18539a8a8204c9f6f039e8896c8897518` | `github.com/klauspost/compress v1.18.0` | CVE-2026-63209 | 2026-12-27 |
| High | `quay.io/argoproj/argocd@sha256:13db7b10db23283b1b36f855046602e18539a8a8204c9f6f039e8896c8897518` | `golang.org/x/crypto v0.36.0` | CVE-2025-47913 | 2026-12-27 |
| High | `quay.io/argoproj/argocd@sha256:13db7b10db23283b1b36f855046602e18539a8a8204c9f6f039e8896c8897518` | `golang.org/x/crypto v0.36.0` | CVE-2026-39829 | 2026-12-27 |
| High | `quay.io/argoproj/argocd@sha256:13db7b10db23283b1b36f855046602e18539a8a8204c9f6f039e8896c8897518` | `golang.org/x/crypto v0.36.0` | CVE-2026-46597 | 2026-12-27 |
| High | `quay.io/argoproj/argocd@sha256:13db7b10db23283b1b36f855046602e18539a8a8204c9f6f039e8896c8897518` | `golang.org/x/crypto v0.36.0` | CVE-2026-56854 | 2026-12-27 |
| High | `quay.io/argoproj/argocd@sha256:13db7b10db23283b1b36f855046602e18539a8a8204c9f6f039e8896c8897518` | `golang.org/x/crypto v0.36.0` | CVE-2026-56855 | 2026-12-27 |
| High | `quay.io/argoproj/argocd@sha256:13db7b10db23283b1b36f855046602e18539a8a8204c9f6f039e8896c8897518` | `golang.org/x/crypto v0.36.0` | CVE-2026-78662 | 2026-12-27 |
| High | `quay.io/argoproj/argocd@sha256:13db7b10db23283b1b36f855046602e18539a8a8204c9f6f039e8896c8897518` | `golang.org/x/crypto v0.53.0` | CVE-2026-56854 | 2026-12-27 |
| High | `quay.io/argoproj/argocd@sha256:13db7b10db23283b1b36f855046602e18539a8a8204c9f6f039e8896c8897518` | `golang.org/x/crypto v0.53.0` | CVE-2026-56855 | 2026-12-27 |
| High | `quay.io/argoproj/argocd@sha256:13db7b10db23283b1b36f855046602e18539a8a8204c9f6f039e8896c8897518` | `golang.org/x/crypto v0.53.0` | CVE-2026-78662 | 2026-12-27 |
| High | `quay.io/argoproj/argocd@sha256:13db7b10db23283b1b36f855046602e18539a8a8204c9f6f039e8896c8897518` | `golang.org/x/net v0.38.0` | CVE-2026-33814 | 2026-12-27 |
| High | `quay.io/argoproj/argocd@sha256:13db7b10db23283b1b36f855046602e18539a8a8204c9f6f039e8896c8897518` | `golang.org/x/net v0.38.0` | CVE-2026-39821 | 2026-12-27 |
| High | `quay.io/argoproj/argocd@sha256:13db7b10db23283b1b36f855046602e18539a8a8204c9f6f039e8896c8897518` | `golang.org/x/net v0.38.0` | CVE-2026-46600 | 2026-12-27 |
| High | `quay.io/argoproj/argocd@sha256:13db7b10db23283b1b36f855046602e18539a8a8204c9f6f039e8896c8897518` | `golang.org/x/net v0.38.0` | CVE-2026-78659 | 2026-12-27 |
| High | `quay.io/argoproj/argocd@sha256:13db7b10db23283b1b36f855046602e18539a8a8204c9f6f039e8896c8897518` | `golang.org/x/net v0.38.0` | CVE-2026-78660 | 2026-12-27 |
| High | `quay.io/argoproj/argocd@sha256:13db7b10db23283b1b36f855046602e18539a8a8204c9f6f039e8896c8897518` | `golang.org/x/net v0.38.0` | CVE-2026-78669 | 2026-12-27 |
| High | `quay.io/argoproj/argocd@sha256:13db7b10db23283b1b36f855046602e18539a8a8204c9f6f039e8896c8897518` | `golang.org/x/net v0.38.0` | CVE-2026-97032 | 2026-12-27 |
| High | `quay.io/argoproj/argocd@sha256:13db7b10db23283b1b36f855046602e18539a8a8204c9f6f039e8896c8897518` | `golang.org/x/net v0.40.0` | CVE-2026-33814 | 2026-12-27 |
| High | `quay.io/argoproj/argocd@sha256:13db7b10db23283b1b36f855046602e18539a8a8204c9f6f039e8896c8897518` | `golang.org/x/net v0.40.0` | CVE-2026-39821 | 2026-12-27 |
| High | `quay.io/argoproj/argocd@sha256:13db7b10db23283b1b36f855046602e18539a8a8204c9f6f039e8896c8897518` | `golang.org/x/net v0.40.0` | CVE-2026-46600 | 2026-12-27 |
| High | `quay.io/argoproj/argocd@sha256:13db7b10db23283b1b36f855046602e18539a8a8204c9f6f039e8896c8897518` | `golang.org/x/net v0.40.0` | CVE-2026-78659 | 2026-12-27 |
| High | `quay.io/argoproj/argocd@sha256:13db7b10db23283b1b36f855046602e18539a8a8204c9f6f039e8896c8897518` | `golang.org/x/net v0.40.0` | CVE-2026-78660 | 2026-12-27 |
| High | `quay.io/argoproj/argocd@sha256:13db7b10db23283b1b36f855046602e18539a8a8204c9f6f039e8896c8897518` | `golang.org/x/net v0.40.0` | CVE-2026-78669 | 2026-12-27 |
| High | `quay.io/argoproj/argocd@sha256:13db7b10db23283b1b36f855046602e18539a8a8204c9f6f039e8896c8897518` | `golang.org/x/net v0.40.0` | CVE-2026-97032 | 2026-12-27 |
| High | `quay.io/argoproj/argocd@sha256:13db7b10db23283b1b36f855046602e18539a8a8204c9f6f039e8896c8897518` | `golang.org/x/net v0.55.0` | CVE-2026-46600 | 2026-12-27 |
| High | `quay.io/argoproj/argocd@sha256:13db7b10db23283b1b36f855046602e18539a8a8204c9f6f039e8896c8897518` | `golang.org/x/net v0.55.0` | CVE-2026-78659 | 2026-12-27 |
| High | `quay.io/argoproj/argocd@sha256:13db7b10db23283b1b36f855046602e18539a8a8204c9f6f039e8896c8897518` | `golang.org/x/net v0.55.0` | CVE-2026-78660 | 2026-12-27 |
| High | `quay.io/argoproj/argocd@sha256:13db7b10db23283b1b36f855046602e18539a8a8204c9f6f039e8896c8897518` | `golang.org/x/net v0.55.0` | CVE-2026-78669 | 2026-12-27 |
| High | `quay.io/argoproj/argocd@sha256:13db7b10db23283b1b36f855046602e18539a8a8204c9f6f039e8896c8897518` | `golang.org/x/net v0.55.0` | CVE-2026-97032 | 2026-12-27 |
| High | `quay.io/argoproj/argocd@sha256:13db7b10db23283b1b36f855046602e18539a8a8204c9f6f039e8896c8897518` | `golang.org/x/net v0.59.0` | CVE-2026-78659 | 2026-12-27 |
| High | `quay.io/argoproj/argocd@sha256:13db7b10db23283b1b36f855046602e18539a8a8204c9f6f039e8896c8897518` | `golang.org/x/net v0.59.0` | CVE-2026-78660 | 2026-12-27 |
| High | `quay.io/argoproj/argocd@sha256:13db7b10db23283b1b36f855046602e18539a8a8204c9f6f039e8896c8897518` | `golang.org/x/net v0.59.0` | CVE-2026-78669 | 2026-12-27 |
| High | `quay.io/argoproj/argocd@sha256:13db7b10db23283b1b36f855046602e18539a8a8204c9f6f039e8896c8897518` | `golang.org/x/net v0.59.0` | CVE-2026-97032 | 2026-12-27 |
| High | `quay.io/argoproj/argocd@sha256:13db7b10db23283b1b36f855046602e18539a8a8204c9f6f039e8896c8897518` | `golang.org/x/text v0.23.0` | CVE-2026-56851 | 2026-12-27 |
| High | `quay.io/argoproj/argocd@sha256:13db7b10db23283b1b36f855046602e18539a8a8204c9f6f039e8896c8897518` | `golang.org/x/text v0.23.0` | CVE-2026-56852 | 2026-12-27 |
| High | `quay.io/argoproj/argocd@sha256:13db7b10db23283b1b36f855046602e18539a8a8204c9f6f039e8896c8897518` | `golang.org/x/text v0.28.0` | CVE-2026-56851 | 2026-12-27 |
| High | `quay.io/argoproj/argocd@sha256:13db7b10db23283b1b36f855046602e18539a8a8204c9f6f039e8896c8897518` | `golang.org/x/text v0.28.0` | CVE-2026-56852 | 2026-12-27 |
| High | `quay.io/argoproj/argocd@sha256:13db7b10db23283b1b36f855046602e18539a8a8204c9f6f039e8896c8897518` | `golang.org/x/text v0.38.0` | CVE-2026-56851 | 2026-12-27 |
| High | `quay.io/argoproj/argocd@sha256:13db7b10db23283b1b36f855046602e18539a8a8204c9f6f039e8896c8897518` | `golang.org/x/text v0.38.0` | CVE-2026-56852 | 2026-12-27 |
| High | `quay.io/argoproj/argocd@sha256:13db7b10db23283b1b36f855046602e18539a8a8204c9f6f039e8896c8897518` | `libcurl3t64-gnutls 8.18.0-1ubuntu2.7` | CVE-2026-92392 | 2026-12-27 |
| High | `quay.io/argoproj/argocd@sha256:13db7b10db23283b1b36f855046602e18539a8a8204c9f6f039e8896c8897518` | `oras.land/oras-go/v2 v2.6.1` | CVE-2026-50163 | 2026-12-27 |
| High | `quay.io/argoproj/argocd@sha256:13db7b10db23283b1b36f855046602e18539a8a8204c9f6f039e8896c8897518` | `oras.land/oras-go/v2 v2.6.1` | CVE-2026-85731 | 2026-12-27 |
| High | `quay.io/argoproj/argocd@sha256:13db7b10db23283b1b36f855046602e18539a8a8204c9f6f039e8896c8897518` | `stdlib go1.24.0` | CVE-2025-22874 | 2026-12-27 |
| High | `quay.io/argoproj/argocd@sha256:13db7b10db23283b1b36f855046602e18539a8a8204c9f6f039e8896c8897518` | `stdlib go1.24.0` | CVE-2025-47907 | 2026-12-27 |
| High | `quay.io/argoproj/argocd@sha256:13db7b10db23283b1b36f855046602e18539a8a8204c9f6f039e8896c8897518` | `stdlib go1.24.0` | CVE-2025-58187 | 2026-12-27 |
| High | `quay.io/argoproj/argocd@sha256:13db7b10db23283b1b36f855046602e18539a8a8204c9f6f039e8896c8897518` | `stdlib go1.24.0` | CVE-2025-58188 | 2026-12-27 |
| High | `quay.io/argoproj/argocd@sha256:13db7b10db23283b1b36f855046602e18539a8a8204c9f6f039e8896c8897518` | `stdlib go1.24.0` | CVE-2025-61723 | 2026-12-27 |
| High | `quay.io/argoproj/argocd@sha256:13db7b10db23283b1b36f855046602e18539a8a8204c9f6f039e8896c8897518` | `stdlib go1.24.0` | CVE-2025-61725 | 2026-12-27 |
| High | `quay.io/argoproj/argocd@sha256:13db7b10db23283b1b36f855046602e18539a8a8204c9f6f039e8896c8897518` | `stdlib go1.24.0` | CVE-2025-61726 | 2026-12-27 |
| High | `quay.io/argoproj/argocd@sha256:13db7b10db23283b1b36f855046602e18539a8a8204c9f6f039e8896c8897518` | `stdlib go1.24.0` | CVE-2025-61729 | 2026-12-27 |
| High | `quay.io/argoproj/argocd@sha256:13db7b10db23283b1b36f855046602e18539a8a8204c9f6f039e8896c8897518` | `stdlib go1.24.0` | CVE-2026-25679 | 2026-12-27 |
| High | `quay.io/argoproj/argocd@sha256:13db7b10db23283b1b36f855046602e18539a8a8204c9f6f039e8896c8897518` | `stdlib go1.24.0` | CVE-2026-27145 | 2026-12-27 |
| High | `quay.io/argoproj/argocd@sha256:13db7b10db23283b1b36f855046602e18539a8a8204c9f6f039e8896c8897518` | `stdlib go1.24.0` | CVE-2026-32280 | 2026-12-27 |
| High | `quay.io/argoproj/argocd@sha256:13db7b10db23283b1b36f855046602e18539a8a8204c9f6f039e8896c8897518` | `stdlib go1.24.0` | CVE-2026-32281 | 2026-12-27 |
| High | `quay.io/argoproj/argocd@sha256:13db7b10db23283b1b36f855046602e18539a8a8204c9f6f039e8896c8897518` | `stdlib go1.24.0` | CVE-2026-32283 | 2026-12-27 |
| High | `quay.io/argoproj/argocd@sha256:13db7b10db23283b1b36f855046602e18539a8a8204c9f6f039e8896c8897518` | `stdlib go1.24.0` | CVE-2026-33811 | 2026-12-27 |
| High | `quay.io/argoproj/argocd@sha256:13db7b10db23283b1b36f855046602e18539a8a8204c9f6f039e8896c8897518` | `stdlib go1.24.0` | CVE-2026-33814 | 2026-12-27 |
| High | `quay.io/argoproj/argocd@sha256:13db7b10db23283b1b36f855046602e18539a8a8204c9f6f039e8896c8897518` | `stdlib go1.24.0` | CVE-2026-33818 | 2026-12-27 |
| High | `quay.io/argoproj/argocd@sha256:13db7b10db23283b1b36f855046602e18539a8a8204c9f6f039e8896c8897518` | `stdlib go1.24.0` | CVE-2026-39820 | 2026-12-27 |
| High | `quay.io/argoproj/argocd@sha256:13db7b10db23283b1b36f855046602e18539a8a8204c9f6f039e8896c8897518` | `stdlib go1.24.0` | CVE-2026-39821 | 2026-12-27 |
| High | `quay.io/argoproj/argocd@sha256:13db7b10db23283b1b36f855046602e18539a8a8204c9f6f039e8896c8897518` | `stdlib go1.24.0` | CVE-2026-39822 | 2026-12-27 |
| High | `quay.io/argoproj/argocd@sha256:13db7b10db23283b1b36f855046602e18539a8a8204c9f6f039e8896c8897518` | `stdlib go1.24.0` | CVE-2026-39836 | 2026-12-27 |
| High | `quay.io/argoproj/argocd@sha256:13db7b10db23283b1b36f855046602e18539a8a8204c9f6f039e8896c8897518` | `stdlib go1.24.0` | CVE-2026-42499 | 2026-12-27 |
| High | `quay.io/argoproj/argocd@sha256:13db7b10db23283b1b36f855046602e18539a8a8204c9f6f039e8896c8897518` | `stdlib go1.24.0` | CVE-2026-42504 | 2026-12-27 |
| High | `quay.io/argoproj/argocd@sha256:13db7b10db23283b1b36f855046602e18539a8a8204c9f6f039e8896c8897518` | `stdlib go1.24.0` | CVE-2026-56853 | 2026-12-27 |
| High | `quay.io/argoproj/argocd@sha256:13db7b10db23283b1b36f855046602e18539a8a8204c9f6f039e8896c8897518` | `stdlib go1.24.0` | CVE-2026-56859 | 2026-12-27 |
| High | `quay.io/argoproj/argocd@sha256:13db7b10db23283b1b36f855046602e18539a8a8204c9f6f039e8896c8897518` | `stdlib go1.24.0` | CVE-2026-56862 | 2026-12-27 |
| High | `quay.io/argoproj/argocd@sha256:13db7b10db23283b1b36f855046602e18539a8a8204c9f6f039e8896c8897518` | `stdlib go1.24.0` | CVE-2026-56866 | 2026-12-27 |
| High | `quay.io/argoproj/argocd@sha256:13db7b10db23283b1b36f855046602e18539a8a8204c9f6f039e8896c8897518` | `stdlib go1.24.0` | CVE-2026-78659 | 2026-12-27 |
| High | `quay.io/argoproj/argocd@sha256:13db7b10db23283b1b36f855046602e18539a8a8204c9f6f039e8896c8897518` | `stdlib go1.24.0` | CVE-2026-78660 | 2026-12-27 |
| High | `quay.io/argoproj/argocd@sha256:13db7b10db23283b1b36f855046602e18539a8a8204c9f6f039e8896c8897518` | `stdlib go1.24.0` | CVE-2026-78667 | 2026-12-27 |
| High | `quay.io/argoproj/argocd@sha256:13db7b10db23283b1b36f855046602e18539a8a8204c9f6f039e8896c8897518` | `stdlib go1.24.0` | CVE-2026-78669 | 2026-12-27 |
| High | `quay.io/argoproj/argocd@sha256:13db7b10db23283b1b36f855046602e18539a8a8204c9f6f039e8896c8897518` | `stdlib go1.24.0` | CVE-2026-94439 | 2026-12-27 |
| High | `quay.io/argoproj/argocd@sha256:13db7b10db23283b1b36f855046602e18539a8a8204c9f6f039e8896c8897518` | `stdlib go1.24.0` | CVE-2026-94440 | 2026-12-27 |
| High | `quay.io/argoproj/argocd@sha256:13db7b10db23283b1b36f855046602e18539a8a8204c9f6f039e8896c8897518` | `stdlib go1.24.0` | CVE-2026-97031 | 2026-12-27 |
| High | `quay.io/argoproj/argocd@sha256:13db7b10db23283b1b36f855046602e18539a8a8204c9f6f039e8896c8897518` | `stdlib go1.24.0` | CVE-2026-97032 | 2026-12-27 |
| High | `quay.io/argoproj/argocd@sha256:13db7b10db23283b1b36f855046602e18539a8a8204c9f6f039e8896c8897518` | `stdlib go1.25.3` | CVE-2025-61726 | 2026-12-27 |
| High | `quay.io/argoproj/argocd@sha256:13db7b10db23283b1b36f855046602e18539a8a8204c9f6f039e8896c8897518` | `stdlib go1.25.3` | CVE-2025-61729 | 2026-12-27 |
| High | `quay.io/argoproj/argocd@sha256:13db7b10db23283b1b36f855046602e18539a8a8204c9f6f039e8896c8897518` | `stdlib go1.25.3` | CVE-2026-25679 | 2026-12-27 |
| High | `quay.io/argoproj/argocd@sha256:13db7b10db23283b1b36f855046602e18539a8a8204c9f6f039e8896c8897518` | `stdlib go1.25.3` | CVE-2026-27145 | 2026-12-27 |
| High | `quay.io/argoproj/argocd@sha256:13db7b10db23283b1b36f855046602e18539a8a8204c9f6f039e8896c8897518` | `stdlib go1.25.3` | CVE-2026-32280 | 2026-12-27 |
| High | `quay.io/argoproj/argocd@sha256:13db7b10db23283b1b36f855046602e18539a8a8204c9f6f039e8896c8897518` | `stdlib go1.25.3` | CVE-2026-32281 | 2026-12-27 |
| High | `quay.io/argoproj/argocd@sha256:13db7b10db23283b1b36f855046602e18539a8a8204c9f6f039e8896c8897518` | `stdlib go1.25.3` | CVE-2026-32283 | 2026-12-27 |
| High | `quay.io/argoproj/argocd@sha256:13db7b10db23283b1b36f855046602e18539a8a8204c9f6f039e8896c8897518` | `stdlib go1.25.3` | CVE-2026-33811 | 2026-12-27 |
| High | `quay.io/argoproj/argocd@sha256:13db7b10db23283b1b36f855046602e18539a8a8204c9f6f039e8896c8897518` | `stdlib go1.25.3` | CVE-2026-33814 | 2026-12-27 |
| High | `quay.io/argoproj/argocd@sha256:13db7b10db23283b1b36f855046602e18539a8a8204c9f6f039e8896c8897518` | `stdlib go1.25.3` | CVE-2026-33818 | 2026-12-27 |
| High | `quay.io/argoproj/argocd@sha256:13db7b10db23283b1b36f855046602e18539a8a8204c9f6f039e8896c8897518` | `stdlib go1.25.3` | CVE-2026-39820 | 2026-12-27 |
| High | `quay.io/argoproj/argocd@sha256:13db7b10db23283b1b36f855046602e18539a8a8204c9f6f039e8896c8897518` | `stdlib go1.25.3` | CVE-2026-39821 | 2026-12-27 |
| High | `quay.io/argoproj/argocd@sha256:13db7b10db23283b1b36f855046602e18539a8a8204c9f6f039e8896c8897518` | `stdlib go1.25.3` | CVE-2026-39822 | 2026-12-27 |
| High | `quay.io/argoproj/argocd@sha256:13db7b10db23283b1b36f855046602e18539a8a8204c9f6f039e8896c8897518` | `stdlib go1.25.3` | CVE-2026-39836 | 2026-12-27 |
| High | `quay.io/argoproj/argocd@sha256:13db7b10db23283b1b36f855046602e18539a8a8204c9f6f039e8896c8897518` | `stdlib go1.25.3` | CVE-2026-42499 | 2026-12-27 |
| High | `quay.io/argoproj/argocd@sha256:13db7b10db23283b1b36f855046602e18539a8a8204c9f6f039e8896c8897518` | `stdlib go1.25.3` | CVE-2026-42504 | 2026-12-27 |
| High | `quay.io/argoproj/argocd@sha256:13db7b10db23283b1b36f855046602e18539a8a8204c9f6f039e8896c8897518` | `stdlib go1.25.3` | CVE-2026-56853 | 2026-12-27 |
| High | `quay.io/argoproj/argocd@sha256:13db7b10db23283b1b36f855046602e18539a8a8204c9f6f039e8896c8897518` | `stdlib go1.25.3` | CVE-2026-56859 | 2026-12-27 |
| High | `quay.io/argoproj/argocd@sha256:13db7b10db23283b1b36f855046602e18539a8a8204c9f6f039e8896c8897518` | `stdlib go1.25.3` | CVE-2026-56862 | 2026-12-27 |
| High | `quay.io/argoproj/argocd@sha256:13db7b10db23283b1b36f855046602e18539a8a8204c9f6f039e8896c8897518` | `stdlib go1.25.3` | CVE-2026-56866 | 2026-12-27 |
| High | `quay.io/argoproj/argocd@sha256:13db7b10db23283b1b36f855046602e18539a8a8204c9f6f039e8896c8897518` | `stdlib go1.25.3` | CVE-2026-78659 | 2026-12-27 |
| High | `quay.io/argoproj/argocd@sha256:13db7b10db23283b1b36f855046602e18539a8a8204c9f6f039e8896c8897518` | `stdlib go1.25.3` | CVE-2026-78660 | 2026-12-27 |
| High | `quay.io/argoproj/argocd@sha256:13db7b10db23283b1b36f855046602e18539a8a8204c9f6f039e8896c8897518` | `stdlib go1.25.3` | CVE-2026-78667 | 2026-12-27 |
| High | `quay.io/argoproj/argocd@sha256:13db7b10db23283b1b36f855046602e18539a8a8204c9f6f039e8896c8897518` | `stdlib go1.25.3` | CVE-2026-78669 | 2026-12-27 |
| High | `quay.io/argoproj/argocd@sha256:13db7b10db23283b1b36f855046602e18539a8a8204c9f6f039e8896c8897518` | `stdlib go1.25.3` | CVE-2026-94439 | 2026-12-27 |
| High | `quay.io/argoproj/argocd@sha256:13db7b10db23283b1b36f855046602e18539a8a8204c9f6f039e8896c8897518` | `stdlib go1.25.3` | CVE-2026-94440 | 2026-12-27 |
| High | `quay.io/argoproj/argocd@sha256:13db7b10db23283b1b36f855046602e18539a8a8204c9f6f039e8896c8897518` | `stdlib go1.25.3` | CVE-2026-97031 | 2026-12-27 |
| High | `quay.io/argoproj/argocd@sha256:13db7b10db23283b1b36f855046602e18539a8a8204c9f6f039e8896c8897518` | `stdlib go1.25.3` | CVE-2026-97032 | 2026-12-27 |
| High | `quay.io/argoproj/argocd@sha256:13db7b10db23283b1b36f855046602e18539a8a8204c9f6f039e8896c8897518` | `stdlib go1.26.2` | CVE-2026-27145 | 2026-12-27 |
| High | `quay.io/argoproj/argocd@sha256:13db7b10db23283b1b36f855046602e18539a8a8204c9f6f039e8896c8897518` | `stdlib go1.26.2` | CVE-2026-33811 | 2026-12-27 |
| High | `quay.io/argoproj/argocd@sha256:13db7b10db23283b1b36f855046602e18539a8a8204c9f6f039e8896c8897518` | `stdlib go1.26.2` | CVE-2026-33814 | 2026-12-27 |
| High | `quay.io/argoproj/argocd@sha256:13db7b10db23283b1b36f855046602e18539a8a8204c9f6f039e8896c8897518` | `stdlib go1.26.2` | CVE-2026-33818 | 2026-12-27 |
| High | `quay.io/argoproj/argocd@sha256:13db7b10db23283b1b36f855046602e18539a8a8204c9f6f039e8896c8897518` | `stdlib go1.26.2` | CVE-2026-39820 | 2026-12-27 |
| High | `quay.io/argoproj/argocd@sha256:13db7b10db23283b1b36f855046602e18539a8a8204c9f6f039e8896c8897518` | `stdlib go1.26.2` | CVE-2026-39821 | 2026-12-27 |
| High | `quay.io/argoproj/argocd@sha256:13db7b10db23283b1b36f855046602e18539a8a8204c9f6f039e8896c8897518` | `stdlib go1.26.2` | CVE-2026-39822 | 2026-12-27 |
| High | `quay.io/argoproj/argocd@sha256:13db7b10db23283b1b36f855046602e18539a8a8204c9f6f039e8896c8897518` | `stdlib go1.26.2` | CVE-2026-39836 | 2026-12-27 |
| High | `quay.io/argoproj/argocd@sha256:13db7b10db23283b1b36f855046602e18539a8a8204c9f6f039e8896c8897518` | `stdlib go1.26.2` | CVE-2026-42499 | 2026-12-27 |
| High | `quay.io/argoproj/argocd@sha256:13db7b10db23283b1b36f855046602e18539a8a8204c9f6f039e8896c8897518` | `stdlib go1.26.2` | CVE-2026-42504 | 2026-12-27 |
| High | `quay.io/argoproj/argocd@sha256:13db7b10db23283b1b36f855046602e18539a8a8204c9f6f039e8896c8897518` | `stdlib go1.26.2` | CVE-2026-46600 | 2026-12-27 |
| High | `quay.io/argoproj/argocd@sha256:13db7b10db23283b1b36f855046602e18539a8a8204c9f6f039e8896c8897518` | `stdlib go1.26.2` | CVE-2026-56853 | 2026-12-27 |
| High | `quay.io/argoproj/argocd@sha256:13db7b10db23283b1b36f855046602e18539a8a8204c9f6f039e8896c8897518` | `stdlib go1.26.2` | CVE-2026-56859 | 2026-12-27 |
| High | `quay.io/argoproj/argocd@sha256:13db7b10db23283b1b36f855046602e18539a8a8204c9f6f039e8896c8897518` | `stdlib go1.26.2` | CVE-2026-56862 | 2026-12-27 |
| High | `quay.io/argoproj/argocd@sha256:13db7b10db23283b1b36f855046602e18539a8a8204c9f6f039e8896c8897518` | `stdlib go1.26.2` | CVE-2026-56866 | 2026-12-27 |
| High | `quay.io/argoproj/argocd@sha256:13db7b10db23283b1b36f855046602e18539a8a8204c9f6f039e8896c8897518` | `stdlib go1.26.2` | CVE-2026-78659 | 2026-12-27 |
| High | `quay.io/argoproj/argocd@sha256:13db7b10db23283b1b36f855046602e18539a8a8204c9f6f039e8896c8897518` | `stdlib go1.26.2` | CVE-2026-78660 | 2026-12-27 |
| High | `quay.io/argoproj/argocd@sha256:13db7b10db23283b1b36f855046602e18539a8a8204c9f6f039e8896c8897518` | `stdlib go1.26.2` | CVE-2026-78667 | 2026-12-27 |
| High | `quay.io/argoproj/argocd@sha256:13db7b10db23283b1b36f855046602e18539a8a8204c9f6f039e8896c8897518` | `stdlib go1.26.2` | CVE-2026-78669 | 2026-12-27 |
| High | `quay.io/argoproj/argocd@sha256:13db7b10db23283b1b36f855046602e18539a8a8204c9f6f039e8896c8897518` | `stdlib go1.26.2` | CVE-2026-94439 | 2026-12-27 |
| High | `quay.io/argoproj/argocd@sha256:13db7b10db23283b1b36f855046602e18539a8a8204c9f6f039e8896c8897518` | `stdlib go1.26.2` | CVE-2026-94440 | 2026-12-27 |
| High | `quay.io/argoproj/argocd@sha256:13db7b10db23283b1b36f855046602e18539a8a8204c9f6f039e8896c8897518` | `stdlib go1.26.2` | CVE-2026-97031 | 2026-12-27 |
| High | `quay.io/argoproj/argocd@sha256:13db7b10db23283b1b36f855046602e18539a8a8204c9f6f039e8896c8897518` | `stdlib go1.26.2` | CVE-2026-97032 | 2026-12-27 |
| High | `quay.io/argoproj/argocd@sha256:13db7b10db23283b1b36f855046602e18539a8a8204c9f6f039e8896c8897518` | `stdlib go1.26.4` | CVE-2026-33818 | 2026-12-27 |
| High | `quay.io/argoproj/argocd@sha256:13db7b10db23283b1b36f855046602e18539a8a8204c9f6f039e8896c8897518` | `stdlib go1.26.4` | CVE-2026-39821 | 2026-12-27 |
| High | `quay.io/argoproj/argocd@sha256:13db7b10db23283b1b36f855046602e18539a8a8204c9f6f039e8896c8897518` | `stdlib go1.26.4` | CVE-2026-39822 | 2026-12-27 |
| High | `quay.io/argoproj/argocd@sha256:13db7b10db23283b1b36f855046602e18539a8a8204c9f6f039e8896c8897518` | `stdlib go1.26.4` | CVE-2026-46600 | 2026-12-27 |
| High | `quay.io/argoproj/argocd@sha256:13db7b10db23283b1b36f855046602e18539a8a8204c9f6f039e8896c8897518` | `stdlib go1.26.4` | CVE-2026-56853 | 2026-12-27 |
| High | `quay.io/argoproj/argocd@sha256:13db7b10db23283b1b36f855046602e18539a8a8204c9f6f039e8896c8897518` | `stdlib go1.26.4` | CVE-2026-56859 | 2026-12-27 |
| High | `quay.io/argoproj/argocd@sha256:13db7b10db23283b1b36f855046602e18539a8a8204c9f6f039e8896c8897518` | `stdlib go1.26.4` | CVE-2026-56862 | 2026-12-27 |
| High | `quay.io/argoproj/argocd@sha256:13db7b10db23283b1b36f855046602e18539a8a8204c9f6f039e8896c8897518` | `stdlib go1.26.4` | CVE-2026-56866 | 2026-12-27 |
| High | `quay.io/argoproj/argocd@sha256:13db7b10db23283b1b36f855046602e18539a8a8204c9f6f039e8896c8897518` | `stdlib go1.26.4` | CVE-2026-78659 | 2026-12-27 |
| High | `quay.io/argoproj/argocd@sha256:13db7b10db23283b1b36f855046602e18539a8a8204c9f6f039e8896c8897518` | `stdlib go1.26.4` | CVE-2026-78660 | 2026-12-27 |
| High | `quay.io/argoproj/argocd@sha256:13db7b10db23283b1b36f855046602e18539a8a8204c9f6f039e8896c8897518` | `stdlib go1.26.4` | CVE-2026-78667 | 2026-12-27 |
| High | `quay.io/argoproj/argocd@sha256:13db7b10db23283b1b36f855046602e18539a8a8204c9f6f039e8896c8897518` | `stdlib go1.26.4` | CVE-2026-78669 | 2026-12-27 |
| High | `quay.io/argoproj/argocd@sha256:13db7b10db23283b1b36f855046602e18539a8a8204c9f6f039e8896c8897518` | `stdlib go1.26.4` | CVE-2026-94439 | 2026-12-27 |
| High | `quay.io/argoproj/argocd@sha256:13db7b10db23283b1b36f855046602e18539a8a8204c9f6f039e8896c8897518` | `stdlib go1.26.4` | CVE-2026-94440 | 2026-12-27 |
| High | `quay.io/argoproj/argocd@sha256:13db7b10db23283b1b36f855046602e18539a8a8204c9f6f039e8896c8897518` | `stdlib go1.26.4` | CVE-2026-97031 | 2026-12-27 |
| High | `quay.io/argoproj/argocd@sha256:13db7b10db23283b1b36f855046602e18539a8a8204c9f6f039e8896c8897518` | `stdlib go1.26.4` | CVE-2026-97032 | 2026-12-27 |
| High | `quay.io/cilium/cilium-envoy@sha256:af7382699576b9e65e9184efa52eeca0b58aea70ad6e511bf260c91d9f740463` | `golang.org/x/net v0.58.0` | CVE-2026-78659 | 2026-12-27 |
| High | `quay.io/cilium/cilium-envoy@sha256:af7382699576b9e65e9184efa52eeca0b58aea70ad6e511bf260c91d9f740463` | `golang.org/x/net v0.58.0` | CVE-2026-78660 | 2026-12-27 |
| High | `quay.io/cilium/cilium-envoy@sha256:af7382699576b9e65e9184efa52eeca0b58aea70ad6e511bf260c91d9f740463` | `golang.org/x/net v0.58.0` | CVE-2026-78669 | 2026-12-27 |
| High | `quay.io/cilium/cilium-envoy@sha256:af7382699576b9e65e9184efa52eeca0b58aea70ad6e511bf260c91d9f740463` | `golang.org/x/net v0.58.0` | CVE-2026-97032 | 2026-12-27 |
| High | `quay.io/cilium/cilium-envoy@sha256:af7382699576b9e65e9184efa52eeca0b58aea70ad6e511bf260c91d9f740463` | `libssl3t64 3.0.13-0ubuntu3.15` | CVE-2026-84782 | 2026-12-27 |
| High | `quay.io/cilium/cilium-envoy@sha256:af7382699576b9e65e9184efa52eeca0b58aea70ad6e511bf260c91d9f740463` | `openssl 3.0.13-0ubuntu3.15` | CVE-2026-84782 | 2026-12-27 |
| High | `quay.io/cilium/cilium-envoy@sha256:af7382699576b9e65e9184efa52eeca0b58aea70ad6e511bf260c91d9f740463` | `stdlib go1.27.1` | CVE-2026-56866 | 2026-12-27 |
| High | `quay.io/cilium/cilium-envoy@sha256:af7382699576b9e65e9184efa52eeca0b58aea70ad6e511bf260c91d9f740463` | `stdlib go1.27.1` | CVE-2026-78659 | 2026-12-27 |
| High | `quay.io/cilium/cilium-envoy@sha256:af7382699576b9e65e9184efa52eeca0b58aea70ad6e511bf260c91d9f740463` | `stdlib go1.27.1` | CVE-2026-78660 | 2026-12-27 |
| High | `quay.io/cilium/cilium-envoy@sha256:af7382699576b9e65e9184efa52eeca0b58aea70ad6e511bf260c91d9f740463` | `stdlib go1.27.1` | CVE-2026-78667 | 2026-12-27 |
| High | `quay.io/cilium/cilium-envoy@sha256:af7382699576b9e65e9184efa52eeca0b58aea70ad6e511bf260c91d9f740463` | `stdlib go1.27.1` | CVE-2026-78669 | 2026-12-27 |
| High | `quay.io/cilium/cilium-envoy@sha256:af7382699576b9e65e9184efa52eeca0b58aea70ad6e511bf260c91d9f740463` | `stdlib go1.27.1` | CVE-2026-94439 | 2026-12-27 |
| High | `quay.io/cilium/cilium-envoy@sha256:af7382699576b9e65e9184efa52eeca0b58aea70ad6e511bf260c91d9f740463` | `stdlib go1.27.1` | CVE-2026-94440 | 2026-12-27 |
| High | `quay.io/cilium/cilium-envoy@sha256:af7382699576b9e65e9184efa52eeca0b58aea70ad6e511bf260c91d9f740463` | `stdlib go1.27.1` | CVE-2026-97031 | 2026-12-27 |
| High | `quay.io/cilium/cilium-envoy@sha256:af7382699576b9e65e9184efa52eeca0b58aea70ad6e511bf260c91d9f740463` | `stdlib go1.27.1` | CVE-2026-97032 | 2026-12-27 |
| High | `quay.io/cilium/cilium@sha256:2939231d0d3e3ebddcd80fffa168b7ddcc78fdf0dc864d1c8c126ff523c54f01` | `github.com/klauspost/compress v1.18.6` | CVE-2026-63209 | 2026-12-27 |
| High | `quay.io/cilium/cilium@sha256:2939231d0d3e3ebddcd80fffa168b7ddcc78fdf0dc864d1c8c126ff523c54f01` | `go.etcd.io/etcd/client/pkg/v3 v3.6.12` | CVE-2026-73500 | 2026-12-27 |
| High | `quay.io/cilium/cilium@sha256:2939231d0d3e3ebddcd80fffa168b7ddcc78fdf0dc864d1c8c126ff523c54f01` | `golang.org/x/crypto v0.53.0` | CVE-2026-56854 | 2026-12-27 |
| High | `quay.io/cilium/cilium@sha256:2939231d0d3e3ebddcd80fffa168b7ddcc78fdf0dc864d1c8c126ff523c54f01` | `golang.org/x/crypto v0.53.0` | CVE-2026-56855 | 2026-12-27 |
| High | `quay.io/cilium/cilium@sha256:2939231d0d3e3ebddcd80fffa168b7ddcc78fdf0dc864d1c8c126ff523c54f01` | `golang.org/x/crypto v0.53.0` | CVE-2026-78662 | 2026-12-27 |
| High | `quay.io/cilium/cilium@sha256:2939231d0d3e3ebddcd80fffa168b7ddcc78fdf0dc864d1c8c126ff523c54f01` | `golang.org/x/net v0.56.0` | CVE-2026-78659 | 2026-12-27 |
| High | `quay.io/cilium/cilium@sha256:2939231d0d3e3ebddcd80fffa168b7ddcc78fdf0dc864d1c8c126ff523c54f01` | `golang.org/x/net v0.56.0` | CVE-2026-78660 | 2026-12-27 |
| High | `quay.io/cilium/cilium@sha256:2939231d0d3e3ebddcd80fffa168b7ddcc78fdf0dc864d1c8c126ff523c54f01` | `golang.org/x/net v0.56.0` | CVE-2026-78669 | 2026-12-27 |
| High | `quay.io/cilium/cilium@sha256:2939231d0d3e3ebddcd80fffa168b7ddcc78fdf0dc864d1c8c126ff523c54f01` | `golang.org/x/net v0.56.0` | CVE-2026-97032 | 2026-12-27 |
| High | `quay.io/cilium/cilium@sha256:2939231d0d3e3ebddcd80fffa168b7ddcc78fdf0dc864d1c8c126ff523c54f01` | `golang.org/x/text v0.39.0` | CVE-2026-56851 | 2026-12-27 |
| High | `quay.io/cilium/cilium@sha256:2939231d0d3e3ebddcd80fffa168b7ddcc78fdf0dc864d1c8c126ff523c54f01` | `google.golang.org/grpc v1.83.1` | CVE-2026-84445 | 2026-12-27 |
| High | `quay.io/cilium/cilium@sha256:2939231d0d3e3ebddcd80fffa168b7ddcc78fdf0dc864d1c8c126ff523c54f01` | `libssl3t64 3.5.5-1ubuntu3.5` | CVE-2026-84782 | 2026-12-27 |
| High | `quay.io/cilium/cilium@sha256:2939231d0d3e3ebddcd80fffa168b7ddcc78fdf0dc864d1c8c126ff523c54f01` | `openssl 3.5.5-1ubuntu3.5` | CVE-2026-84782 | 2026-12-27 |
| High | `quay.io/cilium/cilium@sha256:2939231d0d3e3ebddcd80fffa168b7ddcc78fdf0dc864d1c8c126ff523c54f01` | `openssl-provider-legacy 3.5.5-1ubuntu3.5` | CVE-2026-84782 | 2026-12-27 |
| High | `quay.io/cilium/cilium@sha256:2939231d0d3e3ebddcd80fffa168b7ddcc78fdf0dc864d1c8c126ff523c54f01` | `stdlib go1.26.5` | CVE-2026-33818 | 2026-12-27 |
| High | `quay.io/cilium/cilium@sha256:2939231d0d3e3ebddcd80fffa168b7ddcc78fdf0dc864d1c8c126ff523c54f01` | `stdlib go1.26.5` | CVE-2026-39821 | 2026-12-27 |
| High | `quay.io/cilium/cilium@sha256:2939231d0d3e3ebddcd80fffa168b7ddcc78fdf0dc864d1c8c126ff523c54f01` | `stdlib go1.26.5` | CVE-2026-46600 | 2026-12-27 |
| High | `quay.io/cilium/cilium@sha256:2939231d0d3e3ebddcd80fffa168b7ddcc78fdf0dc864d1c8c126ff523c54f01` | `stdlib go1.26.5` | CVE-2026-56853 | 2026-12-27 |
| High | `quay.io/cilium/cilium@sha256:2939231d0d3e3ebddcd80fffa168b7ddcc78fdf0dc864d1c8c126ff523c54f01` | `stdlib go1.26.5` | CVE-2026-56859 | 2026-12-27 |
| High | `quay.io/cilium/cilium@sha256:2939231d0d3e3ebddcd80fffa168b7ddcc78fdf0dc864d1c8c126ff523c54f01` | `stdlib go1.26.5` | CVE-2026-56862 | 2026-12-27 |
| High | `quay.io/cilium/cilium@sha256:2939231d0d3e3ebddcd80fffa168b7ddcc78fdf0dc864d1c8c126ff523c54f01` | `stdlib go1.26.5` | CVE-2026-56866 | 2026-12-27 |
| High | `quay.io/cilium/cilium@sha256:2939231d0d3e3ebddcd80fffa168b7ddcc78fdf0dc864d1c8c126ff523c54f01` | `stdlib go1.26.5` | CVE-2026-78659 | 2026-12-27 |
| High | `quay.io/cilium/cilium@sha256:2939231d0d3e3ebddcd80fffa168b7ddcc78fdf0dc864d1c8c126ff523c54f01` | `stdlib go1.26.5` | CVE-2026-78660 | 2026-12-27 |
| High | `quay.io/cilium/cilium@sha256:2939231d0d3e3ebddcd80fffa168b7ddcc78fdf0dc864d1c8c126ff523c54f01` | `stdlib go1.26.5` | CVE-2026-78667 | 2026-12-27 |
| High | `quay.io/cilium/cilium@sha256:2939231d0d3e3ebddcd80fffa168b7ddcc78fdf0dc864d1c8c126ff523c54f01` | `stdlib go1.26.5` | CVE-2026-78669 | 2026-12-27 |
| High | `quay.io/cilium/cilium@sha256:2939231d0d3e3ebddcd80fffa168b7ddcc78fdf0dc864d1c8c126ff523c54f01` | `stdlib go1.26.5` | CVE-2026-94439 | 2026-12-27 |
| High | `quay.io/cilium/cilium@sha256:2939231d0d3e3ebddcd80fffa168b7ddcc78fdf0dc864d1c8c126ff523c54f01` | `stdlib go1.26.5` | CVE-2026-94440 | 2026-12-27 |
| High | `quay.io/cilium/cilium@sha256:2939231d0d3e3ebddcd80fffa168b7ddcc78fdf0dc864d1c8c126ff523c54f01` | `stdlib go1.26.5` | CVE-2026-97031 | 2026-12-27 |
| High | `quay.io/cilium/cilium@sha256:2939231d0d3e3ebddcd80fffa168b7ddcc78fdf0dc864d1c8c126ff523c54f01` | `stdlib go1.26.5` | CVE-2026-97032 | 2026-12-27 |
| High | `quay.io/cilium/cilium@sha256:2939231d0d3e3ebddcd80fffa168b7ddcc78fdf0dc864d1c8c126ff523c54f01` | `stdlib go1.26.8` | CVE-2026-56866 | 2026-12-27 |
| High | `quay.io/cilium/cilium@sha256:2939231d0d3e3ebddcd80fffa168b7ddcc78fdf0dc864d1c8c126ff523c54f01` | `stdlib go1.26.8` | CVE-2026-78659 | 2026-12-27 |
| High | `quay.io/cilium/cilium@sha256:2939231d0d3e3ebddcd80fffa168b7ddcc78fdf0dc864d1c8c126ff523c54f01` | `stdlib go1.26.8` | CVE-2026-78660 | 2026-12-27 |
| High | `quay.io/cilium/cilium@sha256:2939231d0d3e3ebddcd80fffa168b7ddcc78fdf0dc864d1c8c126ff523c54f01` | `stdlib go1.26.8` | CVE-2026-78667 | 2026-12-27 |
| High | `quay.io/cilium/cilium@sha256:2939231d0d3e3ebddcd80fffa168b7ddcc78fdf0dc864d1c8c126ff523c54f01` | `stdlib go1.26.8` | CVE-2026-78669 | 2026-12-27 |
| High | `quay.io/cilium/cilium@sha256:2939231d0d3e3ebddcd80fffa168b7ddcc78fdf0dc864d1c8c126ff523c54f01` | `stdlib go1.26.8` | CVE-2026-94439 | 2026-12-27 |
| High | `quay.io/cilium/cilium@sha256:2939231d0d3e3ebddcd80fffa168b7ddcc78fdf0dc864d1c8c126ff523c54f01` | `stdlib go1.26.8` | CVE-2026-94440 | 2026-12-27 |
| High | `quay.io/cilium/cilium@sha256:2939231d0d3e3ebddcd80fffa168b7ddcc78fdf0dc864d1c8c126ff523c54f01` | `stdlib go1.26.8` | CVE-2026-97031 | 2026-12-27 |
| High | `quay.io/cilium/cilium@sha256:2939231d0d3e3ebddcd80fffa168b7ddcc78fdf0dc864d1c8c126ff523c54f01` | `stdlib go1.26.8` | CVE-2026-97032 | 2026-12-27 |
| High | `quay.io/cilium/operator-generic@sha256:64d8798350e8569b8e7622563fed6e44dce2625f311e4651b774816516c744fc` | `github.com/go-jose/go-jose/v4 v4.1.4` | CVE-2026-116587 | 2026-12-27 |
| High | `quay.io/cilium/operator-generic@sha256:64d8798350e8569b8e7622563fed6e44dce2625f311e4651b774816516c744fc` | `github.com/klauspost/compress v1.18.6` | CVE-2026-63209 | 2026-12-27 |
| High | `quay.io/cilium/operator-generic@sha256:64d8798350e8569b8e7622563fed6e44dce2625f311e4651b774816516c744fc` | `go.etcd.io/etcd/client/pkg/v3 v3.6.12` | CVE-2026-73500 | 2026-12-27 |
| High | `quay.io/cilium/operator-generic@sha256:64d8798350e8569b8e7622563fed6e44dce2625f311e4651b774816516c744fc` | `golang.org/x/crypto v0.53.0` | CVE-2026-56854 | 2026-12-27 |
| High | `quay.io/cilium/operator-generic@sha256:64d8798350e8569b8e7622563fed6e44dce2625f311e4651b774816516c744fc` | `golang.org/x/crypto v0.53.0` | CVE-2026-56855 | 2026-12-27 |
| High | `quay.io/cilium/operator-generic@sha256:64d8798350e8569b8e7622563fed6e44dce2625f311e4651b774816516c744fc` | `golang.org/x/crypto v0.53.0` | CVE-2026-78662 | 2026-12-27 |
| High | `quay.io/cilium/operator-generic@sha256:64d8798350e8569b8e7622563fed6e44dce2625f311e4651b774816516c744fc` | `golang.org/x/net v0.56.0` | CVE-2026-78659 | 2026-12-27 |
| High | `quay.io/cilium/operator-generic@sha256:64d8798350e8569b8e7622563fed6e44dce2625f311e4651b774816516c744fc` | `golang.org/x/net v0.56.0` | CVE-2026-78660 | 2026-12-27 |
| High | `quay.io/cilium/operator-generic@sha256:64d8798350e8569b8e7622563fed6e44dce2625f311e4651b774816516c744fc` | `golang.org/x/net v0.56.0` | CVE-2026-78669 | 2026-12-27 |
| High | `quay.io/cilium/operator-generic@sha256:64d8798350e8569b8e7622563fed6e44dce2625f311e4651b774816516c744fc` | `golang.org/x/net v0.56.0` | CVE-2026-97032 | 2026-12-27 |
| High | `quay.io/cilium/operator-generic@sha256:64d8798350e8569b8e7622563fed6e44dce2625f311e4651b774816516c744fc` | `golang.org/x/text v0.39.0` | CVE-2026-56851 | 2026-12-27 |
| High | `quay.io/cilium/operator-generic@sha256:64d8798350e8569b8e7622563fed6e44dce2625f311e4651b774816516c744fc` | `google.golang.org/grpc v1.83.1` | CVE-2026-84445 | 2026-12-27 |
| High | `quay.io/cilium/operator-generic@sha256:64d8798350e8569b8e7622563fed6e44dce2625f311e4651b774816516c744fc` | `stdlib go1.26.8` | CVE-2026-56866 | 2026-12-27 |
| High | `quay.io/cilium/operator-generic@sha256:64d8798350e8569b8e7622563fed6e44dce2625f311e4651b774816516c744fc` | `stdlib go1.26.8` | CVE-2026-78659 | 2026-12-27 |
| High | `quay.io/cilium/operator-generic@sha256:64d8798350e8569b8e7622563fed6e44dce2625f311e4651b774816516c744fc` | `stdlib go1.26.8` | CVE-2026-78660 | 2026-12-27 |
| High | `quay.io/cilium/operator-generic@sha256:64d8798350e8569b8e7622563fed6e44dce2625f311e4651b774816516c744fc` | `stdlib go1.26.8` | CVE-2026-78667 | 2026-12-27 |
| High | `quay.io/cilium/operator-generic@sha256:64d8798350e8569b8e7622563fed6e44dce2625f311e4651b774816516c744fc` | `stdlib go1.26.8` | CVE-2026-78669 | 2026-12-27 |
| High | `quay.io/cilium/operator-generic@sha256:64d8798350e8569b8e7622563fed6e44dce2625f311e4651b774816516c744fc` | `stdlib go1.26.8` | CVE-2026-94439 | 2026-12-27 |
| High | `quay.io/cilium/operator-generic@sha256:64d8798350e8569b8e7622563fed6e44dce2625f311e4651b774816516c744fc` | `stdlib go1.26.8` | CVE-2026-94440 | 2026-12-27 |
| High | `quay.io/cilium/operator-generic@sha256:64d8798350e8569b8e7622563fed6e44dce2625f311e4651b774816516c744fc` | `stdlib go1.26.8` | CVE-2026-97031 | 2026-12-27 |
| High | `quay.io/cilium/operator-generic@sha256:64d8798350e8569b8e7622563fed6e44dce2625f311e4651b774816516c744fc` | `stdlib go1.26.8` | CVE-2026-97032 | 2026-12-27 |
| High | `quay.io/keycloak/keycloak@sha256:a78d6b79572168cb25886b80a8b5b8d4ed4390743e3eecb810538683e209dd6b` | `guava 33.6.0-jre` | CVE-2026-102554 | 2026-12-27 |
| High | `registry.k8s.io/coredns/coredns@sha256:7efd3c635b03efd68c4e8398fc45f0d993d0e9ab016f72c1cefb0fd6d01aa286` | `go.etcd.io/etcd/client/pkg/v3 v3.6.13` | CVE-2026-73500 | 2026-12-27 |
| High | `registry.k8s.io/coredns/coredns@sha256:7efd3c635b03efd68c4e8398fc45f0d993d0e9ab016f72c1cefb0fd6d01aa286` | `golang.org/x/crypto v0.54.0` | CVE-2026-56854 | 2026-12-27 |
| High | `registry.k8s.io/coredns/coredns@sha256:7efd3c635b03efd68c4e8398fc45f0d993d0e9ab016f72c1cefb0fd6d01aa286` | `golang.org/x/crypto v0.54.0` | CVE-2026-56855 | 2026-12-27 |
| High | `registry.k8s.io/coredns/coredns@sha256:7efd3c635b03efd68c4e8398fc45f0d993d0e9ab016f72c1cefb0fd6d01aa286` | `golang.org/x/crypto v0.54.0` | CVE-2026-78662 | 2026-12-27 |
| High | `registry.k8s.io/coredns/coredns@sha256:7efd3c635b03efd68c4e8398fc45f0d993d0e9ab016f72c1cefb0fd6d01aa286` | `golang.org/x/mod v0.37.0` | CVE-2026-56864 | 2026-12-27 |
| High | `registry.k8s.io/coredns/coredns@sha256:7efd3c635b03efd68c4e8398fc45f0d993d0e9ab016f72c1cefb0fd6d01aa286` | `golang.org/x/mod v0.37.0` | CVE-2026-56865 | 2026-12-27 |
| High | `registry.k8s.io/coredns/coredns@sha256:7efd3c635b03efd68c4e8398fc45f0d993d0e9ab016f72c1cefb0fd6d01aa286` | `golang.org/x/net v0.57.0` | CVE-2026-78659 | 2026-12-27 |
| High | `registry.k8s.io/coredns/coredns@sha256:7efd3c635b03efd68c4e8398fc45f0d993d0e9ab016f72c1cefb0fd6d01aa286` | `golang.org/x/net v0.57.0` | CVE-2026-78660 | 2026-12-27 |
| High | `registry.k8s.io/coredns/coredns@sha256:7efd3c635b03efd68c4e8398fc45f0d993d0e9ab016f72c1cefb0fd6d01aa286` | `golang.org/x/net v0.57.0` | CVE-2026-78669 | 2026-12-27 |
| High | `registry.k8s.io/coredns/coredns@sha256:7efd3c635b03efd68c4e8398fc45f0d993d0e9ab016f72c1cefb0fd6d01aa286` | `golang.org/x/net v0.57.0` | CVE-2026-97032 | 2026-12-27 |
| High | `registry.k8s.io/coredns/coredns@sha256:7efd3c635b03efd68c4e8398fc45f0d993d0e9ab016f72c1cefb0fd6d01aa286` | `golang.org/x/text v0.40.0` | CVE-2026-56851 | 2026-12-27 |
| High | `registry.k8s.io/coredns/coredns@sha256:7efd3c635b03efd68c4e8398fc45f0d993d0e9ab016f72c1cefb0fd6d01aa286` | `google.golang.org/grpc v1.83.0` | CVE-2026-84304 | 2026-12-27 |
| High | `registry.k8s.io/coredns/coredns@sha256:7efd3c635b03efd68c4e8398fc45f0d993d0e9ab016f72c1cefb0fd6d01aa286` | `google.golang.org/grpc v1.83.0` | CVE-2026-84445 | 2026-12-27 |
| High | `registry.k8s.io/coredns/coredns@sha256:7efd3c635b03efd68c4e8398fc45f0d993d0e9ab016f72c1cefb0fd6d01aa286` | `stdlib go1.26.6` | CVE-2026-56866 | 2026-12-27 |
| High | `registry.k8s.io/coredns/coredns@sha256:7efd3c635b03efd68c4e8398fc45f0d993d0e9ab016f72c1cefb0fd6d01aa286` | `stdlib go1.26.6` | CVE-2026-78659 | 2026-12-27 |
| High | `registry.k8s.io/coredns/coredns@sha256:7efd3c635b03efd68c4e8398fc45f0d993d0e9ab016f72c1cefb0fd6d01aa286` | `stdlib go1.26.6` | CVE-2026-78660 | 2026-12-27 |
| High | `registry.k8s.io/coredns/coredns@sha256:7efd3c635b03efd68c4e8398fc45f0d993d0e9ab016f72c1cefb0fd6d01aa286` | `stdlib go1.26.6` | CVE-2026-78667 | 2026-12-27 |
| High | `registry.k8s.io/coredns/coredns@sha256:7efd3c635b03efd68c4e8398fc45f0d993d0e9ab016f72c1cefb0fd6d01aa286` | `stdlib go1.26.6` | CVE-2026-78669 | 2026-12-27 |
| High | `registry.k8s.io/coredns/coredns@sha256:7efd3c635b03efd68c4e8398fc45f0d993d0e9ab016f72c1cefb0fd6d01aa286` | `stdlib go1.26.6` | CVE-2026-94439 | 2026-12-27 |
| High | `registry.k8s.io/coredns/coredns@sha256:7efd3c635b03efd68c4e8398fc45f0d993d0e9ab016f72c1cefb0fd6d01aa286` | `stdlib go1.26.6` | CVE-2026-94440 | 2026-12-27 |
| High | `registry.k8s.io/coredns/coredns@sha256:7efd3c635b03efd68c4e8398fc45f0d993d0e9ab016f72c1cefb0fd6d01aa286` | `stdlib go1.26.6` | CVE-2026-97031 | 2026-12-27 |
| High | `registry.k8s.io/coredns/coredns@sha256:7efd3c635b03efd68c4e8398fc45f0d993d0e9ab016f72c1cefb0fd6d01aa286` | `stdlib go1.26.6` | CVE-2026-97032 | 2026-12-27 |
| High | `registry.k8s.io/etcd@sha256:5ed4e32061aa061f970d6500629213e8579ef17571dcf9789074966acb9afad1` | `github.com/klauspost/compress v1.17.9` | CVE-2026-63209 | 2026-12-27 |
| High | `registry.k8s.io/etcd@sha256:5ed4e32061aa061f970d6500629213e8579ef17571dcf9789074966acb9afad1` | `golang.org/x/crypto v0.55.0` | CVE-2026-56855 | 2026-12-27 |
| High | `registry.k8s.io/etcd@sha256:5ed4e32061aa061f970d6500629213e8579ef17571dcf9789074966acb9afad1` | `golang.org/x/crypto v0.55.0` | CVE-2026-78662 | 2026-12-27 |
| High | `registry.k8s.io/etcd@sha256:5ed4e32061aa061f970d6500629213e8579ef17571dcf9789074966acb9afad1` | `golang.org/x/net v0.58.0` | CVE-2026-78659 | 2026-12-27 |
| High | `registry.k8s.io/etcd@sha256:5ed4e32061aa061f970d6500629213e8579ef17571dcf9789074966acb9afad1` | `golang.org/x/net v0.58.0` | CVE-2026-78660 | 2026-12-27 |
| High | `registry.k8s.io/etcd@sha256:5ed4e32061aa061f970d6500629213e8579ef17571dcf9789074966acb9afad1` | `golang.org/x/net v0.58.0` | CVE-2026-78669 | 2026-12-27 |
| High | `registry.k8s.io/etcd@sha256:5ed4e32061aa061f970d6500629213e8579ef17571dcf9789074966acb9afad1` | `golang.org/x/net v0.58.0` | CVE-2026-97032 | 2026-12-27 |
| High | `registry.k8s.io/etcd@sha256:5ed4e32061aa061f970d6500629213e8579ef17571dcf9789074966acb9afad1` | `stdlib go1.26.8` | CVE-2026-56866 | 2026-12-27 |
| High | `registry.k8s.io/etcd@sha256:5ed4e32061aa061f970d6500629213e8579ef17571dcf9789074966acb9afad1` | `stdlib go1.26.8` | CVE-2026-78659 | 2026-12-27 |
| High | `registry.k8s.io/etcd@sha256:5ed4e32061aa061f970d6500629213e8579ef17571dcf9789074966acb9afad1` | `stdlib go1.26.8` | CVE-2026-78660 | 2026-12-27 |
| High | `registry.k8s.io/etcd@sha256:5ed4e32061aa061f970d6500629213e8579ef17571dcf9789074966acb9afad1` | `stdlib go1.26.8` | CVE-2026-78667 | 2026-12-27 |
| High | `registry.k8s.io/etcd@sha256:5ed4e32061aa061f970d6500629213e8579ef17571dcf9789074966acb9afad1` | `stdlib go1.26.8` | CVE-2026-78669 | 2026-12-27 |
| High | `registry.k8s.io/etcd@sha256:5ed4e32061aa061f970d6500629213e8579ef17571dcf9789074966acb9afad1` | `stdlib go1.26.8` | CVE-2026-94439 | 2026-12-27 |
| High | `registry.k8s.io/etcd@sha256:5ed4e32061aa061f970d6500629213e8579ef17571dcf9789074966acb9afad1` | `stdlib go1.26.8` | CVE-2026-94440 | 2026-12-27 |
| High | `registry.k8s.io/etcd@sha256:5ed4e32061aa061f970d6500629213e8579ef17571dcf9789074966acb9afad1` | `stdlib go1.26.8` | CVE-2026-97031 | 2026-12-27 |
| High | `registry.k8s.io/etcd@sha256:5ed4e32061aa061f970d6500629213e8579ef17571dcf9789074966acb9afad1` | `stdlib go1.26.8` | CVE-2026-97032 | 2026-12-27 |
| High | `registry.k8s.io/kube-apiserver@sha256:4b3e69973a1d58d3c1f670d3477a9b9f14a03a271823113e8e0c9a333eb84f48` | `go.etcd.io/etcd/client/pkg/v3 v3.6.8` | CVE-2026-73500 | 2026-12-27 |
| High | `registry.k8s.io/kube-apiserver@sha256:4b3e69973a1d58d3c1f670d3477a9b9f14a03a271823113e8e0c9a333eb84f48` | `go.opentelemetry.io/otel/sdk v1.40.0` | CVE-2026-39883 | 2026-12-27 |
| High | `registry.k8s.io/kube-apiserver@sha256:4b3e69973a1d58d3c1f670d3477a9b9f14a03a271823113e8e0c9a333eb84f48` | `golang.org/x/crypto v0.53.0` | CVE-2026-56854 | 2026-12-27 |
| High | `registry.k8s.io/kube-apiserver@sha256:4b3e69973a1d58d3c1f670d3477a9b9f14a03a271823113e8e0c9a333eb84f48` | `golang.org/x/crypto v0.53.0` | CVE-2026-56855 | 2026-12-27 |
| High | `registry.k8s.io/kube-apiserver@sha256:4b3e69973a1d58d3c1f670d3477a9b9f14a03a271823113e8e0c9a333eb84f48` | `golang.org/x/crypto v0.53.0` | CVE-2026-78662 | 2026-12-27 |
| High | `registry.k8s.io/kube-apiserver@sha256:4b3e69973a1d58d3c1f670d3477a9b9f14a03a271823113e8e0c9a333eb84f48` | `golang.org/x/net v0.56.0` | CVE-2026-78659 | 2026-12-27 |
| High | `registry.k8s.io/kube-apiserver@sha256:4b3e69973a1d58d3c1f670d3477a9b9f14a03a271823113e8e0c9a333eb84f48` | `golang.org/x/net v0.56.0` | CVE-2026-78660 | 2026-12-27 |
| High | `registry.k8s.io/kube-apiserver@sha256:4b3e69973a1d58d3c1f670d3477a9b9f14a03a271823113e8e0c9a333eb84f48` | `golang.org/x/net v0.56.0` | CVE-2026-78669 | 2026-12-27 |
| High | `registry.k8s.io/kube-apiserver@sha256:4b3e69973a1d58d3c1f670d3477a9b9f14a03a271823113e8e0c9a333eb84f48` | `golang.org/x/net v0.56.0` | CVE-2026-97032 | 2026-12-27 |
| High | `registry.k8s.io/kube-apiserver@sha256:4b3e69973a1d58d3c1f670d3477a9b9f14a03a271823113e8e0c9a333eb84f48` | `golang.org/x/text v0.39.0` | CVE-2026-56851 | 2026-12-27 |
| High | `registry.k8s.io/kube-apiserver@sha256:4b3e69973a1d58d3c1f670d3477a9b9f14a03a271823113e8e0c9a333eb84f48` | `google.golang.org/grpc v1.79.3` | CVE-2026-84304 | 2026-12-27 |
| High | `registry.k8s.io/kube-apiserver@sha256:4b3e69973a1d58d3c1f670d3477a9b9f14a03a271823113e8e0c9a333eb84f48` | `google.golang.org/grpc v1.79.3` | CVE-2026-84445 | 2026-12-27 |
| High | `registry.k8s.io/kube-apiserver@sha256:4b3e69973a1d58d3c1f670d3477a9b9f14a03a271823113e8e0c9a333eb84f48` | `google.golang.org/grpc v1.79.3` | GHSA-hrxh-6v49-42gf | 2026-12-27 |
| High | `registry.k8s.io/kube-apiserver@sha256:4b3e69973a1d58d3c1f670d3477a9b9f14a03a271823113e8e0c9a333eb84f48` | `stdlib go1.26.8` | CVE-2026-56866 | 2026-12-27 |
| High | `registry.k8s.io/kube-apiserver@sha256:4b3e69973a1d58d3c1f670d3477a9b9f14a03a271823113e8e0c9a333eb84f48` | `stdlib go1.26.8` | CVE-2026-78659 | 2026-12-27 |
| High | `registry.k8s.io/kube-apiserver@sha256:4b3e69973a1d58d3c1f670d3477a9b9f14a03a271823113e8e0c9a333eb84f48` | `stdlib go1.26.8` | CVE-2026-78660 | 2026-12-27 |
| High | `registry.k8s.io/kube-apiserver@sha256:4b3e69973a1d58d3c1f670d3477a9b9f14a03a271823113e8e0c9a333eb84f48` | `stdlib go1.26.8` | CVE-2026-78667 | 2026-12-27 |
| High | `registry.k8s.io/kube-apiserver@sha256:4b3e69973a1d58d3c1f670d3477a9b9f14a03a271823113e8e0c9a333eb84f48` | `stdlib go1.26.8` | CVE-2026-78669 | 2026-12-27 |
| High | `registry.k8s.io/kube-apiserver@sha256:4b3e69973a1d58d3c1f670d3477a9b9f14a03a271823113e8e0c9a333eb84f48` | `stdlib go1.26.8` | CVE-2026-94439 | 2026-12-27 |
| High | `registry.k8s.io/kube-apiserver@sha256:4b3e69973a1d58d3c1f670d3477a9b9f14a03a271823113e8e0c9a333eb84f48` | `stdlib go1.26.8` | CVE-2026-94440 | 2026-12-27 |
| High | `registry.k8s.io/kube-apiserver@sha256:4b3e69973a1d58d3c1f670d3477a9b9f14a03a271823113e8e0c9a333eb84f48` | `stdlib go1.26.8` | CVE-2026-97031 | 2026-12-27 |
| High | `registry.k8s.io/kube-apiserver@sha256:4b3e69973a1d58d3c1f670d3477a9b9f14a03a271823113e8e0c9a333eb84f48` | `stdlib go1.26.8` | CVE-2026-97032 | 2026-12-27 |
| High | `registry.k8s.io/kube-controller-manager@sha256:2d717af134451db77ea053c3426bc82edc0e55415eb36e1260313c636ebe9a4d` | `go.etcd.io/etcd/client/pkg/v3 v3.6.8` | CVE-2026-73500 | 2026-12-27 |
| High | `registry.k8s.io/kube-controller-manager@sha256:2d717af134451db77ea053c3426bc82edc0e55415eb36e1260313c636ebe9a4d` | `go.opentelemetry.io/otel/sdk v1.40.0` | CVE-2026-39883 | 2026-12-27 |
| High | `registry.k8s.io/kube-controller-manager@sha256:2d717af134451db77ea053c3426bc82edc0e55415eb36e1260313c636ebe9a4d` | `golang.org/x/crypto v0.53.0` | CVE-2026-56854 | 2026-12-27 |
| High | `registry.k8s.io/kube-controller-manager@sha256:2d717af134451db77ea053c3426bc82edc0e55415eb36e1260313c636ebe9a4d` | `golang.org/x/crypto v0.53.0` | CVE-2026-56855 | 2026-12-27 |
| High | `registry.k8s.io/kube-controller-manager@sha256:2d717af134451db77ea053c3426bc82edc0e55415eb36e1260313c636ebe9a4d` | `golang.org/x/crypto v0.53.0` | CVE-2026-78662 | 2026-12-27 |
| High | `registry.k8s.io/kube-controller-manager@sha256:2d717af134451db77ea053c3426bc82edc0e55415eb36e1260313c636ebe9a4d` | `golang.org/x/net v0.56.0` | CVE-2026-78659 | 2026-12-27 |
| High | `registry.k8s.io/kube-controller-manager@sha256:2d717af134451db77ea053c3426bc82edc0e55415eb36e1260313c636ebe9a4d` | `golang.org/x/net v0.56.0` | CVE-2026-78660 | 2026-12-27 |
| High | `registry.k8s.io/kube-controller-manager@sha256:2d717af134451db77ea053c3426bc82edc0e55415eb36e1260313c636ebe9a4d` | `golang.org/x/net v0.56.0` | CVE-2026-78669 | 2026-12-27 |
| High | `registry.k8s.io/kube-controller-manager@sha256:2d717af134451db77ea053c3426bc82edc0e55415eb36e1260313c636ebe9a4d` | `golang.org/x/net v0.56.0` | CVE-2026-97032 | 2026-12-27 |
| High | `registry.k8s.io/kube-controller-manager@sha256:2d717af134451db77ea053c3426bc82edc0e55415eb36e1260313c636ebe9a4d` | `golang.org/x/text v0.39.0` | CVE-2026-56851 | 2026-12-27 |
| High | `registry.k8s.io/kube-controller-manager@sha256:2d717af134451db77ea053c3426bc82edc0e55415eb36e1260313c636ebe9a4d` | `google.golang.org/grpc v1.79.3` | CVE-2026-84304 | 2026-12-27 |
| High | `registry.k8s.io/kube-controller-manager@sha256:2d717af134451db77ea053c3426bc82edc0e55415eb36e1260313c636ebe9a4d` | `google.golang.org/grpc v1.79.3` | CVE-2026-84445 | 2026-12-27 |
| High | `registry.k8s.io/kube-controller-manager@sha256:2d717af134451db77ea053c3426bc82edc0e55415eb36e1260313c636ebe9a4d` | `google.golang.org/grpc v1.79.3` | GHSA-hrxh-6v49-42gf | 2026-12-27 |
| High | `registry.k8s.io/kube-controller-manager@sha256:2d717af134451db77ea053c3426bc82edc0e55415eb36e1260313c636ebe9a4d` | `stdlib go1.26.8` | CVE-2026-56866 | 2026-12-27 |
| High | `registry.k8s.io/kube-controller-manager@sha256:2d717af134451db77ea053c3426bc82edc0e55415eb36e1260313c636ebe9a4d` | `stdlib go1.26.8` | CVE-2026-78659 | 2026-12-27 |
| High | `registry.k8s.io/kube-controller-manager@sha256:2d717af134451db77ea053c3426bc82edc0e55415eb36e1260313c636ebe9a4d` | `stdlib go1.26.8` | CVE-2026-78660 | 2026-12-27 |
| High | `registry.k8s.io/kube-controller-manager@sha256:2d717af134451db77ea053c3426bc82edc0e55415eb36e1260313c636ebe9a4d` | `stdlib go1.26.8` | CVE-2026-78667 | 2026-12-27 |
| High | `registry.k8s.io/kube-controller-manager@sha256:2d717af134451db77ea053c3426bc82edc0e55415eb36e1260313c636ebe9a4d` | `stdlib go1.26.8` | CVE-2026-78669 | 2026-12-27 |
| High | `registry.k8s.io/kube-controller-manager@sha256:2d717af134451db77ea053c3426bc82edc0e55415eb36e1260313c636ebe9a4d` | `stdlib go1.26.8` | CVE-2026-94439 | 2026-12-27 |
| High | `registry.k8s.io/kube-controller-manager@sha256:2d717af134451db77ea053c3426bc82edc0e55415eb36e1260313c636ebe9a4d` | `stdlib go1.26.8` | CVE-2026-94440 | 2026-12-27 |
| High | `registry.k8s.io/kube-controller-manager@sha256:2d717af134451db77ea053c3426bc82edc0e55415eb36e1260313c636ebe9a4d` | `stdlib go1.26.8` | CVE-2026-97031 | 2026-12-27 |
| High | `registry.k8s.io/kube-controller-manager@sha256:2d717af134451db77ea053c3426bc82edc0e55415eb36e1260313c636ebe9a4d` | `stdlib go1.26.8` | CVE-2026-97032 | 2026-12-27 |
| High | `registry.k8s.io/kube-scheduler@sha256:3804f66442962cefbe11fcd5330d5e7a797bfb3dc8535c322d005637b404a85f` | `go.etcd.io/etcd/client/pkg/v3 v3.6.8` | CVE-2026-73500 | 2026-12-27 |
| High | `registry.k8s.io/kube-scheduler@sha256:3804f66442962cefbe11fcd5330d5e7a797bfb3dc8535c322d005637b404a85f` | `go.opentelemetry.io/otel/sdk v1.40.0` | CVE-2026-39883 | 2026-12-27 |
| High | `registry.k8s.io/kube-scheduler@sha256:3804f66442962cefbe11fcd5330d5e7a797bfb3dc8535c322d005637b404a85f` | `golang.org/x/crypto v0.53.0` | CVE-2026-56854 | 2026-12-27 |
| High | `registry.k8s.io/kube-scheduler@sha256:3804f66442962cefbe11fcd5330d5e7a797bfb3dc8535c322d005637b404a85f` | `golang.org/x/crypto v0.53.0` | CVE-2026-56855 | 2026-12-27 |
| High | `registry.k8s.io/kube-scheduler@sha256:3804f66442962cefbe11fcd5330d5e7a797bfb3dc8535c322d005637b404a85f` | `golang.org/x/crypto v0.53.0` | CVE-2026-78662 | 2026-12-27 |
| High | `registry.k8s.io/kube-scheduler@sha256:3804f66442962cefbe11fcd5330d5e7a797bfb3dc8535c322d005637b404a85f` | `golang.org/x/net v0.56.0` | CVE-2026-78659 | 2026-12-27 |
| High | `registry.k8s.io/kube-scheduler@sha256:3804f66442962cefbe11fcd5330d5e7a797bfb3dc8535c322d005637b404a85f` | `golang.org/x/net v0.56.0` | CVE-2026-78660 | 2026-12-27 |
| High | `registry.k8s.io/kube-scheduler@sha256:3804f66442962cefbe11fcd5330d5e7a797bfb3dc8535c322d005637b404a85f` | `golang.org/x/net v0.56.0` | CVE-2026-78669 | 2026-12-27 |
| High | `registry.k8s.io/kube-scheduler@sha256:3804f66442962cefbe11fcd5330d5e7a797bfb3dc8535c322d005637b404a85f` | `golang.org/x/net v0.56.0` | CVE-2026-97032 | 2026-12-27 |
| High | `registry.k8s.io/kube-scheduler@sha256:3804f66442962cefbe11fcd5330d5e7a797bfb3dc8535c322d005637b404a85f` | `golang.org/x/text v0.39.0` | CVE-2026-56851 | 2026-12-27 |
| High | `registry.k8s.io/kube-scheduler@sha256:3804f66442962cefbe11fcd5330d5e7a797bfb3dc8535c322d005637b404a85f` | `google.golang.org/grpc v1.79.3` | CVE-2026-84304 | 2026-12-27 |
| High | `registry.k8s.io/kube-scheduler@sha256:3804f66442962cefbe11fcd5330d5e7a797bfb3dc8535c322d005637b404a85f` | `google.golang.org/grpc v1.79.3` | CVE-2026-84445 | 2026-12-27 |
| High | `registry.k8s.io/kube-scheduler@sha256:3804f66442962cefbe11fcd5330d5e7a797bfb3dc8535c322d005637b404a85f` | `google.golang.org/grpc v1.79.3` | GHSA-hrxh-6v49-42gf | 2026-12-27 |
| High | `registry.k8s.io/kube-scheduler@sha256:3804f66442962cefbe11fcd5330d5e7a797bfb3dc8535c322d005637b404a85f` | `stdlib go1.26.8` | CVE-2026-56866 | 2026-12-27 |
| High | `registry.k8s.io/kube-scheduler@sha256:3804f66442962cefbe11fcd5330d5e7a797bfb3dc8535c322d005637b404a85f` | `stdlib go1.26.8` | CVE-2026-78659 | 2026-12-27 |
| High | `registry.k8s.io/kube-scheduler@sha256:3804f66442962cefbe11fcd5330d5e7a797bfb3dc8535c322d005637b404a85f` | `stdlib go1.26.8` | CVE-2026-78660 | 2026-12-27 |
| High | `registry.k8s.io/kube-scheduler@sha256:3804f66442962cefbe11fcd5330d5e7a797bfb3dc8535c322d005637b404a85f` | `stdlib go1.26.8` | CVE-2026-78667 | 2026-12-27 |
| High | `registry.k8s.io/kube-scheduler@sha256:3804f66442962cefbe11fcd5330d5e7a797bfb3dc8535c322d005637b404a85f` | `stdlib go1.26.8` | CVE-2026-78669 | 2026-12-27 |
| High | `registry.k8s.io/kube-scheduler@sha256:3804f66442962cefbe11fcd5330d5e7a797bfb3dc8535c322d005637b404a85f` | `stdlib go1.26.8` | CVE-2026-94439 | 2026-12-27 |
| High | `registry.k8s.io/kube-scheduler@sha256:3804f66442962cefbe11fcd5330d5e7a797bfb3dc8535c322d005637b404a85f` | `stdlib go1.26.8` | CVE-2026-94440 | 2026-12-27 |
| High | `registry.k8s.io/kube-scheduler@sha256:3804f66442962cefbe11fcd5330d5e7a797bfb3dc8535c322d005637b404a85f` | `stdlib go1.26.8` | CVE-2026-97031 | 2026-12-27 |
| High | `registry.k8s.io/kube-scheduler@sha256:3804f66442962cefbe11fcd5330d5e7a797bfb3dc8535c322d005637b404a85f` | `stdlib go1.26.8` | CVE-2026-97032 | 2026-12-27 |
| Medium (KEV) | `quay.io/argoproj/argocd@sha256:13db7b10db23283b1b36f855046602e18539a8a8204c9f6f039e8896c8897518` | `libbrotli1 1.2.0-3build1` | CVE-2026-111497 | 2026-11-24 |

### Exception calendar

Acceptance fails for expired entries or **<=7 days** remaining; **8–21 days**
is a warning. Counts below cover every active exception row. The target
release dates are a plan, not completed acceptance or permission to ignore a
new scan finding. Every calendar date through **2026-11-16** has zero failing
exceptions under the current approved expiries. Warnings are retained.

| UTC date / checkpoint | Days to Nov 24 (1 KEV) | Days to Nov 27 (59 Critical) | Days to Dec 27 (360 High) | Failing rows | Warning rows |
| --- | ---: | ---: | ---: | ---: | ---: |
| 2026-10-29 / post-promotion pass | 26 | 29 | 59 | 0 | 0 |
| 2026-10-30 / R3b snapshot | 25 | 28 | 58 | 0 | 0 |
| 2026-10-31 / target merge / freeze | 24 | 27 | 57 | 0 | 0 |
| 2026-11-02 / planned rc cut | 22 | 25 | 55 | 0 | 0 |
| 2026-11-09 / planned Stable cut | 15 | 18 | 48 | 0 | 60 |
| 2026-11-13 / WO-46 KEV checkpoint | 11 | 14 | 44 | 0 | 60 |
| 2026-11-16 / release-window bound | 8 | 11 | 41 | 0 | 60 |
| 2026-11-17 / first KEV calendar failure if unchanged | 7 | 10 | 40 | 1 | 59 |

A fresh full scan, owner acceptance and the consolidated rc sign-off still
precede release. Resolve or individually re-approve any remaining risk before
its deadline; this document changes no entry or gate. After the KEV checkpoint,
WO-46 must keep the approved remediation and renewal decisions visible.
