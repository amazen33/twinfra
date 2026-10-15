# WO-36: cairo-1 host network resilience and image-staging safety

**Status:** Approved for implementation (owner, 2026-10-15: "WO-36 approved"). · **Author:** Claude · **Implementer:** Codex
**Branch:** `codex/wo-36-host-network-staging` · **Decisions:** ADR-0048 (bare-metal cairo-1), ADR-0050 (multi-node readiness), ADR-0049 · **Depends on:** WO-31

## Why (two incidents on 2026-10-14/15)

1. **Unstaged images took four services down for about 15 hours.**
   - PR #55 changed the console and Python image digests. Argo CD synced `main` at once, but the images were not staged on the Dell, and the CRI is mirror-only.
   - Every dev Deployment uses `strategy: Recreate`, so the old pods stopped before the new ones could start. The console, gateway, Keycloak and OpenBao sat in `ImagePullBackOff`
     from 2026-10-14 21:40Z until the owner staged the images (runbook step 8).
   - The runbook still names the old console digest `3859…`.
2. **Power cuts removed the node's IP address.**
   - The router lost power at 02:44Z and 10:33–10:35Z. `eno1` lost carrier, and systemd-networkd dropped the DHCP lease, so `192.168.1.3` disappeared.
   - The API server, controller manager, scheduler, Cilium operator and CNPG operator restarted (CNPG 13 times).
   - The Dell itself stayed up. Netplan is `dhcp4: true` only. The router's DHCP pool is 192.168.1.2–.254 (the whole subnet). The WAN uses carrier-grade NAT (10.45.10.220), so there is no inbound internet path, which matches the tunnel-only design.

## Address plan (owner, 2026-10-15)

| Address | Use |
| --- | --- |
| 192.168.1.1 | Router (gateway, DNS) |
| 192.168.1.2 – .99 | Fixed addresses, removed from DHCP |
| 192.168.1.3 | `twinfra-dev-cairo-1` (MAC `64:00:6a:86:5c:4f`), static |
| 192.168.1.10 | WO-33 control-plane VIP |
| 192.168.1.11 – .13 | Future cluster nodes |
| 192.168.1.100 – .254 | Router DHCP pool |

Record it in the SSoT (site network section) and in `docs/dev-environment.md`.

## Scope

**Part A: a static node address with safe apply and rollback.**
1. Add `platform_dev.py host-network --context twinfra-dev-cairo-1 [--check | --apply | --rollback]`, using the same identity checks and systemd-run plus polling pattern as host-bootstrap.
2. `--apply` does the following:
   - writes an owned `/etc/netplan/60-twinfra-static.yaml`: `eno1` static `192.168.1.3/24`, default route via `192.168.1.1`, DNS `192.168.1.1` then `1.1.1.1`, `dhcp4: false`, `dhcp6: false`;
   - disables cloud-init network regeneration with `/etc/cloud/cloud.cfg.d/99-twinfra-disable-network-config.cfg`;
   - moves the old `50-cloud-init.yaml` aside, keeping a copy;
   - applies with `netplan try --timeout 120`, then confirms only after a fresh SSH login and the API server at `https://192.168.1.3:6443/readyz` both succeed. Otherwise netplan rolls back by itself.
3. The address does not change, so the node InternalIP, the certificates and kubeadm stay valid. Never re-init, reset or rotate certificates.
4. `--check` passes when the address shows no `dynamic` flag, the route and DNS match, and the node InternalIP is still 192.168.1.3.
5. `--rollback` restores the saved DHCP configuration with the same `netplan try` safety.
6. Update host-check's lockdown integrity to expect the new owned files.

**Part B: see network loss without reading logs.**
1. Since boot, `host-check` reports these as warnings (not failures): `eno1` carrier losses, DHCP lease losses, and restarts of the control-plane static pods.
2. A WO-10 follow-up adds the Prometheus alert. Note it in WO-10.

**Part C: one unstaged image must never take a service down.**
1. **Rolling updates where safe.**
   - Switch stateless dev workloads (console, gateway, MiniStack and, if safe, Keycloak) to `RollingUpdate` with `maxUnavailable: 0`, `maxSurge: 1`, so a stuck new pod leaves the old one serving.
   - Keep `Recreate` only where two instances must not run together (for example OpenBao on its storage), and document the reason for each workload.
   - Add a test that every `Recreate` has a documented reason.
2. **Staging gate for image changes.**
   - Add a lightweight workflow `staging-check` (on `pull_request` types opened, synchronize, reopened and edited; permissions `contents: read`; no secrets).
   - When a PR changes `deploy/common/images.lock.json`, `deploy/common/bootstrap-images.lock.json` or any rendered dev image reference, it fails until the PR description contains the line
     `Staging: PASS (stage-images --check, <UTC date>)`.
   - The PR template gains that checklist line. The owner stages from the PR branch before merging; staging extra images is harmless.
   - The owner later adds `staging-check` to the required checks (an owner setting; this PR does not change rulesets).
3. **Runbook digests come from the lock.** Remove hard-coded digests from `docs/dev-environment.md` step 8, or add a docs check that fails if a digest in the runbook differs from
   `deploy/common/images.lock.json`. Fix the stale `3859…` now.

## Owner actions, in this order

1. Approve this work order. After merge, run `host-network --check`, then `--apply`, then `--check`.
2. **Only after the Dell is static:** on the router, set the DHCP start to **192.168.1.100** (end stays .254).
   - Optionally, add a reservation for `64:00:6a:86:5c:4f` → .3 as a safety net.
   - The laptop (now .9) moves into the pool automatically on renewal; nothing depends on its address.
3. Consider a small UPS for the router (and the Dell). Optional test, after the change: unplug the router for 60 s; the node keeps 192.168.1.3 and the control plane does not restart.

## Acceptance criteria

- The PR gate is green, including the historical baselines and the licence and supply-chain gates.
- Live:
  - `host-network --check` passes;
  - after a router power cycle, there are no control-plane restarts and the node InternalIP is unchanged;
  - an image-changing PR shows `staging-check` red until the staging line is added;
  - a deliberately unstaged image on a rolling workload leaves the old pod serving.
- Receipt `docs/acceptance/host-network-<date>.md`, with the tester sign-off Pending.

## Report back

The files changed, the `host-network --check` output format, the per-workload strategy table, and CI.

## Amendment 1 (2026-10-15, architect; owner "OK"): fix the failed live apply, adopt the hand-applied static file, add an AMT owner procedure

**What happened live (2026-10-15).**
1. `host-network --apply` (main af954d7) applied the static configuration at 16:42Z. The address, route and DNS (192.168.1.1, 1.1.1.1) were correct, and SSH to .3 worked during the try window.
2. Confirmation was refused ("Applied network verification failed"). The likely cause: the effective DNS list also contained the IPv6 router-advertised resolver `fe80::1`, which the strict comparison rejected.
3. At the 120-second timeout, netplan reverted. The worker restored `50-cloud-init.yaml` (DHCP), and the router (pool now .100–.254) leased **192.168.1.102**. The API server, bound to .3, became unreachable, and the Dell had to be found and recovered at the console.
4. The owner re-applied the same static file by hand at about 19:25Z. `/etc/netplan` now contains only `60-twinfra-static.yaml` (root, 0600), and cloud-init network config is disabled. The backup is in `/var/lib/twinfra/host-network/recover-2026-10-15/`.
   The cluster recovered fully: 20 of 20 pods Running, and all 3 Argo CD apps Synced and Healthy.

**Fixes (one PR, `codex/wo-36a-host-network-fix`):**
1. **DNS comparison.** Compare only the configured IPv4 resolvers, in order. Ignore IPv6 link-local and router-advertised entries.
   Also set `accept-ra: false` and `link-local: []` on `eno1` in the static file, since the node is IPv4-only. Add a test using exactly the live output `["192.168.1.1","1.1.1.1","fe80::1"]`.
2. **A rollback that cannot change the address.** A rollback must never leave the node on a different address.
   - Before writing anything, `--apply` and `--rollback` refuse to run unless a fallback keeps .3: either the DHCP reservation for MAC `64:00:6a:86:5c:4f` is confirmed by the owner (a flag the owner sets), or the rollback target is the previous *static* file.
   - Rework the transaction on netplan's real semantics (`netplan try` restores only the generated backend, not the YAML). Prefer writing the candidate only inside the try, through `netplan try --config-file`, or prove an equivalent with a real test.
3. **Adopt the existing hand-applied file.** If `60-twinfra-static.yaml` is already present, has exactly the expected content and permissions, and the effective state matches, `--check` passes and records ownership without applying anything. `--apply` becomes a no-op.
4. **Test on a real Ubuntu 24.04 VM before the Dell.** In CI, or as a documented local Hyper-V procedure, run apply, the refused-confirmation path and rollback against real netplan and systemd-networkd. Prove the address and route survive each path. The receipt records the VM run.
5. **Address plan:** add `192.168.1.4` = Intel AMT (out-of-band management) to `siteNetwork` in the SSoT and to the docs.

**Owner procedure (documentation only; Codex writes `docs/runbooks/intel-amt.md` and never touches AMT):**
- Hardware facts: i7-4790 (vPro), BIOS A25 (2019-05-30), ME firmware 9.1.45.3000. It includes the INTEL-SA-00075 fix, but ME 9.x is no longer serviced.
- Setup: MEBx (Ctrl+P) with a strong unique password kept in a password manager; network access activated; static 192.168.1.4, gateway .1; KVM on with no user consent; remote provisioning off; TLS after first contact (ports 16993/16995).
  Manage it with MeshCommander or MeshCentral (Apache-2.0) from the laptop only.
- Rules:
  - the host firewall cannot protect AMT;
  - never port-forward 16992–16995, 623, 664 or 5900;
  - AMT stays LAN-only;
  - disable it if the network is ever exposed.
- The test is a remote power cycle plus KVM into the BIOS, with a short receipt.


### Owner clarification: recognized legacy static profile (2026-10-15)

The owner's direct implementation instruction recognizes only the root:root,
0600, 308-byte static file with SHA-256
`1739e68f586cda48fadfc3a38905bd62f22167cb3842415623cce43b5ce89ad7`.
It has `ignore-carrier: true`, and lacks `accept-ra` and `link-local`.
`--check` may record ownership only if the effective address is static `.3`,
gateway `.1`, and IPv4 DNS is `.1` then `1.1.1.1`; report WARN
"adopted (legacy profile; upgrade pending)" while returning passed.
Unknown content or ownership/mode mismatch is refused without changes.
`--apply` upgrades this adopted profile through the fixed transaction; the
rollback target is the legacy static file, never the old DHCP recovery copy.
Tests cover exact-hash adoption, a one-byte difference, upgrade apply and
upgrade rollback retaining `.3`. This clarification qualifies Amendment 1 item 3:
only an already corrected static profile makes `--apply` a no-op.
