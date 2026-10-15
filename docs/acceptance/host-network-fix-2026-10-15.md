# WO-36a host-network fix acceptance — 2026-10-15

## Scope and authorization

- [WO-36 Amendment 1 and owner legacy clarification](../work-orders/WO-36-host-network-and-staging-safety.md).
- Static repository changes; disposable Ubuntu 24.04 CI VM network proof only.
- No Dell SSH, router, AMT, production or GitHub settings changes by Codex.
- Exact implementation commit and CI/artifact links are recorded in the PR.

## Owner-reported incident and recovery

At main `af954d7`, the 2026-10-15 16:42Z apply installed `.3`, gateway `.1`,
and the intended IPv4 DNS. Fresh SSH worked, but confirmation refused. The
additional `fe80::1` resolver is the likely mismatch; this is not independently
proven from packet capture. Timeout restored DHCP and the router assigned `.102`,
making the API bound to `.3` unreachable. The owner recovered at the console
around 19:25Z with the legacy static profile. Owner reports 20/20 pods Running,
three Argo CD Applications Synced/Healthy, and backup at
`/var/lib/twinfra/host-network/recover-2026-10-15/`.

Owner subsequently supplied root:root, mode 0600, 308 bytes and SHA-256
`1739e68f586cda48fadfc3a38905bd62f22167cb3842415623cce43b5ce89ad7` for
`/etc/netplan/60-twinfra-static.yaml`. The prior generator reproduces those exact
bytes offline. These are owner-reported live facts, not a new Codex inspection.

## Executable evidence

- Unit fixtures: ordered IPv4 DNS with the live IPv6 extra, exact legacy adoption,
  altered byte/mode/effective-state refusal, no-write unsafe fallback refusal,
  successful upgrade/rollback to the legacy static file, failed confirmation,
  concurrent/refused/replayed workers and the existing cluster identity guards.
- Real VM proof: `.github/workflows/host-network-vm.yaml`, job `netplan-vm`.
  Runs `tools/ci/host_network_vm.py` on a disposable Ubuntu 24.04 hosted VM.
  Artifact `host-network-ubuntu-24-proof/result.json` contains versions, commit,
  apply/refused-confirmation/rollback outcomes and sampled address/route checks;
  public per-unit journals accompany it. Exact run link/result: Pending CI.
- Real production worker, netplan/networkd, detached systemd unit, key-only SSH
  and TLS-verified kubectl; dummy `eno1` and synthetic Node/readyz API. This proves
  transaction behavior, not Dell hardware, DHCP server or Kubernetes acceptance.
  Primary runner routing is protected; private test keys remain in tmpfs and
  are never uploaded. The fixture refuses non-hosted or pre-existing host state.
- Production/WSL renders, image locks and historical baseline inventory remain
  byte-identical. Gate counts/results and all six historical revisions are in PR CI.

## Remaining owner acceptance

After review/merge, use the [dev runbook](../dev-environment.md#wo-36-dell-address-plan-and-safe-network-changes):
check/adopt (WARN for legacy), apply upgrade, check again; optionally rollback
to the saved legacy static file and check `.3`. Do not assert a DHCP reservation
unless it exists. Controlled router outage and no control-plane restarts remain
Pending. AMT power/KVM acceptance is separately Pending under its
[owner runbook](../runbooks/intel-amt.md). No tool touches AMT.

## Tester sign-off

Tester: Ahmed Mazen (@amazen33), enterprise and cloud tester; QoS tester
Result: Pending
Date (UTC):
QoS targets checked:
Notes:
