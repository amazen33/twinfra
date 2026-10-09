# Proposed local Host Firewall compatibility exception

Status: **superseded on 2026-10-07; Cilium Host Firewall remains enabled**.

The DNS proxy mark repair resolved controller health while retaining the
required Cilium features. See the [validated RCA](../../docs/troubleshooting/argocd-repo-health-wsl.md)
and [correction review](../../docs/correction-review.md). The disablement
proposal below was not applied and no longer blocks the next stage. The
separately approved WSL probe-port ingress exception remains documented in the
[policy runbook](../../deploy/network/platform-probes/README.md). Windows
Firewall reference commands have not been executed as a repair.

## Historical proposal, not an execution instruction

The [WSL setup and troubleshooting guide](../../docs/WSL_SETUP_GUIDE.md) includes
the requested automatic PowerShell WSL/Default Switch adapter detection example,
a scoped rule preview, rollback and Argo CD namespace ordering. These are
documentation references, not executed or validated repairs. Windows Defender
and Hyper-V firewall rules are distinct from Cilium Host Firewall; this Helm
guard does not inspect Windows rules. A Windows allowance therefore cannot
satisfy the guard or authorize disabling Cilium Host Firewall.

Pre-create `argocd` before applying a standalone upstream Argo CD installation.
The existing Twinfra lab uses `platform-services`, which the foundation creates
before installing its relocated Argo CD Core manifests. That namespace and repo
server Pods already exist. The observed `ComparisonError` is not evidence of a
missing `argocd` namespace. Do not install overlapping Argo CD controllers as a
workaround. The guide provides the pinned, separate-cluster reference commands.

The incident's Cilium 1.20.2 host datapath reported K3s host health probes and admission
callbacks from its router address `10.42.0.188` with the `world` identity.
The API and kubelet traffic is therefore denied by host-only rules. Node-address
route selection, legacy host routing and an exact router /32 allowance did not
resolve the identity mismatch. The earlier proposal referenced
[Cilium issue 43012](https://github.com/cilium/cilium/issues/43012); that similarity
was a diagnostic hypothesis, not proof of the full-health failure's cause.

The production [Helm guard](../../tools/helm_node_guard.py) requires
`enable-host-firewall: "true"` and rejected a diagnostic render with it disabled.
The production guard and frozen node exception/inventory remain unchanged.

The proposed disablement would have required separate approval and applied only
to `vcloud-wsl-local`; it was not executed:

```yaml
hostFirewall:
  enabled: false
```

The local post-renderer would still require full kube-proxy replacement, native
routing, Bandwidth Manager, exact frozen Cilium node images/mounts/capabilities,
strict schemas and no privileged containers. All three core namespace deny-all
baselines and narrowly scoped workload allowances would remain enforced.
The dedicated host API firewall would retain its loopback/PodCIDR-only port
16443 boundary. No public ingress, Windows firewall change or production
promotion is included.

This does not establish a comprehensive host deny policy. Cilium host-policy
acceptance would remain deferred to a supported Ubuntu VM/bare-metal profile.
After an approved diagnostic, the exception must be retained only if controller
health and callback tests pass and unauthorized traffic still produces actual
Cilium policy drops. If it does not fix the issue, restore the original settings.

Alternative: keep all required features and move this deployment to the original
Ubuntu 24.04 VM/bare-metal profile after verifying that host's resources/network.
No VM migration or host-wide storage change has been performed.
