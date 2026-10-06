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
RUN = $(PYTHON) tools/module2.py --site "$(SITE)" --build "$(BUILD)" --helm "$(HELM)" --kubeconform "$(KUBECONFORM)" --kubectl "$(KUBECTL)"

.PHONY: host-check validate render diff apply prepare test help
help:
	@printf '%s\n' 'Copy module-2/site-values.example.yaml to module-2/site-values.yaml and configure it.' 'host-check: read-only Ubuntu/eBPF/GPU/storage verification (sudo for the kernel probe)' 'render: local helm template for Cilium and foundation resources' 'validate: render + strict offline kubeconform + SSoT/semantic checks' 'prepare: target/host checks + narrow controller network preparation' 'diff: validated kubectl diff; changes are a successful comparison, errors fail' 'apply: validate + fresh host/live checks + Cilium upgrade + ordered apply' 'test: offline guardrail tests'
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
