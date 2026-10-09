# Build from the repository root for Linux amd64 / Python 3.14.
# Mirror this exact upstream digest before building in the disconnected registry.
FROM registry.vcloud.example.com/docker.io/library/python:3.14.1-slim-trixie@sha256:b823ded4377ebb5ff1af5926702df2284e53cecbc6e3549e93a19d8632a1897e
COPY module-5a/requirements-runtime.lock.txt /opt/vcloud/requirements-runtime.lock.txt
# Reviewed full licence texts and corresponding-source references; no build-time fetch.
COPY security/licences/rag/ /usr/share/licenses/vcloud-rag/
# Image assembly needs a wheel mirror or a connected build executor. Every
# dependency, including the CPU encoder and native PostgreSQL driver, is hashed.
RUN python -m pip install --no-cache-dir --require-hashes --only-binary=:all: \
    -r /opt/vcloud/requirements-runtime.lock.txt
COPY module-5a/rag/pipeline.py /opt/vcloud/pipeline.py
ENV PYTHONDONTWRITEBYTECODE=1 HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 \
    LANGSMITH_TRACING=false LANGCHAIN_TRACING_V2=false HOME=/tmp
USER 65532:65532
ENTRYPOINT ["python", "/opt/vcloud/pipeline.py"]
