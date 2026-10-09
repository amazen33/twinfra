# WSL2 Local Environment Runbook & Troubleshooting

The [local M3–M5 runbook](wsl-local-milestones-3-5.md) covers the subsequent
GitOps DNS, encryption-at-rest, CNPG storage-mode and PGP-init corrections.

For actual browser endpoints, use the [verified local service access runbook](service-access.md).
Start the existing Core dashboard with `sudo bash lab/wsl/access.sh start`;
its local URL is `http://127.0.0.1:8080/`. Reference domain names do not become
live endpoints until a backend and an access route are deployed.

Scope: `vcloud-wsl-local`, six CPUs, approximately 20 GB RAM, mirrored networking.
Node diagnostics require `kubectl`, **`jq`**, `curl` and `ip` (`iproute2`). The WSL
bootstrap installs `jq`; use the [prerequisite installation steps](prerequisites.md)
to repair an existing node without rerunning the cluster bootstrap.
For private registry DNS, containerd API-path mapping and exact CRI cache gates,
use the [image-pull runbook](troubleshooting/image-pull-failures.md). WSL Core and
the full Argo overlay share a pinned digest and explicit `IfNotPresent`; select
one installation owner before applying either profile.
This is a documentation update; the Windows Firewall examples below have not
been executed or validated as fixes on this host. The existing Cilium exception
is [superseded by the validated DNS mark repair](../lab/wsl/HOST-FIREWALL-EXCEPTION.md);
Cilium Host Firewall remains enabled.

## 1. Host Firewall Exception (PowerShell Admin)

First distinguish Windows Defender/Hyper-V filtering from Cilium Host Firewall.
[`helm_node_guard.py`](../tools/helm_node_guard.py) validates rendered Cilium
configuration, schemas and frozen node privileges. It does not inspect Windows
Firewall rules or Windows adapters. Adding a Windows rule cannot satisfy its
`enable-host-firewall: "true"` requirement or repair a Cilium identity mismatch.

The requested automatic adapter detection example is preserved here for
reference. It creates a broad inbound allowance, with no port or source limit,
and can match multiple adapters, including an unrelated Default Switch. It is
not the default zero-trust procedure or a validated remedy for the current lab:

```powershell
$wslAdapter = Get-NetAdapter | Where-Object { $_.Name -like "*WSL*" -or $_.Name -like "*Default Switch*" }
if ($wslAdapter) {
    New-NetFirewallRule -DisplayName "vCloud-WSL-K3s-Exception" -Direction Inbound -InterfaceAlias $wslAdapter.Name -Action Allow
}
```

If evidence identifies a Windows Defender rule as the blocker, preview a rule
with explicit boundaries instead. Run in elevated PowerShell. Detection prefers
a WSL adapter; it stops on ambiguous matches. Verify a Default Switch fallback
belongs to the intended WSL network before applying. The preview does not create
a rule; remove `-WhatIf` only for an intentional Windows Firewall change.

```powershell
$wslAdapter = @(Get-NetAdapter -IncludeHidden | Where-Object {
    $_.Status -eq "Up" -and $_.Name -like "*WSL*"
})
if ($wslAdapter.Count -eq 0) {
    $wslAdapter = @(Get-NetAdapter -IncludeHidden | Where-Object {
        $_.Status -eq "Up" -and $_.Name -like "*Default Switch*"
    })
}
if ($wslAdapter.Count -ne 1) {
    throw "Expected one reviewed WSL adapter; found $($wslAdapter.Count)."
}
$ruleName = "vCloud-WSL-K3s-Exception-TCP16443"
$wslAdapter | Select-Object Name, InterfaceDescription, Status
if (Get-NetFirewallRule -Name $ruleName -ErrorAction SilentlyContinue) {
    Get-NetFirewallRule -Name $ruleName | Get-NetFirewallPortFilter
} else {
    New-NetFirewallRule -Name $ruleName -DisplayName $ruleName `
        -Direction Inbound -InterfaceAlias $wslAdapter[0].Name `
        -Protocol TCP -LocalPort 16443 -RemoteAddress "127.0.0.1/32" `
        -Profile Private -Action Allow -WhatIf
}
```

This example permits only the stated source, interface, protocol, port and
profile. It does not open the Linux API firewall, enable remote access or bypass
an explicit block rule. Review existing rules' address/interface filters as well
as their port filters before relying on them.

Mirrored WSL also has Hyper-V firewall filtering. A conventional adapter rule
does not establish that Hyper-V allows the connection; a WSL-named virtual
adapter may be absent. Inspect the applicable layer using Microsoft's
[WSL networking guidance](https://learn.microsoft.com/en-us/windows/wsl/networking).
Do not change the default inbound action to Allow as a blanket troubleshooting
step. Cmdlet scope and filtering parameters are documented in
[New-NetFirewallRule](https://learn.microsoft.com/en-us/powershell/module/netsecurity/new-netfirewallrule?view=windowsserver2025-ps).

Rollback only a scoped rule created by the preview procedure after applying it:

```powershell
Remove-NetFirewallRule -Name "vCloud-WSL-K3s-Exception-TCP16443" -WhatIf
```

Review the removal preview, then remove `-WhatIf` to delete that exact rule.
Do not flush firewall policies or remove unrelated rules.

## 2. ArgoCD Namespace and Deployment

**Create the installation namespace before applying namespaced resources.**
For a standalone upstream installation, that namespace is `argocd`; the official
[Argo CD installation guide](https://argo-cd.readthedocs.io/en/stable/getting_started/)
uses this ordering. Missing namespaces cause installation failures. A missing or
unreachable repo server can subsequently cause `ComparisonError`; this status
alone does not prove a namespace is missing.

### Existing Twinfra WSL lab: `platform-services`

This repository deliberately installs Argo CD **Core 3.5.3** in
`platform-services`, with relocated service references and RBAC subjects.
The three restricted core namespaces are created by the foundation bootstrap
before `platform.sh` installs controllers. Do not install a second Argo CD in
`argocd` to repair this cluster: its cluster-wide resources would overlap.

Inside the owned WSL Ubuntu distribution, inspect the actual namespace,
deployment, Service and ready endpoints using the private local context:

```bash
kubectl_local() {
  sudo /usr/local/bin/k3s kubectl --kubeconfig /etc/vcloud-wsl/kubeconfig.yaml \
    --context vcloud-wsl-local "$@"
}
kubectl_local get namespace platform-services
kubectl_local get pods -n platform-services -l app.kubernetes.io/part-of=argocd
kubectl_local get deployment argocd-repo-server -n platform-services
kubectl_local get service argocd-repo-server -n platform-services
kubectl_local get endpointslices -n platform-services \
  -l kubernetes.io/service-name=argocd-repo-server
kubectl_local get application vcloud-wsl-platform -n platform-services -o yaml
```

Root access here reads the mode-0600 local kubeconfig; it grants no new Pod
privilege. If the namespace is missing, restore it through the audited foundation
bootstrap before resuming the [platform runbook](../lab/wsl/PLATFORM.md).
If it exists but endpoints are unready, investigate Pod events, health probes,
TLS, network-policy drops and repo-server connectivity before changing namespaces.

The historical [saved status](wsl-platform-status.json) records failed probes
and a repo Service `no route to host` error. The 2026-10-07
[correction review](correction-review.md) supersedes that health gate: all three
probes and local browser access passed with Host Firewall enabled. At that
review, GitOps still reported `ComparisonError` because the discovery binding
targeted the old `argocd` ServiceAccount. The later
[M3–M5 acceptance record](acceptance/wsl-2026-10-07.md) documents the corrected
`platform-services` binding, both Applications Synced/Healthy and PostgreSQL
acceptance. Namespace creation and Windows firewall changes alone do not
resolve a controller RBAC mismatch.

### Separate upstream reference installation: `argocd`

Use only a separately reviewed cluster with no existing Argo CD installation.
The upstream `/stable/manifests/install.yaml` URL is a moving branch; use the
explicit `v3.5.3` release below. Bash commands use plain URLs, not Markdown links.
This is a full upstream reference installation, not the vetted Twinfra Core profile.
Its security/RBAC settings require review before adopting it into Twinfra.

```bash
: "${REVIEWED_CONTEXT:?Set REVIEWED_CONTEXT to the separate target cluster}"
kubectl --context "$REVIEWED_CONTEXT" create namespace argocd --dry-run=client -o yaml \
  | kubectl --context "$REVIEWED_CONTEXT" apply -f -
kubectl --context "$REVIEWED_CONTEXT" apply --server-side -n argocd \
  -f https://raw.githubusercontent.com/argoproj/argo-cd/v3.5.3/manifests/install.yaml
kubectl --context "$REVIEWED_CONTEXT" rollout status deployment/argocd-repo-server \
  -n argocd --timeout=300s
```

Server-side apply avoids the annotation-size limit on large upstream CRDs.
Do not force field ownership over an existing installation. If installing into a
different namespace, update embedded RBAC subjects and service references too;
`kubectl -n` alone does not relocate those fields.

## 3. WSL host routing, eBPF validation and the production boundary

The measured mirrored-network/veth lab requires legacy host routing as its
current GitHub fetch workaround. It is scoped to
[`lab/wsl/values/cilium-routing.yaml`](../lab/wsl/values/cilium-routing.yaml).
The renderer merges it after production/base values, which retain
`bpf.hostLegacyRouting: false`. Native CNI, BPF masquerade and full kube-proxy
replacement remain enabled. Socket load balancing is now explicitly enabled
in the lab overlay. No networking controller changes ownership.

The Helm key is `bpf.hostLegacyRouting`, **not** `enableHostLegacyRouting`.
It renders `cilium-config.data["enable-host-legacy-routing"]`. Verify the
desired lab and base profiles offline using the locked chart:

```bash
python3 tools/check_host_routing.py --helm helm --build .build/host-routing
python3 -m unittest discover -s tests -p test_host_routing.py -v
```

Expected rendered values:

| ConfigMap key | Lab | Base/production |
| --- | --- | --- |
| `enable-host-legacy-routing` | `"true"` | `"false"` |
| `routing-mode` | `"native"` | `"native"` |
| `kube-proxy-replacement` | `"true"` | `"true"` |
| `enable-bpf-masquerade` | `"true"` | `"true"` |
| `bpf-lb-sock` | `"true"` | Existing behavior unchanged |

CI rejects legacy routing in other source values or Argo Applications,
including inline values, valuesObject, Helm parameters and multiple sources.
Production/staging must never reference the local overlay. A required GitHub
ruleset remains necessary to enforce merge blocking; it is tracked separately.

After deliberately reconciling the lab Helm values, use read-only checks to
verify the effective configuration, agent status and repository fetch:

```bash
cd /mnt/e/vCloud
sudo bash lab/wsl/reconcile-host-routing.sh --check
kubectl_local -n kube-system get configmap cilium-config -o json \
  | jq -e '.data | .["enable-host-legacy-routing"] == "true" and
      .["routing-mode"] == "native" and .["kube-proxy-replacement"] == "true" and
      .["enable-bpf-masquerade"] == "true" and .["bpf-lb-sock"] == "true"'
kubectl_local -n kube-system exec daemonset/cilium -c cilium-agent -- cilium-dbg status --verbose
kubectl_local -n platform-services exec deployment/argocd-repo-server -- \
  timeout 25 git ls-remote https://github.com/amazen33/vCloud.git HEAD
sudo bash lab/wsl/test-network.sh
```

`kubectl_local` is defined in section 2. Expect `Host Routing: Legacy`,
kube-proxy replacement enabled and Socket LB enabled in agent status. Native
CNI routing remains eBPF-based, while host packets traverse the Linux stack.
The network test must prove the allowed control and unauthorized Service/direct
Pod requests with matching Cilium drops. Do not accept merely Ready Pods.

The 2026-10-07 15:04 UTC refresh establishes successful GitHub fetching, deny-all
enforcement and effective Socket LB enabled/full coverage in agent status.
The owned Helm reconciliation also converged ConfigMap `bpf-lb-sock: "true"`;
the strict ConfigMap check above now passes. SPIFFE/SPIRE is not established by Cilium's label identities:
`mesh-auth-enabled` is false and the auth certificate provider reports Disabled.
See
[ADR-0024](adr/0024-wsl-host-routing.md) and the
[dated acceptance record](acceptance/wsl-2026-10-07.md) for evidence and limits.

### After a WSL restart: verify the routing interface

Keep an Ubuntu shell open during manual lab acceptance. Microsoft notes that
[systemd services do not keep a WSL instance alive](https://learn.microsoft.com/en-us/windows/wsl/systemd).
After a distro stop, verify the current interface and recreate the owned
transient access units. Do not treat active systemd configuration as an
unattended availability guarantee.

Mirrored WSL interface names can change across starts. On 2026-10-07 the Node
address `192.168.1.9` moved from `eth1` to `eth2`, while Cilium still selected
`eth1`. Cilium reported `direct routing device eth1 has no usable addresses`;
Pods stayed Unknown/ContainerCreating and CNI endpoint creation returned 429.
A Ready Node and old Argo Synced/Healthy status were insufficient evidence:
require a fresh reconciliation at the intended commit and live endpoint tests.

Inspect the actual route, Node address and configured device before recovery:

```bash
sudo -i
cd /mnt/e/vCloud
export KUBECONFIG=/etc/vcloud-wsl/kubeconfig.yaml
k() { /usr/local/bin/k3s kubectl --context=vcloud-wsl-local --request-timeout=40s "$@"; }
ip -4 route get 1.1.1.1
ip -br -4 address
k get nodes -o wide
k -n kube-system get configmap cilium-config -o json | jq '.data.devices'
k -n kube-system logs daemonset/cilium -c cilium-agent --tail=100
```

The following scoped recovery uses the checksum-verified Linux tools and offline
schemas already staged for [CI validation](github-actions-tests.md), the locked
chart and the existing Helm owner. It briefly interrupts this single lab's
networking. Run only on the owned lab with the retained Local PV mounted; if the
detected Node address differs from the Kubernetes InternalIP, stop and investigate
the API/node configuration first. Do not hard-code `eth2` for future starts.

```bash
set -euo pipefail
test -f /var/lib/vcloud-wsl/owner.json
k get nodes -o json | jq -e '.items | length == 1 and .[0].metadata.name == "vcloud-wsl-local"'
findmnt /var/lib/vcloud-wsl/storage/postgres-1
NODE_IP=$(ip -4 route get 1.1.1.1 | awk '{for(i=1;i<=NF;i++) if($i=="src") {print $(i+1);exit}}')
DEVICE=$(ip -4 route get 1.1.1.1 | awk '{for(i=1;i<=NF;i++) if($i=="dev") {print $(i+1);exit}}')
k get node vcloud-wsl-local -o json | jq -e --arg ip "$NODE_IP" \
  '.status.addresses | any(.type == "InternalIP" and .address == $ip)'
ROOT=$PWD
BUILD="$ROOT/.build/wsl-device-recovery"
ASSETS="$ROOT/.build/ci-linux-assets"
test -x "$ASSETS/bin/helm"
test -x "$ASSETS/bin/kubeconform"
test -d "$ASSETS/schemas"
python3 tools/wsl_lab.py render --build "$BUILD" --node-ip "$NODE_IP" --device "$DEVICE"
python3 tools/wsl_lab.py validate --build "$BUILD" --helm "$ASSETS/bin/helm" \
  --kubeconform "$ASSETS/bin/kubeconform" --schemas "$ASSETS/schemas"
k -n kube-system get configmap cilium-config -o json > "$BUILD/cilium-config-before.json"
cat > "$BUILD/kubeconform-offline.sh" <<EOF
#!/usr/bin/env bash
exec "$ASSETS/bin/kubeconform" -kubernetes-version 1.36.5 \
  -schema-location '$ASSETS/schemas/{{.ResourceKind}}.json' "\$@"
EOF
cat > "$BUILD/post-render.sh" <<EOF
#!/usr/bin/env bash
exec python3 "$ROOT/tools/helm_node_guard.py" --kubeconform "$BUILD/kubeconform-offline.sh"
EOF
chmod 0755 "$BUILD/kubeconform-offline.sh" "$BUILD/post-render.sh"
"$ASSETS/bin/helm" upgrade cilium module-2/vendor/cilium-1.20.2.tgz \
  --namespace kube-system --kube-context vcloud-wsl-local --reuse-values \
  -f "$BUILD/cilium-values.yaml" --post-renderer "$BUILD/post-render.sh" --wait --timeout 5m
# A ConfigMap-only change does not restart the agent or reload its selected device.
k -n kube-system rollout restart daemonset/cilium
k -n kube-system rollout status daemonset/cilium --timeout=180s
k -n kube-system exec daemonset/cilium -c cilium-agent -- cilium-dbg status --verbose
python3 tools/wsl_git_dns.py
bash lab/wsl/test-network.sh
bash lab/wsl/test-e2e.sh
KUBE_CONTEXT=vcloud-wsl-local bash deploy/network/platform-probes/apply-and-verify.sh --verify-only
```

Verify the selected device, explicit ConfigMap flags and effective agent status;
require a bounded repo-server GitHub fetch, allowed/DNS controls, denied Service
and direct-Pod traffic with Cilium drops, both Applications Synced/Healthy at
current `main`, demo HTTP 200, database persistence and stable node probes.
The bootstrap already rediscovers the route for rendering, but automatic
post-reboot device reconciliation and agent restart are not implemented.
Manual recovery passed; unattended reboot acceptance remains open.

### Mirrored localhost recovery after Cilium reconfiguration

On 2026-10-08 the same interface drift recurred (`eth1` selected, actual route
on `eth2`). Recover the explicitly observed device using the procedure above.
An automatic device-selection trial selected both the physical LAN and WSL's
separate `10.20.0.1` interface and failed live acceptance. It was rolled back;
the repository retains explicit route-derived device selection.

If Linux TCP to its own listener fails with `No route to host`, inspect
`ip -4 rule show` and `ip -4 route get 127.0.0.1`. In this incident, WSL's
priority-one table 127 routed both local connections and incoming Windows
requests through `loopback0` before local delivery. A blanket priority-zero
local-table rule restored Linux traffic but broke replies to Windows. Do not
use that blanket rule or remove WSL's routing tables.

The manual helper below requires the exact owned profile, root and mirrored
mode. It marks only host-originated connections with both IPv4 endpoints
`127.0.0.1`, restores that mark on their reply packets, and routes those flows
locally. A separate exact `loopback0` ingress selector delivers Windows
requests to the local listener; replies retain WSL routing. The mark is bit
`0x2`, outside Cilium's proxy identity mask. No firewall ACCEPT, physical route
or Kubernetes policy is added. Foreign priority-zero rules or altered owned
table contents cause a refusal instead of an overwrite. Mirrored WSL also
recreates protocol-specific priority-zero ingress rules on boot: exact
`src all`, `iif ethN/loopback0`, `ipproto tcp/udp`, `lookup local` entries.
The helper preserves these WSL-managed rules verbatim. Its repair and rollback
touch only the two Twinfra selectors targeting `127.0.0.1/32` and the exact
owned nftables table. Similar rules with a different source, table, interface,
protocol or additional selector remain a refusal.

```bash
# Run on the owned WSL lab after the Cilium agent has started.
sudo python3 tools/wsl_loopback_routing.py          # review the planned changes
sudo python3 tools/wsl_loopback_routing.py --apply  # idempotent + TCP request/reply check
sudo bash lab/wsl/endpoints/access.sh start
sudo bash lab/wsl/localstack/access.sh
sudo bash lab/wsl/test-e2e.sh
sudo bash lab/wsl/test-network.sh
```

Verify Windows independently with the Host-routed APISIX demo and LocalStack
health URL in [service access](service-access.md). After a Cilium restart,
existing forwards can retain failed streaming connections: restart only the
known `vcloud-wsl-{apisix,prometheus,grafana,keycloak}-access.service`,
`vcloud-wsl-openbao-init.service` and `vcloud-wsl-localstack-access.service`
units after inspecting their `ExecStart`, then repeat acceptance. An active
unit alone does not establish endpoint health.

Rollback is `sudo python3 tools/wsl_loopback_routing.py --remove`; it removes
only the verified recovery table and its two exact rules. In the affected
state rollback reintroduces the localhost failure. This is a manual lab
repair, without a startup timer or unattended restart guarantee. See the
[2026-10-08 acceptance record](acceptance/wsl-restart-recovery-2026-10-08.md).

## 4. Acceptance after a deliberate repair

For a repo-server that accepts 8084 but times out on `/healthz?full=true`, follow
the [validated DNS proxy mark repair](troubleshooting/argocd-repo-health-wsl.md).
It covers the local gRPC SRV lookup, exact Redis DNS allowance and WSL's output
packet-mark overwrite. The owned bootstrap now installs a reconciliation timer
for the two Cilium proxy mark classes. Repair that dependency before restarting
Pods; retain the full health probe and its five-second timeout.

For probe-port recovery in `platform-services`, use the
[platform probe recovery runbook](../deploy/network/platform-probes/README.md#recovery-after-opening-the-probe-ports).
Its sequence applies both network policies first, restarts the
`argocd-repo-server` Deployment and `argocd-application-controller` StatefulSet to
replace Pods carrying restart backoff, waits for the rollouts, then runs all
three node health checks. It retains HTTP 200, readiness and stable restart
counters as acceptance gates. The Make targets require GNU Make; install the
`make` package from the configured Ubuntu sources if it is missing, or invoke
`bash deploy/network/platform-probes/recover.sh` directly with the same
kubeconfig/context. On the owned WSL node with the private kubeconfig:

```bash
cd /mnt/e/vCloud
sudo env KUBECONFIG=/etc/vcloud-wsl/kubeconfig.yaml KUBE_CONTEXT=vcloud-wsl-local \
  make wsl-platform-recovery-plan
sudo env KUBECONFIG=/etc/vcloud-wsl/kubeconfig.yaml KUBE_CONTEXT=vcloud-wsl-local \
  make wsl-platform-recover
# Later read-only health verification, without applying policies or restarting:
sudo env KUBECONFIG=/etc/vcloud-wsl/kubeconfig.yaml KUBE_CONTEXT=vcloud-wsl-local \
  make wsl-platform-probe-verify
```

The recovery helper stops on failure and rejects Nodes outside the labelled
local-validation profile. A successful rollout does not establish that
repo-server's full health check, Git reconciliation or database readiness works.

Require a Ready repo server, ready Service endpoints, and an Application that
is `Synced` and `Healthy` at the intended Git commit with no `ComparisonError`.
Then rerun `sudo bash lab/wsl/test-network.sh` to verify the allowed control and
unauthorized Service/direct-Pod requests with actual Cilium drop evidence.
CNPG SQL/TLS/pgvector, persistent storage and resource growth have separate
[acceptance checks](../lab/wsl/PLATFORM.md). Documentation and syntax checks do
not establish runtime repair, database initialization or production readiness.
