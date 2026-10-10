# DevSecOps review of the WSL corrections

Review date: **2026-10-07**. Repository: `amazen33/twinfra`. Runtime scope:
`vcloud-wsl-local`, Ubuntu 26.04 WSL2, mirrored networking, six CPUs and about
20 GiB RAM. Production `vCloud-prod-01` retains its Ubuntu 24.04/kubeadm contract.

This review consolidates implementation, operational documentation and evidence.
Merging the implementation PR does not complete the pending platform or release
milestones. A Ready operator, HTTP health response or working dashboard is not
evidence of database initialization, GitOps synchronization or production readiness.

## Correction traceability

| Correction | Implementation and runbook | Verification / milestone boundary |
| --- | --- | --- |
| Offline image availability and mirror paths | [Registry ADR-0028](adr/0028-air-gapped-registry.md), [image-pull runbook](troubleshooting/image-pull-failures.md), `tools/airgap.py`, `tools/node_registry.py` | Strict rendered schemas, explicit `IfNotPresent`, immutable Argo digest, private API roots and cache/DNS/TLS failure tests; live authenticated mirror and cold-cache bootstrap remain pending |
| Mandatory diagnostic CLIs | [Prerequisites](prerequisites.md), host/WSL bootstrap | `jq`, `curl`, `iproute2` and pinned `kubectl` availability; WSL mark repair also requires `nftables` |
| Health ingress and restart recovery | [Probe runbook](../deploy/network/platform-probes/README.md), both policies and recovery scripts | Three selected workloads; TCP 9443/8084/8082; dynamic PodCIDRs; server dry-run before writes; apply → restart → rollout wait → HTTP/readiness/stable-restart verification |
| Repo-server full health DNS failure | [RCA](troubleshooting/argocd-repo-health-wsl.md), `tools/wsl_platform.py`, `tools/wsl_proxy_marks.py`, systemd service/timer | Exact Redis/SRV DNS names and local NXDOMAIN answer; two verified proxy mark return rules; unchanged five-second full health probe |
| Browser access | [Service access](service-access.md), `lab/wsl/access.sh`, `lab/wsl/verify-access.ps1` | Loopback-only Core UI and HTTP smoke; Windows HTML, JavaScript and API checks; separate GitOps sync status |
| Namespace and controller ownership | [WSL guide](WSL_SETUP_GUIDE.md), [platform acceptance](../lab/wsl/PLATFORM.md) | Pre-create installation namespace; relocate embedded RBAC subjects; avoid overlapping Argo installations; current discovery binding mismatch remains open |

## Findings and disposition

- **Fixed:** stale documentation described controller health as blocked and a
  Host Firewall disablement approval as the next gate. The proposal is now
  explicitly superseded; Cilium Host Firewall, native routing, L7 proxy,
  Bandwidth Manager and kube-proxy replacement remain enabled.
- **Fixed:** the edited ingress-only probe policy and older tests disagreed.
  Both policies now identify their WSL scope. Tests verify the actual ingress
  contract, separate component dependency egress and preservation of an injected
  custom egress clause during CIDR rendering.
- **Fixed:** CI's prior-PR inventory stopped at #2 and omitted the roadmap
  automation suite. The inventory now pins verified merge commits #1–#3, #5
  and #6; optional-feature checks reject partial implementations without
  requiring future features in earlier revisions.
- **Recorded exception:** the native fallback permits every source on the three
  selected probe ports. The Cilium rule retains `world` and the locally edited
  `cluster` allowance. These are local probe exceptions, not kubelet-only or
  production rules. Metadata labels are documentation, not an admission guard;
  the apply helper rejects Nodes outside the local-validation profile. Explicit
  deny rules still take precedence. No general egress allowance was added.
- **Fixed:** example domains, ClusterIPs and ephemeral Pod IPs were presented
  alongside potential browser URLs. The access runbook separates tested Windows
  endpoints from undeployed services and records process lifetime and rollback.
- **Open:** the live `argocd-application-controller` ClusterRoleBinding targets
  the `argocd` ServiceAccount, while the active controller is in
  `platform-services`. Cluster discovery is denied and the Application reports
  `ComparisonError` / `Unknown`. Restore the vetted single-owner RBAC and prove
  sync and self-healing; do not grant `cluster-admin` as a workaround.
- **Open:** no CNPG Cluster or PVC is initialized. Local database SQL, verified
  TLS, pgvector, persistence and bounded resource growth remain unaccepted.
- **Open:** GitHub reports `main` as unprotected and lists no repository rulesets.
  The workflow exposes `vCloud PR gate`, but GitHub does not currently require
  it before merging. This review waits for fresh checks explicitly; configure
  the repository ruleset separately before relying on enforced merge governance.

The review does not apply new storage, deploy another controller, change Windows
Firewall rules, disable Cilium features, enable GPU/HPC, expose an admin session
on the LAN or publish credentials.

## Evidence and repeatable checks

Public runtime evidence is retained in
[`correction-review-validation.json`](correction-review-validation.json).
Detailed local logs are under `.build/correction-review/`; hosted CI uploads
per-check logs and summaries as described in the [CI guide](github-actions-tests.md).
Historical evidence files retain their original scope and date.

```bash
# Owned WSL node: read-only health and isolation acceptance.
cd /mnt/e/vCloud
sudo env KUBECONFIG=/etc/vcloud-wsl/kubeconfig.yaml KUBE_CONTEXT=vcloud-wsl-local \
  bash deploy/network/platform-probes/apply-and-verify.sh --verify-only
sudo bash lab/wsl/test-network.sh
sudo python3 tools/wsl_proxy_marks.py --plan
sudo bash lab/wsl/access.sh status
```

```powershell
# Windows: verify the actual browser route, assets, APIs and smoke response.
Set-Location E:\vCloud
& .\lab\wsl\verify-access.ps1
```

Offline CI runs schema, Helm/Kustomize, policy, ShellCheck, Cloud-Init drift,
architecture and module regression gates. It does not run these live commands
or use the private kubeconfig. A WSL reboot was not performed during this review;
boot recovery, authenticated mirror pulls and cold-cache isolation need separate
acceptance. GPU inference, secrets/IAM integration, full SIT, load, multi-node,
backup/restore and production release gates remain open.

## Milestones and PR disposition

[MILESTONES.md](../MILESTONES.md) retains the roadmap merged through PRs
[#5](https://github.com/amazen33/twinfra/pull/5) and
[#6](https://github.com/amazen33/twinfra/pull/6), and maps these corrections to
its local-runtime, platform-services and verification gates. All four GitHub
release milestones remain open:

| GitHub milestone | Existing open acceptance issues |
| --- | --- |
| `v0.1.0-alpha` | [#13](https://github.com/amazen33/twinfra/issues/13): align the bootstrap target and complete live foundation acceptance |
| `v0.2.0-beta` | [#15](https://github.com/amazen33/twinfra/issues/15): live GitOps and platform-services integration |
| `v0.3.0-rc` | [#12](https://github.com/amazen33/twinfra/issues/12): drift/failure recovery; [#14](https://github.com/amazen33/twinfra/issues/14): SIT/compliance acceptance |
| `v1.0.0-GA` | [#16](https://github.com/amazen33/twinfra/issues/16): release checks; [#17](https://github.com/amazen33/twinfra/issues/17): multi-node recovery; [#18](https://github.com/amazen33/twinfra/issues/18): performance |

PRs #1–#3, #5 and #6 were already merged when
this audit began; [PR #4](https://github.com/amazen33/twinfra/pull/4) carries the
remaining WSL/reference implementation and corrections. Its fresh candidate and
integration checks must pass before merge; the old green run at `1ab9714` does
not validate these changes.

PR #4 is assigned to the local-foundation release milestone. The active lab
Application still tracks `codex/wsl-local-bootstrap`; keep that branch until a
separately verified GitOps cutover to `main`, even after the implementation PR
is merged. Closing the PR is an implementation decision, not completion of its
broader runtime milestone.

The task's Issue #412 reference does not resolve to an issue in this repository
at this review. It is retained as supplied context, not a claim of GitHub issue
closure. No unfinished runtime milestone or issue is closed by merging PR #4.

Primary semantics: [Cilium entities and CIDRs](https://docs.cilium.io/en/stable/security/policy/layer3/),
[containerd registry host configuration](https://github.com/containerd/containerd/blob/v2.2.2/docs/hosts.md)
and [Argo CD Core access](https://github.com/argoproj/argo-cd/blob/v3.5.3/docs/operator-manual/core.md).
