# vCloud control-plane portal

The React/TypeScript + Tailwind portal runs as `platform-services/vcloud-console`.
Open **<http://localhost:18080/console/>** on the Windows WSL host. Use `localhost`
consistently: the OIDC callback is not registered for `127.0.0.1`.
The existing APISIX loopback forward carries all portal views and API requests.

| Path | View |
| --- | --- |
| `/console/overview` | Live namespace Pod/Deployment health |
| `/console/storage` | S3 buckets and up to 100 object keys |
| `/console/localstack` | LocalStack/MiniStack health and EC2 instance metadata |
| `/console/dynamodb` | Table names and metadata |
| `/console/gitops` | Argo CD Application sync/health/revision |
| `/console/iam` | Keycloak identity and portal roles |

Storage, AWS and DynamoDB views select either emulator. These are original MIT,
read-only views. No real EC2 machines, MinIO server, cloud billing console,
Spinifex deployment or tenant database writes are added. Full Keycloak admin
remains at <https://localhost:18443/admin/>; Argo CD Core's operator dashboard
remains at <http://127.0.0.1:8080/>. Native views avoid fragile iframe embedding.
Optional original S3/DynamoDB views support `/console/proxy/storage/` and
`/console/proxy/dynamodb/`.

## First login

Use **vcloud-admin in the vcloud realm**, separate from the identically named
master administrator. Its temporary password is stored only in encrypted
Kubernetes Secret `platform-services/vcloud-wsl-console-admin` (`admin-user`,
`admin-password`, `realm`). Retrieve it privately in local PowerShell:

```powershell
Set-Location E:\vCloud
& .\deploy\console\copy-password.ps1
# Paste into the login form; clear the clipboard after use.
Set-Clipboard -Value ''
```

Keep clipboard history/cloud synchronization disabled for credentials. First
login requires password change and TOTP enrollment. Keep the new password/MFA
recovery material in operator custody. The Secret retains the initial password;
it is not updated by GUI password changes. No private value is printed, passed
as an argument/environment variable or stored in this repo.

`console.viewer` and `console.admin` are client roles on `vcloud-console`.
Both permit read-only portal access. `console.admin` also displays the external
Keycloak admin link; it grants no `realm-management`, master-realm or Kubernetes
administrative authority.

## Authentication boundary

APISIX validates OIDC signature, issuer/audience and client roles using
confidential code flow with PKCE S256. Anonymous APIs and roleless authenticated
ID tokens return 401 at the gateway; the BFF's role check returns 403.
Spoofed identity headers are scrubbed before authentication. Authorization,
Cookie and access/refresh token headers are removed before upstream forwarding.
JavaScript receives only reduced identity metadata, never JWTs or cookies.

The BFF repeats claims/expiry/role checks on APISIX's decoded `X-ID-Token`
header; it does **not** independently verify a signature. Cilium permits only
APISIX to reach Pod port 3000. Direct BFF exposure needs a new security design.
The namespace Role allows only get/list of Pods, Deployments and Applications;
no Secret, exec, write, node or cluster authority. Exec probes avoid world/node
health-port exceptions.

Session cookies are HttpOnly, SameSite=Lax and scoped to `/console`. The explicit
HTTP loopback profile uses `cookie_secure: false`; production requires HTTPS,
Secure cookies and separate DNS/CA/security acceptance. Keycloak dynamic private
TLS backchannel URLs preserve the browser issuer
`https://localhost:18443/realms/vcloud`. APISIX mounts only the public certificate
and sets `apisix.ssl.ssl_trusted_certificate`. Logs omit query values, auth
codes, cookies and tokens. Browser trust of the public lab certificate is an
operator prerequisite; never bypass TLS verification.

Same-origin native views need no CORS exception. CSP `frame-ancestors 'self'`
and X-Frame-Options SAMEORIGIN remain enforced. Legacy routes strip only exact
prefixes and retain CSP. This portal has no WebSocket backend; socket acceptance
is not claimed.

## Build and validation

Run from the repository root:

```bash
npm ci --prefix console --ignore-scripts --no-audit --no-fund
npm test --prefix console
npm run build --prefix console
docker build -f console/Dockerfile -t registry.vcloud.example.com/vcloud/vcloud-console:1.0.0 .
```

The WSL deployment uses a deterministic OCI layer on the vetted cached Python
base without a Docker socket, daemon or privileged build Pod:

```bash
cd /mnt/e/vCloud
sudo python3 tools/build_console_image.py --import
python3 tools/vcloud_console.py
python3 tools/vcloud_console.py --check
python3 -m unittest discover -s tests -p test_vcloud_console.py -v
python3 tools/vcloud_console.py --validate \
  --kubeconform .build/ci-linux-assets/bin/kubeconform \
  --schemas .build/ci-linux-assets/schemas
```

`image.lock.json` pins the application digest and source hashes. Changed inputs
require rebuild/import, manifest regeneration and retest. The OCI builder is
Linux/amd64, verifies base blobs, stages archives on ext4 `/tmp`, and imports
only into the owned external containerd. It does not push to the placeholder
registry. The Dockerfile is an alternative recipe; executing that build is a
separate gate.

## Controlled deployment and GitOps

Existing Keycloak/master administration, stable Secret encryption, public TLS
and cached images must pass first. The helper preserves existing credentials:

```bash
sudo python3 tools/configure_console_identity.py --create-admin
sudo python3 deploy/console/deploy-wsl.py             # preflight
sudo python3 deploy/console/deploy-wsl.py --apply     # candidate
sudo python3 tools/test_console_live.py
```

The candidate temporarily pauses only `vcloud-wsl-endpoints`, reloads Keycloak
and APISIX and applies the restricted portal/narrow policies. The previous
annotation is recorded in `.build/console/local-trial.json`. After publishing
the tested main revision, restore reconciliation and activate the opt-in app:

```bash
sudo python3 deploy/console/deploy-wsl.py --resume-gitops
sudo /usr/local/bin/k3s kubectl --kubeconfig=/etc/vcloud-wsl/kubeconfig.yaml \
  --context=vcloud-wsl-local apply -f deploy/console/argocd.yaml
sudo bash lab/wsl/test-e2e.sh
sudo python3 tools/test_console_live.py
```

GitOps owns portal Deployment, Service and routes. Operator bootstrap owns its
ServiceAccount, Role/binding, policies and private Secrets. The AppProject
excludes cluster resources and Secrets/RBAC; pruning is disabled. Other
Applications retain ownership of endpoints/backends.

Live tests create disposable MFA users, exercise actual code flow, both
backends, login/logout and denied access, then remove the users. Credentials,
seeds, codes and cookies remain in process memory. Optional
`--browser 'C:/Program Files/Google/Chrome/Application/chrome.exe'` checks six
views/mobile navigation with Playwright; cookies use stdin and no HAR, trace
or storage-state files are saved. Only public screenshots are retained.

Rollback: stop portal reconciliation, remove only the four `vcloud-portal-*`
routes and scale only `vcloud-console` to zero. Restore the reviewed prior
endpoint configuration and exact previous skip-reconcile annotation. Preserve
credential Secrets and databases; do not reset Keycloak or weaken deny-all.
See [acceptance](../docs/acceptance/vcloud-console-2026-10-08.md) and
[ADR-0027](../docs/architecture/adr/ADR-0027-native-control-plane-portal.md).
