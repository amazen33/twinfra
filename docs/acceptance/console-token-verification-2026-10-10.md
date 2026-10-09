# Console token verification acceptance receipt — 2026-10-10

## Scope and authorization

- Work order: [WO-04](../work-orders/WO-04-console-token-verification.md).
- Repository / branch: Twinfra (`amazen33/vCloud`), `codex/wo-04-console-jwt`.
- Environment: static local unit fixtures and hosted CI only. No retired WSL
  cluster deployment, live browser test, image import or GitHub settings change.
- Owner authorization: implement WO-04 statically; defer live acceptance to VM
  `lab-1` after WO-21. This receipt does not authorize that deployment.
- Tested revision: the WO-04 PR head; immutable SHA is recorded in its CI artifacts.
- Tester / witness: Ahmed Mazen; live witness and QoS targets Pending.

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
| `console/browser-acceptance.mjs`: login | Authenticated console access | Pending | VM `lab-1`, after WO-21 |
| Both emulator reads | Read-only views work | Pending | VM `lab-1`, after WO-21 |
| Logout | Session no longer accesses console | Pending | VM `lab-1`, after WO-21 |
| Roleless login | Portal denied | Pending | VM `lab-1`, after WO-21 |
| Direct BFF request with hand-made unsigned header | 401 | Pending | VM `lab-1`, after WO-21 |

## Pending gates, deviations and owner actions

- Live redeployment and the browser/direct-backend tests were **not attempted**.
- Owner: complete WO-21, approve the VM deployment scope and establish its
  reviewed issuer, public CA and gateway profile, then run the live acceptance.
- Claude: review this PR against WO-04 before the owner merges.
- Deviations: none; live deferral is the owner's explicit instruction.
- No restoration or rollback is needed: no live configuration was changed.

## Tester sign-off
Tester: Ahmed Mazen (@amazen33), enterprise and cloud tester; QoS tester
Result: Pending
Date (UTC):
QoS targets checked:
Notes:
