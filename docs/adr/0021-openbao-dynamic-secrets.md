# ADR-0021: OpenBao dynamic database leases and CSI file delivery

**Status:** Proposed — implemented/statically validated; full integration live acceptance pending.
**Date:** 2026-10-06
**Scope:** Module 4a, following the existing SSoT and ADR 0012.

## Context

vCloud needs renewable PostgreSQL credentials, static API keys, Kubernetes workload
authentication and a concrete issue/connect/revoke test. Existing production
workloads, namespace deny-all and frozen node exceptions must keep their ownership.

## Decision

Configure OpenBao secrets-engine mounts through its HTTP API. Do not invent a
SecretBackend CRD. Use KV v2 with compare-and-swap for static keys, and the PostgreSQL
plugin with SCRAM credentials and verify-full TLS to the CNPG read/write service.
The manager is not a PostgreSQL superuser and does not receive CREATEROLE or general
backend-signal rights. Three protected SECURITY DEFINER functions perform the
necessary lifecycle actions only for registered dynamic users, with pinned search
paths, quoted SQL inputs and bounded expiration. Their initial SQL-superuser
installation is explicitly required; the database Pod still runs as UID 26 and
remote superuser access stays disabled.

Bind the application and validation roles to distinct Kubernetes service accounts,
namespace workload-apps, and audience openbao. Validation can issue/revoke only the
short-lived validation database role. Its revocation policy denies the request-body
lease override and grants neither global revocation nor sudo.

Use provider openbao and driver secrets-store.csi.k8s.io. Prefer 0440 memory-backed
CSI files with fsGroup 65532, one complete JSON response for paired credentials,
and a separate static-key file. Retain the provider Agent's renewal cache; applications
must reload files and reopen pools. Static Kubernetes Secret synchronization is an
explicit optional cache for API keys only. No credentials enter Pod environment
variables, source, images or logs.

Provide a standalone consumer and an expiring validation Pod; do not patch Module 3's
frozen promotion template or compete with Module 2's existing Argo ownership. Fold
the CNPG HBA change and OpenBao public-CA mounts through their existing owners.
Additional CSI node mounts/privileges require a separately reviewed approval; this
module provides no node installer and does not amend the approved exception.

## Options considered

| Option | Consequence |
| --- | --- |
| Paired CSI JSON files | Selected; application reload and non-root permissions need live acceptance |
| Separate reads without pairing guarantees | Can mismatch independently issued credentials |
| Kubernetes Secret/env database credentials | Adds a cache and exposes process environment; not selected |
| PostgreSQL superuser login held by OpenBao | Broad remote authority; replaced by constrained functions |
| A broad lease-revoke policy | Allows unrelated lease revocation; scoped validation role selected |

## Verification and consequences

The three-step curl/psql test validates issuance, an actual TLS session, and a fresh
authentication rejection after synchronous revocation. Network errors cannot pass.
Local tests mock transports and tmpfs inventory and do not establish live behavior.
SQL privilege boundaries, existing-session termination, CSI group ownership after
rotation, OpenBao reviewer-token renewal and external API-key issuer revocation
remain runtime acceptance gates. See the [runbook](../../module-4a/README.md) and
[evidence](../module-4a-validation.json).
