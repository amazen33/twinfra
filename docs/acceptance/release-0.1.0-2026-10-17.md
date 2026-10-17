# Twinfra v0.1.0 acceptance — baseline run, 2026-10-17

## Scope and authorization

- Environment: `twinfra-dev-cairo-1`, single-node Ubuntu 24.04.5 Dell, Kubernetes v1.36.5.
- Scope: WO-40a **baseline** acceptance for dev use; the first complete run on real hardware. It is not the 48-hour rc window run, and no release is published.
- Owner authority: WO-40 Amendments 1 to 9 (2026-10-16 and 2026-10-17).
- Tested commit / expected Application revision: `a89de0a6a4e7dc023037bc640fbfd6cd6c7afbcf` (all three Applications).
- Acceptance start/end (UTC): 2026-10-17T17:08:56Z to 2026-10-17T17:10:35Z. The 48-hour rc window run is Pending (WO-40, about 2026-11-02).
- Tester and witness: Ahmed Mazen (@amazen33), owner-run from the laptop through the documented loopback tunnels. Analysis: Claude (architect).
- Prerequisite maintenance: WO-40c (etcd 3.6.15-0, CoreDNS v1.14.7) was applied on 2026-10-17; see the owner-reported record in [the maintenance runbook](../maintenance/etcd-coredns-2026-10.md).

The [consolidated template](release-0.1.0-2026-10-16.md) is unchanged. This receipt records the baseline evidence that the final consolidated receipt will cite.

## Acceptance output

- Command: `python tools/platform_dev.py accept --context twinfra-dev-cairo-1 --expected-revision a89de0a6a4e7dc023037bc640fbfd6cd6c7afbcf --ca-file <private> --session-file <private> --roleless-token-file <private> --with-restart`. Private inputs stay outside Git and are not attached.
- `--with-restart`: explicitly authorized by the owner for this run.
- Fragment: [release-0.1.0-2026-10-17.json](release-0.1.0-2026-10-17.json), committed with LF line endings, SHA-256 `13d59946e8e76554893b0a9c7d5671d012becf0503263a8407091d872b481d16`. The owner's original file `.build/acceptance/accept-20261017T170856534963Z.json` (CRLF) has SHA-256 `d8a92fedfe749b7aa037376378b3bca11c65b71815cd32db7c41b4f2675eb210`; the two differ only in line endings.
- `status`: **passed** (exit code 0).

| Check | Result | Evidence |
| --- | --- | --- |
| `exceptionCalendar` | passed | No expired or <=7-day exception; 2 warnings (below) |
| `node` | passed | Single approved node, Ready, InternalIP and zone/region labels as expected |
| `podsInitial` | passed | No pod not Running, replaced or restarted since the start |
| `gitops` | passed | All three Applications Synced/Healthy at `a89de0a6a4e7` |
| `host-check` | passed | WO-31 host identity, ownership and owned network files verified |
| `host-network` | passed | Read-only network check through the scoped transport |
| `staging:images.lock.json` | passed | All application images staged, pinned, digest-verified |
| `staging:bootstrap-images.lock.json` | passed | All 11 bootstrap images staged, pinned, digest-verified (incl. etcd 3.6.15-0, CoreDNS v1.14.7) |
| `deployedImages` | passed | 31 running containers match their locked manifest digests; 0 problems; no LocalStack image |
| `consoleHTTPS` | passed | Authenticated identity through verified HTTPS (dev CA, hostname checked) returned 200, environment dev |
| `tokenNegatives` | passed | missing 401 / unsigned 401 / duplicate 401 / roleless 403 |
| `valkey` | passed | NOAUTH rejected: True; authenticated PONG: True; Argo clients connected: argocd-application-controller, argocd-repo-server, argocd-server |
| `versions` | passed | Every Ready replica agrees (table below) |
| `valkeyRestart` | passed | Owner-authorized: cache Pod deleted once, replacement Ready, all three Argo clients reconnected |
| `podsFinal` | passed | Only the authorized cache replacement is new; no other pod replaced or restarted |
| `deployedImagesFinal` | passed | Locked digests re-verified after the restart; 0 problems |
| `gitopsFinal` | passed | Fresh healthy reconciliation at the same commit after the restart |

## Actual running versions

From the suite (`versions`), not desired pins.

| Component | Running version / immutable identity |
| --- | --- |
| Kubernetes | v1.36.5 |
| containerd | containerd://2.2.1 |
| Cilium | 1.20.2 |
| etcd | 3.6.15 |
| CoreDNS | 1.14.7 |
| Argo CD | 3.5.3 |
| CloudNativePG | 1.30.1 |
| PostgreSQL / pgvector | 18.6; the vector extension is confirmed separately by the owner |
| Keycloak | 26.8.0 |
| OpenBao | 2.7.1; initialization, unseal and leases are not claimed |
| Valkey | 8.1.10 |
| Console | `registry.twinfra.example.com/docker.io/twinfra/twinfra-console@sha256:ec1eebc9b51a1e7e019b501039f8c822eee5751b6322b205ec0b5eea9f30cd54`; content-addressed, no embedded release-version claim |

## Individual evidence (treatment for owner sign-off)

| Work | Existing receipt | What this run proves | Remaining before the owner signs |
| --- | --- | --- | --- |
| WO-25 | [Valkey](valkey-2026-10-09.md) | NOAUTH rejected, authenticated PONG, three Argo clients before; authorized restart, replacement, reconnect and fresh reconciliation after | None from the suite; owner signs if satisfied |
| WO-34 P2 | [CoreDNS/etcd evidence](wo34-p2-2026-10-15.json) | etcd 3.6.15 and CoreDNS 1.14.7 running with the locked digests after the WO-40c maintenance | None from the suite; owner signs the live part if satisfied |
| WO-34 P1/P3 | [P1](wo34-p1-2026-10-14.json), [P3](wo34-p3-2026-10-14.json) | Running digests match the locks | Static evidence; owner decides |
| WO-04 | [Signed-token checks](console-token-verification-2026-10-10.md) | The four live token negatives (401/401/401/403) and authenticated console identity | Owner's live browser witness: login, logout, emulator views |
| WO-06 | [LocalStack removal](localstack-removal-2026-10-10.md) | No LocalStack image among 31 running containers | Remaining UI/endpoint checks in that receipt |
| WO-31 | [Dell observations](dev-environment-2026-10-13.md) | Node, host identity, network, versions, images and GitOps | The separately witnessed 24-hour soak, storage and firewall gates; a short run does not prove 24 hours of uptime |
| WO-36 / WO-36a | [Router/static address](host-network-2026-10-15.md), [VM qualification](host-network-fix-2026-10-15.md) | `host-network` passed | Signed scope preserved; nothing new inferred |
| WO-37 | [Capabilities](../capabilities.md) | Docs/CI evidence | No live receipt exists or is invented |

## Exception calendar

Every row of the fragment's `exceptionCalendar` (62 rows; 2 warnings, none expired or within 7 days).

| Image | Package / version | CVE | Expiry | Days left at run | Status / owner disposition |
| --- | --- | --- | --- | --- | --- |
| `quay.io/argoproj/argocd` | github.com/argoproj/argo-cd/v3 v3.5.3+dirty | CVE-2026-55797 | 2026-11-02 | 16 | warning: WO-34e interim Argo CD 3.5.3 exception; remediation is the Argo CD 3.5.5 promotion from 2026-10-26 (WO-40 Amendment 1); not extended |
| `quay.io/argoproj/argocd` | github.com/argoproj/argo-cd/v3 v3.5.3+dirty | CVE-2026-77459 | 2026-11-02 | 16 | warning: WO-34e interim Argo CD 3.5.3 exception; remediation is the Argo CD 3.5.5 promotion from 2026-10-26 (WO-40 Amendment 1); not extended |
| `docker.io/apache/apisix` | perl-base 5.36.0-7+deb12u3 | CVE-2026-12087 | 2026-11-12 | 26 | passed |
| `docker.io/apache/apisix` | perl-base 5.36.0-7+deb12u3 | CVE-2026-13221 | 2026-11-12 | 26 | passed |
| `docker.io/apache/apisix` | perl-base 5.36.0-7+deb12u3 | CVE-2026-42496 | 2026-11-12 | 26 | passed |
| `docker.io/apache/apisix` | perl-base 5.36.0-7+deb12u3 | CVE-2026-57433 | 2026-11-12 | 26 | passed |
| `docker.io/apache/apisix` | perl-base 5.36.0-7+deb12u3 | CVE-2026-8376 | 2026-11-12 | 26 | passed |
| `docker.io/ministackorg/ministack` | python 3.13.15 | CVE-2026-19445 | 2026-11-12 | 26 | passed |
| `docker.io/openbao/openbao` | stdlib go1.27.1 | CVE-2026-56857 | 2026-11-12 | 26 | passed |
| `docker.io/openbao/openbao` | golang.org/x/net v0.58.0 | CVE-2026-78663 | 2026-11-12 | 26 | passed |
| `docker.io/openbao/openbao` | stdlib go1.27.1 | CVE-2026-78663 | 2026-11-12 | 26 | passed |
| `ghcr.io/cloudnative-pg/cloudnative-pg` | stdlib go1.27.1 | CVE-2026-56857 | 2026-11-12 | 26 | passed |
| `ghcr.io/cloudnative-pg/cloudnative-pg` | golang.org/x/net v0.58.0 | CVE-2026-78663 | 2026-11-12 | 26 | passed |
| `ghcr.io/cloudnative-pg/cloudnative-pg` | stdlib go1.27.1 | CVE-2026-78663 | 2026-11-12 | 26 | passed |
| `quay.io/argoproj/argocd` | stdlib go1.24.0 | CVE-2025-22871 | 2026-11-12 | 26 | passed |
| `quay.io/argoproj/argocd` | stdlib go1.24.0 | CVE-2025-68121 | 2026-11-12 | 26 | passed |
| `quay.io/argoproj/argocd` | stdlib go1.25.3 | CVE-2025-68121 | 2026-11-12 | 26 | passed |
| `quay.io/argoproj/argocd` | golang.org/x/crypto v0.36.0 | CVE-2026-39830 | 2026-11-12 | 26 | passed |
| `quay.io/argoproj/argocd` | golang.org/x/crypto v0.36.0 | CVE-2026-39831 | 2026-11-12 | 26 | passed |
| `quay.io/argoproj/argocd` | golang.org/x/crypto v0.36.0 | CVE-2026-39832 | 2026-11-12 | 26 | passed |
| `quay.io/argoproj/argocd` | golang.org/x/crypto v0.36.0 | CVE-2026-39833 | 2026-11-12 | 26 | passed |
| `quay.io/argoproj/argocd` | golang.org/x/crypto v0.36.0 | CVE-2026-39834 | 2026-11-12 | 26 | passed |
| `quay.io/argoproj/argocd` | golang.org/x/crypto v0.36.0 | CVE-2026-42508 | 2026-11-12 | 26 | passed |
| `quay.io/argoproj/argocd` | golang.org/x/crypto v0.36.0 | CVE-2026-46595 | 2026-11-12 | 26 | passed |
| `quay.io/argoproj/argocd` | stdlib go1.24.0 | CVE-2026-56857 | 2026-11-12 | 26 | passed |
| `quay.io/argoproj/argocd` | stdlib go1.25.3 | CVE-2026-56857 | 2026-11-12 | 26 | passed |
| `quay.io/argoproj/argocd` | stdlib go1.26.2 | CVE-2026-56857 | 2026-11-12 | 26 | passed |
| `quay.io/argoproj/argocd` | stdlib go1.26.4 | CVE-2026-56857 | 2026-11-12 | 26 | passed |
| `quay.io/argoproj/argocd` | golang.org/x/net v0.38.0 | CVE-2026-78663 | 2026-11-12 | 26 | passed |
| `quay.io/argoproj/argocd` | golang.org/x/net v0.40.0 | CVE-2026-78663 | 2026-11-12 | 26 | passed |
| `quay.io/argoproj/argocd` | golang.org/x/net v0.55.0 | CVE-2026-78663 | 2026-11-12 | 26 | passed |
| `quay.io/argoproj/argocd` | golang.org/x/net v0.56.0 | CVE-2026-78663 | 2026-11-12 | 26 | passed |
| `quay.io/argoproj/argocd` | stdlib go1.24.0 | CVE-2026-78663 | 2026-11-12 | 26 | passed |
| `quay.io/argoproj/argocd` | stdlib go1.25.3 | CVE-2026-78663 | 2026-11-12 | 26 | passed |
| `quay.io/argoproj/argocd` | stdlib go1.26.2 | CVE-2026-78663 | 2026-11-12 | 26 | passed |
| `quay.io/argoproj/argocd` | stdlib go1.26.4 | CVE-2026-78663 | 2026-11-12 | 26 | passed |
| `quay.io/cilium/cilium-envoy` | stdlib go1.27.1 | CVE-2026-56857 | 2026-11-12 | 26 | passed |
| `quay.io/cilium/cilium-envoy` | golang.org/x/net v0.58.0 | CVE-2026-78663 | 2026-11-12 | 26 | passed |
| `quay.io/cilium/cilium-envoy` | stdlib go1.27.1 | CVE-2026-78663 | 2026-11-12 | 26 | passed |
| `quay.io/cilium/cilium` | stdlib go1.26.5 | CVE-2026-56857 | 2026-11-12 | 26 | passed |
| `quay.io/cilium/cilium` | stdlib go1.26.8 | CVE-2026-56857 | 2026-11-12 | 26 | passed |
| `quay.io/cilium/cilium` | golang.org/x/net v0.56.0 | CVE-2026-78663 | 2026-11-12 | 26 | passed |
| `quay.io/cilium/cilium` | stdlib go1.26.5 | CVE-2026-78663 | 2026-11-12 | 26 | passed |
| `quay.io/cilium/cilium` | stdlib go1.26.8 | CVE-2026-78663 | 2026-11-12 | 26 | passed |
| `quay.io/cilium/operator-generic` | stdlib go1.26.8 | CVE-2026-56857 | 2026-11-12 | 26 | passed |
| `quay.io/cilium/operator-generic` | golang.org/x/net v0.56.0 | CVE-2026-78663 | 2026-11-12 | 26 | passed |
| `quay.io/cilium/operator-generic` | stdlib go1.26.8 | CVE-2026-78663 | 2026-11-12 | 26 | passed |
| `registry.k8s.io/coredns/coredns` | stdlib go1.26.6 | CVE-2026-56857 | 2026-11-12 | 26 | passed |
| `registry.k8s.io/coredns/coredns` | golang.org/x/net v0.57.0 | CVE-2026-78663 | 2026-11-12 | 26 | passed |
| `registry.k8s.io/coredns/coredns` | stdlib go1.26.6 | CVE-2026-78663 | 2026-11-12 | 26 | passed |
| `registry.k8s.io/etcd` | stdlib go1.26.8 | CVE-2026-56857 | 2026-11-12 | 26 | passed |
| `registry.k8s.io/etcd` | golang.org/x/net v0.58.0 | CVE-2026-78663 | 2026-11-12 | 26 | passed |
| `registry.k8s.io/etcd` | stdlib go1.26.8 | CVE-2026-78663 | 2026-11-12 | 26 | passed |
| `registry.k8s.io/kube-apiserver` | stdlib go1.26.8 | CVE-2026-56857 | 2026-11-12 | 26 | passed |
| `registry.k8s.io/kube-apiserver` | golang.org/x/net v0.56.0 | CVE-2026-78663 | 2026-11-12 | 26 | passed |
| `registry.k8s.io/kube-apiserver` | stdlib go1.26.8 | CVE-2026-78663 | 2026-11-12 | 26 | passed |
| `registry.k8s.io/kube-controller-manager` | stdlib go1.26.8 | CVE-2026-56857 | 2026-11-12 | 26 | passed |
| `registry.k8s.io/kube-controller-manager` | golang.org/x/net v0.56.0 | CVE-2026-78663 | 2026-11-12 | 26 | passed |
| `registry.k8s.io/kube-controller-manager` | stdlib go1.26.8 | CVE-2026-78663 | 2026-11-12 | 26 | passed |
| `registry.k8s.io/kube-scheduler` | stdlib go1.26.8 | CVE-2026-56857 | 2026-11-12 | 26 | passed |
| `registry.k8s.io/kube-scheduler` | golang.org/x/net v0.56.0 | CVE-2026-78663 | 2026-11-12 | 26 | passed |
| `registry.k8s.io/kube-scheduler` | stdlib go1.26.8 | CVE-2026-78663 | 2026-11-12 | 26 | passed |

## Static evidence and limits

- Suite fixes found by the live runs and merged with green CI before this pass: WO-40c [#70](https://github.com/amazen33/twinfra/pull/70), WO-40d [#71](https://github.com/amazen33/twinfra/pull/71), WO-40e [#72](https://github.com/amazen33/twinfra/pull/72).
- No AWS parity, HA, backup/DR, multi-tenancy, secrets management, observability retention, compliance, Foundation 1.0 or production-readiness claim.
- Owner signs WO-04, WO-06, WO-25, WO-31 and the WO-34 receipts separately, and only for proven scope.
- WO-40b, the Argo CD 3.5.5 promotion, the exception renewal PR and the rc window remain separate release gates.

## Tester sign-off

Tester: Ahmed Mazen (@amazen33), enterprise and cloud tester; QoS tester
Result: Pending
Date (UTC):
QoS targets checked:
Notes:
