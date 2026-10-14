# Changelog

All notable changes to this project are documented here.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and versions follow [Semantic Versioning](https://semver.org/spec/v2.0.0.html).
See [RELEASING.md](RELEASING.md) for the release streams. Twinfra has no earlier releases or tags.

## [Unreleased]

### Security

- Run WO-34 console reproduction and complete image comparisons only in the
  paths-filtered WO-34 workflow; unrelated PRs retain changed-input supply-chain
  validation without rebuilding the console or forcing an image inventory rescan.
- Refresh the console to CPython 3.14.8 and a reproducible Twinfra image; eliminate
  23 fixable Critical and 118 fixable High findings, close 23 superseded exceptions,
  and add pinned Go binary triage with complete before/after image evidence (WO-34 P1).

### Added

- Release streams (Dev, Candidate, Stable): `RELEASING.md`, this changelog, `VERSION`
  (next release: 0.1.0), `compatibility.yaml`, the `release-checks` and `release` workflows
  (releases attach the image locks and the licence register), and the rulesets in
  `.github/rulesets/`.
