# ADR-0022: Separate Keycloak API and Kubernetes identity contracts

**Status:** Reference configuration implemented and statically tested; live acceptance pending.
**Date:** 2026-10-06

## Context

vCloud needs a central issuer and secure API access, while preserving existing
APISIX/Argo ownership and namespace deny-all. Human identity must not automatically
grant cluster administration, Secret access, workload or cloud service-account rights.

## Decision

Use the vcloud realm at the canonical HTTPS issuer. Separate public PKCE clients for
API and Kubernetes access and the vcloud-function resource audience. Disable password,
implicit and service-account grants. Require new-user TOTP enrollment, bounded lifetimes,
refresh rotation and controlled membership. Gate function.read through its realm role;
emit its API audience in access tokens and full Kubernetes group paths in ID tokens.

APISIX 3.19.0 uses secret-free bearer-only JWKS validation in an ApisixPluginConfig v2.
Require issuer, audience, RS256 and function.read; preserve verified upstream TLS and
remove unsigned identity headers. Expose only the vcloud realm and static resources,
overwrite forwarded headers and keep administration private. The public login and
discovery route has no bearer-token requirement.

Configure API-server OIDC with a stable subject username and keycloak: group prefix.
Bind cluster observers to read nodes/namespaces through a narrow ClusterRoleBinding.
Bind workload/HPC readers inside their namespaces. Grant no Secrets, exec/logs,
mutation, impersonation, bind/escalate or cluster-admin rights.

## Alternatives and consequences

A shared client would blur API and Kubernetes audiences. Broad cluster-admin mapping
would make central IAM membership a cluster takeover path. Gateway login/session flow
would need separate secret/session/callback design; this API uses bearer-only validation.

The reference does not install Keycloak, replace Module 2's chart, restart control
planes or widen node exceptions. Startup import skips existing realms; changes need
reviewed private administration. Managed Kubernetes federation requires provider-specific
integration. JWT/key caches require bounded revocation expectations. Real login, claims,
RBAC and negative-token acceptance remain pending. See the
[runbook](../module-4b/README.md) and [evidence](module-4b-validation.json).
