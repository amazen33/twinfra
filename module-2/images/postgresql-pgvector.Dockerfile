# Build on a reviewed external build VM, not a privileged Kubernetes build pod.
# Stage BOTH upstream digests in the canonical registry before entering the air gap.
FROM registry.vcloud.example.com/ghcr.io/cloudnative-pg/pgvector@sha256:79fc129f885e2143bf6eb656a6b181ea449d1ef1a58c40fe5860986ed99bafcb AS vector
FROM registry.vcloud.example.com/ghcr.io/cloudnative-pg/postgresql@sha256:37ade18dbdddba430858c72725aceeec66f33fa5333e82ea1df4942f6c1c83a3
# Root is needed only in this image BUILD stage to install immutable extension files.
USER 0
COPY --from=vector /lib/ /usr/lib/postgresql/18/lib/
COPY --from=vector /share/extension/ /usr/share/postgresql/18/extension/
USER 26:26
# No ImageVolume dependency: this baked image works with the existing containerd CRI.
