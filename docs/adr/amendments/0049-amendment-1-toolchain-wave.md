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

## Amendment 1a (2026-10-16, architect; Accepted (owner, 2026-10-16)): a rule instead of an ID list

Codex's cert-manager admission (WO-08) found five more stdlib Highs (GO-2026-6605, 6607, 6608, 6609, 6613), all fixed by Go 1.26.9 and in the same wave. A list of IDs goes stale within days. Replace the list in item 1 with a rule:

1. **A finding qualifies as toolchain-wave** when all of these hold, as reported by the pinned scanner and recorded in each entry:
   - the affected package is the Go standard library or a `golang.org/x/*` module maintained by the Go team (net, crypto, text, sys, mod and similar);
   - the only fix is a newer release of that same toolchain line or module (for the Go standard library: the newest patch of the minor line the image was built with, currently 1.26.9; for the x/ modules: the fixed version the scanner reports);
   - it is not on the CISA KEV list.
2. **Anything else blocks.** Findings in other packages (grpc, etcd client, cryptography libraries outside the Go team, OS packages, application code) do not qualify and must be fixed or separately approved. The PR lists every qualifying and every non-qualifying finding per image.
3. All the other conditions of Amendment 1 stand: per image and per CVE entries; 30 days for Critical and 60 days for High; `approvedBy` the owner, approved as a batch in the PR; the controls listed; no eligible upstream release built with the fixed toolchain; not reachable from outside; and a refresh PR within 14 days of an eligible fixed release.
4. **Landing.** The rule, ADR-0054 and its gate must reach `main` independently of the backup work: split them out of draft PR #65 into their own PR first.
