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

Provide the backup target and credentials outside Git. Approve the RPO and RTO.

## Report back

Plugin and versions, the target type, the measured RPO and RTO, and the drill timeline.
