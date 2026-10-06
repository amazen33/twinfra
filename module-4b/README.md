# Module 4b: Keycloak IAM and APISIX security

Public reference configuration for Keycloak **26.8.0**, APISIX **3.19.0**, ingress
controller **2.2.0** and the existing local kubeadm Kubernetes **1.36.5** profile.
Issuer: `https://auth.vcloud.example.com/realms/vcloud`. No users, passwords, client
secrets, signing keys or tokens are shipped. Keycloak installation and API-server
changes remain owner-managed runtime prerequisites.

| Deliverable | File |
| --- | --- |
| Realm, clients, groups, mappers and scope gate | [vcloud-realm.json](keycloak/vcloud-realm.json) |
| Reusable OIDC plugin | [oidc-plugin.yaml](manifests/oidc-plugin.yaml) |
| Public Keycloak realm ingress | [identity-gateway.yaml](manifests/identity-gateway.yaml) |
| Existing function route integration | [patch](patches/gateway-route.jsonpatch.yaml), [composed route](examples/secure-function.yaml) |
| Group RBAC | [rbac.yaml](manifests/rbac.yaml) |
| API-server authentication prerequisite | [kubeadm extraArgs](kubernetes/kubeadm-oidc-args.yaml) |
| Pinned upstream inputs | [lock](artifacts.lock.json), [Apache license](../module-2/vendor/LICENSE-Apache-2.0.txt) |
| Tests and evidence | [tests](../tests/test_module4b.py), [evidence](../docs/module-4b-validation.json) |

## Identity and token contracts

```text
Browser + authorization code/PKCE -> Keycloak vcloud realm
  vcloud-api-cli -> access token: aud=vcloud-function, scope=function.read
    -> APISIX openid-connect -> HTTPS Kourier -> protected function
  vcloud-kubernetes -> ID token: aud=vcloud-kubernetes, groups=[/vcloud/...]
    -> kube-apiserver OIDC -> keycloak:/vcloud/... -> Kubernetes RBAC
```

| Client | Flow and token use | Exact callback |
| --- | --- | --- |
| `vcloud-function` | Bearer-only resource identifier; grants disabled | None |
| `vcloud-api-cli` | Public code + PKCE S256; API access token | `http://127.0.0.1:18000/callback` |
| `vcloud-kubernetes` | Public code + PKCE S256; Kubernetes ID token | `http://localhost:8000`, `http://localhost:18000` |

HTTP callbacks apply only to local loopback listeners. Issuer/token endpoints,
public gateway and backends use verified HTTPS. Accept the actual CLI listener and
PKCE behavior before use; an API CLI implementation is not supplied here. A reviewed
[kubelogin client](https://github.com/int128/kubelogin/blob/master/docs/setup.md)
can use the Kubernetes public client. Pin/mirror its executable through the toolchain
owner and use an OS credential store or memory cache. Do not store tokens in a disk
cache, kubeconfig, source, environment variables or logs.

Password/implicit/service-account grants, wildcard redirects and full-scope inheritance
are disabled. Interactive clients use five-minute tokens, refresh rotation, bounded
sessions and brute-force protection. New users must enroll TOTP; existing users need
an explicit enrollment rollout. Accept that the browser flow requires configured OTP
on later logins. No default human group or administrator grant is created.

Only `/vcloud/api-users` receives role `vcloud-function-reader`. The `function.read`
client scope has that role scope mapping: users without the role do not receive the
scope or its audience mapper. APISIX requires the scope, intended issuer/audience,
RS256 signature and valid lifetime. Evaluate both allowed and denied users against
the real import; local tests inspect configuration rather than issuing signed tokens.

`kubernetes-groups` emits full paths in **ID tokens**, avoiding leaf-name collisions,
and is linked only to the Kubernetes client. API audience mapping applies only to
API **access tokens**. Do not reuse tokens across these clients.

## Keycloak setup

Use its reviewed non-root deployment owner in `platform-services`, with a dedicated
`keycloak` PostgreSQL database and restricted migration-capable role. Module 4a's
application read-only lease is unsuitable for Keycloak's database. Deliver TLS keys
and database credentials through the accepted OpenBao workflow with verified CNPG
TLS and no credential environment variables or persistent plaintext. Match the
existing `app.kubernetes.io/name: keycloak` network selector and the reference
Service contract `keycloak:443 -> HTTPS 8443`.

Set the fixed hostname `https://auth.vcloud.example.com`, strict hostname handling,
HTTPS and disabled HTTP. Accept `xforwarded` proxy headers only from reviewed APISIX
addresses. The route overwrites forwarded host/protocol/port/client address and removes
`Forwarded`. Preserve Module 2's upstream CA verification; the backend certificate must
include `auth.vcloud.example.com`. Provision `Secret/keycloak-gateway-tls` in
`platform-services` through the secret owner. Keep admin/master/management endpoints private.

Mount the public reference as `/opt/keycloak/data/import/vcloud-realm.json` using the
existing deployment's ConfigMap volume, then use supported `start --import-realm` for
a **new** realm. JSON is an import reference, not a Kubernetes CRD. Existing-realm startup
import is skipped. Reconcile later changes through reviewed private administration
with backup, preserving users/state; do not delete/recreate an existing realm.

Provision users privately, enroll MFA and assign reviewed groups. No administrator or
user credential is included. Admin events are enabled with representation details
disabled; verify logs exclude authorization headers and token/credential responses.

The public HTTPS route permits `/realms/vcloud/*` and `/resources/*`, without a bearer
plugin: discovery/browser login must work before obtaining tokens. Existing Cilium
policy admits APISIX-to-Keycloak TLS. The Keycloak owner still needs narrow DB/DNS and
accepted HA/cache connectivity. API servers/operators need trusted DNS, CA and egress
to issuer/JWKS; put the actual identity VIP in the reviewed site CIDRs.

## APISIX integration

The supported kind is **`ApisixPluginConfig`**, API `apisix.apache.org/v2`; this
controller has no `APISIXPlugin` kind. The route references it using
**`plugin_config_name`**, in `platform-services` here.

The pinned APISIX 3.19.0 [implementation](https://github.com/apache/apisix/blob/3.19.0/apisix/plugins/openid-connect.lua)
permits no `client_secret` for `bearer_only: true` with `use_jwks: true`. This uses
local JWT verification; login callbacks/introspection would need their own secret and
session design. Generic documentation may describe the secret as always required.

The plugin checks issuer/audience, RS256, lifetime, scope and IdP TLS. It forwards a
signed access token in Authorization; the route removes client-supplied unsigned
identity/token headers. Applications must also validate the signed token and enforce
their own tenant/resource permissions.

Fold the [patch](patches/gateway-route.jsonpatch.yaml) into Module 2's existing
**chart-owned source**. It preserves HTTPS matching, Host rewrite and Kourier backend,
removes duplicate inline OIDC and attaches the reusable config. The composed route is
an integration example, not a second Argo owner. Manual patches would be overwritten
by reconciliation. Admit the plugin before switching the owned route.

Module 2 still declares its earlier OIDC environment reference. When accepting this
replacement, its owner should remove that unused entry/Nginx export, retain the
independent Admin API credentials, and run guard/Helm checks for the reviewed updated
profile. This module does not silently alter its frozen default or node approval.

## Kubernetes mapping

Bindings grant access only after the API server authenticates a user. Merge the OIDC
fragment into **every local kubeadm API server's** `apiServer.extraArgs` list. Preserve
service-account issuer and other authentication. Username claim is stable `sub`;
username/group prefixes are `keycloak:`. The public CA must be readable at
`/etc/kubernetes/pki/keycloak-ca.crt` inside the existing approved PKI mount.

This fragment is not kubectl-applicable. No extra host mount or automated restart is
introduced. Render/audit resulting static Pods under the existing node contract and
use a controlled rollout with an independent recovery identity. Do not combine these
OIDC flags with `--authentication-config`. Managed EKS/GKE/AKS requires its provider's
supported human federation mechanism; kubeadm flags do not configure those control planes.

| Keycloak path | Kubernetes group | Binding and access |
| --- | --- | --- |
| `/vcloud/cluster-observers` | `keycloak:/vcloud/cluster-observers` | ClusterRoleBinding: read nodes/namespaces |
| `/vcloud/workload-readers` | `keycloak:/vcloud/workload-readers` | RoleBinding in workload-apps: read Pods/services/events, apps controllers and batch jobs |
| `/vcloud/hpc-readers` | `keycloak:/vcloud/hpc-readers` | Same read access in hpc-compute |
| `/vcloud/api-users` | No Kubernetes binding | API scope only |

No Secret/log/exec reads, writes, bind/escalate/impersonation or cluster-admin grants
are included. Namespace RoleBindings reuse a ClusterRole without widening their
namespace scope. Human memberships remain separate from workload service accounts,
OpenBao policies and cloud/Spinifex authority.

## Checks and live acceptance

```bash
make module4b-validate module4b-test
kubectl --context vcloud-prod-01 apply --dry-run=server -f module-4b/manifests
```

The first command uses locked local schemas and security tests. The second requires
accepted controllers and was not executed. Realm JSON and API-server args are checked
as reference configuration, not presented as kubeconform-validated CRDs.

| Real probe | Required outcome |
| --- | --- |
| Code/S256 login, enrolled MFA and refresh rotation | Success; no password/implicit fallback |
| Missing/expired/wrong-issuer/wrong-audience/unsigned API token | Denied; no upstream execution |
| API token from api-users / user outside that group | `/function` succeeds / denied without authorized scope/audience |
| Discovery/login/token/JWKS and admin/master paths | Verified HTTPS public realm works; admin/master absent from delivered route |
| Unavailable issuer/JWKS or invalid CA | Fail closed when discovery/keys are unavailable; accept bounded cache behavior |
| Real OIDC context: `kubectl auth whoami` | `keycloak:<sub>` and expected full-path groups |
| Workload reader: `kubectl auth can-i get pods -n workload-apps` | yes |
| Same reader: Secrets, exec, writes or other namespaces | no unless independently granted |
| Cluster observer: nodes / Secrets or RBAC mutation | yes / no |

Use actual OIDC user contexts, without `--as`; impersonation alone does not verify
login/claims. Check that existing bindings do not widen users' rights. Group removal
does not instantly invalidate issued JWTs: accept the five-minute token/cache window
and incident revocation procedure. No live realm import, login, JWT verification,
gateway routing or API-server/RBAC acceptance ran in this Windows workspace.

Primary references: [release](https://www.keycloak.org/2026/10/keycloak-2680-released),
[Keycloak scopes/groups](https://www.keycloak.org/docs/latest/server_admin/),
[import behavior](https://www.keycloak.org/server/importExport),
[APISIX OIDC](https://apisix.apache.org/docs/apisix/plugins/openid-connect/),
[controller CRD](https://github.com/apache/apisix-ingress-controller/blob/2.2.0/config/crd/bases/apisix.apache.org_apisixpluginconfigs.yaml),
[Kubernetes authentication](https://kubernetes.io/docs/reference/access-authn-authz/authentication/).
