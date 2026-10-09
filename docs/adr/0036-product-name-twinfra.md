# ADR-0036: The product is named Twinfra (formerly vCloud)

**Status:** Accepted (owner, 2026-10-09)
**Author:** Claude (platform architecture). **Decider:** Ahmed Mazen, Owner and Product Owner.

## Context

- "VCLOUD" is an active trademark from VMware's vCloud product line (VMware by Broadcom), in use since 2008,
  so the current name is a legal and marketing liability.
- Two owner-proposed alternatives were rejected:
  - "AWSPilot" uses the AWS mark, which AWS's trademark guidelines restrict when it implies affiliation.
  - "CloudPilot" belongs to CloudPilot AI, a Kubernetes and AWS startup in the same market.
- Conflict scans on 2026-10-09 found no exact "Twinfra" product and no GitHub repositories with that name.
  A 2022 "TWIN INFRA" filing covers construction project-management software, which is a different market.

## Decision

1. The product name is **Twinfra**. Tagline: *your AWS twin, on your own infrastructure.*
   It is written "Twinfra" in prose and `twinfra` in identifiers.
2. The rename runs in three stages so the live lab never breaks (WO-20):
   - **Stage A: branding and docs.** README, MILESTONES, current docs and console UI text read "Twinfra",
     with a one-line note "formerly vCloud". Historical ADRs 0001-0035, acceptance receipts and
     validation JSON stay unchanged, because they are history.
   - **Stage B: repository rename.** The owner renames `amazen33/vCloud` to `amazen33/twinfra` in GitHub settings;
     GitHub redirects the old URLs. Codex then updates every hard-coded repository reference:
     Argo CD `repoURL` values, SSoT `gitOpsRepository`, `tools/ci/pr-baselines.json` `repository`, and docs links.
   - **Stage C: technical identifiers.** Covers the SSoT identity (`vCloud-prod-01`, `vcloud.example.com`,
     `registry.vcloud.example.com`), the Keycloak realm and client IDs, `vcloud.io/*` labels, and `vcloud-*` resource names.
     These change when the always-on lab is rebuilt on the Ubuntu VM (ADR-0032, Phase 2), not by in-place
     migration of the WSL lab. This stage needs its own work order.
3. Region naming (D10) stays open. The previous `vc-` prefix proposal is withdrawn; the replacement is
   decided together with D9, D11 and D12.
4. Before any commercial launch, the owner commissions a formal trademark search (USPTO, EUIPO or WIPO,
   plus Saudi Arabia and Egypt). This ADR records a product decision, not legal clearance.

## Consequences

- Public material (README, portfolio, plan) uses Twinfra from Stage A onward.
- Old identifiers coexist with the new name until Stage C. Docs say so explicitly, so nobody mistakes a
  `vcloud` realm or label for a stray leftover.
- CI must keep validating historical baselines that use the old names.
