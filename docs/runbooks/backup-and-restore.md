# cairo-1 off-node backups and restore drill

Status: static implementation; live acceptance **Pending**.
Follow [WO-09 Amendments 1–3](../work-orders/WO-09-backups-and-restore-drill.md),
[ADR-0054](../adr/0054-licence-ladder-and-enterprise-grade-gate.md) and the
[toolchain-wave amendment](../adr/amendments/0049-amendment-1-toolchain-wave.md).
WO-08 cert-manager must be healthy before these live steps. Nothing here has
connected to or changed the Dell. This is dev backup design, not HA or DR acceptance.

## Targets and boundaries

| Data class | Method / cadence | Approved RPO | Approved RTO / verification |
| --- | --- | --- | --- |
| Application PostgreSQL | CNPG Barman plugin: daily 02:00 UTC base, continuous gzip WAL, archive_timeout 300s | 15 min | 2 h dev PITR; row counts and checksums |
| OpenBao PostgreSQL storage | Included in the same physical PostgreSQL backup | 15 min | 2 h PostgreSQL recovery; unseal material separately held by owner |
| Keycloak PostgreSQL storage | Included in the same physical PostgreSQL backup | 15 min | 2 h PostgreSQL recovery; isolated drill only |
| Kubernetes etcd | Admitted etcd image, snapshot/status, CMS encryption then R2 upload every 6 h UTC | 6 h | Decrypt + snapshot status in WO-09; full datastore restore/RTO only WO-23 cairo-2 |

Retention is seven days (Barman recovery window; etcd owned objects older than
seven days). R2 default encryption at rest complements mandatory client-side
encryption for etcd, which contains Kubernetes Secrets. Actual measured RPO/RTO
and timestamps belong in the [Pending drill receipt](../acceptance/backup-restore-drill-2026-10-16.md).

Public configuration lives in [backup-config.json](../../deploy/common/backup-config.json):
bucket `twinfra-dev-cairo-1-backups`, region `auto`, endpoint
`https://481407e21f55c4bcc20def49989f03e2.r2.cloudflarestorage.com`, default
jurisdiction / automatic location (not EU). PostgreSQL prefix is
`postgres/twinfra-postgres`; etcd prefix is `etcd/twinfra-dev-cairo-1`.
The endpoint is configurable; a jurisdiction change requires reviewed config,
Secret/target preparation and regeneration, not generator code edits. TLS
verification stays enabled. Only dev data may leave for this target. Production
requires an in-country or owner-controlled choice under ADR-0041.

## Owner preparation and activation

1. Complete WO-08, image admission and licence qualification. Review fresh Linux
   scans for the newest official plugin release at least 14 days old. Selected
   v0.15.1 was published 2026-09-30; checked 2026-10-16. Never self-build upstream
   Go binaries. No Barman vulnerability exceptions are granted in this draft.
   A toolchain-wave proposal must satisfy every condition of ADR-0049 Amendment 1
   and receive a distinct owner batch approval. Unlisted findings remain blocking.
2. Owner creates the bucket and a token scoped to **Object Read and Write on this
   bucket only**. Do not grant account administration or access to other buckets.
   Confirm TLS, bucket lifecycle and no public access. Do not configure lifecycle
   deletion that races Barman recovery-window retention.
3. Generate the CMS recipient on the **owner laptop**, with OpenSSL already
   available through an approved owner toolchain. Use an encrypted offline key:

   ```bash
   umask 077
   openssl req -new -x509 -newkey rsa:4096 -sha256 -days 365 \
     -subj '/CN=Twinfra dev backup recipient' \
     -keyout twinfra-backup-private.pem -out twinfra-backup-recipient.pem
   openssl x509 -in twinfra-backup-recipient.pem -noout -fingerprint -sha256 -dates
   ```

   Let OpenSSL prompt for the private-key passphrase. No `-passout` or password
   environment variable. Store private key/passphrase offline, separately from
   the Dell and bucket. Send **only** `twinfra-backup-recipient.pem` to the cluster
   administration workstation. Never send private material to the Dell.
   ECDH P-256 is also supported and tested; RSA-4096 is the documented ceremony.
   Retain old private keys until all corresponding retained snapshots expire;
   rotate the public certificate before expiry and prove a restore after rotation.
4. Create the credential Secret from hidden prompts/stdin, without a plaintext
   file, environment variable, shell argument or last-applied annotation:

   ```bash
   python tools/platform_backup_secret.py --context twinfra-dev-cairo-1 \
     --certificate /owner/public/twinfra-backup-recipient.pem
   ```

   This creates `twinfra-backup-s3` in `twinfra-platform-services` with only
   `ACCESS_KEY_ID` and `ACCESS_SECRET_KEY`, and public ConfigMap
   `kube-system/twinfra-backup-recipient` with `certificate.pem`. No command prints credentials.
   WO-08 later owns rotation through External Secrets. Existing Secret rotation
   must use the owner's approved secret workflow; this helper refuses replacement.
   If the second create fails, the Secret may already exist: inspect names only
   and create the public ConfigMap from the certificate with the owner workflow;
   never dump the Secret. Certificate rotation updates that public ConfigMap.
5. Build and stage **all** images using the current lock, not a copied digest:

   ```bash
   python tools/platform_dev.py build-images --download-inputs
   python tools/platform_dev.py stage-images --context twinfra-dev-cairo-1 --ssh <owner-key-only-target> --apply
   python tools/platform_dev.py stage-images --context twinfra-dev-cairo-1 --ssh <owner-key-only-target> --check
   ```

   `backups.oci.tar` is the Python/OpenSSL + existing hash-locked SDK image.
   Barman manager/sidecar are unmodified official images. The etcd Job uses the
   already admitted 3.6.15 image; no Go host tool, age, rclone or pyrage is installed.
   Record the real UTC staging attestation in the PR; static tests cannot supply it.
6. Default `enabled: false` leaves the existing Argo applications/platform
   byte-identical and the separate etcd CronJob suspended. After prerequisite
   approval, change this flag in a reviewed activation PR and regenerate:

   ```bash
   python tools/platform_backup_sources.py render
   python tools/platform_dev.py render
   python tools/platform_dev.py check
   ```

   Argo then reconciles the plugin, ObjectStore, daily schedule, WAL parameters
   and operator watch of `twinfra-restore-drill`. The node CronJob is separately
   owner-applied (no broadened Argo kube-system destination permission):

   ```bash
   kubectl --context twinfra-dev-cairo-1 apply --server-side -k deploy/environments/dev/cairo-1/backups/node
   kubectl --context twinfra-dev-cairo-1 -n twinfra-platform-services get certificates,objectstores,scheduledbackups
   python tools/platform_dev.py backup-check --context twinfra-dev-cairo-1
   ```

   Wait for both plugin Certificates Ready, controller Available and CNPG healthy.
   Before activation, the generated `backups/reference.yaml` is review material,
   not an install command. Disabling again needs a separate recovery plan: do not
   remove the plugin while WAL archiving still refers to it.

## Node exception and encryption

Named exception: `CronJob/kube-system/twinfra-etcd-backup`, exact PodSpec in
[backup-node-exception.json](../../deploy/common/backup-node-exception.json).
Only three individual etcd client files are mounted read-only into `snapshot`:
`ca.crt`, `healthcheck-client.crt`, `healthcheck-client.key`. Never `ca.key`, a
directory mount, host networking or a privileged container. UID 0 is required
only for `snapshot` (root-owned client key) and `snapshot-permissions` (0600
snapshot becomes group-readable). All capabilities are dropped, escalation is
off, filesystem read-only and seccomp RuntimeDefault. The latter has no TLS or
API-token mount. Verifier/uploader run as 65532. The non-system namespaces keep
restricted PSS; kube-system has this explicitly bounded node exception.

Plaintext and encrypted files exist only in the 512 MiB memory emptyDir, which
counts against node memory. The snapshot limit is 256 MiB. Only the uploader
receives a short-lived projected SA token; it GETs the exact credential Secret
and PATCHes the exact public status ConfigMap. S3 credentials stay in process
memory, never environment variables or files. The public certificate is mounted
read-only from its separately created ConfigMap and is never copied from a Secret.
The uploader removes plaintext before upload, verifies downloaded SHA-256 for
both ciphertext and manifest, then records success. Failed Jobs do not advance
the freshness clock. Retention deletes only owned etcd filenames in its prefix.

OpenSSL CLI **3.5.7** and its Debian package/binary hashes are verified in the
admitted Python base. Standard CMS DER with AES-256-GCM is selected if the actual
CMS capability probe succeeds. Only an explicit unsupported-cipher result permits
AES-256-CBC fallback plus a SHA-256 plaintext/ciphertext manifest. CBC plus hashes
does **not** authenticate against an attacker able to replace both objects; the
pinned base is required by CI to support GCM. No custom cryptographic construction.
CI generates private keys only inside a disposable container tmpfs and round-trips
a synthetic etcd snapshot; those are neither owner keys nor live acceptance.

Owner clarification (2026-10-16) supersedes Amendment 3's encryption choice:
**pyrage fails ADR-0054 governance (single maintainer, personal repo, no SECURITY.md);
not selected.** OpenSSL CMS replaces it; boto3 remains. No new OpenSSL package or
image is added. PyCA standard CMS is only the approved fallback if CLI is absent;
the verified CLI is present, so that fallback is not implemented.

## PostgreSQL isolated PITR drill

Only the owner/tester performs this after a successful base backup and WAL upload.
Stop writes to controlled fixture rows during the source checksum observation;
do not publish application/OpenBao/Keycloak rows or Secret values in the receipt.

1. In each source database, create or identify an approved non-sensitive fixture
   table. Through authenticated `psql` (existing secure credential workflow), record
   row count and `md5(string_agg(row_to_json(t)::text, '' ORDER BY id))` over its
   stable primary key. Use bounded fixtures, not a full-table memory aggregation.
   Record a UTC target timestamp after commit; confirm an archived WAL beyond it.
   Make a second fixture change after the timestamp so PITR discrimination is proven.
2. Allocate the **temporary** separate 20 GiB LV (preserves 20 GiB VG reserve):

   ```bash
   python tools/platform_dev.py host-storage --restore-drill --context twinfra-dev-cairo-1 --ssh <owner-key-only-target>
   python tools/platform_dev.py host-storage --restore-drill --context twinfra-dev-cairo-1 --ssh <owner-key-only-target> --apply
   python tools/platform_dev.py restore-manifest --context twinfra-dev-cairo-1 --target-time <UTC-target> > /owner/public/restore.yaml
   ```

   Read the plan before applying. The ownership receipt, LV UUID/tag and filesystem
   UUID are mandatory; foreign storage is refused. No fstab or original PG LV change.
3. Create only the rendered Namespace first, copy the two S3 keys in memory via
   `python tools/platform_backup_secret.py --context twinfra-dev-cairo-1 --copy-to-restore`,
   then apply the remaining rendered restore resources with server-side apply.
   Keep `/owner/public/restore.yaml` free of credentials. The restore source
   ObjectStore has **no retention policy** and the restored Cluster has **no WAL
   archiver**, so it cannot delete or overwrite the original archive.
4. Wait for `Cluster/twinfra-postgres-restore` healthy in `twinfra-restore-drill`.
   Repeat the same fixture count/checksum queries, confirm the later change is
   absent, and compare against the target observation. This verifies physical
   application, Keycloak and OpenBao data, not a second active identity/secrets
   service. Never point production clients at it. OpenBao unseal material stays
   outside the database backup and must be supplied separately for a future service
   recovery; do not initialise a second OpenBao against the restored data.
5. Record last recoverable committed fixture time and failure-simulation time for
   measured RPO, plus recovery-start and verified-query time for measured RTO.
   Sign only after comparison passes. Remove restore namespace, wait for PVCs/Pods
   to disappear, delete its retained PV explicitly, then:

   ```bash
   python tools/platform_dev.py host-storage --restore-drill --context twinfra-dev-cairo-1 --ssh <owner-key-only-target> --apply --remove
   ```

   Cleanup refuses API errors, a remaining namespace/PV or a foreign LV/mount.

## Etcd offline restore verification

Owner downloads a matching `.db.cms` and `.manifest.json` using a bucket-scoped
credential workflow on the recovery workstation, not a public URL. Verify the
manifest ciphertext SHA-256 first, then decrypt with the offline private key:

```bash
umask 077
openssl cms -decrypt -binary -inform DER -in snapshot.db.cms \
  -recip twinfra-backup-recipient.pem -inkey twinfra-backup-private.pem \
  -out snapshot-restored.db
```

OpenSSL prompts for the key passphrase. Require the plaintext SHA-256 to match
the manifest, and run `etcdutl snapshot status snapshot-restored.db --write-out=json`
from the **same admitted etcd image** on an isolated recovery runner. Never restore
over live etcd, put the private key on the Dell, or upload plaintext. Securely
remove the restored Secret-bearing file under the owner's encrypted-workstation
data handling policy. Full etcd restore belongs to WO-23 on cairo-2.

## Freshness and future alert integration

`platform_dev.py backup-check --context twinfra-dev-cairo-1` is read-only and fails
closed on missing/future/nonfinite timestamps or a newer failed base backup.
WARN/FAIL ages: base 86400/87300 seconds, WAL 600/900, etcd 18000/21600. No successful
check claims a tested RPO/RTO. `--prometheus` emits the last-success timestamp per
kind plus failure gauges. WO-10 must execute/scrape this contract regularly,
alert on missing observations, and install the generated PrometheusRule in
`backups/observability/`. Rules include absent metrics, stale backups and explicit
failure; `promtool test rules tests/backup-alerts.test.yaml` covers synthetic cases.
Forced live failure/alert acceptance waits for WO-10. Local tests never sign it.
