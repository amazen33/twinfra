# WO-40: Twinfra v0.1.0 — acceptance suite and release readiness

**Status:** Approved for implementation (owner, 2026-10-16: chose "Road A" after the release-first plan; no pause is needed between v0.1.0 and the next phase). · **Author:** Claude · **Implementer:** Codex
**Branch:** `codex/wo-40-release-0-1-0` · **Decisions:** the release-stream standard (RELEASING.md), ADR-0052 (evidence first), ADR-0049, ADR-0054 · **Owner direction (2026-10-16):** release a stable version first, then pause Twinfra; the owner then chooses between continuing Twinfra and deploying EdgePulse.

## Goal

Cut **Twinfra v0.1.0 (Stable)**: the current single-node platform on the bare-metal Dell, accepted by live evidence, with honest limits. `0.x` states that no production or high-availability profile exists. Stable here means "accepted for dev use", nothing more.

## What v0.1.0 contains (and does not)

- **Contains:** the Module -1 host and kubeadm bootstrap on Ubuntu 24.04; Cilium; Argo CD GitOps; CloudNativePG with pgvector; Keycloak; OpenBao (uninitialised, unsealed state is not claimed); the console with signed-token verification; Valkey for Argo CD; MiniStack as the *emulated* S3, EC2 and DynamoDB read views; host-network hardening; the licence, supply-chain, staging and evidence gates; release streams.
- **Does not claim:** AWS parity (all AWS APIs are Emulated or Planned), high availability, backups or disaster recovery, multi-tenancy, secrets management, observability retention, compliance or production readiness (ADR-0052).

## Scope

1. **Acceptance suite:** `python tools/platform_dev.py accept --context twinfra-dev-cairo-1`, read-only except for HTTP requests. It prints JSON and writes a receipt fragment. It checks:
   - node Ready, zone and labels; all pods Running with no restarts since the acceptance start; the three Argo CD Applications Synced and Healthy at the expected revision;
   - `host-check` and `host-network --check` pass;
   - every deployed image digest equals `deploy/common/images.lock.json` and the bootstrap lock (`stage-images --check` logic);
   - console HTTPS health through the owner's tunnel, and the **token negatives** from the WO-04 receipt: a hand-made unsigned `X-Access-Token` gets 401, a missing or duplicated header gets 401, and a roleless user gets 403 (the owner supplies the roleless test user);
   - Valkey: an unauthenticated command is rejected (`NOAUTH`), an authenticated one succeeds, and Argo CD components reconnect after a Valkey pod restart (the restart is an explicit `--with-restart` flag the owner passes);
   - a **version report** (Kubernetes, containerd, Cilium, etcd, CoreDNS, Argo CD, CNPG, PostgreSQL, Keycloak, OpenBao, Valkey, console);
   - the **exception calendar**: every open vulnerability exception with its expiry and the days left, failing if any expires within 14 days.
2. **Release readiness (one PR):**
   - `VERSION` stays `0.1.0`. `compatibility.yaml` reflects the real requirements and provides (Kubernetes 1.36.x, Cilium 1.20.x; the AWS-compatible API *emulated subset*).
   - `CHANGELOG.md`: a `[0.1.0]` section drafted from `[Unreleased]` with **Known limitations** (the list above) and the exception table.
   - `docs/release-notes/0.1.0.md`: what is included, not claimed, how to install and update, and the upgrade path to 0.2.0.
   - The `vCloud PR gate` also runs on `release/**` (RELEASING.md requires this before the first release branch).
   - README "Current capability and readiness" names v0.1.0 and lists the Dev-verified items with links.
3. **Consolidated receipt** `docs/acceptance/release-0.1.0-<date>.md`: the acceptance output, links to the individual receipts (WO-31, WO-04, WO-06, WO-25, WO-34 P1 to P3, WO-36, WO-36a, WO-37), the exception calendar, and the tester sign-off Pending.
4. **Close the Pending live items** that the suite proves, by listing for the owner exactly which receipts to sign (WO-04, WO-06, WO-25, WO-31). Receipts are never edited by Codex.
5. **No runtime change.** The suite and the documents are the only deliverables.

## Dated items that belong to the release (Codex tasks, kept short)

- **Argo CD 3.5.5** (on or after 2026-10-26): its own small PR (admission: the toolchain-wave rule), then the owner applies it. It removes the four critical Argo CD advisories from the stable.
- **Renewal PR** for the Criticals expiring 2026-11-12, prepared by 2026-11-02 so the stable does not ship with exceptions that lapse within days. Individual proposals, 30 days each, `approvedBy` left for the owner.
- The CoreDNS 1.14.7, etcd 3.6.15 and pause 3.10.2 maintenance is **optional** in the window; the release notes say what is actually running.

## Owner actions, in order

1. Merge PR #66 (WO-36 sign-off).
2. Run `accept` on the Dell, sign the receipts it proves, and sign the consolidated receipt.
3. Apply Argo CD 3.5.5 after its PR merges.
4. Cut `release: 0.1.0-rc.1`, create `release/0.1`, push the tag `v0.1.0-rc.1`. Run the acceptance window (pin the platform Application `targetRevision` to the tag for at least 48 hours, run `accept` again, then set it back to `main`).
5. Tag `v0.1.0` on the same commit, then publish the draft release. I will give the exact commands at each step.

## Acceptance criteria

- The PR gate is green, including the new `release/**` coverage, `staging-check` and the historical baselines.
- `accept` passes on `cairo-1`. The consolidated receipt is signed Accepted.
- The v0.1.0 release contains `platform-images.lock.json`, `console-image.lock.json`, `licence-register.json`, `compatibility.yaml` and `SHA256SUMS`.

## After v0.1.0: Road A (owner decision, 2026-10-16)

Twinfra continues with Foundation 1.0 and the walking skeleton (see `ROADMAP.md`). EdgePulse hosting (WO-39 and IOT-WO-04 Amendment 2) stays prepared but waits until the owner calls it. The foundation work may be developed on branches during the release window, but **nothing merges to `main` between the last release-readiness PR and the cut of `release/0.1`**.

## Report back

The suite's checks and their output format, the release documents, and CI.

## Amendment 1 (2026-10-16, architect): resolves Codex's stop on the release/** scan, Argo CD 3.5.3 and the exception calendar

Codex found three problems. Adding `release/**` to the PR gate triggers a full supply-chain scan; Argo CD 3.5.3 carries CVE-2026-77459 (Critical, CVSS 9.9, fixed in 3.5.4; an AppProject bypass for PostDelete hooks that needs **Git write access to an Application's repository**), which has no exception; and exceptions expiring on 2026-11-12 would fail `accept` from 2026-10-29 under a 14-day threshold.

1. **Split WO-40 into two PRs.**
   - **WO-40a (now, must be green):** the `accept` suite and its tests, the consolidated receipt template, the README and `docs/capabilities.md` updates (WO-36 and WO-36a are now Dev-verified: the receipts are signed Accepted on `main`), and a CHANGELOG entry. **No workflow change.**
   - **WO-40b (after the Argo CD promotion and the renewal PR, about 2026-10-31):** `release/**` coverage in the PR gate, the `[0.1.0]` CHANGELOG section, release notes, `compatibility.yaml`, `VERSION`. This is the last PR before the release freeze.
2. **A tiny interim exception PR first (WO-34e)**, because the same finding also blocks PR #67 and the Argo CD 3.5.5 admission.
   - Codex runs the full scan on `main` and prepares **one entry per image and per CVE** for every Argo CD 3.5.3 finding that the full scan blocks and that is fixed by 3.5.4 or 3.5.5. CVE-2026-77459 is certainly one. Critical entries expire **2026-11-02**; High entries expire no later than 2026-11-02 either.
   - Controls in each entry: the Application repositories are owner-only (AppProject `sourceRepos`); every change to those repositories merges only after the owner's review; Argo CD is tunnel-only; refresh = the Argo CD 3.5.5 promotion (WO-34).
   - `approvedBy` is set to `amazen33` only after the owner approves in chat. Any non-Argo finding that blocks stops the PR for the owner. No other exception is created.
3. **`accept` calendar thresholds:** fail if an exception is expired or expires within **7 days**; warn within **21 days**; print every exception with its days left.
4. **Dates, in order:**
   - 10-26 to 10-28: Argo CD 3.5.5 PR (toolchain-wave rule, PR #67 must be merged first), then the owner stages and applies it.
   - by 10-29: renewal PR for the Criticals that remain open, merged by 10-30, so the calendar is clean before the release.
   - by 10-31: WO-40b merged. Freeze `main`.
   - about 11-02: cut `release/0.1`, tag `v0.1.0-rc.1`; 48-hour acceptance window; about 11-09: `v0.1.0`.
5. PR #67 (WO-09a) stays as is. It merges after WO-34e is green and rebased, and before the Argo CD 3.5.5 PR.
