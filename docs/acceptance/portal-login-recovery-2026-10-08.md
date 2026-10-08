# Portal login recovery — 2026-10-08

Scope: single owned mirrored WSL2 `vcloud-wsl-local`, APISIX 3.19.0,
Keycloak 26.8.0 and the existing restricted native portal. This is local lab
acceptance, not production readiness or unattended restart acceptance.

## Findings and corrections

APISIX logged a missing browser session at `/console/callback`. Windows, WSL
and Keycloak clocks agreed, and the operator account already had an OTP
credential. The callback 500 occurred while recovering OIDC state; the evidence
does not distinguish cookie loss from the 15-minute idle expiry. No operator
OTP seed, code, password or callback query was reused for diagnosis.

The gateway now opens the original encrypted session before OIDC callback
processing. Missing, expired or malformed cookies return HTTP 401 with a fixed
fresh-login link and no reflected parameters. This page exposes no platform
data and does not exchange the supplied code or retry automatically. A present
session continues through APISIX's existing state, PKCE, token and role checks.
API anonymous denial and identity-header scrubbing remain enforced.

The realm import registered `CONFIGURE_TOTP`, but not `UPDATE_PASSWORD`.
An ephemeral browser user enrolled MFA and reached the portal while its password
action remained pending. The new test correctly rejects that incomplete flow.
The renderer now registers both providers, and the existing-realm helper uses
Keycloak's documented `register-required-action` endpoint followed by an
explicit enabled/non-default configuration. Idempotence and unchanged operator
password/OTP credential identifiers were verified. No account password or MFA
credential was reset. Existing users with the pending action now receive the
password-change form at sign-in.

The full browser regression starts at the portal with no injected login cookie,
completes password change and TOTP enrollment, then starts a separate browser
context and signs in with the new password and a fresh TOTP. Both required
actions must be complete. Private inputs use stdin and process memory only;
no OAuth URLs, cookies, seeds, HAR or storage-state files are saved. The test
browser trusts only the public-key fingerprint of the lab certificate already
verified through Python HTTPS, with hostname and validity checks. It changes
neither OS trust nor general TLS verification.

## Restart recovery and measured results

The operator restarted WSL during the investigation. The node initially became
NotReady, access units disappeared and existing containers exited. Cilium's
stale `eth2` selection had no usable address; the current LAN route and Cilium
device table agreed on `eth1` with the existing Node InternalIP. The existing
Helm release was reconciled with the locked chart and guarded post-renderer;
47 resources passed strict schemas. Native routing, BPF masquerade, full proxy
replacement and the local-only legacy host-routing profile remain selected.
The retained PostgreSQL filesystem stayed mounted and its persisted marker
passed after recovery. No PV, database, Windows configuration or firewall was
deleted or reset.

The loopback helper now preserves exact protocol-specific ingress rules that
mirrored WSL recreates at boot. Eight tests cover idempotence, preservation,
precise rollback and rejection of broader/foreign state. Only the two owned
127.0.0.1/32 selectors and the vetted nftables table are repaired. A bounded WSL
process kept the distro alive during testing; keep an Ubuntu shell open for
manual GUI use. Automatic post-restart reconciliation remains an open gate.

| Check | Result |
|---|---|
| Missing and malformed callback cookie | HTTP 401 with recovery link; no reflected code |
| Anonymous/spoofed identity API | HTTP 401 |
| Protocol PKCE and MFA flow | Passed |
| Full browser initial and returning login | Passed; password action and MFA completed |
| Session attributes | HttpOnly, SameSite=Lax, `/console` scope |
| Native APIs and six browser views | HTTP 200; desktop/mobile navigation passed |
| Restarted standalone access | Argo CD Core GUI/Applications API on 8080 and LocalStack four-service health on 4566 passed |
| Authenticated write | HTTP 405 |
| Logout and roleless access | Denied |
| Disposable users | Removed; operator credentials preserved |
| Portal/IAM/routing tests | 21 + 34 + 8 passed |
| CI controls | 31 passed |
| Portal kubeconform | 20 valid; zero invalid/errors/skips |
| Full offline suite | 66 gates / 533 tests passed on the final source tree |
| Platform acceptance | Ten gates passed, zero failures |
| Deny-all regression | DNS/allowed control passed; unauthorized Service/Pod blocked; six matching Cilium drops |
| OpenBao and AI/HPC | Initialization still PGP-gated; GPU/vLLM/Spinifex disabled |

Publication requires green immutable-head GitHub checks before merge, restoration
of the exact prior portal reconciliation annotation, and all three Applications
Synced/Healthy at the published main commit without conditions or pauses.
The complete local offline run uses the existing pinned test libraries:

```bash
export PYTHONPATH="$PWD/.tools/module-5a-linux-sdk:$PWD/.tools/module-5b-sdk"
python3 tools/ci/run_checks.py --source . --assets .build/ci-linux-assets \
  --report .build/console/ci-final-pinned
python3 tools/test_console_live.py \
  --browser 'C:/Program Files/Google/Chrome/Application/chrome.exe'
bash lab/wsl/test-e2e.sh
```

The initial final-suite invocation used system Python without these libraries
and stopped at the missing LangChain import. The pinned RAG suite passed before
rerunning the complete regression. CI installs the checksum-pinned dependencies
from its trusted control revision instead of relying on these local paths.

The previous portal receipt is corrected to distinguish cookie-injected view
testing from the full browser authentication test. See the
[portal runbook](../../console/README.md#login-and-callback-recovery) for login
recovery and private password retrieval. Any exposed OTP seed must be replaced
through an authorized operator procedure; this repair preserves existing MFA.
