# WSL platform startup recovery — 2026-10-08

Scope: the owned single-node `vcloud-wsl-local` lab, mirrored WSL2,
Ubuntu 26.04 / Microsoft kernel 6.18, 20 GiB RAM and six vCPUs. This is local
recovery evidence, not production availability or unattended reboot acceptance.

## Initial failure and repair

The operator reported platform-wide ContainerCreating/Init states, old
Completed PostgreSQL/Argo controller Pods and Prometheus StartError. The Node
and Cilium Pod appeared Ready. Cilium still selected `eth1`, although the
actual route and Node InternalIP `192.168.1.9` were on `eth2`; its logs reported
`direct routing device eth1 has no usable addresses`. Pod sandbox creation
failed with CNI endpoint HTTP 429. Containerd/K3s were active, with no observed
resource pressure. The retained PostgreSQL volume remained mounted on ext4.

The existing manual runbook re-rendered the locked Cilium 1.20.2 chart with
the observed address/device, passed strict schemas (47 resources valid,
zero invalid/errors/skips) and the frozen node-agent audit, upgraded the
existing Helm release and explicitly restarted the agent. Workloads recovered
without deleting database storage or changing application image policies.

## Failed prevention trial and rollback

Automatic device selection was trialled after initial acceptance. It selected
both `eth0` and `eth2`, and localhost TCP failed with `No route to host`.
The full test suite detected the failure. The trial's source edits were
discarded and Helm was rolled back to the validated explicit-interface revision.
Because failed localhost access blocked containerd exec streaming/controller
progress, the exact verified Cilium container was reloaded with the restored
public device setting. Its effective status then showed only `eth2`.

Mirrored routing still sent Linux loopback connections and incoming Windows
SYNs through table 127 / `loopback0` before local delivery. A temporary blanket
local rule fixed Linux but broke Windows replies; it was removed. An attempted
packet-mark return rule did not fix the failure and was also removed.
The final narrowly scoped helper uses connection marking for Linux-originated
127.0.0.1 flows and local delivery of loopback0 ingress, preserving Windows
reply routing. Owned port-forward units were restarted to clear stale streams.
The [runbook](../WSL_SETUP_GUIDE.md#mirrored-localhost-recovery-after-cilium-reconfiguration)
records its guards, idempotency and rollback. This does not establish a general
WSL/kernel root cause beyond the measured routing behavior.

## Executed final acceptance

| Check | Observed result |
| --- | --- |
| Cilium | 1/1 Ready; native Pod routing, legacy host routing, full proxy replacement, BPF masquerade, socket LB, host firewall and bandwidth manager retained on `eth2` |
| Platform Deployments | All 16 desired single replicas Ready |
| GitOps | Both Applications Synced/Healthy at `cf5ca2b412c51dcf7ab44a9458f56ea387174ecc` before this documentation change |
| PostgreSQL | pgvector 0.8.2, verified TLS and retained marker passed |
| Ten platform gates | Zero failures at 11:41:38 UTC; GitOps, database, demo ingress, metrics, trace, Grafana, Keycloak TLS/OIDC, restricted PSS, disabled GPU/HPC and OpenBao gate |
| Deny-all | DNS and allowed control passed; unauthorized Service and direct Pod blocked; six matching Cilium policy drops at 11:52:06 UTC, after the final loopback repair |
| Node health probes | Argo controller 8082, repo server 8084 full health and CNPG 9443 HTTP 200; Ready and stable restart counters across two polls |
| Windows APISIX | Host-routed CPU demo HTTP 200 |
| LocalStack, WSL/Windows | Community 4.14.0; S3, EC2, IAM and DynamoDB health states `running` |
| Windows endpoint regression | APISIX demo, LocalStack health, Grafana health, Prometheus readiness and OpenBao init status all HTTP 200 |
| Recovery guard | Six unit/mutation tests passed; two live `--apply` reruns were idempotent and verified bidirectional Linux TCP |
| CI controls | 30 tests passed in Linux, including incomplete recovery-bundle rejection and historical-revision compatibility |
| Full offline CI | 62 gates and 508 tests passed; strict kubeconform, ShellCheck, Helm renders/lints, architecture, policy and application suites included |

The probe script's existing CNPG `curl -k` verifies reachability only; its
certificate trust is not established by that probe. Database and Keycloak
acceptance separately verified TLS without skipping certificate checks.

## Remaining gates

OpenBao remains uninitialized under the operator PGP-key gate. GPU/vLLM and
Spinifex offloading remain disabled. The new loopback helper is manual; Cilium
startup can change local-table rule priority, so reapply/check it after such
changes. Existing transient forward units do not guarantee recovery after WSL
restarts. Do not mark unattended reboot, production release, SPIFFE attestation
or durable trace storage complete based on this receipt.
