# Keycloak administrator acceptance — 2026-10-07

Scope: first administrator in the single owned `vcloud-wsl-local` WSL lab,
Keycloak 26.8.0, namespace `platform-services`, restricted:v1.30 admission.
This records runtime acceptance before this change's GitHub publication.

## Root cause and implementation

The realm import had no users and the startup profile had no human bootstrap
credential. The master realm already existed. Discovery and the admin console
HTML returned HTTP 200, but the welcome page showed “Local access required”
without a first-admin form. Startup credential flags would not recover an
already created master realm.

The supported offline command was executed using the server's existing database
and TLS configuration, with only Keycloak stopped. A temporary skip-reconcile
annotation prevented the endpoint Application from racing that stop. Its prior
annotation and the single replica were restored in cleanup. Two unsuccessful
input attempts created no account and restored the server; a real terminal
attachment fixed the input channel. A preceding nonsecret terminal fixture
passed and verified no input echo before private credentials were used.

## Executed checks

| Gate | Result |
|---|---|
| Original master-realm users | Zero before recovery |
| Owned-node / restricted admission / encryption-at-rest checks | Passed |
| Offline recovery Pod server admission | Passed with locked images, no privileges/host mounts, bounded runtime and never-Ready Service endpoint |
| Nonsecret terminal fixture | Input reached both reads; not echoed; exact fixture Pod removed |
| Recovery account creation | Temporary `vcloud-bootstrap-admin` created via dedicated CLI |
| Permanent administrator | `vcloud-admin` created in master and assigned master realm `admin` role |
| Actual password authentication | Token endpoint succeeded over public certificate and localhost hostname verification; token kept in process memory |
| Authorized administration | Authenticated GET `/admin/realms/master` succeeded |
| Temporary identity cleanup | Recovery user and recovery Secret removed |
| Idempotent rerun | Existing account authentication/administration verified; password preserved; no offline restart |
| Static Pod fixture | Strict kubeconform: 1 valid, 0 invalid/errors/skips; conftest: 9 passed |
| Credential/recovery regressions | 10 tests passed, including restoration, ownership, stdin/body-only secret transfer, verified TLS and cross-origin redirect refusal |
| Complete repository offline suite | 61 checks / 502 tests passed; `.build/keycloak-admin/ci-complete/summary.json`, completed 2026-10-08 |
| Trusted CI controls | 29 tests passed; a partial admin-bootstrap bundle fails closed |
| Password-copy helper | PowerShell syntax and four synthetic success/refusal cases passed without real clipboard or cluster access; actual operator retrieval is an explicit local action |

Initial credentials remain only in the encrypted Kubernetes Secret
`platform-services/vcloud-wsl-keycloak-admin`. No values appear in this record,
Git, command arguments, environment variables or host plaintext files. The
[runbook](../keycloak-admin-access.md) provides private clipboard retrieval.

Successful password authentication and authorized API access establish the
account's credentials and permissions. Operator browser login, password-manager
custody and MFA enrollment remain separate human actions. The console's
`vcloud-console` OIDC client/Secret gate remains open. OpenBao initialization,
GPU/vLLM and Spinifex offloading were not enabled by this recovery.
