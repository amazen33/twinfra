FROM registry.vcloud.example.com/docker.io/library/python:3.14.1-slim-trixie@sha256:b823ded4377ebb5ff1af5926702df2284e53cecbc6e3549e93a19d8632a1897e
COPY module-5b/requirements.txt /opt/vcloud/requirements.txt
# Dependencies are staged as hash-locked wheels before an offline image build.
# No package download or build step executes in a deployed Pod.
COPY .build/module-5b/wheels/ /opt/wheels/
RUN python -m pip install --require-hashes --no-index --find-links=/opt/wheels -r /opt/vcloud/requirements.txt && rm -rf /opt/wheels
COPY module-5b/runtime/ /opt/vcloud/
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
USER 65532:65532
WORKDIR /opt/vcloud
ENTRYPOINT ["python", "/opt/vcloud/server.py"]
CMD ["--mode", "agent"]
