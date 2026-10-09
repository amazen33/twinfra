# ADR 0023: Bounded DeepSeek planning and disabled Spinifex GPU bursting

**Status:** Accepted for reference implementation; live enablement remains gated

**Date:** 2026-10-06

**Deciders:** vCloud platform owner and principal cloud-native architecture role

## Context

vCloud needs DeepSeek-assisted workflows, GPU batch admission and local-to-cloud
capacity through Spinifex while preserving deny-all, non-root runtime, CSI
storage and narrowly approved node exceptions. The owner selected a disabled
reference profile and corrected the platform region/selector to `vcloud`.
Spinifex supplies AWS-compatible infrastructure APIs, not a generic HPC Job CRD.
The requested H100/A100 hardware and site OS compatibility are unaccepted.

## Decision

Use Kueue 0.20.0 with MultiKueue for whole-job quota/admission and independent
worker-cluster dispatch; use JobSet 0.12.0 for the two-node reference. Manager
and worker quota stay zero and queues stay held. MultiKueue quota management
is Manual and automatic manager quota expansion is off. Use the currently
served, nondeprecated custom API versions and vendored CRD schemas.

The DeepSeek agent uses one bounded structured-output vLLM call and returns
answers or typed synthetic-workload proposals. It has no cloud credentials or
Kubernetes API token and cannot interpret generated shell commands/manifests.
A reviewed submitter owns fixed suspended workload templates. MultiKueue alone
owns execution. A separate read-only observer/capacity bridge rechecks trusted
pressure and reserved demand, then uses boto3/SigV4 for EC2 provisioning.

Keep the bridge disabled before all side effects. Gate enablement on exact HTTPS
endpoints, site/fabric/worker acceptance, short-lived CSI-mounted OpenBao sessions,
finite node count, cooldown and durable idempotency. Retain quota on uncertain
provider outcomes or expiry. Cleanup requires terminal Workload identity and
provider ownership checks followed by proven instance termination. Argo CD owns
configuration reconciliation; Tekton/Alertmanager signal the capacity bridge.

Provide an optional cluster-local Knative GPU vLLM example outside the Argo source.
This adds a scale-to-zero experiment alongside [ADR 0016's warm inference selection](adrs/0016-vllm.md).
The warm Deployment remains the latency-oriented default; this example needs
cold-start measurement and explicit Knative GPU/PVC feature acceptance. It does
not change production inference SLOs. Stage model weights at an exact revision.

Native Spinifex daemon/KVM/VFIO/OVN access belongs on dedicated accepted hosts.
The new public overlay and service gate are configuration references only; they
do not expand [ADR 0001's approved Kubernetes node scope](adr-0001-node-host-mounts.md).
Ubuntu 24.04 host compatibility and Kubernetes 1.36.5 worker parity must be proved
because current Spinifex installation/quickstart examples select other versions.

## Options considered and consequences

| Choice | Benefit | Cost / limitation |
| --- | --- | --- |
| Kueue + MultiKueue, selected | Explicit admission and remote Kubernetes job ownership | Separate worker cluster, controllers, quotas and kubeconfig lifecycle |
| Volcano | Stronger task scheduling controls for some MPI workloads | Another scheduler/ownership model; not selected for this reference |
| Direct agent-to-cloud/job APIs | Fewer integration components | Would grant model-mediated authority; excluded |
| Native Spinifex EC2 capacity bridge | Standard SDK/SigV4 and durable resource bounds | Does not implement worker enrollment or all AWS service semantics |
| Knative GPU scale-to-zero example | Idle capacity experiment | GPU/model cold starts and feature/security prerequisites |

Kueue admission and wait-for-ready are not a guarantee of instantaneous MPI gang
scheduling. Tight jobs need accepted topology, readiness and fabric benchmarks;
they do not span a WAN. The fallback four-GPU PCIe profile is unmapped. Spinifex
1.21.0 is AGPL-3.0; retain attribution and review the commercial distribution and
service model. Application/runtime containers remain non-root without new node
exceptions. OCI builds, real GPU execution, provider calls and live deployment
are separate acceptance gates.

## Validation and acceptance

Run `make module5b-validate module5b-test module5b-alerts` and the full repository
suite. Offline validation reproduces nine CRD schemas, checks frozen pod policy,
renders/lints the pinned Kueue chart and requires strict kubeconform coverage.
Tests exercise disabled zero-I/O paths, pressure/demand rejection, actual SDK
request validation/signing, durable/concurrent budgets, cleanup ownership and
local mTLS identities. Follow the [activation prerequisites](../module-5b/README.md#activation-prerequisites)
before creating the optional inference service or enabling any queue/bridge.

Sources: [Spinifex 1.21.0](https://github.com/mulgadc/spinifex/tree/v1.21.0),
[host installation](https://docs.mulgadc.com/docs/install-multi-node),
[MultiKueue](https://kueue.sigs.k8s.io/docs/concepts/multikueue/),
[DeepSeek model](https://huggingface.co/deepseek-ai/DeepSeek-R1-Distill-Qwen-32B).
