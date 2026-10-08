# Build from repository root: docker build -f console/Dockerfile .
# Only this build stage uses a connected package registry. Runtime is offline.
FROM node:24.15.0-alpine3.23 AS frontend
WORKDIR /build
COPY console/package.json console/package-lock.json ./
RUN npm ci --ignore-scripts --no-audit --no-fund
COPY console/src/ ./src/
COPY console/index.html console/tsconfig.json console/vite.config.ts ./
RUN npm run build

FROM python:3.14.1-slim-trixie@sha256:b823ded4377ebb5ff1af5926702df2284e53cecbc6e3549e93a19d8632a1897e
WORKDIR /app
COPY --from=frontend --chown=65532:65532 /build/dist/ /app/public/
COPY --chown=65532:65532 console/server.py /app/server.py
COPY --chown=65532:65532 lab/wsl/console/ui.py /app/aws_views.py
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PORT=3000
USER 65532:65532
EXPOSE 3000
HEALTHCHECK --interval=20s --timeout=3s CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:3000/healthz',timeout=2)"]
ENTRYPOINT ["python", "-B", "/app/server.py"]
