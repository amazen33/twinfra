# WO-24: Second host: warm DR region `cairo-2`, then more nodes

**Status:** Approved (owner, 2026-10-09). It starts **when the second PC is available**; the owner expects that soon.
**Phase:** 2-3 · **Author:** Claude · **Implementer:** Codex · **Decisions:** ADR-0032, ADR-0038, ADR-0040
**Depends on:** WO-21 (`cairo-1` built multi-node-ready), WO-08 (OpenBao), WO-09 (backups)

## Goal

Turn `cairo-2` from a cold standby into a **warm DR region** on its own physical PC, with continuous replication from
`cairo-1` and a measured failover. Then add further PCs as worker nodes or availability zones without redesign.

## Hardware guidance for each added PC

- **Minimum:** 32 GB RAM (64 GB recommended), 8 or more cores with VT-x/EPT enabled in the BIOS, a 512 GB or larger NVMe SSD.
- **Network:** wired Ethernet (1 Gb, or 2.5 Gb preferred) on the same switch, with a static IP or DHCP reservation.
- **Recommended:** a UPS.
- **Install bare-metal Ubuntu 24.04** with Twinfra's Module -1 (autoinstall or cloud-init USB). That is the real production
  profile, and it avoids Hyper-V overhead.

## Scope

1. **Region `cairo-2` on PC 2.**
   - A Module -1 kubeadm cluster with its own non-overlapping pod and service address ranges (from the WO-21 CIDR plan).
   - Its own Argo CD app-of-apps from `main`, and its own OpenBao with separately held unseal material.
2. **Replication `cairo-1` → `cairo-2`, asynchronous:**
   - **Databases:** a CloudNativePG replica cluster in `cairo-2` streams from `cairo-1` (application, IAM/Keycloak and OpenBao storage)
     over mutual TLS on the LAN, with the network policy limited to the peer.
   - **Objects:** SeaweedFS cross-cluster replication, once WO-22 has added SeaweedFS; confirm the open-source features in a spike.
   - **Backups:** both regions back up to the off-site target.
3. **Failover tooling.** Scripted promotion, OpenBao unseal (owner-held), scale-up, and a DNS or access switch, with
   per-step timing and data checks. This extends the WO-23 runbook from cold to warm.
4. **Warm drill.** Cut `cairo-1` off (pull its network), fail over to `cairo-2`, measure RPO and RTO against the tester's targets,
   then fail back.
5. **More nodes.** A runbook and tests for joining PC 3 and later PCs as workers with zone labels
   (for example `cairo-1b`), so CloudNativePG and stateful sets spread across zones.

## Out of scope

Stretched clusters across sites, automatic DNS failover (later, through a Twinfra health checker), and Cloudflare edge modes (ADR-0041).

## Acceptance criteria

- Replication lag is visible on a dashboard and stays within the RPO target during normal load.
- The warm drill meets the approved RPO and RTO, data checksums match, and failback succeeds.
- A third node joins `cairo-1` with no change to manifests other than its zone label.
- Receipt: `docs/acceptance/warm-dr-drill-<date>.md`, with the tester sign-off left Pending.

## Owner actions

Provide and install the PCs (the Ubuntu install can be done with Codex's autoinstall media), hold the unseal material
for each region, approve the RPO and RTO targets, witness the drill, and sign off.

## Amendment 1 (2026-10-12, ADR-0048)

1. **The first extra PC became `cairo-1`, not `cairo-2`.** It is the Dell OptiPlex 9020, 32 GB (WO-31). A warm `cairo-2` still needs **another** host that meets the hardware guidance above. This work order waits for it.
2. **Until then, `cairo-2` is the cold standby on the laptop's Hyper-V** (WO-23, WO-30).
3. **Lessons from the Dell:**
   - Use a plain FAT32 install stick; this firmware didn't recognise Ventoy's layout.
   - Update the BIOS before installing.
   - Run the vendor memory test right after any RAM change.
   - Keep free space in the LVM volume group for dedicated data volumes.
