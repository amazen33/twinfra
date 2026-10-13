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
| Module -1 | Exact SSoT and Cloud-Init generation, upstream Cloud-Init schema, Bash syntax and ShellCheck, Cilium/NVIDIA Helm renders, strict offline Kubernetes schemas, host regression tests including the node exception policy and guarded systemd 255 BPF migration |
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
| WO-31 image assembly, when present | Anonymous Docker Hub export against a local fake HTTP registry; corrupt root/manifest/config/layer refusal; hash-locked wheel checks; deterministic console fixture builds; both archive/lock checks with no repository writes; unchanged production and retained WSL bytes; receipt/source-drift guards |
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

WO-31 Amendment 4 adds a real kubeadm v1.36.5 preview on the disposable Ubuntu
runner. The binary comes from `dl.k8s.io`, matches the reviewed tool lock and its
published SHA-256, and reports the exact version before use. On each matrix leg,
the candidate CI control checkout renders its dev-cairo-1 and production configs
and etcd patches. Only `sudo -n env KUBEADM_INIT_DRYRUN_DIR=... kubeadm init phase
control-plane all --dry-run` and `... etcd local --dry-run` run; no preflight,
kubelet, container runtime, image pull or cluster is required. The gate checks
the four generated manifests and exactly one config-derived, read-only
`etcd-certs` mount. Any command/checksum/assertion failure fails the job.
Because kubeadm writes those four public YAML files as root with mode 0600,
`sudo -n chown` returns only those exact regular files to the runner user before
assertion/upload; it never recurses or changes host paths or credential files.
Evidence is uploaded under `kubeadm-dry-run/` in every validation artifact.
Historical selected revisions still run their original offline suites; their
old etcd patches are not used as the candidate preview input. Windows unit tests
exercise path/command/checksum failures; the real Linux binary is tested in CI.

Amendment 5 extends that same required step with the shared `install_tooling` /
`install_cli` functions, redirecting only their install destination and final
binary hash lookup into a temporary CI directory. It retains their release URLs,
published checksums, selected archive members and stamps, then checks the
reviewed `host-cli.lock.json`. No global installation or APT changes occur.
Pinned kubectl comes from `dl.k8s.io` with both locked/published SHA256 checks;
jq and kubeadm use the existing staged tools. The gate reads and runs the two
exact client-version lines from `validate_host`, including
`tkn version --component client`, and captures each binary's help and output.
CLI archive/binary corruption, missing commands and version-command failures
fail CI. HPC/GPU conditional checks have a separate
[source review and execution boundary](dev-environment.md#module--1-cli-validation-review).

Amendment 6 removes the inherited runner-HOME workaround. CLI installation and
each pinned help/version command start through `env -i` with PATH only; the
version wrapper uses `sudo -n` to match Module -1's root execution, asserts HOME
is absent, sources Module -1, and exercises its
own exported `/root` default. The exact commands still come from `validate_host`.
`cli-summary.json` records this environment boundary. A missing default or any
version failure fails the required step on the candidate and all six historical
matrix legs. Offline tests also exercise a fake Argo CD requiring HOME, a generic
command exit 20 becoming failure exit 1, the deliberate reboot exit 20, and the
host agent's requirement for matching reboot-result evidence.
The root wrapper executes only help/version commands after loading defaults;
it does not invoke `main`, provision the runner or modify tool configuration.

Amendment 7's offline host suite executes the generated contract checker on a
single object, a direct kubectl `kind: List`, existing object arrays, bare scalar
inputs and malformed nested List entries. Invalid entries must produce violations
and exit 1 without a traceback. The Cilium fixture uses the actual pinned Helm
render and the dev node-exception policy: the agent DaemonSet and all three
Cilium controllers pass in direct/List/array form; host-mount drift still fails.
Strict byte comparisons against merged main `1f7d86f` allow only the checker block
and derived render hashes; a separate comparison confines source changes to
`main()`. Production callers, `flatten()`, policy and pinned versions stay intact.

Amendment 8 runs the real main apply tail under the production shell options and
ERR trap with external host/cluster operations stubbed. Smoke disabled/enabled
and Kubernetes bootstrap disabled must reach `write_result ready`; a mocked
smoke apply failure must still write failed, exit 1 and omit the completion marker.
A static rule rejects status-less early returns, including `|| return`,
`&& return`, compound skip blocks and dispatch arms. Render-byte comparisons
against merged main `24b8bdb` permit only the seven audited return-status lines
and derived checksums/gzip. Existing staging and policy failures retain their
explicit statuses; no live provisioner or cluster is executed.

Amendments 9–9a add the optional `dev-image-build` bundle, detected by its new
orchestrator, test suite or owner action. Old revisions with only the shared
builders remain absent; incomplete new bundles fail closed. Its 13 offline tests
use synthetic OCI graphs, wheels, frontend files and a loopback HTTP registry.
They never download real images, run pip/npm, import images or connect to the
Dell. The retained WSL renderer accepts Twinfra receipt metadata while returning
the unchanged legacy digest reference; changed digests/source hashes fail.
Production, retained WSL outputs and the six baseline pins are compared against
merged main `3b6ec82`. The real pinned image reproduction is separate local
static evidence in the [dated receipt](acceptance/dev-environment-2026-10-13.md).

WO-31 adds an optional bare-metal bundle. Fixtures cover both read-only host-check
modes and every required cluster/listener identity, key-only SSH/SCP, copied SHA-256
verification, sudo refusal, healthy no-op bootstrap, guarded SSH and scoped firewall
rollback, finite LV ownership/reserve/mount settings, CRI pin refusal and dev log caps.
Masked byte comparisons use the immutable pre-WO-31 main `968f336` (PR #38): only
the embedded agent and dev log-cap blocks may differ in cairo-2; production renders
remain byte-identical here because they do not embed the agent. Historical revisions
without this bundle remain absent. Neither SSH nor any owner provisioner is executed.

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
