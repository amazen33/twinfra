# Unified vCloud console acceptance — 2026-10-07

Scope: opt-in CPU-only `vcloud-wsl-local`, 20GB RAM/6 vCPUs, vCloud identity.
Source branch: `codex/unified-vcloud-console`, based on main
`2a6618d1cded4f4a1e7c7418e72cccde2e1da889`. This record covers the working tree,
not a published commit or a GitHub workflow result.

## Completed checks

| Gate | Evidence/result |
|---|---|
| Complete repository offline CI | `.build/url-recovery/ci-complete/summary.json`: 57 checks / 492 tests passed; includes existing module/Helm/CRD/policy gates, the listener repair and all new console gates |
| Trusted CI harness controls | 28 tests passed, including console bundle presence |
| Final console regressions | All 13 tests passed in the complete offline run: rewrite boundaries, same-namespace routing, OIDC Secret gate, header ordering, fixed-origin CORS, restricted PSS mutations, backend allowlist, HTML escaping and live local HTTP-handler 200/400/503 behavior |
| Strict kubeconform | 40 resources in 6 console files; 40 valid, 0 invalid, 0 errors, 0 skipped |
| ShellCheck | Console `deploy-backends.sh`, `apply.sh`, `verify.sh` and revised LocalStack `access.sh` passed |
| Immutable MiniStack staging | Public release `1.5.22` resolved to index digest `sha256:0e51461e29524b884306810ce05c8a2e47f90f0c4dddc5a5f52166d2b56c7818`; exact digest staged/tagged in owned CRI cache |
| API-server admission and rollout | Scoped policies and workloads passed server dry-run; MiniStack, navigation shell, storage-ui and dynamodb-admin all 1/1 Ready under restricted:v1.30 |
| MiniStack and LocalStack health | Both HTTP 200; LocalStack S3/EC2/IAM/DynamoDB all running |
| Both emulator API/read-only views | Signed S3 bucket/object-key reads, DynamoDB table list/metadata, EC2 DescribeInstances and IAM ListUsers passed from the restricted storage-ui Pod |
| Named empty fixtures | `test-backends.py --seed` created only empty `vcloud-console-acceptance` buckets/tables in the two fixed local emulators; both views found them |
| Identity activation gate | Missing `platform-services/vcloud-console-oidc` returned exit 3; no console Application or public console routes applied |
| Existing GitOps | `vcloud-wsl-platform` and `vcloud-wsl-endpoints` remained Synced/Healthy at the original main revision after backend staging |
| New cross-namespace denial | After scoped review access resumed, `test-denied.py` confirmed working DNS and blocked unauthorized `hpc-compute` requests to MiniStack, LocalStack, storage-ui, dynamodb-admin and the shell; its exact created test Pod was cleaned up. |

The cache-only node check passed both required cached images. Its mirror DNS
lookup failed; TCP/TLS to the mirror was not checked. This is cached deployment
acceptance, not fresh mirror connectivity or offline cold-cache proof.

## Outstanding acceptance

- Public hostname/DNS, exact verified Keycloak issuer/client/CA trust and Secret
  provisioning. The selected client reference is deliberately gated.
- Authenticated browser root/views/API health paths through APISIX, denied and
  expired sessions, logout and refresh. No unified-console browser HTTP 200 is
  claimed, and the existing generic gateway smoke 200 is not console acceptance.
- Actual backend WebSocket handshake, UI redirects/asset base paths and framing
  for any replacement third-party UI. Native APISIX websocket flags are configured;
  schema/header assertions do not establish live socket acceptance.
- Spinifex console deployment/source/version and OpenBao TLS/native UI integration;
  both remain excluded disabled references. OpenBao initialization/unseal is not
  attempted, and GPU/vLLM/Spinifex offloading remain disabled.
- Rendered browser visual inspection was not run during the initial tooling
  interruption; HTTP-handler and backend-content tests are separate evidence.
- Commit/push/PR and exact-head GitHub workflow acceptance are pending, not passed.

The source can be reviewed in the workspace and activated using the
[runbook](../../lab/wsl/console/README.md) after the missing identity inputs.
The scoped backend deployment used no new host mounts, root containers, Docker
socket, GPU resources, secret environment variables or OpenBao credentials.

## Tooling interruption

Automatic approval review could not execute the temporary WSL loopback preview:
the reviewer returned an account usage-limit error and stated that the action
was not executed. It was a review availability failure, not a determination that
the action was unsafe. No review bypass was attempted. Existing approved offline
CI completed successfully. Scoped review access subsequently resumed; the
[URL recovery record](local-url-recovery-2026-10-07.md) covers the later listener
repair, retry acceptance and successful Keycloak discovery.
