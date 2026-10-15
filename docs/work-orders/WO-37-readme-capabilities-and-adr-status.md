# WO-37: README, capability statement and ADR status cleanup

**Status:** Approved for implementation (owner, 2026-10-16: "WO-37 approved"). · **Author:** Claude · **Implementer:** Codex
**Branch:** `codex/wo-37-readme-capabilities` · **Decisions:** ADR-0052 (evidence first), ADR-0053 (tenancy, Proposed), ADR-0029, ADR-0033 · Documentation and CI only

## Scope

1. **Add the decision records** to `docs/adr/` and the index: ADR-0050, 0051, 0052 and 0053 from `E:/vcloud-handoff/adr/`, fixing relative links.
2. **ADR status cleanup** in `docs/adr/README.md`, using the ADR-0052 vocabulary:
   - ADR-0014, 0015, 0016, 0017 and 0023 become **Deferred (reference design)**;
   - every evidence link to a WSL receipt is labelled **Historical (retired environment)**, and those ADRs show **Accepted (design)** until they are re-verified on cairo-1;
   - receipts that already exist on cairo-1 (the WO-31 bootstrap, the soak, WO-36) are linked where they apply;
   - ADR-0008 (Tekton) and ADR-0020 (delivery) become **Superseded by ADR-0052** (owner confirmed decision 5: GitHub Actions + GHCR + signed provenance verified at deploy);
   - replace the fixed "39 records" wording with a count generated from the index.
3. **README rewrite of the top section:**
   - **The tagline** keeps "your AWS twin, on your own infrastructure", followed by "— an AWS-compatible API subset; see [capabilities](../capabilities.md)."
   - **New "Current capability and readiness" section:**
     - live: `cairo-1` dev, a single bare-metal node;
     - Dev-verified items, with receipt links;
     - disabled: Modules 5a and 5b;
     - supported environment: kubeadm on Ubuntu 24.04, bare metal or VM; nothing else is supported;
     - not claimed: high availability, multi-tenancy, compliance, production.
   - **Remove WSL as the current environment** (one line pointing to ADR-0045). Fix the console access path to the cairo-1 tunnel, and fix the stale identity text.
   - **Move Modules 5a and 5b** under "Reference designs (disabled)". Qualify the Module 3 "end-to-end GitOps" wording as implemented or reference until it is Dev-verified.
4. **`docs/capabilities.md`:** one row per AWS service and per platform capability.
   - Columns: status (Emulated by MiniStack / Real / Parity-tested / Planned), evidence link, and the work order that changes it.
   - Today every AWS API row is *Emulated* or *Planned*. Real S3 and EC2 are planned in WO-22, and parity in ADR-0033.
5. **CI check (blocking):**
   - every row or ADR marked Dev-verified, Production-accepted, "Real" or "Parity-tested" must link to a receipt under `docs/acceptance/` whose tester sign-off is `Accepted`;
   - Historical evidence never satisfies the check;
   - add tests for a missing receipt, a Pending sign-off and a WSL-only receipt.
6. **CHANGELOG entry.** Only docs and CI change; no runtime change.

## Acceptance criteria

The PR gate is green, including the historical baselines. The new check passes on the cleaned index and fails on the three test fixtures. The README makes no claim stronger than its evidence.

## Report back

The status changes per ADR (before and after), the capability table, and CI.
