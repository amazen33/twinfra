# WO-31 bare-metal cairo-1 acceptance · 2026-10-12

Environment: `twinfra-dev-cairo-1` on the Dell, namespace
`twinfra-platform-services`. Decision: [ADR-0048](../adr/0048-cairo-1-on-bare-metal-host.md).
Work order: [WO-31 with Amendments 1–3](../work-orders/WO-31-bare-metal-cairo-1.md).

## Static scope

Scripts, generated profiles, mocked transports, pure storage/policy decisions,
masked main-byte comparisons and CI only. No SSH, bootstrap, VM provisioning,
software installation, host firewall/storage mutation or GitHub-settings changes
were performed by Codex. Host-check fixture: Ubuntu 24.04, x86-64/VT-x/KVM,
31 GiB RAM, 80 GiB free root, 120.5 GiB free VG, synchronized time,
192.168.1.3 on eno1 and integrity lockdown. These are **synthetic inputs**.
The pre-bootstrap fixture passes with free reserved ports; the post-bootstrap
fixture passes only with all Amendment 1 identity and process-owner inputs.

WO-31 Amendment 2 changes Module -1's BPF setup and containerd mount dependency.
Production renders change only those embedded blocks and derived script SHA256
metadata (plus the regenerated gzip). The cairo-2 seed also embeds that fix;
its shared pinning agent and dev log-cap allowances from Amendment 1 remain.
Masked comparisons against pre-WO-31 main `968f336` and Amendment 2 base
`a8f4f43` verify remaining bytes. No new dependencies.

Amendment 3 changes only the embedded staging agent in the cairo-2 seed against
merged PR #41 main `a7512ed`; production renders and all image locks remain
byte-identical. Fake CRI lookup uses digest-only names for digest references;
staging preserves the old name and pins both records. No live repair was run.

## Live acceptance

| Gate | Result | Evidence to record |
| --- | --- | --- |
| Dell ePSA Thorough memory test | Pending | Owner console result |
| 24-hour soak / all Pods Running / no freeze | Pending | Start/end UTC and observed state |
| Kernel machine-check / hung-task errors | Pending | Owner-reviewed journal summary |
| host-check / SSH hardening / integrity lockdown | Pending | Real sanitized report and effective settings |
| Amendment 2 BPF migration / incomplete bootstrap re-run | Pending | Exact legacy unit disabled/removed; existing bpffs retained; containerd starts; new verified staging receipt; bootstrap images staged and kubeadm init completes |
| LAN 22/6443 reachable, 2379/10250 blocked | Pending | Laptop connection results |
| Argo CD syncs from GitHub through the host firewall | Pending | Firewall confirmed/enabled; GitHub repository fetch and successful sync with Synced/Healthy application status |
| Node Ready / Cilium healthy under lockdown | Pending | Actual status and deny-policy proof |
| Actual containerd version and every image pinned | Pending | `containerd --version`; CRI pinned status |
| Amendment 3 Cilium resolves staged digest-only names locally | Pending | Normalized `crictl inspecti` reports expected digest and pinned true; `kubectl -n kube-system get events` shows no Pulling events for Cilium agent/operator/envoy images |
| PostgreSQL 20 GiB LV / UUID mount / ownership | Pending | LV size, mount options, 26:26 and 0700 |
| All dev overlay Pods Running | Pending | Namespace inventory |
| etcd WAL fsync p99 under 10 ms | Pending | Metric interval and measured value, even if target missed |
| API through stable name / HTTPS console and Keycloak | Pending | Laptop checks and browser result |

Source review confirms containerd 2.2.1's pin-label/CRI-field implementation.
Owner-provided Amendment 3 evidence reports containerd 2.2.1
(`2.2.1-0ubuntu1~24.04.3`) and crictl v1.36.0 on the Dell; Codex did not inspect
the host. Live digest-only lookup and no-Pulling acceptance remain Pending.
OpenBao remains sealed and GPU/HPC/Spinifex remain disabled. This receipt does
not claim HA, production readiness, backup or DR acceptance.

## Tester sign-off

Tester: Ahmed Mazen (@amazen33), enterprise and cloud tester; QoS tester
Result: Pending
Date (UTC):
QoS targets checked:
Notes:
