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

## Amendment 1 (2026-10-14, architect): ruling on the stop in draft PR #55

**Status:** still Approved. The due date of **2026-11-12** stands. Draft PR #55 stays a draft until P1 is complete.

1. **No expedite. I agree with Codex.**
   - The CISA KEV catalog 2026.10.13 has no entry for CVE-2026-78663 (GO-2026-6612, Go stdlib and `x/net`).
   - It also has no entry for the Argo CD 3.5.4 advisories CVE-2026-77459, CVE-2026-55797 and CVE-2025-61560.
   - Vendor-rated "critical" without evidence of active exploitation does not qualify.
2. **Release-age rule for base images.** This is the owner-delegated recommendation, and I agree with it.
   - Age is measured from the **upstream software release**: CPython 3.14.8 was released on 2026-09-30, so it qualifies.
   - A **rebuilt digest of that same release from the official publisher** is eligible when it passes the WO-32 gate.
   - Record both dates in the receipt; the digest was published on 2026-10-09.
   - This applies to every base image. It will be written into ADR-0049 as a clarification at its next revision.
3. **One blocked component no longer stops the whole work order.** Use one PR per priority, which the work order already allows.
   - **PR #55: finish P1 (the console) now.**
     - Commit the preserved candidate.
     - Run the full before-and-after scans and close the console's exceptions.
     - Mark it ready for review.
     - The govulncheck tooling stays in this PR.
   - **P2a Argo CD: target `v3.5.5`.** It was released on 2026-10-12 at 10:59 UTC and is **eligible from 2026-10-26**.
     - It is the first 3.5 patch that has **both** the Argo CD security fixes from 3.5.4 and the Go 1.26.9 and `golang-x` updates.
     - **Before** 2026-10-26, as data only:
       - run govulncheck on the 3.5.5 binaries and confirm that GO-2026-6612 is gone;
       - show, by static search of the rendered manifests, that Twinfra uses neither of 3.5.4's potentially breaking behaviours: `helmGlobals.configHome`, and OCI manifests larger than 4 MiB;
       - confirm that the release notes don't change ServerSideDiff or IncludeMutationWebhook (WO-31 Amendments 14 and 14a).
     - **On or after** 2026-10-26, promote it in its own PR.
     - If 3.5.5 doesn't clear the finding, **stop and report**. Do not move to 3.6.
   - **P2b CoreDNS and etcd, and P3: continue now, each in its own PR.**
     - Triage every Go binary with govulncheck.
     - If a component has a reachable finding and no eligible patch, stop **that component only** and report the date its patch becomes eligible.
4. **Interim risk until 3.5.5 is live.**
   - The Dell runs Argo CD 3.5.3. It lacks 3.5.4's fixes for four CRITICAL advisories:
     - repo-server command execution through Kustomize remote refs;
     - command execution through Kustomize's Helm config home;
     - file reads through Jsonnet imports;
     - an AppProject bypass through PreDelete and PostDelete hooks.
   - Exploiting them requires putting content into a repository or Application that Argo CD processes.
   - **Codex,** statically and with no live changes, reports:
     - that every AppProject's `sourceRepos` allows only the owner's repositories;
     - that no Application uses Jsonnet or Kustomize remote bases.
   - **Owner:**
     - add no third-party repository or Application to Argo CD until 3.5.5 is live;
     - keep branch protection on the synced branch;
     - keep Argo CD reachable only through the tunnel.
   - The existing WO-32 exception for the Go finding stays in force until its own expiry. It is not extended.

## Amendment 2 (2026-10-14, architect): ruling on Codex's status report of 2026-10-14

**Status:** still Approved; due **2026-11-12**.
- **P1 (console) met its acceptance:** 23 → 0 Critical and 118 → 0 High with fixes.
- **Correction to Amendment 1:** Argo CD **3.5.5 still contains GO-2026-6612.** Its Go 1.26.9 update did not clear the finding.

1. **New repository rules apply** (twinfra PR #57, merged 2026-10-14):
   - every PR must add an entry under `## [Unreleased]` in `CHANGELOG.md`, or carry the label `changelog:skip` with a reason;
   - `release-checks` is a required check on `main`.

   Rebase PRs #55 and #56, and the coming P3 PR, onto the new `main`, and add their changelog entries.
2. **P1 (PR #55):** push the local fix for the historical hygiene assertion. Once CI is green, mark it ready for review.
3. **P2a, Argo CD: net improvement beats waiting.**
   - Staying on 3.5.3 keeps **both** GO-2026-6612 **and** the four CRITICAL Argo CD advisories that 3.5.4 fixed.
   - **Promote 3.5.5 on or after 2026-10-26**, provided it introduces no new Critical or High finding compared with 3.5.3, and the static compatibility checks from Amendment 1 hold.
   - GO-2026-6612 stays an **open, tracked finding**. It is not a reason to keep the worse version.
4. **Precise reachability for GO-2026-6612** (Argo CD, and CoreDNS and etcd as well).
   - Binary mode shows only that the affected symbols are present. Run `govulncheck` in **source mode** on each project's source at the pinned tag, with the Go toolchain recorded in the binary's build info (`GOTOOLCHAIN`), and record the call stacks.
   - Report which module still carries the finding in 3.5.5: the stdlib or `golang.org/x/net`.
   - **Not reachable:** keep it under an evidence-backed exception, at most 30 days if Critical, as WO-34's rules allow.
   - **Reachable:** stop and report. The owner chooses between a time-boxed risk acceptance, with the compensating controls already in place (Argo CD reachable only through the tunnel, owner repositories only), and waiting for a fixed patch.
   - **Never** build Argo CD, CoreDNS or etcd ourselves, and no minor upgrade (Argo CD 3.6) within WO-34.
5. **P2b (PR #56, CoreDNS and etcd):** apply the same rule. Promote a candidate only if it is a net improvement, and only at versions kubeadm v1.36 supports; otherwise keep the current pins. Attach the source-mode evidence.
6. **P3 (MiniStack 1.5.18, pause 3.10.2):**
   - finish the full scans and the regression run;
   - the reviewer's usage limit only stopped the final test command; it did not reject it, so re-run it;
   - then commit and open the PR.
7. **Deadline watch.** If any Critical exception would expire on 2026-11-12 with no fix and no not-reachable evidence, report it **by 2026-11-05**. The owner then decides on an extension, with evidence, before it expires.
