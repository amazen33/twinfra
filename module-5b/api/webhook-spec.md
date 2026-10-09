# Twinfra capacity and agent API contract

All API endpoints require TLS 1.3 and a certificate issued by the mounted CA.
The certificate must contain one URI SAN, with exact role identity:

| Endpoint | Method | Accepted peer |
| --- | --- | --- |
| `/v1/agent/runs` | POST | `spiffe://vcloud/platform/apisix` |
| `/hooks/capacity` | POST | `spiffe://vcloud/hpc/tekton-trigger` or `spiffe://vcloud/platform/alertmanager` |
| `/hooks/alerts` | POST | `spiffe://vcloud/hpc/tekton-trigger` or `spiffe://vcloud/platform/alertmanager` |

APISIX validates the Module 4b Keycloak issuer, audience, RS256 and `function.read`
scope before calling the proposal-only agent over mTLS. The agent does not
interpret client-supplied identity headers. Capacity endpoints are not exposed
through APISIX. The health/metrics port 9091 carries no request or credential data.

Bodies require `Content-Type: application/json`, exactly one Content-Length and
at most 65536 bytes. Duplicate JSON keys, non-finite numbers, transfer encoding
and redirects are rejected. At most 16 connections and 16 request handlers run
concurrently; handshakes, request reads and upstream calls have timeouts.

## Agent request

```json
{"prompt":"Propose a synthetic simulation on two accepted H100 nodes","steps":1}
```

One model invocation returns a validated answer or a proposal:

```json
{"status":"proposed","execution_enabled":false,"proposal":{"profile":"spinifex.gpu.h100.80gb.8x","nodes":2,"dataset":"synthetic"},"queue":"spinifex-hpc-burst"}
```

The proposal cannot become a shell command, URL, arbitrary image or manifest.
Model/provider exceptions produce generic dependency errors and never an unsafe
execution fallback. User prompts, output, credentials and client certificates
are excluded from application request logs. The budget field caps requested
steps at four; this reference performs one planning call.

## Capacity request

Replace the public example identifiers with a real Kueue Workload identity:

```json
{"request_id":"43bbdf22-4f51-4bf2-9af3-7b1fa7dc8bd3","workload_name":"reference-eight-gpu","workload_uid":"292360fb-30d1-439a-adce-e3373e438171","profile":"spinifex.gpu.h100.80gb.8x","nodes":1,"queue":"spinifex-hpc-burst"}
```

The bridge independently gets that Workload from the Kubernetes API. It must
belong to `hpc-compute`, match `vcloud.io/offload-target: spinifex-hpc`, reserve
manager quota, remain unadmitted and unfinished, and wait at least 120 seconds.
Each Pod requests eight GPUs and the sum of PodSet counts equals `nodes`.
All three accepted Prometheus samples must be fresh within 60 seconds, cover
five minutes and carry cluster `vCloud-prod-01`. CPU/GPU must exceed .85 or
memory must reach .85. No caller-provided utilization value is trusted.

Responses: `202 disabled` before any credential, ledger, Kubernetes or metrics
I/O; `202 held` for insufficient pressure; `202 provisioned` after a checked
EC2 response; `422` for invalid inputs/prerequisites or uncertain provider
outcome; `403` for unapproved URI identity; `503` for dependency/concurrency
failures. Disabled responses never reserve or provision capacity.

## Alertmanager request

The receiver accepts the actual Alertmanager webhook format; it does not expect
a custom capacity JSON object from Alertmanager:

```json
{"version":"4","receiver":"vcloud-hpc-capacity","status":"firing","alerts":[{"status":"firing","labels":{"alertname":"VCloudHPCBurstCandidate","cluster":"vCloud-prod-01","queue":"spinifex-hpc-burst"}}]}
```

Only matching firing alerts cause a pending Workload lookup. The first reserved
candidate in a bounded list is rechecked with current metrics; incompatible
whole-node demand fails closed. Alert values are a wake-up signal. Resolved or
foreign alerts are ignored. The [receiver snippet](../config/alertmanager-receiver.reference.yaml)
must be merged through the existing Alertmanager owner with its client TLS mount.

## Standard SDK and lifecycle

`runtime/engine.py:aws_client` constructs boto3 EC2/EKS/STS clients with explicit
region `vcloud-hpc-1`, exact accepted HTTPS endpoint, SigV4, mounted CA trust,
short-lived mounted credentials, five-second connection timeout, fifteen-second
read timeout and at most two SDK attempts. No ambient AWS environment credentials,
metadata credentials or HTTP proxy are used. Endpoint references are:

```text
disabled internal: http://spinifex-controller.hpc-compute.svc.cluster.local:3000
accepted external candidate: https://ec2.spinifex.pcloud.example.com
accepted internal candidate: https://spinifex-controller.hpc-compute.svc.cluster.local:3000
region: vcloud-hpc-1; signature: SigV4; services: ec2, eks, sts
credential file: /var/run/vcloud/spinifex/aws-credentials.json
```

The SDK builder is reusable for EKS/STS; the capacity engine only invokes EC2.
No operation coverage is inferred from SDK availability. The site must verify
EKS/STS routes, policies and session issuance against its actual gateway.

SQLite transactions reserve the global four-node budget before the first provider
call. Workload UID plus immutable launch/profile parameters determine a persisted
EC2 ClientToken. Retries across new alert/request IDs and process restarts reuse
that token; changed parameters and released Workloads cannot relaunch. Uncertain
outcomes retain quota. Burst creation has a ten-minute cooldown, including after
release. One writer uses a CSI-backed ReadWriteOnce ledger, WAL and full fsync.

Every minute, cleanup checks the exact Workload name/UID/namespace/queue. Only a
Finished Workload can trigger cleanup; provider instance type, identities and
`vcloud:cluster`, `vcloud:workload-uid`, `vcloud:managed-by` tags must all match.
Termination requests retain quota until DescribeInstances proves all selected
instances terminated. Missing or inconsistent inventory stays uncertain and
needs operator reconciliation. Lease expiry alerts but never destroys an active
job. Keep terminal Workloads until cleanup is confirmed; deleting them early
intentionally leaves capacity held. No generic provider error text is returned.

The bridge only provisions capacity. Worker image boot/enrollment, quota based
on ready nodes and MultiKueue workload placement belong to separate accepted
controllers/site owners. The worker cluster is independent of the manager.
