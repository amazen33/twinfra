# Build-only root is needed to set ownership of APISIX's generated configuration.
# Mirror/scan this exact base version; publish an immutable derivative digest.
FROM registry.vcloud.example.com/docker.io/apache/apisix:3.19.0-ubuntu
USER 0
RUN chown -R 65532:65532 /usr/local/apisix/conf /usr/local/apisix/logs
USER 65532:65532
