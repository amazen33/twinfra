# ADR-0025: Restricted LocalStack AWS API validation on WSL

Status: Accepted for the local lab, 2026-10-07.

## Context

The operator selected legacy LocalStack Community 4.14.0 for S3, EC2, IAM and
DynamoDB validation without a license token. The WSL gateway previously used
file-driven APISIX and had no ingress controller or `ApisixRoute` CRDs. Applying
a route object alone could not create an operational ingress route.

## Decision

Deploy the digest-pinned API emulator with restricted:v1.30 security, bounded
ephemeral tmpfs storage and no Docker socket, root, capabilities, host mounts or
public egress. Keep GPU/vLLM and Spinifex offloading disabled. Health requires
four `running` service states and real signed read-only AWS API calls.

Supply the official frozen APISIX 2.2.0 ingress controller and ADC 0.27.1 with
their served, non-deprecated CRDs. Change only the local APISIX 3.19 gateway to
TLS-authenticated API-driven standalone mode without etcd. A `GatewayProxy`
references a create-only encrypted Kubernetes Secret; no private credential is
committed or put in environment variables, argv or host plaintext. The admin
API is private and Cilium permits only controller traffic to 9180. ADC verifies
the mounted CA. Preserve both existing CPU demo and smoke routes.

Argo owns namespaced workloads and routes; controller/RBAC, CRDs and dynamic
node health policies remain bootstrap-owned. The upstream controller's global
informers require read-only Secret discovery; it cannot write Secrets. Production
Secret-cache scoping and least-privilege review remain open. No node exception
is expanded. The controller's writable filesystem does not grant root or added
capabilities. Public CA trust does not justify disabling TLS verification.

## Consequences and validation

Port 4566 is an AWS API endpoint, with no installed browser console. The local
Host route `aws.platform.example.com` is tested on loopback port 18080; it does
not configure Windows DNS or port 80. EC2 emulates API state and does not launch
VMs. Pod replacement loses emulator data. The old Community release is a lab
choice, not a maintained-production release recommendation.

Static acceptance includes strict offline schemas, restricted-PSS policies,
ShellCheck, image/cache/routing mutation tests and full module CI. Live acceptance
checks all four AWS calls, direct and gateway health, root HTTP 200/302, existing
GitOps/demo/database/metrics/trace gates and deny-all regression. Report actual
results separately from this decision. Admin certificates require operator
renewal within 90 days. Rollback procedure and exact last-good source revision
are in the [lab runbook](../../../lab/wsl/localstack/README.md).
