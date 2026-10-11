# ADR-0048: `cairo-1` runs on a dedicated bare-metal host; the laptop is the operator workstation (amends ADR-0032 and ADR-0046)

**Status:** Accepted (owner, 2026-10-11: "I choose Dell to hold Cairo-1 as main").
**Author:** Claude (platform architecture). **Decider:** Ahmed Mazen, Owner and Product Owner.

## Context

- **The laptop can't comfortably host the VM.** WO-21, WO-29 and WO-30 built `cairo-1` as a 20 GiB Hyper-V VM on the owner's laptop (ThinkPad P15 Gen 2, 32 GB). On 2026-10-10 the first real `-Plan` stopped: 20.9 GiB was free and 24 GiB was needed. Windows and the owner's desktop apps hold 8–14 GB, so the VM could run only with almost everything else closed.
- **A second PC is available on the same LAN.** It is a Dell OptiPlex 9020 (i7-4790, 4 cores / 8 threads, VT-x and VT-d). The owner upgraded it to 32 GB.
- **What was done on 2026-10-11/12:**
  - BIOS updated to **A25**, the final release, and switched to UEFI.
  - **Ubuntu Server 24.04.5 LTS** installed on it.

## Decision

1. **`cairo-1` (environment `dev`) runs on bare-metal Ubuntu 24.04 on the Dell.** There is no hypervisor: Module -1 (kubeadm) runs directly on the host.
   - Host name `twinfra-dev-cairo-1`.
   - Address `192.168.1.3/24` on `eno1`, reserved in the router.
   - Control-plane endpoint `api.dev.cairo-1.twinfra.example.com:6443`, resolving to `192.168.1.3`.
2. **The laptop is the operator workstation, not a node.** It runs kubectl, SSH, the browser, Claude and Codex. The laptop no longer has to free RAM for `cairo-1`.
3. **The Hyper-V path stays and is re-targeted to `cairo-2`.** `deploy/hyperv/` (WO-21, WO-29, WO-30) becomes the **cold-standby `cairo-2`** that WO-23 rebuilds on the laptop during DR drills. No merged code is reverted.
4. **Network exposure: LAN only, tunnel-only for UIs.**
   - SSH (22) and the Kubernetes API (6443) accept connections only from `192.168.1.0/24`. A host firewall (nftables, class `base-os` under ADR-0044) filters `eno1` only and never touches Cilium's interfaces.
   - No router port forwarding.
   - Console, Keycloak and Argo CD stay tunnel-only (WO-29 Amendment 1 C). The tunnel target changes from `10.50.0.10` to `192.168.1.3`.
5. **Address plan.** Unchanged.
   - Pods `10.110.0.0/16`, Services `10.111.0.0/16`.
   - They must not overlap `192.168.1.0/24` (the home LAN, now the node network), `10.20.0.0/24` (pCloud `iotee-nat`) or `10.50.0.0/24` (`twinfra-nat`).
6. **Storage.**
   - **Root.** The root logical volume is 100 GB, holding the OS, containerd, etcd and logs.
   - **Free space.** About 120 GB stays **unallocated** in `ubuntu-vg`.
   - **Stateful data gets dedicated, finite logical volumes,** never directories on `/`. The first is `twinfra-postgres-1`, 20 GiB, mounted at `/var/lib/twinfra/local-pv/postgres-1`. That matches the existing 20Gi PV, so the manifests don't change.
   - **Scope of the 20 GiB disk sizing.** The owner's "20 GiB per VM" decision applies to VMs, so to `cairo-2` on Hyper-V. It does not apply to this host.
7. **Identities.**
   - `twinfra` is the owner's console administrator.
   - Automation uses a separate account, `twinfra-operator`: SSH key only, passwordless sudo, matching the VM design.
   - SSH password login is turned off once the operator key works.
8. **Secure Boot stays on.** Ubuntu then runs the kernel in lockdown `integrity` mode. Cilium and KubeVirt must be verified under it.

## Consequences

- **The laptop's RAM problem disappears for `cairo-1`.** The Dell gives Kubernetes about 30 GiB, against the 20 GiB budget, with no nested virtualization. KubeVirt (WO-22) runs on real VT-x.
- **Weaker hardware.** It is a 2014 desktop with a budget SATA SSD (Crucial BX500, DRAM-less) and no UPS.
  - The BIOS has AC Recovery = Power On.
  - Acceptance measures etcd's fsync latency.
  - The installer froze several times right after the RAM upgrade, so a memory test and a 24-hour soak are acceptance gates (WO-31).
- **WO-24 changes.** WO-24's "PC 2" is now `cairo-1`. A warm `cairo-2` still needs another host. Until then, `cairo-2` is the cold standby on the laptop.
- **The node shares the home LAN.** The host firewall and LAN-only bindings are the boundary. Moving to a separate VLAN is a later improvement.

## Verified host facts (2026-10-12, read-only checks over SSH)

| | |
| --- | --- |
| OS | Ubuntu 24.04.5 LTS, kernel 7.0.0-38-generic |
| CPU | i7-4790, 8 threads, VT-x, `/dev/kvm` present, DMAR interrupt remapping present, microcode 0x28 (`intel-microcode` 3.20260210) |
| RAM | 31 GiB usable |
| Disk | Crucial CT240BX500SSD1, 223.6 GiB. GPT: ESP 1 GiB, `/boot` 2 GiB, LVM PV 220.5 GiB. Root LV 100 GiB; VG free 120.5 GiB |
| Boot | UEFI, Secure Boot enabled, BIOS A25 |
| Network | `eno1` 192.168.1.3/24 by DHCP, gateway 192.168.1.1 |
| Access | SSH key login for `twinfra` works. Password login is still enabled; WO-31 turns it off |
