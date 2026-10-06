# Proposed local Host Firewall compatibility exception

Status: **awaiting user approval**. No exception is active.

The live Cilium 1.20.2 host datapath reports K3s host health probes and admission
callbacks from its router address `10.42.0.188` with the `world` identity.
The API and kubelet traffic is therefore denied by host-only rules. Node-address
route selection, legacy host routing and an exact router /32 allowance did not
resolve the identity mismatch. The behavior matches
[Cilium issue 43012](https://github.com/cilium/cilium/issues/43012).

The production [Helm guard](../../tools/helm_node_guard.py) requires
`enable-host-firewall: "true"` and rejected a diagnostic render with it disabled.
The production guard and frozen node exception/inventory remain unchanged.

The proposed, user-approved exception would apply only to `vcloud-wsl-local`:

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
