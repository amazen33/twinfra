# ADR-0010: Grafana for authenticated operational dashboards

**Status:** Proposed  
**Date:** 2026-10-05  
**Deciders:** vCloud platform owner and Principal Architect  
**Selection:** Grafana is required by Module 1.  
**Scope:** [SSoT and shared implementation contract](README.md).

## Context

Platform operators need one investigation surface for metrics and retained traces.
Grafana queries configured data sources; it is not the metrics or trace storage engine.
See [data-source concepts](https://grafana.com/docs/grafana/latest/datasources/).

## Decision

- Run non-root Grafana in `platform-services`, reachable through an authenticated
  private/VPN administrative route. Use Keycloak OIDC, disable anonymous access and
  map a bounded operator/viewer role set. Do not assume advanced enterprise-only
  data-source permissions exist in the selected open-source edition.
- Provision dashboards and non-secret data-source definitions through Git/Argo CD.
  Query Prometheus for metrics and the separately selected trace backend for traces.
  Correlate request traces with API latency, vLLM queue/TTFT, database lag, Kafka lag
  and HPC queue state. No trace dashboard is declared functional before storage/export
  integration is implemented.
- Keep data-source credentials read-only and retrieve them through OpenBao using a
  reviewed runtime mechanism. Restrict outbound data-source destinations and installed
  plugins. Pin plugins by exact version and verify their supply chain.
- For HA Grafana, use a dedicated PostgreSQL database/role and release-supported shared
  configuration instead of sharing a SQLite file between replicas. Isolate its lifecycle
  from application data and coordinate database migrations during upgrades. See
  [HA guidance](https://grafana.com/docs/grafana/latest/setup-grafana/set-up-for-high-availability/).

## Options considered

| Option | Benefits | Costs and limits |
| --- | --- | --- |
| Grafana with explicit data sources | Shared operational view and Git-provisioned dashboards | Identity, data-source access and HA need configuration |
| Per-component dashboards | Less central setup | Fragmented investigations and access controls |
| Hosted visualization service | Reduced dashboard operations | Additional external data/identity dependency |

## Trade-off analysis

Grafana improves investigation without becoming a new authoritative telemetry store.
For this design, dashboards are for platform operators; tenant-facing analytics need
separate isolation and licensing review.

## Consequences

Dashboards must not display raw prompts, secrets or unauthorized document content.
Grafana availability is not required for the synchronous API, but its database and
data sources still need backup and recovery procedures.

## Action items and acceptance

- [ ] Pin Grafana/plugins and provision reviewed Prometheus/trace data sources.
- [ ] Test OIDC role mapping, disabled anonymous access and denied unapproved data sources.
- [ ] Verify dashboard queries, trace correlation and no sensitive payload exposure.
- [ ] Exercise replica loss, shared-database recovery and a dashboard configuration rollback.
