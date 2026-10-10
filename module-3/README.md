# Module 3: end-to-end GitOps delivery

Authenticated pushes to protected `main` in `amazen33/twinfra` start the Tekton
`vcloud-ci` pipeline. It checks out the exact commit, runs application and repository
tests, builds and pushes an OCI image, then updates its source tag **and SHA-256 digest**
on `gitops/prod` in the same repository. Argo CD continuously reconciles that branch.
Pushes to `gitops/prod`, forks, other repositories, deleted refs and forced pushes
are excluded from the trigger. No pipeline task deploys Kubernetes objects.

```text
GitHub main push -> APISIX HTTPS -> HMAC + CEL -> Tekton PipelineRun
    clone exact SHA -> app/schema/guardrail tests -> mTLS BuildKit VM
    -> registry.vcloud.example.com/vcloud/api:git-<source SHA>@sha256:<digest>
    -> validate exact candidate -> ordinary git push to gitops/prod
    -> Argo CD vcloud-delivery -> Knative vcloud-api in workload-apps
Tekton/Argo metrics -> Prometheus -> Perses dashboard + Prometheus alerts
```

| Deliverable | File |
| --- | --- |
| Four complete Tasks | [tasks.yaml](manifests/tasks.yaml) |
| Pipeline, ordered tests/build/promotion and results | [pipeline.yaml](manifests/pipeline.yaml) |
| Manual PipelineRun, initially pending | [pipelinerun.yaml](examples/pipelinerun.yaml) |
| GitHub binding/template/listener and APISIX HTTPS route | [triggers.yaml](manifests/triggers.yaml) |
| Narrow trigger RBAC; token-free runtime identities | [rbac.yaml](manifests/rbac.yaml) |
| CI network, controller probes and monitoring allowances | [network.yaml](manifests/network.yaml) |
| Argo CD Applications and separate AppProjects | [application.yaml](argocd/application.yaml) |
| ServiceMonitors, alerts and Perses dashboard | [observability.yaml](manifests/observability.yaml) |
| New workload, identity and Cilium policy | [gitops/](gitops/) |
| Trusted runtime/promotion code | [runner.py](runtime/runner.py), [final verifier](runtime/validate_workload.py) |
| CI tooling image | [Dockerfile](images/ci-tooling.Dockerfile) |
| Version/source/schema hashes | [artifact lock](artifacts.lock.json), [toolchain lock](toolchain.lock.json) |
| Architecture and limitations | [ADR 0020](../docs/adr/0020-module-3-delivery.md) |

## Security and ownership

`vcloud-api` is a new scale-to-zero workload. Module 2 retains ownership of
`secure-function`, its database and storage. `vcloud-delivery` owns only the new
Knative Service, ServiceAccount and Cilium policy. `vcloud-ci` owns the separately
reviewed CI definitions under `module-3/manifests`, following protected `main`.
Both applications self-heal, disable pruning and prohibit empty deletion.

`gitops/prod` is deliberately a moving environment branch: image references are
immutable digests, and each promotion records the exact source SHA. This implements
automatic manifest updates in Module 3, superseding Module 1's proposed per-image
pull-request flow for this dedicated workload. Protect both branches and require
review/tests on `main`. The short-lived GitHub App token must be unable to bypass
source-branch protection. Do not grant general users permission to create/edit
production Tasks, PipelineRuns, EventListeners, credentials or Argo projects.

Task steps use UID/GID 65532, RuntimeDefault seccomp, dropped capabilities, a read-only
root filesystem and no API tokens. The EventListener needs an API token to create
PipelineRuns and read trigger metadata; its Role cannot mutate workloads. Its only
cluster permission reads ClusterInterceptor definitions. Git write credentials
are mounted only in the publisher Task. Registry push and builder mTLS credentials
are mounted only in the build Task. The test Task receives none of those secrets.

The trusted publisher and final verifier are baked into the CI image. Repository
code is never executed with Git write credentials. Only the image and source-revision
fields of `module-3/gitops/workload.yaml` may change. The file uses JSON syntax,
which is valid YAML, to avoid rewriting sibling documents. Validate the final
candidate with strict kubeconform before committing. No force push, hook execution,
TLS bypass, Docker socket, application hostPath or CI node exception is introduced.
The build Task fetches the exact tested commit into a fresh context and never consults
Git configuration or generated files left by the test Task.

The clone, build and publisher reject a source SHA when protected `main` has advanced
at their observed checks. A competing GitOps commit causes a bounded fetch/retry;
the new commit is preserved. A repeated same-source/same-digest promotion is a no-op.
A different digest for the same source fails for review. This is optimistic Git
concurrency, not an atomic lock across GitHub's two branches. The SHA-derived trigger
PipelineRun name prevents a retained run from being recreated on webhook replay;
retry a failed run with a new manual name after inspecting the failure.

## Prerequisites and connected staging

The reference deployment uses connected GitHub delivery. A strictly air-gapped site
needs an authenticated webhook relay plus a Git mirror that replicates `main` and
`gitops/prod`. Point both Argo Applications at that internal mirror and adjust the
reviewed generator, Git endpoints and Cilium DNS/FQDN allowances together. These
manifests do not make a disconnected site receive GitHub events automatically.

1. Stage Tekton Pipelines **1.17.0**, Triggers/core interceptors **0.37.1**,
   Argo CD **3.5.3**, the existing Knative/Kourier TLS profile, APISIX and Cilium.
   Prometheus Operator **0.94.1** schemas are pinned for the monitoring resources.
   Controller/helper images must be mirrored to `registry.vcloud.example.com`
   with explicit versions/digests and accepted under the node/pod contract.
   Vendored gzip inputs contain CRDs for schema reproduction, **not a controller installer**.
2. Keep Tekton controllers in their upstream `tekton-pipelines` system namespace.
   This auxiliary infrastructure namespace prevents collision with Knative's
   `config-observability` in `platform-services`; the three core SSoT namespaces
   retain their roles. CI executions stay in `workload-apps`. Do not enable unused
   remote Task resolvers or silently relocate upstream components.
3. Provide an isolated, disposable **BuildKit 0.33.1** VM. Run the daemon rootless
   with its normal process sandbox, private-CA trust and client-certificate
   authentication on `buildkit.vcloud.example.com:1234`. Restrict its firewall to
   reviewed CI source networks and its egress to the staged registry. All Dockerfile
   RUN network access is disabled by `force-network-mode=none`; the daemon still
   needs registry access for base images/push. No privileged builder pod is installed.
   Ubuntu 24.04 rootless AppArmor/user-namespace setup needs separate host acceptance;
   this module does not weaken the prepared Kubernetes host's AppArmor settings.
4. Provide the reviewed dynamic CSI StorageClass **`vcloud-ci-csi`** with
   `WaitForFirstConsumer`, allowing non-root/fsGroup access. Each run requests a
   separate 5 GiB RWO workspace. Module 2's static `vcloud-local` class cannot
   dynamically provision these claims. Accept scheduling/attach behavior, capacity,
   and a PipelineRun/PVC retention/cleanup policy before enabling the webhook.
5. Have the existing OpenBao integration provision the secrets below. No secret
   values, secret YAML, `.env` or signing/private keys belong in Git. Mount private
   CA certificates with the named TLS secret; do not disable certificate validation.

| Secret in workload-apps | Required keys / purpose |
| --- | --- |
| `vcloud-registry-pull` | `.dockerconfigjson`; private step/runtime pulls |
| `vcloud-registry-push` | `.dockerconfigjson`; scoped push to vcloud/api |
| `vcloud-buildkit-mtls` | `ca.crt`, `tls.crt`, `tls.key`; short-lived builder client identity |
| `vcloud-git-write` | `token`; short-lived GitHub App installation token, protected promotion branch |
| `vcloud-webhook-hmac` | `secretToken`; GitHub signature verification |
| `vcloud-ci-webhook-tls` | `tls.crt`, `tls.key`; public ci.vcloud.example.com certificate |

Mirror the digest-pinned Python base used by the two Dockerfiles. The CI tooling
image installs OS/test dependencies during connected image preparation; root is
required only at image-build time to install packages. Runtime Tasks run as UID 65532.
Use your package/wheel mirror during isolated image preparation. No Task runs pip,
APT or binary downloads at execution time.

```bash
# Connected staging; verifies the upstream binary checksums in toolchain.lock.json.
python3 tools/stage_module3_toolchain.py --download
docker build -f module-3/images/ci-tooling.Dockerfile \
  -t registry.vcloud.example.com/vcloud/ci-tooling:1.0.0 .
docker push registry.vcloud.example.com/vcloud/ci-tooling:1.0.0
# Make this semantic version immutable at the registry; do not overwrite it.
make module3-validate module3-test module3-alerts
```

## Bootstrap order

Publish the reviewed Module 3 code to protected `main` before enabling triggers.
Seed `gitops/prod` from that exact commit with the `module-3/gitops` directory intact,
then protect the branch. The pipeline does not create an absent production branch.
The bootstrap workload image `:0.1.0` is an explicit version reference; publish that
image first or keep the workload Application disabled until the first successful
promotion supplies its real digest. Do not fabricate a digest for an unbuilt image.

Configure the pinned Tekton controllers before running any PipelineRun. Merge only
the required ConfigMap fields, retaining the upstream configuration:

```bash
kubectl --context vcloud-prod-01 patch configmap feature-flags -n tekton-pipelines \
  --type merge --patch-file module-3/controller-config/feature-flags.patch.json
kubectl --context vcloud-prod-01 patch configmap config-observability -n tekton-pipelines \
  --type merge --patch-file module-3/controller-config/observability.patch.json
make module3-preflight CONTEXT=vcloud-prod-01
# This read-only prerequisite check does not prove builder/webhook/runtime acceptance.
```

Create the auxiliary namespace and install network allowances before the controllers
need those paths. Preserve the existing namespace deny-all baselines. Follow with
scoped RBAC, Tasks/Pipeline, trigger definitions, observability, and the reviewed
Argo AppProjects/Applications. For initial manual installation:

```bash
kubectl --context vcloud-prod-01 apply -f module-3/manifests/tekton-namespace.yaml
kubectl --context vcloud-prod-01 apply -f module-3/manifests/network.yaml
# Install/accept pinned controllers and external dependencies before continuing.
kubectl --context vcloud-prod-01 apply --dry-run=server -f module-3/manifests
kubectl --context vcloud-prod-01 apply -f module-3/manifests
kubectl --context vcloud-prod-01 apply -f module-3/argocd/application.yaml
```

The Argo bootstrap file intentionally contains AppProjects as well as Applications;
Argo namespace placement and project RBAC must already allow `platform-services`.
After Argo accepts `vcloud-ci`, it owns the CI definitions. The controller ConfigMap
merge patches remain a separately reviewed upstream-controller integration.

Configure GitHub's webhook at **`https://ci.vcloud.example.com/hooks/github`**, JSON
content type, **push events only**, and SSL verification enabled. Supply the exact
OpenBao-provisioned HMAC secret in GitHub's protected webhook settings. Do not send
test payloads until namespace isolation, credentials and the builder are accepted.

For a manual run, copy [the example](examples/pipelinerun.yaml), choose a unique
name and the current protected-main 40-character SHA containing Module 3, then
remove `spec.status: PipelineRunPending`. Applying the checked-in example alone
does not execute a build. Observe `tkn pipelinerun describe <name> -n workload-apps`
and the `IMAGE_DIGEST` / `GITOPS_COMMIT` results. An application rollback restores
the previous verified digest in the promotion branch; Argo performs reconciliation.

## Metrics, dashboard and alerts

The selected controller exposes `http-metrics` on 9090. The ServiceMonitor selector
and interceptor TLS port **8443** were checked against the pinned upstream releases.
`metrics-protocol: prometheus`, pipeline-level labels and histogram duration metrics
are explicit. No pushgateway or per-run high-cardinality custom metrics are added.

Configure the existing Prometheus resource's namespace/ServiceMonitor/rule selectors
to include these `app.kubernetes.io/part-of: vcloud` resources in `platform-services`
and scrape the Tekton system namespace. Argo CD's existing `argocd-metrics` Service
must expose its `metrics` port. Native failure, out-of-sync/unhealthy and missing
scrape alerts are in [observability.yaml](manifests/observability.yaml). Alertmanager
routes and notification credentials stay with the existing observability owner.
The ConfigMap contains Perses `twinfra-delivery.json`, provisioned as code by
[the WO-07 generator](../deploy/observability/perses/README.md). The four PromQL
queries are unchanged. The dashboard uses the project Prometheus datasource
behind APISIX OIDC; browser edits are disabled. Dashboards display metrics; Prometheus evaluates
the alerts and Alertmanager routes them. No external notification was sent here.

## Validation and live acceptance

Run `make module3-validate module3-test module3-alerts` offline with kubeconform 0.8.0
and promtool 3.15.0.
The test Task also runs Module 4a's offline CSI/schema and revocation-control checks;
the tooling image includes jq. Those checks mock curl/psql and do not contact OpenBao.
It also checks Module 4b's public realm, APISIX and group RBAC references without contacting IAM.
The validator uses only local schemas, verifies their checksums, reproduces all
eight added CRD schemas and supplements Tekton Triggers' permissive upstream schema
with exact structural/security checks. `triggers.tekton.dev/v1beta1` is served and
not marked deprecated in 0.37.1; beta API names are not automatically deprecated.
All Task/Pipeline/PipelineRun definitions use `tekton.dev/v1`.

See [validation evidence](../docs/module-3-validation.json). Real local bare Git
repositories exercise checkout, push, replay, stale-source rejection and concurrent
fast-forward retry. The BuildKit invocation is checked with a mocked daemon result;
an OCI build is not claimed. Application tests include a real local HTTP request.

Still accept actual controller/helper Pod security and mirrored images, CSI workspaces,
GitHub HMAC and replay behavior, short-lived token rotation, builder mTLS/OCI push,
registry CA verification, branch protection, Argo drift/rollback, scale-to-zero
activation and observed Prometheus/Perses/Alertmanager behavior. Signed images,
SBOM/provenance and admission verification proposed in ADR 0008 are not implemented
by this baseline; they remain required before a production artifact-trust claim.

Primary references: [Tekton v1.17 metrics](https://github.com/tektoncd/pipeline/blob/v1.17.0/docs/metrics.md),
[security/configuration](https://github.com/tektoncd/pipeline/blob/v1.17.0/docs/additional-configs.md),
[GitHub interceptors](https://tekton.dev/docs/triggers/interceptors/),
[BuildKit TLS and buildctl](https://github.com/moby/buildkit/blob/v0.33.1/docs/reference/buildctl.md),
[rootless limitations](https://github.com/moby/buildkit/blob/v0.33.1/docs/rootless.md),
[Argo automated sync](https://argo-cd.readthedocs.io/en/stable/user-guide/auto_sync/),
and [Prometheus Operator APIs](https://prometheus-operator.dev/docs/api-reference/api/).
The Module 5b extension adds its offline checks when `module-5b` is present.
Before rebuilding the CI tooling image with that extension, run
`python3 tools/stage_module5b.py --download` in the connected staging environment;
the image consumes the verified SDK wheels offline. These dependencies and the
new GPU reference do not enable live capacity requests.
