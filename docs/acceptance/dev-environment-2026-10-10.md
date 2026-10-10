# Dev environment acceptance receipt — 2026-10-10

## Scope and authorization

- Work order: [WO-21](../work-orders/WO-21-twinfra-dev-environment.md), Amendments 1–4.
- Follow-up: [WO-29](../work-orders/WO-29-make-dev-environment-runnable.md), including Amendment 1.
- Environment: dev · cairo-1; proposed VM/context `twinfra-dev-cairo-1`.
- Authorization: static implementation and offline tests only. Owner runs provisioning.
- Tested revision / PR / GitHub run: recorded in the PR after checks complete.
- QoS targets: Ready node, deny-all conformance, Synced/Healthy GitOps, TLS/persistent
  PostgreSQL with pgvector, PKCE/MFA portal login and correct environment badge.

## Static evidence

PowerShell fixture tests import only the pure planner. Provisioning entry point
was not run, including against real host inventory. Fixture `-Plan` output is in
[the Hyper-V runbook](../../deploy/hyperv/README.md). Candidate and historical gate
results are reported in the PR; static tests do not establish live readiness.

WO-29 fixture: 113 GiB free disk and 24 GiB free RAM pass with a 20 GiB VM
default; 109 GiB disk and 23 GiB RAM fail. Offline staging tests use fake SSH/ctr;
CA tests generate keys only in memory, checking SANs/serverAuth/key usage and
Git-boundary refusal without writing private files. Bootstrap inventory equality
is tested for cairo-1/cairo-2 against rendered kubeadm/Cilium/containerd settings.
Nine saved production render hashes preserve the pre-change bytes. The
provisioning entry point, staging against a VM, CA output/ACL writes and trust-store
commands have not been executed. GitHub candidate/historical results are linked
in the PR; Windows cannot run the complete Linux dependency/alert matrix locally.

## Live evidence

| Check | Expected | Observed |
| --- | --- | --- |
| Hyper-V/Ubuntu/NoCloud/shared kubeadm bootstrap | Ready node, zone cairo-1a | Pending |
| Bootstrap staging | Eleven canonical digest/CRI entries; mirror_status staged-verified | Pending |
| Application staging | Ten locked images; --check has no missing/mismatched entries | Pending |
| Dev CA / gateway HTTPS | Owner-only key ACLs, trusted SANs, loopback TLS 18444→9443, Secure cookies | Pending |
| Cilium default deny | Cross-namespace denied traffic fails; authorized succeeds | Pending |
| Argo protected-main reconciliation | All dev Applications Synced/Healthy | Pending |
| Valkey authentication/reconnect | Authenticated ping succeeds; unauthenticated fails; Argo reconnects after restart | Pending |
| PostgreSQL 18/pgvector | TLS, vector extension and data survive Pod restart | Pending |
| Console identity | PKCE/MFA, roleless 403, Dev · cairo-1 badge | Pending |
| Worker join/native routes | Verified common L2, second node Ready, deny test retained | Pending; additional PC required |

## Pending gates, deviations and owner actions

No live changes, VM creation, lab retirement, key ceremony or GitHub settings
changes were performed. Owner frees RAM/disk, supplies SSH public key, prepares
locked OCI artifacts and dev CA outside Git, reviews real `-Plan`, provisions/starts the VM, merges
the PR before protected-main reconciliation, executes live acceptance and signs
this receipt. WO-28 deletion remains gated. Ubuntu distribution licence summary
and SBOM evidence is a dated ADR-0044 baseline, expiring 2027-01-08.
Production profile deviations are documented in [the runbook](../dev-environment.md).

## Tester sign-off
Tester: Ahmed Mazen (@amazen33), enterprise and cloud tester; QoS tester
Result: Pending
Date (UTC):
QoS targets checked:
Notes:
