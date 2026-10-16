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
  public per-unit journals accompany it. The [real VM run](https://github.com/amazen33/twinfra/actions/runs/38800517974)
  passed on 2026-10-15 at 20:18:34Z, testing PR merge commit
  `871ebeab52def254dd9095b47e1fecd06a4c065a` (branch `a6e65de`).
- Real production worker, netplan/networkd, detached systemd unit, key-only SSH
  and TLS-verified kubectl; dummy `eno1` and synthetic Node/readyz API. This proves
  transaction behavior, not Dell hardware, DHCP server or Kubernetes acceptance.
  Primary runner routing is protected; private test keys remain in tmpfs and
  are never uploaded. The fixture refuses non-hosted or pre-existing host state.
- Production/WSL renders, image locks and historical baseline inventory remain
  byte-identical. Gate counts/results and all six historical revisions are in PR CI.

### Observed real Ubuntu VM results

Ubuntu 24.04.5 LTS, Microsoft virtual machine; netplan.io
`1.1.2-8ubuntu1~24.04.3`, systemd `255.4-1ubuntu8.17`, OpenSSH server
`1:9.6p1-3ubuntu13.19`. The initial exact legacy profile was adopted with WARN.

| Transaction | Result | Duration | Address / route / final YAML |
| --- | --- | --- | --- |
| Apply legacy upgrade | Accepted after fresh key login and trusted HTTPS readiness | 3.67 s | `.3/24`, gateway `.1`, corrected static profile |
| Rollback upgrade | Accepted through the same confirmation checks | 3.22 s | `.3/24`, gateway `.1`, exact legacy static bytes |
| Apply with readiness returning HTTP 503 | Confirmation refused; real timeout and worker restoration passed | 121.49 s | `.3/24`, gateway `.1`, exact legacy static bytes; no DHCP YAML |

All 235 samples (approximately every 0.5 seconds) recorded the intended address,
gateway and Node InternalIP; no sample showed a missing/different address or
route. This is sampled evidence, not a claim of zero sub-sample packet loss.
The timeout operation correctly reports `failed`; the integration test passes
because it asserts refusal and successful runtime/YAML restoration. No mocked
netplan subprocess, shortened timeout or insecure TLS override was used.

**Repeat-run finding:** the [next VM run](https://github.com/amazen33/twinfra/actions/runs/38801049650)
completed all three operations with the expected final static `.3` and route,
but its continuous-sampling assertion failed. Sample 9 at
`2026-10-15T20:20:27.057968Z` observed `.3` temporarily absent and no default route
on `eno1` during reconfiguration; adjacent samples and all final checks show
`.3`/gateway `.1`. No different address was observed. This supersedes any
inference that the first pass establishes uninterrupted retention. The strict
assertion correctly failed. The owner then approved a measured gap of at most
five seconds, no alternate IPv4 or DHCP on `eno1`, and fresh SSH/trusted TLS/
Node InternalIP post-checks. The updated VM sampler enforces those exact bounds;
the qualifying [bounded VM run](https://github.com/amazen33/twinfra/actions/runs/38802229941)
passed at `2026-10-15T20:31:10Z`, PR merge commit
`d5fa59bdfad828e39d1127cc1c85981ba2ee3792` (branch `eaba8dd`). The original
first-pass result alone is insufficient; this bounded run makes the PR eligible
for review under the owner's explicit direction.

| Bounded acceptance measurement | Observed result |
| --- | --- |
| Maximum measured address/default-route gap upper bound | **0 seconds** (no missing-address/route samples; limit 5 seconds) |
| Samples / maximum observation interval including command time | **1,154 / 0.150156 seconds** |
| All IPv4 addresses on eno1 | `.3` only; no alternate address |
| DHCP on eno1 | Disabled generated networkd configuration, no DHCP client/lease or dynamic address; no standalone DHCP client process observed |
| Apply / rollback / refused confirmation | 2.94 s / 2.94 s / 121.89 s; expected accepted / accepted / failed operation statuses |
| Fresh key-only SSH / trusted TLS readyz after each operation | All passed |
| Node InternalIP after each operation | `192.168.1.3` |

The sampler queries `networkctl --json=short`, the active generated network
configuration and lease state, `/proc` client processes, every `eno1` IPv4
address and its default routes. It fails on sampling errors, observation
coverage gaps over one second, alternate IPv4, DHCP activity, wrong routes,
unrecovered gaps or a conservative gap bound over five seconds. Gap bounds span
the last healthy sample through completion of the first recovered sample.
The unrelated runner primary NIC retains its own network configuration. Results
are sampled evidence, not proof of no shorter unobserved packet interruption.

The [bounded repeat on branch faaecc5](https://github.com/amazen33/twinfra/actions/runs/38802828350)
passed at `2026-10-15T20:35:33Z`, PR merge commit
`a535c335069e3b3cc9638fd85a1c77de3de2b2d6`. It measured one conservative
address/default-route gap upper bound of **0.244071 seconds**, below the
five-second limit; 1,150 samples, maximum observation interval 0.141625 seconds.
This is the maximum across the two recorded bounded qualification runs.
No alternate IPv4 or DHCP activity was observed. Fresh SSH, trusted `/readyz`
and `.3` Node InternalIP passed after apply (4.10 s), rollback (4.12 s), and
refused confirmation with real timeout/restoration (121.66 s). This repeat
demonstrates that a measured nonzero gap is recorded and assessed against the
owner's bound rather than silently excluded.

Local verification: 133 related unit/regression tests, 151 CI-control tests,
864 conftest checks, 127 kubeconform-valid resources, render/source drift,
licence, documentation/Mermaid and actionlint passed. Git Bash needed execution
outside the Windows sandbox; the same offline tests then passed without
weakening them. The real Linux kubeadm preview and six historical baselines run
in GitHub CI, not on this Windows host.

## Remaining owner acceptance

The [owner-reported WO-36 live evidence](host-network-2026-10-15.md#owner-reported-observations--2026-10-1516-utc)
now records a passed current-profile check, static `.3` with ordered IPv4 DNS,
`accept-ra: false` / `link-local: []`, a 40-second router-cycle carrier outage
with no address change or DHCP lease losses, no pod/control-plane restarts
after the reported last boot, 20/20 pods Running and three Argo CD Applications
Synced/Healthy. The owner also confirms `staging-check` is required as of
2026-10-16. Those supplied observations await tester sign-off; Codex performed
no new live checks or settings changes. Physical carrier downtime is distinct
from the five-second netplan transaction-gap bound above.

Use the [dev runbook](../dev-environment.md#wo-36-dell-address-plan-and-safe-network-changes)
for any separately authorized transaction. No new Dell apply/rollback or
blocked-rollout proof is supplied by this evidence update. Do not assert a DHCP
reservation unless it exists. AMT power/KVM acceptance is separately Pending under its
[owner runbook](../runbooks/intel-amt.md). No tool touches AMT.

## Tester sign-off

Tester: Ahmed Mazen (@amazen33), enterprise and cloud tester; QoS tester
Result: Accepted
Date (UTC): 2026-10-16
QoS targets checked: netplan apply, refused confirmation and rollback on real Ubuntu 24.04; maximum reconfiguration gap 0.245504 s (limit 5 s) over 1,140 samples; no alternate IPv4 and no DHCP activity; fresh SSH and trusted /readyz passed.
Notes: VM proof (CI). Live adoption on twinfra-dev-cairo-1 confirmed by host-network --check: static 192.168.1.3, owned files current. Recorded by the architect at the owner's instruction.
