# Module 2: vCloud infrastructure bootstrap and guardrails

This module implements the **vCloud** SSoT v2.2 in `amazen33/vCloud`, for the prepared
Ubuntu 24.04 Kubernetes host. The example is a single-VM acceptance profile. It is
statically validated; Ubuntu, GPU, TLS, scheduling and service integration still need
the live acceptance steps below. The approved kubeadm/Cilium/NVIDIA exception remains
unchanged. No SR-IOV node exception, application hostPath, privileged Pod or MPS daemon
is introduced.

## Files and version contract

| File | Purpose |
| --- | --- |
| [chart](chart/Chart.yaml) | Helm chart 0.2.0; storage, network, database, function and GitOps groups |
| [Cilium values](values/cilium.yaml) | Full kube-proxy replacement, native routing, Bandwidth Manager, Host Firewall |
| [APISIX values](values/apisix.yaml) | Separately installed, private API-driven standalone gateway profile |
| [site overlay](site-values.example.yaml) | Real addresses, devices, node names, images and readiness evidence |
| [copy-ready reference manifests](manifests/README.md) | Rendered YAML for inspection; documentation addresses, automatic GitOps sync disabled |
| [artifact lock](artifacts.lock.json) | Hashes and official source URLs for local charts and schemas |
| [Makefile](../Makefile) | Offline render/validation, actual-host checks, preparation, diff and apply |
| [resource scaler](chart/files/scaler.py) | Bounded VPA recommendation to CNPG Cluster resource growth |
| [pgvector image](images/postgresql-pgvector.Dockerfile) | Bake pgvector into PostgreSQL; containerd ImageVolume support is not assumed |
| [APISIX image](images/apisix.Dockerfile) | Build-time directory ownership; runtime UID/GID 65532 |
| [bootstrap decisions](../docs/adr-0019-module-2-bootstrap.md) | Configuration ownership, storage limits and scaling constraints |
| [validation evidence](../docs/module-2-validation.json) | Exact static results and outstanding live gates |

| Component | Pinned version / API |
| --- | --- |
| Kubernetes | 1.36.5, matching the approved host bootstrap; target floor 1.30+ |
| Cilium | Chart 1.20.2, `cilium.io/v2` |
| Knative Serving / Kourier | 1.23.0, `serving.knative.dev/v1` |
| CloudNativePG | 1.30.1, `postgresql.cnpg.io/v1` |
| PostgreSQL / pgvector | 18.6 / 0.8.2, derivative tag `18.6.0-pgvector0.8.2` |
| VPA | Recommender 1.8.0, `autoscaling.k8s.io/v1`, mode `Off` |
| APISIX / chart / ingress controller | 3.19.0 / 2.18.0 / 2.2.0, `apisix.apache.org/v2` |
| Argo CD | 3.5.3, served, non-deprecated `argoproj.io/v1alpha1` |
| Validation tools | Helm 3.22.0, kubeconform 0.8.0, GNU Make 4.4.1 |

The version matrix is a pinned integration target, not a claim that the full stack has
run together. APISIX controller 2.2.0 requires Kubernetes 1.31+; this profile's 1.36.5
meets that floor ([installation requirements](https://apisix.apache.org/docs/ingress-controller/install/)).
Argo's supported CRD API name contains `alpha`; that does not make it a deprecated
Kubernetes built-in API. Only these two schema-checked Argo kinds bypass the older
generic auditor's blanket alpha/beta filter.

## Offline preparation

On a connected staging machine, scan and transfer the repository, its locked artifacts,
Linux binaries for Helm/kubectl/kubeconform, GNU Make, Python 3.11+ and PyYAML 6.0.3.
Ubuntu 24.04 supplies Python 3.12. Stage the `make` and `python3-yaml` packages through
the approved offline apt mirror; Module -1's dependency list does not include PyYAML.
The Windows `.tools` binaries used for development are not Ubuntu runtime binaries.
All Make targets use local charts and schema files. They never add a Helm repository,
update dependencies or fall back to an internet schema URL.

Mirror the exact images at `registry.vcloud.example.com`, preserving digests. The Python
image uses the checked multi-architecture digest in `chart/values.yaml`. Mirror the
two digest-pinned CNPG base/extension images, then build and scan the pgvector derivative:

```bash
docker build -f module-2/images/postgresql-pgvector.Dockerfile \
  -t registry.vcloud.example.com/vcloud/postgresql-pgvector:18.6.0-pgvector0.8.2 .
docker build -f module-2/images/apisix.Dockerfile \
  -t registry.vcloud.example.com/vcloud/apisix:3.19.0-vcloud.1 .
```

Build/push commands are staging tasks; neither image was built or pushed during local
validation. Root in these Dockerfiles is justified **only during image construction**
to place binaries and set ownership. PostgreSQL runs as 26:26; APISIX runs as 65532:65532.
Record the published derivative digests in the site/profile before live deployment.
The APISIX image owns its generated `conf` and `logs` directories; its root filesystem
is writable. A read-only variant requires a tested configuration-seeding profile.

Stage Knative/Kourier, CNPG, Argo CD and the VPA **recommender only** using the versions
above. Rebase controller images to the canonical registry and audit their manifests
against the SSoT. No standard controller may add root, host mounts, capabilities or a
privileged sidecar through this module. Install them in `platform-services`, retain
restricted Pod Security, and match the selectors in `chart/templates/network.yaml`.
For Knative these are `app: controller`, `autoscaler`, `activator`, `webhook`,
`net-kourier-controller` and `3scale-kourier-gateway`. Record exact main-container
image references in `dependencies.images`; live preflight compares ready controllers
against these lists and audits their templates. Install CRDs from the pinned releases;
the gzip vendor inputs are schema sources, not a replacement for complete controller
installation bundles. Accept and record controller/runtime configuration before setting
the readiness booleans. Empty image lists and false readiness flags block final apply.

Publish the reviewed tree to `amazen33/vCloud` and mirror it to
`https://git.vcloud.example.com/amazen33/vCloud.git`. Use a 40-character commit SHA or
the documented protected release tag `vcloud-module-2-v0.2.0`. The example tag is an
intended release, not a published repository revision. Prefer a commit SHA once
published. GitOps reads this internal mirror over verified TLS; it does not need GitHub
egress. Supply private Git/registry credentials through the approved secret custody
integration, outside Git and site values. Namespace-scoped image pull credentials are
required if node-level containerd authentication is not used.

## Configure and inspect the actual site

```bash
cp module-2/site-values.example.yaml module-2/site-values.yaml
# Edit addresses/CIDRs, devices, nodes, mirrored image references and dependency evidence.
make render
make validate
make test
```

The example's RFC 5737 addresses are deliberately rejected by live targets. Configure
the static API endpoint, registry/Git/identity/DNS CIDRs and the actual native-routing
devices. Remote node PodCIDRs need working underlay routes; `autoDirectNodeRoutes` is
disabled because same-L2 topology is not assumed. Keep the three namespaces and
platform/domain/registry identity fixed. Configure kubeconfig for the exact
`vCloud-prod-01` cluster and its HTTPS API address; insecure TLS bypass is rejected.
`site.referenceOnly: false` enables real GitOps sync. Reference manifests keep it off.

The static Local PV plan is confined to these paths, and **physical vetting remains
mandatory**. The `vcloud.io/vetted` annotation records the exact declarative plan;
it alone never passes the physical gate:

| Local PV | Directory suffix under `/var/lib/vcloud/local-pv` | UID:GID | Claim |
| --- | --- | --- | --- |
| `vcloud-function-data` | `function` | 65532:65532 | `workload-apps/function-data`, read-only |
| `vcloud-postgres-1` | `postgres-1` | 26:26 | `platform-services/vcloud-postgres-1` |
| `vcloud-postgres-2` | `postgres-2` | 26:26 | Second instance; separate node |
| `vcloud-postgres-3` | `postgres-3` | 26:26 | Third instance; separate node |

Use an explicitly identified, dedicated ext4/xfs data mount at this base directory or
its planned children. Have the storage administrator provision/own the listed
directories and seed the non-secret `function/greeting.txt`. This module does not
format disks or create directories. Ancestor symlinks, world-writable directories,
wrong ownership, root-filesystem storage and insufficient aggregate free space are
rejected. Require at least 1.2 times the planned capacity free on each backing
filesystem. Local PV capacity is a scheduling declaration, not a filesystem quota;
separate mounts/quotas and disk-full monitoring are needed for workload isolation.

The example has one 20 GiB PostgreSQL PV and a 1 GiB function PV. Production defaults
have three database PVs on different nodes with required anti-affinity. StorageClass
uses `kubernetes.io/no-provisioner`, `WaitForFirstConsumer`, `Retain`, no expansion.
Claims are prebound to prevent accidental cross-workload allocation. Do not reuse a
retained PostgreSQL PV for a new instance without an explicit recovery/rebinding plan.
Local PVs do not provide node-independent recovery or a backup. Function scale is
bounded at one replica because its persistent volume is tied to one node.

On **each** node in the volume plan, using the same site file:

```bash
sudo env KUBECONFIG=/etc/kubernetes/admin.conf make host-check
```

This read-only check verifies Ubuntu 24.04, kernel 6.8+, cgroup v2, bpffs, kernel BPF/TC
capability, swap/sysctls, containerd systemd cgroups, NVIDIA runtime, accessible driver
550+, devices, 128 x 2 MiB plus 1 x 1 GiB HugePages, and exact local mount/ownership/
capacity. It writes `.build/module-2/host-<hostname>.json`. Copy multi-node reports to
the bootstrap machine without modifying their contents. Live targets require matching
site hashes and reports less than 15 minutes old. Driver visibility is not a CUDA Pod
execution test. HugePages stay reserved on the host; this PostgreSQL template uses
ordinary memory (`huge_pages=off`) until a separately sized hugepage workload profile
is accepted. Reserve sufficient ordinary RAM for controllers, GPU workloads and growth
to 2 CPU/4 GiB per database instance before enabling the scaler.

## Prepare the controller network and TLS profiles

Module -1 already installs Cilium and the core namespaces' deny-all policies. After
real host inspection, use the preparation target to enable the approved Cilium config
and install only the network allowances. This resolves the controller bootstrap
dependency without requiring already-running controllers:

```bash
make prepare
```

`prepare` still validates local artifacts, checks the target and namespace baselines,
requires Cilium's served CRDs and fresh host reports, and runs server-side admission
before mutation. It does not create volumes, workloads or secrets. Both preparation
and final apply use a Helm post-renderer to validate **the actual Helm output** against
local schemas and the frozen node allowlist before Helm changes the cluster.

Install and accept the pinned controller profiles after preparation. Knative's PVC and
Pod security fields need explicit [feature flags](https://knative.dev/docs/serving/configuration/feature-flags/).
For a raw-manifest installation, merge only these data entries:

```bash
kubectl -n platform-services patch configmap config-features --type=merge \
  --patch-file module-2/values/knative-features.patch.json
kubectl -n platform-services patch configmap config-network --type=merge \
  --patch-file module-2/values/knative-network.patch.json
```

If the Knative Operator owns those ConfigMaps, put the same keys in its installation
CR instead; avoid two writers. Expose Kourier's private service at 443 -> 8443. This
profile uses internal TLS at activator/queue-proxy 8112. Internal Knative encryption is
an [experimental feature](https://knative.dev/docs/serving/encryption/encryption-overview/);
test supported behavior for the pinned release rather than assuming every control
connection is encrypted. Audit generated queue-proxy Pods under restricted admission.

Provision `vcloud-runtime-ca`, `apisix-admin-tls`, `apisix-gateway-tls`,
`knative-upstream-tls` and `apisix-runtime-secrets` in `platform-services` through the
reviewed OpenBao bridge/custody workflow. The CA Secret has `ca.crt`; TLS Secrets have
`tls.crt` and `tls.key`. Runtime secret keys are `admin`, `viewer`, `oidc-client-secret`.
No plaintext credential, secret-generation recipe or cluster secret dump is in Git.
The gateway CA must trust both the actual Kourier certificate and the Keycloak issuer;
validate hostname/SNI and rotation. `ApisixUpstream.tlsSecret` supplies a client
certificate, **not server trust**. Upstream verification comes from the explicit
Nginx CA/verify directives in the APISIX profile. Any future upstream `tls.verify`
override must preserve verification. The public `ApisixTls` object selects the
gateway certificate for `api.vcloud.example.com`.

After secret provisioning, the optional dependency profile is ready to install:

```bash
kubectl apply --server-side -f module-2/values/apisix-serviceaccount.yaml
helm upgrade --install apisix module-2/vendor/apisix-2.18.0.tgz \
  -n platform-services -f .build/module-2/apisix-values.yaml --wait --timeout 10m
```

The chart/profile is included in static validation, but is not automatically installed
by `make apply`. Install ingress controller 2.2.0 separately, with class `apisix`, its
same-namespace gateway target, private HTTPS Admin API on 9180, verified CA and client
TLS. This controller is the sole APISIX configuration writer; do not enable etcd,
the file watcher, another controller instance with different ownership, or public
administration. Review the rendered dependency manifests before this explicit install.
Test native APISIX config parsing/startup, absent credentials, CA rotation and invalid
issuer/audience/signature tokens before recording `apisix.profileReady: true`.
See [deployment modes](https://apisix.apache.org/docs/apisix/deployment-modes/) and
the [OIDC plugin](https://apisix.apache.org/docs/apisix/plugins/openid-connect/).
The route's `$ENV://APISIX_OIDC_CLIENT_SECRET` is a runtime reference, not a credential.
Accept private Argo repo RPC and Redis TLS/authentication profiles on the permitted
8081/6379 ports; policies specify reachability, not encryption. No Argo UI exposure
or user login route is installed by this module.

## Final bootstrap and ownership handoff

After controller/TLS acceptance and setting the matching readiness/image evidence:

```bash
make validate
make diff                 # Valid comparisons succeed; changes are printed; errors fail.
make apply
```

GNU Make maps a failing recipe to its own error status. The `diff` target therefore
accepts kubectl's 0/1 comparison results and fails for errors. For a CI job that needs
kubectl's exact 0/1 difference status, invoke `python3 tools/module2.py diff` directly.

`apply` repeats validation and live preflight, preserves existing grown database
resources, and stamps the observed database resourceVersion for optimistic concurrency.
A concurrent operator/scaler update rejects that database write; rerun after inspecting
the change, without forcing conflicts. Real admission/CEL/webhooks are exercised through
server dry-run before the first mutation. Cilium remains owned by Helm/this bootstrap;
Argo owns the four child groups after handoff. Repeated bootstrap uses the same SSA
field manager. Missing prerequisites/errors stop subsequent steps; previous successful
steps are not rolled back destructively.

The root Application references the internal mirror of `amazen33/vCloud`, chart path
`module-2/chart`, and immutable revision. It creates storage/network/database/function
children with waves -20/-10/0/10. AppProject scopes those resources to the three core
namespaces, the specified Local PV/StorageClass and host policy kinds. Automatic pruning
is disabled. Sync waves order declarations; do not assume they prove child readiness
without a separately reviewed Application health customization. No remote cluster,
repository publication, protected tag or Argo installation is created by this Makefile.

CloudNativePG owns database Pods. VPA emits recommendations with mode `Off`; the
non-root CronJob reads one VPA and patches one CNPG Cluster, never Pods or evictions.
Default bounds are 1–2 CPU and 2–4 GiB per instance, a 1-hour cooldown, 25% hysteresis,
at most 2x growth and recommendations no older than 15 minutes. Unhealthy instances,
failover, maintenance, missing freshness or changed resource versions stop growth.
Memory/CPU reductions require reviewed maintenance. Argo ignores only the resources
and scaler timestamp of this Cluster so it does not revert growth. RBAC limits patching
to this object; RBAC cannot restrict JSON field paths, so the reviewed scaler code is
part of the trust boundary. Growth can trigger CNPG restarts/switchover and still needs
available scheduler capacity. It does not add writable primaries, tune all PostgreSQL
memory parameters or provide load-based replica scaling.
Live preflight checks existing scheduled Pod requests plus the database's maximum
reservation against 90% of each database node's allocatable CPU/memory. This initial
capacity check does not reserve unused capacity against future workloads or guarantee
resource availability for every later growth operation.
See [CNPG resource ownership and VPA guidance](https://cloudnative-pg.io/docs/1.28/resource_management/).

## Network and runtime acceptance

| Flow | Allowed destination |
| --- | --- |
| All core namespaces -> DNS | Only `kube-system/kube-dns`, UDP/TCP 53 |
| External client -> APISIX | HTTPS container 9443; `/function` with verified bearer token |
| APISIX -> Knative | Kourier private HTTPS 8443, rewritten function Host |
| Kourier/activator -> function | Queue TLS 8112; autoscaler gets only its declared telemetry ports |
| Knative controllers / infrastructure clients -> API | Kubernetes API entity on 443/6443 |
| APISIX controller -> gateway | Private TLS Admin 9180, one configuration writer |
| CNPG instance/operator peers | Replication 5432; operator management 8000; explicit webhook/probes |
| Argo controller -> repo / cache | Private 8081 / 6379; repo -> pinned Git CIDRs on 443 |
| Opted-in HPC peers, same job group | TCP 22/2222 and 10000–10100; no cross-job/namespace SSH/MPI |

`hostFirewall.enabled=true` loads the feature, but the host policy selects only nodes
labeled `vcloud.io/host-firewall-reviewed=true`. Unlabelled nodes do not have this
host deny policy enforced. Validate break-glass console access, SSH and all peer routes
in Cilium host audit mode, then label one reviewed node and test before the rest.
Audit mode itself is not persistent enforcement; follow the
[Host Firewall procedure](https://docs.cilium.io/en/stable/security/host-firewall/).
Bandwidth Manager is enabled; no workload rate is imposed without explicit
`kubernetes.io/ingress-bandwidth` / `kubernetes.io/egress-bandwidth` Pod annotations
([EDT configuration](https://docs.cilium.io/en/stable/network/kubernetes/bandwidth-manager/)).

`cni.exclusive=false` permits a reviewed Multus/SR-IOV coexistence profile; it does not
install device plugins, VFs or privileged agents. A direct secondary VF/RDMA path may
bypass the primary Cilium datapath. Secondary-network annotations are rejected here;
fabric/device policy and a separate node exception are needed before that path can be
claimed protected. This SSH/MPI preset is TCP-only: configure and verify both launcher
control ports and data ports within its fixed range. Default ephemeral ports, UDP/RDMA
and UCX transports are not implicitly allowed. Port 2222 supports non-root SSH;
allowing network port 22 does not authorize root or `NET_BIND_SERVICE` in an HPC Pod.

On the real cluster, record these acceptance results before promotion:

- Prove Cilium kube-proxy replacement/native routing, host-firewall enforcement on
  reviewed nodes, bandwidth limiting, node restart and cross-node DNS reachability.
- Prove arbitrary egress and cross-namespace/cross-job ingress are denied while the
  specified DNS, gateway, webhook, replication, autoscaler and MPI paths work.
- Invoke HTTPS `/function` with a valid token, then wrong issuer/audience/expired/unsigned
  tokens; prove direct unauthorized Knative access is blocked. Verify all request-path
  TLS hostnames/CA rotation. Observe scale-to-zero and activation back to one replica.
- Inspect `nvidia.com/gpu` allocatable and run an approved non-root, digest-pinned CUDA
  test with the NVIDIA runtime. Driver checks alone do not prove container GPU access.
- Query `pg_extension` for `vector`, test encrypted SQL with `sslmode=verify-full`,
  disconnect plaintext SQL, restart the instance and validate persistent data. Trigger
  a bounded resource recommendation, observe CNPG's update, then test cooldown/failure.
- Prove scheduling headroom at the maximum resource bounds and rehearse rollback of
  a failed resource change. Monitor disk space and take/recover an actual backup.
- Verify root/child GitOps sync against the published commit; confirm resource growth
  survives reconciliation and retained PVs are not pruned. No live result is implied by
  the static evidence or by a readiness boolean.

Schemas intentionally retain CRD fields marked `x-kubernetes-preserve-unknown-fields`
(including plugin configuration). Kubeconform does not execute CRD CEL expressions,
admission webhooks, controller logic or APISIX plugin parsing. Local semantic checks
cover the provided policy/authentication/security contracts; server admission and the
live steps cover the remaining behavior. Reproduce the 10 converted CRD schemas with
`python3 tools/build_module2_schemas.py`; it uses locked local inputs only.
