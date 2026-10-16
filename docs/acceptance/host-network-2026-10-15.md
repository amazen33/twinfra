# Host network and staging safety acceptance receipt — 2026-10-15

## Scope and authorization

- Work order: [WO-36](../work-orders/WO-36-host-network-and-staging-safety.md).
- Environment: `twinfra-dev-cairo-1`, node `192.168.1.3`, interface `eno1`.
- Original implementation authorization: static changes only, 2026-10-15.
- This update records the owner's supplied live evidence, 2026-10-15/16 UTC.
  Codex executed no SSH/Dell, host-network, router, ruleset or live cluster operation.
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

### Owner-reported observations — 2026-10-15/16 UTC

Source: Ahmed Mazen's supplied live report. These observations were not
independently re-run by Codex. The UTC times below are retained as supplied
within that reporting window; no additional tested revision or measurements
are inferred. Recording them does not change tester sign-off.

| Check | Owner-reported observation |
| --- | --- |
| `host-network --check` | Passed; static address `192.168.1.3` |
| IPv4 DNS, in order | `192.168.1.1`, `1.1.1.1` |
| Owned network files | Current; profile has `accept-ra: false` and `link-local: []` on `eno1` |
| Router power-cycle / carrier loss | `eno1` carrier lost `23:35:48Z`, regained `23:36:28Z`: **40 seconds** |
| DHCP lease losses | **0** |
| Node address through the router cycle | Unchanged at `192.168.1.3` |
| Pod / control-plane restarts | None after the last boot at `22:32:03Z` |
| Platform pods | **20/20 Running** |
| Argo CD | Three Applications **Synced/Healthy** |
| Required repository check | Owner confirms `staging-check` is required, 2026-10-16; Codex made no GitHub settings change |

The 40 seconds measure physical carrier loss during a router power cycle, not
an address/default-route reconfiguration gap during a netplan transaction.
They do not replace or relax the five-second transaction-gap limit qualified
in the [WO-36a VM receipt](host-network-fix-2026-10-15.md).
The router's powered-off interval was not supplied; this record does not claim
that the earlier suggested 60-second power-off scenario was measured.

### Acceptance gates

| Check | Expected outcome | Observed outcome |
| --- | --- | --- |
| host-network --check | Owned current static .3 profile and ordered IPv4 DNS | Owner reports passed above; tester sign-off Pending |
| host-network --apply / fresh login and API readiness | Confirm only after fresh key login and trusted API ready | No new live apply/confirmation evidence supplied here; see WO-36a VM proof; Dell acceptance Pending |
| Router power-cycle | .3 retained; no control-plane restarts | Owner reports 40 s carrier outage, unchanged address, 0 DHCP lease losses and no pod/control-plane restarts since boot; tester sign-off Pending |
| Required staging check | Owner makes staging-check required | Owner reports configured on 2026-10-16; tester sign-off Pending |
| Image-changing PR without staging line | staging-check fails, then passes after actual staging/check and dated attestation | Pending |
| Deliberately unstaged stateless rollout | Previous Ready pod continues serving | Pending |
| Rollback under WO-36 Amendment 1, if required | Saved static .3 restored; rollback cannot select a different address | Dell live acceptance Pending; bounded transaction proof in WO-36a receipt |

## Pending gates, deviations and owner actions

- No deviations. The netplan includes `ignore-carrier: true` to implement the
  required address retention on carrier loss. Primary-source evidence is in the
  [runbook](../dev-environment.md#wo-36-dell-address-plan-and-safe-network-changes).
- The owner-reported current-profile check and router-cycle results are now
  recorded above; the tester reviews their scope before acceptance. No DHCP
  range change, MAC reservation, UPS test or new Dell rollback result is
  inferred. Image-staging failure and blocked-rollout acceptance remain Pending.
- The owner confirms `staging-check` is required as of 2026-10-16. This is an
  owner-reported settings fact, not a settings change or independent audit by
  Codex. Claude reviews before merge. The link-loss alert remains WO-10 work.
- Unexpected worker death or failure after acceptance requires local journal /
  saved-file inspection; the tool reports failure and does not claim recovery.

## Tester sign-off

Tester: Ahmed Mazen (@amazen33), enterprise and cloud tester; QoS tester
Result: Pending
Date (UTC):
QoS targets checked:
Notes:
