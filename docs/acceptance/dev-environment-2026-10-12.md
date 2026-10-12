# WO-31 bare-metal cairo-1 acceptance · 2026-10-12

Environment: `twinfra-dev-cairo-1` on the Dell, namespace
`twinfra-platform-services`. Decision: [ADR-0048](../adr/0048-cairo-1-on-bare-metal-host.md).
Work order: [WO-31 with Amendment 1](../work-orders/WO-31-bare-metal-cairo-1.md).

## Static scope

Scripts, generated profiles, mocked transports, pure storage/policy decisions,
masked main-byte comparisons and CI only. No SSH, bootstrap, VM provisioning,
software installation, host firewall/storage mutation or GitHub-settings changes
were performed by Codex. Host-check fixture: Ubuntu 24.04, x86-64/VT-x/KVM,
31 GiB RAM, 80 GiB free root, 120.5 GiB free VG, synchronized time,
192.168.1.3 on eno1 and integrity lockdown. These are **synthetic inputs**.
The pre-bootstrap fixture passes with free reserved ports; the post-bootstrap
fixture passes only with all Amendment 1 identity and process-owner inputs.

Module -1 and production renders are unchanged. Only the shared pinning agent
and dev log-cap blocks change the cairo-2 seed; masked comparisons against
pre-WO-31 main `968f336` verify all remaining bytes. No new dependencies.

## Live acceptance

| Gate | Result | Evidence to record |
| --- | --- | --- |
| Dell ePSA Thorough memory test | Pending | Owner console result |
| 24-hour soak / all Pods Running / no freeze | Pending | Start/end UTC and observed state |
| Kernel machine-check / hung-task errors | Pending | Owner-reviewed journal summary |
| host-check / SSH hardening / integrity lockdown | Pending | Real sanitized report and effective settings |
| LAN 22/6443 reachable, 2379/10250 blocked | Pending | Laptop connection results |
| Argo CD syncs from GitHub through the host firewall | Pending | Firewall confirmed/enabled; GitHub repository fetch and successful sync with Synced/Healthy application status |
| Node Ready / Cilium healthy under lockdown | Pending | Actual status and deny-policy proof |
| Actual containerd version and every image pinned | Pending | `containerd --version`; CRI pinned status |
| PostgreSQL 20 GiB LV / UUID mount / ownership | Pending | LV size, mount options, 26:26 and 0700 |
| All dev overlay Pods Running | Pending | Namespace inventory |
| etcd WAL fsync p99 under 10 ms | Pending | Metric interval and measured value, even if target missed |
| API through stable name / HTTPS console and Keycloak | Pending | Laptop checks and browser result |

Source review confirms containerd 2.2.1's pin-label/CRI-field implementation;
the Dell's installed package/version and runtime behavior remain unverified.
OpenBao remains sealed and GPU/HPC/Spinifex remain disabled. This receipt does
not claim HA, production readiness, backup or DR acceptance.

## Tester sign-off

Tester: Ahmed Mazen (@amazen33), enterprise and cloud tester; QoS tester
Result: Pending
Date (UTC):
QoS targets checked:
Notes:
