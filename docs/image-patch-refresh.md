# WO-34 image patch refresh

The [approved work order](work-orders/WO-34-image-patch-refresh.md) controls
release selection, digest pinning, exception closure and owner live acceptance.
No staging, upgrade or rollout is authorized by this static PR.

## Static preparation and current stop (2026-10-14)

Main was updated to `b55c0ea`; WO-32 was merged as `140c04d`.
The first priority remains in progress. [PR #55](https://github.com/amazen33/twinfra/pull/55)
is a draft and must not be merged or deployed as a completed refresh.

The pinned BSD-3-Clause govulncheck v1.1.4 build uses Go 1.27.1 and SHA256-locked
SDK/module inputs. Its Linux binary SHA256 is
`f77f577722ac825bf649c24023c24af64e44c77152ab4e1778b2f8a27c2011fb`.
Windows Application Control blocked the local Go linker; laptop policy was not
changed. The disposable Linux runner reproduced the binary. Discovery never ran
the scanner; the recorded hash is verified before binary analysis.

[Run 38592818563](https://github.com/amazen33/twinfra/actions/runs/38592818563)
extracted `/usr/local/bin/argocd` from the pinned Argo CD image
`quay.io/argoproj/argocd@sha256:dd3f47d5a5e4da563a7a398506e892481b358a7cec50abdf320c71aa55904bfa`.
The extracted binary SHA256 is
`e557da422ff52a729989e3d631bcc171b3f6e925631c157306c1724228e8f8f9`.
It was read as data, never executed. govulncheck ran with `-mode=binary -json`.

For [GO-2026-6612 / CVE-2026-78663](https://pkg.go.dev/vuln/GO-2026-6612),
the output contains affected `golang.org/x/net/http2` symbols (for example
`Framer.WriteSettingsAck`) at x/net v0.56.0, fixed in v0.60.0; it also contains
affected `net/http` symbols at stdlib v1.26.4, fixed in v1.26.9.
Binary analysis establishes symbol presence, not a runtime call graph. Under
WO-34 these potential paths are conservatively blocking; they are not recorded
as "not reachable" or accepted under another exception.

The other Argo CD image executables (`helm`, `kustomize`, `git-lfs`, `pebble`) and
other images have not yet received complete binary triage. Absence from the one
inspected binary is not evidence that a vulnerability is absent from the image.

| Argo CD patch | Upstream publication | 14-day status on 2026-10-14 |
| --- | --- | --- |
| [3.5.3](https://github.com/argoproj/argo-cd/releases/tag/v3.5.3) | 2026-09-14 | Eligible; currently pinned; affected symbols found |
| [3.5.4](https://github.com/argoproj/argo-cd/releases/tag/v3.5.4) | 2026-10-06 | Ineligible until 2026-10-20; patch coverage still requires verification |
| [3.5.5](https://github.com/argoproj/argo-cd/releases/tag/v3.5.5) | 2026-10-12 | Ineligible until 2026-10-26; patch coverage still requires verification |

The current CISA KEV catalog `2026.10.13` contains no match for this CVE. A Critical
rating alone does not meet the work order's expedite condition. No qualifying
vendor statement of active exploitation has been established. No waiver is used.
Argo CD 3.5.4 also documents changed `helmGlobals.configHome` handling and a 4 MiB
OCI-manifest limit; those changes require compatibility review before selection.

**Stop:** the newest age-eligible Argo CD patch is the affected current pin.
Reachable/potentially reachable findings cannot retain an exception under WO-34.
Proceed only when an eligible compatible patch is verified, or when the owner
records an expedite waiver backed by the required KEV/vendor evidence. The
vulnerability exception register has not been changed or extended.

## Priority 1 candidate (not promoted)

The owner delegated the age-rule recommendation. Python selection uses the
[CPython 3.14.8 release date](https://www.python.org/downloads/release/python-3148/),
2026-09-30, which is 14 days old. The selected Docker digest was published
2026-10-09. Both dates must remain in the final receipt; this is not an expedite
waiver. The base remains on Python 3.14 and Debian trixie.

An uncommitted local console candidate rebuilt as
`sha256:ec1eebc9b51a1e7e019b501039f8c822eee5751b6322b205ec0b5eea9f30cd54`.
Its base is
`python:3.14.8-slim-trixie@sha256:a2b82f3c48559aa0a8446d9af49826b6e2b2016f4cd2afabfe6013ec53729170`.
The title label and application history say `twinfra-console`; builder names use
`registry.twinfra.example.com`. Application source hashes are unchanged.
The PostgreSQL image digest remains
`sha256:baea2bf7f829393ef2d43eae67242fed561f8532fbb1a7c6bbdbacf583a643f6`.

The candidate receipts/renders are preserved locally for continuation. Full
Linux before/after scans, zero fixable Critical acceptance, exception closures,
schema/render checks and owner digest approval remain Pending. Native Windows
OCI scans cannot supply the acceptance evidence because Syft's layer cache uses
colon-containing names. Preliminary regular-file inventory is not promoted as a
complete image scan or legal SBOM review.

| Changed-image candidate | Before: Critical with/without fix | After: Critical with/without fix | Before/after: High with/without fix |
| --- | --- | --- | --- |
| Twinfra console | Pending complete image scan | Pending | Pending |
| Shared Python base | Pending comparable complete scan | Pending | Pending |

## Owner live actions after static acceptance

Keep the [dev runbook](dev-environment.md) as the execution procedure. After
all priorities pass CI, Claude reviews and the owner approves the new digests:

1. Fetch the reviewed main revision, build both locked archives with
   `python tools/platform_dev.py build-images --download-inputs`, and verify the
   returned digests against the committed receipts and image locks.
2. Stage through the existing owner-only `stage-images` procedure in the dev
   runbook; check the staged canonical digest records before any rollout.
3. If the refreshed Kubernetes 1.36 patch differs from the host version, follow
   the upstream `kubeadm upgrade plan`, reviewed `kubeadm upgrade apply` and
   matching kubelet/kubectl package upgrade procedure. Never re-run init/reset,
   skip a minor version, or upgrade when the reviewed patch is unchanged.
4. Verify Running/Ready pods, Argo CD Synced/Healthy, PostgreSQL persistence,
   trusted HTTPS endpoints and the next nightly vulnerability report. The tester
   records dated acceptance in the dev receipt.

All of these live steps remain Pending. Do not stage the local candidate above.
