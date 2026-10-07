# LocalStack Community API acceptance: WSL, 2026-10-07

Scope: owned single-node `vcloud-wsl-local`, `platform-services`, CPU-only local
validation. Operator selected legacy Community **4.14.0** without a license
token. The runtime health reports `edition: community` and `version: 4.14.0`.
No production promotion, AWS GUI, actual EC2 VMs or Spinifex offloading is claimed.

## Executed acceptance

The corrected immutable candidate `6f3c898baf36ec8906695fd487c8faf629cc594f`
was Synced/Healthy in Argo during the 16:08 UTC local trial. Windows endpoint
checks passed at 16:08:49 UTC. Publish/merge status is tracked in
[PR #21](https://github.com/amazen33/vCloud/pull/21); final hosted head and main
checks must pass before promotion back to continuously tracking `main`.

| Check | Observed result |
| --- | --- |
| Namespace admission | `restricted:v1.30` enforced |
| LocalStack Pod security | Non-root UID/GID 65532, no privilege escalation, drop ALL, RuntimeDefault; live Pod checked |
| S3 ListBuckets | Signed AWS API HTTP 200 |
| EC2 DescribeInstances | Signed AWS API HTTP 200 |
| IAM ListUsers | Signed AWS API HTTP 200 |
| DynamoDB ListTables | Signed AWS API HTTP 200 |
| Direct health, loopback 4566 | HTTP 200; all four configured services `running` |
| APISIX root, Host `aws.platform.example.com`, loopback 18080 | HTTP 200 from WSL and Windows |
| APISIX health route | HTTP 200; same four `running` states from WSL and Windows |
| Private APISIX admin | Mounted CA verified; unauthenticated HTTPS request rejected with HTTP 401 |
| Existing local end-to-end suite | Ten gates passed, zero failures |
| Demo routing | APISIX -> Kourier -> Knative HTTP 200 |
| Data/telemetry regression | Verified PostgreSQL TLS, retained pgvector marker, APISIX/CNPG/Knative Prometheus targets up and real demo span exported |
| GPU/HPC gates | No GPU allocation, AI/HPC containers or enabled offload flags |
| Deny-all regression | Unauthorized Service and direct Pod traffic blocked from `hpc-compute` to `platform-services`; six matching Cilium policy drops |
| OpenBao gate | Uninitialized/sealed; missing public keys -> exit 3, no POST/init-output Secret |
| Final strict schema checks | 158 rendered resources plus 42 GitOps resources; zero invalid/errors/skipped |
| Restricted-PSS policy | 972 assertions passed, zero warnings/failures/exceptions |
| Static shell analysis | ShellCheck clean for all three new scripts |
| New regression suite | Eight image/security/health/routing tests passed |
| CI-control suite | 27 tests passed, including fail-closed optional-bundle coverage |

The complete pre-cutover offline harness passed 52 checks/478 tests. The route
regression added one further test; hosted candidate validation repeats the full
suite at the final head. CI remains static/offline and does not replace the live
checks above. Non-secret raw evidence is under ignored `.build/localstack/`;
the ten-gate report is `.build/wsl-endpoints/acceptance.json`.

## Corrections made during the bounded trial

The restricted LocalStack UID initially resolved its cache under `/.cache`,
which failed on the read-only root filesystem. Setting HOME/XDG_CACHE_HOME to
the bounded writable memory volume fixed startup without root or capabilities.

Controller 2.2.0 could not create usable upstream nodes for a platform-namespace
ExternalName bridge to Kourier. The demo `ApisixRoute` now lives beside the real
Kourier Service in `workload-apps`, with the IngressClass explicitly referring
to the platform GatewayProxy. The obsolete trial route and bridge Service were
removed after the new route was accepted. AWS and smoke routes remain in
`platform-services`. A brief old-Pod port-forward interruption was handled by
its existing systemd restart; the AWS verifier now retries transient curl errors.

## Bounds and outstanding gates

The emulator uses ephemeral memory state, no Docker socket, hostPath, external
egress or real AWS credentials. DynamoDB starts its internal streams/Kinesis
dependencies; the four requested public API checks are the acceptance scope.
The APISIX controller's upstream global Secret discovery is read-only; production
cache scoping/least-privilege review remains open. Admin credentials and TLS
keys are encrypted create-only Kubernetes Secrets, never host plaintext or Git.
Admin TLS is verified with the mounted public CA and certificates require
operator renewal within 90 days. No new node exception is granted.

Runbook: [LocalStack](../../lab/wsl/localstack/README.md).
Decision: [ADR-0025](../architecture/adr/ADR-0025-localstack-api-lab.md).
