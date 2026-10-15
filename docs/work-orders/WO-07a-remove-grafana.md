# WO-07a: Remove Grafana (Perses deployment moves to WO-10)

**Status:** Approved for implementation (owner, 2026-10-15: "split approved") · **Phase:** 1 · **Author:** Claude · **Implementer:** Codex
**Branch:** `codex/wo-07a-remove-grafana` · **Decisions:** ADR-0030, ADR-0034, ADR-0044, ADR-0049 · **Supersedes:** the deployment part of WO-07 (PR #39)

## Why

Grafana is AGPL and is the last `pending-removal` entry in the licence register, expiring **2026-12-08**. PR #39 tried to replace it with Perses, but the newest eligible
Perses 0.54.0 and Operator 0.5.0 were built with Go 1.26.5. Each image carries 3 fixable Critical and 21–26 fixable High findings (`.build/wo-34/perses-pr39-preflight/STOP.md`).
Grafana does not run on the Dell dev environment, and Prometheus only arrives with WO-10, so Perses would have no data to show today.

## Verified context (`origin/main` 4829912)

- The register entry `oci-image|docker.io/grafana/grafana|sha256:b28bae15…` (`pending-removal`, expires 2026-12-08) is pinned in `lab/wsl/endpoints/artifacts.lock.json`
  and `lab/wsl/endpoints/gitops/workloads.yaml`. The WSL endpoint files also reference it in `deploy.sh`, `access.sh` and `README.md`, and in `tools/wsl_endpoint_acceptance.py`.
- `tools/render_module3.py` (lines 195-196, 243) renders a Grafana dashboard ConfigMap `vcloud-delivery-dashboard` (label `grafana_dashboard: "1"`) into
  `module-3/manifests/observability.yaml`.
- The dev overlay (`deploy/environments/dev/cairo-1`) contains no Grafana.

## Scope

1. **Remove Grafana from everything that can deploy it**, through the generators: the WSL endpoint lock, workloads, scripts, acceptance tool and docs; and the Module 3
   dashboard ConfigMap. The WSL endpoint files stay otherwise intact until WO-28.
2. **Keep the dashboards as code, not deployed.**
   - Take the ported Perses dashboard definitions from PR #39 (`twinfra-delivery`, with all four panels and the PromQL unchanged, and `twinfra-health`) and store them as plain
     files under `deploy/observability/dashboards/`, with a README saying they are deployed by WO-10.
   - Do not add the Perses images, Operator, CRDs or `PersesDashboard` objects. `tools/render_module3.py` no longer emits a dashboard object.
3. **Licence register.** Remove the Grafana entry. The `pending-removal` list becomes empty, and the gate stays green.
4. **CI guard.** Fail if a Grafana image, Helm chart, manifest or `grafana_dashboard` label appears in any locked or rendered deployment input. Historical revisions,
   ADRs, receipts and the six historical baselines are exempt, and the six historical revisions must still pass.
5. **Docs and changelog.**
   - Update `docs/service-access.md`, the Module 3 README and the observability docs. Dashboards now arrive with WO-10.
   - Add a CHANGELOG entry.
   - Copy this work order to `docs/work-orders/`, and add a status line to WO-07 that says its deployment part moved to WO-10 (WO-07b) and its removal part is this work order.
6. **PR #39.** Do not modify it. In this PR's description, say that it supersedes #39; the owner closes #39 after this merges.

## Out of scope

Deploying Perses or Prometheus (WO-10). Removing other WSL files (WO-28).

## Acceptance criteria

- The PR gate is green, including the licence gate, the supply-chain gate and the six historical revisions.
- No Grafana image, manifest or dashboard label remains in any deployment input, and the new CI guard enforces it.
- The licence register has zero `pending-removal` entries.
- Live: nothing to change on the Dell (Grafana was never deployed there). The receipt notes this.

## Report back

The files changed, the dashboards kept and where they are, the register and gate results, and CI.
