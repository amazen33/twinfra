# Twinfra control-plane portal

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
Cookie, ID/userinfo/refresh token headers are removed before upstream forwarding.
Only the gateway-issued signed access token is forwarded in `X-Access-Token`.
JavaScript receives only reduced identity metadata, never JWTs or cookies.

The BFF independently verifies each signed access token with PyJWT/cryptography.
It accepts only RS256 or ES256, requires the exact canonical issuer and console
client in `aud` or `azp`, requires `exp`, checks optional `nbf`, and allows only
30 seconds of clock leeway. Roles come from `resource_access.vcloud-console.roles`.
Invalid/missing/duplicate token headers return 401 with `{"error":"Session required"}`;
valid tokens with neither console role return 403 with `{"error":"Console role required"}`.
Old unsigned `X-ID-Token` headers provide no identity. Write methods remain 405.

JWKS is fetched only from the fixed private HTTPS Keycloak certs endpoint, with
hostname/certificate verification against `/oidc-trust/tls.crt` and no redirects.
The existing `vcloud-wsl-keycloak-tls` mount exposes only public `tls.crt`, never
the private key. The thread-safe key cache lives for five minutes. An unknown
`kid` can refetch at most once a minute across all requests; failed fetches also
consume the cooldown. A successful refresh replaces removed keys. An expired
cache or unavailable/untrusted JWKS fails closed; no stale-key fallback is used.
Token-provided key URLs are never fetched. Cilium allows only APISIX to reach
Pod port 3000 and adds only the BFF-to-Keycloak TCP 8443 TLS flow.

The client generator already maps console audience, client roles and username
into access tokens; WO-04 requires no mapper or live Keycloak change.
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

Python dependencies are pinned with official wheel hashes in
[`requirements.txt`](requirements.txt); licence sources and hashes are in
[`licence-register.json`](../security/licence-register.json). The pins are PyJWT
2.15.0 (MIT), cryptography 50.0.1 (Apache-2.0 OR BSD-3-Clause), cffi 2.0.0 (its
shipped upstream licence is MIT-0), and pycparser 3.0 (BSD-3-Clause). All bundled
wheel licence notices are retained in `/app/vendor/*dist-info/licenses/`.

WO-04 is static only: the WSL lab is being retired. Browser acceptance and the
direct-backend hand-made-header negative test are **Pending** on VM `lab-1`
after WO-21 and owner-approved redeployment. See the
[WO-04 receipt](../docs/acceptance/console-token-verification-2026-10-10.md).
The existing WSL deployment instructions below are historical; do not run them
for WO-04. WO-21 must establish the VM's reviewed issuer, CA and gateway profile.

The deterministic builder composes the vetted Python base and verified Linux
amd64 CPython 3.14 wheels without a Docker socket or privileged build Pod:

```bash
python3 -m pip download --require-hashes --only-binary=:all: \
  -r console/requirements.txt -d .build/console/wheels
python3 -m pip install --require-hashes --only-binary=:all: -r console/requirements.txt
python3 tools/build_console_image.py --base /path/to/verified-python-base.oci.tar \
  --output .build/console/vcloud-console.oci.tar --wheels .build/console/wheels
python3 tools/vcloud_console.py
python3 -m unittest discover -s tests -p test_vcloud_console.py -v
```

The static builder verifies every base blob and wheel hash; it never imports
an image unless `--import` is explicitly supplied. Both build recipes include
the same pinned runtime libraries. CI installs the candidate control checkout's
hash-locked requirements only for revisions that contain this verification lock.

Historical owned-WSL import and deployment commands:

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
The browser option also starts a separate disposable user at the portal,
changes its temporary password, enrolls TOTP and tests a returning MFA login.
It fails if either required action is skipped. The disposable browser trusts
only the public-key fingerprint of the lab certificate already verified by the
Python HTTPS client; it does not disable TLS checks globally or install OS trust.

## Login and callback recovery

Start at <http://localhost:18080/console/> in one browser. Use the **vcloud**
realm account, complete the required password change, and enter a fresh code
from its enrolled authenticator. The initial password Secret is not updated
when you choose your permanent password. Master-realm credentials are separate.
An OTP consumed during enrollment cannot be reused for a second login in the
same 30-second interval. Never paste a seed, password or callback URL into logs.

The callback requires the original encrypted `vcloud_portal` browser session.
Its idle limit is 15 minutes; this is separate from the Keycloak login session.
If that cookie is missing, expired or malformed, the callback returns a clear
HTTP 401 page with a fixed fresh-login link. The gateway discards the returned
code and does not retry automatically. Callbacks with a valid session still
pass through APISIX state, PKCE, issuer, audience, signature and role checks.
Changing cookie settings to bypass state validation is prohibited.

An opaque callback 500 previously corresponded to APISIX's missing-session
error. This establishes the failure point, but does not prove whether the
browser dropped the cookie or the login exceeded the idle limit. Start again
from the portal; do not replay a bookmarked Keycloak or callback URL. If needed,
clear only the site's cookies and reopen the portal in a private window.
Windows, WSL and Keycloak clocks must agree for TOTP validation. If a seed was
exposed, replace that OTP credential through an authorized operator procedure;
the provisioning helper never removes existing MFA or resets a working password.

The imported realm must explicitly register `UPDATE_PASSWORD` as an enabled
built-in required action. An action name on a user alone does not establish
that its provider exists. `configure_console_identity.py` repairs only that
provider and preserves users, passwords, OTP credentials and roles. It enables
password change for accounts that already require it; it is not a default
action for all users and does not re-import the realm or restart Keycloak.

Rollback: stop portal reconciliation, remove only the four `vcloud-portal-*`
routes and scale only `vcloud-console` to zero. Restore the reviewed prior
endpoint configuration and exact previous skip-reconcile annotation. Preserve
credential Secrets and databases; do not reset Keycloak or weaken deny-all.
See [acceptance](../docs/acceptance/vcloud-console-2026-10-08.md) and
[ADR-0027](../docs/adr/0027-native-control-plane-portal.md).
