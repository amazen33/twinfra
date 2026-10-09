# Third-party product notices

The [register](../licence-register.json) records exact versions, licence sources,
integrities and owner decisions. Open baseline findings in
[the evidence baseline](../licence-baseline.json) are not verified SBOMs.

OpenBao server 2.7.1, Helm chart 0.30.2 and CSI provider 2.0.3 are unmodified,
separate MPL-2.0 units under ADR-0044. Preserve upstream LICENSE and NOTICE files
when mirroring/distributing them. Their distributed notice evidence and the
provider/chart artifact hashes remain explicit, expiring baseline findings.
The original ADR-0030 OpenBao exception remains recorded in policy history.

The RAG image includes the [package notices](rag/NOTICE.md) and complete licence
texts at `/usr/share/licenses/vcloud-rag/`. The three psycopg LGPL exceptions
remain disabled and time-limited under ADR-0043/0044.

NVIDIA CUDA `12.4.1-base-ubuntu22.04` is an **operator-pulled reference** governed
by the [NVIDIA CUDA 12.4.1 EULA](https://docs.nvidia.com/cuda/archive/12.4.1/eula/index.html).
The CUDA smoke test defaults to false (`GPU_SMOKE_TEST`), independently of GPU
driver/runtime provisioning (`ENABLE_GPU=auto`). The operator must accept those
terms and obtain owner authorization before enabling the CUDA test; this project
does not grant NVIDIA rights or include CUDA in a first-party image. The licence gate rejects using
that reference as a Dockerfile base or enabling the default CUDA smoke-test switch.

Redis, Grafana and LocalStack are pending removal, not approved new platform
selections. Their frozen expiry dates and follow-up work orders appear in the
register and every successful CI licence report.
