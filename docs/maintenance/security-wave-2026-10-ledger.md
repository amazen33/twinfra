# R12: exact exception review ledger

Generated from the full candidate scan. Every approval is Pending. See the [review and owner runbook](security-wave-2026-10.md).

## Every qualifying and non-qualifying High, grouped by image/package

| Image | Package/version | Route | Every advisory | Scanner fixes | Remediation/eligibility evidence |
| --- | --- | --- | --- | --- | --- |
| apiserver | go.etcd.io/etcd/client/pkg/v3 v3.6.8 | normal | CVE-2026-73500 | 3.5.33, 3.6.14, 3.7.1 | WO-46 remediation candidate v1.36.6, eligible 2026-11-11T04:56:35Z; fixed package/build still requires a full rescan |
| apiserver | go.opentelemetry.io/otel/sdk v1.40.0 | normal | CVE-2026-39883 | 1.43.0 | WO-46 remediation candidate v1.36.6, eligible 2026-11-11T04:56:35Z; fixed package/build still requires a full rescan |
| apiserver | golang.org/x/crypto v0.53.0 | toolchain-wave | CVE-2026-56854, CVE-2026-56855, CVE-2026-78662 | 0.55.0, 0.56.0 | WO-46 remediation candidate v1.36.6, eligible 2026-11-11T04:56:35Z; fixed package/build still requires a full rescan |
| apiserver | golang.org/x/net v0.56.0 | toolchain-wave | CVE-2026-78659, CVE-2026-78660, CVE-2026-78669, CVE-2026-97032 | 0.60.0 | WO-46 remediation candidate v1.36.6, eligible 2026-11-11T04:56:35Z; fixed package/build still requires a full rescan |
| apiserver | golang.org/x/text v0.39.0 | toolchain-wave | CVE-2026-56851 | 0.41.0 | WO-46 remediation candidate v1.36.6, eligible 2026-11-11T04:56:35Z; fixed package/build still requires a full rescan |
| apiserver | google.golang.org/grpc v1.79.3 | normal | CVE-2026-84304, CVE-2026-84445, GHSA-hrxh-6v49-42gf | 1.82.1, 1.82.2, 1.83.1 | WO-46 remediation candidate v1.36.6, eligible 2026-11-11T04:56:35Z; fixed package/build still requires a full rescan |
| apiserver | stdlib go1.26.8 | toolchain-wave | CVE-2026-56866, CVE-2026-78659, CVE-2026-78660, CVE-2026-78667, CVE-2026-78669, CVE-2026-94439, CVE-2026-94440, CVE-2026-97031, CVE-2026-97032 | 1.26.9, 1.27.2 | WO-46 remediation candidate v1.36.6, eligible 2026-11-11T04:56:35Z; fixed package/build still requires a full rescan |
| apisix | libpcre2-8-0 10.42-1+deb12u1 | normal | CVE-2026-103111 | 10.42-1+deb12u2 | No verified fixed same-line image release or eligibility date; WO-46 must track upstream and rescan before promotion |
| apisix | libssl3 3.0.22-1~deb12u1 | normal | CVE-2026-84782 | 3.0.22-1~deb12u2 | No verified fixed same-line image release or eligibility date; WO-46 must track upstream and rescan before promotion |
| apisix | openssl 3.0.22-1~deb12u1 | normal | CVE-2026-84782 | 3.0.22-1~deb12u2 | No verified fixed same-line image release or eligibility date; WO-46 must track upstream and rescan before promotion |
| apisix | perl-base 5.36.0-7+deb12u3 | normal | CVE-2026-42497, CVE-2026-48959, CVE-2026-48962, CVE-2026-57432, CVE-2026-7017 | 5.36.0-7+deb12u4 | No verified fixed same-line image release or eligibility date; WO-46 must track upstream and rescan before promotion |
| argocd | github.com/go-jose/go-jose/v4 v4.1.4 | normal | CVE-2026-116587 | 4.1.6 | No verified fixed same-line image release or eligibility date; WO-46 must track upstream and rescan before promotion |
| argocd | github.com/klauspost/compress v1.18.0 | normal | CVE-2026-63209 | 1.18.7 | No verified fixed same-line image release or eligibility date; WO-46 must track upstream and rescan before promotion |
| argocd | golang.org/x/crypto v0.36.0 | toolchain-wave | CVE-2025-47913, CVE-2026-39829, CVE-2026-46597, CVE-2026-56854, CVE-2026-56855, CVE-2026-78662 | 0.43.0, 0.52.0, 0.55.0, 0.56.0 | No verified fixed same-line image release or eligibility date; WO-46 must track upstream and rescan before promotion |
| argocd | golang.org/x/crypto v0.53.0 | toolchain-wave | CVE-2026-56854, CVE-2026-56855, CVE-2026-78662 | 0.55.0, 0.56.0 | No verified fixed same-line image release or eligibility date; WO-46 must track upstream and rescan before promotion |
| argocd | golang.org/x/net v0.38.0 | toolchain-wave | CVE-2026-33814, CVE-2026-39821, CVE-2026-46600, CVE-2026-78659, CVE-2026-78660, CVE-2026-78669, CVE-2026-97032 | 0.53.0, 0.55.0, 0.56.0, 0.60.0 | No verified fixed same-line image release or eligibility date; WO-46 must track upstream and rescan before promotion |
| argocd | golang.org/x/net v0.40.0 | toolchain-wave | CVE-2026-33814, CVE-2026-39821, CVE-2026-46600, CVE-2026-78659, CVE-2026-78660, CVE-2026-78669, CVE-2026-97032 | 0.53.0, 0.55.0, 0.56.0, 0.60.0 | No verified fixed same-line image release or eligibility date; WO-46 must track upstream and rescan before promotion |
| argocd | golang.org/x/net v0.55.0 | toolchain-wave | CVE-2026-46600, CVE-2026-78659, CVE-2026-78660, CVE-2026-78669, CVE-2026-97032 | 0.56.0, 0.60.0 | No verified fixed same-line image release or eligibility date; WO-46 must track upstream and rescan before promotion |
| argocd | golang.org/x/net v0.59.0 | toolchain-wave | CVE-2026-78659, CVE-2026-78660, CVE-2026-78669, CVE-2026-97032 | 0.60.0 | No verified fixed same-line image release or eligibility date; WO-46 must track upstream and rescan before promotion |
| argocd | golang.org/x/text v0.23.0 | toolchain-wave | CVE-2026-56851, CVE-2026-56852 | 0.39.0, 0.41.0 | No verified fixed same-line image release or eligibility date; WO-46 must track upstream and rescan before promotion |
| argocd | golang.org/x/text v0.28.0 | toolchain-wave | CVE-2026-56851, CVE-2026-56852 | 0.39.0, 0.41.0 | No verified fixed same-line image release or eligibility date; WO-46 must track upstream and rescan before promotion |
| argocd | golang.org/x/text v0.38.0 | toolchain-wave | CVE-2026-56851, CVE-2026-56852 | 0.39.0, 0.41.0 | No verified fixed same-line image release or eligibility date; WO-46 must track upstream and rescan before promotion |
| argocd | libcurl3t64-gnutls 8.18.0-1ubuntu2.7 | normal | CVE-2026-92392 | 8.18.0-1ubuntu2.8 | No verified fixed same-line image release or eligibility date; WO-46 must track upstream and rescan before promotion |
| argocd | oras.land/oras-go/v2 v2.6.1 | normal | CVE-2026-50163, CVE-2026-85731 | 2.6.2 | No verified fixed same-line image release or eligibility date; WO-46 must track upstream and rescan before promotion |
| argocd | stdlib go1.24.0 | normal | CVE-2025-22874, CVE-2025-47907, CVE-2025-58187, CVE-2025-58188, CVE-2025-61723, CVE-2025-61725, CVE-2025-61726, CVE-2025-61729, CVE-2026-25679, CVE-2026-27145, CVE-2026-32280, CVE-2026-32281, CVE-2026-32283, CVE-2026-33811, CVE-2026-33814, CVE-2026-33818, CVE-2026-39820, CVE-2026-39821, CVE-2026-39822, CVE-2026-39836, CVE-2026-42499, CVE-2026-42504, CVE-2026-56853, CVE-2026-56859, CVE-2026-56862, CVE-2026-56866, CVE-2026-78659, CVE-2026-78660, CVE-2026-78667, CVE-2026-78669, CVE-2026-94439, CVE-2026-94440, CVE-2026-97031, CVE-2026-97032 | 1.23.12, 1.24.11, 1.24.12, 1.24.4, 1.24.6, 1.24.8, 1.24.9, 1.25.10, 1.25.11, 1.25.12, 1.25.13, 1.25.2, 1.25.3, 1.25.5, 1.25.6, 1.25.8, 1.25.9, 1.26.1, 1.26.2, 1.26.3, 1.26.4, 1.26.5, 1.26.6, 1.26.9, 1.27.0-rc.2, 1.27.0-rc.3, 1.27.2 | No verified fixed same-line image release or eligibility date; WO-46 must track upstream and rescan before promotion |
| argocd | stdlib go1.25.3 | normal | CVE-2025-61726, CVE-2025-61729, CVE-2026-25679, CVE-2026-27145, CVE-2026-32280, CVE-2026-32281, CVE-2026-32283, CVE-2026-33811, CVE-2026-33814, CVE-2026-33818, CVE-2026-39820, CVE-2026-39821, CVE-2026-39822, CVE-2026-39836, CVE-2026-42499, CVE-2026-42504, CVE-2026-56853, CVE-2026-56859, CVE-2026-56862, CVE-2026-56866, CVE-2026-78659, CVE-2026-78660, CVE-2026-78667, CVE-2026-78669, CVE-2026-94439, CVE-2026-94440, CVE-2026-97031, CVE-2026-97032 | 1.24.11, 1.24.12, 1.25.10, 1.25.11, 1.25.12, 1.25.13, 1.25.5, 1.25.6, 1.25.8, 1.25.9, 1.26.1, 1.26.2, 1.26.3, 1.26.4, 1.26.5, 1.26.6, 1.26.9, 1.27.0-rc.2, 1.27.0-rc.3, 1.27.2 | No verified fixed same-line image release or eligibility date; WO-46 must track upstream and rescan before promotion |
| argocd | stdlib go1.26.2 | normal | CVE-2026-27145, CVE-2026-33811, CVE-2026-33814, CVE-2026-33818, CVE-2026-39820, CVE-2026-39821, CVE-2026-39822, CVE-2026-39836, CVE-2026-42499, CVE-2026-42504, CVE-2026-46600, CVE-2026-56853, CVE-2026-56859, CVE-2026-56862 | 1.25.10, 1.25.11, 1.25.12, 1.25.13, 1.26.3, 1.26.4, 1.26.5, 1.26.6, 1.27.0-rc.2, 1.27.0-rc.3 | No verified fixed same-line image release or eligibility date; WO-46 must track upstream and rescan before promotion |
| argocd | stdlib go1.26.2 | toolchain-wave | CVE-2026-56866, CVE-2026-78659, CVE-2026-78660, CVE-2026-78667, CVE-2026-78669, CVE-2026-94439, CVE-2026-94440, CVE-2026-97031, CVE-2026-97032 | 1.26.9, 1.27.2 | No verified fixed same-line image release or eligibility date; WO-46 must track upstream and rescan before promotion |
| argocd | stdlib go1.26.4 | normal | CVE-2026-33818, CVE-2026-39821, CVE-2026-39822, CVE-2026-46600, CVE-2026-56853, CVE-2026-56859, CVE-2026-56862 | 1.25.12, 1.25.13, 1.26.5, 1.26.6, 1.27.0-rc.2, 1.27.0-rc.3 | No verified fixed same-line image release or eligibility date; WO-46 must track upstream and rescan before promotion |
| argocd | stdlib go1.26.4 | toolchain-wave | CVE-2026-56866, CVE-2026-78659, CVE-2026-78660, CVE-2026-78667, CVE-2026-78669, CVE-2026-94439, CVE-2026-94440, CVE-2026-97031, CVE-2026-97032 | 1.26.9, 1.27.2 | No verified fixed same-line image release or eligibility date; WO-46 must track upstream and rescan before promotion |
| cilium | github.com/klauspost/compress v1.18.6 | normal | CVE-2026-63209 | 1.18.7 | WO-46 remediation candidate v1.20.4, eligible 2026-11-06T14:51:39Z; fixed package/build still requires a full rescan |
| cilium | go.etcd.io/etcd/client/pkg/v3 v3.6.12 | normal | CVE-2026-73500 | 3.5.33, 3.6.14, 3.7.1 | WO-46 remediation candidate v1.20.4, eligible 2026-11-06T14:51:39Z; fixed package/build still requires a full rescan |
| cilium | golang.org/x/crypto v0.53.0 | toolchain-wave | CVE-2026-56854, CVE-2026-56855, CVE-2026-78662 | 0.55.0, 0.56.0 | WO-46 remediation candidate v1.20.4, eligible 2026-11-06T14:51:39Z; fixed package/build still requires a full rescan |
| cilium | golang.org/x/net v0.56.0 | toolchain-wave | CVE-2026-78659, CVE-2026-78660, CVE-2026-78669, CVE-2026-97032 | 0.60.0 | WO-46 remediation candidate v1.20.4, eligible 2026-11-06T14:51:39Z; fixed package/build still requires a full rescan |
| cilium | golang.org/x/text v0.39.0 | toolchain-wave | CVE-2026-56851 | 0.41.0 | WO-46 remediation candidate v1.20.4, eligible 2026-11-06T14:51:39Z; fixed package/build still requires a full rescan |
| cilium | google.golang.org/grpc v1.83.1 | normal | CVE-2026-84445 | 1.83.2 | WO-46 remediation candidate v1.20.4, eligible 2026-11-06T14:51:39Z; fixed package/build still requires a full rescan |
| cilium | libssl3t64 3.5.5-1ubuntu3.5 | normal | CVE-2026-84782 | 3.5.5-1ubuntu3.6 | WO-46 remediation candidate v1.20.4, eligible 2026-11-06T14:51:39Z; fixed package/build still requires a full rescan |
| cilium | openssl 3.5.5-1ubuntu3.5 | normal | CVE-2026-84782 | 3.5.5-1ubuntu3.6 | WO-46 remediation candidate v1.20.4, eligible 2026-11-06T14:51:39Z; fixed package/build still requires a full rescan |
| cilium | openssl-provider-legacy 3.5.5-1ubuntu3.5 | normal | CVE-2026-84782 | 3.5.5-1ubuntu3.6 | WO-46 remediation candidate v1.20.4, eligible 2026-11-06T14:51:39Z; fixed package/build still requires a full rescan |
| cilium | stdlib go1.26.5 | normal | CVE-2026-33818, CVE-2026-39821, CVE-2026-46600, CVE-2026-56853, CVE-2026-56859, CVE-2026-56862 | 1.25.13, 1.26.6, 1.27.0-rc.3 | WO-46 remediation candidate v1.20.4, eligible 2026-11-06T14:51:39Z; fixed package/build still requires a full rescan |
| cilium | stdlib go1.26.5 | toolchain-wave | CVE-2026-56866, CVE-2026-78659, CVE-2026-78660, CVE-2026-78667, CVE-2026-78669, CVE-2026-94439, CVE-2026-94440, CVE-2026-97031, CVE-2026-97032 | 1.26.9, 1.27.2 | WO-46 remediation candidate v1.20.4, eligible 2026-11-06T14:51:39Z; fixed package/build still requires a full rescan |
| cilium | stdlib go1.26.8 | toolchain-wave | CVE-2026-56866, CVE-2026-78659, CVE-2026-78660, CVE-2026-78667, CVE-2026-78669, CVE-2026-94439, CVE-2026-94440, CVE-2026-97031, CVE-2026-97032 | 1.26.9, 1.27.2 | WO-46 remediation candidate v1.20.4, eligible 2026-11-06T14:51:39Z; fixed package/build still requires a full rescan |
| cnpg | golang.org/x/net v0.58.0 | toolchain-wave | CVE-2026-78659, CVE-2026-78660, CVE-2026-78669, CVE-2026-97032 | 0.60.0 | No verified fixed same-line image release or eligibility date; WO-46 must track upstream and rescan before promotion |
| cnpg | stdlib go1.27.1 | toolchain-wave | CVE-2026-56866, CVE-2026-78659, CVE-2026-78660, CVE-2026-78667, CVE-2026-78669, CVE-2026-94439, CVE-2026-94440, CVE-2026-97031, CVE-2026-97032 | 1.26.9, 1.27.2 | No verified fixed same-line image release or eligibility date; WO-46 must track upstream and rescan before promotion |
| controller | go.etcd.io/etcd/client/pkg/v3 v3.6.8 | normal | CVE-2026-73500 | 3.5.33, 3.6.14, 3.7.1 | WO-46 remediation candidate v1.36.6, eligible 2026-11-11T04:56:35Z; fixed package/build still requires a full rescan |
| controller | go.opentelemetry.io/otel/sdk v1.40.0 | normal | CVE-2026-39883 | 1.43.0 | WO-46 remediation candidate v1.36.6, eligible 2026-11-11T04:56:35Z; fixed package/build still requires a full rescan |
| controller | golang.org/x/crypto v0.53.0 | toolchain-wave | CVE-2026-56854, CVE-2026-56855, CVE-2026-78662 | 0.55.0, 0.56.0 | WO-46 remediation candidate v1.36.6, eligible 2026-11-11T04:56:35Z; fixed package/build still requires a full rescan |
| controller | golang.org/x/net v0.56.0 | toolchain-wave | CVE-2026-78659, CVE-2026-78660, CVE-2026-78669, CVE-2026-97032 | 0.60.0 | WO-46 remediation candidate v1.36.6, eligible 2026-11-11T04:56:35Z; fixed package/build still requires a full rescan |
| controller | golang.org/x/text v0.39.0 | toolchain-wave | CVE-2026-56851 | 0.41.0 | WO-46 remediation candidate v1.36.6, eligible 2026-11-11T04:56:35Z; fixed package/build still requires a full rescan |
| controller | google.golang.org/grpc v1.79.3 | normal | CVE-2026-84304, CVE-2026-84445, GHSA-hrxh-6v49-42gf | 1.82.1, 1.82.2, 1.83.1 | WO-46 remediation candidate v1.36.6, eligible 2026-11-11T04:56:35Z; fixed package/build still requires a full rescan |
| controller | stdlib go1.26.8 | toolchain-wave | CVE-2026-56866, CVE-2026-78659, CVE-2026-78660, CVE-2026-78667, CVE-2026-78669, CVE-2026-94439, CVE-2026-94440, CVE-2026-97031, CVE-2026-97032 | 1.26.9, 1.27.2 | WO-46 remediation candidate v1.36.6, eligible 2026-11-11T04:56:35Z; fixed package/build still requires a full rescan |
| coredns | go.etcd.io/etcd/client/pkg/v3 v3.6.13 | normal | CVE-2026-73500 | 3.5.33, 3.6.14, 3.7.1 | No verified fixed same-line image release or eligibility date; WO-46 must track upstream and rescan before promotion |
| coredns | golang.org/x/crypto v0.54.0 | toolchain-wave | CVE-2026-56854, CVE-2026-56855, CVE-2026-78662 | 0.55.0, 0.56.0 | No verified fixed same-line image release or eligibility date; WO-46 must track upstream and rescan before promotion |
| coredns | golang.org/x/mod v0.37.0 | toolchain-wave | CVE-2026-56864, CVE-2026-56865 | 0.40.0 | No verified fixed same-line image release or eligibility date; WO-46 must track upstream and rescan before promotion |
| coredns | golang.org/x/net v0.57.0 | toolchain-wave | CVE-2026-78659, CVE-2026-78660, CVE-2026-78669, CVE-2026-97032 | 0.60.0 | No verified fixed same-line image release or eligibility date; WO-46 must track upstream and rescan before promotion |
| coredns | golang.org/x/text v0.40.0 | toolchain-wave | CVE-2026-56851 | 0.41.0 | No verified fixed same-line image release or eligibility date; WO-46 must track upstream and rescan before promotion |
| coredns | google.golang.org/grpc v1.83.0 | normal | CVE-2026-84304, CVE-2026-84445 | 1.83.1, 1.83.2 | No verified fixed same-line image release or eligibility date; WO-46 must track upstream and rescan before promotion |
| coredns | stdlib go1.26.6 | toolchain-wave | CVE-2026-56866, CVE-2026-78659, CVE-2026-78660, CVE-2026-78667, CVE-2026-78669, CVE-2026-94439, CVE-2026-94440, CVE-2026-97031, CVE-2026-97032 | 1.26.9, 1.27.2 | No verified fixed same-line image release or eligibility date; WO-46 must track upstream and rescan before promotion |
| envoy | golang.org/x/net v0.58.0 | toolchain-wave | CVE-2026-78659, CVE-2026-78660, CVE-2026-78669, CVE-2026-97032 | 0.60.0 | WO-46 remediation candidate v1.20.4, eligible 2026-11-06T14:51:39Z; fixed package/build still requires a full rescan |
| envoy | libssl3t64 3.0.13-0ubuntu3.15 | normal | CVE-2026-84782 | 3.0.13-0ubuntu3.16 | WO-46 remediation candidate v1.20.4, eligible 2026-11-06T14:51:39Z; fixed package/build still requires a full rescan |
| envoy | openssl 3.0.13-0ubuntu3.15 | normal | CVE-2026-84782 | 3.0.13-0ubuntu3.16 | WO-46 remediation candidate v1.20.4, eligible 2026-11-06T14:51:39Z; fixed package/build still requires a full rescan |
| envoy | stdlib go1.27.1 | toolchain-wave | CVE-2026-56866, CVE-2026-78659, CVE-2026-78660, CVE-2026-78667, CVE-2026-78669, CVE-2026-94439, CVE-2026-94440, CVE-2026-97031, CVE-2026-97032 | 1.26.9, 1.27.2 | WO-46 remediation candidate v1.20.4, eligible 2026-11-06T14:51:39Z; fixed package/build still requires a full rescan |
| etcd | github.com/klauspost/compress v1.17.9 | normal | CVE-2026-63209 | 1.18.7 | WO-46 remediation candidate v3.6.16, eligible 2026-11-05T23:00:22Z; fixed package/build still requires a full rescan |
| etcd | golang.org/x/crypto v0.55.0 | toolchain-wave | CVE-2026-56855, CVE-2026-78662 | 0.56.0 | WO-46 remediation candidate v3.6.16, eligible 2026-11-05T23:00:22Z; fixed package/build still requires a full rescan |
| etcd | golang.org/x/net v0.58.0 | toolchain-wave | CVE-2026-78659, CVE-2026-78660, CVE-2026-78669, CVE-2026-97032 | 0.60.0 | WO-46 remediation candidate v3.6.16, eligible 2026-11-05T23:00:22Z; fixed package/build still requires a full rescan |
| etcd | stdlib go1.26.8 | toolchain-wave | CVE-2026-56866, CVE-2026-78659, CVE-2026-78660, CVE-2026-78667, CVE-2026-78669, CVE-2026-94439, CVE-2026-94440, CVE-2026-97031, CVE-2026-97032 | 1.26.9, 1.27.2 | WO-46 remediation candidate v3.6.16, eligible 2026-11-05T23:00:22Z; fixed package/build still requires a full rescan |
| keycloak | guava 33.6.0-jre | normal | CVE-2026-102554 | 33.7.2 | No verified fixed same-line image release or eligibility date; WO-46 must track upstream and rescan before promotion |
| openbao | github.com/go-jose/go-jose/v4 v4.1.4 | normal | CVE-2026-116587 | 4.1.6 | WO-46 remediation candidate v2.7.2, eligible 2026-11-09T20:24:37Z; fixed package/build still requires a full rescan |
| openbao | golang.org/x/net v0.58.0 | toolchain-wave | CVE-2026-78659, CVE-2026-78660, CVE-2026-78669, CVE-2026-97032 | 0.60.0 | WO-46 remediation candidate v2.7.2, eligible 2026-11-09T20:24:37Z; fixed package/build still requires a full rescan |
| openbao | stdlib go1.27.1 | toolchain-wave | CVE-2026-56866, CVE-2026-78659, CVE-2026-78660, CVE-2026-78667, CVE-2026-78669, CVE-2026-94439, CVE-2026-94440, CVE-2026-97031, CVE-2026-97032 | 1.26.9, 1.27.2 | WO-46 remediation candidate v2.7.2, eligible 2026-11-09T20:24:37Z; fixed package/build still requires a full rescan |
| openbao | zlib 1.3.2-r0 | normal | CVE-2026-85091 | 1.3.2-r1 | WO-46 remediation candidate v2.7.2, eligible 2026-11-09T20:24:37Z; fixed package/build still requires a full rescan |
| operator | github.com/go-jose/go-jose/v4 v4.1.4 | normal | CVE-2026-116587 | 4.1.6 | WO-46 remediation candidate v1.20.4, eligible 2026-11-06T14:51:39Z; fixed package/build still requires a full rescan |
| operator | github.com/klauspost/compress v1.18.6 | normal | CVE-2026-63209 | 1.18.7 | WO-46 remediation candidate v1.20.4, eligible 2026-11-06T14:51:39Z; fixed package/build still requires a full rescan |
| operator | go.etcd.io/etcd/client/pkg/v3 v3.6.12 | normal | CVE-2026-73500 | 3.5.33, 3.6.14, 3.7.1 | WO-46 remediation candidate v1.20.4, eligible 2026-11-06T14:51:39Z; fixed package/build still requires a full rescan |
| operator | golang.org/x/crypto v0.53.0 | toolchain-wave | CVE-2026-56854, CVE-2026-56855, CVE-2026-78662 | 0.55.0, 0.56.0 | WO-46 remediation candidate v1.20.4, eligible 2026-11-06T14:51:39Z; fixed package/build still requires a full rescan |
| operator | golang.org/x/net v0.56.0 | toolchain-wave | CVE-2026-78659, CVE-2026-78660, CVE-2026-78669, CVE-2026-97032 | 0.60.0 | WO-46 remediation candidate v1.20.4, eligible 2026-11-06T14:51:39Z; fixed package/build still requires a full rescan |
| operator | golang.org/x/text v0.39.0 | toolchain-wave | CVE-2026-56851 | 0.41.0 | WO-46 remediation candidate v1.20.4, eligible 2026-11-06T14:51:39Z; fixed package/build still requires a full rescan |
| operator | google.golang.org/grpc v1.83.1 | normal | CVE-2026-84445 | 1.83.2 | WO-46 remediation candidate v1.20.4, eligible 2026-11-06T14:51:39Z; fixed package/build still requires a full rescan |
| operator | stdlib go1.26.8 | toolchain-wave | CVE-2026-56866, CVE-2026-78659, CVE-2026-78660, CVE-2026-78667, CVE-2026-78669, CVE-2026-94439, CVE-2026-94440, CVE-2026-97031, CVE-2026-97032 | 1.26.9, 1.27.2 | WO-46 remediation candidate v1.20.4, eligible 2026-11-06T14:51:39Z; fixed package/build still requires a full rescan |
| scheduler | go.etcd.io/etcd/client/pkg/v3 v3.6.8 | normal | CVE-2026-73500 | 3.5.33, 3.6.14, 3.7.1 | WO-46 remediation candidate v1.36.6, eligible 2026-11-11T04:56:35Z; fixed package/build still requires a full rescan |
| scheduler | go.opentelemetry.io/otel/sdk v1.40.0 | normal | CVE-2026-39883 | 1.43.0 | WO-46 remediation candidate v1.36.6, eligible 2026-11-11T04:56:35Z; fixed package/build still requires a full rescan |
| scheduler | golang.org/x/crypto v0.53.0 | toolchain-wave | CVE-2026-56854, CVE-2026-56855, CVE-2026-78662 | 0.55.0, 0.56.0 | WO-46 remediation candidate v1.36.6, eligible 2026-11-11T04:56:35Z; fixed package/build still requires a full rescan |
| scheduler | golang.org/x/net v0.56.0 | toolchain-wave | CVE-2026-78659, CVE-2026-78660, CVE-2026-78669, CVE-2026-97032 | 0.60.0 | WO-46 remediation candidate v1.36.6, eligible 2026-11-11T04:56:35Z; fixed package/build still requires a full rescan |
| scheduler | golang.org/x/text v0.39.0 | toolchain-wave | CVE-2026-56851 | 0.41.0 | WO-46 remediation candidate v1.36.6, eligible 2026-11-11T04:56:35Z; fixed package/build still requires a full rescan |
| scheduler | google.golang.org/grpc v1.79.3 | normal | CVE-2026-84304, CVE-2026-84445, GHSA-hrxh-6v49-42gf | 1.82.1, 1.82.2, 1.83.1 | WO-46 remediation candidate v1.36.6, eligible 2026-11-11T04:56:35Z; fixed package/build still requires a full rescan |
| scheduler | stdlib go1.26.8 | toolchain-wave | CVE-2026-56866, CVE-2026-78659, CVE-2026-78660, CVE-2026-78667, CVE-2026-78669, CVE-2026-94439, CVE-2026-94440, CVE-2026-97031, CVE-2026-97032 | 1.26.9, 1.27.2 | WO-46 remediation candidate v1.36.6, eligible 2026-11-11T04:56:35Z; fixed package/build still requires a full rescan |
| valkey | zlib 1.3.2-r0 | normal | CVE-2026-85091 | 1.3.2-r1 | WO-46 remediation candidate 8.1.11, eligible 2026-11-09T23:27:52Z; fixed package/build still requires a full rescan |

## Each remaining Critical: individual renewal

Fix/advisory URLs and exact image paths are retained per row in the [machine-readable ledger](../../security/security-wave-2026-10-review.json). Reachability is conservatively potentially reachable; no unproven negative result is used to lower severity.

| Image | Package/version | Advisory | Fix | Expiry | Primary fix/advisory reference |
| --- | --- | --- | --- | --- | --- |
| apisix | perl-base 5.36.0-7+deb12u3 | CVE-2026-12087 | 5.36.0-7+deb12u4 | 2026-11-27 | https://security-tracker.debian.org/tracker/CVE-2026-12087 |
| apisix | perl-base 5.36.0-7+deb12u3 | CVE-2026-13221 | 5.36.0-7+deb12u4 | 2026-11-27 | https://security-tracker.debian.org/tracker/CVE-2026-13221 |
| apisix | perl-base 5.36.0-7+deb12u3 | CVE-2026-42496 | 5.36.0-7+deb12u4 | 2026-11-27 | https://security-tracker.debian.org/tracker/CVE-2026-42496 |
| apisix | perl-base 5.36.0-7+deb12u3 | CVE-2026-57433 | 5.36.0-7+deb12u4 | 2026-11-27 | https://security-tracker.debian.org/tracker/CVE-2026-57433 |
| apisix | perl-base 5.36.0-7+deb12u3 | CVE-2026-8376 | 5.36.0-7+deb12u4 | 2026-11-27 | https://security-tracker.debian.org/tracker/CVE-2026-8376 |
| openbao | golang.org/x/net v0.58.0 | CVE-2026-78663 | 0.60.0 | 2026-11-27 | https://go.dev/cl/847187 |
| openbao | stdlib go1.27.1 | CVE-2026-56857 | 1.26.9, 1.27.2 | 2026-11-27 | https://go.dev/cl/847305 |
| openbao | stdlib go1.27.1 | CVE-2026-78663 | 1.27.2 | 2026-11-27 | https://go.dev/cl/847187 |
| cnpg | golang.org/x/net v0.58.0 | CVE-2026-78663 | 0.60.0 | 2026-11-27 | https://go.dev/cl/847187 |
| cnpg | stdlib go1.27.1 | CVE-2026-56857 | 1.26.9, 1.27.2 | 2026-11-27 | https://go.dev/cl/847305 |
| cnpg | stdlib go1.27.1 | CVE-2026-78663 | 1.27.2 | 2026-11-27 | https://go.dev/cl/847187 |
| argocd | golang.org/x/crypto v0.36.0 | CVE-2026-39830 | 0.52.0 | 2026-11-27 | https://go.dev/cl/781640 |
| argocd | golang.org/x/crypto v0.36.0 | CVE-2026-39831 | 0.52.0 | 2026-11-27 | https://go.dev/cl/781662 |
| argocd | golang.org/x/crypto v0.36.0 | CVE-2026-39832 | 0.52.0 | 2026-11-27 | https://go.dev/cl/778642 |
| argocd | golang.org/x/crypto v0.36.0 | CVE-2026-39833 | 0.52.0 | 2026-11-27 | https://go.dev/cl/778640 |
| argocd | golang.org/x/crypto v0.36.0 | CVE-2026-39834 | 0.52.0 | 2026-11-27 | https://go.dev/cl/781663 |
| argocd | golang.org/x/crypto v0.36.0 | CVE-2026-42508 | 0.52.0 | 2026-11-27 | https://go.dev/cl/781220 |
| argocd | golang.org/x/crypto v0.36.0 | CVE-2026-46595 | 0.52.0 | 2026-11-27 | https://go.dev/cl/781642 |
| argocd | golang.org/x/net v0.38.0 | CVE-2026-78663 | 0.60.0 | 2026-11-27 | https://go.dev/cl/847187 |
| argocd | golang.org/x/net v0.40.0 | CVE-2026-78663 | 0.60.0 | 2026-11-27 | https://go.dev/cl/847187 |
| argocd | golang.org/x/net v0.55.0 | CVE-2026-78663 | 0.60.0 | 2026-11-27 | https://go.dev/cl/847187 |
| argocd | golang.org/x/net v0.59.0 | CVE-2026-78663 | 0.60.0 | 2026-11-27 | https://go.dev/cl/847187 |
| argocd | stdlib go1.24.0 | CVE-2025-22871 | 1.23.8, 1.24.2 | 2026-11-27 | https://go.dev/cl/652998 |
| argocd | stdlib go1.24.0 | CVE-2025-68121 | 1.24.13, 1.25.7, 1.26.0-rc.3 | 2026-11-27 | https://go.dev/cl/737700 |
| argocd | stdlib go1.24.0 | CVE-2026-56857 | 1.26.9, 1.27.2 | 2026-11-27 | https://go.dev/cl/847305 |
| argocd | stdlib go1.24.0 | CVE-2026-78663 | 1.26.9 | 2026-11-27 | https://go.dev/cl/847187 |
| argocd | stdlib go1.25.3 | CVE-2025-68121 | 1.24.13, 1.25.7, 1.26.0-rc.3 | 2026-11-27 | https://go.dev/cl/737700 |
| argocd | stdlib go1.25.3 | CVE-2026-56857 | 1.26.9, 1.27.2 | 2026-11-27 | https://go.dev/cl/847305 |
| argocd | stdlib go1.25.3 | CVE-2026-78663 | 1.26.9 | 2026-11-27 | https://go.dev/cl/847187 |
| argocd | stdlib go1.26.2 | CVE-2026-56857 | 1.26.9, 1.27.2 | 2026-11-27 | https://go.dev/cl/847305 |
| argocd | stdlib go1.26.2 | CVE-2026-78663 | 1.26.9 | 2026-11-27 | https://go.dev/cl/847187 |
| argocd | stdlib go1.26.4 | CVE-2026-56857 | 1.26.9, 1.27.2 | 2026-11-27 | https://go.dev/cl/847305 |
| argocd | stdlib go1.26.4 | CVE-2026-78663 | 1.26.9 | 2026-11-27 | https://go.dev/cl/847187 |
| envoy | golang.org/x/net v0.58.0 | CVE-2026-78663 | 0.60.0 | 2026-11-27 | https://go.dev/cl/847187 |
| envoy | stdlib go1.27.1 | CVE-2026-56857 | 1.26.9, 1.27.2 | 2026-11-27 | https://go.dev/cl/847305 |
| envoy | stdlib go1.27.1 | CVE-2026-78663 | 1.27.2 | 2026-11-27 | https://go.dev/cl/847187 |
| cilium | golang.org/x/net v0.56.0 | CVE-2026-78663 | 0.60.0 | 2026-11-27 | https://go.dev/cl/847187 |
| cilium | stdlib go1.26.5 | CVE-2026-56857 | 1.26.9, 1.27.2 | 2026-11-27 | https://go.dev/cl/847305 |
| cilium | stdlib go1.26.5 | CVE-2026-78663 | 1.26.9 | 2026-11-27 | https://go.dev/cl/847187 |
| cilium | stdlib go1.26.8 | CVE-2026-56857 | 1.26.9, 1.27.2 | 2026-11-27 | https://go.dev/cl/847305 |
| cilium | stdlib go1.26.8 | CVE-2026-78663 | 1.26.9 | 2026-11-27 | https://go.dev/cl/847187 |
| operator | golang.org/x/net v0.56.0 | CVE-2026-78663 | 0.60.0 | 2026-11-27 | https://go.dev/cl/847187 |
| operator | stdlib go1.26.8 | CVE-2026-56857 | 1.26.9, 1.27.2 | 2026-11-27 | https://go.dev/cl/847305 |
| operator | stdlib go1.26.8 | CVE-2026-78663 | 1.26.9 | 2026-11-27 | https://go.dev/cl/847187 |
| coredns | golang.org/x/net v0.57.0 | CVE-2026-78663 | 0.60.0 | 2026-11-27 | https://go.dev/cl/847187 |
| coredns | stdlib go1.26.6 | CVE-2026-56857 | 1.26.9, 1.27.2 | 2026-11-27 | https://go.dev/cl/847305 |
| coredns | stdlib go1.26.6 | CVE-2026-78663 | 1.26.9 | 2026-11-27 | https://go.dev/cl/847187 |
| etcd | golang.org/x/net v0.58.0 | CVE-2026-78663 | 0.60.0 | 2026-11-27 | https://go.dev/cl/847187 |
| etcd | stdlib go1.26.8 | CVE-2026-56857 | 1.26.9, 1.27.2 | 2026-11-27 | https://go.dev/cl/847305 |
| etcd | stdlib go1.26.8 | CVE-2026-78663 | 1.26.9 | 2026-11-27 | https://go.dev/cl/847187 |
| apiserver | golang.org/x/net v0.56.0 | CVE-2026-78663 | 0.60.0 | 2026-11-27 | https://go.dev/cl/847187 |
| apiserver | stdlib go1.26.8 | CVE-2026-56857 | 1.26.9, 1.27.2 | 2026-11-27 | https://go.dev/cl/847305 |
| apiserver | stdlib go1.26.8 | CVE-2026-78663 | 1.26.9 | 2026-11-27 | https://go.dev/cl/847187 |
| controller | golang.org/x/net v0.56.0 | CVE-2026-78663 | 0.60.0 | 2026-11-27 | https://go.dev/cl/847187 |
| controller | stdlib go1.26.8 | CVE-2026-56857 | 1.26.9, 1.27.2 | 2026-11-27 | https://go.dev/cl/847305 |
| controller | stdlib go1.26.8 | CVE-2026-78663 | 1.26.9 | 2026-11-27 | https://go.dev/cl/847187 |
| scheduler | golang.org/x/net v0.56.0 | CVE-2026-78663 | 0.60.0 | 2026-11-27 | https://go.dev/cl/847187 |
| scheduler | stdlib go1.26.8 | CVE-2026-56857 | 1.26.9, 1.27.2 | 2026-11-27 | https://go.dev/cl/847305 |
| scheduler | stdlib go1.26.8 | CVE-2026-78663 | 1.26.9 | 2026-11-27 | https://go.dev/cl/847187 |

## Fixed prior exception rows

| Old target | Package/version | Advisory | Evidence |
| --- | --- | --- | --- |
| docker.io/ministackorg/ministack@sha256:11d7308bfc75029d55625b9525e84a2401431ed1ff2148c6311800ff5009ae9c | python 3.13.15 | CVE-2026-19445 | https://github.com/amazen33/twinfra/actions/runs/40767198838 |
| quay.io/argoproj/argocd@sha256:dd3f47d5a5e4da563a7a398506e892481b358a7cec50abdf320c71aa55904bfa | github.com/argoproj/argo-cd/v3 v3.5.3+dirty | CVE-2026-55797 | https://github.com/amazen33/twinfra/actions/runs/40767198838 |
| quay.io/argoproj/argocd@sha256:dd3f47d5a5e4da563a7a398506e892481b358a7cec50abdf320c71aa55904bfa | github.com/argoproj/argo-cd/v3 v3.5.3+dirty | CVE-2026-77459 | https://github.com/amazen33/twinfra/actions/runs/40767198838 |
