# ADR-0050: Make `cairo-1` multi-node ready before EdgePulse (HA when nodes arrive)

**Status:** Accepted (owner, 2026-10-14). Proposed by the architect the same day.
- **Owner's intent (2026-10-14):** prepare Twinfra to grow beyond one node **before EdgePulse is deployed**. No additional PCs exist yet.
- **Revised the same day:** an earlier draft of this ADR assumed two PCs were available. That draft is replaced.

**Author:** Claude. **Implementer:** WO-33 (readiness now) and WO-33b (joining, once PCs exist).
**Builds on:** the 2026-10-12 multi-node direction:
- **D1:** discover the node, propose it, the owner approves it, then it joins;
- **D2:** TopoLVM first;
- **D3:** a single control plane for now; HA with three control planes later.

## Facts read from the live cluster (2026-10-14, read-only)

- **API endpoint:** `controlPlaneEndpoint: api.dev.cairo-1.twinfra.example.com:6443`. It is in the certificate SANs and in the admin kubeconfig, so **no rebuild** is needed to grow.
- **etcd:** a single member, `https://192.168.1.3:2380`.
- **Cilium:** native routing over `10.110.0.0/16`, with kube-proxy replacement and `auto-direct-node-routes=false`.
- **Node labels:** `topology.kubernetes.io/zone=cairo-1a` and `twinfra.io/region=cairo-1`. The standard region label is missing.
- **Storage:**
  - one static StorageClass, `twinfra-local` (no provisioner), and one PV, `twinfra-postgres-1`;
  - LVM `ubuntu-vg`: 220.5 GiB, with **100.5 GiB free**;
  - WO-22 reserves 30 GiB for SeaweedFS, and 20 GiB must stay free.
- **Replicas:** every platform Deployment runs 1 replica, and CNPG runs `instances=1`.

## Decision: what is done now, on one node

1. **API endpoint on a virtual IP (kube-vip, Apache-2.0, ARP mode, a static pod).**
   - The Dell holds one VIP (a free LAN address outside the DHCP range), and `api.dev.cairo-1.twinfra.example.com` resolves to it.
   - Joining control planes later changes nothing for clients.
   - kube-vip is a new **named exception** to the host-network rule, approved by the owner.
2. **Cilium:** set `autoDirectNodeRoutes=true` now (no effect on one node, required for more).
3. **Firewall from the single source of truth (SSoT).** The host firewall's peer rules are generated from the list of nodes in the SSoT:
   - etcd 2379–2380, kubelet 10250 and Cilium health 4240 are open to listed peers only;
   - today the list holds only the Dell, so nothing new opens;
   - CI renders and tests the rules for a fake three-node SSoT.
4. **Module -1 gets a join flow (D1):**
   - `node-discover` proposes a node entry to the SSoT as a PR;
   - `node-join` supports **worker** and **control-plane** modes;
   - join tokens and certificate keys come from the owner's session and are never stored;
   - images are staged on every listed node.

   Tested with fake-root tests and CI rendering.
5. **Standard topology labels:** add `topology.kubernetes.io/region=cairo-1` and keep `twinfra.io/region`. Scheduling rules use the standard labels.
6. **Dynamic local storage: TopoLVM** (Apache-2.0) on `ubuntu-vg`.
   - Its capacity guard keeps at least 20 GiB free, plus WO-22's 30 GiB reserve.
   - New StorageClass `twinfra-topolvm` (`WaitForFirstConsumer`).
   - **New** stateful services use it: OpenBao Raft, SeaweedFS, and future CNPG replicas.
   - The existing static PostgreSQL volume stays until CNPG grows.
7. **Stateful services are HA-capable at size 1:**
   - **OpenBao:** WO-08 initialises it with **integrated Raft storage** (one voter) and `retry_join` through a headless Service. More voters join later, with no migration. Using file storage now would force a migration later, so it is **not** used.
   - **CNPG:** required pod anti-affinity per host, still at `instances=1`. Growing means `instances=3` with synchronous quorum replication.
   - **Keycloak:** clustered cache with Kubernetes discovery (headless Service), still at 1 replica.
   - **Gateway, console and MiniStack:** topology spread (`ScheduleAnyway`).
   - **PodDisruptionBudgets** are added only once a service has 2 or more replicas. A PDB on a single replica would block node drains.
   - **Argo CD:** stays non-HA until there are three nodes.
8. **Backups first.** WO-09 runs before any of the above touches the API endpoint.

## Validation without new PCs

- **CI:** render tests for a fake three-node SSoT, covering firewall peers, kube-vip, join commands and image staging.
- **On the Dell:**
  - the API through the VIP (laptop, Argo CD, console);
  - TopoLVM provisioning and deletion of a test PVC;
  - OpenBao Raft with one voter;
  - CNPG and Keycloak unchanged;
  - a fresh 24-hour soak.
- **Optional, owner's choice: a temporary test worker.**
  - A Hyper-V VM on the laptop, bridged to the LAN, joins as a **worker only** (never a control plane), to prove the join flow, cross-node pod routing, TopoLVM on a second node and the firewall peer rules.
  - Afterwards: drain it, `kubectl delete node`, `kubeadm reset` on the VM, and remove its SSoT entry through a PR.

## Later: WO-33b, when two PCs exist

- Join them as control planes, so etcd has 3 members, and the VIP follows the leader.
- CNPG grows to 3 instances with synchronous replication; OpenBao to 3 voters; Argo CD becomes HA; Keycloak, gateway and console get 2 replicas each, with PDBs.
- **Acceptance:**
  - power off any one node: the API survives within 30 s or less, and CNPG fails over within 60 s or less with no lost commit;
  - rolling reboot of all nodes;
  - `kubeadm upgrade` rehearsal;
  - a 24-hour soak.

**Hardware per new PC:**
- at least 4 cores and 16 GiB RAM (32 GiB recommended);
- an SSD of at least 240 GB, with at least 120 GB unallocated;
- wired Ethernet on the same subnet, with a DHCP reservation;
- VT-x enabled.

## Alternatives rejected

- **Waiting for hardware before preparing.** Every item above would land at once, on the critical path, after EdgePulse already holds state.
- **keepalived or HAProxy for the VIP.** keepalived is GPL, which the licence gate rejects.
- **OpenBao on file storage now.** It would force a storage migration later.
- **Joining a laptop VM as a control plane.** Removing an etcd member later is risky; test workers only.
