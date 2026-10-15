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

## Amendment 3 (2026-10-15, owner decision on the reachable GO-2026-6612 and the 2026-11-12 expiry)

**Owner decision (Ahmed Mazen, 2026-10-15): "accept the recommendation".** It resolves the P2 stop in draft PR #56 and the early expiry notice.

1. **Promote the improved candidates** once each is eligible and passes the supply-chain gate with no new Critical or High identity:
   Argo CD **v3.5.5** (on or after **2026-10-26**), CoreDNS **v1.14.7** and etcd **v3.6.15-0**.
   - CoreDNS and etcd are set through kubeadm's own override fields (`dns.imageTag`, `etcd.local.imageTag`) for the dev profiles only, with the digests staged in the
     bootstrap lock and the scope-B tag-only list (Amendment 13b of WO-31) updated to the new versions. Add a test that the rendered kubeadm config uses exactly these versions.
   - Live: these are owner-scheduled maintenance steps on the Dell (etcd and CoreDNS one at a time, with an etcd snapshot first). Never re-init or reset the cluster.
2. **Time-boxed risk acceptance for GO-2026-6612 / CVE-2026-78663 only** (golang.org/x/net HTTP/2 `Framer.ReadFrame`, fixed in x/net v0.60.0):
   - one exception entry per image (Argo CD, CoreDNS, etcd), class Critical, `approvedBy: amazen33`, expiry **30 days** from the merge of the promoting PR;
   - reason "reachable in source mode; no released fix; risk accepted by owner 2026-10-15";
   - controls listed in each entry and verified by tests or existing checks:
     - Argo CD is tunnel-only, with no NodePort, LoadBalancer or Ingress;
     - etcd client and peer ports are dropped at the Dell firewall;
     - CoreDNS is cluster-internal;
     - the dev environment is LAN-only.
   This acceptance does not extend to any other vulnerability.
3. **Take the fix as soon as possible.** When a release of any of the three ships x/net >= v0.60.0 and is at least 14 days old, open a refresh PR. The WO-32 weekly watch
   reports it. If the vulnerability becomes KEV-listed, the ADR-0049 expedite rule applies at once.
4. **The 76 Critical exceptions expiring 2026-11-12.** By **2026-11-05**, Codex prepares one PR that:
   - closes every exception the promotions fixed, with evidence;
   - for each Critical still open (mostly Argo CD's 22), proposes renewal individually: 30 days maximum, linked to the upstream fix release or issue, with the
     reachability result. There are no grouped or blanket renewals;
   - leaves `approvedBy` empty for the owner, who approves the list in the PR.
5. **#56 stays a draft** until the promotions in item 1 replace it. #58 continues as reviewed (pause 3.10.2; MiniStack not promoted).

## Amendment 3a (2026-10-15, architect; APPROVED by the owner 2026-10-15: "3a approved"): making the approved promotion executable

Codex's stop report (`.build/wo-34/p2-promote-stop/STOP.md`) is right: Amendment 3 approved the promotion but not the gate mechanics it needs.
The principle the owner approved still stands: **promote a candidate only if it is strictly better, and accept no new risk beyond GO-2026-6612.**

1. **Net-improvement promotion.** A candidate may replace a pinned image only if the complete comparison shows that its fixable Critical and High identities
   (vulnerability ID plus package) are a **subset** of the currently pinned image's identities. In other words, nothing new is introduced. Both CoreDNS 1.14.7 and etcd 3.6.15 meet this (CI run 38662896911).
2. **Carry existing exceptions; never extend them.** For each identity that remains, an exception that already exists for the old digest is moved to the new digest:
   - same vulnerability, same reason, same `approvedBy`;
   - the **same expiry** (2026-11-12 for the current Criticals), never extended.

   Exceptions for identities that the candidate fixes are closed with evidence. This covers CVE-2026-56857 / GO-2026-6604: it is already present and excepted on the current digests, so moving it adds no new risk.
3. **"Introduced" means a new identity, not a new digest.** In `supply_chain.py`, a finding on a changed digest counts as introduced only if its (component, package, vulnerability)
   identity did not exist on the previously pinned digest of the same component. The first-seen date carries over by identity, so the 14-day High clock is neither reset nor falsely started.
   Add tests:
   - a carried identity is not "introduced";
   - a genuinely new identity on a changed digest blocks;
   - a carried Critical without a carried exception still blocks.
4. **GO-2026-6612 entries are per image and per affected package.** Each image gets two entries, one for `golang.org/x/net` and one for `stdlib`. Each has a 30-day expiry from the merge of the promoting PR and lists the Amendment 3 controls.
   If this identity is already excepted on the old digest, carry that exception instead, using the earlier of the two expiry dates.
5. **Stop rule.** Stop and report if any candidate has an identity not present on the pinned image, or if a remaining Critical has no existing exception to carry.
6. **Prerequisite.** Start only after PR #58 is actually merged; check the merge on `main` first.
