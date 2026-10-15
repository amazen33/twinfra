# WO-34 P3: MiniStack and dev pause patches

Static only. No Dell connection, image execution, staging, runtime restart or
GitHub settings change. This PR is stacked on PR #55; merge P1 first, then rebase
and retarget this PR to main. Live acceptance and tester sign-off remain Pending.

## Reviewed pins and compatibility

- MiniStack candidate 1.5.18 is **stopped**; the deployed pin stays 1.5.17. Candidate digest
  `sha256:451a0cc80a4f464e1c2d2f77fbb40ac37d01902d58ca3630ac5eaea9c92f12da`.
  The [release](https://github.com/ministackorg/ministack/releases/tag/v1.5.18)
  was published 2026-09-28T22:29:28Z and its official Docker digest
  2026-09-28T22:44:59.959202Z; eligible 2026-10-12. Entrypoint, command, user,
  working directory and environment (except the version string) match the old
  image. The restricted non-root Pod configuration and API-only backend remain
  unchanged. AUTH stays at its existing setting; no Docker socket is provided
  for optional execution features. The MIT licence was verified at the tag, but the candidate is not registered as a deployable component because promotion is stopped.
- Dev containerd pause 3.10.1 → 3.10.2, digest
  `sha256:f548e0e8e3dc1896ca956272154dde3314e8cc4fde0a57577ee9fa1c63f5baf4`.
  This is the already registered and staged kubeadm v1.36.5 pause pin. Both dev
  regions now set the same canonical `pause:3.10.2` sandbox reference. Duplicate
  lock keys alias one canonical object; staging verifies every key and the CRI
  digest. The old production/default alias is retained as reference-only
  metadata, excluded from dev staging. Production/default renders and WSL stay
  byte-identical; no control-plane version changes or kubeadm upgrade occur.

Complete before/after Linux amd64 OCI scans use one fresh Grype database and
govulncheck on every Go ELF, without executing image code. The first complete comparison finished; only pause is selected for the static pin refresh. Required candidate/historical gate results are linked in the PR. The P3 comparison fails if a
candidate has a fixable Critical or High finding. The existing MiniStack CVE-2026-19445 exception remains unchanged; pause has no existing vulnerability exception. No approval is transferred to a new digest.

## Other P3 components

Kubernetes 1.36.5, Cilium 1.20.2, CNPG 1.30.1, APISIX 3.19.0 and Valkey 8.1.10
remain on the newest verified published patch within their approved minor.
OpenBao 2.6.4 becomes age-eligible 2026-10-15 and still has affected Go symbols;
no promotion or new exception is made. CoreDNS/etcd and Argo CD are handled in
P2 with the source-mode/net-improvement gates from Amendment 2.

The CI-only npm updates stop at the compatibility boundary: Mermaid 11.12.3
introduces a parser major/dependency minor jump; lodash 4.17.23 still has a High
finding needing 4.18.x, and the available Mermaid/KaTeX advisory fixes leave
their pinned minors. No npm pins change. No minor upgrade or expedite is used.

## Owner procedure after review

1. Merge P1 before P3; obtain Claude review and owner digest approval. Fetch
   reviewed main and follow the existing [dev staging runbook](dev-environment.md).
   Verify the retained MiniStack canonical digest and `pause:3.10.2` in CRI before a
   rollout. Existing pause 3.10.2 may already be staged under the kubeadm alias;
   verification remains mandatory. Keep the owner’s root-owned config and
   bootstrap inventories aligned with the reviewed dev output.
2. For the existing dev host, changing CRI sandbox configuration is an owner
   maintenance action. Use the shared `render_containerd` function from the
   reviewed Module -1 script with the updated dev env, and validate the rendered
   config with the installed containerd. Inspect its diff before installing:
   only the runtime pause reference may change. Preserve systemd cgroups,
   mirror-only resolution and all runtime options. Keep a copy of the old config;
   schedule and approve a containerd restart. Do not use init/reset or a full
   bootstrap to apply this one runtime setting. Existing sandboxes retain their
   image until replacement; verify a newly created sandbox when the owner tests.
3. Validate S3/EC2/DynamoDB reads, APISIX routing, GitOps health, node readiness
   and the nightly scan. On regression, stop the rollout and have the owner
   choose a reviewed response. No automatic image fallback is implemented.
4. Critical exceptions without a fix or validated not-reachable evidence are
   already flagged for owner review **by 2026-11-05**, before **2026-11-12**.
   No exception expiry is changed by P3.

## Completed candidate scans

[Complete OCI scan run](https://github.com/amazen33/twinfra/actions/runs/38631598894) used one fresh database and inspected every Go ELF as data (none present in these four images). The initial comparison correctly rejected MiniStack and was not bypassed. The generator restored only that blocked app pin; the next gate enforces the actual selected pause image.

| Image | Critical with fix | Critical without fix | High with fix | High without fix |
| --- | ---: | ---: | ---: | ---: |
| MiniStack 1.5.17 | 1 | 0 | 3 | 12 |
| MiniStack 1.5.18 | 1 | 0 | 3 | 12 |
| pause 3.10.1 | 0 | 0 | 0 | 0 |
| pause 3.10.2 | 0 | 0 | 0 | 0 |

MiniStack still bundles Python 3.13.15 (Critical CVE-2026-19445, fixed 3.13.16), two fixable High Python findings and zlib 1.3.2-r0 (High CVE-2026-85091, fixed r1). It is not a net improvement. No eligible fixed MiniStack patch has been verified. 1.5.19's software release reaches 14 days at **2026-10-14T22:16:48Z**, but it is not declared fixed or eligible for promotion without its own complete scan and compatibility review. No self-built replacement image is made.
