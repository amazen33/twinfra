# Intel AMT recovery access — owner procedure

Scope: [WO-36 Amendment 1](../work-orders/WO-36-host-network-and-staging-safety.md#amendment-1-2026-10-15-architect-owner-ok-fix-the-failed-live-apply-adopt-the-hand-applied-static-file-add-an-amt-owner-procedure).
Documentation only. Codex has not connected to or configured AMT. The owner
executes this procedure and records a receipt; tester sign-off remains Pending.

## Inventory and boundary

Owner-reported Dell: i7-4790 with vPro, BIOS A25 dated 2019-05-30, Intel ME
9.1.45.3000. This includes the INTEL-SA-00075 fix according to the owner;
[Intel's advisory](https://www.intel.com/content/www/us/en/security-center/advisory/intel-sa-00075.html)
lists 9.1.41.3024 as the fixed 9.1 release. This does not establish that every
later vulnerability is fixed. ME 9.x is no longer serviced under the approved
work order; treat it as legacy management firmware.

SSoT `siteNetwork.management.address` reserves **192.168.1.4** for AMT. It is
independent of Ubuntu's **192.168.1.3**; gateway/DNS is **192.168.1.1** and the
subnet is `/24`. Neither is in the router DHCP pool `.100–.254`.

AMT operates below the host OS: **the Ubuntu host firewall cannot protect it**.
Keep access LAN-only, from the owner's laptop. Never port-forward TCP/UDP
**16992–16995, 623, 664 or 5900**. No WAN publishing, cloud relay or remote
provisioning. If the network becomes exposed, disable AMT network access at MEBx.
CGNAT alone is not an access-control boundary.

## Owner setup at the physical console

1. Enter MEBx with **Ctrl+P**. Set a strong unique management password in the
   owner's password manager. Never put it in Git, environment variables, shell
   history, screenshots or acceptance output.
2. Activate network access. Configure static `192.168.1.4/24`, gateway/DNS `.1`.
   Keep Ubuntu/netplan at `.3`; do not reuse the OS address for AMT.
3. Enable KVM with user consent disabled, as explicitly approved in the work
   order for unattended recovery. This grants BIOS/power control: limit laptop
   and LAN access accordingly. Disable remote provisioning.
4. From the laptop on the trusted LAN, use MeshCommander or MeshCentral. Both
   upstream projects declare Apache-2.0:
   [MeshCommander licence](https://github.com/Ylianst/MeshCommander/blob/master/LICENSE),
   [MeshCentral licence](https://github.com/Ylianst/MeshCentral/blob/master/LICENSE).
   This runbook installs neither tool or a platform component. Version selection
   and any managed deployment need their own licence/security review and pins.
5. Establish first contact locally, then provision TLS for management/KVM on
   **16993/16995**, verify the intended certificate and retire plaintext access
   where firmware supports it. Keep certificate private keys in the owner's
   approved custody. Do not disable TLS verification globally or weaken browser
   TLS settings to accommodate legacy firmware. If a trusted TLS session cannot
   be established, stop and review the legacy compatibility risk with the owner.
   See [MeshCentral security guidance](https://docs.meshcentral.com/meshcentral/security/).

## Owner acceptance and recovery

Schedule a dev maintenance window: a power cycle interrupts the control plane
and database. First verify console access, backups and a local recovery path.
From the laptop, remotely power-cycle the Dell and use KVM to enter BIOS. Confirm
that recovery works independently of Ubuntu SSH/API reachability, then leave BIOS
without changing settings and allow normal boot. Verify static `.3`, node Ready
and Argo CD health using the existing dev runbook. Do not disconnect the router
or introduce another outage during this test.

Record a short dated receipt under `docs/acceptance/`: tester, firmware inventory,
LAN-only/TLS configuration, power and BIOS KVM result, dev recovery status and
outage duration. Include no credentials, private keys or sensitive screenshots.
Set `Result: Pending` for the designated tester. No AMT test has been performed
by this work order's static implementation.
