## Work order and scope

- Work order ID and link:
- Scope implemented:
- Out of scope:

## Static checks

List the commands, tested revision, results and any failures or checks that could
not run locally. Link the exact GitHub run for the `vCloud PR gate`, including
the historical baselines. Do not treat static checks as live acceptance.

## Live checks

List owner authorization, environment, commands and results, or state
`Not executed: no live changes in this work order`. Keep credentials and
private configuration out of commands, logs and PR text.

## Evidence receipt

- Receipt path or validation artifact/run link:
- Date and acceptance scope:

Live results require a dated receipt in `docs/acceptance/`. If a gate remains
pending, identify it explicitly rather than recording a pass.

## Licence register

List component/licence-register changes, or state `Not applicable: no component
changes`. Apply the licence-register gate once WO-02 lands.

## Deviations

List approved deviations from the work order, with the owner's authorization,
or state `None`. Stop and report an unapproved incorrect or impossible requirement.

## Owner actions and review

- Owner actions still required:
- Named reviewer and review outcome:

Claude reviews against the work order before the owner merges. Agents must not
approve their own work. The owner applies repository rules using the
[branch-protection runbook](../docs/governance/branch-protection.md).
