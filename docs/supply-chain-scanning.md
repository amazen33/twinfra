# Supply-chain vulnerability scanning

[ADR-0049](adr/0049-supply-chain-vulnerability-scanning.md) and
[WO-32](work-orders/WO-32-supply-chain-scanning.md) govern this static CI boundary.
The scanners never deploy, execute an image, use repository secrets or connect
to the Dell. No Aqua/Trivy action or image is used.

## Policy

| Finding | Gate |
| --- | --- |
| CISA KEV, matched by any CVE alias | Block, even without a fix |
| Critical with a fix | Block |
| High with a fix, introduced by the PR | Block immediately |
| Pre-existing High with a fix | Block 14 days after first seen |
| No fix; Medium, Low or Negligible | Report only (KEV still blocks) |
| Expired, malformed or over-length exception (Critical 30 / High 60 / other 90 days) | Fail |

The first-seen clock is carried in a compressed JSON comment on the single
**Supply-chain scan: open findings** issue, labelled `security`. Resolved keys
are retained so reappearing risk doesn't get another grace period. Repeated
identity strings are dictionary-coded losslessly so thousands of full SHA256
finding identities fit GitHub's single-issue limit; no key is shortened or
record dropped. Before that
issue exists, pre-existing pins use the baseline date 2026-10-13; new PR
introductions are immediate. A malformed existing issue state fails rather than
resetting the clock. When an existing issue has no record for a newly discovered finding, its
first-seen date is the current scan date, not the initial baseline anchor.
Only the security-labelled tracking issue created by the owner or GitHub
Actions is trusted; public issue impersonation fails instead of resetting dates.
Package changes are compared with a scan of the base
lockfile using the same current OSV data; an unchanged lockfile finding is not
treated as newly introduced just because a tooling change scans everything.

The issue shows artifact/package, vulnerability aliases, severity, fix state,
KEV membership, first-seen date and exception/gate outcome. Follow its run link
for full JSON/Markdown reports, per-image findings and CycloneDX SBOMs. Large
issue tables are bounded; first-seen state remains intact. The full artifact
retains the untruncated table. Database status and the downloaded KEV checksum
are logged with the report; scanners fail on operational errors.

## Inputs and integrity

Every entry in the bootstrap and application image locks is covered by a
Linux amd64 digest scan. Upstream registries are read directly; the placeholder
mirror is not a CI dependency. When the two `.build/dev-images` archives exist,
their pinned digest and complete OCI graph are verified before scanning.
Otherwise the report explicitly marks unpublished builds as **pinned inputs
only**: Python, CNPG PostgreSQL and pgvector. This fallback does not claim that
the complete unpublished application image was scanned.

OSV scans all tracked supported npm, pip, Go and other ecosystem lockfiles with
`--no-resolve`; hash-locked `.txt` files explicitly use the requirements parser.
Call analysis is off; no compiler or dependency build script executes.
Custom OCI/tool lock JSON is handled by image/tool inventory, not passed to OSV
as an unsupported ecosystem lockfile. Ignored caches and installed dependencies
are excluded.

Syft v1.52.0, Grype v0.119.0 and OSV-Scanner v2.6.0 are pinned in the CI tool
lock by release SHA256 and extracted binary SHA256, verified against official
checksum files. They are unmodified Apache-2.0 `build-tool` entries. Syft SBOMs
are cached under the input digest, platform and scanner hash, with document
integrity checks; a cache miss pulls the pinned image. Each scan attaches a
CycloneDX copy. SBOMs and database files are never committed. Grype updates its
database before matching; OSV uses current vulnerability responses.

The existing schema-source licence baseline hashes the whole CI tool lock.
WO-32 refreshes only that fingerprint for the added verified scanner entries;
every old artifact, schema URL/hash, baseline owner, reason and original
2027-01-07 deadline remain unchanged. Historical PR pins are untouched.

## Pull requests and scheduled jobs

The existing required **vCloud PR gate** includes `scan-pr`. Image lock,
receipt or lockfile changes scan selected inputs; policy/tool/workflow changes
scan the full inventory. No relevant change produces an explicit empty
selection, while exception validity is still checked. PR base commits are
immutable 40-hex SHAs. Scanner jobs have only `contents: read` and never run on
`pull_request_target`. All actions use full commit SHAs.

The scheduled workflow runs nightly at **02:30 UTC** and weekly on **Monday
03:00 UTC**. Manual dispatch selects `scan-nightly` or `watch-weekly`.
Issue-writing jobs have only `issues: write`, consume the artifact, and run a
stdlib-only reporter with no scanner. They run only on trusted `main`; scanner
errors cannot publish a fabricated success. The reporter creates or edits the
existing exact-title issue, never one issue per run, and refuses duplicates.
The issue writer creates the `security` issue label if absent, after merge.
The automatic GitHub token is used only by the reporter; no repository secret
is provided to scanners.

The weekly job compares current image/CI-tool findings with the newest
verifiable published stable release at least 14 days old. Candidate image
tags are resolved to digests before scanning. Candidate binaries are verified
data inputs, never executables. Missing publication evidence or an unavailable
artifact is reported as unavailable, never guessed or silently replaced by
`latest`. Twinfra-owned unpublished images have no independent upstream
release; their pinned input coverage remains explicit. The watch does not
edit locks or create PRs. Version changes require a later reviewed work order.

## Exceptions

Add a narrow entry to [vulnerability-exceptions.json](../security/vulnerability-exceptions.json)
using its [schema](../security/vulnerability-exceptions.schema.json): vulnerability
ID, exact artifact digest or lockfile, package/version, `severity`, named `owner`,
mitigation/removal reason, named `approvedBy`, `createdOn` and `expires`.
Maximum lifetime from `createdOn` is **30 days for Critical, 60 for High and
90 for other severities**, without automatic extensions. The gate rejects a
severity that differs from the matched finding. A fixable finding requires a
named `workOrder` (for example `WO-34`); its reason states the scanner's fix
version, dev exposure and remediation plan. This register uses individual
entries; grouped or wildcard Critical waivers are rejected. A changed
artifact/package version does not inherit the exception. Explain each approval
in PR review.

The first full PR scan produces `proposed-exceptions.json` for every blocking
finding, with `owner: amazen33`, `approvedBy: pending-owner`, and the severity's
maximum expiry from creation. The initial 99 Critical entries expire
**2026-11-12**. Each records its actual fix version from the saved Grype result,
LAN-only APIs and tunnel-only UI exposure, and remediation by `WO-34`.
Those proposals must be copied to the committed register and reviewed.
Pending approval is valid only on the owner repository's
`codex/wo-32-supply-chain-scanning` pull-request branch; forks, other branches,
pushes, schedules and dispatches reject it. The owner must replace
`pending-owner` after reviewing the reasons before merge. No blanket exception
admits new vulnerabilities or new versions.

## Run locally

Use Linux or WSL for scanning. Syft's registry layer cache cannot pull images
on Windows because of colon-containing filenames. Windows can run the offline
fixtures. This is tooling validation, not a provisioner or live lab command.

```bash
python -m pip install -r tools/ci/requirements.txt
python tools/ci/stage_tools.py --source . --destination .build/scan-tools --only syft grype osv-scanner
python tools/ci/supply_chain.py inventory --full
python tools/ci/supply_chain.py sbom --tools .build/scan-tools/bin
python tools/ci/supply_chain.py scan --tools .build/scan-tools/bin
python tools/ci/supply_chain.py evaluate
python tools/ci/supply_chain.py report
python -m unittest discover -s tools/ci/tests -p test_supply_chain.py -v
```

For changed-input coverage, use `inventory --base <full-base-SHA>` instead of
`--full`. `watch --tools .build/scan-tools/bin` performs the weekly comparison
without publishing. `report --publish` is reserved for the trusted main-only
issue writer. Local pending-owner proposals do not bypass the gate.

## After-merge acceptance (Pending)

Dispatch `scan-nightly` on `main` twice. Record that both runs update the same
open-findings issue number. Dispatch `watch-weekly` on `main` and record its
single **Upstream updates available** issue. These GitHub issue mutations are
after-merge acceptance; this static PR does not execute them or change settings.

# Supply-chain image-reference validation

[WO-31 Amendments 13–13b](work-orders/WO-31-bare-metal-cairo-1.md) govern the
[image-reference guard](../tools/platform_image_references.py). It renders
locally with the existing Bash, Helm and Kustomize tools; it never provisions,
pulls, stages, applies or connects to the dev host.

| Scope | Lock and rule | Result |
| --- | --- | --- |
| A: dev platform/services workloads in every rendered region | `deploy/common/images.lock.json`; canonical repository plus the locked digest, optionally retaining a tag | Blocking |
| B: dev bootstrap/system images | `deploy/common/bootstrap-images.lock.json`; digest references, with the closed kubeadm/containerd tag allowance below | Blocking |
| C: production cloud-init/profile renders | The same resolution rules; print dated production debt and preserve existing production references | Report-only warning |

The guard checks container, init and ephemeral images, CR image fields
including Cluster/ImageCatalog/ClusterImageCatalog/Pooler, and literal env
values whose names contain `IMAGE`. Missing or indirect IMAGE env values cannot
prove lock resolution and fail in dev. CRD schema declarations are field
definitions; the instances that use those fields are checked. Kustomize builds
every existing dev platform/services overlay; cairo-2 currently has only a seed.
The real CI kubeadm dry-run also checks its four actual generated static Pods.

CNPG's operator setting takes version `1.30.1` from the checksum-verified vendor
manifest and the repository/digest from `images.lock.json`. Its generated init
containers therefore use the existing pinned CRI digest record. The vendor,
image locks and image content are unchanged. The owner-only stuck initdb Job
recovery is documented in the [dev runbook](dev-environment.md).

## Closed bootstrap tag allowance

`BOOTSTRAP_TAG_ALLOWLIST` is a constant with exactly these renderer/object/ref
bindings. Each reference must also equal a canonical name in the bootstrap lock,
which the existing staging step stages and digest-verifies before kubeadm init.
An ADR or work-order amendment is required to add a binding. A Helm-installed
image cannot use this allowance, even if its tag appears in an image lock.

| Renderer and object | Approved canonical tag |
| --- | --- |
| kubeadm Pod/kube-apiserver | `registry.twinfra.example.com/registry.k8s.io/kube-apiserver:v1.36.5` |
| kubeadm Pod/kube-controller-manager | `registry.twinfra.example.com/registry.k8s.io/kube-controller-manager:v1.36.5` |
| kubeadm Pod/kube-scheduler | `registry.twinfra.example.com/registry.k8s.io/kube-scheduler:v1.36.5` |
| kubeadm Pod/etcd | `registry.twinfra.example.com/registry.k8s.io/etcd:3.6.8-0` |
| kubeadm Deployment/coredns | `registry.twinfra.example.com/registry.k8s.io/coredns:v1.14.2` |
| containerd sandbox_image (1.x) / pinned_images.sandbox (2.x) | `registry.twinfra.example.com/registry.k8s.io/pause:3.10.1` |
| kubeadm pause image | `registry.twinfra.example.com/registry.k8s.io/pause:3.10.2` |

The guard checks both dev regions, both containerd config generations, and the
checksum-verified kubeadm version constants. Cilium remains digest-pinned.
The unused `DaemonSet/nvidia-device-plugin-mps-control-daemon` is removed just
as Module -1's existing filter removes it; the production device-plugin
DaemonSet is still reported. No unused runtime object gets a blanket waiver.

## Production follow-up

Scope C remains debt for a separate work order: Stage C registry names under
ADR-0036, an NVIDIA digest lock or an approved `operator-pulled` record under
ADR-0044, and the production smoke image references. No production references,
locks or digests change in this PR. The snapshot below comes from the offline
production renderer, including conditional NVIDIA and CPU smoke templates;
it is not a live production inventory. Both production cloud-init files and
the shared bootstrap remain byte-identical. There is no production CNPG
Deployment in the current profile to patch.

## Run the static guard

```bash
python tools/platform_image_references.py --bash bash --helm helm --kustomize kustomize \
  --nvidia-chart .build/ci-tools/nvidia-device-plugin-0.20.1.tgz --out .build/image-references
python -m unittest discover -s tests -p test_image_references.py -v
```

The existing licensed CI tools must already be staged. The required PR gate
records JSON and dated text/Markdown under `image-references/`, alongside the
real kubeadm preview and its production debt report. Historical revisions
without this guard keep their original tests; candidate controls enforce the
actual dev kubeadm preview on all seven matrix jobs. New incomplete guard
bundles fail instead of silently disappearing from the matrix.

<!-- BEGIN GENERATED PRODUCTION IMAGE DEBT -->
## Production image-reference debt

Snapshot: 2026-10-14. Report-only scope C; no production references changed.

Input sources: `production`, `user-data-remote.yaml`, `user-data.yaml`.

| Consumers | Reference | Finding |
| --- | --- | --- |
| Job/allowed, Job/denied, Pod/server | registry.vcloud.example.com/docker.io/library/busybox:1.37.0 | Missing/invalid digest or tag-only reference outside the closed bootstrap allowance |
| Job/hugepages | registry.vcloud.example.com/docker.io/library/python:3.12.12-slim | Missing/invalid digest or tag-only reference outside the closed bootstrap allowance |
| DaemonSet/nvidia-device-plugin | registry.vcloud.example.com/nvcr.io/nvidia/k8s-device-plugin:v0.20.1 | Missing/invalid digest or tag-only reference outside the closed bootstrap allowance |
| DaemonSet/cilium-envoy | registry.vcloud.example.com/quay.io/cilium/cilium-envoy:v1.37.6-1789133542-cbec91f666af0bf742da986d43832932dbb26b82@sha256:af7382699576b9e65e9184efa52eeca0b58aea70ad6e511bf260c91d9f740463 | Repository/digest does not resolve to this scope lock |
| DaemonSet/cilium | registry.vcloud.example.com/quay.io/cilium/cilium:v1.20.2@sha256:2939231d0d3e3ebddcd80fffa168b7ddcc78fdf0dc864d1c8c126ff523c54f01 | Repository/digest does not resolve to this scope lock |
| Deployment/cilium-operator | registry.vcloud.example.com/quay.io/cilium/operator-generic:v1.20.2@sha256:64d8798350e8569b8e7622563fed6e44dce2625f311e4651b774816516c744fc | Repository/digest does not resolve to this scope lock |
| Deployment/coredns | registry.vcloud.example.com/registry.k8s.io/coredns:v1.14.2 | Missing/invalid digest or tag-only reference outside the closed bootstrap allowance |
| Pod/etcd | registry.vcloud.example.com/registry.k8s.io/etcd:3.6.8-0 | Missing/invalid digest or tag-only reference outside the closed bootstrap allowance |
| Pod/kube-apiserver | registry.vcloud.example.com/registry.k8s.io/kube-apiserver:v1.36.5 | Missing/invalid digest or tag-only reference outside the closed bootstrap allowance |
| Pod/kube-controller-manager | registry.vcloud.example.com/registry.k8s.io/kube-controller-manager:v1.36.5 | Missing/invalid digest or tag-only reference outside the closed bootstrap allowance |
| Pod/kube-scheduler | registry.vcloud.example.com/registry.k8s.io/kube-scheduler:v1.36.5 | Missing/invalid digest or tag-only reference outside the closed bootstrap allowance |
| ContainerRuntimeConfiguration/containerd | registry.vcloud.example.com/registry.k8s.io/pause:3.10.1 | Missing/invalid digest or tag-only reference outside the closed bootstrap allowance |
| RuntimeImage/pause | registry.vcloud.example.com/registry.k8s.io/pause:3.10.2 | Missing/invalid digest or tag-only reference outside the closed bootstrap allowance |

<!-- END GENERATED PRODUCTION IMAGE DEBT -->

## Identity continuity (WO-34 Amendment 3a)

A digest change selects an image for scanning. A finding is introduced only when
its component, package and vulnerability identity was absent from that component's
previous pin. Candidate and previous images are scanned against one fresh Grype
database. A different component cannot supply its baseline. Critical findings with
a fix always require an exact target/package/version/vulnerability exception.

The issue keeps digest-independent component clock records in its existing lossless
format. The initial nightly migration resolves historical targets through the
same component's Git lock history and uses the trusted issue's original dates.
It does not reset the High clock or change first-seen for newly discovered risk.

P2 carries six existing approvals, with unchanged reasons, approvers and November 12
expiry, and closes 16 fixed Critical entries. GO-2026-6612 remains separately recorded
for x/net and stdlib in each candidate, with explicit compensating controls.
[Promotion evidence and maintenance](image-patch-refresh-p2.md). No exception is
renewed here; individual renewal proposals remain a separate owner review.
