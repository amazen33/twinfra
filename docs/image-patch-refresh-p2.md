# WO-34 P2: dev CoreDNS and etcd promotion

Owner-approved [Amendments 3 and 3a](work-orders/WO-34-image-patch-refresh.md)
replace the earlier P2 stop. [PR #58](https://github.com/amazen33/twinfra/pull/58)
is merged as e922552. Argo CD 3.5.5 stays separate and cannot promote before
2026-10-26. PR #39 is outside this change.

## Verified pins and comparison

Complete Linux amd64 OCI graphs from the
[successful comparison](https://github.com/amazen33/twinfra/actions/runs/38662896911),
with source/binary govulncheck evidence from the same workflow:

| Image | Before C/H with fix | After C/H with fix | C/H without fix |
| --- | --- | --- | --- |
| CoreDNS 1.14.2 → 1.14.7 | 11 / 48 | 3 / 20 | 0 / 0 |
| etcd 3.6.8-0 → 3.6.15-0 | 11 / 43 | 3 / 13 | 0 / 0 |

Neither candidate adds a package/vulnerability identity. Kubernetes and kubeadm
remain v1.36.5. Both overrides stay within the existing minor versions:
`dns.imageTag: v1.14.7`, `etcd.local.imageTag: 3.6.15-0`.

- CoreDNS: `sha256:7efd3c635b03efd68c4e8398fc45f0d993d0e9ab016f72c1cefb0fd6d01aa286`.
- etcd: `sha256:5ed4e32061aa061f970d6500629213e8579ef17571dcf9789074966acb9afad1`.

The generator verifies release age, primary Apache-2.0 licences, OCI platform/config/
layer hashes and complete scan/SBOM evidence before updating the bootstrap lock,
register and receipt. Old production defaults remain reference-only and are not
staged by the dev inventory. The shared source and generated production seeds
change only to embed the dev-only override/contract blocks and derived hashes;
production image selections, source exception policy and SSoT remain unchanged.

## Exceptions and controls

Six exact entries are carried to the new digests/installed package versions;
16 fixed Critical entries close. Reasons, owners, approvers, creation dates and
**2026-11-12 expiry remain unchanged**. That earlier expiry takes precedence over
a new 30-day interval. No approval transfers to a different vulnerability.
GO-2026-6612 entries are separate for x/net and stdlib, including the statically
tested tunnel-only Argo CD, host-firewall etcd deny, cluster-internal DNS and
LAN-only dev boundary. CVE-2026-56857 remains under its original carried approval.
Source reachability is not relabeled as unreachable.

The [generated receipt](acceptance/wo34-p2-2026-10-15.json) lists every carried
and closed entry, immutable references, publication/licence/SBOM hashes and controls.
Live maintenance and tester sign-off remain Pending.

## Owner maintenance, one component at a time

This PR executes none of these live steps. Schedule a maintenance window on the
single-node dev environment. Preserve its current kubeadm configuration and all
four static Pod manifests, and obtain a verified etcd snapshot before etcd work.
Keep backup material outside Git and retain the existing PKI/mount settings.

1. Stage and verify the generated bootstrap lock with the existing shared agent:
   `sudo python3 deploy/common/stage-images.py --lock deploy/common/bootstrap-images.lock.json`;
   repeat with `--check`. Run from the reviewed checkout on the dev host.
2. Review the existing `kube-system/kubeadm-config` ClusterConfiguration and merge
   only the approved etcd/DNS imageTag values. Preserve v1.36.5, registry, cluster
   identity, CIDRs, kube-proxy disabled setting and current patches. Use an
   owner-reviewed v1beta4 UpgradeConfiguration for the existing cluster.
3. Preview the etcd/control-plane upgrade with the pinned kubeadm's
   `upgrade apply phase control-plane --dry-run --etcd-upgrade=true` and the
   existing patch directory. Apply only after reviewing that preview, then verify
   etcd health, API readiness and WAL latency before continuing.
4. Preview and perform the CoreDNS addon phase separately using the pinned tool's
   `upgrade apply phase addon` help to select CoreDNS only. Verify DNS from a
   permitted workload, Cilium policies, GitOps health and the new pinned image.
5. Confirm the tunnel/firewall boundaries and nightly scan; record the actual
   revision and results in the live receipt. A failed component blocks the next
   maintenance step. Retain the pre-maintenance artifacts for owner-led recovery.

The [Kubernetes v1.36 upgrade phase reference](https://v1-36.docs.kubernetes.io/docs/reference/setup-tools/kubeadm/kubeadm-upgrade-phase/)
describes independent phases, config, dry-run and patch flags. Never use
`kubeadm init`, `reset`, full host-bootstrap or a blind script rerun for this
existing-cluster patch maintenance. Static CI previews establish no live outcome.
