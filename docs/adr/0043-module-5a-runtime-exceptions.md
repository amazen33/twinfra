# ADR-0043: Time-boxed runtime exceptions for the Module 5a RAG image (amends ADR-0042 decision 4)

Amended by [ADR-0044](0044-licence-gate-scope-and-classes.md).

**Status:** Accepted (owner, 2026-10-09).
**Author:** Claude (platform architecture). **Decider:** Ahmed Mazen, Owner and Product Owner.

## Context

Applying the amended WO-02 found four runtime packages in the Module 5a RAG image
(`module-5a/requirements-runtime.lock.txt`, installed by `module-5a/images/rag.Dockerfile`) that no class allows:

| Package | Version | Licence | Why it is there |
| --- | --- | --- | --- |
| psycopg | 3.3.6 | LGPL-3.0-only | Hard dependency of `langchain-postgres` 0.0.19 |
| psycopg-binary | 3.3.6 | LGPL-3.0-only | Compiled speedups for psycopg |
| psycopg-pool | 3.3.3 | LGPL-3.0-only | Hard dependency of `langchain-postgres` |
| certifi | 2026.7.22 | MPL-2.0 | CA certificate bundle, used by `httpx` and `requests` |

They cannot be `build-tool`, because they ship in the image. The pipeline already pins `asyncpg` (Apache-2.0), but
`langchain-postgres` requires psycopg, so removing psycopg means replacing `langchain-postgres`. Module 5a is a **disabled
integration reference**: its RAG service is off and its Jobs are suspended until GPU, storage, TLS, secrets and database
acceptance pass. Nothing here is deployed today.

## Decision

1. **Record four time-boxed runtime exceptions** (E-1 to E-4) in the licence register, each citing this ADR. They are the only
   runtime exceptions besides OpenBao.
2. **Conditions for all four:**
   - used unmodified, installed from the hash-pinned lock, imported as ordinary Python packages (dynamic use, no static bundling,
     so a user can replace the library);
   - the image carries the licence texts and a notice listing package, version, licence and source URL (a source offer for the LGPL packages);
   - no copy of their source is vendored into Twinfra repositories.
3. **Expiry and enforcement.** Each exception expires **before Module 5a is enabled** or in 120 days, whichever is first.
   The licence gate fails if `enabled: true` is set in `module-5a/config/rag.yaml` while E-1, E-2 or E-3 is still registered.
   The exceptions therefore cannot reach a running service.
4. **Replacement plan (follow-up work order, before 5a is enabled).** Replace `langchain-postgres` with a thin Twinfra-owned
   pgvector store on `asyncpg` (Apache-2.0) and `pgvector-python` (MIT). That removes psycopg, psycopg-pool and psycopg-binary
   and the SQLAlchemy psycopg dialect from the image. `certifi` (E-4, MPL-2.0, a data bundle) may stay as a permanent,
   recorded weak-copyleft exception, or be replaced with the operating system trust store.
5. **Legal review.** The owner's legal reviewer confirms the LGPL position before any commercial release that includes this image (ADR-0030).

## Consequences

WO-02 can go green without weakening the permissive-only rule for anything that runs. The cost is one follow-up work order, and
a hard stop if someone tries to enable the RAG module before it is done. Because Module 5a is disabled, the exposure today is the
repository contents only.
