# GitHub Actions validation

The [vCloud tests workflow](../.github/workflows/pr-tests.yaml) runs on pull
requests targeting `main`, pushes to `main`, and manual dispatch. Its stable
aggregate check is **vCloud PR gate**. Require that check in a GitHub branch
ruleset after the workflow has run; this change does not modify repository rules.

Every normal run tests the candidate revision and the immutable merged revision
of [PR #1](https://github.com/amazen33/vCloud/pull/1),
`1bc96d335bcb82482e33d4656102123e714c8fe9`, covering Modules -1, 1 and 2.
The reviewed [baseline inventory](../tools/ci/pr-baselines.json) controls those
historical commits. Add future baseline PRs to that inventory through review.

Once this workflow is merged into `main`, select **Actions → vCloud tests →
Run workflow**, and enter a PR number to retest another prior PR. Alternatively:

```bash
gh workflow run pr-tests.yaml --repo amazen33/vCloud --ref main -f pr_number=1
gh run list --repo amazen33/vCloud --workflow pr-tests.yaml
```

Merged PRs are tested at their merge commit. Open or unmerged closed PRs are
tested at the resolved head commit. Input is validated as a positive integer;
repository metadata and every selected 40-character commit SHA are verified.
Manual dispatch is available after the workflow exists on the default branch.

## Executed gates

| Revision content | Required validation |
| --- | --- |
| Module -1 | Exact SSoT and Cloud-Init generation, upstream Cloud-Init schema, Bash syntax and ShellCheck, Cilium/NVIDIA Helm renders, strict offline Kubernetes schemas, all 42 host regression tests including the node exception policy |
| Module 1 | All 17 component ADRs, identities, local documentation links, frozen approved node policy/inventory hashes, real Mermaid parser and required data-flow edges |
| Module 2 | Vendored Helm and CRD integrity, strict rendered kubeconform validation, all 54 infrastructure guardrail tests |
| Module 3, when present | CI/GitOps manifest validation, pipeline and application tests, Prometheus rule validation and alert scenarios |
| Module 4a, when present | OpenBao/CSI configuration validation, Bash/jq integration contract tests with mock transports |
| Module 4b, when present | Keycloak/APISIX/RBAC validation and security regression tests |
| CI controls | Historical revision selection, invalid input/commit rejection, checksum and archive safety, partial module rejection, no skipped or empty suites, immutable action/tool pins |

The [runner](../tools/ci/run_checks.py) always requires the original modules.
Later modules absent from an older commit are recorded as
`not_present_in_revision`; partial implementations fail. Unit-test failures,
empty suites and skipped tests fail the gate. The runner produces fresh evidence
instead of trusting previously committed validation reports.

## Dependency and execution boundaries

Jobs use disposable GitHub-hosted Ubuntu 24.04 runners with read-only repository
permissions, checkout credentials disabled, and no deployment secrets. Actions
use immutable commit pins. Python libraries and Node.js have explicit versions;
Mermaid dependencies use a checked-in integrity lock. Downloaded executables,
the NVIDIA chart and extra host schemas are SHA256 verified against the
[CI tool lock](../tools/ci/toolchain.lock.json); Kubernetes and operator schemas
already vendored in the selected revision remain subject to its integrity checks.

GitHub-hosted CI needs network access to fetch those pinned dependencies. The
module gates run with local schemas and chart archives; this is not an air-gapped
runner provisioning solution. No privileged container, host bootstrap execution,
`kubectl apply`, database connection or real secret issuance occurs.

Each matrix job uploads its public validation summary and individual logs for
14 days, including evidence available before a failure. Caches, kubeconfigs,
environment dumps and credential files are excluded. These results establish
static/offline acceptance; GPU, Kubernetes admission, end-to-end networking,
OIDC discovery and live OpenBao revocation still require the Ubuntu lab.
