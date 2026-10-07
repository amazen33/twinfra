# Local service URLs and browser access

Verified on **2026-10-07** from Windows against `vcloud-wsl-local`. This is the
WSL validation cluster. A reference hostname or a Service manifest does not
establish that its backend is deployed or that a browser route exists.

| Service | Windows browser URL | Verified result |
| --- | --- | --- |
| Argo CD Core dashboard | <http://127.0.0.1:8080/> | UI rendered with `vcloud-wsl-platform`; HTML, JavaScript and application API passed |
| Lab HTTP smoke server | <http://127.0.0.1:18080/> | HTTP 200 with `vcloud-wsl-ok`; a connectivity test, not a SaaS application |

The two URLs use **HTTP**, on this Windows computer only. Keep WSL running.
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
# When finished:
sudo bash lab/wsl/access.sh stop
```

The script verifies the owned single-node context, ready Pods and the running
Argo CD image digest. It copies the CLI from that cached image and verifies the
binary SHA-256 before execution; no internet download is required. It starts
two exact transient systemd units, preserves unrelated listeners and keeps
access alive after the shell closes. Repeated `start` calls reuse active units.
After WSL stops or reboots, run `start` again. The script installs no Kubernetes
workload and does not change network policies, Services or Windows firewall rules.

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
sudo systemctl status vcloud-wsl-argocd-dashboard.service vcloud-wsl-http-access.service
sudo journalctl -u vcloud-wsl-argocd-dashboard.service -u vcloud-wsl-http-access.service -n 40
sudo ss -ltnp 'sport = :8080 or sport = :18080'
```

The dashboard is Core in `platform-services`. At the review on 2026-10-07,
there is no full `argocd-server` Service in `argocd`. A stale cluster discovery
binding from the earlier installation still targets that namespace. Restore
the single-owner RBAC rather than installing another controller over the
existing cluster-wide Argo CD resources.

## Services with no working browser endpoint

| Component | Current local state |
| --- | --- |
| Spinifex EC2 API and console | No controller or console deployed; offloading remains disabled |
| APISIX, Knative and customer SaaS/API | No runtime deployment or ingress route |
| Grafana and Prometheus | Not deployed |
| OpenTelemetry collector and trace backend | Not deployed; a collector is a telemetry receiver, not a dashboard |
| Keycloak and OpenBao | Not deployed |
| vLLM and RAG | Not deployed; heavy GPU profiles remain bypassed |
| PostgreSQL/pgvector | CNPG operator is Ready; no database Pod is running at this snapshot |

`api.vcloud.example.com`, `auth.vcloud.example.com`, the example Spinifex
endpoint and Kubernetes `*.svc.cluster.local` references are **not working
Windows browser URLs**. A ClusterIP or Pod IP is an internal address; Pod IPs
also change on replacement. No Ingress, NodePort or LoadBalancer is configured
in this snapshot. Do not publish example URLs as live endpoints.

## Reconciliation blocker visible in the working dashboard

`vcloud-wsl-platform` is **Healthy / Unknown**, with `ComparisonError`: its
`platform-services:argocd-application-controller` ServiceAccount is denied
cluster discovery (the review captured forbidden ControllerRevision listing,
and the Node authorization check also failed). The dashboard displays this
actual status. Resolve
installation ownership and restore the vetted controller RBAC before treating
GitOps as accepted. Avoid granting `cluster-admin` as a workaround. Database
and full platform readiness require their own deployment and acceptance gates.
