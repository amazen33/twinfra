# Build from repository root: docker build -f console/Dockerfile .
# Only this build stage uses a connected package registry. Runtime is offline.
FROM node:24.15.0-alpine3.23@sha256:d1b3b4da11eefd5941e7f0b9cf17783fc99d9c6fc34884a665f40a06dbdfc94f AS frontend
WORKDIR /home/node
USER node
COPY --chown=node:node console/package.json console/package-lock.json ./
RUN npm ci --ignore-scripts --no-audit --no-fund
COPY --chown=node:node console/src/ ./src/
COPY --chown=node:node console/index.html console/tsconfig.json console/vite.config.ts ./
RUN npm run build

FROM python:3.14.8-slim-trixie@sha256:a2b82f3c48559aa0a8446d9af49826b6e2b2016f4cd2afabfe6013ec53729170
WORKDIR /app
COPY console/requirements.txt /app/requirements.txt
RUN python -m pip install --require-hashes --only-binary=:all: --no-compile --no-cache-dir --target /app/vendor -r /app/requirements.txt
COPY --from=frontend --chown=65532:65532 /home/node/dist/ /app/public/
COPY --chown=65532:65532 console/server.py /app/server.py
COPY --chown=65532:65532 console/aws_views.py /app/aws_views.py
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHONPATH=/app/vendor PORT=3000
USER 65532:65532
EXPOSE 3000
HEALTHCHECK --interval=20s --timeout=3s CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:3000/healthz',timeout=2)"]
ENTRYPOINT ["python", "-B", "/app/server.py"]
