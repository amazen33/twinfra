# ADR-0009: Prometheus for metrics and service objectives

**Status:** Proposed  
**Date:** 2026-10-05  
**Deciders:** vCloud platform owner and Principal Architect  
**Selection:** Prometheus is required by Module 1.  
**Scope:** [SSoT and shared implementation contract](README.md).

## Context

Operators need bounded metrics and actionable alerts across API, database, inference
and HPC systems. Prometheus collects and queries time-series data; alert rules are
delivered to Alertmanager for routing. See
[Prometheus overview](https://prometheus.io/docs/introduction/overview/) and
[alerting architecture](https://prometheus.io/docs/alerting/latest/overview/).

## Decision

- Deploy Prometheus in `platform-services` with CSI-backed storage and explicit
  retention/size limits. For production availability, use independent replicas and
  deduplicated alert routing. Additional long-term remote storage requires its own decision.
- Scrape authenticated metrics endpoints using narrowly permitted destinations and
  least-privilege discovery RBAC. Scrape APISIX, Knative, CloudNativePG, Kafka/Strimzi,
  vLLM, OpenBao, controllers and the OpenTelemetry Collector where supported.
  No host-mounted node exporter or privileged GPU metrics agent is implicitly approved.
- Define measured service objectives before paging: API availability/latency,
  generation time-to-first-token and token latency, database lag/backup age,
  Kafka consumer lag, secret-service availability and HPC queue age/job failure rate.
  Record workload/site/model labels from a bounded vocabulary; exclude tenant secrets,
  raw prompts, user IDs and unbounded document/job identifiers from metric labels.
- Keep Prometheus read-only relative to production workloads. If its metrics feed
  capacity automation, a separate adapter/controller owns the scaling decision with
  explicit quota, freshness and failure behavior. Missing metrics do not authorize
  unlimited scale-up or a scale-down below HA floors.

## Options considered

| Option | Benefits | Costs and limits |
| --- | --- | --- |
| Prometheus with Alertmanager | Established metric/query and alert model | Storage/cardinality budgeting and HA need configuration |
| Provider-only metrics | Low local operational effort in cloud | Inconsistent local-to-cloud observability and platform coupling |
| Logs as the only health signal | Simple initial collection | Poor numeric capacity signals and delayed failure detection |

## Trade-off analysis

Prometheus is the operational metrics authority. It does not replace distributed
tracing, log retention or backup evidence. Storage retention must leave free-space
headroom; see [TSDB storage guidance](https://prometheus.io/docs/prometheus/latest/storage/).

## Consequences

Metrics and rule definitions live in Git. Alert receivers and credentials come from
OpenBao. Routing rules must identify an owner and runbook, rather than creating broad
notifications for every metric anomaly.

## Action items and acceptance

- [ ] Pin server/exporter versions and any selected operator/CRD schemas.
- [ ] Validate rules/configuration and test scrape authentication under default deny.
- [ ] Inject API/DB/GPU/queue failures; verify alerts and redundant-server behavior.
- [ ] Demonstrate retention, cardinality limits and safe handling of stale scaling metrics.
