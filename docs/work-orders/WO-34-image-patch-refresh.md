# WO-34: Patch refresh of all pinned images, prioritised by risk

**Status:** Approved for implementation (owner, 2026-10-14: "approve exceptions and WO-34"). Start after PR #49 (WO-32) merges. Due **2026-11-12**, matching the expiry of WO-32's Critical exceptions.
**Phase:** 2 · **Author:** Claude · **Implementer:** Codex · **Branch:** `codex/wo-34-image-refresh` (several PRs are allowed, one per priority).
**Decisions:** ADR-0049 (gate, exceptions, expedite rule), ADR-0044 (licence gate). **Depends on:** WO-32 merged, because the gate and exception list must exist.

## Why

The baseline scan of 2026-10-13 (`E:\vcloud-handoff\receipts\supply-chain-baseline-2026-10-13.md`) found:
- **77 Critical and 371 High findings that have a fix available**, across 22 images, and **0 KEV matches**;
- **where they come from:** 792 Go modules (an old Go standard library in kube-* 1.36.5, Cilium and etcd; `golang.org/x/crypto` and `x/net`), and 279 Debian packages (OpenSSL 3.5.4 and `perl-base` in the console's Python base, plus APISIX);
- **the lockfiles:** only the CI-only `tools/ci/mermaid` has findings (`lodash-es`, `mermaid`, `katex`).

Aggregate counts aren't a risk rating. This work order fixes what's fixable, and **triages** the rest by exploitability, exposure, privileges and mitigations.

## Scope, in priority order

1. **Our console image, Critical.**
   - Move the Python base to the newest supported `python:3.14.x-slim-trixie` digest.
   - Rebuild the console reproducibly (`platform_dev.py build-images`).
   - The **digest changes**. Update `console/image.lock.json` and `deploy/common/images.lock.json` through the builders and generators, and say so in the PR. The owner approves the new digest.
   - **In the same rebuild (WO-35 prerequisite, so the console digest changes only once):** rename the image's title label and history text from `vcloud-console` to `twinfra-console`, and the builder's `TAG` and `BASE` to the `registry.twinfra.example.com` names.
2. **Argo CD, CoreDNS and etcd, High.** Move each to its latest supported patch release for the pinned minor version:
   - Argo CD 3.5.x;
   - CoreDNS and etcd as kubeadm v1.36 supports them, checked against kubeadm's version constants.
3. **Everything else.**
   - Kubernetes control-plane images: the latest 1.36.z.
     - kubeadm, kubelet and kubectl move with them.
     - The Dell needs a `kubeadm upgrade` runbook step; that's an owner live action.
     - Never skip a minor version.
   - Cilium, Envoy and the operator: the latest 1.20.z.
   - APISIX, OpenBao, MiniStack, Valkey, CNPG and pause: their latest patch releases.
   - The CI-only `tools/ci/mermaid`: update `mermaid` and its `lodash-es` and `katex` dependencies.
4. **Rebuild, rescan and compare before promotion.** For every changed image, include a *before versus after* table in the PR: Critical and High, with and without fixes. Confirm the digests in the locks are the ones the dev overlay renders and the Dell stages.

## Rules

- **Release choice.**
  - Use the newest patch release that is at least 14 days old (ADR-0049).
  - **Expedite** (the owner waives the cooling-off period in the PR) when a fix addresses a KEV-listed vulnerability or one the vendor rates critical and actively exploited.
  - Never take a release *only* because of its age. Read its release notes for regressions and breaking changes.
- **Compatibility.** Each update must be compatible with Kubernetes v1.36, Cilium 1.20 and the other pins. Use only versions the upstream project supports for that combination. Stop and report if an update needs a minor-version jump or a behaviour change.
- **Immutable pins.** Pin by digest. Change generated manifests, checksums and receipts only through their generators. Keep the six historical baselines green.
- **Triage the Go findings.**
  - Before accepting any Go-standard-library or `x/*` finding as an exception, run `govulncheck -mode=binary` on the extracted binaries to classify each as **reachable** or **not reachable**. govulncheck is BSD-3-Clause; pin it and add it to the licence register.
  - Reachable findings must be patched; they can't be excepted.
  - Not-reachable findings may keep a WO-32 exception with that evidence attached.
- **Closing exceptions.** Each fixed finding closes its WO-32 exception in the same PR.

## Out of scope

Minor or major version upgrades (for example Kubernetes 1.37 or Argo CD 3.6), the production profile's rollout, and GHCR publishing.

## Acceptance criteria

- **Gate:** the PR gate is green (supply-chain gate, licence gate, historical baselines).
- **Console:** 0 Critical findings with a fix.
- **Argo CD, CoreDNS and etcd:** 0 Critical findings with a fix.
- **Exceptions:** every remaining Critical exception has govulncheck or vendor evidence, and an expiry within 30 days.
- **Live, by the owner:** the Dell has the refreshed images staged and pinned; the control plane is upgraded to the refreshed 1.36.z with `kubeadm upgrade`; all pods are Running; the nightly scan issue shows the drop.
