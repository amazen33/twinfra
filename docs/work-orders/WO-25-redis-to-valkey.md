# WO-25: Replace Redis with Valkey in the Argo CD base

**Status:** Approved for implementation (owner, 2026-10-09) · **Phase:** 1 · **Author:** Claude · **Implementer:** Codex
**Branch:** `codex/wo-25-valkey` · **Decisions:** ADR-0044 decision 5, ADR-0030 · **Depends on:** WO-02 merged

## Goal

Remove the only known licence gap in what runs. Redis 8.2.3 is offered under RSALv2, SSPLv1 or AGPLv3, and none is permitted. Valkey
(BSD-3-Clause, Linux Foundation, Redis-protocol compatible) takes its place as the `argocd-redis` cache, pinned by digest. The Redis entry
in the licence register is `pending-removal` and expires 2026-12-08.

## Verified context (`origin/main`)

- The vendored Argo CD v3.5.3 install (`deploy/kustomize/base/argocd/install.yaml`, line 32857) runs `public.ecr.aws/docker/library/redis:8.2.3-alpine`
  as Deployment `argocd-redis`, with args `--save '' --appendonly no --requirepass $(REDIS_PASSWORD)`, `runAsUser 999`, a read-only root
  filesystem, and Service port `tcp-redis` 6379. The password comes from Secret `argocd-redis` key `auth`. Argo CD clients read `REDIS_PASSWORD`,
  `REDIS_SERVER` and related settings, which do not change.
- The image is also pinned in `deploy/kustomize/overlays/vcloud-local/kustomization.yaml` (lines 16-17, registry mirror rename),
  `deploy/registry-images.lock.json` (line 20), `deploy/required-images.txt` (line 3) and `lab/wsl/platform-images.txt` (line 3).
- `tools/wsl_platform.py` (around lines 68-73) builds a custom `argocd-redis` command that runs `redis-server` from a generated config. That generator
  stays in CI until WO-28 removes the WSL lab.
- Valkey stable releases seen on 2026-10-09: 9.1.2 and 8.1.10 (both published about 2026-08-31 or 2026-09-01), so both pass the 14-day rule.
  Image: `docker.io/valkey/valkey`.
- Cache only: Argo CD's Redis stores no durable state (`--save ''`, `--appendonly no`), so there is no data migration.

## Scope

1. **Choose and pin.** Use the newest patch of the Valkey line you can verify against Argo CD 3.5.3's Redis usage: start with **`8.1.x-alpine`**
   (the closest to the Redis 7.2 and 8 behaviour Argo CD was built against) and move to 9.x only if the owner asks. Record the exact tag **and
   digest**, plus the date it was published (at least 14 days old).
2. **Swap the image without editing the vendored file.** Use the kustomize `images:` transformer in the base or overlay to replace
   `public.ecr.aws/docker/library/redis` with the Valkey image, keeping the existing registry-mirror rename for the overlay. Keep
   `deploy/vendor/argocd-v3.5.3-install.yaml.gz` and `install.yaml` unchanged unless a container `command` must change.
3. **Check the entrypoint.** Confirm from the pinned image's metadata that the arguments (`--save`, `--appendonly`, `--requirepass`) reach
   `valkey-server` and that it runs as UID 999 with a read-only root filesystem (needs `/data` as an `emptyDir` or no writes). If a `command` or an
   `emptyDir` is needed, add it with a kustomize patch, never by hand-editing the vendored manifest.
4. **Update every pin and generator through its generator:** `deploy/registry-images.lock.json`, `deploy/required-images.txt`,
   `lab/wsl/platform-images.txt`, and `tools/wsl_platform.py` (use `valkey-server` or the compatible `redis-server` link, whichever the image provides,
   and verify which). Regenerate any rendered output the repository commits.
5. **Licence register and baseline (ADR-0044).** Remove the Redis `pending-removal` entry and its three pins. Add Valkey as `allowed`
   (BSD-3-Clause, with the licence source at the pinned version) and an `image-sbom` baseline finding that expires within 90 days, like the other images.
   The gate must stay green and print no Redis entry.
6. **Docs.** Update the image tables and the Argo CD notes that name Redis. Mention that the Redis protocol, port, Secret and
   `REDIS_*` variables are unchanged. Add a line to the ADR index entry for ADR-0044 stating that decision 5 is implemented by this work order.

## Out of scope

Redis HA or a Valkey cluster; Valkey for any application cache; Argo CD upgrades; downgrading to Redis 7.2.x (no security fixes); Redis in `module-5*`
(none found, but report anything you find).

## Acceptance criteria

- **Static (this PR):** the PR gate is green including the six historical revisions; the licence gate shows no Redis entry and a Valkey `allowed` entry; no
  Redis image appears in **deployable output** (see the definition below); `kustomize build` and kubeconform pass; the rendered `argocd-redis` container uses the pinned Valkey digest.
- **Live (on the VM lab `lab-1` when WO-21 deploys Argo CD, or on any cluster the owner approves):**
  - Valkey is running as `argocd-redis`, with an authenticated ping succeeding and an unauthenticated one rejected (`NOAUTH`);
  - the application controller, repo server and API server connect (no cache errors in their logs);
  - an Application syncs and shows Synced and Healthy; the cache is hit on a repeat sync;
  - after deleting the `argocd-redis` pod, everything reconnects without manual action.
- Receipt: `docs/acceptance/valkey-<date>.md`, with the tester sign-off left Pending. No live change is made by the static PR.

## Owner actions

Approve the live rollout (on `lab-1`), and sign off as tester. If a Valkey incompatibility appears, I decide the fallback; do not reintroduce Redis.

## Report back

The pinned tag, digest and publication date; the entrypoint findings; the files changed; whether `tools/wsl_platform.py` needed a command change; the
register and baseline changes; and the check results.

## Amendment 1 (2026-10-09, architect; resolves Codex's stop on the scope and acceptance contradiction)

"Deployable output" means every place the Redis image could be pulled or run:
- the output of `kustomize build` for the base and every overlay;
- the image lists and locks (`deploy/registry-images.lock.json`, `deploy/required-images.txt`, `lab/wsl/platform-images.txt`);
- generator output that is committed or rendered in CI (including `tools/wsl_platform.py` output);
- the licence register and baseline.

The static acceptance check fails if the Redis image reference (`library/redis`) appears in deployable output. **These are excluded and may keep the string:**
1. the preserved upstream sources: `deploy/kustomize/base/argocd/install.yaml` and `deploy/vendor/argocd-v3.5.3-install.yaml.gz`;
2. the kustomize transformer's **match key** (`name: public.ecr.aws/docker/library/redis` in the `images:` entry), which must name the image it replaces;
3. history and context: ADRs, work orders (including this one), acceptance receipts and the licence-gate documentation that explains the removal.

Add a test that renders the overlay and fails when the Redis image appears in the rendered output, and a test that the preserved sources still contain it
(so the transformer cannot silently stop matching). Nothing else in this work order changes.
