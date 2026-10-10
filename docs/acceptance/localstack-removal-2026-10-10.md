# LocalStack removal acceptance receipt — 2026-10-10

## Scope and authorization

- Work order: [WO-06](../work-orders/WO-06-remove-localstack.md).
- Environment / namespace: `twinfra-dev-cairo-1` / `twinfra-platform-services`, under [ADR-0046](../adr/0046-naming-dev-environment-and-regions.md).
- Owner authorization: static repository removal only; no live changes, provisioning, installations or GitHub settings changes.
- Tested revision: the `codex/wo-06-remove-localstack` PR head; exact SHA and CI evidence are recorded in its PR and validation artifacts.
- Live test start/end (UTC), witness and agreed QoS targets: Pending.

## Static evidence

- The deleted module is `lab/wsl/localstack/*`, `tools/wsl_localstack.py` and `tests/test_wsl_localstack.py`. Shared APISIX ingress prerequisites are preserved in `tools/platform_ingress.py` and `deploy/common/`.
- The console has a single MiniStack backend and the AWS read view is `/console/cloud`. LocalStack routes, selectors, policies and images are removed from generated deployable output. The CI guard rejects reintroductions in code, locks and manifests; only the exact historical CI bundle/dispatch lines remain exempt.
- MiniStack is pinned to `1.5.17`, `sha256:11d7308bfc75029d55625b9525e84a2401431ed1ff2148c6311800ff5009ae9c`. Release and image publication dates were verified against the 14-day rule on 2026-10-10. MIT licence evidence is recorded in the register and `security/licences/ministack/LICENSE`.
- Unit fixtures cover signed, read-only S3, EC2 and DynamoDB requests against MiniStack. Browser behavior is Pending.
- Existing acceptance receipts remain unchanged. Two historic links to the deleted runbook are resolved by a CI check against its frozen pre-removal Git revision and content hash; current missing links still fail validation.
- Commands/results and the full candidate plus six historical baseline run URLs: recorded in the PR. Linux-only checks run in GitHub CI rather than being reported as local passes.

## Live evidence

| Check | Expected outcome | Observed outcome | Evidence reference / UTC timestamp |
| --- | --- | --- | --- |
| Dev environment state before removal | Inventory any remaining LocalStack deployment, service, route and forwarding | Not observed; Pending | No live access authorized |
| Owner-approved cleanup, if resources exist | Remove only obsolete LocalStack resources and forwarding | Pending | Owner authorization required |
| Dev environment state after deployment | MiniStack is the only emulator | Pending | Deploy and inspect the PR revision in the dev environment |
| Port 4566 forwarding | MiniStack health endpoint responds | Pending | See [service access](../service-access.md) |
| Console storage, AWS and DynamoDB tabs | S3, EC2 and DynamoDB read views succeed against MiniStack | Pending | Tester browser acceptance in the dev environment |

## Pending gates, deviations and owner actions

- No live changes or browser acceptance were attempted. WSL material is retained until WO-28, except the LocalStack module explicitly removed by WO-06.
- Lost features: the LocalStack backend, its selector choice, proxy/health endpoints and `/console/localstack` tab. The MiniStack AWS tab moves to `/console/cloud`; its S3, EC2 and DynamoDB read capabilities remain covered by unit fixtures.
- MiniStack image SBOM review remains an open licence-baseline finding, with its original expiry of 2027-01-07. Updating the pin does not assert image-level licence clearance or extend the deadline.
- Deviations: None; references to the old lab are interpreted as the dev environment under the owner's instruction and ADR-0046.
- Owner actions: obtain Claude's review before merge; authorize any necessary live cleanup separately; deploy to the dev environment, run the Pending checks, and obtain tester sign-off.

## Tester sign-off
Tester: Ahmed Mazen (@amazen33), enterprise and cloud tester; QoS tester
Result: Pending
Date (UTC):
QoS targets checked:
Notes:
