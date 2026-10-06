FROM registry.vcloud.example.com/docker.io/library/python:3.14.1-slim-trixie@sha256:b823ded4377ebb5ff1af5926702df2284e53cecbc6e3549e93a19d8632a1897e
# Build-time UID 0 installs the clients; runtime and validation use UID 65532.
USER 0
RUN apt-get update && apt-get install -y --no-install-recommends bash curl jq postgresql-client util-linux ca-certificates \
    && rm -rf /var/lib/apt/lists/*
COPY module-4a/scripts/ /opt/vcloud/
COPY module-4a/runtime/check-csi.py /opt/vcloud/check-csi.py
COPY module-4a/openbao/ /opt/openbao/
RUN chmod 0555 /opt/vcloud/*.sh /opt/vcloud/check-csi.py
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
USER 65532:65532
WORKDIR /tmp
CMD ["sleep", "infinity"]
