# Local GitOps and PostgreSQL acceptance

This stage extends the owned `vcloud-wsl-local` cluster. It does not promote the
production root Application or enable GPU, AI or Spinifex workloads.

## Current gate

The deny-all test passed with matching Cilium drop events. Argo CD and CNPG
controller manifests are installed, but host probe/callback drops prevent
controller readiness. The proposed [WSL Host Firewall exception](HOST-FIREWALL-EXCEPTION.md)
requires an explicit decision before deployment continues. GitOps reconciliation
and SQL acceptance are not complete. This document describes the executable
acceptance procedure, not a successful deployment claim.

## Reproducible inputs

`platform-artifacts.lock.json` locks official Argo CD 3.5.3 Core, CloudNativePG
1.30.1 and metrics-server 0.9.0 manifests and strict Kubernetes 1.36.5 schemas.
The CNPG/Argo custom resource schemas are validated with the repository's
vendored CRD schemas. Missing schemas fail validation.

Connected staging explicitly pulls `platform-images.txt` and imports canonical
registry aliases into the private local CRI cache. `tools/wsl_pg_image.py`
constructs the PostgreSQL 18.6 + pgvector 0.8.2 image from two immutable OCI
parents, matching the production Dockerfile's extension paths. Its image receipt
records both parent digests, layer digests and runtime UID/GID 26. No privileged
builder or Docker socket is mounted. Runtime private registry fallback remains
disabled; staging does not establish air-gap or private registry availability.

## Vetted Local PV

`prepare-storage.sh` verifies ownership and actual host state before creating
one fresh 4 GiB ext4 loop filesystem. The root-only backing image is
`/var/lib/vcloud-wsl/volumes/postgres-1.ext4`; the mount is
`/var/lib/vcloud-wsl/storage/postgres-1`, UID/GID 26, mode 0700, with
`nodev,nosuid,noexec`. An ownership marker records the exact path and size.
The script rejects unrelated existing data or mounts and performs no recursive
chown or automatic deletion. A systemd mount and K3s dependency restore the
mount before the cluster service starts; restart recovery needs its own test.

The static `vcloud-wsl-postgres-1` Local PV has capacity 4 GiB, `Retain`, exact
node affinity `vcloud-wsl-local`, and claim reservation for
`platform-services/vcloud-wsl-postgres-1`. The non-default StorageClass uses
`kubernetes.io/no-provisioner`, delayed binding, and no expansion. Application
Pods use a PVC; they receive no hostPath. The local validator admits only this
exact PV path and node, without changing frozen production exceptions.
This finite development volume has no HA, external backup or DR guarantee.

## Continuous reconciliation

Argo CD Core uses the public Git repository `https://github.com/amazen33/vCloud.git`,
the lab source branch `codex/wsl-local-bootstrap`, and `lab/wsl/gitops`. Publish
the tested source before applying `.build/wsl-platform/application.yaml`.
The AppProject permits only the `platform-services` destination and explicit
workload kinds. Namespace write RBAC does not grant PV/StorageClass changes.
The controller has read-only cluster discovery rights. Automatic self-healing
is enabled; automatic prune and empty-source deletion are disabled.

The repo server verifies its private service TLS certificate. Its DNS service
forwards only `github.com` externally and cluster-local queries internally.
Cilium limits HTTPS egress to `github.com`; broad DNS/world allowances are absent.
Argo Core has no publicly exposed UI or API. Credentials are generated in
Kubernetes Secrets and never copied to Git. Thirty-day local serving certificates
require rotation; OpenBao certificate lifecycle integration is a later stage.

Acceptance requires a `Synced`/`Healthy` Application at the published commit and
an observed self-heal of the `vcloud-wsl-gitops-marker` ConfigMap after changing
its `state` from `managed-by-github` to `drift-test`.

## PostgreSQL and automatic growth

One CNPG instance initializes database `vcloud`, application role `vcloud_app`
and the `vector` extension. The Pod uses UID/GID 26, dropped capabilities and
restricted security. Local HugePages are bypassed. TLS and SCRAM authentication
are required; the acceptance client verifies the server's CA and DNS name.

Initial requests and limits are 500m CPU / 512 MiB. A restricted CronJob obtains
three actual metrics samples, 16 seconds apart, and patches only this named CNPG
Cluster when a healthy, stable primary exceeds 85% CPU or memory in every sample.
Growth is 25%, capped at 1 CPU / 1 GiB, with a 30-minute cooldown and no shrink.
CNPG owns the resulting instance rollout. Optimistic JSON-patch tests prevent
overwriting concurrent changes. Argo ignores the scaler-owned resource fields
and timestamp, and respects that ownership during sync. This is bounded vertical
growth, not replica autoscaling or a claim that CNPG provides a built-in HPA.

## Execute and inspect

Inside the owned WSL Ubuntu distribution:

```bash
cd /mnt/e/vCloud
sudo bash lab/wsl/test-network.sh
sudo python3 tools/stage_wsl_platform.py --cache .tools/wsl-platform
sudo python3 tools/wsl_pg_image.py --cache .tools/wsl-platform
python3 tools/wsl_platform.py render --gitops
python3 tools/wsl_platform.py validate --kubeconform .tools/wsl-lab/kubeconform
# Continue only after resolving the controller-health compatibility gate.
sudo bash lab/wsl/platform.sh
sudo python3 tools/wsl_db_test.py --restart
sudo /usr/local/bin/k3s kubectl --kubeconfig /etc/vcloud-wsl/kubeconfig.yaml \
  --context vcloud-wsl-local apply -f .build/wsl-platform/application.yaml
```

The SQL client mounts only the application credentials and public CA. Its
password file exists only in a memory-backed volume with mode 0600. Tests assert
PostgreSQL/pgvector versions, verified TLS, vector distance and retained data
after recreating only the database instance Pod. Deleting that Pod does not
delete the PVC, PV or backing filesystem.

Sanitized evidence is written to `.build/wsl-network/acceptance.json` and
`.build/wsl-platform/database-acceptance.json`. Argo sync, real CPU-driven growth
and final live Pod security audits must also pass before this stage is accepted.
Static tests alone do not prove these runtime outcomes.
