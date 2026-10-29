# Changelog

All notable changes to this project are documented here.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and versions follow [Semantic Versioning](https://semver.org/spec/v2.0.0.html).
See [RELEASING.md](RELEASING.md) for the release streams. Twinfra has no earlier releases or tags.

## [Unreleased]

### Changed

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
