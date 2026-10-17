# WO-40c: etcd and CoreDNS control-plane maintenance

**Status:** Approved for static implementation (owner, 2026-10-17).
**Branch:** `codex/wo-40c-control-plane-maintenance`.

The authoritative scope is [WO-40 Amendment 2](WO-40-twinfra-v0-1-0-release.md#amendment-2-2026-10-17-architect-the-first-baseline-accept-failed-the-etcd-and-coredns-maintenance-is-mandatory-not-optional),
as corrected by [Amendment 3](WO-40-twinfra-v0-1-0-release.md#amendment-3-2026-10-17-architect-wo-40c-mechanism-corrected-after-codexs-stop-kubeadm-v1365-source).
Amendment 3 supersedes only the UpgradeConfiguration generator and upgrade
apply phases; the backup, staging, verification, rollback and date requirements stand.

Deliver the [owner-run maintenance procedure](../maintenance/etcd-coredns-2026-10.md),
offline candidate/preview guards and tests. Do not change image locks, acceptance
logic or receipts. No live execution, full bootstrap, reset or upgrade apply.
Under Amendment 4, only the named etcd-local phase and canonical-tag CoreDNS set-image are in scope.

Live acceptance remains Pending for `twinfra-dev-cairo-1`. The owner runs the
maintenance after review/merge and supplies the evidence; Codex does not sign it.

[Amendment 4](WO-40-twinfra-v0-1-0-release.md#amendment-4-2026-10-17-architect-review-of-pr-70-wo-40c-changes-requested) supersedes raw comparison and all CoreDNS phase/digest instructions: use pinned migrate normalisation and the canonical-tag set-image path only.
