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
