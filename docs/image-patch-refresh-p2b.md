# WO-34 P2b: CoreDNS and etcd data-only triage

Date: 2026-10-14. Static only; no image promotion, lock change, staging or live action.
[WO-34 Amendment 1](https://github.com/amazen33/twinfra/pull/55) permits each blocked component to stop independently.

## Result

Both components are blocked. The newest published patches on the supported pinned minors still contain affected symbols for [GO-2026-6612](https://pkg.go.dev/vuln/GO-2026-6612).
No fixed later patch or eligibility date has been verified. The dates below show when the tested patches became eligible; age alone does not permit promotion of an affected image.

| Component | Current | Latest tested patch | Published | Eligible | Promotion |
| --- | --- | --- | --- | --- | --- |
| CoreDNS | 1.14.2 | [1.14.7](https://github.com/coredns/coredns/releases/tag/v1.14.7) | 2026-08-19 | 2026-09-02 | Blocked: affected symbols |
| etcd | 3.6.8-0 | [3.6.15-0](https://github.com/etcd-io/etcd/releases/tag/v3.6.15) | 2026-09-22 | 2026-10-06 | Blocked: affected symbols |

## Evidence

[All-binary CI run 38601213896](https://github.com/amazen33/twinfra/actions/runs/38601213896) inspected every Go ELF in the verified Linux amd64 graphs. Image code was never executed.
govulncheck v1.1.4 binary SHA256: `f77f577722ac825bf649c24023c24af64e44c77152ab4e1778b2f8a27c2011fb`.
Binary mode establishes affected symbol presence, not runtime calls. Symbols are conservatively treated as reachable under WO-34; no not-reachable exception is created or extended.

Candidate pins (data only):

- CoreDNS: `registry.k8s.io/coredns/coredns@sha256:7efd3c635b03efd68c4e8398fc45f0d993d0e9ab016f72c1cefb0fd6d01aa286`.
- etcd: `registry.k8s.io/etcd@sha256:5ed4e32061aa061f970d6500629213e8579ef17571dcf9789074966acb9afad1`.

| Image | Binary | Affected module/version | Affected symbols | Reported fix |
| --- | --- | --- | ---: | --- |
| coredns | `/coredns` | `golang.org/x/net v0.51.0` | 80 | `v0.60.0` |
| coredns | `/coredns` | `stdlib v1.26.1` | 217 | `v1.26.9` |
| coredns-1.14.7 | `/coredns` | `golang.org/x/net v0.57.0` | 80 | `v0.60.0` |
| coredns-1.14.7 | `/coredns` | `stdlib v1.26.6` | 217 | `v1.26.9` |
| etcd | `/usr/local/bin/etcd` | `golang.org/x/net v0.47.0` | 80 | `v0.60.0` |
| etcd | `/usr/local/bin/etcd` | `stdlib v1.24.13` | 217 | `v1.26.9` |
| etcd | `/usr/local/bin/etcdctl` | `golang.org/x/net v0.47.0` | 80 | `v0.60.0` |
| etcd | `/usr/local/bin/etcdctl` | `stdlib v1.24.13` | 217 | `v1.26.9` |
| etcd | `/usr/local/bin/etcdutl` | `golang.org/x/net v0.47.0` | 80 | `v0.60.0` |
| etcd | `/usr/local/bin/etcdutl` | `stdlib v1.24.13` | 217 | `v1.26.9` |
| etcd-3.6.15 | `/usr/local/bin/etcd` | `golang.org/x/net v0.58.0` | 80 | `v0.60.0` |
| etcd-3.6.15 | `/usr/local/bin/etcd` | `stdlib v1.26.8` | 217 | `v1.26.9` |
| etcd-3.6.15 | `/usr/local/bin/etcdctl` | `golang.org/x/net v0.58.0` | 80 | `v0.60.0` |
| etcd-3.6.15 | `/usr/local/bin/etcdctl` | `stdlib v1.26.8` | 217 | `v1.26.9` |
| etcd-3.6.15 | `/usr/local/bin/etcdutl` | `golang.org/x/net v0.58.0` | 80 | `v0.60.0` |
| etcd-3.6.15 | `/usr/local/bin/etcdutl` | `stdlib v1.26.8` | 217 | `v1.26.9` |

## Compatibility and next action

The checksum-verified kubeadm v1.36.5 constants remain `CoreDNSVersion=v1.14.2` and `DefaultEtcdVersion=3.6.8-0`, with minor 36 mapped to etcd 3.6.8-0. Candidate releases stay on CoreDNS 1.14 and etcd 3.6, but have not been promoted or declared accepted kubeadm overrides. A future fixed candidate requires both binary triage and verified kubeadm configuration/render validation before promotion.

No changed images means no before/after promotion scan table applies to this evidence-only PR. Complete vulnerability scans and zero fixable Critical acceptance remain Pending for a future fixed patch. Existing exceptions and their expiry dates are unchanged.

Live acceptance and tester sign-off: Pending for the owner on `twinfra-dev-cairo-1` after a separately reviewed fixed patch. Do not stage these candidate pins.
