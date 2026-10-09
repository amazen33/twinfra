# Module 5b: Twinfra agent and disabled hybrid HPC reference

This module supplies a DeepSeek planning agent, a bounded EC2 capacity bridge,
Kueue/MultiKueue queues, GPU workload examples and telemetry for
`vCloud-prod-01`. It is a **disabled reference**, not a deployed HPC service.
`SPINIFEX_OFFLOAD_ENABLED=false`, replicas are zero, every GPU/CPU/memory quota
is zero, queues are held, Jobs/JobSets are suspended, the PipelineRun is pending
and Argo CD automatic sync is off. Model output cannot submit a job or provision
resources. Creating the optional Knative example requires separate acceptance.

The platform identity is `vcloud`; the region is `vcloud-hpc-1` and the offload
selector is `vcloud.io/offload-target: spinifex-hpc`. The explicitly supplied
provider address `ec2.spinifex.pcloud.example.com` is preserved.

| Deliverable | Source |
| --- | --- |
| Disabled profile, four-node global budget | [reference-profile.json](reference-profile.json) |
| Agent/bridge deployments and CSI state | [workloads.yaml](manifests/workloads.yaml) |
| Manager queues and MultiKueue references | [queues.yaml](manifests/queues.yaml) |
| Independent worker queues and fabric topology | [worker/queues.yaml](worker/queues.yaml) |
| OpenBao CSI identity and observer RBAC | [integration.yaml](manifests/integration.yaml), [role.json](openbao/role.json), [policy.hcl](openbao/policy.hcl) |
| APISIX OIDC, gateway TLS and upstream mTLS | [gateway.yaml](manifests/gateway.yaml) |
| Deny-all and narrow reciprocal Cilium rules | [network.yaml](manifests/network.yaml) |
| Tekton trigger Task/Pipeline and held run | [pipeline.yaml](manifests/pipeline.yaml), [pipelinerun.yaml](examples/pipelinerun.yaml) |
| Paused Argo CD Application and AppProject | [application.yaml](argocd/application.yaml) |
| GPU Job and two-node JobSet examples | [job.yaml](examples/job.yaml), [jobset.yaml](examples/jobset.yaml) |
| Private GPU Knative model service | [vllm.knative.yaml](examples/vllm.knative.yaml) |
| Metrics, recording rules and alerts | [observability.yaml](manifests/observability.yaml), [Alertmanager owner snippet](config/alertmanager-receiver.reference.yaml) |
| Native host partial configuration | [public overlay](host/spinifex-public-overlay.toml), [service gate](host/spinifex-daemon-gate.conf), [acceptance inventory](host/node-integration.json) |
| API and integration contract | [webhook-spec.md](api/webhook-spec.md) |
| Architecture and commercial summary | [topology](docs/hybrid-topology.md), [summary](docs/platform-summary.md), [ADR 0023](../docs/adr/0023-module-5b-hybrid-hpc.md) |

## Version and capacity contract

Selected releases are Spinifex 1.21.0, Kueue 0.20.0, JobSet 0.12.0, vLLM 0.31.0,
Knative 1.23.0 and Kubernetes 1.36.5. Upstream sources, CRD schemas and the Helm
chart are checksum-locked in [artifacts.lock.json](artifacts.lock.json).
Kueue's currently served API is `kueue.x-k8s.io/v1beta2`; JobSet uses its currently
served `jobset.x-k8s.io/v1alpha2`. These custom APIs are not deprecated. Deprecated
Kueue v1beta1 is not used. No missing schemas are skipped.

The H100 profile requests eight whole GPUs per batch node, 80 GB each, with a
desired 900 GB/s NVLink and 100 Gb/s RoCE/SR-IOV fabric. Four burst nodes would
represent 32 GPUs; that is a reference ceiling, not installed capacity.
`p5.48xlarge` is a reference mapping whose site acceptance is still false. The
four-GPU A100 PCIe fallback has no accepted instance type and is never selected
automatically. An eight-GPU SXM instance type is not a substitute for that profile.

[Spinifex](https://github.com/mulgadc/spinifex/tree/v1.21.0) runs a native
`spx service spinifex start` daemon and exposes AWS-compatible APIs. This module
does not invent a Spinifex Kubernetes node-agent CRD or a `/jobs` HTTP endpoint.
Its controller DNS name and port are a site gateway reference, not an installed
Spinifex controller. Current [host installation instructions](https://docs.mulgadc.com/docs/install-multi-node)
document Ubuntu 26.04/Debian 13; compatibility on the requested Ubuntu 24.04 is
unaccepted. The [EKS quickstart](https://docs.mulgadc.com/docs/eks-quickstart)
uses Kubernetes 1.32, so worker parity with 1.36.5 also needs evidence.

## Agent and execution ownership

The agent makes one structured model request per API invocation, with a maximum
1024 generated tokens, 12000 prompt characters and a request step budget at most
four. It accepts an answer or a typed simulation proposal: selected H100 profile,
one to four nodes and the synthetic dataset. It has no Kubernetes token, cloud
credentials, shell tool or arbitrary manifest/image/URL tool. The `steps` field
is a caller budget ceiling; this reference performs one planning step.

The agent connects to the cluster-local vLLM Knative service over verified TLS.
The model is `deepseek-ai/DeepSeek-R1-Distill-Qwen-32B`, revision
`711ad2ea6aa40cfca18895e8aca02ab92df1a746`, served as
`deepseek-r1-distill-qwen-32b`. Its weights must be staged and verified on the
`vcloud-deepseek-models` CSI claim before the example is created. No runtime
Hugging Face download or remote-code execution is configured. GPU inference
uses a dedicated inference node, separate from whole-node batch admission.
The vLLM 0.31.0 [structured reasoning interface](https://docs.vllm.ai/en/v0.31.0/features/structured_outputs/#reasoning-outputs)
uses `--reasoning-parser deepseek_r1`; request/output logging is explicitly disabled
with its current CLI flags. A real model smoke test remains pending.

An operator or reviewed workload submitter converts a proposal to the fixed,
suspended Job/JobSet template. Kueue owns quota/admission and MultiKueue owns job
execution in an independent Spinifex worker Kubernetes cluster. The capacity
bridge can only observe manager Workloads; it cannot create Jobs or edit quota.
The JobSet example exercises GPU allocation on two nodes independently. It is
not a distributed-training benchmark. A real NCCL/MPI application, fabric test,
dataset staging and scoped worker traffic policy are subsequent acceptance
steps. `NCCL_IB_DISABLE=1` keeps unaccepted RDMA out of the reference exercise.
Kueue admission and wait-for-ready controls do not guarantee simultaneous MPI
process scheduling. A tightly coupled job stays inside one accepted fabric domain.

## Trigger and credential contract

CPU/GPU saturation must exceed 85%, or memory usage must reach 85% of defined
limits, over five minutes. Capacity also requires a Workload that has reserved
manager quota, has waited at least 120 seconds and is not admitted or finished.
The bridge refetches all three metric series from the accepted Prometheus backend,
rejects missing/ambiguous/stale samples and independently rechecks the Workload.
Alertmanager sends a wake-up signal; Tekton sends an exact Workload request.
Argo CD reconciles reviewed configuration and never serves as a metrics scheduler.

The CSI-mounted OpenBao KV object `kv/data/vcloud/spinifex`, key `credentials`,
must contain a JSON object with `access_key_id`, `secret_access_key`,
`session_token` and epoch `expires_at`. The site credential issuer supplies a
short-lived provider session; this reference does not claim an OpenBao AWS
dynamic-secrets engine is compatible with Spinifex IAM. Mounts stay in tmpfs,
no Kubernetes Secret synchronization is configured for AWS credentials, and
the agent never receives them. Sessions must remain valid at least 60 seconds
and expire within one hour. SDK credentials are explicit, with no ambient
environment, instance-metadata or profile fallback.

The supplied internal `http://...:3000` URL is stored as the disabled reference.
Enabling the bridge with it fails closed. Activation requires verified HTTPS
at the exact external endpoint, or the internal DNS name on port 3000, with
mounted private CA trust. No `-k`, TLS bypass or redirects are supported.
EC2, EKS and STS clients use standard boto3/SigV4 with region `vcloud-hpc-1`.
The active bridge implementation uses EC2 `RunInstances`, `DescribeInstances`
and `TerminateInstances`; EKS/STS operation parity remains a site test.

## Build and offline validation

Run from the repository root with the pinned test dependencies and tools:

```bash
# Connected artifact preparation, followed by an offline transfer to the lab.
python3 tools/stage_module5b.py --download
python3 -m pip install --require-hashes --no-index \
  --find-links=.build/module-5b/wheels -r module-5b/requirements.txt

# These commands never apply resources or contact Spinifex.
make module5b-wheels module5b-render module5b-validate module5b-test module5b-alerts

# Optional reviewed image builds; scan and publish their explicit versions/digests.
docker build --network=none -f module-5b/images/agent-bridge.Dockerfile \
  -t registry.vcloud.example.com/vcloud/agent-bridge:1.0.0 .
docker build --network=none -f module-5b/images/worker.Dockerfile \
  -t registry.vcloud.example.com/vcloud/hpc-reference-worker:1.0.0 .
```

The agent Dockerfile and the Module 3 tooling image consume seven hash-locked
offline wheels. [wheel lock](python-wheels.lock.json) and
[requirements](requirements.txt) must agree. Host/CI validation still needs the
repository's pinned PyYAML/jsonschema tooling. Unit tests use real local TLS
sockets with ephemeral certificates, real SQLite state, SDK request validation
and SigV4 signing; provider responses are Stubber fixtures. They do not prove
GPU execution, provider capacity, queue scheduling or distributed performance.
GitHub's optional gate tests this module when present in a revision. Hosted
acceptance is established by the selected commit's workflow result, independently
of earlier local validation or the original workflow-only PR.

## Activation prerequisites

1. Accept dedicated native Spinifex host OS, KVM/VFIO isolation, OVN/br-wan/IPsec
   ownership and daemon capabilities separately from the approved Kubernetes
   node exception. The public TOML is a partial overlay, never a replacement
   for the site's full native configuration. The drop-in gate is not installed.
2. Accept the physical H100 inventory, fabric topology, GPU passthrough and
   a credential-free, signed worker image. Its site bootstrap must obtain
   short-lived cluster enrollment credentials securely and join the independent
   worker cluster at Kubernetes 1.36.5. Run CUDA/NCCL, Cilium, CSI and failure tests.
3. Install and audit Kueue/JobSet controllers under their own reviewed profiles.
   [Kueue values](values/kueue.yaml) are an installer reference, outside this
   Application. Review controller RBAC and API-server/webhook/DNS/worker network
   rules in `kueue-system`/`jobset-system`; the workload rules do not install them.
   MultiKueue's kubeconfig Secret belongs to `kueue-system`, key `kubeconfig`.
4. Supply CSI claims/classes, model revision provenance, mirrored scanned images,
   image-pull credentials, private TLS identities and the public trust ConfigMap.
   Merge [Knative features](patches/knative-gpu-features.mergepatch.yaml) through
   the existing owner and verify internal encryption; GPU cold starts need a
   separate latency test. No inference Service is included in the Argo path.
5. Configure OpenBao Kubernetes auth/CSI rotation with the Module 4a owner. Supply
   APISIX and bridge TLS Secrets, Prometheus mTLS, Alertmanager receiver/client
   identity and namespace label through their current owners. RBAC and CSI
   service-account audience must match actual API-server and provider settings.
6. Prove AWS API authentication, launch idempotency and cleanup after partial
   failure. Keep one bridge replica and a durable single-writer CSI ledger.
   Only a Finished Workload plus verified instance ownership/termination frees
   capacity. Expiry alone never deletes an active training job or releases quota.
7. Review finite manager quota for capacity reservation and worker quota derived
   from ready, accepted hardware. Both stay zero/held here. The bridge never
   expands quota or releases queues. Deliberately enable the independently
   reviewed site profile, Task, replicas, queues and GitOps settings only after
   positive/negative tests; flipping one environment variable is insufficient.

Spinifex 1.21.0 is AGPL-3.0; its [upstream license](vendor/LICENSE.gz) is retained.
The commercial deployment model and any modifications need license review.
No proprietary relabeling or unrestricted AWS service parity is claimed.
