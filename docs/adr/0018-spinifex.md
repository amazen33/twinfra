# ADR-0018: Spinifex as an infrastructure provider for HPC capacity

**Status:** Superseded by [ADR-0029](0029-aws-compatible-enterprise-simulator.md), [ADR-0030](0030-licence-policy.md). Original record follows unchanged except for relocated links.

**Status:** Proposed  
**Date:** 2026-10-05  
**Deciders:** vCloud platform owner and Principal Architect  
**Selection:** Spinifex open-source cloud is required by Module 1.  
**Classification:** Constraint — selection required by Module 1; alternatives assess implementation, not an open component competition.
**Scope:** [SSoT and shared implementation contract](README.md).

## Context

vCloud needs local-to-cloud capacity for admitted HPC jobs. Spinifex exposes
AWS-compatible cloud infrastructure APIs and documents managed Kubernetes provisioning;
it is not, by that fact, a Kubernetes batch scheduler or a ready-made vCloud bursting
adapter. See the [project](https://mulgadc.com/spinifex) and
[EKS provisioning example](https://docs.mulgadc.com/docs/eks-quickstart).

## Decision

- Use Spinifex as a local/private infrastructure provider on **dedicated infrastructure
  hosts**, with Kubernetes workers in provisioned guests or a separately reviewed layout.
  Keep Spinifex host networking/storage ownership separate from Cilium Pod routing.
  Do not run hypervisor services as an application pod with unrestricted host access.
  Its multi-node topology is a separate infrastructure deployment; see
  [installation guidance](https://docs.mulgadc.com/docs/install-multi-node).
- In `hpc-compute`, implement an authenticated job API, durable job state and a proposed
  **admission/capacity adapter**. Kueue is the intended admission integration from the
  platform context, but its release, job-framework integration and adapter are additional
  implementation work. Slurm is an optional separately designed target; installing its
  client libraries does not create a Slurm control plane or a working scheduler.
- The adapter observes admitted demand and quota, then requests capacity through a
  single reviewed infrastructure reconciler using provider-scoped Spinifex/cloud API
  credentials. Kubernetes schedules jobs after capacity is ready. Argo CD manages cluster
  workload intent; it does not compete with the infrastructure reconciler for VM state.
- Burst to separately registered site/cloud execution clusters over authenticated private
  connectivity. Match job images, architecture, CUDA/GPU and MPI/UCX/fabric profiles, CSI
  storage and policy before placement. Use whole-job/gang placement where required;
  avoid latency-sensitive tightly coupled MPI across a WAN by default.
- Persist idempotent submission keys, selected site, lease/cost budget and execution
  ownership. Transfer only authorized datasets/artifacts, report status through Kafka,
  store result references, and tear down leased resources after verified completion.
  Retry cannot create duplicate paid jobs or destroy active capacity.

## Options considered

| Option | Benefits | Costs and limits |
| --- | --- | --- |
| Spinifex plus explicit capacity adapter | Local/private cloud APIs with a Kubernetes execution contract | Provider coverage, adapter and failure recovery must be proved |
| Direct public-cloud provisioning only | Fewer local cloud services | Does not satisfy the selected open-source local cloud layer |
| Stretch one cluster/MPI fabric across WAN | Apparent single scheduling domain | Latency, route and outage coupling; not the default |

## Trade-off analysis

Bursting is an end-to-end workflow requiring admission, provisioning, data movement,
execution ownership and cleanup. AWS-compatible APIs do not establish complete EKS/GKE/AKS
feature equivalence. Pin and test each provider operation used by the adapter.

## Consequences

Spinifex-specific host privileges and device/storage interfaces need a separate inventory
and explicit justification; [ADR 0001](0001-node-host-mounts.md) grants no Spinifex
node exception. Review the selected release's AGPL/commercial licensing and model/data
licenses before distribution or hosted operation. Secret recovery and artifact retrieval
must work at each execution site without depending on an unreachable home cluster.

## Action items and acceptance

- [ ] Pin Spinifex, provider tooling, admission/job controllers and fabric/runtime profiles.
- [ ] Implement the adapter and prove provision, authenticate, admit, run, report and cleanup.
- [ ] Test quota/cost limits, duplicate events, lost connectivity, controller restart and orphan GC.
- [ ] Demonstrate a controlled local/cloud job with verified artifacts before claiming seamless bursting.
