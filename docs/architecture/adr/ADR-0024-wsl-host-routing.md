# ADR-0024: WSL2 lab host-routing compatibility exception

**Status:** Accepted for the local lab only
**Date:** 2026-10-07
**Deciders:** vCloud operator; scoped routing test explicitly approved
**Scope:** Single-node `vcloud-wsl-local`; production/staging excluded

## Context

On this Ubuntu 26.04 WSL2 mirrored-network/veth topology, Argo CD repo-server
intermittently timed out fetching GitHub. A temporary Pod MTU change did not
repair the fetch and was reverted. The approved Cilium host-routing test
switched only the legacy-host-routing option and restarted Cilium. GitHub HEAD
then fetched successfully; three subsequent bounded fetches also succeeded.

Cilium's [host-routing tuning documentation](https://docs.cilium.io/en/stable/operations/performance/tuning/#ebpf-host-routing)
describes `bpf.hostLegacyRouting=true` for compatibility with dependencies on
host netfilter hooks. This fits the observed local workaround. It does not
establish that every WSL kernel needs legacy routing, or isolate the setting
from the accompanying DaemonSet restart as a complete root-cause experiment.

## Decision

The dedicated [WSL values overlay](../../../lab/wsl/values/cilium-routing.yaml)
is the only source YAML permitted to enable legacy host routing. Merge it
after [base Cilium values](../../../module-2/values/cilium.yaml). The renderer
checks its exact approved shape and preserves the base's node mount/security
settings. Cilium remains bootstrap/Helm-owned; Argo manages application resources
and must not acquire a second owner for this cluster's Cilium installation.

Use the supported **Helm** key `bpf.hostLegacyRouting: true`. This renders
**ConfigMap/daemon** key `enable-host-legacy-routing: "true"`.
`enableHostLegacyRouting` is not a supported Cilium 1.20.2 Helm key and must
not be silently passed as a values override.

| Control | WSL overlay | Base/production |
| --- | --- | --- |
| Legacy host routing | `bpf.hostLegacyRouting: true` | Explicit `false` |
| Native CNI routing | `routingMode: native` | Retained |
| eBPF proxy replacement | `kubeProxyReplacement: true` | Retained |
| BPF masquerade | `bpf.masquerade: true` | Retained |
| Socket load balancing | `socketLB.enabled: true`, explicitly rendered | Existing base/chart behavior unchanged |
| Namespace deny-all and Cilium identities | Retained; tested allowed/denied paths | Existing policies unchanged |

Legacy **host** routing deliberately traverses the Linux host stack. It does
not disable Cilium's native Pod routing, eBPF service handling or policy
datapath, and must not be described as retaining BPF *host* routing. Live status
confirmed `Routing: Network: Native Host: Legacy`, not BPF host routing.

## Options considered

1. Keep BPF host routing in this lab: preserves its fast path but left the
   observed repository fetch unreliable.
2. Local legacy host routing: selected for measured connectivity; adds host
   stack overhead and needs a WSL-specific acceptance/rollback procedure.
3. Enable legacy routing for every environment: rejected; no production or
   staging evidence justifies widening this compatibility exception.

## Consequences and validation

[The CI guard](../../../tools/check_host_routing.py) rejects enabled options
outside the exact local file, including Argo inline values, valuesObject,
parameters, multiple sources, ApplicationSet templates, lab valueFiles
references, daemon ConfigMaps and JSON patches. Unsupported aliases, duplicate
YAML keys and ambiguous string booleans also fail closed. Both the current
candidate and applicable selected-revision renders are checked. Historical PR
revisions without this feature keep their original gates; the candidate
boundary check still runs unconditionally.

The locked Cilium 1.20.2 chart renders the lab option `"true"`, base option
`"false"`, native mode, BPF masquerade and proxy replacement. The lab also
renders `bpf-lb-sock: "true"`. Unit mutation tests and strict kubeconform
validate the source/rendered contract. Helm rendering establishes desired
configuration. The separate live refresh at **2026-10-07 14:12:36 UTC** confirms
effective Socket LB enabled with full coverage, BPF masquerading, native Pod
routing and proxy replacement. The existing ConfigMap still has `bpf-lb-sock:
"false"`, overridden by full kube-proxy replacement in the agent; the overlay
makes this intent explicit on the next Helm reconciliation. No additional
Cilium restart or socket configuration mutation was performed for that check.

The live fetch and six policy-denied drops were rechecked at 14:11 UTC in the
[dated acceptance record](../../acceptance/wsl-2026-10-07.md). SPIFFE/SPIRE
attestation was not deployed or tested by these checks. Cilium label/security
identities are not evidence of SPIFFE identity. A claim that all SPIFFE and
socket behavior is "100% validated" would exceed the available evidence.

The GitHub `vCloud PR gate` must be a required ruleset check before CI failures
can guarantee merge prevention; branch protection remains a separate open
milestone. No production environment or GitHub ruleset is modified here.

## Action items

- [x] Codify the narrow local override and preserve explicit base `false`.
- [x] Add fail-closed CI governance, mutation tests and both Helm render assertions.
- [x] Document actual routing/fetch/policy evidence and its limits.
- [x] Document the exact-head/integration GitHub publication gate; [PR #19](https://github.com/amazen33/vCloud/pull/19) carries its current results.
- [x] Record live effective socket LB/native/BPF/proxy status and repeat GitHub/deny-all/endpoint checks.
- [ ] Reconcile the new explicit socket LB ConfigMap value through the lab Helm owner.
- [ ] Retest WSL reboot and revisit this workaround after kernel/Cilium upgrades.
- [ ] Separately deploy/validate SPIFFE if adopted; retain the existing default-deny policies.
