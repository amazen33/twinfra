# ADR-0049 Amendment 1: the toolchain-wave rule

**Status:** Accepted (owner, 2026-10-16: "toolchain-wave rule approved").

## Context

In October 2026, GO-2026-6612 (x/net HTTP/2, CVE-2026-78663) and GO-2026-6604 (stdlib) affect **every Go binary built before Go 1.26.9 and x/net 0.60.0**. That includes most of Kubernetes' ecosystem (etcd, CoreDNS, Argo CD, Perses, the Barman plugin, cert-manager, OpenBao and External Secrets are likely). Each upstream rebuilds on its own schedule.
Without a rule, every Foundation 1.0 work order stops at the same findings, and the owner decides the same question again for each one.

## Rule

1. A **toolchain-wave advisory** is one fixed only by a newer language toolchain or core library (for Go: the stdlib, `golang.org/x/net`, `x/crypto`, `x/text`, `x/sys`). The owner names it in this amendment's list.
   Current list: GO-2026-6612 / CVE-2026-78663, GO-2026-6604 / CVE-2026-56857, and the x/crypto, x/net and x/text Highs fixed by x/crypto 0.56.0, x/net 0.60.0 and x/text 0.41.0.
2. A new or upgraded component whose **only** blocking findings are listed toolchain-wave advisories may be admitted when **all** of these hold:
   - no upstream release built with the fixed toolchain is eligible yet (14-day rule);
   - none of the advisories is on the CISA KEV list;
   - the component is not reachable from outside the cluster or LAN;
   - its controls are listed in each entry.
3. Entries stay **per image and per CVE** (no blanket waivers; ADR-0049 is unchanged): Critical 30 days, High 60 days, `approvedBy` the owner, approved as a batch in the PR that admits the component.
4. **Replacement duty.** When an eligible upstream release with the fixed toolchain appears (the WO-32 weekly watch reports it), open the refresh PR within 14 days. If an advisory reaches KEV, the expedite rule applies at once.
5. **No self-rebuilding** of upstream binaries to dodge the rule, unless the owner approves a specific reproducible rebuild work order.
