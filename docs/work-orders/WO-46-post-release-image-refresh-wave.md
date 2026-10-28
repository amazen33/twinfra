# WO-46: Post-v0.1.0 image refresh wave

**Status:** Proposed (architect, 2026-10-28). It is named as the remediation work order for the High exceptions R12 groups (WO-40 Amendment 10). The owner approves it with the R12 exception batch.
**Author:** Claude. **Implementer:** Codex. **Live steps:** the owner.
**Due:** before the earliest R12 High entry expires (60 days after R12 merges, about 2026-12-28). Each promotion is also due within 14 days of its fixed release becoming eligible (ADR-0049 Amendment 1, item 4).

## Goal

Close the High and Critical exceptions that R12 carries past v0.1.0 by promoting eligible upstream releases, never by extending the exceptions.

## Scope

Each item is one PR. Each PR passes the net-improvement rule (WO-34 Amendment 3a) and closes its exceptions with evidence.

1. **Kubernetes control plane:** 1.36.6, eligible from 2026-11-11.
   - kube-apiserver, controller-manager and scheduler;
   - the etcd and CoreDNS versions that kubeadm 1.36.6 pins.

   It is a live maintenance, done the same way as WO-40c: backup, preview, phased apply and verification.
2. **Cilium:** 1.20.4, eligible from 2026-11-06. This covers the agent, the operator and Envoy, and is a rolling upgrade with an acceptance pass.
3. **Platform images:** OpenBao, the CNPG operator, APISIX and Valkey, each at its newest eligible fixed release.
4. **Argo CD:** the next eligible patch, if R12 carries any Argo CD entry.
   - **KEV duty (WO-40 Amendment 10a):** promote the first Argo CD release whose image carries `libbrotli1` ≥ 1.2.0-3ubuntu0.1 (CVE-2026-111497).
   - Promote it **at once, under the KEV expedite rule**, without waiting 14 days, and close the KEV exception. Its term is the R12 merge date plus 25 days (WO-40 Amendment 10b); there is a checkpoint on 2026-11-13.
5. **Keycloak:** the first eligible image with the fixed `ca-certificates` (the eMudhra CA bundle), if R12 renewed that Critical.
6. **After each step:** the owner runs `run-acceptance.ps1 -WithRestart`, and the nightly gate passes with the closed entries removed.

## Out of scope

Minor-version upgrades: Kubernetes 1.37, and any new Cilium or Argo CD minor line. Those need their own decision.

## Acceptance

- Every exception that R12 created or renewed with reason "fixed by WO-46" is closed, or replaced by an individually justified entry within ADR-0049's limits.
- The nightly gate passes.
- Each live step has an acceptance pass recorded.

## R12 authority: WO-40 Amendments 10a–10c

Item 4 includes the first upstream Argo CD image fixing libbrotli1 CVE-2026-111497. Promote that fix immediately under ADR-0049’s KEV expedite rule; do not wait 14 days. The architect reports weekly-watch evidence at the 2026-11-13 checkpoint. The R12 exception expires on the merge date plus 25 days (2026-11-24 for a 2026-10-30 merge), subject to owner O-2/O-4b approval. See [WO-40](WO-40-twinfra-v0-1-0-release.md#amendment-10b-2026-10-28-architect-the-kev-exceptions-expiry-versus-the-release-calendar). No live maintenance is authorised by this record.
