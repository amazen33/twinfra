# ADR-0011: OpenTelemetry for instrumentation and telemetry transport

**Status:** Proposed  
**Date:** 2026-10-05  
**Deciders:** vCloud platform owner and Principal Architect  
**Selection:** OpenTelemetry is required by Module 1.  
**Scope:** [SSoT and shared implementation contract](README.md).

## Context

A RAG request crosses authentication, HTTP revision routing, retrieval and generation.
OpenTelemetry instruments and exports signals; its Collector receives, processes and
exports them. A Collector is not a durable trace database. See
[Collector architecture](https://opentelemetry.io/docs/collector/architecture/).

## Decision

- Instrument the LangChain application with an approved OpenTelemetry SDK and W3C
  trace context. Propagate context through APISIX/Knative where supported and tested;
  create explicit retrieval, database and inference-client spans. vLLM server spans
  depend on the pinned release's instrumentation, not an assumed automatic capability.
- Deploy non-root gateway Collectors in `platform-services`. SDKs and approved service
  exporters send authenticated OTLP over TLS. This avoids a hostPath log-tail DaemonSet.
  Pin the Collector distribution and enabled receivers/processors/exporters; do not
  load arbitrary collector components. See the
  [gateway pattern](https://opentelemetry.io/docs/collector/deploy/gateway/).
- Apply memory limits, bounded queues, batching, sampling and redaction before export.
  Telemetry failures must not indefinitely block requests. Keep trace IDs in logs for
  correlation, while excluding prompt text, secrets, tokens and document contents.
- Expose application metrics through the reviewed Collector Prometheus exporter and
  scrape them with Prometheus. Export traces to an **additional persistent OTLP-compatible
  backend**, to be selected/pinned in an implementation ADR; Grafana queries that backend.
  Log retention similarly requires a selected sink. Neither is supplied by the three
  requested observability products alone.

## Options considered

| Option | Benefits | Costs and limits |
| --- | --- | --- |
| SDKs plus gateway Collectors | Common transport and centrally managed redaction | Export backend, queues and authentication need configuration |
| SDKs directly to each backend | Fewer collector hops | Application coupling and duplicated export policy |
| Host log-tail/agent collectors by default | Broad collection | New host-access exceptions; not selected |

## Trade-off analysis

Gateway collection fits the current host-volume restrictions. Durable telemetry,
sampling bias and dropped signals remain explicit operational concerns.

## Consequences

Observability must not become a data-exfiltration route. Give Collector egress only
to the selected backends; namespace-wide access to application services is unnecessary.
Asynchronous Kafka work carries trace links/IDs in an approved event envelope.

## Action items and acceptance

- [ ] Pin SDKs/Collector and select trace/log backends, retention and data residency.
- [ ] Verify a trace spans gateway, RAG retrieval and inference with correct tenant redaction.
- [ ] Test exporter outage, full queues and restart; document dropped-signal behavior.
- [ ] Prove TLS/identity enforcement and reject unauthorized OTLP senders.
