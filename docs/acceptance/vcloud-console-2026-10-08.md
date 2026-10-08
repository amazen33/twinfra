# Native vCloud portal acceptance — 2026-10-08

Scope: owned mirrored WSL2 `vcloud-wsl-local`, 20 GiB RAM/six vCPUs, existing
APISIX ingress and Keycloak 26.8.0, restricted:v1.30 namespace admission.
This is local implementation/acceptance, not a production release.

## Implemented behavior

React/TypeScript + Tailwind shell and read-only Python BFF run as
`platform-services/vcloud-console`. APISIX routes the six native views at
<http://localhost:18080/console/>. Both LocalStack Community 4.14.0 and MiniStack
are selectable. Argo Application status and namespace health use a get/list-only
Role, projected short-lived token and verified Kubernetes TLS. No Secrets,
cluster resources or write/exec permissions are exposed.

The approved `vcloud/vcloud-admin` account receives only the client role
`console.admin`; its independent temporary password resides in encrypted Secret
`vcloud-wsl-console-admin`. Password change/MFA are required at first login.
The operator credential was not consumed by acceptance. The master account and
password remain separate. Client/session credentials reside in the owned
`vcloud-console-oidc` Secret, without committed values.

Keycloak's browser issuer remains `https://localhost:18443/realms/vcloud`;
its private dynamic TLS backchannel supports gateway discovery/code exchange.
An initial login HTTP 500 exposed a CA configuration error: placing
`lua_ssl_trusted_certificate` under arbitrary `nginx_config.http` did not render
the directive. The corrected `apisix.ssl.ssl_trusted_certificate` mounts only
the public certificate; actual verified-TLS code exchange then passed.

## Executed acceptance

`tools/test_console_live.py` creates and removes disposable realm users, performs
real confidential code flow with PKCE and mandatory TOTP enrollment, and keeps
all passwords, MFA seeds, codes, cookies and tokens in memory. Browser cookie
transfer uses process stdin; no storage-state, HAR or trace file is produced.

| Check | Observed outcome |
| --- | --- |
| Portal Deployment | Ready; restricted non-root, no escalation, dropped ALL capabilities, RuntimeDefault seccomp, read-only root filesystem |
| Anonymous API | HTTP 401 |
| Forged gateway identity headers | HTTP 401; client headers cannot establish identity |
| Authenticated API writes | HTTP 405; rejected bodies close their connection |
| Real OIDC code/PKCE and MFA | Login callback returned portal HTML HTTP 200 |
| API identity/overview/GitOps | Each HTTP 200 with reduced read-only output |
| Storage/DynamoDB/EC2, both emulators | Six API checks HTTP 200 |
| Original proxy views | Storage/DynamoDB HTTP 200; exact prefix assets and SAMEORIGIN/CSP retained |
| Browser | Real Windows Chrome navigated/reloaded all six views; mobile menu and horizontal-overflow checks passed |
| Logout | Next API request HTTP 401 |
| Authenticated roleless user | Gateway HTTP 401; portal denied (BFF role rejection separately HTTP 403 in unit tests) |
| Private acceptance cleanup | Both disposable users removed; operator temporary password preserved |
| Frontend | Five interaction tests passed; TypeScript/Vite build passed |
| Production dependency audit | Zero reported vulnerabilities |
| Backend/security | 17 unit tests passed |
| CI control regression | 31 tests passed |
| Full offline CI | 66 gates, 525 tests passed; ShellCheck and pinned Helm lint/render included |
| Strict kubeconform | 20 portal resources plus two Argo resources valid; zero invalid/errors/skips |
| Portal restricted policy | 63 conftest assertions passed; zero warnings/failures |
| Node Docker build base | Exact Node 24.15.0-alpine3.23 tag resolved with Linux/amd64 support |

Public desktop/mobile screenshots are in
`.build/console/screenshots/overview-desktop.png` and `overview-mobile.png`.
They were visually inspected. A transient diagnostic scaler Pod can make the
live ready count change; the UI displays measured status rather than a fixed
success indicator. No screenshot contains a password, token or MFA setup page.

The rejected-write acceptance exposed an unread-body keep-alive issue. Closing
those connections, rebuilding/importing the pinned image and repeating the
browser/API suite passed under concurrent full-CI load.

Full offline CI and post-publication reconciliation are recorded in the final
delivery evidence. Initial local CI reached HPC checks but failed on a CRLF
character in an ignored runner's report path; the runner was corrected to LF
and the full suite rerun. This was a harness path error, not a passing gate.
An intermediate run also caught a documentation link while its target was
being created; the completed tree passed that gate on rerun.
GitHub runs candidate and immutable historical PRs #1–#6 independently.

## Limits and operating procedure

The runtime image is locally built/imported and digest pinned in
`console/image.lock.json`; the placeholder registry has not received an image
push. Dockerfile execution is not asserted by OCI-builder deployment. Full
Keycloak/Argo administration retains separate endpoints. Native views avoid
iframes while retaining CSP/XFO; there is no real WebSocket acceptance.
HTTP loopback cookies require a separate HTTPS/Secure-cookie production design.

The controlled candidate pauses only endpoint reconciliation and records its
prior annotation. Restore reconciliation after tested publication and activate
the opt-in portal Application; verify Synced/Healthy and rerun platform gates.
OpenBao remains gated, GPU/vLLM and Spinifex stay disabled, and unattended reboot,
load/soak, SPIFFE attestation and production security sign-off remain open.
See [portal runbook](../../console/README.md) and
[ADR-0027](../architecture/adr/ADR-0027-native-control-plane-portal.md).
