# Host network and staging safety acceptance receipt — 2026-10-15

## Scope and authorization

- Work order: [WO-36](../work-orders/WO-36-host-network-and-staging-safety.md).
- Environment: `twinfra-dev-cairo-1`, node `192.168.1.3`, interface `eno1`.
- Owner authorization: static implementation only, 2026-10-15.
- No SSH/Dell, host-network, router, ruleset or live cluster operation executed.
- Tested revision: WO-36 branch; exact commit and CI run are linked in the PR.
- QoS target: retain the address/control plane across link loss and the old
  stateless pod during a blocked image rollout. Live results remain Pending.

## Static evidence

- Fake SSH/netplan transaction fixtures cover detached apply, timeout/zero-exit
  rollback, lost login, HTTPS failure, concurrent refusal, ownership, successful
  rollback and failed rollback restoring static files.
- Fixtures check address/route/DNS/InternalIP, since-boot WARN counters, both
  permitted Recreate reasons, PR-body staging attestation and unchanged image
  locks, production, retained WSL renders and historical baseline inventory.
- `platform_dev.py check`, `platform_sources.py check`, Helm/Kustomize,
  kubeconform, conftest, actionlint, documentation, licence and regression checks
  run offline. The PR records exact counts and the candidate/six-baseline CI run.
- Root file ownership and host commands are mocked in Windows fixtures; Linux
  CI runs the same offline tests. None establishes live netplan acceptance.

## Live evidence

| Check | Expected outcome | Observed outcome |
| --- | --- | --- |
| host-network --check / --apply / --check | Owned static .3, exact route/DNS, fresh key login and trusted API ready | Pending, owner after merge |
| Router power off for 60 seconds | .3 retained; unchanged node InternalIP; no control-plane restarts | Pending, optional owner test |
| Image-changing PR without staging line | staging-check fails, then passes after actual staging/check and dated attestation | Pending |
| Deliberately unstaged stateless rollout | Previous Ready pod continues serving | Pending |
| Rollback, if required | Saved DHCP restored only after fresh key login/API readiness; otherwise static restored | Pending |

## Pending gates, deviations and owner actions

- No deviations. The netplan includes `ignore-carrier: true` to implement the
  required address retention on carrier loss. Primary-source evidence is in the
  [runbook](../dev-environment.md#wo-36-dell-address-plan-and-safe-network-changes).
- After merge: owner checks, applies, and rechecks the static network. Only then
  change DHCP to `.100–.254`; optional MAC reservation to `.3`; optional UPS and
  controlled router outage test. No router change belongs to this PR.
- Owner adds `staging-check` as a required check later. Claude reviews before
  merge. Link-loss Prometheus alert remains WO-10 follow-up.
- Unexpected worker death or failure after acceptance requires local journal /
  saved-file inspection; the tool reports failure and does not claim recovery.

## Tester sign-off

Tester: Ahmed Mazen (@amazen33), enterprise and cloud tester; QoS tester
Result: Pending
Date (UTC):
QoS targets checked:
Notes:
