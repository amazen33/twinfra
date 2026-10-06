# Connected staging only. Runtime Tasks never install tools or download dependencies.
FROM registry.vcloud.example.com/docker.io/library/python:3.14.1-slim-trixie@sha256:b823ded4377ebb5ff1af5926702df2284e53cecbc6e3549e93a19d8632a1897e
# Build-time UID 0 is required to install OS packages; it is not the runtime identity.
USER 0
RUN apt-get update && apt-get install -y --no-install-recommends bash git make jq openssl ca-certificates \
    && rm -rf /var/lib/apt/lists/*
COPY .build/module-3-toolchain/bin/ /usr/local/bin/
COPY tests/requirements.txt /tmp/test-requirements.txt
RUN pip install --no-cache-dir -r /tmp/test-requirements.txt && rm /tmp/test-requirements.txt
COPY module-5b/requirements.txt /tmp/hpc-requirements.txt
COPY .build/module-5b/wheels/ /opt/hpc-wheels/
RUN pip install --require-hashes --no-index --find-links=/opt/hpc-wheels -r /tmp/hpc-requirements.txt && rm -rf /opt/hpc-wheels /tmp/hpc-requirements.txt
COPY module-3/runtime/ /opt/vcloud-ci/
COPY module-3/gitops/workload.yaml /opt/vcloud-ci/workload-template.yaml
COPY module-2/schemas/serving.knative.dev/service_v1.json /opt/vcloud-ci/schemas/serving.knative.dev/service_v1.json
RUN chmod 0755 /usr/local/bin/buildctl /usr/local/bin/helm /usr/local/bin/kubeconform /usr/local/bin/promtool /opt/vcloud-ci/askpass.py \
    && helm version --short && kubeconform -v && buildctl --version && promtool --version
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 HOME=/tmp
USER 65532:65532
WORKDIR /tmp
CMD ["python3", "/opt/vcloud-ci/runner.py", "test"]
