# WO-29: Make the dev environment runnable on the owner's PC

**Status:** Approved for implementation (architect review of merged PR #35, 2026-10-10; owner approves this order) · **Phase:** 2
**Author:** Claude · **Implementer:** Codex · **Branch:** `codex/wo-29-dev-runnable` · **Depends on:** WO-21 merged (PR #35)
**Decisions:** ADR-0032, ADR-0038, ADR-0046, ADR-0047

## Why

The architect's review of PR #35 found that the script is safe, but the owner cannot run it on this host as merged. These checks were made on the host on 2026-10-10:

| Finding | Evidence | Effect |
| --- | --- | --- |
| PowerShell 7 is not installed. The script uses `ConvertFrom-Json -AsHashtable` and has no `#Requires`. | `pwsh` not found; Windows PowerShell 5.1 only | The script fails at once with an unclear error |
| The disk guard needs `DiskGB + 35` = 135 GiB free on E:. | E: has 113.6 GiB free | The plan refuses. The 35 GiB reserve is about four times what the conversion uses (0.6 GiB image, about 3.5 GiB raw VHD, about 3.5 GiB initial VHDX) |
| The RAM guard needs `MemoryGB + 4` = 28 GiB free with the 24 GiB default. | 31.7 GiB host. Windows, the browsers and the desktop apps need about 6-8 GiB | 28 GiB free is not reachable in normal use. The architect's 24 GiB sizing was too high |
| Bootstrap needs a reachable private registry `registry.twinfra.example.com` with every image staged, plus a pull Secret. | `docs/dev-environment.md` lines 108-114 | The owner has no registry. The WSL environment avoided this by pulling, verifying and importing images itself |
| Keycloak, OpenBao and Argo CD TLS come "through the owner's PKI". | `docs/dev-environment.md` lines 140-146, 192 | The owner has no PKI. WO-08 (cert-manager and OpenBao PKI) is the long-term answer, but it needs a running cluster first |

## Scope

1. **PowerShell 7.** Add `#Requires -Version 7.4` to `deploy/hyperv/New-TwinfraDev.ps1` and `Twinfra.psm1`. If `pwsh` is missing, the README gives the exact
   install command, `winget install --id Microsoft.PowerShell --source winget` (MIT, Microsoft), as an owner action. Do not install it.
2. **Disk reserve.** Reduce the conversion and cache reserve from 35 GiB to **10 GiB** (the guard becomes `DiskGB + 10`). Delete `canonical-base.vhd` after a successful
   `Convert-VHD`. If an image file in the cache has the wrong size or hash, report "delete <path> and rerun"; never delete it automatically.
3. **Memory default.** Change the default `-MemoryGB` to **20** (the guard becomes 24 GiB free). Recompute the RAM budget table in `docs/dev-environment.md`
   for 20 GiB and say which components shrink, keeping at least 1 GiB headroom. The plan output states the free RAM it measured and what to close if it is short.
4. **Local image staging instead of a registry** (dev only; the production profile is unchanged):
   - Add `python3 tools/platform_dev.py stage-images --context twinfra-dev-cairo-1 --ssh <user>@10.50.0.10`. It reads `deploy/common/images.lock.json`, and inside the VM,
     over SSH, it runs `ctr -n k8s.io images pull --platform linux/amd64 <upstream>@<digest>`, checks that the digest matches the lock, then
     `ctr -n k8s.io images tag` to the canonical `registry.twinfra.example.com/...` name. Locally built images (console, PostgreSQL with pgvector) are copied as OCI archives and
     loaded with `ctr -n k8s.io images import`, then verified by digest.
   - It uses only tools already present: containerd's `ctr` in the VM, and OpenSSH and Python on the host. No new third-party tool.
   - In the dev overlay, `imagePullPolicy` is `IfNotPresent` and there is **no** `twinfra-registry-cred` requirement. A missing image fails with a clear message.
     The container runtime has no upstream fallback at run time, the same rule as before.
   - The command is idempotent. A `--check` mode lists missing or mismatched images and changes nothing.
5. **Development certificate authority** (dev only, replaced by WO-08):
   - Add `python3 tools/platform_dev_ca.py --out E:/Twinfra/secrets/dev-ca` using the `cryptography` library already in the licence register.
   - It creates a dev root CA (10 years, EC P-256) and leaf certificates for Keycloak, OpenBao and Argo CD, with the SANs listed in `docs/dev-environment.md`.
   - The output directory is outside the repository. Private keys are written with an owner-only ACL, and the tool refuses to write inside the Git working tree.
   - `--apply --context twinfra-dev-cairo-1` creates `twinfra-keycloak-tls`, `twinfra-openbao-tls` and the `argocd-secret` TLS keys through kubectl standard input, and prints names only.
   - The README explains how to trust the dev root CA in the owner's browser (Windows certificate store, CurrentUser\Root, `certutil -user -addstore Root`), and how to remove it.
6. **Runbook.** Rewrite the owner procedure in `docs/dev-environment.md` as numbered steps, each with its command and the expected output:
   install PowerShell 7 → `wsl --shutdown` → plan → provision → start the VM → wait for cloud-init → copy kubeconfig → `stage-images` → bootstrap → `platform_dev_ca.py --apply` → secrets → Argo CD sync → browser checks.
   Every step that changes the host or the cluster is marked as an owner action.
7. **Tests:** the PowerShell 7 requirement (a test asserts the `#Requires` line); the disk guard at 110 GiB passes and at 109 GiB fails; the memory default of 20 with the guard at 24;
   `stage-images` with a fake `ssh` and `ctr` covering a digest mismatch (fail), an already-staged image (no-op) and `--check` (no changes); the dev CA's SANs, key usage and refusal to write in the repo.

## Out of scope

A real private registry, cert-manager and OpenBao PKI (WO-08), changes to the production profile, and running anything on the owner's host.

## Acceptance criteria

- The PR gate is green, including the historical baselines and the licence gate.
- `-Plan` with a fixture of 113 GiB free disk and 24 GiB free RAM passes with the new defaults.
- Live (owner, after merge): the plan passes on this host; the VM is created and boots; `stage-images --check` reports nothing missing; all pods in the dev overlay are Running;
  the browser reaches Keycloak and the console over HTTPS with the dev CA trusted. Receipt: update `docs/acceptance/dev-environment-<date>.md`, with the tester sign-off left Pending.

## Report back

The changed files, the new RAM budget, the `-Plan` output with the new defaults, and the list of images that `stage-images` handles (upstream and locally built).

## Amendment 1 (2026-10-10, architect): resolves Codex's three stops (bootstrap order, bootstrap inventory, console HTTPS)

This amendment supersedes scope items 4 and 5 and the runbook order where it contradicts them.

### A. Two inventories, staged at two different times

1. **Bootstrap inventory, staged by cloud-init inside the VM before the registry preflight and before kubeadm.**
   - New lock `deploy/common/bootstrap-images.lock.json`: every image the dev profile's bootstrap actually runs. That means the control plane
     (`kube-apiserver`, `kube-controller-manager`, `kube-scheduler`, plus `kube-proxy` only if the profile installs it), `etcd`, `coredns`, `pause`, the Cilium agent,
     operator and envoy, the registry probe image (busybox), and the smoke-test images that `RUN_SMOKE_TESTS` uses. Each entry has the upstream reference, the canonical
     `registry.twinfra.example.com/...` name and a verified digest, for linux/amd64.
   - Derive the list from the pinned versions already in `00-setup-ubuntu-host.sh`, `vcloud-ssot.yaml` and the vendored Cilium chart. Do not guess.
     A CI test renders the dev bootstrap configuration (the kubeadm config, the Cilium values, the containerd `sandbox_image` and the smoke manifests) and fails if the image set differs from the lock.
   - The lock is embedded in the generated dev NoCloud seed (`/etc/twinfra/bootstrap-images.lock.json`, generated, never hand-edited).
2. **Application inventory** (`deploy/common/images.lock.json`, the ten images including the locally built console and PostgreSQL with pgvector) stays as in scope item 4:
   it is staged after bootstrap over SSH with `tools/platform_dev.py stage-images`, once the kubeconfig exists.

### B. Dev-only replacement for the registry preflight

1. Add a setting `IMAGE_STAGING` (default `false`). The generated SSoT validation allows `IMAGE_STAGING=true` **only** for the `dev-cairo-1` and `dev-cairo-2` profiles.
   Production refuses it, and a test proves this. `MIRROR_REQUIRED` stays `true` for dev, so the CRI configuration keeps **no upstream fallback**: kubelet can never pull from the internet.
2. With `IMAGE_STAGING=true`, Module -1 runs a `stage_bootstrap_images` step right after containerd is running and **instead of** the mirror reachability probe and `crictl pull`:
   - for each lock entry: `ctr -n k8s.io images pull --platform linux/amd64 <upstream>@<digest>`, using the upstream registry directly. Pass `ctr` an explicit empty hosts directory so it does not read
     `/etc/containerd/certs.d`. Then verify the digest, then `ctr -n k8s.io images tag` to the canonical name;
   - then verify that **every** lock entry is present under its canonical name with the locked digest (`crictl inspecti`). Any miss stops bootstrap with a clear message;
   - set `MIRROR_STATUS=staged-verified` in the existing status JSON.
   It must be idempotent: on a rerun, already-staged images are skipped after the digest check.
3. kubeadm then finds every image locally and pulls nothing. The production behaviour, the production profile values and the production mirror preflight do not change.
   The generated production `user-data` changes only because the script gains the guarded dev step; say so in the PR.
4. Tests: production with `IMAGE_STAGING=true` (refused); dev staging with a fake `ctr` covering a digest mismatch (stop), a missing image after staging (stop), and a rerun (no-op);
   dev with `IMAGE_STAGING=false` (the existing registry preflight runs unchanged).

### C. Console over HTTPS

1. The gateway (standalone APISIX) terminates TLS on **9443** with Secret `twinfra-gateway-tls`. The plain-HTTP listener on 9080 is removed from the Service and the
   readiness probe moves to 9443. Session cookies are `Secure`.
2. The dev CA (scope item 5) also issues `twinfra-gateway-tls` with SAN `console.dev.cairo-1.twinfra.example.com` (and the `cairo-2` name for that overlay).
3. **Access stays tunnel-only** (no new exposure). On the VM: `kubectl port-forward svc/twinfra-gateway 18444:9443`, bound to loopback. From Windows: an SSH tunnel for 18444, 18443 and 18081.
   In the Windows hosts file (owner action), the three names map to `127.0.0.1`.
4. Keycloak client: redirect URI `https://console.dev.cairo-1.twinfra.example.com:18444/console/callback`, web origin `https://console.dev.cairo-1.twinfra.example.com:18444`, and post-logout
   `https://console.dev.cairo-1.twinfra.example.com:18444/console/`. Update the APISIX `openid-connect` `redirect_uri` and the docs to match. No `http://` console URL remains in the dev overlay.
5. Tests: the rendered realm has only `https://` console URIs; the gateway Service exposes only 9443; the dev CA leaf for the gateway has the right SAN and `serverAuth` key usage.

### D. Runbook order (replaces scope item 6's order)

Install PowerShell 7 → `wsl --shutdown` → `-Plan` → provision → **create the dev CA** (host, files outside the repo) → start the VM → cloud-init stages the bootstrap images and runs kubeadm
→ copy the kubeconfig → `stage-images` (application images) → `platform_dev_ca.py --apply` (Keycloak, OpenBao, Argo CD, gateway) → platform bootstrap and secrets → Argo CD sync
→ hosts file and tunnels → trust the dev root CA → browser checks over HTTPS.
