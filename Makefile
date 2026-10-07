# Module 2. All targets consume local artifacts; none downloads dependencies.
SHELL := /bin/bash
.SHELLFLAGS := -eu -o pipefail -c
.DELETE_ON_ERROR:
PYTHON ?= python3
HELM ?= helm
KUBECONFORM ?= kubeconform
KUBECTL ?= kubectl
SITE ?= module-2/site-values.yaml
BUILD ?= .build/module-2
PROMTOOL ?= promtool
BASH_BINARY ?= $(SHELL)
JQ_BINARY ?= jq
KUSTOMIZE ?= kustomize
CONFTEST ?= conftest
RUN = $(PYTHON) tools/module2.py --site "$(SITE)" --build "$(BUILD)" --helm "$(HELM)" --kubeconform "$(KUBECONFORM)" --kubectl "$(KUBECTL)"

.PHONY: host-check validate render diff apply prepare test help module3-render module3-validate module3-test module3-preflight module3-alerts module4a-render module4a-validate module4a-test module4b-render module4b-validate module4b-test
help:
	@printf '%s\n' 'Copy module-2/site-values.example.yaml to module-2/site-values.yaml and configure it.' 'host-check: read-only Ubuntu/eBPF/GPU/storage verification (sudo for the kernel probe)' 'render: local helm template for Cilium and foundation resources' 'validate: render + strict offline kubeconform + SSoT/semantic checks' 'prepare: target/host checks + narrow controller network preparation' 'diff: validated kubectl diff; changes are a successful comparison, errors fail' 'apply: validate + fresh host/live checks + Cilium upgrade + ordered apply' 'test: offline guardrail tests'
	@printf '%s\n' 'module3-render / module3-validate: generate or check offline CI/CD manifests' 'module3-test / module3-alerts: CI/Git/HTTP contracts and Prometheus alert tests' 'module3-preflight CONTEXT=<reviewed context>: read-only cluster prerequisites'
	@printf '%s\n' 'module4a-render / module4a-validate / module4a-test: public OpenBao configuration, CSI patches and offline revocation guards'
	@printf '%s\n' 'module4b-render / module4b-validate / module4b-test: public Keycloak, APISIX OIDC and group RBAC references'
	@printf '%s\n' 'wsl-platform-recovery-plan / wsl-platform-recover: preview or apply probe policies, restart Argo CD and verify health' 'wsl-platform-probe-verify / wsl-platform-probe-test: read-only live health checks or offline recovery tests'
host-check:
	$(RUN) host-check
render:
	$(RUN) render
validate:
	$(RUN) validate
diff:
	@$(RUN) diff || { result=$$?; if [ "$$result" -eq 1 ]; then printf '%s\n' 'Differences found; review the diff before apply.'; else exit "$$result"; fi; }
apply:
	$(RUN) apply
prepare:
	$(RUN) prepare
test:
	$(PYTHON) -m unittest discover -s tests -p 'test_module2.py' -v
module3-render:
	$(PYTHON) tools/render_module3.py
module3-validate:
	$(PYTHON) tools/module3.py --kubeconform "$(KUBECONFORM)"
module3-test:
	$(PYTHON) -m unittest discover -s tests -p 'test_module3.py' -v
	$(PYTHON) -m unittest discover -s module-3/app -p 'test_app.py' -v
module3-preflight:
	$(PYTHON) tools/check_module3_cluster.py --kubectl "$(KUBECTL)" --context "$(CONTEXT)"
module3-alerts:
	$(PROMTOOL) check rules module-3/observability/rules.yaml
	$(PROMTOOL) test rules tests/module3-alerts.test.yaml
module4a-render:
	$(PYTHON) tools/render_module4a.py
module4a-validate:
	$(PYTHON) tools/module4a.py --kubeconform "$(KUBECONFORM)"
module4a-test:
	BASH_BINARY="$(BASH_BINARY)" JQ_BINARY="$(JQ_BINARY)" $(PYTHON) -m unittest discover -s tests -p 'test_module4a.py' -v
module4b-render:
	$(PYTHON) tools/render_module4b.py
module4b-validate:
	$(PYTHON) tools/module4b.py --kubeconform "$(KUBECONFORM)"
module4b-test:
	$(PYTHON) -m unittest discover -s tests -p 'test_module4b.py' -v

.PHONY: module5b-render module5b-validate module5b-test module5b-alerts module5b-wheels
module5b-render:
	$(PYTHON) tools/render_module5b.py
module5b-validate:
	$(PYTHON) tools/module5b.py --helm "$(HELM)" --kubeconform "$(KUBECONFORM)"
module5b-test:
	$(PYTHON) -m unittest discover -s tests -p 'test_module5b.py' -v
module5b-alerts:
	$(PROMTOOL) check rules module-5b/observability/rules.yaml
	$(PROMTOOL) test rules tests/module5b-alerts.test.yaml
module5b-wheels:
	$(PYTHON) tools/stage_module5b.py

.PHONY: module5a-render module5a-validate module5a-test
module5a-render:
	$(PYTHON) tools/render_module5a.py
module5a-validate:
	$(PYTHON) tools/module5a.py --kubeconform "$(KUBECONFORM)"
module5a-test:
	$(PYTHON) -m unittest discover -s tests -p test_module5a.py -v

# Invoke these targets inside WSL Ubuntu; no production target is substituted.
.PHONY: wsl-lab-plan wsl-lab-apply wsl-lab-validate wsl-lab-test
wsl-lab-plan:
	bash lab/wsl/bootstrap.sh --plan
wsl-lab-apply:
	sudo bash lab/wsl/bootstrap.sh --apply
wsl-lab-validate:
	sudo bash lab/wsl/bootstrap.sh --validate
wsl-lab-test:
	$(PYTHON) -m unittest discover -s tests -p test_wsl_lab.py -v

.PHONY: wsl-network-test wsl-platform-render wsl-platform-validate wsl-platform-apply wsl-platform-test wsl-database-test
wsl-network-test:
	sudo bash lab/wsl/test-network.sh
wsl-platform-render:
	$(PYTHON) tools/wsl_platform.py render --gitops
wsl-platform-validate:
	$(PYTHON) tools/wsl_platform.py validate --kubeconform "$(KUBECONFORM)"
wsl-platform-apply:
	sudo bash lab/wsl/platform.sh
wsl-platform-test:
	$(PYTHON) -m unittest discover -s tests -p test_wsl_platform.py -v
wsl-database-test:
	sudo python3 tools/wsl_db_test.py --restart

# Run on the WSL node with access to the private lab kubeconfig.
KUBE_CONTEXT ?= vcloud-wsl-local
.PHONY: wsl-platform-recovery-plan wsl-platform-recover wsl-platform-probe-verify wsl-platform-probe-test
wsl-platform-recovery-plan:
	KUBE_CONTEXT="$(KUBE_CONTEXT)" "$(BASH_BINARY)" deploy/network/platform-probes/recover.sh --plan
wsl-platform-recover:
	KUBE_CONTEXT="$(KUBE_CONTEXT)" "$(BASH_BINARY)" deploy/network/platform-probes/recover.sh
wsl-platform-probe-verify:
	KUBE_CONTEXT="$(KUBE_CONTEXT)" "$(BASH_BINARY)" deploy/network/platform-probes/apply-and-verify.sh --verify-only
wsl-platform-probe-test:
	BASH_BINARY="$(BASH_BINARY)" $(PYTHON) -m unittest discover -s tests -p test_platform_probes.py -v

.PHONY: airgap-validate airgap-test node-registry-plan node-preflight
airgap-validate:
	$(PYTHON) tools/airgap.py --kustomize "$(KUSTOMIZE)" --kubeconform "$(KUBECONFORM)" --conftest "$(CONFTEST)"
airgap-test:
	$(PYTHON) -m unittest discover -s tests/ci -v
node-registry-plan:
	bash scripts/bootstrap-node.sh --plan
node-preflight:
	bash scripts/validate-node.sh

.PHONY: wsl-endpoints-stage wsl-endpoints-render wsl-endpoints-validate wsl-endpoints-apply wsl-e2e wsl-openbao-init
wsl-endpoints-stage:
	sudo $(PYTHON) tools/stage_wsl_endpoints.py
wsl-endpoints-render:
	$(PYTHON) tools/wsl_endpoints.py render
wsl-endpoints-validate:
	$(PYTHON) tools/wsl_endpoints.py validate --kubeconform "$(KUBECONFORM)"
wsl-endpoints-apply:
	sudo bash lab/wsl/endpoints/deploy.sh
wsl-e2e:
	sudo bash lab/wsl/test-e2e.sh
wsl-openbao-init:
	sudo bash lab/wsl/endpoints/access.sh openbao
	sudo bash lab/wsl/openbao-init.sh
