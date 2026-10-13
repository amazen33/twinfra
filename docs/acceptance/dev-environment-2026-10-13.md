# WO-31 Amendments 7–9a acceptance · 2026-10-13

Environment: `twinfra-dev-cairo-1` on the Dell.
Work order: [WO-31 Amendments 7–9a](../work-orders/WO-31-bare-metal-cairo-1.md).
Decision: [ADR-0048](../adr/0048-cairo-1-on-bare-metal-host.md).

## Static scope

Generated checker input normalization, offline CLI fixtures, generator checks,
strict render-byte bounds against merged main `1f7d86f`, licence gate and the
candidate/six historical CI baselines. No Dell connection, bootstrap, reboot,
VM, live environment, IOT-EE or GitHub-settings change is authorized or executed
in this implementation task.

The source fix is confined to `tools/manifest_contract.py`'s `main()` and embedded
through the SSoT/Cloud-Init/dev generators. Production output changes only in
the generated checker block and derived script checksums/gzip; cairo-2 embeds
the same checker. Callers and `flatten()` remain unchanged. Non-object entries,
including nested List items, become violations with exit 1. The real chart
fixture is the pinned Cilium Helm render relocated to the dev registry; no
live Pod or DaemonSet data was fetched. Approved node-agent mounts still pass
and mount drift still fails. No new components or licence-policy changes.

Amendment 8 is confined to seven explicit return-status lines in the shared
bootstrap, plus derived render checksums/gzip, enforced against merged main
`24b8bdb`. Four intentional skips return 0; staging completion and the two main
dispatch exits preserve status with `return $?`. The production-options/ERR-trap
tests exercise the real main tail with smoke off/on and bootstrap off; a genuine
mocked smoke error still fails. A static rule bans status-less returns. Earlier
Amendment 7 source/render evidence retains its frozen merged revision.

Amendments 9–9a build the existing console and PostgreSQL images without WSL,
using an anonymous checksum-verified Docker Hub export and existing vetted
PostgreSQL exports. The truncated console base was re-fetched. Before receipt
refresh, the unchanged console build reproduced exactly
`sha256:385934466c5453902e4beda1d6ed7afb09eae6dd3419d0a7b0b219eece4cc4e2`.
Only authorized tooling hashes and base/tag/canonical metadata were refreshed;
all console source hashes, image config and digest remain unchanged.
`platform_dev.py build-images` then built and graph-verified both archives:

| Archive | Verified manifest digest |
| --- | --- |
| `.build/dev-images/console.oci.tar` | `sha256:385934466c5453902e4beda1d6ed7afb09eae6dd3419d0a7b0b219eece4cc4e2` |
| `.build/dev-images/postgresql-pgvector.tar` | `sha256:baea2bf7f829393ef2d43eae67242fed561f8532fbb1a7c6bbdbacf583a643f6` |

The command performs no repository writes or runtime import. Its 13 offline
tests cover fake registry integrity, corrupt wheels, deterministic builds,
lock refusal, download opt-in, source drift and retained WSL byte identity.
Both real archives were rebuilt twice with identical archive SHA-256 values;
all console image blobs match the reproduction before tooling changes. A
tracked/untracked source snapshot remained unchanged across both builds.
Production renders, common image pins and historical baseline inventory remain
byte-identical to merged main `3b6ec82`. No new third-party tools or libraries.

## Owner-reported context

The approved amendment records that main `1f7d86f` passed version validation and
correctly returned failure exit 1. Its read-only wrapped-input pre-check had zero
findings, kube-proxy replacement was true, and hugepages were 256 MiB / 1 GiB.
These are owner-provided work-order facts, not new live checks by Codex.

Amendment 8 records that main `24b8bdb` passed all validation gates, including
both zero-finding contract checks, before a disabled smoke guard returned 1.
This is owner-provided context, not a completed bootstrap acceptance receipt.

Amendment 9 records that main `3b6ec82` completed host-bootstrap and reported
post-bootstrap/passed in host-check. These are owner-reported facts; this task
neither connects to the Dell nor changes the tester's Pending sign-off.

## Live acceptance

From updated merged main in `E:\twinfra-live`, the owner runs `host-bootstrap`,
then `host-check` and records sanitized output. No reboot is requested by this fix.

| Gate | Result | Evidence to record |
| --- | --- | --- |
| Direct kubectl List passes the installed checker | Pending | Cilium controller input reports passed / 0 findings; no traceback |
| Module -1 and host-bootstrap complete | Pending | Result ready, host-bootstrap passed, dev log caps applied with one kubelet restart, labels and complete.json |
| Disabled smoke step is successful | Pending | Updated main changes 00-setup-ubuntu-host.sh; RUN_SMOKE_TESTS=false reaches ready/complete without smoke calls or an ERR-trap failure |
| Final host-check | Pending | post-bootstrap / passed with matching cluster, node, listener and result identities |
| Rebuilt archives staged on the Dell | Pending | From merged main in E:\twinfra-live, build-images --download-inputs passes both pins; stage-images --archive-dir .build/dev-images then --check reports problems: [] and CRI pinned true |
| Platform and browser continuation | Pending | Runbook steps 9–11 after staging: dev CA/TLS, secrets/platform/Argo CD and HTTPS browser checks |

## Tester sign-off

Tester: Ahmed Mazen (@amazen33), enterprise and cloud tester; QoS tester
Result: Pending
Date (UTC):
QoS targets checked:
Notes:
