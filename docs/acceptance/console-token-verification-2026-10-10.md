# Console token verification acceptance receipt — 2026-10-10

## Scope and authorization

- Work order: [WO-04](../work-orders/WO-04-console-token-verification.md).
- Repository / branch: Twinfra (`amazen33/vCloud`), `codex/wo-04-console-jwt`.
- Environment: static local unit fixtures and hosted CI only. No retired-lab
  cluster deployment, live browser test, image import or GitHub settings change.
- Owner authorization: implement WO-04 statically; defer live acceptance to VM
  `lab-1` after WO-21. This receipt does not authorize that deployment.
- Tested revision: the WO-04 PR head; immutable SHA is recorded in its CI artifacts.
- Tester / witness: Ahmed Mazen; live witness and QoS targets Pending.
- Environment (live): `twinfra-dev-cairo-1` on the Dell (ADR-0048 replaced the planned VM `lab-1`).
  Live evidence 2026-10-17 (WO-40a acceptance) and 2026-10-18 (tester browser witness).

## Static evidence

Unit tests generate temporary RSA/EC keys in memory and stub JWKS; localhost HTTP
fixtures verify the actual handler's status/JSON contract. No real token, private
key, credential, cookie or cluster connection is used or logged.

- `python -m unittest discover -s tests -p test_vcloud_console.py -v`: 33 tests passed.
- `python -m unittest discover -s tools/ci/tests -v`: 66 CI-control tests passed.
- `npm test --prefix console`: 5 frontend tests passed; `npm run build --prefix console` passed.
- `tools/vcloud_console.py --validate` with pinned offline kubeconform/schemas:
  20 resources valid, zero invalid/errors/skipped.
- Deterministic OCI archive build and extracted-payload Linux import/RS256 smoke:
  passed without creating a container or importing an image.
- The alternative Docker-daemon build was not executed; the static OCI builder
  was used. No live/browser command was attempted.
- `tools/ci/run_checks.py` against the candidate with cached Linux tools/schemas:
  all 68 checks and 550 unit tests passed, including ShellCheck, strict schemas,
  PSS/Helm checks and both source/rendered licence gates.
- A fresh local immutable PR #1 baseline run passed: 17 checks and 96 tests.
- The historical baseline file's SHA256 remains
  `19c40da7d2ec928562d0c8b68865b0d0c2399d1a05200fde31c63ed62f0e1659`.

| Unit acceptance case | Expected response | Static outcome |
| --- | --- | --- |
| Valid RS256 access token with console role | 200, reduced identity | Passed |
| Valid ES256 token; array audience; `azp` client | Accepted | Passed |
| Forged signature | 401 | Passed |
| Unknown `kid` | 401 | Passed |
| Expired token | 401 | Passed |
| Not-yet-valid token | 401 | Passed |
| Wrong issuer | 401 | Passed |
| Wrong audience and no matching authorized party | 401 | Passed |
| `alg: none` | 401 | Passed |
| HS256 using the RSA public key as secret | 401 | Passed |
| Malformed or missing token header | 401 | Passed |
| Valid token without a console role | 403 | Passed |
| Unsigned old identity header; duplicate access headers | 401 | Passed |
| Write methods | 405 | Passed |
| Unknown-key refresh, rotation, removed key, failed/stale cache | Bounded, fail closed | Passed |
| Private CA, fixed URL, no redirects, bounded JWKS | Verified TLS contract | Passed |

The existing Keycloak audience and client-role mappers already set
`access.token.claim: "true"`; no mapper or realm mutation is required.
Dependency versions and every accepted SHA256 are in
[console/requirements.txt](../../console/requirements.txt). Their upstream
licence sources are in the [register](../../security/licence-register.json).

The PR records final candidate/module/schema/ShellCheck, CI-control, frontend,
licence and six immutable historical-matrix results and the hosted run URL.
Static evidence is distinct from the unexecuted live gates below.

## Live evidence

| Check | Expected outcome | Observed outcome | Environment / evidence |
| --- | --- | --- | --- |
| `console/browser-acceptance.mjs`: login | Authenticated console access | Passed: the tester signed in as `amazen` (password and TOTP) and reached the console | `twinfra-dev-cairo-1`, tester browser witness 2026-10-18; automated `consoleHTTPS` identity 200 in the WO-40a runs of 2026-10-17 |
| Both emulator reads | Read-only views work | Passed: the S3, EC2 and DynamoDB read views listed without errors | `twinfra-dev-cairo-1`, tester browser witness 2026-10-18 |
| Logout | Session no longer accesses console | Passed: after sign-out the console required a new sign-in | `twinfra-dev-cairo-1`, tester browser witness 2026-10-18 |
| Roleless login | Portal denied | Passed: `accept-roleless` was refused at the gateway (401 Authorization Required; the OIDC claim check requires a console role) | `twinfra-dev-cairo-1`, tester browser witness 2026-10-18; a roleless token at the BFF returns 403 (WO-40a `tokenNegatives`) |
| Direct BFF request with hand-made unsigned header | 401 | Passed: 401 (missing 401, unsigned 401, duplicate 401, roleless 403) | WO-40a `tokenNegatives`, runs 2026-10-17 17:08 and 22:24 UTC; [baseline receipt](release-0.1.0-2026-10-17.md) |

## Pending gates, deviations and owner actions

- The live gates were completed on `twinfra-dev-cairo-1` on 2026-10-17 and 2026-10-18. The VM `lab-1` plan was
  superseded by the Dell (ADR-0048). The tester witnessed the browser cases manually instead of running
  `console/browser-acceptance.mjs`; the direct-backend cases come from the WO-40a acceptance suite.
- Owner: complete WO-21, approve the VM deployment scope and establish its
  reviewed issuer, public CA and gateway profile, then run the live acceptance.
- Claude: review this PR against WO-04 before the owner merges.
- Deviations: none; live deferral is the owner's explicit instruction.
- No restoration or rollback is needed: no live configuration was changed.

## Tester sign-off
Tester: Ahmed Mazen (@amazen33), enterprise and cloud tester; QoS tester
Result: Accepted
Date (UTC): 2026-10-18
QoS targets checked: interactive sign-in with TOTP, the S3, EC2 and DynamoDB read views, sign-out ends access, a roleless user is refused, and missing, unsigned and duplicate tokens return 401 while a roleless token returns 403.
Notes: Dev-verified on twinfra-dev-cairo-1. Signed by the owner in chat ("sign WO-04 and WO-06"); recorded by the architect at the owner's instruction.
