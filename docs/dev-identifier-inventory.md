# Rebuild identifier inventory

Generated from tracked current sources by the WO-21 audit. Existing WSL material and historical records are preserved for WO-28. Generated Pod suffixes are not stable names. Upstream-owned names are listed separately in [the register](../deploy/upstream-names.json).

| Existing identifier | Rebuild disposition | Current references |
| --- | --- | --- |
| `vcloud-lab-allow-client` | `twinfra-conformance-allow-client` | `tools/wsl_lab.py` |
| `vcloud-lab-allow-server` | `twinfra-conformance-allow-server` | `tools/wsl_lab.py` |
| `vcloud-lab-allowed` | `twinfra-conformance-allowed` | `docs/wsl-local-acceptance.json`, `lab/wsl/bootstrap.sh`, `lab/wsl/test-network.sh`, `tools/wsl_lab_acceptance.py` |
| `vcloud-lab-denied` | `twinfra-conformance-denied` | `docs/correction-review-validation.json`, `docs/wsl-local-acceptance.json`, `docs/wsl-network-acceptance.json`, `lab/wsl/bootstrap.sh`, `lab/wsl/test-network.sh`, `tools/wsl_lab_acceptance.py` |
| `vcloud-lab-dns` | `twinfra-conformance-dns` | `lab/wsl/bootstrap.sh`, `tools/wsl_lab.py` |
| `vcloud-lab-dns-68dcb5bb4-rjgtx` | Retain historical generated Pod reference; rebuild controller as `twinfra-conformance-dns` | `docs/wsl-local-acceptance.json` |
| `vcloud-lab-server` | `twinfra-conformance-server` | `docs/correction-review-validation.json`, `docs/wsl-local-acceptance.json`, `docs/wsl-network-acceptance.json`, `lab/wsl/access.sh`, `lab/wsl/bootstrap.sh`, `lab/wsl/endpoints/gitops/workloads.yaml`, `lab/wsl/test-network.sh`, `tools/wsl_endpoints.py`, `tools/wsl_lab.py`, `tools/wsl_lab_acceptance.py`, `tools/wsl_localstack.py` |
| `vcloud-lab-smoke` | `twinfra-conformance-smoke` | `tools/wsl_lab.py` |
| `vcloud-wsl-api-firewall` | WSL-only mechanism retired by WO-28; no dev resource | `lab/wsl/bootstrap.sh` |
| `vcloud-wsl-apisix` | `twinfra-gateway` (standalone APISIX) | `tools/wsl_endpoints.py` |
| `vcloud-wsl-apisix-access` | WSL-only mechanism retired by WO-28; no dev resource | `deploy/console/deploy-wsl.py`, `docs/service-access.md`, `lab/wsl/access.sh`, `lab/wsl/endpoints/access.sh` |
| `vcloud-wsl-apisix-admin` | No dev admin API; legacy service retired by WO-28 | `lab/wsl/endpoints/gitops/workloads.yaml`, `tools/wsl_localstack.py`, `tools/wsl_runtime_secrets.py` |
| `vcloud-wsl-apisix-aws` | Routes consolidated into `twinfra-gateway`; no separate dev object | `tools/wsl_localstack.py` |
| `vcloud-wsl-apisix-ingress` | No ingress controller in the standalone dev profile; retired by WO-28 | `tools/wsl_localstack.py` |
| `vcloud-wsl-argo-controller` | `twinfra-argocd-application-controller-network`; controller retains upstream name | `tools/wsl_platform.py` |
| `vcloud-wsl-argo-redis` | `twinfra-argocd-redis-network`; Valkey cache retains upstream name | `tools/wsl_platform.py` |
| `vcloud-wsl-argo-repo` | `twinfra-argocd-repo-server-network`; repo server retains upstream name | `docs/troubleshooting/argocd-repo-health-wsl.md`, `lab/wsl/reconcile-prerequisites.sh`, `tools/wsl_platform.py` |
| `vcloud-wsl-argocd-dashboard` | WSL-only mechanism retired by WO-28; no dev resource | `docs/service-access.md`, `lab/wsl/access.sh` |
| `vcloud-wsl-cnpg-metrics` | Observability deferred to WO-10; future own names use `twinfra-` | `tools/wsl_endpoints.py` |
| `vcloud-wsl-console` | `twinfra-console` | `lab/wsl/console/reference/argocd.yaml`, `tools/wsl_console.py` |
| `vcloud-wsl-console-admin` | `twinfra-console-admin` | `console/README.md`, `deploy/console/copy-password.ps1`, `tools/configure_console_identity.py` |
| `vcloud-wsl-db-client` | `twinfra-db-client` | `lab/wsl/gitops/network.yaml`, `tools/wsl_db_test.py`, `tools/wsl_platform.py` |
| `vcloud-wsl-db-node-probe` | `twinfra-db-node-probe` | `tools/wsl_endpoints.py` |
| `vcloud-wsl-db-scaler` | Legacy WSL scaler not installed; future scaling work uses `twinfra-` | `lab/wsl/gitops/network.yaml`, `lab/wsl/gitops/workload.yaml`, `tools/wsl_platform.py` |
| `vcloud-wsl-demo` | `twinfra-demo` | `tools/wsl_endpoints.py` |
| `vcloud-wsl-endpoints` | Consolidated into `twinfra-services` Application | `MILESTONES.md`, `console/README.md`, `deploy/console/deploy-wsl.py`, `docs/wsl-local-milestones-3-5.md`, `lab/wsl/endpoints/argocd.yaml`, `lab/wsl/endpoints/deploy.sh`, `lab/wsl/localstack/deploy.sh`, `tools/wsl_endpoint_acceptance.py`, `tools/wsl_endpoints_gitops.py`, `tools/wsl_keycloak_admin.py` |
| `vcloud-wsl-endpoints-writer` | Consolidated into `twinfra-dev` AppProject; no separate dev writer | `lab/wsl/endpoints/argocd.yaml`, `tools/wsl_endpoints_gitops.py` |
| `vcloud-wsl-git-dns` | WSL-only mechanism retired by WO-28; no dev resource | `lab/wsl/install-git-dns-timer.sh`, `lab/wsl/reconcile-prerequisites.sh`, `lab/wsl/vcloud-wsl-git-dns.timer`, `tools/wsl_platform.py` |
| `vcloud-wsl-gitops-marker` | WSL acceptance marker retained as history; not installed in dev | `lab/wsl/PLATFORM.md`, `lab/wsl/gitops/workload.yaml`, `tools/wsl_platform.py` |
| `vcloud-wsl-gitops-writer` | Consolidated into `twinfra-dev` AppProject; no separate dev writer | `lab/wsl/reconcile-prerequisites.sh`, `tools/wsl_platform.py` |
| `vcloud-wsl-grafana` | Excluded from WO-21; future component work order uses `twinfra-` names | `tools/wsl_endpoints.py` |
| `vcloud-wsl-grafana-access` | WSL-only mechanism retired by WO-28; no dev resource | `lab/wsl/endpoints/access.sh` |
| `vcloud-wsl-grafana-admin` | Excluded from WO-21; future component work order uses `twinfra-` names | `lab/wsl/endpoints/gitops/workloads.yaml`, `tools/wsl_endpoints.py`, `tools/wsl_runtime_secrets.py` |
| `vcloud-wsl-http-access` | WSL-only mechanism retired by WO-28; no dev resource | `lab/wsl/access.sh`, `lab/wsl/endpoints/access.sh` |
| `vcloud-wsl-identity-db` | Database `twinfra-keycloak` on cluster `twinfra-postgres` | `tools/wsl_endpoints.py` |
| `vcloud-wsl-keycloak` | `twinfra-keycloak` | `lab/wsl/endpoints/gitops/workloads.yaml` |
| `vcloud-wsl-keycloak-access` | WSL-only mechanism retired by WO-28; no dev resource | `deploy/console/deploy-wsl.py`, `lab/wsl/endpoints/access.sh` |
| `vcloud-wsl-keycloak-admin` | `twinfra-keycloak-admin` | `docs/keycloak-admin-access.md`, `lab/wsl/endpoints/copy-keycloak-password.ps1`, `tools/wsl_keycloak_admin.py` |
| `vcloud-wsl-keycloak-db` | `twinfra-keycloak-db` | `lab/wsl/endpoints/gitops/workloads.yaml`, `lab/wsl/gitops/workload.yaml` |
| `vcloud-wsl-keycloak-recovery` | `twinfra-keycloak-recovery` | `docs/keycloak-admin-access.md`, `tools/wsl_keycloak_admin.py` |
| `vcloud-wsl-keycloak-tls` | `twinfra-keycloak-tls` | `console/README.md`, `deploy/console/deployment.yaml`, `deploy/console/gitops/workloads.yaml`, `lab/wsl/endpoints/gitops/workloads.yaml`, `tools/test_console_live.py`, `tools/vcloud_console.py`, `tools/wsl_endpoint_acceptance.py`, `tools/wsl_endpoints.py`, `tools/wsl_keycloak_admin.py` |
| `vcloud-wsl-knative` | Excluded from WO-21; future component work order uses `twinfra-` names | `tools/wsl_endpoints.py` |
| `vcloud-wsl-local` | `twinfra-dev-cairo-1` (VM/context only); `twinfra-node` (node) | `README.md`, `console/README.md`, `deploy/console/copy-password.ps1`, `deploy/console/profile.json`, `deploy/network/platform-probes/README.md`, `docs/WSL_SETUP_GUIDE.md`, `docs/correction-review-validation.json`, `docs/correction-review.md`, `docs/keycloak-admin-access.md`, `docs/service-access.md`, `docs/troubleshooting/argocd-repo-health-wsl.md`, `docs/wsl-local-acceptance.json`, `docs/wsl-local-milestones-3-5.md`, `docs/wsl-network-acceptance.json`, `docs/wsl-platform-status.json`, `lab/wsl/HOST-FIREWALL-EXCEPTION.md`, `lab/wsl/PLATFORM.md`, `lab/wsl/README.md`, `lab/wsl/access.sh`, `lab/wsl/bootstrap.sh`, `lab/wsl/console/apply.sh`, `lab/wsl/console/deploy-backends.sh`, `lab/wsl/console/gitops/workloads.yaml`, `lab/wsl/console/profile.json`, `lab/wsl/console/test-denied.py`, `lab/wsl/console/workloads.yaml`, `lab/wsl/enable-secret-encryption.sh`, `lab/wsl/endpoints/README.md`, `lab/wsl/endpoints/access.sh`, `lab/wsl/endpoints/copy-keycloak-password.ps1`, `lab/wsl/endpoints/deploy.sh`, `lab/wsl/gitops/workload.yaml`, `lab/wsl/localstack/README.md`, `lab/wsl/localstack/access.sh`, `lab/wsl/localstack/artifacts.lock.json`, `lab/wsl/localstack/deploy.sh`, `lab/wsl/localstack/verify.sh`, `lab/wsl/openbao-init.sh`, `lab/wsl/platform.sh`, `lab/wsl/prepare-storage.sh`, `lab/wsl/prepare-tls.sh`, `lab/wsl/profile.json`, `lab/wsl/reconcile-host-routing.sh`, `lab/wsl/reconcile-prerequisites.sh`, `lab/wsl/test-network.sh`, `lab/wsl/values/cilium-routing.yaml`, `tools/check_host_routing.py`, `tools/configure_console_identity.py`, `tools/openbao_pgp_init.py`, `tools/vcloud_console.py`, `tools/wsl_console.py`, `tools/wsl_console_preflight.py`, `tools/wsl_db_test.py`, `tools/wsl_endpoint_acceptance.py`, `tools/wsl_git_dns.py`, `tools/wsl_keycloak_admin.py`, `tools/wsl_lab.py`, `tools/wsl_lab_acceptance.py`, `tools/wsl_platform.py`, `tools/wsl_runtime_secrets.py` |
| `vcloud-wsl-local-CA` | WSL-only mechanism retired by WO-28; no dev resource | `lab/wsl/prepare-tls.sh` |
| `vcloud-wsl-localstack` | Excluded from WO-21; future component work order uses `twinfra-` names | `tools/wsl_localstack.py` |
| `vcloud-wsl-localstack-access` | WSL-only mechanism retired by WO-28; no dev resource | `docs/WSL_SETUP_GUIDE.md`, `lab/wsl/localstack/README.md`, `lab/wsl/localstack/access.sh` |
| `vcloud-wsl-ok` | `twinfra-ok` | `docs/service-access.md`, `lab/wsl/access.sh`, `lab/wsl/bootstrap.sh`, `lab/wsl/test-network.sh`, `lab/wsl/verify-access.ps1`, `tools/wsl_lab.py` |
| `vcloud-wsl-openbao` | `twinfra-openbao` | `lab/wsl/endpoints/gitops/workloads.yaml` |
| `vcloud-wsl-openbao-db` | `twinfra-openbao-db` | `lab/wsl/endpoints/gitops/workloads.yaml`, `lab/wsl/gitops/workload.yaml` |
| `vcloud-wsl-openbao-init` | OpenBao activation deferred to WO-08; no initialization resource now | `docs/WSL_SETUP_GUIDE.md`, `lab/wsl/endpoints/access.sh` |
| `vcloud-wsl-openbao-tls` | `twinfra-openbao-tls` | `lab/wsl/endpoints/gitops/workloads.yaml` |
| `vcloud-wsl-operator` | WSL-only mechanism retired by WO-28; no dev resource | `tools/wsl_platform.py` |
| `vcloud-wsl-otel` | Excluded from WO-21; future component work order uses `twinfra-` names | `tools/wsl_endpoints.py` |
| `vcloud-wsl-pg` | Vetted PV path `/var/lib/twinfra/local-pv/postgres-1` | `lab/wsl/prepare-storage.sh` |
| `vcloud-wsl-platform` | `twinfra-platform` | `docs/WSL_SETUP_GUIDE.md`, `docs/correction-review-validation.json`, `docs/service-access.md`, `docs/wsl-local-milestones-3-5.md`, `lab/wsl/endpoints/deploy.sh`, `lab/wsl/reconcile-prerequisites.sh`, `lab/wsl/verify-access.ps1`, `tools/wsl_endpoint_acceptance.py`, `tools/wsl_platform.py` |
| `vcloud-wsl-postgres` | `twinfra-postgres` | `lab/wsl/endpoints/deploy.sh`, `lab/wsl/endpoints/gitops/workloads.yaml`, `lab/wsl/gitops/network.yaml`, `lab/wsl/gitops/workload.yaml`, `lab/wsl/platform.sh`, `lab/wsl/reconcile-prerequisites.sh`, `tools/wsl_db_scaler.py`, `tools/wsl_keycloak_admin.py`, `tools/wsl_platform.py` |
| `vcloud-wsl-postgres-1` | `twinfra-postgres-1` | `lab/wsl/PLATFORM.md`, `lab/wsl/gitops/workload.yaml`, `lab/wsl/platform.sh` |
| `vcloud-wsl-postgres-ca` | `twinfra-postgres-ca` | `lab/wsl/endpoints/gitops/workloads.yaml` |
| `vcloud-wsl-postgres-rw` | `twinfra-postgres-rw` | `lab/wsl/endpoints/gitops/workloads.yaml`, `lab/wsl/endpoints/runtime-config.py` |
| `vcloud-wsl-prerequisites` | Legacy bootstrap mechanism replaced by shared Module -1; no dev resource | `lab/wsl/reconcile-prerequisites.sh` |
| `vcloud-wsl-prom-operator` | Excluded from WO-21; future component work order uses `twinfra-` names | `tools/wsl_endpoints.py` |
| `vcloud-wsl-prometheus` | Excluded from WO-21; future component work order uses `twinfra-` names | `tools/wsl_endpoints.py` |
| `vcloud-wsl-prometheus-access` | WSL-only mechanism retired by WO-28; no dev resource | `lab/wsl/endpoints/access.sh` |
| `vcloud-wsl-proxy-marks` | WSL-only mechanism retired by WO-28; no dev resource | `docs/troubleshooting/argocd-repo-health-wsl.md`, `lab/wsl/bootstrap.sh`, `lab/wsl/vcloud-wsl-proxy-marks.service`, `lab/wsl/vcloud-wsl-proxy-marks.timer`, `tools/ci/run_checks.py` |
| `vcloud-wsl-redis` | `twinfra-argocd-cache` Secret; cache keeps upstream `argocd-redis` name | `lab/wsl/prepare-tls.sh` |
| `vcloud-wsl-smoke-gateway` | `twinfra-smoke-gateway` | `tools/wsl_endpoints.py` |
| `vcloud-wsl-tls` | WSL-only mechanism retired by WO-28; no dev resource | `lab/wsl/prepare-tls.sh` |

**TLS mount:** `vcloud-wsl-keycloak-tls` becomes `twinfra-keycloak-tls`, including the console and gateway trust mounts. The `ca.crt` key contains public CA trust; private `tls.key` is mounted only in Keycloak.

Names created dynamically from the old prefix follow the same rule: PostgreSQL operator-generated `-ca`, `-server`, `-replication`, `-app`, `-rw`, `-ro`, `-r`, ordinal Pods/PVCs and tester Jobs use the `twinfra-postgres` parent. Argo Applications/AppProjects and our bootstrap/configuration Secrets always use `twinfra-` even where an upstream workload keeps its fixed name.
