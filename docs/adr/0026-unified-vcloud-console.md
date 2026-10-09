# ADR-0026: Unified vCloud console with gated identity and permissive views

**Status:** Accepted (lab) — [vcloud-console-wsl-2026-10-07.md](../acceptance/vcloud-console-wsl-2026-10-07.md); backend/reference staging only; public reference OIDC remains gated. Partly superseded by [ADR-0035](0035-console-self-service.md) for the read-only decision only; identity, cookie and isolation decisions remain in force.
**Date:** 2026-10-07
**Deciders:** vCloud platform owner and platform engineering

## Context

The 20GB/6-vCPU WSL lab has APISIX, its official ingress controller and a
restricted LocalStack Community 4.14.0 API emulator. The operator requests a
single `console.vcloud.local:18080` interface with both MiniStack and LocalStack,
permissive navigation/storage/DynamoDB UIs and Keycloak authentication. The
operator selected a gated `vcloud-console` OIDC client/Secret reference.

The pinned ApisixRoute API cannot reference Services across namespaces, and
ExternalName Services produced empty upstream nodes in the previous repair.
Spinifex is not deployed and offloading stays disabled. Local OpenBao is sealed
and TLS-enabled in platform-services; the requested platform-system aliases do
not exist. Bare prefix rewriting does not repair absolute UI assets/callbacks.

## Decision

Use same-namespace ApisixRoutes on the existing controller-managed gateway. Put
original MIT vCloud navigation at `/`, lightweight read-only MIT S3/DynamoDB
views at `/storage/` and `/dynamodb/`, and distinct immutable MiniStack and
Community LocalStack API endpoints at their named prefixes. A ClusterIP alias
selects the existing LocalStack Pod. Keep requested Spinifex/OpenBao route
addresses in a separately excluded disabled reference file.

Use confidential OIDC code flow with PKCE, verified TLS, exact issuer/audience
and callback. Obtain client/session secrets through the controller's Kubernetes
`secretRef` mechanism; do not commit values. Validate Secret shape and ready
backends before creating the opt-in Argo Application. Discovery, issuer DNS,
gateway CA trust and browser positive/negative authentication remain operator
acceptance gates. Missing credentials must not reach the shared ADC snapshot.

Use native APISIX WebSocket handling, anchored prefix stripping, explicit
forwarded-prefix/host/scheme headers and fixed-origin credentialed CORS.
Set SAMEORIGIN framing without deleting upstream CSP. Original views support
the known public prefixes and escape displayed backend data. They sign AWS
requests directly to fixed in-cluster emulator endpoints; generic SigV4
prefix compatibility is not assumed. No GPU, Docker socket or host mount is added.

## Options considered

| Option | Assessment |
|---|---|
| Replace gateway with a standalone route file | Conflicts with ingress-controller/ADC ownership; rejected |
| Blind prefix proxy of every third-party UI | Breaks absolute assets/redirects, assumes undeployed services and misstates licenses; rejected |
| Original MIT navigation and bounded read-only views, gated backend references | Small CPU footprint, clear license and authentication boundary; selected |

## Consequences and acceptance

The shell/views are permissive; proxied projects retain their own licenses.
Spinifex Core/MinIO Console AGPL and OpenBao MPL are documented accurately.
The shell links to services rather than automatically framing privileged
management UIs. It provides read-only discovery, not an AWS management console
or database mutation interface. Ephemeral emulator state is suitable for local
validation only. HTTP session cookies are limited to the loopback lab; HTTPS
and Secure cookies are required for a separately designed production profile.

Static schema, restricted PSS, immutable-cache image policy, URL boundaries,
Secret gate and UI escaping tests are mandatory. Live staging/negative access,
both emulator reads, browser login, logout and socket/backend base-path tests
are reported individually; static success is not live identity acceptance.

See [console runbook](../../lab/wsl/console/README.md) for activation and
rollback, [APISIX OIDC source](https://github.com/apache/apisix/blob/3.19.0/apisix/plugins/openid-connect.lua),
and [controller Secret translation](https://github.com/apache/apisix-ingress-controller/blob/2.2.0/internal/adc/translator/apisixroute.go).
