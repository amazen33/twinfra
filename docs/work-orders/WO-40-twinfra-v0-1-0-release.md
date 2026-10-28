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
- ~~The CoreDNS 1.14.7, etcd 3.6.15 and pause 3.10.2 maintenance is optional in the window.~~ **Superseded by Amendment 2:** the etcd and CoreDNS maintenance is mandatory before the baseline `accept`; the release notes say what is actually running.

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

## Amendment 2 (2026-10-17, architect): the first baseline `accept` failed; the etcd and CoreDNS maintenance is mandatory, not optional

**Finding (owner's run, 2026-10-17 00:27 UTC, 8 seconds).** Passed: exception calendar (2 warnings: the two interim Argo CD 3.5.3 exceptions, 16 days left), node, initial pods, GitOps (all applications at `b4c70e8`), `host-check`, `host-network`, `images.lock.json` (10 of 10). **Failed: `staging:bootstrap-images.lock.json`.** The read-only re-check names two images: `etcd:3.6.15-0` and `coredns:v1.14.7` are in the lock (WO-34 P2, promoted 2026-10-15) but are not staged on the Dell. The cluster still runs etcd `3.6.8-0` and CoreDNS `v1.14.2` (read from the pods). The suite stopped there, so the console, token, Valkey and restart checks are unproven.

**My error.** Amendment 1's text above and the "Dated items" list said this maintenance is optional in the window. That is wrong: `accept` compares every running image with the lock, so the baseline cannot pass while the lock and the node disagree. The check is right and is not weakened. The alternative (reverting the promotion in the lock) would discard an approved, net-improving change (WO-34 Amendment 3 and 3a), so it is rejected.

**Decision.** Do the maintenance that WO-34 Amendment 3 item 1 already approved and `docs/image-patch-refresh-p2.md` already outlines, **before** the baseline, one component at a time, never `kubeadm init`, `reset` or a full bootstrap rerun.

1. **WO-40c (Codex, one small PR, no live action).** Turn the outline into an exact, reviewed, copy-paste runbook plus a generator, in `docs/maintenance/` and `tools/`:
   - read-only preflight (versions, `kubectl get --raw=/readyz`, etcd health, free disk, current manifests and `kubeadm-config`);
   - backups outside Git: the four static Pod manifests, the `kubeadm-config` ConfigMap, and a **verified etcd snapshot** (`etcdctl snapshot save`, then `etcdutl snapshot status`), kept on the Dell and copied to the laptop;
   - staging with `stage-images.py --lock deploy/common/bootstrap-images.lock.json`, then `--check` (this part is safe to run first);
   - a script that reads the live `kubeadm-config` and writes the v1beta4 `UpgradeConfiguration` changing **only** `dns.imageTag` and `etcd.local.imageTag`, with a diff the owner reviews;
   - dry run, then etcd, then verify (etcd health, API ready, WAL latency, `Ready` node), then CoreDNS addon phase, then verify (DNS from a permitted workload, Cilium policy, GitOps healthy, pinned images);
   - a rollback section per component (restore the saved manifest or the previous ConfigMap value; an etcd snapshot restore is the last resort and needs the owner);
   - tests that the generated configuration changes exactly those two tags.
   - **Stop rule:** if the pinned kubeadm cannot apply a same-version etcd or addon image change through `upgrade apply phase`, stop and report. Do not improvise by editing manifests live; the fallback (edit the etcd static Pod image and the CoreDNS Deployment, with `kubeadm-config` updated to match) needs my review first.
2. **Owner maintenance window** (about 30 minutes, after WO-40c merges). Expect the API to be unreachable for about a minute while etcd restarts; running pods keep running. Nothing else changes. The owner pastes the check outputs and I review them between the two components.
3. **Then the baseline again:** `run-acceptance.ps1` (it now reads the commit without `git`). The sign-offs for WO-04, WO-06, WO-25, WO-31, the WO-34 P2 live receipt and the consolidated receipt follow the green run.
4. **Dates:** WO-40c PR by 2026-10-19; maintenance window and baseline by 2026-10-22, so Argo CD 3.5.5 (from 2026-10-26) reuses the same staging step. The 2026-10-31 and 2026-11-02 dates are unchanged.

## Amendment 3 (2026-10-17, architect): WO-40c mechanism corrected after Codex's stop (kubeadm v1.36.5 source)

Codex verified against the v1.36.5 source and stopped correctly: `UpgradeConfiguration` has no `dns.imageTag` or `etcd.local.imageTag` (they belong to `ClusterConfiguration`), the upgrade loader ignores supplied `ClusterConfiguration` documents, and `upgrade apply` reads the stored `kube-system/kubeadm-config`. **My Amendment 2 item 1 (the `UpgradeConfiguration` generator and the `upgrade apply phase` steps) is superseded by this amendment; its other parts (preflight, backups, staging, verification, rollback, dates) stand.** The error was mine.

**Mechanism: kubeadm's documented reconfiguration route, one component at a time.** The stored `ClusterConfiguration` holds the intended tags; the node manifest and the CoreDNS Deployment are re-rendered from a candidate configuration. `upgrade apply` is not used, because it re-renders every control-plane component and needs a version argument.

1. **Base configuration.** Locate the configuration file the bootstrap used on the Dell (WO-31's state directory, `kubeadm.yaml` and its patches directory, which carry the read-only etcd certificate mount and the other approved patches). Compare it with the `ClusterConfiguration` in `kube-system/kubeadm-config`. **They must agree on everything except possibly the two tags; otherwise stop and report the differences.**
2. **Generator (tools/, with tests).** Reads that configuration and writes a candidate that changes **only** `dns.imageTag` (to `v1.14.7`) and `etcd.local.imageTag` (to `3.6.15-0`), prints the diff, and refuses any other difference. It also writes the candidate `ClusterConfiguration` document for the ConfigMap.
3. **Previews, without touching the cluster.** `kubeadm init phase etcd local --config <candidate> --dry-run` (the cairo-2 seed already does this) and `kubeadm init phase addon coredns --config <candidate> --dry-run`. Acceptance for each preview, by diff against what is live:
   - etcd: the rendered manifest differs from `/etc/kubernetes/manifests/etcd.yaml` **only in the image**; the patched read-only certificate mount, flags, data directory and node name are unchanged;
   - CoreDNS: the Deployment differs only in the image, and the `coredns` ConfigMap (Corefile) is not changed by the phase.
4. **Apply order and ConfigMap timing.** The ConfigMap is updated **after** each component is verified, never before, so a failure leaves the stored configuration matching the running state.
   - etcd: `kubeadm init phase etcd local --config <candidate>` (writes only the etcd manifest; the kubelet restarts the static Pod), then verify (etcd health, `readyz`, the new image digest in the Pod, WAL latency, `Ready` node), then update the ConfigMap's `etcd.local.imageTag` from the saved candidate.
   - CoreDNS: if the preview in item 3 shows an image-only change, run `kubeadm init phase addon coredns --config <candidate>`. **If the phase would change the Corefile or anything else, use the pre-approved fallback for CoreDNS only:** `kubectl -n kube-system set image deployment/coredns coredns=<pinned digest reference from the lock>`, which leaves the ConfigMap untouched. Verify DNS from a permitted workload, Cilium policies and GitOps health; then update `dns.imageTag` in the ConfigMap.
   - **etcd has no fallback.** If the etcd preview shows any difference beyond the image, stop and report.
5. **Rollback.** Per component: restore the saved manifest or the previous Deployment image, and leave the ConfigMap unchanged (it was not yet updated); an etcd snapshot restore is the last resort and needs the owner.
6. **Unchanged:** staging first (`stage-images.py --lock deploy/common/bootstrap-images.lock.json`, then `--check`), a verified etcd snapshot and manifest backups before etcd, and the dates in Amendment 2. Never `kubeadm init`, `reset`, `upgrade apply`, or a full host-bootstrap rerun.

## Amendment 4 (2026-10-17, architect): review of PR #70 (WO-40c), changes requested

PR #70 is careful work: CAS-guarded ConfigMap patches, a strict etcd image-only guard proven with the pinned kubeadm in CI, new-only private outputs, and an honest list of unverified points. Four defects would stop or mislead the live window, and three smaller items should be fixed in the same push.

**Blocking**

1. **The strict host/stored comparison will stop every time.** `render_kubeadm` in `00-setup-ubuntu-host.sh` writes a minimal `ClusterConfiguration`. kubeadm's upload-config stores the *defaulted* object (for example `certificatesDir`, `etcd.local.dataDir`, `encryptionAlgorithm`, the certificate validity periods, empty component sections). Comparing raw files therefore always reports drift, which is exactly what `test_even_materialized_default_difference_is_not_silently_ignored` asserts. My Amendment 3 item 1 caused this; it is corrected here:
   - Normalise **both** sides with the pinned kubeadm's own defaulting, offline: the `ClusterConfiguration` document of `kubeadm config migrate --old-config <file>` for the host file and for the stored document. Then compare strictly; only the two tags may differ. Any other remaining difference stops the window, and the owner pastes the diff for my decision.
   - Verify from the v1.36.5 source (cite it) that `config migrate` applies the same static and dynamic defaults to `ClusterConfiguration` as init's upload-config. **CI proof:** the cairo-1 render, migrated, equals the `ClusterConfiguration` that `kubeadm init --dry-run` would upload, apart from the two tags. If that cannot be shown, stop and report.
   - The migrate output may contain a generated bootstrap token. It is used only for the comparison, never applied, and deleted at cleanup.
   - The etcd image-only manifest diff remains the binding gate for etcd.
2. **The CoreDNS fallback image breaks acceptance.** `image coredns --digest` sets `…/coredns@sha256:…`. `platform_accept.image_problems` allows only `cri_reference(canonical)`, which for CoreDNS is the **tag** form `registry.twinfra.example.com/registry.k8s.io/coredns:v1.14.7`. A digest reference would be reported as "unverified image". It also has no staged digest-only containerd record, so the kubelet may try to pull it from the non-existent dev registry. Fix: the fallback uses the canonical tag exactly as kubeadm renders it (staged, pinned and digest-verified by `stage-images` and `accept`); the documented `jq` assertion accepts only that form; add a test that the fallback reference is in `accept`'s allowed set.
3. **Dell `kubectl` has no kubeconfig for the operator.** The bootstrap uses `KUBECONFIG=/etc/kubernetes/admin.conf` (root, 0600), and the repository's Dell procedures use `sudo kubectl --kubeconfig /etc/kubernetes/admin.conf` (`docs/service-access.md`, `docs/dev-environment.md`). The runbook's bare `kubectl` commands would fail at the first preflight call. Use that form throughout on the Dell, and `sudo env KUBECONFIG=/etc/kubernetes/admin.conf cilium status --wait` for Cilium.
4. **The step after the etcd apply would trigger a needless rollback.** While etcd restarts, the API is down, so `kubectl wait` fails at once with "connection refused", and the runbook says to stop and roll back. First wait, with a bound, for `readyz` (for example `timeout 300 bash -c 'until sudo kubectl --kubeconfig /etc/kubernetes/admin.conf get --raw=/readyz >/dev/null 2>&1; do sleep 5; done'`). Then do the Pod-level checks. State that one kube-apiserver restart during the etcd restart is expected, not a failure.

**Also fix**

5. **CoreDNS: one mutation only.** A live Deployment carries server-side defaults, so a strict diff against kubeadm's template can never be image-only. The phase path is therefore unreachable, and it invites a judgement call in the window. CoreDNS uses only the `set image` fallback with the canonical tag. Remove the CoreDNS dry-run, which also removes the copy of `admin.conf` into the maintenance directory.
6. **WAL threshold.** The gate is WO-31's target, p99 under 10 ms. Report the value against the 2026-10-13 baseline (p99 at most 4 ms). A value between 4 and 10 ms is reported, not a stop.
7. **Cleanup and laptop commit.**
   - Add a cleanup section that runs after `accept` passes: remove `/var/lib/etcd/wo40c-before.db` from the etcd data directory (the copies in `$MAINT` and on the laptop remain), and delete the migrate outputs.
   - Old images stay cached until acceptance.
   - On the laptop, `git` is not on the owner's PATH: read the commit from `.git/HEAD`, as `run-acceptance.ps1` does.
   - CI also runs `kubeadm config validate` and the etcd dry run on the exact `candidate.yaml` the generator writes (JSON documents separated by `---`), not only on the YAML re-dump.

The stop rules, CAS patches, no-fallback rule for etcd, backups and dates stand.

## Amendment 5 (2026-10-17, architect): live maintenance result and one generator defect

**Live result (owner, 2026-10-17, through the owner-private wrapper of the reviewed runbook).** Backups and the verified snapshot (revision 988107) are on the Dell and the laptop with matching hashes. The two images were staged (11 of 11). The migrated host and stored configurations agreed apart from the tags, and the etcd preview was image-only. etcd runs 3.6.15-0 with the locked digest: healthy, WAL p99 at most 4 ms over 1,224 samples. CoreDNS runs v1.14.7 with the locked digest; the Corefile is unchanged, DNS resolves from the console, and Cilium and Argo CD are healthy. Both tags are recorded in `kubeadm-config`.

**Defect (WO-40c generator; missed in my review of PR #70).** `control_plane_candidate.py` writes the ConfigMap's `ClusterConfiguration` as **JSON** text. kubeadm writes YAML, and the WO-31 host check (`host-admin.py` `config_value`) reads `clusterName:` and `controlPlaneEndpoint:` line by line. After the patches, `host-check` blocks with "bootstrap identity/version/listener verification failed", and `host-network` refuses with "requires identity-verified ready WO-31 host". The live ConfigMap was restored to kubeadm's YAML format, with identical content, by a compare-and-swap patch (the saved original YAML plus the two tags).

**Codex follow-up (small PR, WO-40d):**
- The generator writes YAML in kubeadm's format (sorted keys, as uploaded), never JSON.
- A test runs `host-admin.config_value` on every generated ConfigMap value, so both identity keys resolve.
- The rollback patches are regenerated to match.
- Add the live result above to the runbook's record, without editing any receipt.

## Amendment 6 (2026-10-17, architect): the acceptance suite aborts on locally built images; WO-40d scope

**Third baseline run (05:38 UTC, `b92dd20`).** Passed: calendar (2 warnings), node, initial pods, GitOps, `host-check`, `host-network`, both staging locks. Then the run aborted inside `cri_identities`, before `deployedImages`.

**Cause (reproduced read-only).** For `twinfra-console` and `twinfra-postgres` (locally built, imported by `stage_applications` with `ctr images import --digests`), the kubelet reports `imageID` as `docker.io/library/import-2026-10-15@sha256:ec1eebc9…` and `docker.io/library/import-2026-10-13@sha256:baea2bf7…`. Those temporary import names no longer exist in containerd, so `crictl inspecti` exits non-zero, `SSH.run` raises, and the whole suite stops. The reported digests are **exactly the locked digests**, and `image_problems` returns **no problems** with the same data. The platform is correct; the suite's lookup is unnecessary and fragile.

**WO-40d (one small Codex PR, no live action) now contains:**
1. **Suite fix (`platform_accept.py`).**
   - `cri_identities` looks up a runtime reference only when its digest is not the locked digest of the canonical reference that container runs. A reference whose digest equals the lock is verified by digest, as `runtime_matches` already does first.
   - A lookup that still fails becomes a recorded `deployedImages` problem for that container, never an exception that aborts the run.
   - Tests: an imported image whose `import-*` name is gone passes when its digest matches; a digest mismatch whose lookup fails is reported as a problem; the suite still never prints command output.
2. **Generator fix (Amendment 5).** YAML in kubeadm's format, the `config_value` test, regenerated rollback patches.
3. **Report only, no change:** whether `stage_applications` (or anything else) removes the `import-*` digest names after tagging, and whether `--digests` is still needed. Any change to import naming waits for my review.

Then the owner updates `E:\twinfra-live` to the merge commit and reruns `run-acceptance.ps1`.

## Amendment 7 (2026-10-17, architect): PR #71 (WO-40d) approved; import aliases

- **PR #71 at `0472810` is approved for the owner's merge.**
  - **Suite:** a runtime reference whose digest equals the locked digest is no longer looked up. A failed canonical or runtime lookup is recorded as a sanitized `deployedImages` problem. A canonical mismatch, which used to abort the run, now fails the check instead; that is stricter, not weaker.
  - **Generator:** sorted YAML for every ConfigMap value, including rollbacks, with a `config_value` test.
- **`ctr images import --digests`:** Codex's source analysis says the date-based aliases are unnecessary for fully named archives. **No change during the release window.** Removing the flag is a post-v0.1.0 item, bundled with the next image refresh and proven by a live import test.
- **What removed the two aliases on the Dell stays unknown.** It is investigated read-only only if it happens again. Canonical names remain protected by the staging check on every `accept` run.

## Amendment 8 (2026-10-17, architect): fifth baseline; WO-40e (versions step)

**Run at 15:03 UTC on `d9c81f2`.** Every acceptance check passed:
- calendar (2 warnings), node, pods, GitOps, `host-check`, `host-network`, both staging locks;
- `deployedImages` (0 problems);
- `consoleHTTPS`;
- `tokenNegatives` (401, 401, 401, 403);
- `valkey` (authentication enforced; all three Argo CD clients connected).

The run then aborted in the informational `versions` step. Owner-side fixes made this run possible: a hidden console tunnel with an end-to-end probe, and a forced Keycloak login for the roleless user.

**Cause (reproduced read-only).** `versions()` requires exactly one Pod per component. CoreDNS runs two replicas (`k8s-app=kube-dns`), so it raises "ambiguous". Every other probe succeeds:

| Component | Version |
|---|---|
| Cilium | 1.20.2 |
| etcd | 3.6.15 |
| CoreDNS | 1.14.7 |
| Argo CD | v3.5.3 |
| CNPG | 1.30.1 |
| PostgreSQL | 18.6 |
| Keycloak | 26.8.0 |
| OpenBao | v2.7.1 |
| Valkey | 8.1.10 |

**WO-40e (one tiny Codex PR, no live action):**
1. For a component with several replicas, query **every** matching Ready Pod and require them to report the same version. Record it once; disagreement is a failure.
2. A version probe that fails becomes a recorded, sanitized `versions` check failure, never an exception that aborts the run. The remaining steps (the restart test, the final checks) still run.
3. Tests: two CoreDNS replicas with equal versions pass, unequal versions fail, a failing exec is recorded and does not abort, and no command output is serialized.

## Amendment 9 (2026-10-17, architect): PR #72 (WO-40e) approved

PR #72 at `fab16e0` is approved for the owner's merge.
- **Versions:** every Ready replica is queried, and the versions must agree.
- **Receipt content:** only the parsed version string is recorded, never command output.
- **Failures:** a failed or unequal probe becomes a `versions` check failure instead of an abort.
- **Restart test:** an informational `versions` failure does not block the explicitly authorized restart test. Health, security and image failures still refuse it.
- **Regex:** checked against the live outputs from the fifth run (Cilium, etcd, CoreDNS, Argo CD, CNPG, PostgreSQL, Keycloak, OpenBao, Valkey). Each yields the right version.

Next:
1. The owner merges, updates `E:\twinfra-live` (Copilot prompt C2), and waits for Argo CD to sync.
2. The owner runs the full pass with the restart test: `run-acceptance.ps1 -WithRestart`.

## Amendment 10 (2026-10-28, architect): the October security wave; R1 and R2 become one PR (R12)

### Facts

Source: nightly run 40659063932 (2026-10-28), its artifact and `security/vulnerability-exceptions.json` on `main` (`0d95007`).

- **374 findings now block,** not the 6 reported on 10-26. On 10-27, 367 High findings crossed ADR-0049's 14-day rule; all were first seen on 10-13. The rest are 5 Critical findings with a fix, and 2 KEV findings.
- **The seven Critical and KEV records:**

  | Image or lockfile | Package | Advisory | Why it blocks | Fixed in |
  | --- | --- | --- | --- | --- |
  | Keycloak | `ca-certificates` (RPM) | CVE-2026-114406 | Critical | 2026.2.92 |
  | MiniStack | `brotli-libs` | CVE-2026-111497 | KEV | 1.2.1-r0 |
  | MiniStack | `certifi` | GHSA-6q48-6c7w-9gw2 | Critical | 2026.10.18 |
  | Argo CD | `libbrotli1` | CVE-2026-111497 | KEV (Medium) | 1.2.0-3ubuntu0.1 |
  | `module-5a/requirements-runtime.lock.txt` | `certifi` | GHSA-6q48-6c7w-9gw2 | Critical | 2026.10.18 |
  | `tools/ci/rag-requirements.txt` | `certifi` | GHSA-6q48-6c7w-9gw2 | Critical | 2026.10.18 |
  | `tools/ci/mermaid/package-lock.json` | `dompurify` | CVE-2026-116804 | Critical | 3.4.17 |

  **Four of the seven are the eMudhra CA compromise:** the `certifi` and `ca-certificates` bundles still trust the roots whose intermediate keys leaked. It is the same incident as Cloudflare's 10-20 advisory.
- **The 367 Highs by image:**

  | Image | Highs |
  | --- | ---: |
  | Argo CD | 148 |
  | Cilium | 37 |
  | kube-apiserver, kube-controller-manager, kube-scheduler, CoreDNS | 22 each |
  | operator-generic | 19 |
  | etcd | 15 |
  | cilium-envoy | 15 |
  | OpenBao | 14 |
  | CNPG | 13 |
  | APISIX | 8 |
  | Keycloak | 6 |
  | MiniStack | 3 |
  | Valkey | 1 |

  - Most are the Go standard library and `golang.org/x/*`.
  - The rest do not qualify as toolchain-wave findings: grpc, the etcd client, the OpenTelemetry SDK, and OS packages (perl-base, pcre2, zlib, OpenSSL, Python).
- **Existing exceptions:**
  - 60 Critical entries expire on **2026-11-12**. From 11-05 they fall inside the acceptance suite's 7-day failure window, which is during the rc window and before stable.
  - The 2 interim Argo CD entries expire on **2026-11-02**. `accept` has failed on them since 10-26.
- **`main` has not moved since 10-19.** R1 (due 10-26) was not sent.
- **Upstream releases:**

  | Component | Release | Published | Eligible under the 14-day rule |
  | --- | --- | --- | --- |
  | Argo CD | 3.5.5 | 10-12 | Now |
  | Argo CD | 3.5.6 | 10-20 | 11-03 |
  | Keycloak | 26.8.1 | 10-13 | Now |
  | MiniStack | 1.5.33 | 10-26 | Under the KEV expedite rule only |
  | Kubernetes | 1.36.6 | 10-28 | 11-11 |
  | Cilium | 1.20.4 | 10-23 | 11-06 |

### Why one PR

When the exception policy changes, the PR gate scans **all** inputs (`pr-tests.yaml`). An Argo CD-only PR therefore can't pass while 374 findings block. R2 on its own would also write 148 Argo CD entries that R1 then closes. One PR dispositions everything once.

### Decisions

1. **R12 replaces R1 and R2.** Its prompt is in `CODEX-PROMPTS.md`. R3b follows R12 unchanged.
2. **Scope control: only three images change before v0.1.0.**
   - **Argo CD**, as planned.
   - **MiniStack and Keycloak**, because their Critical and KEV findings force it.
   - **Everything else** is covered by an exception under the existing rules and refreshed after the release by **WO-46**.
   - **No Kubernetes, Cilium, etcd or CoreDNS change before the release.** Each would be a live maintenance inside the freeze.
3. **The KEV expedite rule** (ADR-0049) admits a MiniStack or Argo CD release younger than 14 days, but only if:
   - it fixes the brotli KEV;
   - it passes the net-improvement rule (WO-34 Amendment 3a): its fixable Critical and High identities are a subset of the current image's.
4. **Highs:**
   - Findings that qualify under ADR-0049 Amendment 1/1a get **per-image, per-CVE** entries, 60 days at most.
   - Findings that don't qualify are **grouped per image and package**, 60 days at most, with the reason "fixed by WO-46". ADR-0049 allows grouping only for a named remediation work order.
5. **The 60 Critical entries expiring 11-12:**
   - Close each one a promotion fixes, with evidence.
   - Renew any that remain **individually**, for 30 days at most, with the upstream fix reference and the reachability result.
6. **Calendar:** after R12 merges, no exception has expired, and none falls within 7 days of any date up to **2026-11-16**.
7. **Dates:**
   - R12 should merge by **10-30**.
   - The owner stages the images, merges and runs `run-acceptance.ps1 -WithRestart`.
   - Then R3b by 10-31, the freeze, rc.1 around 11-02 and stable around 11-09.
   - If R12 merges later, every later date moves by the same number of days.
   - The Argo CD promotion must be live **before 11-02**, when the two interim entries expire.

### Owner decisions

- **O-1: APPROVED by the owner, 2026-10-28 ("O-1 approved").** Waive the 14-day cooling-off for four fixes. Architect's recommendation: **yes**. They only remove compromised CA roots, or patch a CI-only tool or a disabled module.
  - `certifi` ≥ 2026.10.18 in the two Python lockfiles;
  - DOMPurify 3.4.17 in the Mermaid build tool;
  - the `certifi` fix inside MiniStack;
  - a Keycloak image whose only change is the CA-bundle fix, if one appears.
- **O-2:** approve the exception rows in the R12 PR, as always (`approvedBy` stays empty until then).
- **O-3: APPROVED by the owner, 2026-10-28 ("accept your recommendations").** The date rule in decision 7.

## Amendment 10a (2026-10-28, architect): the Argo CD brotli KEV that no release fixes yet

**Codex's stop report** (branch `codex/security-wave-2026-10`, diagnostic commit `de5e466`, comparison runs 40754061462) is right.

| Candidate | Fixable Critical/High, before → after | Result |
| --- | --- | --- |
| Argo CD 3.5.5 | 23/152 → 22/144 | Net improvement passes. `libbrotli1 1.2.0-3build1` (KEV CVE-2026-111497) remains. |
| Argo CD 3.5.6 | 23/152 → 22/143 | Same KEV remains. The expedite rule therefore doesn't apply, and it isn't eligible until 11-03. |
| MiniStack 1.5.33 | 3/6 → 0/0 | Removes the KEV and the `certifi` Critical. |
| Keycloak 26.8.1 | 1/7 → 0/1 | Fixes the eMudhra CA Critical. One Guava High remains. |

No upstream Argo CD image contains the fixed Ubuntu package (`1.2.0-3ubuntu0.1`). R12 authorised no exception for a KEV, so Codex correctly stopped.

### Decisions

1. **Promote Argo CD 3.5.5.** It is eligible under the normal 14-day rule, passes the net-improvement rule and removes 9 identities. Version 3.5.6 is not admissible: the expedite rule needs a release that fixes the KEV.
2. **Promote MiniStack 1.5.33** under the KEV expedite rule, and **Keycloak 26.8.1** (O-1 covers the CA fix).
   - Keycloak's remaining Guava High is handled under R12 item 5b: grouped, "fixed by WO-46".
   - That holds only if Guava is in 26.8.0 too. If 26.8.1 introduces it, the net-improvement rule fails: stop and report.
3. **The Argo CD brotli KEV gets one individual, short exception, proposed for owner decision O-4.**
   - **Expiry: 14 days** from the R12 merge. ADR-0049 would allow 90 days for a Medium; the KEV listing is the reason for the shorter term. **Superseded by Amendment 10b: merge date + 25 days.**
   - **Reason:** "no upstream Argo CD image contains libbrotli1 ≥ 1.2.0-3ubuntu0.1; fixed by WO-46 item 4".
   - **Reachability, which Codex verifies and records in the entry with evidence:**
     - which binaries in the image link `libbrotlidec`;
     - whether any Argo CD process uses them.
     
     The expected path is libcurl inside `git` and `helm` in `argocd-repo-server`. The Go binaries don't use the system library.
   - **Controls on `main`:**
     - Repo-server egress is limited by Cilium FQDN policy to `github.com:443`, so a malicious brotli stream needs a forged TLS response from GitHub.
     - The Argo CD server's ingress allows only the `host`, `remote-node` and `health` entities on 8080. It is not routed through the gateway or exposed beyond the node.
   - **Replacement duty:** WO-46 item 4 now includes promoting the first Argo CD release whose image carries the fixed `libbrotli1`. It is promoted **at once, under the KEV expedite rule**, without waiting 14 days. The weekly watch reports it.
   - **Renewal:** only by a new owner decision, 14 days at a time, with the watch evidence that no fixed image exists.
4. **Rejected: a Twinfra-patched Argo CD image** (`apt-get` upgrade on top of the upstream digest).
   - ADR-0049 Amendment 1 item 5 requires a separate, owner-approved, reproducible rebuild work order.
   - The nightly gate scans only the pinned inputs of locally built images, so it would still report the upstream base, and the KEV would stay visible.
   - It would also add a new build and publish path inside the freeze week.
5. **Everything else in R12 is unchanged.** The PR proposes the KEV row with `approvedBy` empty, and the owner decides O-4 in the PR together with O-2.

### Owner decision

- **O-4: APPROVED in principle by the owner, 2026-10-28 ("accept your recommendations").** Accept the 14-day individual exception for the Argo CD brotli KEV, on the controls above. Architect's recommendation: **accept**.
  - The row's `approvedBy` is still filled only when the owner approves the R12 exception batch in the PR (O-2).
  - The approval holds only if Codex's reachability evidence matches the controls above.

## Amendment 10b (2026-10-28, architect): the KEV exception's expiry versus the release calendar

**Codex's question is right: two of the architect's own requirements conflict.**
- Amendment 10a set a 14-day expiry. For a 10-30 merge, that is **11-13**.
- R12 item 8 requires no exception to be expired, or within 7 days of expiring, at any date through **11-16** (the stable target 11-09 plus a week of margin). That needs an expiry of **11-24 or later**.
- `accept` fails on any entry within 7 days of expiry. A 14-day term would therefore fail the acceptance suite from **11-06**, inside the release window.

### Resolution

1. **Expiry = R12 merge date + 25 days.** For a 10-30 merge, that is **2026-11-24**. It is the earliest date that keeps the release window clear.
   - It stays under the 30-day Critical maximum, stricter than the 90 days ADR-0049 allows for a Medium.
   - If R12 merges later, the expiry moves with it, like every date under O-3.
2. **R12 item 8 and the acceptance gate are unchanged.** The calendar is not weakened, and nothing extends any other row.
3. **The KEV's short leash is kept by duties, not by the expiry date:**
   - **Immediate replacement (WO-46 item 4):** the first Argo CD image with the fixed `libbrotli1` is promoted under the KEV expedite rule.
   - **Every weekly watch** reports whether such an image exists.
   - **Checkpoint on 2026-11-13,** the original 14-day mark. The architect reports the watch evidence.
     - If a fixed image exists before stable, the owner chooses: promote it before stable, which needs a new release candidate, or promote it immediately after the stable cut.
     - Either way, the exception is closed by that promotion, not renewed.
4. **Owner confirmation (O-4b):** the owner confirms the 25-day term when approving the R12 exception batch in the PR (O-2). Codex proposes the row with this expiry and `approvedBy` empty.

## Amendment 10c (2026-10-28, architect): ADR-0054 admission for the three patched components

**Codex's stop is right.** ADR-0054's gate requires full enterprise-grade records for any changed legacy entry, and R12 changes three of them:
- MiniStack 1.5.33, which declares Beta;
- `certifi`;
- DOMPurify.

Neither O-1 nor O-2/O-4b changes ADR-0054.

**Resolution:** [ADR-0054 Amendment 1](../adr/amendments/0054-amendment-1-security-fix-carry-forward.md), security-fix carry-forward (owner decision **O-5**). Under it:
- each record moves to the patched version with its **original backfill due date unchanged**;
- the licence is re-verified from the primary source;
- the tier is unchanged;
- the net-improvement rule passes;
- the owner approves each carry-forward in the PR.

The two modelling issues it records (CI-only and disabled-module components treated as runtime, and the `OR` tier) are post-release follow-ups. They do not block R12.
  - The running Argo CD 3.5.3 already carries the same package, so promoting 3.5.5 adds no risk and removes 9 other identities.
  - The alternative is holding v0.1.0 until upstream ships a fixed image, on an unknown date.
