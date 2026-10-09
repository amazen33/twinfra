# ADR-0029: vCloud is an AWS-compatible enterprise simulator

**Status:** Accepted (owner, 2026-10-08). D9-D12 below remain open.
**Author:** Claude (platform architecture). **Decider:** vCloud owner.
**Records:** owner decisions D1 (as amended) and D6 (as extended).

## Context

vCloud exists so the same workloads can switch between AWS and on-premises. The owner set the
main application contract to be the AWS API itself: the AWS CLI, the AWS SDKs and CloudFormation
must work unchanged against vCloud. Copying every AWS service is not feasible, so compatibility
has to be scoped, measured and labelled.

## Decision

1. **Contract.** Applications use the AWS API. A vCloud region exposes an AWS-compatible endpoint.
   Clients switch with `AWS_ENDPOINT_URL` (or per-service variants) or `endpoint_url` in a profile,
   plus credentials. On AWS the endpoint is left out. Open protocols (Kubernetes, PostgreSQL wire,
   OTLP, OIDC) remain the implementation underneath.
2. **Shape.** Each region runs a vCloud API gateway that verifies SigV4 (including presigned URLs and
   chunked payloads), evaluates IAM policies, writes a CloudTrail-style audit trail and routes
   calls to service handlers. Handlers create vCloud Platform API claims (ADR-0031), which are
   fulfilled by real back-end services.
3. **Identity.** vCloud IAM, STS and accounts, using the AWS formats for account IDs, ARNs and keys. People federate
   from Keycloak through `AssumeRoleWithWebIdentity`. Workloads federate from Kubernetes service
   accounts. VMs read role credentials from an IMDSv2-compatible endpoint.
4. **Catalog (D6 as extended by the owner).** Tier 1:
   - IAM, STS and accounts; S3; CloudWatch metrics, alarms and logs; KMS, Secrets Manager and SSM; CloudTrail.
   - EC2 with EBS, AMIs, key pairs, user data and IMDSv2; VPC basics and security groups; Elastic Load Balancing.
   - Auto Scaling and self-healing; Lambda (Go first); RDS for PostgreSQL; ECR.
   - CloudFormation, including CDK output; EKS; multiple regions.
   - An admin console for EC2, VMs and EKS.

   Tier 2: SQS, SNS, EventBridge, DynamoDB, ElastiCache, Route 53, Organizations, quotas and
   simulated billing. Tier 3: the long tail, served by MiniStack (MIT) and labelled Emulated.
5. **Labels.** Each service is labelled **Real** (real infrastructure, persistent) or **Emulated**. The
   label appears in the console, the docs and the parity scorecard (ADR-0033).
6. **Naming.** vCloud is described as "AWS-compatible". It is never presented as AWS or as endorsed
   by Amazon.

## Open decisions (not yet approved)

- D9: how to build the API layer. Recommended: a Go gateway with real back-end services for Tiers 1 and 2, and
  MiniStack behind the gateway for the long tail.
- D10: region names. Recommended: `vc-<site>-<n>`, with optional aliases to AWS names.
- D11: Lambda limits. Recommended: AWS limits by default, with an opt-in unconstrained switch per function or
  account that carries a portability warning.
- D12: lab regions. Recommended: two logical regions in the VM lab now, and a second VM before Phase 7.

## Consequences

- AWS compatibility becomes a long-running engineering programme, delivered in Phases 3-8 of the plan.
- Fidelity claims require parity evidence (ADR-0033). Static checks alone never make a service Real.
- The earlier "open contracts only" proposal (plan version 1) is superseded.
- The licence rules of ADR-0030 apply to every building block.
