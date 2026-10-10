# Stage this base in the private registry before configuring the builder.
FROM registry.vcloud.example.com/docker.io/library/python:3.14.1-slim-trixie@sha256:b823ded4377ebb5ff1af5926702df2284e53cecbc6e3549e93a19d8632a1897e
ARG SOURCE_REVISION
LABEL org.opencontainers.image.source="https://github.com/amazen33/twinfra" org.opencontainers.image.revision="${SOURCE_REVISION}"
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PORT=8080
WORKDIR /app
COPY --chown=65532:65532 app.py /app/app.py
USER 65532:65532
EXPOSE 8080
CMD ["python3", "/app/app.py"]
