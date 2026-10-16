# Twinfra v0.1.0 consolidated acceptance template — 2026-10-16

## Scope and authorization

- Environment: `twinfra-dev-cairo-1`, single-node Ubuntu 24.04 Dell.
- Scope: WO-40a acceptance candidate for dev use only; no published release.
- Owner authority: WO-40 Amendment 1, 2026-10-16.
- Tested commit / expected Application revision: Pending.
- Acceptance start/end (UTC), including the later 48-hour rc window: Pending.
- Tester/witness and agreed QoS targets: Pending.

No live check was executed by Codex for WO-40a. This is a template, not a live
pass. Existing signed receipts are referenced without changing their contents.

## Acceptance output

Owner follows the [acceptance runbook](../runbooks/release-acceptance.md), retains
the full sanitized JSON fragment under `.build/acceptance/` and attaches its
contents or a public evidence link here. Never attach private inputs or tokens.

- Read-only command / JSON fragment / SHA-256: Pending.
- Explicit `--with-restart` authorization and complete-run fragment: Pending.
- `status`: Pending (must be `passed`; `incomplete` is not sufficient).
- `node`, `podsInitial`, `podsFinal`: Pending.
- `gitops`, `gitopsFinal`, expected commit and all three Applications: Pending.
- `host-check`, `host-network`, both `staging:*`, `deployedImages`: Pending.
- `consoleHTTPS`: Pending (HTTP 200 through verified HTTPS).
- Token negatives: Pending (missing 401 / unsigned 401 / duplicate 401 / roleless 403).
- Valkey NOAUTH / authenticated PONG / three Argo clients: Pending.
- Owner restart / replacement cache / fresh reconciliations / reconnect: Pending.
- Initial/final snapshots and long-window monitoring/soak evidence: Pending.

## Actual running versions

Fill from the suite, not desired pins or optional maintenance proposals.

| Component | Running version / immutable identity |
| --- | --- |
| Kubernetes | Pending |
| containerd | Pending |
| Cilium | Pending |
| etcd | Pending |
| CoreDNS | Pending |
| Argo CD | Pending |
| CloudNativePG | Pending |
| PostgreSQL / pgvector | Pending; suite reports PostgreSQL, owner confirms the installed vector extension separately |
| Keycloak | Pending |
| OpenBao | Pending; initialization/unseal/leases are not claimed |
| Valkey | Pending |
| Console | Pending actual image digest; no embedded release-version claim |

## Individual evidence

| Work | Existing evidence | Consolidated acceptance treatment |
| --- | --- | --- |
| WO-31 | [Dell observations](dev-environment-2026-10-13.md) | Pending suite, soak and remaining witnessed gates; owner signs only proven scope |
| WO-04 | [Signed-token checks](console-token-verification-2026-10-10.md) | Pending live negatives and remaining browser cases |
| WO-06 | [LocalStack removal](localstack-removal-2026-10-10.md) | Pending current image/UI/endpoint evidence |
| WO-25 | [Valkey](valkey-2026-10-09.md) | Pending complete owner-authorized restart/reconnect run |
| WO-34 P1 | [Console rebuild evidence](wo34-p1-2026-10-14.json) | Static evidence; owner records actual staged/running digest above |
| WO-34 P2 | [CoreDNS/etcd evidence](wo34-p2-2026-10-15.json) | Static evidence; optional maintenance is not assumed applied |
| WO-34 P3 | [Image refresh evidence](wo34-p3-2026-10-14.json) | Static evidence; actual versions come from acceptance |
| WO-36 | [Accepted router/static address evidence](host-network-2026-10-15.md) | Preserve signed scope; remaining staging-failure gates are not inferred |
| WO-36a | [Accepted VM qualification and adoption evidence](host-network-fix-2026-10-15.md) | Preserve signed scope; no new Dell rollback claim |
| WO-37 | [Capability statement](../capabilities.md), [work order](../work-orders/WO-37-readme-capabilities-and-adr-status.md) | Docs/CI evidence; no separate live receipt exists or is invented |

## Exception calendar

Copy **every** row from the complete fragment's `exceptionCalendar`, not only
the warnings. Expired or <=7 days remaining fails acceptance; 8..21 days warns.
Record the warning disposition and planned remediation without extending an
approval. Any renewal follows a separate owner-approved PR.

| Image | Package / version | CVE | Expiry | Days left at run | Status / owner disposition |
| --- | --- | --- | --- | --- | --- |
| Pending full calendar from the owner run | Pending | Pending | Pending | Pending | Pending |

## Static evidence and limits

- WO-40a PR commit / CI run / candidate and all six historical results: Pending.
- Staging-check, licence, supply-chain and evidence gate results: Pending.
- No live runtime/configuration, GitHub settings, tag or release changes by Codex.
- No AWS parity, HA, backup/DR, multi-tenancy, secrets management, observability
  retention, compliance, Foundation 1.0 or production-readiness claim.
- Owner: separately sign WO-04, WO-06, WO-25 and WO-31 only after their full
  required evidence exists; the acceptance runbook identifies partial coverage.
- WO-40b, the Argo CD promotion and renewal PR remain separate release gates.

## Tester sign-off

Tester: Ahmed Mazen (@amazen33), enterprise and cloud tester; QoS tester
Result: Pending
Date (UTC):
QoS targets checked:
Notes:
