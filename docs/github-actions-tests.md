# GitHub Actions validation

The [vCloud tests workflow](../.github/workflows/pr-tests.yaml) runs on pull
requests targeting `main`, pushes to `main`, and manual dispatch. Its stable
aggregate check is **vCloud PR gate**. Require that check in a GitHub branch
ruleset after the workflow has run; this change does not modify repository rules.
Apply and verify it using the [WO-01 branch-protection runbook](governance/branch-protection.md).

Every normal run tests the candidate revision and six immutable merged revisions:

| Prior PR | Verified merge commit | Scope |
| --- | --- | --- |
| [#1](https://github.com/amazen33/twinfra/pull/1) | `1bc96d335bcb82482e33d4656102123e714c8fe9` | Modules -1, 1 and 2 |
| [#2](https://github.com/amazen33/twinfra/pull/2) | `49848feb7fd58870650c919928297509af3f243a` | Initial workflow |
| [#3](https://github.com/amazen33/twinfra/pull/3) | `e13aa15f3fd4864bb8ee022bd561c29441be7b31` | Delivery, IAM, secrets and gated HPC |
| [#4](https://github.com/amazen33/twinfra/pull/4) | `05471067cb64d89d4ef20fd87319c8cadf3bf7a4` | WSL corrections, recovery documentation and CI review |
| [#5](https://github.com/amazen33/twinfra/pull/5) | `405ac74bedd9ed19f98de699932edf716949a510` | Roadmap document |
| [#6](https://github.com/amazen33/twinfra/pull/6) | `87ed35e883e547311e70fda22161a829687c7f81` | Roadmap automation |

The reviewed [baseline inventory](../tools/ci/pr-baselines.json) controls those
historical commits. Add future baseline PRs to that inventory through review.

Once this workflow is merged into `main`, select **Actions → vCloud tests →
Run workflow**, and enter a PR number to retest another prior PR. Alternatively:

```bash
gh workflow run pr-tests.yaml --repo amazen33/twinfra --ref main -f pr_number=1
gh run list --repo amazen33/twinfra --workflow pr-tests.yaml
```

Merged PRs are tested at their merge commit. Open or unmerged closed PRs are
tested at the resolved head commit. Input is validated as a positive integer;
repository metadata and every selected 40-character commit SHA are verified.
Manual dispatch is available after the workflow exists on the default branch.

## Executed gates

WO-02 adds an offline licence gate against the **candidate CI control checkout**
on each matrix job. Historical inventories are not reclassified. The runner
uploads `licences.json` alongside its normal summary, and prints every open
baseline/pending-removal entry and its fixed expiry. See the
[licence gate runbook](../security/LICENSING.md). New components, changed evidence
inputs, expired entries and invalid class conditions fail the required gate.

| Revision content | Required validation |
| --- | --- |
| Module -1 | Exact SSoT and Cloud-Init generation, upstream Cloud-Init schema, Bash syntax and ShellCheck, Cilium/NVIDIA Helm renders, strict offline Kubernetes schemas, all 42 host regression tests including the node exception policy |
| Module 1 | All 17 component ADRs, identities, local documentation links, frozen approved node policy/inventory hashes, real Mermaid parser and required data-flow edges |
| Module 2 | Vendored Helm and CRD integrity, strict rendered kubeconform validation, all 54 infrastructure guardrail tests |
| Module 3, when present | CI/GitOps manifest validation, pipeline and application tests, Prometheus rule validation and alert scenarios |
| Module 4a, when present | OpenBao/CSI configuration validation, Bash/jq integration contract tests with mock transports |
| Module 4b, when present | Keycloak/APISIX/RBAC validation and security regression tests |
| Module 5a, when present | Strict GPU Knative/CSI/Job/policy schemas, frozen Pod security audit, deterministic renders, real LangChain/SQLAlchemy client and LCEL tests with mocked database/inference transports |
| Module 5b, when present | Disabled Spinifex profile, Kueue Helm/CRD validation, durable capacity limits, SDK signing/stubs, local mTLS and HPC alert scenarios |
| WSL lab, when present | Local K3s configuration, strict manifests/frozen Cilium audit, resource/adoption/CIDR safeguards; no host execution on GitHub |
| WSL routing boundary | Unconditional candidate source guard; applicable selected revisions also run mutation tests and locked-chart lab/base render assertions; reject legacy routing outside the exact local values overlay, including Argo Helm overrides |
| WSL GitOps/database, when present | Locked Argo/CNPG/metrics artifacts, strict rendered schemas, exact Local PV vetting, TLS/RBAC boundaries and bounded CPU/memory growth; SQL and reconciliation require live acceptance |
| WSL endpoints, when present | Strict endpoint/GitOps schemas and render drift, restricted Pod policy, CPU-only mutations, PGP-only initialization/custody guards; no initialization or deployment on GitHub |
| Registry overlay, when present | Strict kubeconform with no skipped resources; explicit `IfNotPresent`, immutable Argo images and pull-secret references; Rego rules and DNS/TLS/cache/private-path fixtures |
| Platform probe correction, when present | Both policy schemas, workload/port scope, dependency prechecks, dynamic CIDR preservation, multi-pod health/stability and fail-closed restart recovery fixtures |
| Roadmap automation, when present | Mocked pagination, exact-title reuse, milestone assignment, dry-run no-writes and closed-milestone rejection; no GitHub mutation |
| Rebuilt dev environments, when present | Pure Hyper-V planner fixtures (including six Amendment 3 cases), generic image conversion guards, naming/source mutation tests, deterministic dev/seed generation, strict kubeconform, restricted Pod policy and unchanged node-agent mount/security projection; no provisioner entry-point execution |
| WO-29 runnable dev profile, when present | 7.4 requirement/resource-bound fixtures; fake SSH/ctr staging, cache/mismatch/readonly checks; two-region rendered bootstrap-image inventory equality; in-memory dev CA SAN/key-usage and Git-boundary tests; HTTPS-only gateway/realm and saved production-render byte identity |
| CI controls | Historical revision selection, invalid input/commit rejection, checksum and archive safety, partial module rejection, no skipped or empty suites, immutable action/tool pins |
| WO-06 emulator removal | Unconditional candidate code/lock/manifest search; only exact historical CI mapping/dispatch lines may name the removed emulator; aged MiniStack pin, fixed backend and mocked S3/EC2/DynamoDB reads; deleted runbook links in two unchanged historical records verified against frozen Git source |

The [runner](../tools/ci/run_checks.py) always requires the original modules.
It also lints the packaged Cilium/APISIX charts and, when present, Kueue.
Later modules absent from an older commit are recorded as
`not_present_in_revision`; partial implementations fail. Unit-test failures,
empty suites and skipped tests fail the gate. The runner produces fresh evidence
instead of trusting previously committed validation reports.
The document-only roadmap does not require a later automation implementation,
and historical WSL profiles do not require the later proxy repair. Once either
feature is present, incomplete bundles fail instead of disappearing from coverage.

The candidate [host-routing guard](../tools/check_host_routing.py) runs from the
CI control checkout before selected-revision gates. Thus historical PRs without
the new WSL overlay do not suppress the candidate's production/staging boundary
check. New routing bundles require the overlay, guard and tests together.
The selected-revision render gate asserts lab legacy routing `"true"`, base
`"false"`, native mode, BPF masquerade, proxy replacement and explicit lab socket
LB. The [ADR](adr/0024-wsl-host-routing.md) records the exception.
Require `vCloud PR gate` in a GitHub ruleset for enforced merge prevention;
the local CI rule alone does not protect an otherwise unprotected `main` branch.

## Dependency and execution boundaries

Jobs use disposable GitHub-hosted Ubuntu 24.04 runners with read-only repository
permissions, checkout credentials disabled, and no deployment secrets. Actions
use immutable commit pins. Python libraries and Node.js have explicit versions;
Mermaid dependencies use a checked-in integrity lock. Downloaded executables,
the NVIDIA chart and extra host schemas are SHA256 verified against the
[CI tool lock](../tools/ci/toolchain.lock.json); Kubernetes and operator schemas
already vendored in the selected revision remain subject to its integrity checks.
WO-21 also stages the official MIT PowerShell 7.6.6 runtime by SHA256 into the
disposable CI workspace. Archive entries are bounded and checked individually;
links and parent paths are refused. Its tests import only the pure fixture planner.
When Module 5b is present, the workflow installs its seven SDK test dependencies
from the CI control checkout's hash-locked `hpc-requirements.txt`. Historical
revisions without the module do not install or run that optional dependency set.
Module 5a similarly installs 43 hash-locked client test packages from
`rag-requirements.txt`; its 73-package CPU encoder runtime remains a separate
Linux amd64 image lock. Hosted unit tests do not download model weights or
connect to a database or GPU.
The earlier workflow-only PR's results do not validate Module 5b. Each later
hosted run validates its exact selected candidate and reports optional modules
present in that revision.

GitHub-hosted CI needs network access to fetch those pinned dependencies. The
module gates run with local schemas and chart archives; this is not an air-gapped
runner provisioning solution. No privileged container, host bootstrap execution,
`kubectl apply`, database connection or real secret issuance occurs.

Each matrix job uploads its public validation summary and individual logs for
14 days, including evidence available before a failure. Caches, kubeconfigs,
environment dumps and credential files are excluded. These results establish
static/offline acceptance; GPU, Kubernetes admission, end-to-end networking,
OIDC discovery and live OpenBao revocation still require the Ubuntu lab.
