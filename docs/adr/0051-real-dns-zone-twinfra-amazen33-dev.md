# ADR-0051: Real DNS names under `twinfra.amazen33.dev`

**Status:** Accepted (owner, 2026-10-14: "subdomain twinfra.amazen33.dev, and you will lead me to complete the task").
**Author:** Claude. **Amends:** ADR-0038 and ADR-0046. Their `twinfra.example.com` names remain the **internal** names.

## Context

- Today, clients reach `cairo-1` through internal names such as `api.dev.cairo-1.twinfra.example.com`, which hosts-file entries resolve on the Dell and the laptop.
- The owner's zone `amazen33.dev` is served by Cloudflare (`maxim` and `wally.ns.cloudflare.com`).
- ADR-0050 introduces a virtual IP for the API. A public DNS name lets clients find it without editing hosts files, and it later allows publicly trusted TLS certificates.

## Decision

1. **Mirror the internal names under `twinfra.amazen33.dev`.** For example, the API becomes `api.dev.cairo-1.twinfra.amazen33.dev`.
2. **DNS-only records** (grey cloud, never proxied) pointing at **private LAN addresses**. Nothing becomes reachable from the internet; the names only resolve. The owner accepts that public DNS shows a private address.
3. **The internal names stay** as `controlPlaneEndpoint`, in kubeconfigs and in the generated hosts entries.
   - The real API name is **added** as an extra certificate name in WO-33 Part D.
   - The internal `controlPlaneEndpoint` is not renamed: that would touch every kubeconfig and Cilium's API host setting, for no gain.
4. **The owner manages the records** in Cloudflare, with Claude guiding the steps. No Cloudflare credential is stored in Twinfra.
5. **Later, after WO-08:** publicly trusted TLS through Let's Encrypt DNS-01, using a **zone-scoped Cloudflare API token** (DNS edit on `amazen33.dev` only) kept in OpenBao. That needs its own work order and passes the licence gate (cert-manager).

## Records

| Name | Type | Value | When |
| --- | --- | --- | --- |
| `api.dev.cairo-1.twinfra.amazen33.dev` | A, DNS only | `192.168.1.3` now; the VIP after WO-33 Part D | Now |
| Others (`console`, `aws`, …) | — | — | Not yet: they are reached only through tunnels |
