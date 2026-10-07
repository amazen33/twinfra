# WSL platform probe-port exception

This bundle implements the user-approved WSL exception for node probe traffic
classified as `reserved:world` (security ID 2). It selects only these three
workloads in `platform-services` and opens TCP **9443, 8084 and 8082**:

| Workload label `app.kubernetes.io/name` | Node health URL |
| --- | --- |
| `cloudnative-pg` | `https://POD_IP:9443/readyz` |
| `argocd-repo-server` | `http://POD_IP:8084/healthz?full=true` |
| `argocd-application-controller` | `http://POD_IP:8082/healthz` |

The requested Cilium exception permits `host`, `remote-node`, `health` and
**`world`**, plus `10.42.0.0/16`. The reviewed Cilium source also retains
`cluster`. The native fallback omits `from`, so it permits **all sources**
on the three ports for the same selected pods. This is broader than a kubelet-only
allowance: external clients can access a probe endpoint when routing permits,
and PodCIDR traffic can reach it. TCP policy cannot restrict access to the listed
HTTP paths. Ingress stays limited to these probe ports. The reviewed
Cilium source is ingress-only; the WSL renderer's separate component policies
provide controller, DNS and Redis dependency egress. Recovery preserves any
egress clauses present in its input. Probe settings and node privileges are not
changed by the recovery helper.

This is a **local WSL lab exception**, not the production zero-trust baseline.
Both manifests carry `vcloud.io/profile: wsl-local`. Contract tests verify the
ingress-only bundle and the separate component dependency policies. A fixture
with explicit egress proves CIDR rendering preserves its input. Metadata labels
document scope; they do not enforce an API admission boundary. The guarded script refuses to apply
on a cluster containing a Node without `vcloud.io/environment=local-validation`,
the label already set by the WSL bootstrap. Production needs correct host
identity classification and the narrower host/remote-node/health approach.
Native policy has no Cilium entity equivalent; its port-only rule also allows
ordinary pod sources, subject to their own egress policies.

Install the [mandatory node CLIs](../../../docs/prerequisites.md): `kubectl`,
`jq`, `curl` and `iproute2`. A missing `jq` fails before API access with an
installation command. Run on the node hosting all three workload types with
credentials for the intended cluster:

```bash
cd /mnt/e/vCloud
export KUBECONFIG=/etc/vcloud-wsl/kubeconfig.yaml
export KUBE_CONTEXT=vcloud-wsl-local
bash deploy/network/platform-probes/recover.sh --plan
bash deploy/network/platform-probes/recover.sh
```

## Recovery after opening the probe ports

Use [`recover.sh`](recover.sh) when the repaired policy is ready but Argo CD
Pods still have restart backoff. The helper prechecks the local node, all three
scheduled workload types, mandatory CLIs, PodCIDRs and the local-validation Node
labels. It validates both policies on the server, applies the policy directory,
restarts **repo-server and application-controller**, waits for both rollouts,
then invokes `apply-and-verify.sh`. Every kubectl operation uses the same reviewed
context and `platform-services` namespace. The policy directory contains only
the two YAML policies; kubectl ignores its Markdown and shell files.

The complete manual sequence, after a successful recovery plan on the owned lab,
is:

```bash
set -euo pipefail
cd /mnt/e/vCloud
export KUBECONFIG=/etc/vcloud-wsl/kubeconfig.yaml
export KUBE_CONTEXT=vcloud-wsl-local
bash deploy/network/platform-probes/recover.sh --plan
# Pin this shell's kubectl calls to the reviewed private lab context.
kubectl() { command kubectl --context "$KUBE_CONTEXT" "$@"; }

# 1. Open the health ports before replacing Pods.
kubectl apply -f deploy/network/platform-probes/
# 2. Replace Argo CD Pods to clear the old Pods' restart backoff.
kubectl rollout restart deployment argocd-repo-server -n platform-services
kubectl rollout restart statefulset argocd-application-controller -n platform-services
# Wait for replacement Pods so the verifier does not race Pod termination.
kubectl rollout status deployment/argocd-repo-server -n platform-services --timeout=180s
kubectl rollout status statefulset/argocd-application-controller -n platform-services --timeout=180s
# 3. Reapply with detected PodCIDRs and verify all three node health URLs.
bash deploy/network/platform-probes/apply-and-verify.sh
```

Run the manual sequence in Bash (or run `recover.sh`) so a failed command stops
the procedure. Rollout restart requests fresh Pods; it does not
resolve a failing health-check dependency. The controller must use its normal
RollingUpdate strategy; an OnDelete strategy or partition can prevent automatic
replacement. The final HTTP/readiness/restart-counter checks remain mandatory.
See Kubernetes' [rollout restart](https://kubernetes.io/docs/reference/kubectl/generated/kubectl_rollout/kubectl_rollout_restart/)
and [rollout status](https://kubernetes.io/docs/reference/kubectl/generated/kubectl_rollout/kubectl_rollout_status/)
references.

| Make target | Behavior |
| --- | --- |
| `wsl-platform-recovery-plan` | Read-only prechecks and ordered command preview |
| `wsl-platform-recover` | Apply policies → restart both Argo CD workloads → wait → live health validation |
| `wsl-platform-probe-verify` | Read-only health acceptance; no policy apply or restart |
| `wsl-platform-probe-test` | Offline policy, recovery-order and failure-path tests |

Make defaults to `KUBE_CONTEXT=vcloud-wsl-local`; use `KUBE_CONTEXT=<reviewed-lab-context>`
to override it. The targets require GNU Make (`sudo apt-get install -y make`
from the configured Ubuntu package sources); the direct Bash helper works
without Make. The private kubeconfig requires its owner/root access. From a
non-root WSL shell, preserve the explicit kubeconfig/context when invoking the
helper, for example
`sudo env KUBECONFIG=/etc/vcloud-wsl/kubeconfig.yaml KUBE_CONTEXT=vcloud-wsl-local bash deploy/network/platform-probes/recover.sh`.
The helper stops on policy apply, restart, rollout, or validation failure and
prints the failed stage. `ROLLOUT_TIMEOUT_SECONDS` defaults to 180 per workload
and is bounded at 900; `TIMEOUT_SECONDS` and `POLL_SECONDS` retain the verifier's
bounds below. After a rollout failure, inspect Pod events and run the read-only
verification target for diagnostics. Repeated restarts do not establish recovery.

The script identifies the local node from its interface addresses and the
Nodes API InternalIP list. It reads **all node-assigned PodCIDRs** from
`Node.spec.podCIDRs` (or `spec.podCIDR`), deduplicates them, and adds them to the
Cilium `fromCIDR` or `fromCIDRSet` rule while retaining the requested
`10.42.0.0/16` reference and existing controller egress rules.
For this node, the discovered allocation is `10.42.0.0/24`; it differs from the
cluster aggregate `/16`, the management LAN, and the Service CIDR. Missing
allocations, invalid prefix lengths and default-route allocations fail closed.
The native fallback records the discovered CIDRs in an annotation; its existing
all-source probe-port allowance is preserved. It does not narrow that allowance
to Node InternalIPs. Rerun rendering when node allocations change.

Both rendered manifests are server-validated before either is applied. Then the
script polls every selected active pod, including multiple repo-server replicas,
for readiness and stable pod UIDs/restart counters. Every local pod is curled
at the corresponding URL with `--max-time 5` and proxies bypassed. CNPG HTTPS
uses `-k` to reproduce the unauthenticated kubelet probe; this is not a TLS trust
or secrets test. No API bearer token or credentials are sent in those requests.

Success requires **all three workload types present and Ready**, HTTP **200**
from every local pod, and unchanged UIDs/restart counters across two consecutive
polls. HTTP 503, redirects, missing pods/IPs, connection timeouts, API errors and
continuing restarts cannot produce a pass. Default polling timeout is 180 seconds;
individual API/curl calls have their own bounds. Timeout returns nonzero and
prints Warning events. This is a short recovery check, not sustained availability.

```bash
# Read-only acceptance after deployment:
TIMEOUT_SECONDS=180 bash deploy/network/platform-probes/apply-and-verify.sh --verify-only
# Native fallback on a local-validation cluster without Cilium:
bash deploy/network/platform-probes/apply-and-verify.sh --kubernetes-only
```

On multiple nodes, run verification on a node hosting all three selected workload
types or adapt the operational rollout to check each node. This script refuses to
claim local verification for a workload hosted elsewhere. The WSL renderer includes
the shared Cilium source in bootstrap-owned network resources; node-specific
rendering stays out of Argo's workload directory. `apply-and-verify.sh` itself
does not restart workloads; `recover.sh` performs the two requested Argo CD
restarts before calling it. A matching explicit Cilium `ingressDeny`/`egressDeny`
continues to take precedence over these additive allowances.

The earlier three-entity exception failed on 2026-10-07: source `10.42.0.188`
was mapped to `host` in the ipcache but appeared as `world` in endpoint drops.
The user subsequently authorized this broader WSL exception. The scope change
is deliberate; live HTTP recovery must be measured separately from YAML/schema
checks. If requests still fail, inspect Cilium drops, node routes and listeners,
and compare the current pod IPs rather than increasing timeouts or disabling
probes.

Live validation on 2026-10-07 applied both expanded policies, with the Cilium
CIDR list containing the reference `10.42.0.0/16` and discovered node allocation
`10.42.0.0/24`. CNPG `/readyz` and the application-controller `/healthz`
returned HTTP 200 from the node. Repo-server accepted TCP connections on 8084,
but its `/healthz?full=true` request did not complete within five seconds;
repo-server logged `rpc error: code = Canceled desc = context canceled` from
its full health check. A subsequent snapshot showed `CrashLoopBackOff` and
connection refusal while the container was stopped. The complete acceptance
script returned **1**, so recovery of all three workloads is not established.
The remaining full-health failure needed investigation beyond allowing the probe
port. The subsequent [validated RCA and repair](../../../docs/troubleshooting/argocd-repo-health-wsl.md)
identified blocked local gRPC SRV/Redis DNS lookups and WSL's nftables output
mark overwrite. After repairing those dependencies, the unchanged full health
check returned 200, the three-workload verifier passed, and cross-namespace
unauthorized traffic still produced matching Cilium Policy denied events.

References: [Cilium entities and CIDRs](https://docs.cilium.io/en/stable/security/policy/layer3/),
[Cilium deny policies](https://docs.cilium.io/en/stable/security/policy/deny/),
[Kubernetes NetworkPolicy semantics](https://kubernetes.io/docs/concepts/services-networking/network-policies/).
