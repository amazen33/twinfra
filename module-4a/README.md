# Module 4a: OpenBao dynamic secrets and verification

This module configures PostgreSQL dynamic credentials and KV-v2 static API keys,
binds Kubernetes identities to exact roles, and mounts secrets through the OpenBao
CSI provider. It includes an executable three-step curl/psql integration test.
It does not initialize/unseal OpenBao or install node agents.

| Deliverable | File |
| --- | --- |
| Database secrets engine | [mount](openbao/database-mount.json), [connection](openbao/database-connection.json), [application role](openbao/database-role-vcloud-app-readonly.json) |
| Static API-key backend | [KV-v2 mount](openbao/kv-mount.json), [CAS configuration](openbao/kv-config.json) |
| Kubernetes authentication | [configuration](openbao/kubernetes-config.json), [CSI role](openbao/kubernetes-role-vcloud-csi-client.json), [test role](openbao/kubernetes-role-vcloud-validation.json) |
| Bounded permissions | [workload policy](openbao/policies/workload.hcl), [validation policy](openbao/policies/validation.hcl) |
| CSI files | [SecretProviderClass](manifests/secretproviderclass.yaml), [mount patch](patches/consumer-csi.jsonpatch.yaml), [complete consumer](manifests/consumer.yaml) |
| Optional Kubernetes Secret delivery | [static-key sync patch](patches/static-secret-sync.jsonpatch.yaml) |
| Database lifecycle and HBA | [SQL](sql/bootstrap-lifecycle.sql), [HBA patch](patches/cnpg-hba.mergepatch.yaml) |
| Scoped network and TokenReview | [policies](manifests/network.yaml), [RBAC](manifests/reviewer-rbac.yaml) |
| Configuration and test | [configure](scripts/configure-openbao.sh), [three-step test](scripts/verify-rotation.sh), [Kubernetes login wrapper](scripts/login-and-verify.sh) |
| Validation runtime | [validator Pod](examples/validator-pod.yaml), [Dockerfile](images/verifier.Dockerfile), [test evidence](../docs/module-4a-validation.json) |

## Names and API contracts

`SecretBackend` here means an OpenBao **secrets-engine mount**, not a built-in
Kubernetes CRD. The public JSON payloads are sent to OpenBao's HTTP API; do not
apply them with kubectl. Kubernetes uses `secrets-store.csi.x-k8s.io/v1` and
`kind: SecretProviderClass`, with `spec.provider: openbao`.

The correct volume driver name is **`secrets-store.csi.k8s.io`**. The requested
`csi-secrets-store.csi.k8s.io` spelling is not this driver's registered name.
Pinned integration inputs are OpenBao **2.7.1**, OpenBao Helm **0.30.2**, provider
**2.0.3**, Secrets Store CSI Driver **1.6.1**, CNPG **1.30.1** and the existing
Kubernetes **1.36.5** schema profile. See [the lock](artifacts.lock.json).

```text
Pod service account -> TokenRequest (audience openbao) -> OpenBao Kubernetes auth
  -> workload policy -> database/creds/vcloud-app-readonly -> one database.json
                     -> kv/data/vcloud/api -> api-key file
OpenBao -> verified TLS -> CNPG RW service -> constrained credential lifecycle
Test identity -> database/creds/vcloud-validation -> TLS SELECT -> sync revoke -> rejected login
```

## Bootstrap and trust prerequisites

Accept the existing Ubuntu/Kubernetes/CNPG foundation first. Supply an initialized,
unsealed, TLS-verified OpenBao service at
`https://openbao.platform-services.svc.cluster.local:8200`. OpenBao server Pods must
use service account `openbao` in `platform-services` and labels
`app.kubernetes.io/name: openbao`, `component: server`. Match the documented network
selectors to the actual reviewed profile before deployment.

Use the approved private CA and certificates with SANs for the actual OpenBao and
CNPG DNS names. Preserve CA and hostname verification; neither script has an insecure
TLS option. Unseal shares, recovery keys, administrator tokens, initial management
passwords and API keys stay outside Git, images, environment variables, logs and
persistent plaintext files. Scripts use private client-side tmpfs and clean it on exit.
Audit devices must retain HMAC redaction and disable raw secret-value logging.

OpenBao's projected/default service-account token and cluster CA must be available
at `/var/run/secrets/kubernetes.io/serviceaccount/`. The Kubernetes auth configuration
omits a persisted reviewer JWT, so OpenBao rereads the rotating local token. Apply
the narrow TokenReview binding; do not give application identities auth-delegator,
Secret-read or token-creation permissions.

Mount the **public CNPG CA** into every OpenBao server at
`/openbao/trust/postgres/ca.crt` before registering the connection. For the existing
OpenBao chart owner, merge these fields into its reviewed values, preserving all
existing volumes and mounts:

```yaml
server:
  serviceAccount:
    name: openbao
    createSecret: false
  volumes:
    - name: postgres-public-ca
      configMap:
        name: vcloud-postgres-public-ca
        defaultMode: 292
  volumeMounts:
    - name: postgres-public-ca
      mountPath: /openbao/trust/postgres
      readOnly: true
```

These are owner-integration values, not a replacement OpenBao deployment profile.
Populate that ConfigMap from only the public `ca.crt` of CNPG's CA Secret; never copy
its CA private key. Keep `enableSuperuserAccess: false` in the CNPG Cluster.

## CSI provider prerequisites and node approval

Accept the CSI driver and provider separately, on Linux nodes. Their kubelet/provider
socket host mounts and required node privileges are **outside** the frozen
kubeadm/Cilium/NVIDIA approval. No installer, privilege exemption or hostPath workload
is introduced by this module. Review the exact rendered node inventory and obtain
its approval before installing these additional node components.

Place the reviewed provider in `kube-system`, with label
`app.kubernetes.io/name: openbao-csi-provider`, retaining its Agent's memory cache
and UNIX socket. Its Agent must trust the public OpenBao CA, verify the upstream
hostname, and use the explicit mirrored 2.7.1 image; the provider uses mirrored 2.0.3.
Configure the provider's remote OpenBao address and CA at that owner integration.
Do not set `baoAddress` on this SecretProviderClass, which would bypass the Agent.
Disable provider debug logging and persistent Agent cache storage.

The driver profile needs `enableSecretRotation: true`, `rotationPollInterval: 2m`,
and `syncSecret.enabled: false` for the primary file-only integration. The driver
must have the accepted token-request RBAC. Merge the
[CSIDriver patch](patches/csi-fsgroup.mergepatch.yaml) through its owner: it sets
`fsGroupPolicy: File`, `requiresRepublish: true` and a 600-second `openbao` audience.
Preserve any other already-reviewed token audiences when merging its array.

Secrets are 0440 files with Pod fsGroup 65532. Prove that the non-root consumer can
read them **both at initial mount and after rotation**; the upstream descriptor
does not explicitly set File group handling. Do not relax files to world-readable
or change the workload to root to conceal a failed CSI permissions integration.

## PostgreSQL configuration

Review [bootstrap-lifecycle.sql](sql/bootstrap-lifecycle.sql) and execute it in
database `vcloud` as CNPG's local `postgres` administrator. That SQL authority is
required to create roles and terminate only registered-role sessions; OS execution
remains the existing PostgreSQL UID 26. OpenBao's login role is non-superuser,
NOCREATEROLE and has only EXECUTE on three schema-protected lifecycle functions.
The functions pin their search path, quote identifiers/values, bound expiration,
and keep a registry to prevent revoking unrelated roles.

For an already-accepted cluster, resolve its actual primary Pod name:

```bash
primary_pod=$(kubectl --context vcloud-prod-01 get cluster -n platform-services vcloud-postgres \
  --output=jsonpath='{.status.currentPrimary}')
test -n "$primary_pod"
kubectl --context vcloud-prod-01 exec -i -n platform-services "$primary_pod" -c postgres -- \
  psql --no-psqlrc --set ON_ERROR_STOP=1 --username postgres --dbname vcloud \
  < module-4a/sql/bootstrap-lifecycle.sql
kubectl --context vcloud-prod-01 exec -it -n platform-services "$primary_pod" -c postgres -- \
  psql --no-psqlrc --username postgres --dbname vcloud
# At the psql prompt: \password openbao_manager
# Supply a strong initial password through the hidden prompt; do not put it in SQL/history.
```

The application group receives SELECT on existing public tables and future public
tables created by `vcloud_app`. Review that table scope for your application; dynamic
users cannot own/create application objects or execute lifecycle functions. Fold the
[HBA patch](patches/cnpg-hba.mergepatch.yaml) into Module 2's **chart-owned source**,
keeping its other reviewed entries. Its ordering permits this read group and manager
only in `vcloud`, over SCRAM/TLS, before rejecting their access to other databases.
The offline validator checks that patch after composing a full CNPG Cluster.

## Configure the secrets engines and roles

`configure-openbao.sh --plan` prints operations without reading credentials or
contacting a server. Execute `--apply` from a trusted operator client with the
documented OpenBao/API reachability; keep CA files local/public and use tmpfs.
For in-cluster configuration, the validator Pod below has the required network paths.

```bash
bash module-4a/scripts/configure-openbao.sh --plan
set +x
read -r -s -p 'Short-lived OpenBao configuration token: ' config_token; printf '\n' >&2
read -r -s -p 'Initial openbao_manager password (new connection only): ' manager_password; printf '\n' >&2
read -r -s -p 'Static API key: ' api_key; printf '\n' >&2
bash module-4a/scripts/configure-openbao.sh --apply \
  --bao-ca /etc/ssl/vcloud/bao-ca.crt --pg-ca /etc/ssl/vcloud/postgres-ca.crt \
  --api-key-fd 5 \
  3< <(printf '%s\n' "$config_token") \
  4< <(printf '%s\n' "$manager_password") \
  5< <(printf '%s\n' "$api_key")
unset config_token manager_password api_key
```

The script refuses conflicting mount types, retains an existing connection's
encrypted password, checks its public TLS/identity settings, and rotates the management
password through OpenBao on each authorized reconcile. Static writes use KV-v2 CAS:
the first key uses CAS 0; an existing key is retained unless `--rotate-api-key` is
explicit. Rotation uses the observed current version and fails on a race. Operations
are sequential and not one database/OpenBao transaction; inspect a failed run and retry.

KV storage/version changes do not revoke a key at its issuing external API. Coordinate
that issuer's create/revoke procedure and consumer reload separately. The database
three-step test below does not claim to verify third-party API-key invalidation.

## Workload integration and optional Kubernetes Secret

Build, scan and publish the verifier image before applying the example:

```bash
docker build -f module-4a/images/verifier.Dockerfile \
  -t registry.vcloud.example.com/vcloud/openbao-verifier:1.0.0 .
docker push registry.vcloud.example.com/vcloud/openbao-verifier:1.0.0
# Enforce semantic-tag immutability at the registry; record its real digest when published.
make module4a-validate module4a-test
kubectl --context vcloud-prod-01 apply --dry-run=server -f module-4a/manifests
kubectl --context vcloud-prod-01 apply -f module-4a/manifests
```

The standalone `vcloud-secrets-consumer` sleeps with readiness checks for CSI file
shape/readability; it does not pretend to be a RAG application or database query service.
It owns no Module 2 or Module 3 workload. Its [base](examples/consumer-base.yaml)
and [JSON patch](patches/consumer-csi.jsonpatch.yaml) compose to the delivered full
Deployment. For application use, add these file mounts through that application's
GitOps owner and implement connection-pool reload/close when the paired JSON changes.
Never mount the secret files with `subPath`, which prevents normal update visibility.

`database.json` contains one whole provider response (`data.username`, `data.password`,
`lease_id`, `lease_duration`), so a reader opens and parses a single credential generation.
`api-key` is the extracted current KV-v2 key. Agent renewal can retain the same database
credential; CSI polling is not a promise to issue a new database user every two minutes.
Applications must fail closed after expiry/revocation and reopen connections after updates.

If a specific integration requires a Kubernetes Secret, the optional
[static sync patch](patches/static-secret-sync.jsonpatch.yaml) asks CSI to create
`Secret/vcloud-api-key-cache`, type Opaque, key `api-key`. No Secret value is stored
in Git. Enable that driver's reviewed sync RBAC and `syncSecret.enabled` first;
require API-server encryption at rest, strict Secret RBAC and file-based consumption.
The cache exists only while a consuming Pod mounts the class and has its own lifecycle.
Dynamic database credentials are never synchronized into Kubernetes Secrets here.

## Three-step live validation

Create `ConfigMap/vcloud-secrets-trust` in `workload-apps` from the **public** OpenBao
and CNPG CA certificates, keys `bao-ca.crt` and `postgres-ca.crt`. Then:

```bash
kubectl --context vcloud-prod-01 apply -f module-4a/examples/validator-pod.yaml
kubectl --context vcloud-prod-01 wait -n workload-apps --for=condition=Ready pod/vcloud-secret-validator --timeout=120s
kubectl --context vcloud-prod-01 exec -n workload-apps vcloud-secret-validator -- \
  bash /opt/vcloud/login-and-verify.sh \
  --bao-ca /run/trust/bao-ca.crt --pg-ca /run/trust/postgres-ca.crt
kubectl --context vcloud-prod-01 delete pod -n workload-apps vcloud-secret-validator
```

The wrapper logs in with the 600-second projected `openbao` JWT, invokes the
three-step script, and revokes its own OpenBao token on exit. Its service account
has no Kubernetes RBAC and no automatic API token. The Pod expires after 30 minutes.
Alternatively run [verify-rotation.sh](scripts/verify-rotation.sh) with an existing
short-lived validation-role token on descriptor 3, using the same hidden-prompt pattern.

Expected output:

```text
[1/3] PASS: renewable validation lease issued (values redacted)
[2/3] PASS: leased identity connected to vcloud using verified TLS
[3/3] PASS: synchronous revocation completed; a fresh login was rejected
```

Step 1 requires a renewable 30–300-second lease on `vcloud-validation`; step 2 checks
the leased username, database and negotiated TLS with psql; step 3 calls path-scoped
`sys/leases/revoke/<lease_id>` with `sync: true` and requires a fresh PostgreSQL login
to report authentication rejection. A timeout, connection refusal, CA failure,
revocation API error or surviving credential exits nonzero. Private temporary files
are removed; a failed intermediate test attempts lease cleanup. The validation ACL
forbids a body `lease_id` override that could bypass its URL scope.

The test closes its successful psql session before revocation. The supplied SQL also
terminates registered-role sessions, but acceptance of an already-open/pool session
requires a separate long-lived-session test. Default English PostgreSQL auth messages
are expected; a different server locale fails closed rather than accepting any error.

## What was verified locally

`make module4a-validate module4a-test` verifies locked/reproducible schemas, CSI patch
composition, public backend/auth wiring, original node approval and restricted Pod
contexts. Script tests execute real Bash and jq with **mocked curl, psql and tmpfs
inventory**; Windows tests simulate Unix permission bits. They check credential
redaction, TLS settings, cleanup, stale config rejection, CAS conflicts and rejection
of false-positive revocation failures. See [evidence](../docs/module-4a-validation.json).

Live SQL installation, OpenBao login/leases, actual CSI mounts and permissions after
rotation, database connection/revocation, controller admission and OCI builds remain
unexecuted. A passing local test is not a production or runtime acceptance claim.

Primary references: [OpenBao PostgreSQL](https://openbao.org/docs/secrets/databases/postgresql/),
[Kubernetes authentication](https://openbao.org/docs/auth/kubernetes/),
[CSI configuration](https://openbao.org/docs/platform/k8s/csi/configurations/),
[pinned CSI response implementation](https://github.com/openbao/openbao-csi-provider/blob/v2.0.3/internal/provider/provider.go),
[CSI rotation](https://secrets-store-csi-driver.sigs.k8s.io/topics/secret-auto-rotation.html),
[PostgreSQL password files](https://www.postgresql.org/docs/18/libpq-pgpass.html),
[safe SECURITY DEFINER functions](https://www.postgresql.org/docs/18/sql-createfunction.html).
