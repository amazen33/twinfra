# ADR-0032: One environment model; the always-on lab moves to an Ubuntu VM

**Status:** Accepted (owner, 2026-10-08)
**Author:** Claude (platform architecture). **Decider:** vCloud owner. **Records:** D4.

## Context

The running system is single-node K3s on WSL (`lab/wsl/`). The production profile (Ubuntu 24.04,
kubeadm, Modules -1 to 5b) has no live acceptance. The console exists twice (`deploy/console/`
and `lab/wsl/console/`). Several recent changes repair WSL networking and restarts, and
ADR-0024 records a WSL routing exception.

## Decision

1. Environments (lab, on-prem, AWS) are declared in `vcloud-ssot.yaml`. Each is rendered from
   one shared base plus an overlay, and differences live only in overlays.
2. Argo CD runs one app-of-apps per environment, from protected `main` or a release tag. It never
   tracks a feature branch.
3. The always-on lab runs on an Ubuntu 24.04 VM on Hyper-V using the real kubeadm profile.
   WSL K3s stays for fast inner-loop development only.
4. One console code base, with per-environment configuration.

## Consequences

- WSL-specific repairs stop being platform work.
- The production profile is exercised every day.
- D12 (two logical regions in the lab) is still open and builds on this model.
