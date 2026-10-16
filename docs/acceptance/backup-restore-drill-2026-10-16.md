# WO-09 backup and restore drill — 2026-10-16

Environment: `twinfra-dev-cairo-1`. Scope: static implementation only.
Tester: Ahmed Mazen (@amazen33), enterprise and cloud tester; QoS tester.
Result: Pending

Owner-approved targets: PostgreSQL RPO 15 minutes, dev PITR RTO 2 hours;
etcd RPO 6 hours. Application, OpenBao and Keycloak data share the PostgreSQL
physical backup. No RPO/RTO has been measured. No Dell connection, bucket/token
creation, Secret creation or live backup/restore has been performed.

| Live evidence required | Status / measured value |
| --- | --- |
| WO-08 cert-manager and plugin TLS readiness | Pending |
| Fresh complete image scans, enterprise admission and real image staging | Pending |
| R2 bucket scope, encryption-at-rest and successful base/WAL objects | Pending |
| CMS certificate fingerprint and owner offline private-key custody | Pending; never record the key or passphrase |
| Etcd snapshot, encrypted upload, download verification and snapshot status | Pending |
| Source fixture counts/checksums and UTC PITR target | Pending |
| Restore namespace/LV identity, isolated recovery and fixture comparison | Pending |
| Simulated loss timestamp / last recovered commit / measured RPO | Pending |
| Recovery start / verified query / measured RTO | Pending |
| Restore namespace, PVC/PV and owned LV cleanup | Pending |
| Live forced-failure alert | Pending; WO-10 |
| Full etcd restore on cairo-2 | Outside WO-09; WO-23 |

Use the [owner runbook](../runbooks/backup-and-restore.md). Static unit/schema,
promtool and synthetic-container evidence belongs in the PR/CI artifacts; it does
not substitute for tester sign-off or a measured restore timeline.
