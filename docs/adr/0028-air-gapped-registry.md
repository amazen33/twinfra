# ADR-0020: Air-Gapped Registry Mirroring and Image Pull Policy Standards

**Status:** Accepted for implementation; offline cold-start acceptance pending.
**Date:** 2026-10-07
**Deciders:** vCloud platform owner and Principal Platform Architect
**Scope:** Architecture registry catalog; this record does not replace the
legacy [delivery ADR-0020](../../adr-0020-module-3-delivery.md).

## Context

The repo-server attempted a manifest lookup on `registry.vcloud.example.com`
through node resolver `10.255.255.254` and received `no such host`. The successful
init container did not establish current registry availability. The upstream
Argo main containers request `Always`, while a versioned init image can default
to `IfNotPresent`. Runtime cache contents and registry resolution are separate.
The registry repository layout includes upstream names, for example
`quay.io/argoproj/argocd`. A bare mirror endpoint does not insert that prefix.

## Decision

1. Explicit `IfNotPresent` applies to every container and init container in
   rendered local platform overlays. Conftest rejects `Always`, `Never` and an
   omitted policy. Strict kubeconform validates the complete render without skips.
2. Pin Argo CD 3.5.3 to its verified OCI digest. Both full Argo and WSL Core use
   the same lock. Canonical references start with `registry.vcloud.example.com/`.
   Other full-profile dependencies have explicit semantic versions; digest
   promotion for these remains an artifact provenance improvement.
3. Generate per-upstream `hosts.toml` files with API roots such as
   `https://registry.vcloud.example.com/v2/quay.io` and `override_path=true`.
   Configure the final `server` with the same root and settings, preventing an
   upstream fallback or an extra `/v2` suffix. Canonical registry references use
   its ordinary `/v2` endpoint and do not get a second upstream prefix.
4. Verify node DNS and TLS on port 443. An optional explicit registry IP may be
   written to `/etc/hosts` only after TLS hostname verification and a registry
   `/v2/` response succeed using the approved CA. Never guess an address, disable
   WSL DNS tunneling, replace the node resolver with public DNS, or skip TLS.
5. Validate exact canonical names/digests through the active external CRI before
   rollout. The explicit cache-only profile tolerates mirror outages only with a
   complete cache. An empty cache requires an offline image import or a reachable
   internal mirror; `IfNotPresent` cannot manufacture image content.
6. Reference `vcloud-registry-cred` on Argo Pod templates and ServiceAccounts.
   Provision it per namespace through the approved secret lifecycle. No registry
   credentials enter Git, shell arguments, host-file headers or node reports.
7. The full `argocd` overlay is an explicitly selected profile. Existing WSL Core
   remains in `platform-services`; neither script installs a competing controller
   or migrates ownership. Existing Cilium host/firewall exceptions remain unchanged.

## Options considered

| Option | Assessment |
| --- | --- |
| Private registry + complete offline cache + explicit policy | Selected; requires maintained image inventory and imports |
| `Always` with upstream fallback | Depends on remote resolution and permits unreviewed egress |
| `Never` everywhere | Cannot recover a missing image from an available internal registry |
| Bare endpoint + `override_path=true` | Incorrect API path for this canonical repository layout |
| DNS hosts entry without certificate verification | Can direct the node to an untrusted endpoint |

## Consequences

Registry changes require operator-supplied site addresses and public CA material.
Cache aliases are part of node readiness, not just image layers. Image updates
require lock changes, staging and review; tag mutation cannot silently advance
Argo. Host-file edits reload without restarting containerd; changes to its daemon
configuration require a controlled restart. Bootstrap scripts preserve unrelated
runtime fields and stop rather than discard existing authentication or CA settings.

## Action items and acceptance

- [x] Implement overlay, shared image pin, mirror generation and deployment gates.
- [x] Add policy, outage/cache and DNS/TLS regression tests to the CI harness.
- [ ] Accept offline cold-cache import and bootstrap with internet egress denied.
- [ ] Accept actual mirror DNS, approved CA, authenticated pulls and rollout.
- [ ] Confirm the single intended Argo installation and GitOps owner on the lab.

Implementation checks are distinct from these live gates. See the
[image-pull runbook](../../troubleshooting/image-pull-failures.md).
Primary contracts: [Kubernetes image policies](https://kubernetes.io/docs/concepts/containers/images/),
[containerd hosts](https://github.com/containerd/containerd/blob/main/docs/hosts.md),
and [containerd path parsing](https://github.com/containerd/containerd/blob/v2.2.2/core/remotes/docker/config/hosts.go).
