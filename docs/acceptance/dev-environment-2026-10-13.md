# WO-31 Amendments 7–8 acceptance · 2026-10-13

Environment: `twinfra-dev-cairo-1` on the Dell.
Work order: [WO-31 Amendments 7–8](../work-orders/WO-31-bare-metal-cairo-1.md).
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

## Owner-reported context

The approved amendment records that main `1f7d86f` passed version validation and
correctly returned failure exit 1. Its read-only wrapped-input pre-check had zero
findings, kube-proxy replacement was true, and hugepages were 256 MiB / 1 GiB.
These are owner-provided work-order facts, not new live checks by Codex.

Amendment 8 records that main `24b8bdb` passed all validation gates, including
both zero-finding contract checks, before a disabled smoke guard returned 1.
This is owner-provided context, not a completed bootstrap acceptance receipt.

## Live acceptance

From updated merged main in `E:\twinfra-live`, the owner runs `host-bootstrap`,
then `host-check` and records sanitized output. No reboot is requested by this fix.

| Gate | Result | Evidence to record |
| --- | --- | --- |
| Direct kubectl List passes the installed checker | Pending | Cilium controller input reports passed / 0 findings; no traceback |
| Module -1 and host-bootstrap complete | Pending | Result ready, host-bootstrap passed, dev log caps applied with one kubelet restart, labels and complete.json |
| Disabled smoke step is successful | Pending | Updated main changes 00-setup-ubuntu-host.sh; RUN_SMOKE_TESTS=false reaches ready/complete without smoke calls or an ERR-trap failure |
| Final host-check | Pending | post-bootstrap / passed with matching cluster, node, listener and result identities |

## Tester sign-off

Tester: Ahmed Mazen (@amazen33), enterprise and cloud tester; QoS tester
Result: Pending
Date (UTC):
QoS targets checked:
Notes:
