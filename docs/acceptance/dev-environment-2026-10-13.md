# WO-31 dev environment evidence · 2026-10-13–14

Environment: `twinfra-dev-cairo-1` on the Dell.
Work order: [WO-31 Amendments 7–14](../work-orders/WO-31-bare-metal-cairo-1.md).
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

The Amendments 10/11/14–14a hygiene follow-up adds a static node-exposure/default-
deny contract, server-side apply in the owner runbook, per-Application
`ServerSideDiff=true,IncludeMutationWebhook=true` and removal of the unsupported
OpenBao configuration field. Both dev-region Application factory outputs and
all persisted dev Applications are tested; cairo-2 remains a cold seed until
WO-23. Production/bootstrap/firewall/image bytes are unchanged. The laptop
loopback/clipboard/TOTP procedures are documentation, not live actions here.

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

## Owner-reported live evidence

Source: Ahmed Mazen's task report, recorded 2026-10-14. These are sanitized
owner-provided observations, not commands executed or independently re-run by
Codex. Recording them does not sign acceptance or conclude the soak.

### 2026-10-13 · main `3b6ec82`

| Check | Owner-reported observation |
| --- | --- |
| Shared host bootstrap | `host-bootstrap` passed |
| Read-only host check | `host-check`: `post-bootstrap` / `passed` |
| Node | Ready; zone `cairo-1a` |
| Bootstrap image cache | 11/11 bootstrap images pinned |
| Cilium image resolution | 0 Cilium `Pulling` events |
| PostgreSQL storage | 20 GiB PG LV mounted with `nosuid,nodev,noexec,noatime` |
| Log caps | Applied |
| Kernel lockdown | `[integrity]` |
| etcd WAL fsync | p99 <= 4 ms; mean approximately 1 ms; approximately 92k samples; target < 10 ms |
| Laptop-to-Dell firewall test | TCP 22/6443 open; 10250/2379 dropped |
| Hardware | Dell ePSA Thorough memory test passed, performed by the owner |

24-hour soak start: `2026-10-13T14:43:38Z`. The earliest 24-hour endpoint is
`2026-10-14T14:43:38Z`; no completion or clean kernel-log verdict was supplied.
Soak verdict: Pending. Machine-check/hung-task log acceptance remains Pending.

### 2026-10-14 · application staging and platform continuation

| Check | Owner-reported observation |
| --- | --- |
| `build-images` console | Reproduced `sha256:385934466c5453902e4beda1d6ed7afb09eae6dd3419d0a7b0b219eece4cc4e2` |
| `build-images` PostgreSQL | Reproduced `sha256:baea2bf7f829393ef2d43eae67242fed561f8532fbb1a7c6bbdbacf583a643f6` |
| Application staging | `stage-images`: PASS |
| Dev PKI | Dev CA and four TLS-bearing Secrets applied: `twinfra-keycloak-tls`, `twinfra-openbao-tls`, `argocd-secret`, `twinfra-gateway-tls` |
| Platform after PRs #50 and #51 | All 11 platform pods Running; CNPG Cluster healthy; Databases applied |
| GitHub egress through host firewall | Argo CD fetched revisions `9c33d0c`, then `9404906` |
| `twinfra-services` | Synced/Healthy |
| `twinfra-platform` | Healthy/OutOfSync; Amendment 14 addresses CNPG-default diff noise |
| Browser access | Console, Keycloak and Argo CD reachable over trusted HTTPS via laptop loopback port-forwards |
| Console identity | Keycloak sign-in with TOTP succeeded for a user with `console.admin` |

OpenBao Running/transport observations do not establish initialization or
unseal; WO-08's ceremony remains separate. No credential, token, OTP seed,
private key or full authorization URL is recorded here.

## Live acceptance

Observed outcomes below remain subject to tester sign-off. No additional live
command is executed for this hygiene PR, and no bootstrap rerun or reboot is
required by Amendments 10/11/14. After merge, the owner verifies the new dev
Application comparison and OpenBao configuration through normal GitOps sync.

| Gate | Result | Evidence to record |
| --- | --- | --- |
| Direct kubectl List passes the installed checker | Pending | Cilium controller input reports passed / 0 findings; no traceback |
| Module -1 and host-bootstrap complete | Owner reported passed; sign-off Pending | 2026-10-13, main `3b6ec82`: host-bootstrap passed, log caps applied, node Ready in cairo-1a |
| Disabled smoke step is successful | Pending | Updated main changes 00-setup-ubuntu-host.sh; RUN_SMOKE_TESTS=false reaches ready/complete without smoke calls or an ERR-trap failure |
| Final host-check | Owner reported passed; sign-off Pending | 2026-10-13: post-bootstrap / passed |
| Rebuilt archives staged on the Dell | Owner reported PASS; sign-off Pending | 2026-10-14: both locked digests reproduced; stage-images PASS |
| Platform and browser continuation | Owner observations recorded; sign-off Pending | 11 pods Running, CNPG healthy, Databases applied, trusted HTTPS and Keycloak/TOTP console.admin sign-in; platform remains Healthy/OutOfSync |
| Amendment 14 reconciliation | Pending | twinfra-platform Synced/Healthy after Server-Side Diff; unsupported-field warning absent from OpenBao logs |
| 24-hour hardware/platform soak | Pending | Start 2026-10-13T14:43:38Z; completion and kernel-log verdict not supplied |

## Owner-reported display-driver incident (2026-10-17; Amendment 15)

Read-only owner finding: nouveau on the GeForce GT 710 began a framebuffer
warning loop at **2026-10-17 18:07:58 UTC**, after the prior clean window.
Reported approximately 9,400 warning traces in the first hour and 19,854 in the
next, about 1.17 million kernel-log lines/hour. No machine-check, hung-task,
OOM, I/O or filesystem errors were reported. The prior full acceptance passed
at 17:08 UTC, before the onset; that does not accept the subsequent soak.

The owner selected option B: keep the card, disable nouveau/nvidiafb using the
reviewed owned-file/initramfs action, then schedule the reboot. **Remediation,
post-reboot acceptance and a fresh clean 24-hour soak remain Pending.** No live
remediation or reboot was performed for this PR. Trigger remains unknown.
See the [owner procedure](../dev-environment.md#owner-display-driver-recovery-wo-31-amendment-15).
This adds the finding only; the tester sign-off below is unchanged.

## Tester sign-off

Tester: Ahmed Mazen (@amazen33), enterprise and cloud tester; QoS tester
Result: Pending
Date (UTC):
QoS targets checked:
Notes:
