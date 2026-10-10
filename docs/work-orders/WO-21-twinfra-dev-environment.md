# WO-21: Twinfra dev environment (`cairo-1`) with clean names, the always-on dev environment

**Status:** Approved for implementation (owner, 2026-10-09; backlog decision A) · **Phase:** 2 (moved earlier) · **Author:** Claude · **Implementer:** Codex
**Branch:** `codex/wo-21-dev-environment` · **Decisions:** ADR-0032, ADR-0036 (Stage C), ADR-0038 · **Depends on:** WO-20 Stage A merged

## Goal

Rebuild the always-on dev environment on an Ubuntu 24.04 VM under Hyper-V using Twinfra's real production profile
(Module -1: `00-setup-ubuntu-host.sh`, cloud-init `user-data.yaml`, kubeadm, Cilium), with clean names from
ADR-0038. The dev environment then runs the hardening work (WO-05 to WO-11) once, on the right platform.

## Verified host constraints (2026-10-09)

- 31.7 GB RAM; the WSL lab currently uses 20 GB until WO-28 retires it. The pCloud lab will not run at the same time (owner, 2026-10-09). Intel i7-11850H, 8 cores / 16 threads, which supports nested virtualization.
- Free disk: E: 115 GB, C: 18 GB, D: 23 GB.
- Therefore the VM and the full WSL lab cannot run together. When the VM is up, the WSL lab is stopped or reduced
  to a small dev profile (at most 4 GB).

## Scope

1. **VM provisioning.** Add `deploy/hyperv/` with a PowerShell script (MIT) that the **owner runs as administrator**. It:
   - creates one Generation 2 VM named `twinfra-dev-cairo-1`: 8 vCPU, 24 GB RAM (static), and a 100 GB dynamic VHDX on E:;
   - enables nested virtualization (`ExposeVirtualizationExtensions`) for KubeVirt later;
   - creates the internal NAT switch `twinfra-nat` with the static IP plan below (never reusing an existing range);
   - supplies Module -1 through a cloud-init NoCloud seed ISO.

   The script is idempotent, has a `-Plan` mode that changes nothing, and fails if the free RAM or disk is insufficient.
   Codex writes it and its offline tests. Codex does not run it.
2. **Bootstrap.** Module -1 with `BOOTSTRAP_K8S=true`: kubeadm and Cilium, exactly as the production profile. Any dev-only deviation
   goes in an overlay, documented, never as a fork of the script.
3. **Environment model (ADR-0032).**
   - Declare the `dev` environment in `vcloud-ssot.yaml` (still named that until Stage C), with region `cairo-1`.
     The region name depends on D10; use `cairo-1` as the default.
   - Add an app-of-apps for `dev` that Argo CD reads from protected `main`.
   - Platform components are **redeployed from Git, not migrated.** Dev data is disposable, except configuration
     kept as code (Keycloak realm, console client).
4. **Names (ADR-0038).** Every resource deployed to `cairo-1` uses `twinfra-<component>` names and the `twinfra.io/*` labels.
   This covers the Keycloak realm (`twinfra`) and the client IDs (`twinfra-console`). The console reads its environment badge
   and region from configuration.
5. **Initial component set** (sized for 24 GB): Cilium (default deny), Argo CD, CloudNativePG + PostgreSQL 18 with pgvector,
   Keycloak, OpenBao (sealed until WO-08), APISIX, the console and MiniStack.
   - **Do not install:** LocalStack (WO-06), Grafana (WO-07), Knative (until needed), or any GPU/HPC module.
   - **Admission policies:** WO-05 policies in audit mode from day one, if WO-05 has merged.
6. **Access.** Windows reaches the dev environment through the VM's IP or the documented port mapping, never through WSL mirrored networking.
   Cloudflare Tunnel stays out of scope (a later work order under ADR-0037).
7. **WSL lab.** Document how to stop it or shrink it to a dev profile, and how to retire it after `cairo-1` passes acceptance.
   Codex never deletes WSL data; the owner decides.

8. **Ready for more PCs (owner, 2026-10-09: more hosts are coming soon).** These settings are cheap now and expensive to change later:
   - **Stable control-plane endpoint.** Set kubeadm's `controlPlaneEndpoint` at init to a stable name or a virtual IP
     (for example `api.cairo-1.<domain>`), never a node IP, so control-plane nodes can be added later.
   - **Address plan (corrected 2026-10-09).** The first plan put `cairo-2` on 10.20.0.0/16, which overlaps the existing pCloud
     Hyper-V lab network `iotee-nat` (10.20.0.0/24). Never reuse 10.20.0.0/24, the home LAN (192.168.1.0/24), or WSL's
     10.255.255.254. Use the environment-and-region ranges in the table of Amendment 3 (pods and services per environment and region),
     recorded in the SSoT. The older single-column list is superseded.
     The Hyper-V switch for the Twinfra dev environment is a new internal NAT switch named `twinfra-nat` on 10.50.0.0/24
     (gateway 10.50.0.1, VM 10.50.0.10). The provisioning script reads the existing switches, NAT networks, host routes and
     IP addresses first, and **refuses to run if any planned range overlaps one that exists**.
     The pCloud lab, its `iotee-nat` switch and the WSL controller distro are not touched.
   - **Zone labels.** Every node carries `topology.kubernetes.io/zone` (for example `cairo-1a`). CloudNativePG and stateful
     sets use zone-spread rules from day one.
   - **Node-join runbook.** A tested way to add a worker on another PC: Cilium native routing with direct node routes on the same LAN.

## Out of scope

KubeVirt and real EC2 (WO-22), OpenBao activation (WO-08), backups (WO-09), observability (WO-10), and a second region.

## Acceptance criteria

- **Static:** the provisioning script tests pass, including plan mode, resource checks and idempotence. The dev environment overlay renders, and
  a CI search finds no `wsl` or `vcloud` in names under the `dev` environment.
- **Live, after the owner runs the script:**
  - the node is Ready;
  - Cilium default deny is proven with a deny test;
  - Argo CD apps are Synced and Healthy from `main`;
  - PostgreSQL survives a restart with TLS;
  - console login with PKCE and MFA works on the `twinfra` realm, and the console shows "Dev · cairo-1" with no host names.
- Receipt: `docs/acceptance/dev-environment-<date>.md`, with the tester sign-off left Pending.

## Owner actions

Turn on the Hyper-V feature if it isn't already, run the script as administrator after reviewing its `-Plan` output,
stop the WSL lab while `cairo-1` runs, and sign off the receipt.

## Report back

The script plan output, VM sizing used, the component list with RAM use, any production-profile deviations, and the receipt.

## Amendment: WSL lab retirement (owner, 2026-10-09)

The Twinfra dev environment replaces the WSL lab. WO-21 therefore also:

1. **Ports what is reusable before anything is deleted.** Move environment-neutral pieces from `lab/wsl/**`, `tools/wsl_*.py` and
   `deploy/console/deploy-wsl.py` to neutral locations (for example `deploy/common/` and `tools/platform_*.py`) under the ADR-0038 names,
   so WO-28 can delete the rest without breaking the dev environment.
2. **Does not delete WSL material.** Deletion is WO-28, and starts only after the tester signs the dev-environment receipt as Accepted.
3. **Leaves the WSL controller alone.** The same Ubuntu WSL distro (mirrored networking) is the controller for the pCloud and
   IOT-EE Hyper-V lab. Nothing in this work order may unregister it or change its network mode.

## Amendment 2 (2026-10-09, owner confirmation): one VM now, two regions later

- **Now: one VM, one single-node cluster.** `twinfra-dev-cairo-1` (region `cairo-1`). KubeVirt guests launched later (WO-22) run **inside** it as nested VMs,
  not as extra Hyper-V machines.
- **Later: one VM per region.** When the multi-region work arrives (`cairo-1` with its DR partner `cairo-2`, ADR-0040), each region is its own VM and its
  **own independent cluster**. Never one cluster stretched over two VMs.
- **The provisioning script is parameterised**, so a second region is the same script with other values:
  `-Region`, `-Cpu`, `-MemoryGB`, `-DiskGB`, `-IpAddress`, `-PodCidr`, `-ServiceCidr`. Defaults for `cairo-1`: 8 vCPU, 24 GB, 100 GB, 10.50.0.10,
  10.110.0.0/16, 10.111.0.0/16. The VM name is always `twinfra-<env>-<region>` (ADR-0046), for example `twinfra-dev-cairo-1`. A second VM on the same switch uses the next address (10.50.0.11) and its own CIDRs from the plan.
- **Two regions on this one PC** are a rehearsal only. Suggested split: 12 GB and 4 vCPU each. It proves the procedure but not a site failure, because both
  share one host. A real DR region needs a second PC (WO-24).
- **Ubuntu image.** Use Canonical's official Ubuntu 24.04 cloud image. The script downloads it from the official Canonical cloud-images site, verifies it
  against the published SHA256SUMS (and the signed checksum file if practical), and refuses to continue on a mismatch. State the exact URL, file name and size in
  the `-Plan` output so the owner approves the download before it happens. The Module -1 Cloud-Init is supplied through a NoCloud seed.
- **Hyper-V.** The script checks that Hyper-V is enabled and the user is an administrator, and says exactly what is missing instead of failing halfway.

## Amendment 3 (2026-10-10, architect): resolves Codex's stop on the overlap rule, idempotence and the CIDR table

**1. What counts as an overlap.** The script compares every planned range (the switch or NAT subnet, each pod CIDR, each service CIDR and each VM IP)
against the host's existing IPv4 address prefixes, its specific routes, existing NAT networks, other Hyper-V switch subnets, and **against the other planned ranges**.
These are **never** counted, because they overlap everything or nothing useful: the default route `0.0.0.0/0` (and `::/0`), loopback `127.0.0.0/8`,
link-local `169.254.0.0/16`, multicast `224.0.0.0/4`, and the limited broadcast `255.255.255.255/32`. No other exclusion is allowed.

**2. Script-owned objects are exempt, so reruns and a second region work.** An object is script-owned only if **all** of these hold:
- an Internal switch named `twinfra-nat`;
- the host adapter `vEthernet (twinfra-nat)` carrying exactly `10.50.0.1/24`;
- a NAT network named `twinfra-nat` with prefix exactly `10.50.0.0/24`;
- on a rerun, the VM `twinfra-<env>-<region>` and its own VHDX and seed files.

Owned objects and the routes they create (the on-link route for 10.50.0.0/24 and the host route for 10.50.0.1/32) are excluded from the overlap check.
If an object with an owned name exists with **any different configuration** (another prefix, extra addresses, another type), refuse, report it, and change
nothing. Never modify or delete a foreign object. A second region's VM joins the same switch with the next free address in 10.50.0.0/24: not `.0`, `.1` or `.255`,
and not already used by another VM or host address.

**3. Ranges per environment and region** (one row per cluster; no value appears twice, and none overlaps another row or the home LAN, `iotee-nat`, WSL or the switch):

| Environment | Region | Pod CIDR | Service CIDR | VM address on `twinfra-nat` |
| --- | --- | --- | --- | --- |
| dev | cairo-1 | 10.110.0.0/16 | 10.111.0.0/16 | 10.50.0.10 |
| dev | cairo-2 | 10.120.0.0/16 | 10.121.0.0/16 | 10.50.0.11 |
| production | cairo-1 | 10.130.0.0/16 | 10.131.0.0/16 | on the production network, not `twinfra-nat` |
| production | cairo-2 | 10.140.0.0/16 | 10.141.0.0/16 | on the production network, not `twinfra-nat` |
| staging | (reserved) | 10.150.0.0/16 | 10.151.0.0/16 | (reserved) |

Only the two `dev` rows are used in this work order. The other rows are recorded in the SSoT so that no later environment reuses a range.

**4. Tests to add:** a default route present (no overlap reported); the owned switch, NAT and gateway present from a previous run (rerun passes, nothing changes);
an owned name with a different prefix (refused); a second `dev` region on the same switch with the next address (passes); a planned range that overlaps `iotee-nat`
10.20.0.0/24, 192.168.1.0/24 or another planned range (refused); and two planned entries with the same range (refused).

## Amendment 4 (2026-10-10, architect): upstream-owned names (ADR-0047)

Codex stopped because Argo CD 3.5.3 looks up `argocd-cm`, `argocd-secret` and similar names directly. ADR-0047 resolves it:

1. **Approved.** Upstream-owned resources keep their upstream names exactly as shipped in the pinned manifest or chart. Twinfra-owned resources follow ADR-0038 and ADR-0046.
   Do not patch vendored files to rename upstream objects.
2. **Register.** Add `deploy/upstream-names.json` (project, pinned version, source, and the upstream-owned names) and a CI check that renders the dev environment and fails when:
   a resource whose name does not start with `twinfra-` is not listed there; or a listed name is absent from its pinned source.
   Start with Argo CD 3.5.3, Cilium, CloudNativePG, Knative, Keycloak, APISIX and the other pinned upstream projects that the dev environment installs.
3. **Labels.** Upstream-owned objects get the `twinfra.io/environment`, `twinfra.io/region` and `twinfra.io/component` labels through kustomize or Helm label transformers, with selectors unchanged.
4. **Names Twinfra chooses stay Twinfra-owned:** Argo CD Applications and AppProject, the Keycloak realm and client IDs, Secrets and ConfigMaps Twinfra creates, and Namespaces from the SSoT. The ban on `lab`, `wsl` and `vcloud` applies to all of them.
5. **Add ADR-0047** (from `E:/vcloud-handoff/adr/ADR-0047-upstream-owned-resource-names.md`, fixing relative links) to `docs/adr/` and the ADR index, with an "Amended by ADR-0047" line at the top of ADR-0038.
6. **Tests:** an upstream name listed and present (pass); a non-`twinfra-` name not listed (fail); a listed name missing from the pinned source (fail); a Twinfra-owned name containing `lab`, `wsl` or `vcloud` (fail).
