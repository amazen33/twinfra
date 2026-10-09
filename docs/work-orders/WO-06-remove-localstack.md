# WO-06: Remove LocalStack; MiniStack is the only emulator

**Status:** Approved for implementation (owner, 2026-10-08) · **Phase:** 1 · **Author:** Claude · **Implementer:** Codex
**Branch:** `codex/wo-06-remove-localstack` · **Decision:** ADR-0030

## Goal

Remove LocalStack, because releases since March 2026 require a LocalStack account and auth token.
MiniStack (MIT), which is already deployed, becomes the only AWS emulator. Later it serves the
long-tail services behind the gateway.

## Verified context

- LocalStack Community 4.14.0 is pinned in `lab/wsl/localstack/artifacts.lock.json`.
- The LocalStack module is `lab/wsl/localstack/*`, `tools/wsl_localstack.py` and `tests/test_wsl_localstack.py`.
  Its CI mapping is the `lab/wsl/localstack` entry in `tools/ci/run_checks.py` (around line 38).
- The console offers a backend choice (`console/src/App.tsx` line 77; `console/server.py`; `console/src/api.ts`;
  `console/src/App.test.tsx`). The lab console (`lab/wsl/console/*`) has routes and profile entries.
- Other references are in `deploy/console/bootstrap.yaml`, `docs/service-access.md`, `lab/wsl/README.md`,
  `lab/wsl/endpoints/README.md`, `docs/WSL_SETUP_GUIDE.md` and ADR-0025/0026.
- MiniStack is configured in `lab/wsl/console/profile.json` (service `ministack`, port 4566, MIT).

## Scope

1. Delete the LocalStack module, its tool and its tests. Remove LocalStack from the console UI, backend, API client,
   tests, profiles, routes and network policies, through their generators (`tools/vcloud_console.py`, `tools/wsl_console.py`).
2. Make MiniStack the default and only backend. Remove the emulator selector, or keep it with MiniStack as its single option.
   Pin MiniStack by digest in the lock file at the newest release that is at least 14 days old.
3. In `tools/ci/run_checks.py`, keep the `lab/wsl/localstack` mapping valid for **historical baselines**
   by applying it only when the directory exists in the selected revision.
4. Docs: update the service-access, README and lab docs. Leave existing acceptance receipts unchanged, because they are history.
   Mark ADR-0025 superseded (done in WO-03 if that merges first). Update the licence register (WO-02) so LocalStack is removed.
5. Live lab: remove the LocalStack Deployment, Service, route and port-forward **only after owner approval**,
   then verify that port 4566 forwarding still reaches MiniStack.

## Out of scope

New MiniStack services or real back-end services, which come in Phase 3.

## Acceptance criteria

- No LocalStack image or reference remains in lock files, manifests or code. A CI search check enforces this.
- Console S3, EC2 and DynamoDB read views work against MiniStack in browser acceptance.
- The PR gate passes, including the historical baselines.
- Receipt: `docs/acceptance/localstack-removal-<date>.md`, with the lab state before and after.

## Owner actions

Approve removing LocalStack from the live lab.

## Report back

Files removed and changed, the MiniStack version and digest, and any console feature lost in the change.
