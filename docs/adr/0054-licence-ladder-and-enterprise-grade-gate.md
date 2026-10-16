# ADR-0054: The licence ladder and the enterprise-grade gate (amends ADR-0030, ADR-0042, ADR-0044)

**Status:** Accepted (owner, 2026-10-16: "ADR-0054 approved, Barman approved"), from the owner's direction: "if an MIT tool has no enterprise grade and stability, move to Apache; if none under Apache, go up the ladder".
**Author:** Claude (platform architecture). **Decider:** Ahmed Mazen, Owner and Product Owner.

## Context

ADR-0030 is MIT-first and allows other permissive licences. ADR-0044 added classes for build tools, base OS, weak copyleft and disabled modules. What is missing is a rule for when the most permissive option is **not good enough for an enterprise**.
WO-09 showed the case: pgBackRest (MIT) is mature, but its CloudNativePG plugin is experimental (v0.0.3). CNPG's mature, official path, Barman, is GPL-3.0.

## Decision

1. **The ladder.** For each component, choose the **most permissive tier that has a candidate passing the enterprise-grade gate** (decision 2):

   | Tier | Licences | Conditions |
   | --- | --- | --- |
   | 1 | MIT, MIT-0, BSD-2/3-Clause, ISC, 0BSD, PostgreSQL, Zlib, PSF, Unlicense, CC0, BlueOak | None beyond notices |
   | 2 | Apache-2.0 (it adds an explicit patent grant) | Notices; NOTICE file |
   | 3 | Weak copyleft: MPL-2.0, LGPL-2.1/3.0, EPL-2.0 | Unmodified; a separate unit or dynamic linking; notices plus a source offer; the owner approves the component |
   | 4 | Strong copyleft: GPL-2.0/3.0 | Only as a **separate, unmodified program in its own process or container**, never linked into or merged with Twinfra code; notices plus a source offer; the owner approves the component (an exception record); legal review before any commercial release |
   | Never | AGPL, SSPL, BUSL, Elastic, Commons Clause, source-available or account-gated terms; proprietary EULAs in shipped components | Proprietary images may only be operator-pulled (ADR-0044). OpenBao (MPL-2.0) stays the recorded exception it is today |

   Build-time-only tools keep the ADR-0042 rules.
2. **The enterprise-grade gate.** A candidate passes only if every item is true, with the evidence recorded in the licence register (`enterpriseGrade`: per-criterion result, evidence link, date):
   - **Maturity:** a stable release (1.0 or later, or declared production-ready by the project); not experimental, alpha or beta.
   - **Governance:** hosted by a foundation (CNCF, ASF, LF, OpenSSF, PostgreSQL), **or** at least 3 active maintainers from at least 2 organisations, **or** a vendor offering commercial support.
   - **Activity and support:** a release within the last 6 months, a published supported-version or LTS policy, and security fixes delivered.
   - **Security process:** a published disclosure policy (SECURITY.md or equivalent) and CVE handling. Releases are signed or checksummed. The OpenSSF Scorecard is recorded where available, with a target of 6 or more.
   - **Supply chain:** digest-pinnable artifacts, and an SBOM is available or can be generated (Syft), passing the ADR-0049 gate.
   - **Adoption:** public production adopters, or CNCF Graduated or Incubating status.
3. **The climbing record.** If a component is taken from tier 3 or 4, its record lists the higher-tier candidates that were rejected and the gate criterion each one failed. Re-evaluate at every minor upgrade, or every 6 months. When a more permissive candidate passes the gate, open a replacement work order.
4. **Certification readiness (no claims).** These principles create the evidence that enterprise assessments such as ISO/IEC 27001 and SOC 2 look for:
   - supplier evaluation (this gate);
   - asset inventory (the licence register and SBOMs);
   - vulnerability management (ADR-0049);
   - change management (PR gates and owner approval);
   - evidence-based acceptance (ADR-0052);
   - backups and restore (WO-09);
   - incident records (postmortems).

   A controls map (Annex A or Trust Services Criteria → Twinfra evidence) is a later work order. **No certification is claimed** until an accredited audit is passed.

## Consequences

The licence choice becomes a recorded engineering decision, not a preference. Permissive stays the default. Copyleft enters only when nothing more permissive is enterprise-grade, always as a separate, unmodified, owner-approved component, and it is replaced when something better matures.

**First application (WO-09):**
- pgBackRest (MIT) is mature, but its CNPG plugins (Dalibo and Opera, Apache-2.0) **fail the maturity criterion** (experimental, v0.0.x).
- WAL-G (Apache-2.0) has no CNPG integration.
- So **Barman Cloud (GPL-3.0)**, in its own plugin sidecar container and unmodified, is the tier-4 choice. psycopg2 (LGPL) is tier 3. Both need the owner's approval.
- The pgBackRest plugin is re-evaluated every 6 months, and when it reaches a stable release.
