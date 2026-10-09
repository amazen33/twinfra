# Module 5a: private GPU inference and pgvector RAG

This module provides a GPU Knative Service and an executable LangChain retrieval
pipeline for Twinfra. It is a disabled integration reference: no resource here is
included in the current Argo Applications. The GPU example requires an accepted
H100 node; the 20 GB WSL lab keeps AI/HPC bypassed.

| Deliverable | Source |
| --- | --- |
| One-GPU vLLM Knative Service | [vllm.knative.yaml](examples/vllm.knative.yaml) |
| Public RAG connection/vector configuration | [rag.yaml](config/rag.yaml) |
| Executable LangChain pipeline | [pipeline.py](rag/pipeline.py) |
| Paired CSI identities/configuration and Cilium policies | [integration.yaml](manifests/integration.yaml), [network.yaml](manifests/network.yaml) |
| Suspended query and ingestion Jobs | [rag-jobs.yaml](examples/rag-jobs.yaml) |
| Administrator-owned vector table/index and writer lifecycle | [migrate.sql](sql/migrate.sql) |
| Public OpenBao role/policy payloads | [query role](openbao/database-role-vcloud-rag-query.json), [ingest role](openbao/database-role-vcloud-rag-ingest.json), [reader policy](openbao/vcloud-rag.hcl), [writer policy](openbao/vcloud-rag-indexer.hcl) |
| CPU runtime image recipe | [rag.Dockerfile](images/rag.Dockerfile), [wheel lock](requirements-runtime.lock.txt) |
| Explicit model staging | [stage_module5a_models.py](../tools/stage_module5a_models.py) |

```text
External client -> APISIX + Keycloak -> authorized application
  -> RAG query (workload-apps, CPU MiniLM encoder, 384 normalized dimensions)
  -> CNPG + pgvector (platform-services, cosine HNSW, retrieve top 4)
  -> retrieved context + question -> Knative internal TLS/Kourier
  -> private vcloud-vllm (hpc-compute, H100 GPU) -> answer + source references

Trusted ingestion -> separate CSI writer lease -> same CPU encoder -> vector table
OpenBao -> CSI database.json (one paired username/password response per identity)
```

The inference server does not connect to PostgreSQL. The pipeline retrieves
documents before constructing the generation request. It uses the current
[`PGEngine` and `PGVectorStore` API](https://reference.langchain.com/python/langchain-postgres/v2/vectorstores/PGVectorStore),
SQLAlchemy's URL object and the native psycopg driver. Runtime code creates no
extension, schema, table or index. LCEL composes retrieval and generation; empty
retrieval returns a bounded response without calling vLLM.

## Inference resource and storage contract

The private service is `vcloud-vllm` in `hpc-compute`, matching Module 5b's
reference endpoint. When promoting this module, make Module 5a the single owner
of that Service/ServiceAccount; do not also apply the older Module 5b example.
The image is mirrored vLLM **0.31.0**, with explicit `IfNotPresent` pulling.
Record the approved mirrored image digest before promotion.

Each Pod requests/limits **one NVIDIA GPU**, requests 8 CPU / 80 GiB RAM and
limits 16 CPU / 96 GiB RAM. `runtimeClassName: nvidia` and the selectors require
an inference node labeled `vcloud.io/gpu-role=inference` and
`vcloud.io/gpu-profile=spinifex.gpu.h100.80gb.8x`. An accepted node profile has
eight H100 80 GB GPUs; this model uses one of those GPUs with tensor parallelism
one. It does not allocate all eight. Verify device-plugin capacity and CUDA
compatibility against the [pinned vLLM deployment documentation](https://docs.vllm.ai/en/v0.31.0/deployment/k8s/).

The model is **DeepSeek-R1-Distill-Qwen-32B**, revision
`711ad2ea6aa40cfca18895e8aca02ab92df1a746`, served as
`deepseek-r1-distill-qwen-32b`. The local model path, context bound of 4,096
tokens, GPU utilization 0.85 and logging flags are explicit
[vLLM serve settings](https://docs.vllm.ai/en/v0.31.0/cli/serve/).
This 32B profile is beyond the WSL lab's RAM and 6 GB laptop GPU capacity.

Supply vetted, prepopulated `vcloud-deepseek-models` and
`vcloud-rag-embeddings` PVCs in their consumers' namespaces, using an accepted
CSI driver or Local PVs. No application hostPath or storage adoption is allowed.
Mount weights read-only and make their files readable by UID/GID 65532 before
acceptance. Non-root workloads drop all capabilities, forbid privilege
escalation, use RuntimeDefault seccomp and have a read-only root filesystem.
Inference has bounded tmpfs `/tmp` (2 GiB) and `/dev/shm` (8 GiB), charged to
the Pod memory limit. A writable cache is not permission to download models.

Knative scale limits are **0–1 per revision**, concurrency one, initial scale
zero. A rollout can overlap old/new revisions; budget GPU capacity for that
overlap or retire the old revision before promotion. The startup probe allows
20 minutes and the owner patch gives a 30-minute progress deadline. A 32B cold
start can exceed the 150-second RAG HTTP budget: warm and accept the revision
before interactive tests, or review a minimum scale of one for sustained
latency. No claim of instantaneous GPU scale-from-zero is made.

Review the [feature flags](patches/knative-features.mergepatch.yaml),
[autoscaler settings](patches/knative-autoscaler.mergepatch.yaml) and
[deployment deadline](patches/knative-deployment.mergepatch.yaml) with the
existing Knative ConfigMap owner. They are merge-patch payloads, not standalone
resources. The validator checks their resulting ConfigMap shapes.
Knative's [feature-flag reference](https://knative.dev/docs/serving/configuration/feature-flags/)
describes the PVC, security context and scheduling opt-ins. Admission and
non-root GPU startup still require live acceptance with Knative 1.23.0.

## Database, secrets and trust prerequisites

Accept the existing CNPG cluster `vcloud-postgres` and its **pgvector 0.8.2**
extension in database `vcloud` first. Execute Module 4a's lifecycle bootstrap,
then this module's administrator migration on the current primary. The SQL
requires the local PostgreSQL administrator; the existing database container
remains UID 26 and remote superuser access remains disabled.

```bash
primary_pod=$(kubectl --context vcloud-prod-01 get cluster -n platform-services \
  vcloud-postgres -o jsonpath='{.status.currentPrimary}')
test -n "$primary_pod"
kubectl --context vcloud-prod-01 exec -i -n platform-services "$primary_pod" \
  -c postgres -- psql -U postgres -d vcloud -v ON_ERROR_STOP=1 < module-5a/sql/migrate.sql
```

The transaction creates an administrator-owned lifecycle function, an
application-owned UUID-keyed vector(384) collection and a cosine HNSW index.
It checks the existing schema/owner and rejects incompatible reuse. The query
lease inherits Module 4a's existing **read access to public tables**, including
this collection. The writer additionally inherits SELECT/INSERT/UPDATE only
on `vcloud_rag_documents`; neither identity creates DDL, deletes records or
receives Kubernetes RBAC. This reader role is not a tenant-isolation boundary.
Add reviewed RLS/collection isolation before sharing it across tenants.

Use the existing TLS-verified, nonsecret OpenBao administrative workflow to:

1. Preserve `vcloud-app-readonly` and `vcloud-validation` and extend
   `database/config/vcloud-postgres.allowed_roles` with `vcloud-rag-query` and
   `vcloud-rag-ingest`. Merge into its trusted connection input; never place the
   management password or a serialized credential-bearing DSN in Git or argv.
2. Write the two public `database-role-*.json` payloads to
   `database/roles/vcloud-rag-query` / `database/roles/vcloud-rag-ingest`, and the
   HCL policies under names `vcloud-rag` / `vcloud-rag-indexer`.
3. Write the corresponding [Kubernetes auth roles](openbao/kubernetes-role-vcloud-rag.json)
   and [indexer role](openbao/kubernetes-role-vcloud-rag-indexer.json) to
   `auth/kubernetes/role/<identity>`. They bind only their workload-apps service
   account and the `openbao` audience.

Reconcile the allowed-role extension after any later Module 4a connection
reconfiguration, which uses its original role list. Leases use the audited
create/renew/revoke functions with a 15-minute default and one-hour maximum.
Do not run the role JSON through kubectl: those are OpenBao API request bodies.

Accept the existing [Module 4a CSI integration and its separate node approval](../module-4a/README.md)
before using these mounts. Both credential fields come from one 0440
`database.json` response; no Kubernetes Secret synchronization is configured.
The pipeline reads that file for each operation and uses `NullPool`, so later
operations do not reuse a cached revoked lease. A failed/revoked lease fails the
operation without printing the driver exception or credentials. Mount/group
permissions and rotation require the existing three-step live secrets test.

Create `vcloud-rag-public-trust` in `workload-apps` from **only public CA
certificates**, with keys `postgres-ca.crt` and `knative-ca.crt`. PostgreSQL uses
`sslmode=verify-full`; inference uses the standard verified HTTPS context and
refuses redirects/proxies. Accept SANs for both exact Service DNS names and the
Knative cluster-local TLS setup from Module 2. No insecure TLS fallback exists.
Private service access is controlled by Cilium; externally exposed API access
must retain the Module 4b APISIX/Keycloak boundary.

Keep Module 2's namespace deny-all and controller/DNS policies. The new policies
permit only RAG DNS and database traffic, query-to-Kourier TLS, explicit
activator/autoscaler-to-inference ports, and existing bounded host probes. The
ingestion identity has no inference egress. Policies are additive: acceptance
must also inspect every other policy selecting these endpoints.

## Model and image preparation

The encoder is **all-MiniLM-L6-v2**, pinned revision
`1110a243fdf4706b3f48f1d95db1a4f5529b4d41`. It runs on CPU with 384 normalized
dimensions. The encoder and collection dimensions/revision cannot silently
change; a different encoder requires an explicitly migrated collection.
Stage weights on a connected artifact builder, then transfer the materialized,
hashed tree into the accepted PVC through its storage owner:

```bash
python tools/stage_module5a_models.py embeddings \
  --destination .build/models/all-minilm-l6-v2 --cache .tools/model-cache
# The inference snapshot is large; stage it only on the accepted GPU builder.
python tools/stage_module5a_models.py inference \
  --destination .build/models/deepseek-r1-distill-qwen-32b --cache .tools/model-cache
```

The script refuses existing destinations, pins the immutable Hub commit,
materializes files and writes `vcloud-model.json`. Record its exact SHA256 in
the public RAG configuration. Every encoder startup verifies the accepted
receipt and complete file hashes, with remote code disabled and offline-only
loading. Verify the inference tree receipt during GPU acceptance as well;
vLLM receives only the accepted read-only directory.

The custom image tag in the Jobs is a **build target**, not an available image.
The recipe uses a digest-pinned mirrored Python base and a 73-package hashed
Python 3.14 / Linux amd64 CPU wheel lock. Build, scan and mirror the image,
record its immutable digest in the reviewed Job owner, then prove the accepted
base interpreter/glibc and CPU encoder work together. For a disconnected build,
stage all wheels in the internal mirror first, including the pinned direct
CPU torch artifact. The recipe does not provide a wheel-mirroring service.

```bash
docker build --platform linux/amd64 -f module-5a/images/rag.Dockerfile \
  -t registry.vcloud.example.com/vcloud/rag:1.0.0 .
```

Image assembly uses build authority; the final image and all runtime Pods run
as 65532. No credential is copied into that image. Build/publish, GPU execution
and PVC population are acceptance steps; this module does not execute them.

## Activation and executable usage

Promote through reviewed GitOps after the prerequisites above pass. Change
`embeddings.manifestSHA256` to the accepted receipt and `enabled` to true in
the config owner, rerender, and install only the reviewed resources. Remove
`suspend: true` from one accepted Job at a time. Merely applying these defaults
or unsuspending a Job cannot bypass the configuration gate.

For ingestion, supply `vcloud-rag-ingest-input` with `documents.json`:

```json
[{"source":"vcloud-architecture-v1","text":"Twinfra uses Kubernetes, Cilium and CloudNativePG."}]
```

Run ingestion serially from trusted inputs. Source identifiers are immutable;
repeating the same content upserts deterministic UUIDs. Changed content under
an existing source fails before writing. Use a new versioned source, or have
the database owner retire old chunks explicitly before replacing it. Ingestion
is bounded, performs no deletions, and is not a concurrent document lifecycle
manager. Retrieved text is treated as untrusted data; prompt wording alone is
not a security boundary.

Inside the accepted image/CSI environment, the code is executable directly:

```bash
python /opt/vcloud/pipeline.py --config /etc/vcloud/rag.yaml \
  ingest --documents /input/documents.json
python /opt/vcloud/pipeline.py --config /etc/vcloud/rag.yaml \
  query --question 'Which database stores Twinfra vectors?'
```

The returned JSON contains an answer and retrieved source/chunk references.
Question/context bounds are characters, not tokenizer limits; unusual input
may still exceed vLLM's 4,096-token context and is rejected without fallback.
No LangSmith export, request/document logging or credential-bearing environment
variable is configured.

## Validation and remaining runtime gates

```bash
make module5a-render module5a-validate module5a-test
```

After installing the hash-locked CPU runtime and staging the embedding snapshot,
an additional real encoder check runs without a database or GPU:

```bash
python tools/module5a_encoder_smoke.py --model .build/models/all-minilm-l6-v2 \
  --report .build/module-5a/encoder.json
```

It verifies the weight receipt, 384-dimensional normalized output, agreement
between query/document encoding and a simple semantic similarity ordering.
Its explicit host model path does not modify or enable the application config.

The validator checks deterministic renders, authenticates the shared schemas,
strictly validates all objects and composed patches without skipped kinds, and
applies the frozen node/Pod security contract. CI installs a separate 43-package
hash-locked client graph. Unit tests exercise the actual LangChain LCEL and
SQLAlchemy/native driver APIs, with mocked database and HTTP transports;
test embeddings are deliberately synthetic. They do not establish SQL, GPU or
end-to-end RAG acceptance.

Before enabling, prove an initialized CNPG/pgvector collection, writer/query
permissions, CSI readability/rotation/revocation, verified TLS and Cilium
denial, digest-pinned images, accepted model receipts, actual GPU health and
warm/cold-start behavior. Then ingest a known document and assert its retrieved
source and grounded answer; inspect undesired cross-namespace traffic drops.
The current WSL Argo/CNPG controller connectivity issue still prevents this
live sequence. This implementation does not bypass that gate.
