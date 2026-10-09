# ADR-0030: Licence policy, MIT-first

**Status:** Accepted (owner, 2026-10-08)
**Author:** Claude (platform architecture). **Decider:** vCloud owner. **Records:** D2.

## Decision

1. All vCloud code is MIT. Upstream LICENSE and NOTICE files ship with what we redistribute.
2. Third-party components must use one of these licences: MIT, MIT-0, Apache-2.0,
   BSD-2-Clause, BSD-3-Clause, ISC, 0BSD or PostgreSQL.
3. The only exception is **OpenBao (MPL-2.0)**. It runs unmodified as a separate service.
   Applications reach it only through External Secrets Operator or the vCloud gateway (KMS, Secrets Manager, SSM).
   Modifying OpenBao's files requires a new ADR.
4. Excluded: AGPL, GPL, LGPL, SSPL, BSL, source-available licences, the Elastic License, and any
   component that needs a vendor account or token to run.
5. Every component is recorded in `security/licence-register.json` with its SPDX ID and the
   LICENSE source at the pinned version. CI enforces the register (WO-02).

## Consequences for current components

| Component | Licence issue | Action |
| --- | --- | --- |
| Grafana 13.2.3 (lab) | AGPL-3.0 | Replace with Perses (WO-07); ADR-0010 superseded by ADR-0034 |
| LocalStack Community 4.14.0 (lab) | Account and token required for releases since 2026-03 | Remove (WO-06); ADR-0025 superseded |
| Spinifex (Module 5b reference) | AGPL core | Not deployed; ADR-0018 superseded; KubeVirt and Cluster API replace it |
| MinIO | AGPL; repository archived | Never deployed; stays excluded |
| ScyllaDB Alternator | Source-available | Not used; ExtendDB (Apache-2.0) instead |
| Terraform / OpenTofu | BSL / MPL-2.0 | Not used; Crossplane (ADR-0031) |
| Upbound official provider builds | Commercial terms | Use crossplane-contrib builds (Apache-2.0) |
| Elasticsearch, Kibana, Loki, Tempo, Mimir | SSPL, Elastic License, AGPL | Excluded; OpenSearch and Jaeger instead |

## Notes

Licences were verified on 2026-10-08 from each project's LICENSE file or GitHub licence record.
Licences can change at any release, so the register records evidence per pinned version.
This ADR is an engineering policy, not legal advice. The owner's legal reviewer confirms it before
any commercial release.
