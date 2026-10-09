# WO-10: Observability stack v1 at the baseline versions

**Status:** Approved for implementation (owner, 2026-10-08) · **Phase:** 1 · **Author:** Claude · **Implementer:** Codex
**Branch:** `codex/wo-10-observability` · **Decision:** ADR-0034 · **Depends on:** WO-02, WO-07

## Goal

A commercially usable, all-Apache-2.0 observability stack in which any request can be followed end to end,
and an SLO breach alerts a person. This stack later serves the CloudWatch API.

## Verified context

- The lab pins Prometheus 3.15.0, which is not on the LTS line, plus Prometheus Operator 0.94.1 and the OpenTelemetry Collector contrib image 0.162.0
  (`lab/wsl/endpoints/artifacts.lock.json`).
- The Collector sends traces to the `debug` exporter (`lab/wsl/endpoints/gitops/workloads.yaml`), and there is no log store.
- Alert rules exist with promtool tests (`module-3/observability/rules.yaml`, `tests/module3-alerts.test.yaml`).
  No external notification has ever been sent (`module-3/README.md`).

## Scope

1. **vCloud Collector build.** Built with the Collector Builder (`cmd/builder`, matching version) from
   stable- or beta-stability components only. The PR lists each component with its stability level.
   The image is built reproducibly in CI, with an SBOM, and pinned by digest. The agent runs as a DaemonSet and the gateway as a Deployment.
2. **Host access.** Pod-log collection (read-only `/var/log/pods`) and node_exporter need host mounts.
   Prepare the node-exception requests as ADR-0001 requires: exact paths, the pinned image, and the justification.
   Do **not** change `security/node-exceptions.json` or its SSoT hash without the owner's approval in the PR.
3. **Metrics:** Prometheus 3.13.4 LTS (replacing 3.15.0), Alertmanager 0.34.1, and kube-state-metrics 2.20.0,
   plus node_exporter 1.12.1 once approved.
4. **Traces:** Jaeger v2 2.21.0, storing traces in OpenSearch.
5. **Logs and search:** OpenSearch 3.8.0 and OpenSearch Dashboards. Start with a short spike on whether Jaeger 2.21 supports
   OpenSearch 3.x; if it does not, use the maintained 2.19 line and record that.
   Size it for the lab: single node, a small heap, and retention settings.
6. **SLOs:** gateway availability, login success, GitOps sync time and database availability, each with
   multi-window burn-rate rules, promtool tests, and Perses dashboards (WO-07). Alertmanager routes to the receiver the owner chooses.
7. Restricted Pod Security, default-deny network policies with exact allow rules, licence-register entries,
   and every manifest produced through the generators.

## Out of scope

AWS exporters (Phase 4 and D7), the CloudWatch API (Phase 3), Thanos (Phase 5), and the OpenTelemetry Operator
(optional; add it only if auto-instrumentation is needed).

## Acceptance criteria

- One request through APISIX to the console backend appears in Jaeger, and its logs are found in OpenSearch by `trace_id`.
- A forced SLO breach sends an alert to the real receiver.
- Versions match ADR-0034, or the PR records the version-policy reason for any difference.
- The promtool tests and the PR gate pass, including the historical baselines.
- Receipt: `docs/acceptance/observability-v1-<date>.md`.

## Owner actions

Approve the node exceptions, choose the alert receiver, and approve the live rollout.

## Report back

The component list with stability levels, the OpenSearch version decision, resource use in the lab, and the receipt.
