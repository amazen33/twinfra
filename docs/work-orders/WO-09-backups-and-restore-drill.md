# WO-09: Off-node backups and a restore drill

**Status:** Approved for implementation (owner, 2026-10-08) · **Phase:** 1 · **Author:** Claude · **Implementer:** Codex
**Branch:** `codex/wo-09-backups` · **Review finding:** R2

## Goal

Losing the lab node does not lose data. Restores are proven, not assumed.

## Verified context

- CloudNativePG runs PostgreSQL 18.6 with pgvector 0.8.2 as a single instance on a 4 GiB loop-file Local PV.
  `lab/wsl/PLATFORM.md` says it has "no HA, external backup or DR guarantee".
- OpenBao stores its data in PostgreSQL.
- There is no backup configuration in the repo.

## Scope

1. Write `docs/runbooks/backup-and-restore.md`. It proposes an RPO and RTO per data class (application data, OpenBao storage,
   Keycloak data, cluster datastore) for the owner to approve. A suggested lab default is RPO 15 minutes and RTO 2 hours.
2. **Backup target:** an S3-compatible endpoint that is **not on the lab node**, supplied by the owner. Preferred is
   SeaweedFS on a separate Hyper-V VM, the future S3 back end. The alternative is an S3 bucket in the AWS sandbox (ADR-0033).
   Credentials come through ESO (WO-08) or a Kubernetes Secret created by the owner, never through Git.
3. **CloudNativePG:** scheduled base backups and continuous WAL archiving through the Barman Cloud plugin.
   Record its licence in the register (expected Apache-2.0) and confirm it. Add encryption at rest on the target and a retention policy.
4. **Cluster datastore:** a scheduled snapshot of the K3s datastore to the same target, or of etcd once the VM lab runs kubeadm.
5. **Restore drill:** a point-in-time restore into a new cluster or namespace at a chosen timestamp, compared by
   checksums on sample tables. Document how OpenBao recovers (data from backup, unseal material held separately).
6. A Prometheus alert for backup failure or stale backups, with a promtool test.

## Out of scope

High availability and replicas (Phase 2 onward), and cross-region replication (Phase 7).

## Acceptance criteria

- Backups and WAL appear in the target. The restore matches its checksums. The measured RPO and RTO are recorded against the approved targets.
- The alert fires in a forced-failure test.
- Receipt: `docs/acceptance/backup-restore-drill-<date>.md`.

## Owner actions

Provide the backup target and credentials outside Git. As QoS tester, Ahmed Mazen approves the RPO and RTO
targets, witnesses the restore drill, and signs off the receipt.

## Report back

Plugin and versions, the target type, the measured RPO and RTO, and the drill timeline.

## Amendment 1 (2026-10-16, architect; APPROVED by the owner 2026-10-16: "R2 yes, targets approved"): cairo-1 reality

The original text predates the bare-metal Dell (ADR-0048), ADR-0046 and ADR-0052. Where it says "lab" or K3s, read **`twinfra-dev-cairo-1`** and **kubeadm etcd**.
This amendment supersedes scope items 2, 4, 5 and 6 where they conflict.

1. **Verified context now.**
   - CNPG 1.30.1 runs PostgreSQL 18.6 with pgvector 0.8.2 (`twinfra-postgres-1`) on a 20 GiB LV at `/var/lib/twinfra/local-pv/postgres-1`.
   - OpenBao and Keycloak store their data in it.
   - etcd is a kubeadm static pod.
   - The volume group has about 100 GiB free.
   - No backups exist.
2. **Backup target (dev): a Cloudflare R2 bucket** in the owner's account (S3-compatible, off-site, inside the free tier for this size). It replaces the Hyper-V SeaweedFS VM, because the laptop is not always on.
   - The owner creates bucket `twinfra-dev-cairo-1-backups` and an API token scoped to **Object Read and Write on that bucket only**.
   - The credentials become Secret `twinfra-backup-s3`, created by the owner through kubectl standard input, never in Git or chat. WO-08 later moves them to External Secrets.
   - **Dev data only.** Before any production use, choose an in-country or owner-controlled target (ADR-0041 sovereignty). Record this in the runbook.
3. **PostgreSQL.**
   - The CNPG Barman Cloud plugin, licence-registered and pinned by digest.
   - A daily base backup plus continuous WAL archiving, with `archive_timeout` at most 5 minutes.
   - zstd or gzip compression, 7-day retention, and R2's default encryption at rest.
4. **etcd.**
   - A host systemd timer runs `etcdctl snapshot save` every 6 hours and checks it with `etcdutl snapshot status`.
   - It **encrypts the snapshot client-side with age before upload**, because a snapshot contains every Kubernetes Secret. The age public key is on the host; **the private key is held offline by the owner** and never on the Dell.
   - Uploads use a pinned, licence-registered tool (for example rclone, MIT). Keep 7 days of snapshots.
5. **Restore drill (live, owner-witnessed).**
   - A point-in-time restore of PostgreSQL into a separate namespace `twinfra-restore-drill`, on a temporary LV created by `host-storage`.
   - Compare row counts and checksums of sample tables (application, Keycloak, OpenBao) against the source at the chosen time.
   - Measure RPO and RTO, then delete the drill namespace and LV.
   - For etcd, prove only decryption plus `snapshot status`. A full etcd restore happens in the WO-23 DR drill on `cairo-2`, never on the live node.
6. **Freshness check now, alert later.**
   - `platform_dev.py backup-check` reports the age of the last base backup and the last archived WAL, and the last etcd snapshot, with WARN or FAIL thresholds from the approved RPO.
   - Ship the PrometheusRule and its promtool test now. The live "alert fires" acceptance moves to WO-10, because Prometheus arrives there.
7. **Targets (approved by the QoS tester, 2026-10-16):** RPO 15 minutes for PostgreSQL and 6 hours for etcd; RTO 2 hours for a PostgreSQL restore (dev).

## Amendment 2 (2026-10-16, architect; APPROVED by the owner 2026-10-16: "ADR-0054 approved, Barman approved")

Codex stopped at preflight: the CNPG Barman Cloud plugin sidecar bundles Barman (GPL-3.0) and psycopg2 (LGPL). Under the ADR-0054 ladder:
- tiers 1 and 2: pgBackRest (MIT) with the Dalibo or Opera CNPG-I plugins (Apache-2.0) fails the **maturity** criterion (experimental v0.0.x). WAL-G (Apache-2.0) has no CNPG integration;
- tier 4: **Barman Cloud plugin** (plugin Apache-2.0; sidecar contains Barman, GPL-3.0) is selected. psycopg2 (LGPL-3.0) is tier 3.

Implementation rules:
1. Use the official plugin release (v0.15.1 or newer, at least 14 days old), digest-pinned, **unmodified**, running only as its own sidecar container next to PostgreSQL. No Twinfra code links to or embeds Barman.
2. Licence register: Barman as class `exception` (tier 4) and psycopg2 as `exception` (tier 3), each with an `enterpriseGrade` record, the climbing record (pgBackRest plugins rejected: maturity; WAL-G rejected: no CNPG integration), `approvedBy: amazen33` after the owner approves, and a re-evaluation date 6 months out.
3. Notices and a source offer for the sidecar image's GPL and LGPL components in `security/licences/`.
4. The optional second copy (nightly age-encrypted `pg_dump` to R2) is **not** required with a mature primary. Leave it out unless the restore drill fails.
5. Everything else in Amendment 1 stands.

## Amendment 3 (2026-10-16, architect; APPROVED by the owner 2026-10-16: "WO-09 Amendment 3 approved, toolchain-wave rule approved"): resolve the supply-chain stop

Codex's preflight (`docs/acceptance/backup-preflight-2026-10-16.md`) found two things:
- every proposed Go component (the Barman plugin manager and sidecar, age, rclone, etcdctl and etcdutl) carries the same toolchain-wide Go advisories (GO-2026-6612 and GO-2026-6604, fixed in Go 1.26.9 and x/net 0.60.0), plus x/crypto and x/net Highs;
- the official plugin **requires cert-manager**, which arrives with WO-08.

1. **Order.** WO-08 (OpenBao, External Secrets, cert-manager) now comes **before** WO-09's live steps. WO-09's static PR may merge as soon as its gates pass. The live install waits for WO-08.
2. **No new Go host tools.**
   - **etcd snapshots** run as a CronJob on the control-plane node, using the **already admitted etcd image** (v3.6.15, existing carried exceptions) for `etcdctl snapshot save` and `etcdutl snapshot status`. It mounts only the etcd client certificates read-only (a node exception per ADR-0001, named in the PR) and writes to an `emptyDir`.
   - **Encryption and upload** use the **already admitted Python base image** with `pyrage` (MIT, age-compatible) and `boto3` (Apache-2.0), hash-pinned and licence-registered with enterpriseGrade records.
   - The owner's key ceremony uses `rage-keygen` or `pyrage` on the laptop.
   - `age` and `rclone` are dropped. If Codex finds no clean way to do this, stop and report.
3. **Barman plugin images.**
   - **No exceptions now.** The plugin releases about monthly (v0.14.0 2026-07-29, v0.15.0 09-03, v0.15.1 09-30). Re-scan at WO-09's live time with the newest eligible release.
   - If findings remain then, apply the ADR-0049 toolchain-wave rule (Amendment 1 of ADR-0049, approved): per-image entries, 30 days, with the plugin's controls listed (cluster-internal only, egress only to the R2 endpoint, no Service exposed outside the namespace).
4. Open the WO-09 PR as a **draft** with the static work. It is marked ready once the gate passes, either with a clean release or with owner-approved entries.
