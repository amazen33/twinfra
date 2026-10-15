# ADR-0053: Tenancy model — AWS-style accounts and IAM map to tenants

**Status:** Proposed (design only; owner approved writing it now, 2026-10-16). It is implemented with WO-22 and Wave 2, after Foundation 1.0 (ADR-0052).
**Author:** Claude (platform architecture). **Decider:** Ahmed Mazen, Owner and Product Owner.

## Context

Twinfra is AWS-compatible (ADR-0029). In AWS, the **account** is the hard isolation boundary, and **IAM** decides who may do what inside it. WO-22 (real S3 and EC2 through the gateway) needs this model fixed first.
The reviews correctly noted that Module 5a's reader role is not a tenant boundary. ADR-0005 already requires tenant IDs, row-level security and cross-tenant denial tests for shared stores.

## Decision (proposed)

1. **Tenant = account.** A Twinfra account has a 12-digit ID and is the only tenant boundary. Platform operators are not tenants. No tenant receives Kubernetes API access by default.
2. **Runtime isolation.**
   - Each account owns one or more namespaces labelled `twinfra.io/account=<id>`, with Cilium default-deny between accounts.
   - Each account has a ResourceQuota and LimitRange, and Pod Security restricted.
   - Workloads run with per-account ServiceAccounts, with no cross-account RBAC.
3. **Identity and authorisation.**
   - The gateway implements IAM: users, groups, roles, policies and access keys, stored in the gateway's PostgreSQL. It is evaluated on every SigV4 request, with explicit deny first and default deny.
   - STS AssumeRole issues short-lived credentials.
   - Humans sign in through Keycloak and federate into IAM roles (`AssumeRoleWithWebIdentity`): Keycloak proves *who* someone is, and Twinfra IAM decides *what* they may do.
   - Each account has a root user that is used only to bootstrap.
4. **Names and resources.**
   - ARNs follow `arn:aws:<service>:<region>:<account>:<resource>` with the region `cairo-1`.
   - Each service maps its resources into the owning account:
     - S3 buckets → a SeaweedFS collection per account; bucket names stay globally unique, as in AWS;
     - EC2 instances → KubeVirt VMs in the account's namespace;
     - RDS → a CNPG cluster per DB instance in the account's namespace;
     - DynamoDB → tables scoped per account.
5. **Shared stores** (for example pgvector, ADR-0005) use a validated account context and row-level security; the account ID never comes from client input.
6. **Evidence (required before any multi-tenant claim).** For every service, a **cross-account denial matrix**:
   - account A cannot list, read, write or delete account B's resources through the API, the console or the network;
   - each check is an automated test, plus one live receipt on `cairo-1`.
7. **Out of scope for now:** Organizations and SCPs, billing and metering, cross-account resource sharing, and VPC peering.

## Owner answers (2026-10-16)

- Dev starts with **two tenant accounts** plus the operator, so cross-account denial tests are real from day one.
- Accounts are created **by an operator only**. Self-service is out of scope.

## Consequences

Every service built in Wave 2 inherits one isolation rule and one IAM engine. Multi-tenancy can be claimed only service by service, as each passes its denial matrix.
