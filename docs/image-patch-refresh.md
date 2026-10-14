# WO-34 image patch refresh

## Priority 1: console static acceptance (2026-10-14)

[PR #55](https://github.com/amazen33/twinfra/pull/55) implements [WO-34 Amendment 1](work-orders/WO-34-image-patch-refresh.md). Live acceptance is Pending.

The console digest changes from `sha256:385934466c5453902e4beda1d6ed7afb09eae6dd3419d0a7b0b219eece4cc4e2` to `sha256:ec1eebc9b51a1e7e019b501039f8c822eee5751b6322b205ec0b5eea9f30cd54`. Application source bytes stay unchanged. Python remains on 3.14 and Debian trixie. OCI title/history and builder names use Twinfra. PostgreSQL stays unchanged.

CPython 3.14.8 released **2026-09-30**; its official Docker digest published **2026-10-09**. Software release age qualifies under Amendment 1; no expedite waiver is used. Both dates are generated into the image receipt.

Complete Linux amd64 OCI archives, including the app and hash-locked wheels, were compared against one fresh Grype database. The archives reproduced both locked console digests. [Scan run 38602665963](https://github.com/amazen33/twinfra/actions/runs/38602665963).

| Image | Critical with fix | Critical without fix | High with fix | High without fix |
| --- | ---: | ---: | ---: | ---: |
| console-before | 23 | 0 | 118 | 55 |
| console-after | 0 | 0 | 0 | 55 |
| python-before | 23 | 0 | 118 | 55 |
| python-after | 0 | 0 | 0 | 55 |

**23 replaced console-base exceptions closed; 76 unrelated exceptions retain their original records and expiry dates.** The 55 High findings without fixes remain report-only. The old immutable image itself is not declared patched; retained inactive/reference Dockerfiles are unchanged.

Evidence: [static acceptance receipt](acceptance/wo34-p1-2026-10-14.json). The generated frontend archive binds the preserved compiled bytes to source hashes. The generated compressed application layer binds gzip bytes to a freshly assembled tar payload and uncompressed digest; this removes platform zlib variation while preserving image content. Corruption or changed payload fails closed. Both generators retain notices from the hash-locked wheels. They introduce no additional runtime libraries.

## Go binary tooling and independent component stops

govulncheck v1.1.4 is BSD-3-Clause, built from SHA256-pinned Go 1.27.1 SDK/module inputs. Linux binary SHA256: `f77f577722ac825bf649c24023c24af64e44c77152ab4e1778b2f8a27c2011fb`. Every Go ELF in the selected current and candidate graphs was inspected as data, never executed. [Successful all-binary run](https://github.com/amazen33/twinfra/actions/runs/38601213896). Binary mode establishes symbol presence, not runtime calls; affected symbols are conservatively reachable under WO-34.

Argo CD **3.5.5 does not clear GO-2026-6612**. The main binary still carries x/net v0.59.0 (fix v0.60.0); pebble, git-lfs, helm and kustomize also contain affected symbols. Its release is age-eligible on **2026-10-26**, but it must not be promoted then with these findings. No 3.6 move, expedite, new exception or expiry extension is made. See [Argo CD data-only report](image-patch-refresh-argocd.md).

CoreDNS 1.14.7 and etcd 3.6.15 also retain affected symbols. Their independent stop evidence is in [PR #56](https://github.com/amazen33/twinfra/pull/56); no later fixed patch eligibility date is verified. P3 proceeds independently.

## Owner actions after review

1. Claude reviews; owner approves the new console digest and merges P1 after the PR gate passes.
2. Follow [the dev runbook](dev-environment.md): fetch reviewed main, run `python tools/platform_dev.py build-images --download-inputs`, verify both receipts, then stage the reviewed archives. Default builds reuse only the source/payload-verified generated inputs and write no tracked files.
3. Verify console login, trusted HTTPS, Running/Ready pods, GitOps health and the nightly supply-chain scan. Live acceptance/tester sign-off remain Pending.
4. Kubernetes upgrade remains an owner-only `kubeadm upgrade plan`/reviewed `kubeadm upgrade apply` procedure if a future eligible 1.36 patch is promoted. Never re-run init/reset or skip a minor. Current Kubernetes remains 1.36.5.
