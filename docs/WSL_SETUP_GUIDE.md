# WSL2 Local Environment Runbook & Troubleshooting

Scope: `vcloud-wsl-local`, six CPUs, approximately 20 GB RAM, mirrored networking.
This is a documentation update; the Windows Firewall examples below have not
been executed or validated as fixes on this host. The existing Cilium exception
is still [awaiting a separate decision](../lab/wsl/HOST-FIREWALL-EXCEPTION.md).

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

### Existing vCloud WSL lab: `platform-services`

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

The recorded lab failure has an existing `platform-services` namespace and repo
server Pods, but failed probes and `ComparisonError` with `no route to host` on
the repo Service. [Saved status](wsl-platform-status.json) and the
[Cilium compatibility proposal](../lab/wsl/HOST-FIREWALL-EXCEPTION.md) describe the
remaining gate. These Windows and namespace examples do not establish its fix.

### Separate upstream reference installation: `argocd`

Use only a separately reviewed cluster with no existing Argo CD installation.
The upstream `/stable/manifests/install.yaml` URL is a moving branch; use the
explicit `v3.5.3` release below. Bash commands use plain URLs, not Markdown links.
This is a full upstream reference installation, not the vetted vCloud Core profile.
Its security/RBAC settings require review before adopting it into vCloud.

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

## 3. Acceptance after a deliberate repair

Require a Ready repo server, ready Service endpoints, and an Application that
is `Synced` and `Healthy` at the intended Git commit with no `ComparisonError`.
Then rerun `sudo bash lab/wsl/test-network.sh` to verify the allowed control and
unauthorized Service/direct-Pod requests with actual Cilium drop evidence.
CNPG SQL/TLS/pgvector, persistent storage and resource growth have separate
[acceptance checks](../lab/wsl/PLATFORM.md). Documentation and syntax checks do
not establish runtime repair, database initialization or production readiness.
