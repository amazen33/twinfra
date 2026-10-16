# WO-09 backup components and corresponding source

Owner licence approval: Ahmed Mazen (`amazen33`), 2026-10-16,
[ADR-0054](../../../docs/adr/0054-licence-ladder-and-enterprise-grade-gate.md)
and [WO-09 Amendment 2](../../../docs/work-orders/WO-09-backups-and-restore-drill.md).
This approval grants no vulnerability exception or commercial legal clearance.

| Component | Licence | Source and distribution boundary |
| --- | --- | --- |
| Official Barman plugin 0.15.1 | Apache-2.0 | [Unmodified upstream](https://github.com/cloudnative-pg/plugin-barman-cloud/tree/v0.15.1); manager and sidecar remain separate containers |
| Barman 3.20.1 | GPL-3.0-only | [Corresponding source](https://pypi.org/project/barman/3.20.1/#files); exact archive URL and SHA-256 in `deploy/common/backup-artifacts.lock.json`; only the official sidecar process imports it |
| psycopg2 2.9.13 | LGPL-3.0-or-later, additional OpenSSL permission | [Corresponding source](https://pypi.org/project/psycopg2/2.9.13/#files); exact archive URL/hash in the same lock; unmodified dynamically imported dependency inside that sidecar |
| OpenSSL 3.5.7, Debian 3.5.7-1~deb13u3 | Apache-2.0 | [Upstream source/licence](https://github.com/openssl/openssl/tree/openssl-3.5.7); already present in the admitted Python base; no installation or modification |
| boto3 1.43.108 and SDK dependencies | Apache-2.0 / individually registered permissive licences | Hash-locked existing SDK wheels; upstream licence files remain in their dist-info directories inside the backup image |

The adjacent licence texts are copied verbatim from the verified source archives.
The GPL text applies to Barman; the psycopg2 LICENSE and LGPL text preserve its
copyright, exception and redistribution terms. The complete official image must
also retain its original base-OS and dependency notices.

Corresponding-source offer: recipients of a redistributed Barman sidecar can
request its complete matching source, build/install material and licence notices
from the repository owner through a [source request](https://github.com/amazen33/twinfra/issues/new).
Keep that material available for at least three years after the last distribution,
and longer where the applicable licence requires. Supply it without a licence fee;
only reasonable physical delivery costs may be charged. Preserve upstream
relinking/replacement rights for LGPL components. Before any commercial release,
the owner/legal reviewer must validate the complete image's corresponding source
and offer, not just these two top-level packages. No Twinfra code links to Barman.

No new image SBOM baseline is granted here. Complete Linux image SBOMs and scans
remain CI artifacts under ADR-0049; their licence review is a draft-readiness gate.
