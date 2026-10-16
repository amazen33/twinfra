# v0.1.0 dev acceptance (WO-40a)

This is an owner-run procedure for `twinfra-dev-cairo-1` only. Implementation
and offline fixtures do not constitute live acceptance. No tag, release,
provisioning action or settings change is performed by this work order.
WO-40b supplies final release documents and `release/**` workflow coverage later.

## Prerequisites

Use the [cairo-1 runbook](../dev-environment.md) for the existing key-only SSH
access, kubeconfig and loopback tunnels. Check out the exact candidate revision.
The three Applications must report that same immutable 40-character commit.
Do not point this command at production or another environment.

- Existing tools: Python with this repository's admitted Python dependencies,
  kubectl and OpenSSH; no installation or new image is needed.
- The public dev CA certificate, and the existing HTTPS tunnel on port 18444.
  `console.dev.cairo-1.twinfra.example.com` must resolve only to loopback on
  the laptop. Certificate and hostname verification are mandatory; no `-k`.
- An owner-only file **outside every Git checkout**, containing just
  `twinfra_portal=<current cookie>` from the owner's authenticated console
  session. It is not a password and must not be pasted into chat or commands.
- A separate owner-only file outside Git containing a current, signed access
  token for an existing Keycloak `twinfra` user with neither console role.
  The token must otherwise have the correct issuer/audience and be unexpired;
  an invalid token returning 401 does not satisfy the required roleless 403.
  Obtain it using the existing approved OIDC flow; the suite creates no users,
  credentials, grants or sessions. Never enable password grants for this test.
- Private files require owner-only ACLs on Windows, or owner ownership and
  mode 0600 on Linux. Keep these short-lived values out of environment variables,
  shell history, logs and receipts; remove them when the owner finishes.
- Current, owned host-network files. The suite refuses metadata adoption; run
  any separately authorized remediation outside acceptance first.

## Run and inspect

Replace the public paths and commit below; never put token/cookie contents in
the command. The command prints one sanitized JSON object and writes a new
fragment under `.build/acceptance/` (or `--receipt .build/acceptance/<new>.json`).

```bash
python tools/platform_dev.py accept --context twinfra-dev-cairo-1 \
  --expected-revision <40-character-candidate-commit> \
  --ca-file /owner/public/dev-ca.crt \
  --session-file /owner/private/console-cookie \
  --roleless-token-file /owner/private/roleless-access-token
```

Default execution makes no host or cluster configuration changes. It executes
bounded read commands in existing containers and performs HTTP GETs; tokens
travel on stdin and are never placed in exec arguments or logged. Fragment
files are local output, never signed receipts. Existing fragments are not
overwritten. Exit codes: **0** all checks passed, **1** failed/unavailable,
**2** incomplete because the explicitly gated Valkey restart was not run.

For the complete Valkey acceptance, the owner explicitly adds `--with-restart`
to the same command. Only after all preceding checks pass does this delete
**one `argocd-redis` cache Pod**. It makes no Deployment/StatefulSet/configuration
patch. The cache is non-durable; application database Pods are never restarted.
The bounded wait (`--timeout`, default 300 seconds, maximum 900) requires a new
Ready cache Pod, authenticated PONG, NOAUTH without authentication, all three
Argo components Ready and connected in Valkey CLIENT LIST, and fresh
reconciliations of all three Applications at the expected commit. A failure
reports failed acceptance; it does not attempt a rollout or automatic repair.

`--since <UTC ISO timestamp>` extends the restart check back to an acceptance
window start. The normal run also compares the initial/final Pod UID and all
container restart counters, and rejects surviving Pods created/replaced since
the window start (apart from the one explicitly authorized cache replacement). All namespaces are inspected. Non-Running Pods,
including completed Jobs, fail the literal WO-40 requirement; the suite never
deletes them or silently omits a namespace. Resolve their disposition separately.
Historical Pod events that are no longer present cannot be reconstructed by
this command; keep the start/end fragments and owner monitoring evidence for
the 48-hour release window. It does not replace the existing soak verdict.

## Checks and JSON contract

| Check | Required result |
| --- | --- |
| `node` | Single approved node Ready, InternalIP `.3`, dev/cairo-1 labels and zone `cairo-1a` |
| `podsInitial`, `podsFinal` | Every Pod Running; no unexpected UID/restart-count changes or surviving restart since the window start |
| `gitops`, `gitopsFinal` | `twinfra-root`, `twinfra-platform`, `twinfra-services` all Synced/Healthy at the expected commit |
| `host-check`, `host-network` | Existing read-only host checks pass; network adoption is prohibited in acceptance |
| `staging:*`, `deployedImages`, `deployedImagesFinal` | Both locks pass the existing `stage-images --check` agent; every container/init/ephemeral reference is locked and its running image ID binds to that staged manifest/CRI ID |
| `consoleHTTPS` | Authenticated GET of the existing `/console/api/identity` through trusted HTTPS/APISIX returns 200 for dev |
| `tokenNegatives` | Inside the existing BFF container: missing, unsigned and duplicate `X-Access-Token` headers return 401; a valid roleless token returns 403 |
| `valkey`, `valkeyRestart` | NOAUTH, authenticated PONG, all three Argo client connections; explicit owner restart proves reconnection and fresh application reconciliation |
| `exceptionCalendar` | Every registered exception printed; expired or **<=7 days** fails, **8..21 days** warns, >21 days passes |

The gateway scrubs client identity headers and redirects unauthenticated browser
requests. Therefore token negatives exercise the BFF's actual loopback listener
via `kubectl exec`, not an OIDC redirect mistaken for a 401. No public BFF ingress
or Cilium exception is added. [Valkey's pinned CLI](https://github.com/valkey-io/valkey/blob/8.1.10/src/valkey-cli.c)
supports `--askpass`; its non-TTY input reads the existing mounted secret without
placing it on argv. [CNPG's pinned version subcommand](https://github.com/cloudnative-pg/cloudnative-pg/blob/v1.30.1/internal/cmd/versions/cmd.go)
is `/manager version`.

JSON contains UTC start/end, environment, expected revision, per-check status
and sanitized evidence, a version report for Kubernetes, containerd, Cilium,
etcd, CoreDNS, Argo CD, CNPG, PostgreSQL, Keycloak, OpenBao, Valkey and console,
plus every exception's image/package/CVE/expiry/days-left. Console identity is
its actual digest; no embedded release version is invented. A raw CRI config
digest is compared to `crictl inspecti` for the exact pinned manifest, not to an
unrelated OCI index. Tokens, cookie values and subprocess errors are omitted.
`testerSignOff` always remains `Pending`.

## Owner evidence and remaining release work

Attach sanitized output to the [consolidated template](../acceptance/release-0.1.0-2026-10-16.md).
Only the tester signs. The suite supplies evidence toward these existing
receipts; it does not edit or automatically accept them:

- [WO-04](../acceptance/console-token-verification-2026-10-10.md): the four live
  token-negative checks. Its browser login/logout and emulator views still need
  the owner's live witness before accepting the entire receipt.
- [WO-06](../acceptance/localstack-removal-2026-10-10.md): locked deployed-image
  evidence can show absence of LocalStack; complete any remaining UI/endpoint
  checks in that receipt before signing.
- [WO-25](../acceptance/valkey-2026-10-09.md): NOAUTH, authenticated PING and all
  three clients before/after the explicit cache restart, plus fresh healthy sync.
- [WO-31](../acceptance/dev-environment-2026-10-13.md): node/host/network, versions,
  images and GitOps evidence. The separately witnessed soak/storage/firewall
  gates must also be resolved; a short run does not establish 24 hours of uptime.

Preserve the already signed WO-36/36a receipts. WO-08, draft WO-09 #65 and other
roadmap work remain paused. No Foundation 1.0, backup/DR, AWS parity or production
readiness is established here. Follow WO-40 Amendment 1 for Argo CD promotion,
renewal, WO-40b and the owner-run release cut. Nothing in this PR tags/releases
or enables `release/**` workflow coverage early.
