# WO-05: Admission policies generated from the SSoT

**Status:** Approved for implementation (owner, 2026-10-08) · **Phase:** 1 · **Author:** Claude · **Implementer:** Codex
**Branch:** `codex/wo-05-admission-policies` · **Review finding:** R5

## Goal

The SSoT security rules are enforced inside the cluster, not only in CI. Manifests applied by
script or by hand can no longer break them.

## Verified context

- `vcloud-ssot.yaml` (`security`) forbids floating image tags and application hostPath, restricts
  privileged or root access to justified exceptions, and names the registry.
- `tools/check_manifest_contract.py` enforces this statically and verifies the SHA-256 of
  `security/node-exceptions.json` against the SSoT.
- Lab components are applied by scripts that bypass CI, for example `lab/wsl/platform.sh`,
  `lab/wsl/endpoints/deploy.sh` and `deploy/console/deploy-wsl.py`.
- Lab schemas are Kubernetes 1.36. ValidatingAdmissionPolicy (`admissionregistration.k8s.io/v1`) has been GA since 1.30, so no new component is needed.

## Scope

1. Add `tools/render_admission_policies.py`. It generates ValidatingAdmissionPolicy and binding
   manifests into `deploy/policy/admission/` from `vcloud-ssot.yaml` and `security/node-exceptions.json`.
   It has a drift check, like the existing renderers, and CI fails if the output is stale.
2. Policies, which apply to Pods and to Pod templates of workload controllers:
   - Every image must come from an allowed registry prefix in the SSoT and be digest-pinned (`@sha256:`).
     If the lab needs staging aliases, add them to the SSoT, not to the policy.
   - No `hostPath` volumes, except exact matches from the node-exception allowlist.
   - No `privileged`, no `allowPrivilegeEscalation: true`, no added capabilities, and `runAsNonRoot` required.
     Exceptions come only from the allowlist.
3. Bindings cover the Twinfra namespaces (`platform-services`, `workload-apps`, `hpc-compute` and other Twinfra-owned ones).
   Before binding, inventory the running images and namespaces read-only with `kubectl get pods -A -o json`.
   K3s system namespaces are excluded at first, and the PR lists each exclusion with its reason.
4. Rollout: ship with `validationActions: [Audit, Warn]`. Switch to `[Deny]` in a separate small PR
   after the owner approves and the audit shows zero violations.
5. Tests: offline allow and deny fixtures for every rule, evaluated by a CEL-capable test harness of
   Codex's choice (record the licence in the register), plus server-side dry-run in the lab.

## Out of scope

Signature verification (a later work order, after image signing). Changing the node-exception allowlist or its hash.

## Acceptance criteria

- The generator, drift check and fixture tests pass in CI.
- In the lab, audit mode shows zero violations from current workloads (evidence: audit log excerpt).
- After enforcement, these three Pods are each rejected with a clear message in a Twinfra namespace:
  one with a floating tag, one with a hostPath, and one from an unknown registry. Existing workloads still roll out.
- Receipt: `docs/acceptance/admission-policies-<date>.md`.

## Owner actions

Approve the switch from audit to enforcement.

## Report back

The excluded namespaces and why, the violations found during audit and their fixes, and the CEL test tool chosen.
