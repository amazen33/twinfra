# ADR-0045: Retire the WSL environment once the Twinfra dev environment is accepted

**Status:** Accepted (owner, 2026-10-09: "use the VM instead of the WSL environment, and remove all WSL evidence once it runs successfully").
**Author:** Claude (platform architecture). **Decider:** Ahmed Mazen, Owner and Product Owner.
**Supersedes:** ADR-0024 (WSL host-routing exception) when WO-28 completes. Builds on ADR-0032 and ADR-0038.

## Context

The WSL K3s environment lost pod networking on 2026-10-07, 2026-10-08 and 2026-10-09. After each WSL restart the mirrored network card changed
its name (`eth1` to `eth2`), Cilium kept the old name, and every pod sandbox failed. The repository documents a manual fix and
states that unattended recovery is not implemented. The WSL environment also reserves 20 GB of the host's 32 GB. A Hyper-V VM has fixed interfaces
and fixed memory, so the failure cannot occur there.

## Decision

1. **The dev environment (WO-21) is the only Twinfra environment.** No further work is done to repair or automate the WSL environment.
2. **Retirement gate.** WSL material is removed only after **all** of these hold:
   - the dev-environment receipt (`docs/acceptance/dev-environment-<date>.md`) has the tester sign-off **Accepted**;
   - reusable pieces have been ported to environment-neutral locations (WO-21 amendment);
   - the owner confirms in the pull request.
3. **What "remove all WSL evidence" means.**
   - **In the repository tree (WO-28):** delete the WSL environment code, tests, docs, receipts, validation records, Makefile targets and CI
     mappings, and the WSL sections of the README and MILESTONES. Names containing `wsl` do not appear in current files.
   - **Preserved in Git history only:** the last commit that contained them is tagged `archive/wsl-final`. Nothing about the
     lab stays in the working tree. History is not rewritten.
   - **Decision records stay.** ADRs are the decision log and are never deleted. Those that mention WSL (ADR-0024 and others) become
     `Superseded` with one line, and their text is unchanged.
   - **CI keeps working for old revisions.** The six historical baselines are checked out at their own commits, so deleting files on
     `main` does not affect them. CI checks that mention WSL paths must tolerate their absence.
4. **Live cleanup is an owner action, not Codex's** (runbook in WO-28). It removes only the vCloud pieces from the WSL distro.
   **The distro itself is not unregistered**: the same Ubuntu WSL installation (mirrored networking) is the controller for the
   pCloud and IOT-EE Hyper-V lab.
5. **Address plan.** The Twinfra dev environment must not reuse the pCloud lab's `iotee-nat` range (10.20.0.0/24). WO-21's plan is corrected.

## Consequences

One environment, no environment-specific names, and about 20 GB of host memory returned. The cost is that the WSL environment's receipts are no
longer browsable in the tree. They remain one `git checkout archive/wsl-final` away.
