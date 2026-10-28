# R12: October security wave review

**Activated:** Ahmed Mazen approved O-2/O-4b/O-5 on 2026-10-29 (Africa/Cairo) for the exact batch at `86d4318`. The active registry contains 420 approved rows. Three carry approvals preserve the original deadlines. See the [owner decision record](../../security/security-wave-2026-10-approval.json) for immutable proposal/log hashes, the UTC recording time and the separate owner decision date. Gate approvalDate uses the actual UTC recording date; no future date or gate exception is introduced. Local re-evaluation of the full final PR scan passes with zero blockers. CI is rerun independently; staging, merge and live acceptance remain Pending.

**The proposal review snapshot below is preserved for audit. Its references to pending batch approval describe the pre-activation state at `86d4318`, not the current active approval. Original proposed JSON remains unchanged with blank approval fields; the active [exception registry](../../security/vulnerability-exceptions.json) differs only by approvedBy.**


Static work only. Owner batch approval, staging, merge and live acceptance are Pending. No image was rebuilt or run.

Authority: [WO-40 Amendments 10–10c](../work-orders/WO-40-twinfra-v0-1-0-release.md), [ADR-0054 Amendment 1](../adr/amendments/0054-amendment-1-security-fix-carry-forward.md) and [WO-46](../work-orders/WO-46-post-release-image-refresh-wave.md).

## Full scan and per-image disposition

[Baseline scan](https://github.com/amazen33/twinfra/actions/runs/40659063932): 2,178 findings, 374 blocked. [Candidate full scan](https://github.com/amazen33/twinfra/actions/runs/40767198838): 2,004 findings, 374 blocked before owner approval. The raw blocked total is unchanged because 22 retained Criticals in the new Argo CD digest no longer match the old-digest approvals. The promotions and lockfile fixes remove 22 previously blocking records. No gate or grace period changed.

The 420 proposed rows cover all 374 current blockers plus 46 other in-scope image findings: 59 individual Critical renewals (2026-11-27), 360 High rows (2026-12-27), one Medium KEV (2026-11-24). 270 rows qualify as toolchain-wave; 149 use the normal route; the KEV uses WO-40 Amendment 10b. Exact package/version/advisory matching remains mandatory; normal Highs are grouped by image/package in the review ledger only.

| Image or lockfile | Blocking before | Closed blocking | Raw blocking after | Proposed rows | Remaining if approved |
| --- | ---: | ---: | ---: | ---: | ---: |
| docker.io/apache/apisix | 8 | 0 | 8 | 13 | 0 |
| docker.io/ministackorg/ministack | 5 | 5 | 0 | 0 | 0 |
| docker.io/openbao/openbao | 14 | 0 | 14 | 18 | 0 |
| docker.io/valkey/valkey | 1 | 0 | 1 | 1 | 0 |
| ghcr.io/cloudnative-pg/cloudnative-pg | 13 | 0 | 13 | 16 | 0 |
| lockfile:module-5a/requirements-runtime.lock.txt | 1 | 1 | 0 | 0 | 0 |
| lockfile:tools/ci/mermaid/package-lock.json | 1 | 1 | 0 | 0 | 0 |
| lockfile:tools/ci/rag-requirements.txt | 1 | 1 | 0 | 0 | 0 |
| quay.io/argoproj/argocd | 149 | 7 | 164 | 167 | 0 |
| quay.io/cilium/cilium | 37 | 0 | 37 | 43 | 0 |
| quay.io/cilium/cilium-envoy | 15 | 0 | 15 | 18 | 0 |
| quay.io/cilium/operator-generic | 19 | 0 | 19 | 24 | 0 |
| quay.io/keycloak/keycloak | 7 | 7 | 0 | 1 | 0 |
| registry.k8s.io/coredns/coredns | 22 | 0 | 22 | 25 | 0 |
| registry.k8s.io/etcd | 15 | 0 | 15 | 19 | 0 |
| registry.k8s.io/kube-apiserver | 22 | 0 | 22 | 25 | 0 |
| registry.k8s.io/kube-controller-manager | 22 | 0 | 22 | 25 | 0 |
| registry.k8s.io/kube-scheduler | 22 | 0 | 22 | 25 | 0 |

Conditional evaluation of an in-memory owner-approved test fixture passes with zero blockers. **This is not an active gate pass or owner approval.** The active registry closes three fixed exceptions but retains 59 prior Critical approvals until the owner authorizes their individual replacements. Every proposed `approvedBy` is empty.

See the [complete High and Critical ledger](security-wave-2026-10-ledger.md), [machine-readable review](../../security/security-wave-2026-10-review.json) and [exact proposed replacement registry](../../security/proposals/r12-vulnerability-exceptions.json).

## Candidate comparisons and immutable pins

[Data-only comparison run](https://github.com/amazen33/twinfra/actions/runs/40754061462): complete Linux amd64 OCI graphs; pinned Syft/Grype and binary-mode govulncheck; no image execution. User, entrypoint, command and working-directory contracts are unchanged. Counts below are fixable Critical/High records, not the full nightly gate totals.

| Candidate | Before C/H | After C/H | Closed package/advisory identities | Introduced | Decision |
| --- | --- | --- | ---: | ---: | --- |
| Argo CD 3.5.5 | 23/152 | 22/144 | 9 | 0 | Promote; eligible 2026-10-26 |
| Argo CD 3.5.6 | 23/152 | 22/143 | 10 | 0 | Do not promote; KEV remains, no expedite |
| MiniStack 1.5.33 | 3/6 | 0/0 | 9 | 0 | KEV expedite; O-1 |
| Keycloak 26.8.1 | 1/7 | 0/1 | 7 | 0 | Promote; O-1 |

Keycloak carries the same Guava 33.6.0-jre / CVE-2026-102554 High as 26.8.0 (fix 33.7.2). Its CA Critical is cleared, so no CA-bundle exception is needed. The checked-in realm has no external identity providers, user federation or external SMTP; the unchanged dev network policy permits internal database/DNS only.

- argocd: `registry.twinfra.example.com/quay.io/argoproj/argocd@sha256:13db7b10db23283b1b36f855046602e18539a8a8204c9f6f039e8896c8897518`.
- ministack: `registry.twinfra.example.com/docker.io/ministackorg/ministack@sha256:b58186186515a372798ccf0ca9975c295db219b5a811975337d6967b968e07b4`.
- keycloak: `registry.twinfra.example.com/quay.io/keycloak/keycloak@sha256:a78d6b79572168cb25886b80a8b5b8d4ed4390743e3eecb810538683e209dd6b`.

O-1 (owner, 2026-10-28) waives cooling-off for certifi 2026.10.23 in both specified Python locks and DOMPurify 3.4.17 in the Mermaid lock. Exact hashes and primary licence evidence are generated in the security-wave dependency/carry records. No other image pin, locally built image, console source, production render or bootstrap lock changes.

## O-5 security-fix licence carries

| Component | Old → new | Tier unchanged | Original backfill due | Advisories cleared |
| --- | --- | ---: | --- | --- |
| MiniStack | 1.5.17 → 1.5.33 | 1 | 2027-04-16 | CVE-2026-111497; GHSA-6q48-6c7w-9gw2 |
| certifi | 2026.7.22 → 2026.10.23 | 3 | 2027-01-14 | GHSA-6q48-6c7w-9gw2 |
| DOMPurify | 3.4.16 → 3.4.17 | 3 | 2027-01-14 | CVE-2026-116804 |

The [append-only carry log](../../security/licence-carry-log.json) anchors the original approvals to main `0d95007`. The current map records `carriedFrom`, exact-version primary licence SHA-256, cleared advisories and O-5 authorization date. `approvalDate` and `approvedBy` await the PR batch decision. Second carries cannot move the original deadline. No class, tier or OR-expression logic changes. Argo CD and Keycloak have full new Apache-2.0 qualification records; their supply-chain criteria remain Pending until the vulnerability batch is approved and the gate passes.

## Argo CD brotli KEV: O-4b decision required

**CVE-2026-111497 / libbrotli1 1.2.0-3build1: one individual row, expected merge 2026-10-30, expiry 2026-11-24.** Recompute merge + 25 days if the merge date changes. The architect checkpoint is 2026-11-13. WO-46 must promote the first fixing upstream image immediately under the KEV expedite rule.

The complete Syft ELF metadata identifies `/usr/lib/x86_64-linux-gnu/libcurl-gnutls.so.4.8.0` as the direct `libbrotlidec.so.1` importer. Git HTTP fetch/push, imap-send and remote-http helpers import libcurl. The repo-server uses Git HTTP helpers ([pinned git execution source](https://github.com/argoproj/argo-cd/blob/v3.5.5/util/git/client.go)). The Go argocd, helm, kustomize, git-lfs and pebble ELFs do not import that system library. The amendment’s expected Helm/libcurl path is corrected by this evidence: [Helm is executed as a Go binary](https://github.com/argoproj/argo-cd/blob/v3.5.5/util/helm/cmd.go). This is potential reachability, not an exploit test or a non-reachability assertion.

The policies are unchanged from main `0d95007`: `twinfra-argocd-repo-server-network` allows external egress only to github.com TCP 443 (plus internal DNS and Valkey); `twinfra-argocd-server-network` ingress allows host/remote-node/health TCP 8080 only. Controller and server egress is internal DNS, repo-server, Valkey and the Kubernetes API. Argo Services are ClusterIP; there is no APISIX route, host port or host-network exposure. This is static intent, not live Cilium enforcement evidence. A DNS/FQDN policy is not cryptographic proof of GitHub origin.

AppProject `sourceRepos` is only `https://github.com/amazen33/twinfra.git`. Active dev Applications use local Git paths; there are no active OCI sources, Jsonnet sources or remote Kustomize bases. No `helmGlobals.configHome` is configured. Thus the OCI >4 MiB compatibility case is not used by this profile. Every dev Application retains `ServerSideDiff=true,IncludeMutationWebhook=true`; Server-Side Diff does not run on initial creation.

## Calendar and newly observed grace-period risk

Every proposed expiry is beyond seven days throughout 2026-10-30–2026-11-16. The closest expiry on November 16 is November 24 (eight days). Active old approvals are not extended by this report; the owner must authorize and activate the exact proposed replacements before merge.

| Date | Nearest expiry (days) | Expired | Within seven days |
| --- | ---: | ---: | ---: |
| 2026-10-30 | 25 | 0 | 0 |
| 2026-10-31 | 24 | 0 | 0 |
| 2026-11-01 | 23 | 0 | 0 |
| 2026-11-02 | 22 | 0 | 0 |
| 2026-11-03 | 21 | 0 | 0 |
| 2026-11-04 | 20 | 0 | 0 |
| 2026-11-05 | 19 | 0 | 0 |
| 2026-11-06 | 18 | 0 | 0 |
| 2026-11-07 | 17 | 0 | 0 |
| 2026-11-08 | 16 | 0 | 0 |
| 2026-11-09 | 15 | 0 | 0 |
| 2026-11-10 | 14 | 0 | 0 |
| 2026-11-11 | 13 | 0 | 0 |
| 2026-11-12 | 12 | 0 | 0 |
| 2026-11-13 | 11 | 0 | 0 |
| 2026-11-14 | 10 | 0 | 0 |
| 2026-11-15 | 9 | 0 | 0 |
| 2026-11-16 | 8 | 0 | 0 |

Six lockfile Highs are not currently blocking and are outside R12’s image-exception scope. They must not be mistaken for approved exceptions. The dates below use the unchanged first-seen clock plus 14 days; they can block subsequent scans during the release window. The owner/architect must assign a fix or separate approval.

| Lockfile | Package/version | Advisory | Scanner fixed versions | Blocks from |
| --- | --- | --- | --- | --- |
| lockfile:console/package-lock.json | undici 8.11.2 | CVE-2026-109383 | 6.29.1, 7.30.1, 8.12.2 | 2026-11-11 |
| lockfile:console/package-lock.json | undici 8.11.2 | CVE-2026-109829 | 7.30.1, 8.12.2 | 2026-11-11 |
| lockfile:console/package-lock.json | undici 8.11.2 | CVE-2026-109869 | 6.29.1, 7.30.1, 8.12.2 | 2026-11-07 |
| lockfile:console/package-lock.json | undici 8.11.2 | CVE-2026-87018 | 6.29.1, 7.30.1, 8.12.2 | 2026-11-11 |
| lockfile:module-5a/requirements-runtime.lock.txt | filelock 4.0.12 | CVE-2026-112940 | 4.2.1 | 2026-11-07 |
| lockfile:tools/ci/mermaid/package-lock.json | lodash-es 4.17.21 | CVE-2026-4800 | 4.18.0 | 2026-10-31 |

## Owner execution order

1. Claude reviews this PR. Owner O-2 approves the exact exception batch; O-4b confirms the KEV term; O-5 approves each named carry. Implementer records those decisions without changing their due dates, reruns all gates and reports CI. No pending proposal authorizes merge.
2. Before merge, use the reviewed PR branch in the existing operator checkout with its existing verified console/PostgreSQL archives. No rebuild is part of R12. Check the context and retrieve digests from the current lock:

```powershell
python -c "import json; from pathlib import Path; d=json.loads(Path('deploy/common/images.lock.json').read_text())['images']; print('\n'.join(k+': '+d[k]['canonical'] for k in ('argocd','ministack','keycloak')))"
```

Expected: exactly the three approved candidate digests above. Any disagreement stops staging.

```powershell
python tools/platform_dev.py stage-images --context twinfra-dev-cairo-1 --ssh twinfra-operator@192.168.1.3 --archive-dir .build/dev-images
```

Expected: all application images verified; no running workload changed by staging.

```powershell
python tools/platform_dev.py stage-images --context twinfra-dev-cairo-1 --ssh twinfra-operator@192.168.1.3 --check
```

Expected: PASS, canonical CRI digests and pinned labels. Only after that check succeeds, the owner adds `Staging: PASS (stage-images --check, YYYY-MM-DD)` with the actual UTC date to the PR. Never invent that attestation.

3. Owner merges after every required check passes; Argo CD then reconciles the approved images, including its own Deployment/StatefulSet. Observe rollout and all three Applications Synced/Healthy before acceptance. Do not rerun bootstrap, init or reset.
4. In the existing owner live checkout, run the owner-maintained acceptance wrapper (not a tracked repository script):

```powershell
.\run-acceptance.ps1 -WithRestart
```

Expected: every acceptance check passes, Valkey reconnects, and a new owner receipt is created outside existing signed receipts. If the wrapper is missing, stop and recover the owner’s existing setup; do not invent credentials or bypass checks. No receipt is edited by this PR.

5. WO-46 follows each upstream fixed-image release. The [primary release metadata](../../security/security-wave-2026-10-upstream.json) records exact publication/eligibility instants. Kubernetes 1.36.6 is eligible November 11; Cilium 1.20.4 November 6; etcd 3.6.16 November 5; OpenBao 2.7.2 and Valkey 8.1.11 November 9. These are remediation candidates: unscanned future images are not claimed fixed. No eligible same-line fix is verified for CoreDNS/CNPG/APISIX/Guava. WO-46 must verify the relevant fixed packages before promoting; a missing fix remains a tracked individual risk.

## Validation status

CI run links and final results are reported in PR #82. The required gate remains blocked until the owner approval batch and real staging attestation exist. Static validation is separate from live acceptance. Local Windows cannot execute the Linux-only shell/systemd/CRI fixture suites faithfully; the six historical Linux legs remain required.
