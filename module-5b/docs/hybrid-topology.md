# Twinfra hybrid HPC flow

```text
Client + Keycloak OIDC bearer token
                 |
                 v
       APISIX: issuer / audience / scope / rate limit
                 | HTTPS + workload mTLS
                 v
       DeepSeek planning agent (no API/cloud credentials)
          |                          |
          | verified internal TLS    | bounded proposal (execution disabled)
          v                          v
  Private Knative vLLM       Reviewed workload submitter
  pinned offline model       fixed suspended Job / JobSet
  dedicated inference GPU             |
                                      v
                              LocalQueue in hpc-compute
                                      |
                              ClusterQueue (zero / held)
                                      |
                     Kueue admission + MultiKueue ownership
                                      |
                     independent Spinifex worker K8s cluster
                                      |
                      whole-node GPU jobs, one fabric domain
                                      |
                    results / approved CSI and dataset storage

Prometheus: sustained CPU/GPU/memory + pending demand
          |
          v
Alertmanager mTLS webhook ----+     Tekton mTLS capacity Task
                             |              |
                             +--------------+
                                    |
                                    v
                     Capacity bridge (feature disabled)
                     recheck Workload + fresh metrics
                     CSI durable ledger / global max 4
                                    |
                     OpenBao CSI --> short-lived AWS session
                                    |
                     HTTPS + AWS SDK / SigV4, EC2 API
                                    |
                         native Spinifex AWS gateway
                                    |
                     dedicated KVM/VFIO compute hosts
                                    |
                     accepted worker image joins worker K8s

Argo CD --> reviewed configuration; automatic sync disabled
Prometheus/Grafana <-- pipeline outcomes / admission / cleanup alerts
```

This diagram distinguishes job placement from capacity provisioning. Spinifex
runs native infrastructure services; MultiKueue dispatches Kubernetes jobs into
an independent worker cluster. The manager is never its own MultiKueue worker.
APISIX exposes the proposal agent, not the capacity API or model service.
The eight-GPU H100 profile and four-node ceiling describe intended capacity.
No hardware, controller, endpoint or GPU performance was accepted by this diagram.
MPI/NCCL traffic remains within an accepted fabric; no WAN MPI performance claim.
