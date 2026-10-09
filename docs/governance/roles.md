# Twinfra roles and Definition of Done

## Roles

Title: **Ahmed Mazen (@amazen33), Founder and Product Lead.** He holds the four people-roles below. They stay
separate in the docs, so it is always clear which hat a sign-off is given in.

| Role | Who | Responsibilities |
| --- | --- | --- |
| Owner and Product Owner | Ahmed Mazen (@amazen33) | Owns the product goal and the backlog order (which work orders run, and when); decides; accepts ADRs; approves live lab changes; merges |
| Scrum Master | Ahmed Mazen (@amazen33) | Runs the cadence (sprint planning, review, retrospective), removes blockers, protects the Definition of Done |
| Enterprise and cloud tester; QoS tester | Ahmed Mazen (@amazen33) | Approves test scope and quality-of-service targets (SLOs, latency, throughput, availability, RPO and RTO); runs or witnesses live acceptance; signs off every live receipt and the parity scorecard |
| Architect and reviewer (Developer) | Claude | Writes architecture, ADRs and work orders; reviews every PR against its work order |
| Implementer (Developer) | Codex | The only coder; implements one work order per branch |

## Definition of Done

A work order is done when all of these are true:
- its PR is merged with the "vCloud PR gate" green, historical baselines included;
- Claude has approved it against the work order;
- every live result has a receipt in `docs/acceptance/` with the tester's sign-off set to Accepted;
- licence-register and documentation updates are in the same PR.

## Review and acceptance

Claude reviews each PR against its work order before the owner merges. No agent
approves its own work. Stage 1's zero required GitHub approvals does not remove
this review or the Definition of Done. See the [staged ruleset runbook](branch-protection.md).

Every live result uses the [acceptance receipt template](../acceptance/README.md).
Codex writes `Result: Pending`. Only the tester changes it. A work order's live
acceptance is complete only after the tester's sign-off. A rejection reopens the
work order with the tester's notes.
