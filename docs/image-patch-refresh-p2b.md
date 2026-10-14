# WO-34 P2b: CoreDNS and etcd data-only triage

Date: 2026-10-14. Static only; no image promotion, lock change, staging or live action.
[WO-34 Amendment 1](https://github.com/amazen33/twinfra/pull/55) permits each blocked component to stop independently.

## Result

Promotion is stopped: completed source analysis reports reachable GO-2026-6612 under owner-approved Amendment 2. The owner must decide whether to accept risk with controls or wait for a fixed eligible patch. The newest published patches on the supported pinned minors still contain affected symbols for [GO-2026-6612](https://pkg.go.dev/vuln/GO-2026-6612).
No fixed later patch or eligibility date has been verified. The dates below show when the tested patches became eligible; age alone does not permit promotion of an affected image.

| Component | Current | Latest tested patch | Published | Eligible | Promotion |
| --- | --- | --- | --- | --- | --- |
| CoreDNS | 1.14.2 | [1.14.7](https://github.com/coredns/coredns/releases/tag/v1.14.7) | 2026-08-19 | 2026-09-02 | Stopped: source reachable |
| etcd | 3.6.8-0 | [3.6.15-0](https://github.com/etcd-io/etcd/releases/tag/v3.6.15) | 2026-09-22 | 2026-10-06 | Stopped: source reachable |

## Evidence

[All-binary CI run 38601213896](https://github.com/amazen33/twinfra/actions/runs/38601213896) inspected every Go ELF in the verified Linux amd64 graphs. Image code was never executed.
govulncheck v1.1.4 binary SHA256: `f77f577722ac825bf649c24023c24af64e44c77152ab4e1778b2f8a27c2011fb`.
Binary mode establishes affected symbol presence, not runtime calls. Affected symbols are present, which alone does not establish a source call path. No not-reachable exception is created or extended.

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

The checksum-verified kubeadm v1.36.5 constants remain `CoreDNSVersion=v1.14.2` and `DefaultEtcdVersion=3.6.8-0`, with minor 36 mapped to etcd 3.6.8-0. Candidate releases stay on CoreDNS 1.14 and etcd 3.6, but have not been promoted or declared accepted kubeadm overrides. A net-improving candidate requires source call-stack evidence and verified kubeadm configuration/render validation before promotion. A reachable finding stops that component for an owner decision.

No pins change in this evidence-only revision. Complete before/after scans run as data in PR #55; no new Critical/High finding and a net improvement are required by Amendment 2. Source analysis uses the binary-matched Go SDK: CoreDNS go1.26.6, etcd/server/etcdctl/etcdutl go1.26.8. Completed source evidence and the scan table are recorded below. Existing exceptions and their expiry dates are unchanged.

Live acceptance and tester sign-off: Pending for the owner on `twinfra-dev-cairo-1` after a separately reviewed, eligible patch. Do not stage these candidate pins.

Amendment 2 deadline watch: report any Critical exception with no fix or validated not-reachable evidence to the owner by **2026-11-05**, before its **2026-11-12** expiry. Current binary-only evidence cannot discharge that risk; no expiry is extended.

## Completed Amendment 2 source/scan assessment

[CI source and comparison run 38630364025](https://github.com/amazen33/twinfra/actions/runs/38630364025) passed its data-analysis jobs. All four complete Linux amd64 OCI graphs used one fresh database:

| Image | Critical with fix | Critical without fix | High with fix | High without fix |
| --- | ---: | ---: | ---: | ---: |
| CoreDNS 1.14.2 | 11 | 0 | 48 | 0 |
| CoreDNS 1.14.7 | 3 | 0 | 20 | 0 |
| etcd 3.6.8-0 | 11 | 0 | 43 | 0 |
| etcd 3.6.15-0 | 3 | 0 | 13 | 0 |

Both candidates are net improvements and add no new Critical/High finding, but source mode stops their promotion:

- CoreDNS v1.14.7, GOTOOLCHAIN=go1.26.6: 235 GO-2026-6612 source findings, in stdlib v1.26.6 and x/net v0.57.0. A representative path is `main → coremain.Run → caddy.Start → dnsserver.Serve → grpc.Server.Serve → NewServerTransport → http2.Framer.ReadFrame`.
- etcd v3.6.15, GOTOOLCHAIN=go1.26.8: 214 server, 135 etcdctl and 99 etcdutl source findings. stdlib v1.26.8 and x/net v0.58.0 remain affected. A representative server path is `main → etcdmain.Main → startGRPCProxy → startServe → grpc.Server.Serve → NewServerTransport → http2.Framer.ReadFrame`.

[Full source positions, SDK/source hashes and receipt](https://github.com/amazen33/twinfra/blob/codex/wo-34-image-refresh/docs/image-patch-refresh-source.md) preserve the call stacks. These are conservative source-call paths, not live exploitability proof. The owner chooses a documented risk acceptance or a fixed patch; there is no automatic exception or extension. Kubeadm v1.36.5 defaults stay unchanged, and candidate override acceptance is not claimed while promotion is stopped.

All **76** currently open Critical records across the platform expire 2026-11-12 and have no validated not-reachable clearance established by this work. This is their early risk notice, delivered before 2026-11-05. No expiry changes.
