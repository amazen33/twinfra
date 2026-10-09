# ADR-0034: Observability baseline (Apache-2.0) and managed observability on AWS

**Status:** Accepted (owner, 2026-10-08). Supersedes ADR-0010 (Grafana).
**Author:** Claude (platform architecture). **Decider:** vCloud owner. **Records:** D7 and the observability baseline.

## Decision

1. **On-prem stack.** All components are Apache-2.0, with baseline versions as seen on 2026-10-08:

| Role | Component | Baseline |
| --- | --- | --- |
| Collector | OpenTelemetry Collector, vCloud build from stable and beta components (Collector Builder) | 0.162.0, production from 2026-10-13 |
| Collector operator | OpenTelemetry Operator | 0.160.0 (optional in v1) |
| Metrics | Prometheus **LTS** | 3.13.4 (LTS supported to 2027-07-31) |
| Metrics operator | Prometheus Operator | 0.94.1 |
| Alerting | Alertmanager | 0.34.1 |
| Cluster metrics | kube-state-metrics, node_exporter | 2.20.0, 1.12.1 |
| Traces | Jaeger v2 | 2.21.0 (2.22.0 from 2026-10-20) |
| Logs and trace storage | OpenSearch, OpenSearch Dashboards | 3.8.0; fallback is the 2.19 line if Jaeger does not support 3.x |
| Dashboards | Perses, Perses Operator | 0.54.0, 0.5.0 (pre-1.0: pin and test upgrades) |
| Long-term metrics (later) | Thanos, on the S3 API | 0.42.4 |

2. **Topology.** Applications send OTLP to a Collector agent on each node, which forwards to a Collector gateway. Only the gateway's exporters change between environments.
3. **AWS (D7).** The same Collector build exports to Amazon Managed Service for Prometheus,
   AWS X-Ray or Amazon OpenSearch Service, and CloudWatch Logs.
4. **CloudWatch API.** The vCloud CloudWatch handlers (Phase 3) are built on this stack.
5. **Host access.** Pod-log and host-metric collection need read-only host mounts. Each one goes through the
   node-exception process (ADR-0001): exact paths, a pinned image, owner approval.
6. **Version policy.**
   - Adopt a new minor version after 14 days, or 30 days for production.
   - Take LTS patches once CI passes.
   - Pin every image by digest.
   - Renovate or Dependabot proposes upgrades through the PR gate.
7. **Excluded:** Grafana, Loki, Tempo and Mimir (AGPL), and Elasticsearch and Kibana.

## Consequences

Grafana is removed (WO-07). Three interfaces: Perses for metrics, the Jaeger UI for traces and
OpenSearch Dashboards for logs, all linked from the console. Versions in this ADR are a dated
baseline. Upgrades follow the policy without a new ADR.
