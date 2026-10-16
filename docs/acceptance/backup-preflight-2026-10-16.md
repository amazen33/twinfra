# WO-09 backup dependency preflight — 2026-10-16

Scope: static preparation on `codex/wo-09-backups`, based on main `09d56f3`.
No Dell connection, Kubernetes change, bucket, token or GitHub setting change.
Implementation is incomplete and uncommitted; no deployment or restore is claimed.

## Approved inputs

- [ADR-0054](../adr/0054-licence-ladder-and-enterprise-grade-gate.md) and
  [WO-09 Amendments 1/2](../work-orders/WO-09-backups-and-restore-drill.md):
  owner-approved 2026-10-16. Licence approval is separate from vulnerability approval.
- Owner R2 endpoint and default/automatic jurisdiction are recorded as configurable
  public values in `deploy/common/backup-config.json`. Credentials remain absent.
- Owner dated backfill: 13 conservative tier-3/4 legacy runtime entries due
  2027-01-14; 513 tier-1/2 entries due 2027-04-16. Earlier expiry dates remain.

## Verified plugin provenance

Official [v0.15.1 release](https://github.com/cloudnative-pg/plugin-barman-cloud/releases/tag/v0.15.1)
was published 2026-09-30T13:34:15Z and meets the 14-day rule. The official release
API lists no newer stable plugin release as of this preflight.

| Artifact | Verified SHA-256 |
| --- | --- |
| Official release manifest | `8f377ff4a7d0d3f74fc64b0f7ac4f449fc38ca9e83a40107cca2f9315a9bd920` |
| Manager multi-platform image | `c75acad19a36e8176cfe2885761ff1b836c6ef977d7257e298c99a28b5c302ef` |
| Sidecar multi-platform image | `2287a793a804db751edd0d07d44cd549e357677e98a800eb12e2cf7c0d53f9b0` |

The official sidecar pins Barman 3.20.1 and psycopg2 2.9.13. Hash-verified PyPI
source archives confirm GPL-3.0-only for Barman (its project metadata) and
LGPL-3.0-or-later with an additional OpenSSL linking permission for psycopg2.
Full enterprise-grade admissions/notices have not been completed because of
the independent supply-chain stop below.

## Supply-chain stop

The already registered Syft 1.52.0 and Grype 0.119.0 versions were used. Their
official Windows release archives were verified against these SHA-256 values:

- Syft: `de787a374cf961c56fd7b206b2e183295abba32d0af3cb44d9aef2357ca9eda2`.
- Grype: `1db5c23b8ba0038a04acebed9c17945e1ade68d9f83e2fe1c101e4fb1feb9a48`.

Grype database: v6.1.10, built 2026-10-15T06:30:36Z; published archive checksum
`2f1597f25b5089e966272b251eb4d1f9977e59d57029af1c8810deb6e5321aa2`.

Direct image scanning on Windows failed because stereoscope creates layer cache
names containing `sha256:`, which Windows rejects. The fallback verified the OCI
blobs, extracted the manager binary and the sidecar's regular-file rootfs, and
scanned those without executing them. Symlinks were omitted. This is **partial
package evidence, not a complete Linux image scan or reachability analysis**.
It is sufficient to expose unresolved package matches; a Linux CI scan and
govulncheck triage remain necessary before any exception decision.

| Proposed component | Version | Critical findings with fixes | High findings with fixes |
| --- | --- | ---: | ---: |
| Barman plugin manager | 0.15.1 | 3 | 11 |
| Barman plugin sidecar | 0.15.1 | 3 | 11 |
| age | 1.3.2 | 2 | 10 |
| age-keygen (owner key ceremony only) | 1.3.2 | 2 | 10 |
| rclone | 1.75.1 | 3 | 12 |
| etcdctl | 3.6.15 | 3 | 11 |
| etcdutl | 3.6.15 | 3 | 13 |

Counts are package/vulnerability matches, including repeated advisories in
different packages/binaries. They are not counts of exploitable endpoints.
The manager and sidecar contain `golang.org/x/net v0.58.0` and `stdlib go1.26.6`.
Examples include GO-2026-6612 (fixes: x/net 0.60.0 and Go 1.26.9) and
GO-2026-6604 (Go 1.26.9/1.27.2). Existing approvals for different image targets
cannot be inherited by these new components.

The unchanged `supply_chain.evaluate()` was run against the two images' findings,
the current approved exception file, and a fresh CISA KEV catalog: **failed,
28 image findings blocked, zero matching exceptions**. Runtime tool matches are
additional manual preflight evidence; this does not claim that the existing
image-only scanner automatically covers their new host installation path.

Latest age release is 1.3.2. Latest compatible etcd 3.6 patch is 3.6.15. Rclone
1.75.2 was published 2026-10-09, so it reaches the 14-day boundary on 2026-10-23;
it has not been selected or approved here. No unmodified eligible plugin patch
is available to resolve the mandatory image gate at this point.

Local, ignored raw evidence is retained in `.build/wo09/`:
`admission-report.json`, `manager-binary.syft.json`, `manager-binary.grype.json`,
`sidecar-filesystem.syft.json`, `sidecar-filesystem.grype.json`, the five host-tool
scan pairs, `kev.json`, verified OCI archives and `scan-remaining.log`.
The admission report records raw scan hashes and exact targets. No exception
approval or expiry was added or renewed.

## Checks and remaining prerequisites

- New ladder/schema/backfill tests: **10 passed**.
- Existing licence unit regression: **24 passed** after giving its synthetic
  positive admission fixtures explicit enterprise-grade records.
- `git diff --check`: passed.
- Full candidate regression, six historical baselines, rendered schema checks,
  GitHub CI and staging-check: **not completed**; dependency admission is blocked.
- Official plugin installation requires cert-manager (WO-08) in addition to
  CNPG. It must precede live plugin installation; no new TLS controller was
  installed or substituted by this work order.
- New image staging requires the owner's real `stage-images --check` attestation;
  none has been fabricated. Backup upload, WAL continuity, restore, alert firing,
  RPO/RTO measurements and the private age-key ceremony remain live owner actions.

Owner/architect decision needed: resolve the package findings through eligible
official artifacts or a separately reviewed vulnerability-triage/exception
amendment. ADR-0054's Barman licence exception does not override ADR-0049.

## Tester sign-off

Tester: Ahmed Mazen (@amazen33), enterprise and cloud tester; QoS tester.
Result: Pending
No backup/restore acceptance has been performed.

## Follow-up: approved Amendment 3 and CMS clarification

The preceding sections preserve the earlier preflight, including tools that are
now rejected. Owner-approved WO-09 Amendment 3 and ADR-0049 Amendment 1 permit a
draft static implementation with explicitly unresolved admission. No new Go host
tools are selected. The admitted etcd image supplies a bounded node CronJob.

Owner clarification, 2026-10-16: pyrage fails ADR-0054 governance (single maintainer,
personal repository, no SECURITY.md); **not selected**, not pending qualification.
OpenSSL CMS from the admitted Python base replaces age/pyrage, with the existing
hash-pinned boto3 SDK. `/usr/bin/openssl` is present: OpenSSL 3.5.7, Debian package
3.5.7-1~deb13u3. CLI and libcrypto hashes are recorded in the backup artifact lock.
Only the public certificate reaches the Dell; private key stays with the owner.
The real CMS synthetic snapshot round-trip is a disposable CI test, not a live
restore. CBC fallback is limited to an explicit unsupported-GCM capability result.

No Barman vulnerability exceptions have been added. The conservative toolchain
wave matcher refuses unlisted stdlib-only Highs, KEV and an eligible fixed release.
Fresh complete Linux scans, reviewed image licence evidence/enterprise admission,
WO-08 and owner staging remain readiness/live gates. Refer to the PR's current
check table for results; the earlier "not completed" row above is historical.
