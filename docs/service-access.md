# Local service URLs and browser access

Verified on **2026-10-07** from Windows against `vcloud-wsl-local`. This is the
WSL validation cluster. A reference hostname or a Service manifest does not
establish that its backend is deployed or that a browser route exists.

| Service | Windows browser URL | Verified result |
| --- | --- | --- |
| Argo CD Core dashboard | <http://127.0.0.1:8080/> | UI rendered with `vcloud-wsl-platform`; HTML, JavaScript and application API passed |
| Lab HTTP smoke server | <http://127.0.0.1:18080/> | HTTP 200 with `vcloud-wsl-ok`; a connectivity test, not a SaaS application |
| APISIX -> CPU Knative demo | <http://127.0.0.1:18080/> with Host `demo-cpu-app.workload-apps.example.com` | HTTP 200 and `vcloud-knative-cpu-ok` verified from WSL and Windows |
| Prometheus | <http://127.0.0.1:9090/query> | Targets API verified from Windows; APISIX, CNPG and Knative up |
| Grafana | <http://127.0.0.1:3000/login> | Application health HTTP 200/database ok; credentials remain private |
| Keycloak | <https://localhost:18443/realms/vcloud/.well-known/openid-configuration> | WSL OIDC discovery with verified TLS; browser trust requires its public lab certificate |
| LocalStack Community AWS API | <http://127.0.0.1:4566/_localstack/health> | Windows and WSL HTTP 200; S3, EC2, IAM and DynamoDB running; JSON API, no console GUI |

Keycloak's discovery URL returns JSON by design; its GUI is
<https://localhost:18443/admin/>. The operator supplied a working discovery
document with issuer `https://localhost:18443/realms/vcloud`. Windows and WSL
independently returned HTTP 200 with the public lab certificate and hostname
verified. This confirms transport/discovery, not an administrator login.

Administrator provisioning and private password retrieval are documented in
the [Keycloak admin runbook](keycloak-admin-access.md). The intended master-realm
username is `vcloud-admin`; no password appears in this repository.

LocalStack port 4566 was repaired after the owned forward exhausted rapid retries
during a temporary API-server outage. Its root and health URLs now return HTTP
200 from Windows. [Recovery instructions](../lab/wsl/localstack/README.md#recovery)
include the delayed-retry and health-check helper.

OpenBao's `{"initialized":false}` response is successful HTTP 200 from its
initialization-status API. It is reachable but has not issued unseal shares or a
root token; initialization remains behind the operator PGP-key gate.

## Unified Twinfra console profile

**Updated 2026-10-08:** the native React portal is activated at
<http://localhost:18080/console/> with verified OIDC/MFA login, all six views,
both emulator APIs and positive/negative authorization. Use `localhost`
consistently. Sign in with the dedicated **vcloud-realm** `vcloud-admin` account;
retrieve its separate temporary password with `deploy/console/copy-password.ps1`.
First login requires password change and TOTP. See the
[portal runbook](../console/README.md) and
[acceptance record](acceptance/vcloud-console-2026-10-08.md).

| Portal path | Function |
| --- | --- |
| <http://localhost:18080/console/overview> | Namespace workload health |
| <http://localhost:18080/console/storage> | S3 buckets/object keys, either emulator |
| <http://localhost:18080/console/localstack> | LocalStack/MiniStack health and EC2 metadata |
| <http://localhost:18080/console/dynamodb> | Table names/metadata, either emulator |
| <http://localhost:18080/console/gitops> | Argo Application sync/health |
| <http://localhost:18080/console/iam> | Portal identity and roles |

The following paragraph describes the earlier hostname-based reference;
it does not supersede the activated localhost portal above.

The new [console runbook](../lab/wsl/console/README.md) prepares
`http://console.vcloud.local:18080` with controller-managed routes, an MIT
navigation shell, distinct MiniStack/LocalStack API prefixes, and MIT read-only
S3/DynamoDB views. The four new Deployments are Ready in the WSL lab; both
emulators passed signed S3, EC2, IAM and DynamoDB reads on 2026-10-07.

**The earlier `console.vcloud.local` URL remains gated.** Its discovery/hostname
reference differs from the activated localhost profile. Its historical missing
Secret gate was satisfied for the new portal by isolated client provisioning;
no hostname resolution or WebSocket handshake is claimed for this reference.
`/spinifex/` and `/vault/` are excluded disabled references, not working browser
links. Complete the identity/CA/DNS/base-path gates in the runbook first.

The remaining URLs below retain their existing access procedures; no console
port-forward, Windows hosts entry or broad firewall exception was installed.

The HTTP links and Keycloak HTTPS listener bind loopback on this computer only. Keep WSL running.
The dashboard has been opened in Codex. Core's local dashboard uses the invoking
process's Kubernetes credentials rather than a separate Argo CD login; this is
the upstream [Core access model](https://github.com/argoproj/argo-cd/blob/v3.5.3/docs/operator-manual/core.md).
Root is required here to read `/etc/vcloud-wsl/kubeconfig.yaml` (0600). No
credential is copied to Windows, printed or committed. Bind only `127.0.0.1`:
this local admin session is unsuitable for public or LAN exposure.

## Start, check and stop access

Inside Ubuntu WSL:

```bash
cd /mnt/e/vCloud
sudo bash lab/wsl/access.sh start
sudo bash lab/wsl/access.sh status
# Deploy the endpoint profile first, then start its application/monitoring forwards:
sudo bash lab/wsl/endpoints/access.sh start
sudo bash lab/wsl/test-e2e.sh
sudo bash lab/wsl/localstack/access.sh
sudo bash lab/wsl/localstack/verify.sh
# When finished:
sudo bash lab/wsl/access.sh stop
```

The script verifies the owned single-node context, ready Pods and the running
Argo CD image digest. It copies the CLI from that cached image and verifies the
binary SHA-256 before execution; no internet download is required. It starts
exact owned transient systemd units, preserves unrelated listeners and keeps
access alive after the shell closes. Repeated `start` calls reuse active units.
After WSL stops or reboots, run `start` again. The script installs no Kubernetes
workload and does not change network policies, Services or Windows firewall rules.
When APISIX exists, the Core access helper delegates the HTTP forward to the
endpoint helper and retains the old hostless smoke route. Its stop command
stops Core and the HTTP forward only; other component units are separate.

From PowerShell, start access and test the actual Windows route:

```powershell
Set-Location E:\vCloud
wsl.exe -d Ubuntu -- bash /mnt/e/vCloud/lab/wsl/access.sh start
& .\lab\wsl\verify-access.ps1
```

The verifier checks the dashboard HTML route, referenced JavaScript bundle,
version/settings/projects/applications APIs and exact smoke response. Evidence
is written to `.build/service-access/access-validation.json`. An access pass
does **not** imply successful GitOps reconciliation.

If access fails:

```bash
sudo systemctl status vcloud-wsl-argocd-dashboard.service vcloud-wsl-apisix-access.service
sudo journalctl -u vcloud-wsl-argocd-dashboard.service -u vcloud-wsl-apisix-access.service -n 40
sudo ss -ltnp 'sport = :8080 or sport = :18080'
```

The dashboard is Core in `platform-services`, with no second Argo installation.
The 2026-10-07 discovery/DNS repair restored its existing owner and the platform
Application is now Synced/Healthy. See the
[application/observability runbook](wsl-local-milestones-3-5.md).

## Services with no working browser endpoint

| Component | Current local state |
| --- | --- |
| Spinifex EC2 API and console | No controller or console deployed; offloading remains disabled |
| LocalStack Web Console | No GUI installed; Community 4.14.0 AWS API emulator is available on loopback 4566 |
| Customer SaaS/API | CPU smoke demo runs; production authorization and application acceptance remain separate |
| OpenTelemetry trace GUI/backend | Collector exports a real demo span to logs; no trace GUI or durable backend is deployed |
| OpenBao activation | Server runs but is uninitialized/sealed; four operator public keys are absent |
| vLLM and RAG | Not deployed; heavy GPU profiles remain bypassed |
| PostgreSQL/pgvector GUI | Database Ready; TLS/vector/persistence verified; no database GUI is deployed |

`api.vcloud.example.com`, `auth.vcloud.example.com`, the example Spinifex
endpoint and Kubernetes `*.svc.cluster.local` references are **not working
Windows browser URLs**. A ClusterIP or Pod IP is an internal address; Pod IPs
also change on replacement. No NodePort, LoadBalancer or Windows DNS entry is
configured for the endpoint profile; access uses private loopback forwarding
and controller-reconciled APISIX Host routes. Do not publish example domains as
resolvable live endpoints.

For the AWS API Host route, use:

```bash
curl -i -H 'Host: aws.platform.example.com' http://127.0.0.1:18080/
curl --resolve aws.platform.example.com:18080:127.0.0.1 \
  http://aws.platform.example.com:18080/_localstack/health
```

Both returned HTTP 200 on 2026-10-07, with all four configured API services
running. The [LocalStack runbook](../lab/wsl/localstack/README.md) covers API
tests, security, state loss on restart and controller prerequisites. This EC2
emulator does not deploy Spinifex or launch VMs.

## OpenBao operator endpoint

`http://127.0.0.1:8200/v1/sys/init` forwards to the Pod's loopback-only HTTP
listener. The normal in-cluster Service uses HTTPS 8200. GET returned false on
2026-10-07; the guarded init helper returned Linux exit 3 for missing public
keys and created no init-output Secret. Use the
[PGP gate](wsl-local-milestones-3-5.md#openbao-initialization-gate) before manual
operator unseal. No plaintext keys/token or private Grafana credentials are
displayed here; Ready transport probes do not establish secrets acceptance.
