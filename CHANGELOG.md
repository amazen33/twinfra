# Changelog

All notable changes to this project are documented here.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and versions follow [Semantic Versioning](https://semver.org/spec/v2.0.0.html).
See [RELEASING.md](RELEASING.md) for the release streams. Twinfra has no earlier releases or tags.

## [Unreleased]

### Security

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

- Release streams (Dev, Candidate, Stable): `RELEASING.md`, this changelog, `VERSION`
  (next release: 0.1.0), `compatibility.yaml`, the `release-checks` and `release` workflows
  (releases attach the image locks and the licence register), and the rulesets in
  `.github/rulesets/`.
