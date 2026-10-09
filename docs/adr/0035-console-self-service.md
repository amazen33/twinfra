# ADR-0035: Self-service console through the vCloud API

**Status:** Accepted (owner, 2026-10-08). Partly supersedes ADR-0026 and ADR-0027: their read-only
decision ends. Their identity, cookie and isolation decisions stay in force.
**Author:** Claude (platform architecture). **Decider:** vCloud owner. **Records:** D8 and the owner's request
for an admin console covering EC2, VMs and EKS.

## Context

The console backend answers every create, change and delete request with `405 Read-only API`
(`console/server.py`, lines 175-181). The owner requires an AWS-style console that can create and
manage resources, including EC2 instances, VMs and EKS clusters for administrators.

## Decision

1. **Same API as customers.** The console calls the vCloud gateway (ADR-0029) with temporary STS
   credentials, obtained from the Keycloak sign-in through `AssumeRoleWithWebIdentity`, using the AWS SDK for
   JavaScript v3 (Apache-2.0). It has no private write path, and its service account has no
   write permissions.
2. **Change model (D8).** Tenant resources are created immediately. Platform changes (accounts,
   regions, quotas, enabling services) open a Git pull request for owner approval.
3. **Roles.**
   - `console.viewer`: read only.
   - `console.operator`: create and change in your own account.
   - `console.admin`: all accounts and regions, platform health, approvals.
4. **Guardrails.**
   - Quotas per account; approval required for expensive requests such as GPUs or large disks.
   - Two-step delete; databases retained by default.
   - Cross-site request forgery checks on every state change; every change written to the audit trail.
5. **Fidelity.** Every service page shows Real or Emulated.
6. **Delivery.**
   - Phase 1 (WO-11): roles, forgery protection and audit, with writes disabled behind a feature switch.
   - Phase 3: the write path through the gateway, plus S3, IAM and CloudWatch pages.
   - Phase 4: EC2, VMs and Auto Scaling. Phase 5: Lambda, RDS and more. Phase 6: CloudFormation and EKS.

## Consequences

The console cannot do anything the CLI cannot. Authorisation is enforced once, at the gateway.
No temporary write path is built and then thrown away.
