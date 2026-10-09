# ADR-0031: Crossplane as the internal provisioning engine (vCloud Platform API)

**Status:** Accepted (owner, 2026-10-08)
**Author:** Claude (platform architecture). **Decider:** vCloud owner. **Records:** D3.

## Context

AWS-compatible service handlers (ADR-0029) and GitOps both need one declarative way to ask for
infrastructure (buckets, databases, VMs, clusters) with an implementation per environment.

## Decision

1. Crossplane (Apache-2.0, CNCF) hosts the **vCloud Platform API**. Composite resource definitions
   (for example Bucket, PostgresDatabase, AppSecret, VirtualMachine, Cluster and Tenant) are
   fulfilled by an on-prem composition (SeaweedFS, CloudNativePG, OpenBao, KubeVirt, Cluster API)
   or an AWS composition.
2. For AWS, use the Apache-2.0 **crossplane-contrib** provider builds. Do not use Upbound official
   builds, which carry commercial terms.
3. Service handlers and the console create claims. They never write back-end resources directly.
4. Keep the set of resource types small. Add one only when a phase needs it.
5. Release choice follows the version policy in ADR-0034. The baseline seen on 2026-10-08 was
   Crossplane v2.4.2 (released 2026-09-22).

## Consequences

- One reconciliation model for the gateway, the console and GitOps.
- Terraform and OpenTofu are not needed (ADR-0030).
- Composition complexity is a risk, mitigated by small resource types and conformance tests per type.
