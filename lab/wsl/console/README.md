# Unified Twinfra local console

Opt-in, CPU-only WSL profile for `http://console.vcloud.local:18080` on the
existing APISIX 3.19.0 / ingress-controller 2.2.0 gateway. Twinfra is the only
platform identity. This directory's original navigation and browser code is MIT.
It does not change the licenses of the proxied applications or dependencies.

The Keycloak **gated reference** was selected by the operator. The console
Application is not included in the existing endpoint Application. Backends may be
staged independently; public console routes must wait for OIDC credentials and
issuer acceptance. Existing AWS and Knative hosts remain owned by their current
Application. Never overwrite APISIX's controller-managed full configuration with
an out-of-band Admin API route snapshot or mount this file as `apisix.yaml`.

## Files and route map

`apisix-routes.yaml` contains the five active-profile Kubernetes `ApisixRoute`
definitions. They are **activation-gated**, not anonymous routes. The separate
`reference/apisix-routes-disabled.yaml` contains the two disabled target
references and must not be applied. Each route lives beside its actual Service;
the frozen CRD prohibits cross-namespace Service backends. The IngressClass
`vcloud-local` points to the existing platform-services GatewayProxy.

| Public path | Service DNS and port | Local behavior |
|---|---|---|
| `/`, `/console.css`, `/oidc/callback` | `vcloud-console-shell.platform-services.svc.cluster.local:3000` | MIT Twinfra navigation; OIDC callback handled by APISIX |
| `/ministack`, `/ministack/*` | `ministack.platform-services.svc.cluster.local:4566` | MiniStack 1.5.22 APIs and `/_ministack/health` |
| `/localstack`, `/localstack/*` | `localstack.platform-services.svc.cluster.local:4566` | Community 4.14.0 APIs and `/_localstack/health` |
| `/storage`, `/storage/*` | `storage-ui.platform-services.svc.cluster.local:9001` | MIT Twinfra read-only bucket/object-key browser |
| `/dynamodb`, `/dynamodb/*` | `dynamodb-admin.platform-services.svc.cluster.local:8081` | MIT Twinfra read-only table list/metadata viewer |
| `/spinifex`, `/spinifex/*` | `spinifex-console.platform-system.svc.cluster.local:3000` | Disabled reference; no console deployed, offloading stays false |
| `/vault`, `/vault/*` | `openbao-ui.platform-system.svc.cluster.local:8200` | Disabled reference; this Service is not the existing local OpenBao |

`localstack` is a real ClusterIP Service selecting the existing
`localstack-aws-console` Pod, not a second emulator. MiniStack has its own
Deployment and distinct ephemeral state. No Docker socket, privileged Pod,
hostPath, GPU allocation, real AWS credentials or external infrastructure launches
are added. Resource requests are 125m CPU / 224Mi for the four new Pods;
limits are 1.75 CPU / 896Mi in total, within the 20GB/6-vCPU lab budget.

The two AWS gateways return JSON/XML APIs; they are not AWS web consoles.
The original Twinfra storage/DynamoDB views select `?backend=ministack` or
`?backend=localstack`, list at most 100 resources and display table metadata only.
They cannot upload/delete objects, mutate tables, scan rows or launch instances.
Emulator credentials `test/test` are public test fixtures held in-process;
the SDK-equivalent SigV4 signer uses only the two fixed internal endpoints.
Responses are limited to 1MiB and four seconds; redirects to other endpoints are
refused, and displayed data is HTML escaped. Backend errors return HTTP 503.

## Rewriting, WebSockets and embedding

Each prefix rule matches both the bare prefix and `/<prefix>/*`. Anchored
`^/<prefix>(?:/(.*))?$` -> `/$1` rewrites strip only that prefix. Query strings
are preserved by APISIX. Thus `/dynamodb/table/users` forwards `/table/users`;
the lightweight viewer serves `/` and intentionally returns 404 for unsupported
operations. Its links explicitly include `/dynamodb/` or `/storage/` and its
stylesheet uses the shared `/console.css`, so it works after prefix stripping.

`websocket: true` uses APISIX's native Upgrade/Connection handling on Spinifex,
OpenBao and DynamoDB routes. Do not force `Connection: upgrade` on ordinary
requests. The shipped read-only DynamoDB view has no live socket feed; the route
is ready for a separately tested socket-capable replacement. Its schema/headers
are tested; a live socket backend handshake is a separate acceptance gate.

`response-rewrite` sets `X-Frame-Options: SAMEORIGIN` and fixed
`Access-Control-Allow-Origin: http://console.vcloud.local:18080`, with credentials
allowed. The `cors` plugin handles preflight for that exact origin, including AWS
headers; it does not use `*` with cookies. Existing upstream CSP is not removed.
Our UIs set `frame-ancestors 'self'`; optional framing can embed these same-origin
views. The delivered shell uses ordinary links and has no external CDN/fonts or
JavaScript, browser token storage, automatic credential injection or iframes.
An upstream CSP that forbids framing still needs upstream configuration.

**AWS signing:** arbitrary SigV4 clients signing a prefixed URL may fail when a
strict verifier sees the stripped path. OIDC Bearer and AWS Authorization also
share the Authorization header. Use browser OIDC session cookies for the prefixed
API routes; OIDC emits `X-Access-Token` and `X-ID-Token` without replacing AWS
Authorization. Our read-only views sign the direct internal path, avoiding that
conflict. For general CLI/SDK validation use the original direct emulator
endpoints (LocalStack host loopback 4566, MiniStack an explicit operator
port-forward). Do not claim prefixed API routes are a universal SigV4 endpoint.

## OIDC activation gate

1. In the existing `vcloud` Keycloak realm, create/update only the client described
   by `keycloak-client.json`. Do not re-import/reset the realm or create default
   users. Register the exact callback and origin, confidential code flow, PKCE
   S256 and the console audience mapper. The reference uses
   `https://auth.vcloud.example.com/realms/vcloud` with TLS verification.
   The current lab Keycloak hostname is `https://localhost:18443`; that is not
   this reference issuer. Fix discovery, browser/node DNS and certificate trust
   through a separately reviewed identity configuration before activation.
2. The operator's credential manager must supply encrypted-at-rest Kubernetes
   Secret `platform-services/vcloud-console-oidc`, with **only** keys
   `client_secret` (at least 16 characters) and `session.secret` (at least 32).
   Controller 2.2.0 expands dotted keys into nested plugin config. No Secret
   values or dummy passwords are shipped. Never put values in Git, shell argv,
   environment variables, host plaintext files or logs. No automatic client
   credential generation or OpenBao initialization/unseal is performed here.
3. Mount the issuer's **public** CA chain into APISIX and configure its
   `apisix.ssl.ssl_trusted_certificate` (rendered as `lua_ssl_trusted_certificate`),
   permit APISIX-to-Keycloak TLS ingress on 8443 and validate discovery from that
   Pod. The delivered additive policy supplies gateway egress to Keycloak only;
   identity-owner ingress/trust/DNS settings are not guessed. Verify exact issuer,
   authorization/token/JWKS endpoints, valid audience, rejected invalid tokens,
   exact redirect and logout, then attest `VCLOUD_CONSOLE_ISSUER_VERIFIED=true`.
   This is a nonsecret operator gate, not an automated claim of those tests.

APISIX OIDC validates TLS, issuer, audience and RS256.
The requested scope is `openid`: the actual local discovery document does not
advertise a `profile` client scope, and the read-only console needs no profile data.
Spoofed identity headers are removed before OIDC runs; proxy-rewrite then
preserves headers generated by successful authentication. Browser session cookies
are HttpOnly, SameSite=Lax, scoped to `/`. `cookie_secure: false` is solely for the
requested HTTP loopback lab origin. An HTTPS deployment must change origin,
callback, forwarded scheme and enable Secure cookies; do not reuse this profile
for staging/production or expose it on a public listener.

Missing credentials prevent route creation: the controller does not fail closed
by itself on missing plugin Secrets and may push incomplete configuration to the
shared ADC gateway. `apply.sh` calls `wsl_console_preflight.py` before creating
the Application, validating Secret encoding/shape, PodSecurity labels and ready
Service endpoints. Public console activation remains gated until all inputs
are supplied. Network policies allow only APISIX ingress to the new backends
and UI egress to the two emulators, preserving the existing deny-all baseline.

## Execute on the owned WSL lab

From `/mnt/e/vCloud` as the node operator, after publishing tested main:

```bash
# Connected staging is explicit; runtime image resolution stays mirror-only.
python3 tools/wsl_console.py --stage
bash lab/wsl/console/deploy-backends.sh

# Read-only backend integration checks inside the restricted UI Pod.
kubectl -n platform-services exec -i deployment/storage-ui -- \
  python - < lab/wsl/console/test-backends.py
python3 lab/wsl/console/test-denied.py

# After completing and recording the identity gate above:
VCLOUD_CONSOLE_ISSUER_VERIFIED=true bash lab/wsl/console/apply.sh
bash lab/wsl/console/verify.sh
```

Argo CD already has bounded platform-services ConfigMap/Deployment/Service/
ApisixRoute writes. `reference/argocd.yaml` grants the new project only these
namespaced kinds; no Secrets, Nodes, CRDs, RBAC or platform-system writes are
added. The project reconciles `lab/wsl/console/gitops` from `amazen33/twinfra` main;
bootstrap owns the additive Cilium policies. Never activate against an unpublished
revision. Verify the new Application Synced/Healthy and existing two Applications
remain Synced/Healthy after activation. Preserve the current gateway admin TLS
and controller credential configuration.

For hostname-independent testing:

```bash
curl --resolve console.vcloud.local:18080:127.0.0.1 \
  -I http://console.vcloud.local:18080/storage/
```

Unauthenticated requests must redirect HTTP 302 to the verified Keycloak issuer
or return 401. After login, root, both browser views and both health paths must
return their expected content with HTTP 200. Then test denied/expired sessions,
refresh and logout. `verify.sh` is the anonymous negative-auth gate only; it does
not simulate a successful user login. It does not log cookies or callback codes.

To use the exact URL in a browser, an administrator may add a single
`127.0.0.1 console.vcloud.local` entry to the Windows hosts file and the WSL hosts
file. `.local` may use mDNS; verify resolution on each side. No hosts or firewall
files are changed by these scripts, and no public exposure is configured.

## Disabled integrations and rollback

Spinifex Core is [AGPL-3.0](https://github.com/mulgadc/spinifex/blob/main/LICENSE),
not MIT/Apache-2.0. A console service/image, version/license inventory, API/OIDC
integration and supported asset base path must be provided/tested first. Existing
`SPINIFEX_OFFLOAD_ENABLED=false`, zero GPU quota and GPU/vLLM disablement remain.

OpenBao is [MPL-2.0](https://github.com/openbao/openbao/blob/v2.7.1/LICENSE), a
file-level copyleft license. The actual local deployment is TLS-enabled in
`platform-services`, uninitialized/sealed behind the PGP gate, not an HTTP
`openbao-ui` in `platform-system`. Native UI assets `/ui/` and API paths `/v1/`
are not fixed by prefix stripping alone. Use a verified dedicated integration
with explicit native-path routing/TLS upstream trust or a supported upstream
base-path setting before enabling `/vault/`; never forward credentials to an
unverified HTTP alias. The disabled YAML records the requested address only.

MiniStack [MIT source](https://github.com/ministackorg/ministack/tree/v1.5.22)
and LocalStack [Community 4.14.0 Apache-2.0 source](https://github.com/localstack/localstack/blob/v4.14.0/LICENSE.txt)
are API emulators. LocalStack's separately hosted Web Console is not included.
MinIO Console is [AGPL-3.0](https://github.com/minio/console/blob/master/LICENSE);
it was not selected for the requested permissive UI scope. Other backend/core
licenses do not become MIT merely by appearing behind this navigation shell.

Rollback: stop automated reconciliation for the **new** console Application,
remove only the five `vcloud-console-*` active ApisixRoutes, then remove that
Application/project and the new Deployments/Services/ConfigMap/policies if no
longer needed. Never delete the existing LocalStack Pod, shared APISIX gateway,
Keycloak realm, CNPG data or OpenBao secrets. Inspect named objects before removal;
avoid `kubectl delete -f` across the whole generated workload file because it
includes the LocalStack alias and controller-managed declarations.
