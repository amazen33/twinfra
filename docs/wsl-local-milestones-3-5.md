# Local WSL application and observability acceptance

Scope: the 20 GiB, six-CPU `vcloud-wsl-local` lab. The requested local stages
M3 (application endpoints), M4 (observability), M5 (validation) are separate from
the GitHub release milestone numbering in [MILESTONES.md](../MILESTONES.md).
They do not close public-release, security-audit or multi-node acceptance gates.

## Prerequisites and repair order

Require the private `/etc/vcloud-wsl/kubeconfig.yaml`, root-owned lab marker,
one Ready Node, restricted:v1.30 enforcement, cached images, the already-vetted
4 GiB Local PV, Argo Synced/Healthy and PostgreSQL TLS/pgvector/persistence.
Mandatory CLIs: `kubectl`, `jq`, `curl`, `ip`, Python with PyYAML/cryptography,
`gpg`, `systemctl`, `ctr`, plus the pinned validation tools.

The initial live check on 2026-10-07 found Argo discovery RBAC pointed to the
old `argocd` namespace, a missing Git DNS Deployment, and no database Cluster.
The repair restores the existing controller binding to `platform-services`;
its cluster role remains read-only. Scoped namespace writer roles supply actual
reconciliation permissions. An exact Git DNS policy is retained, including the
existing manual ingress exception; SSA conflicts are never forced away.

WSL's virtual DNS resolver `10.255.255.254` resolves GitHub from the host but
timed out from the Git DNS Pod. `tools/wsl_git_dns.py` publishes fresh public
GitHub-only answers through the host resolver. It never opens arbitrary public
DNS or adds fixed Internet addresses to source control. Refresh before GitOps
activation and run the owned timer during lab operation; cluster DNS remains
in-cluster. Failed refresh is reported, never replaced with a guessed address.

The final run reproduced intermittent repository fetch timeouts. A temporary
Pod MTU test failed and restored its original value. The operator approved a
scoped Cilium routing test after automatic approval review flagged its brief
lab-wide interruption. With `bpf.hostLegacyRouting: true`, repo-server fetched
GitHub successfully. The WSL renderer now preserves that measured workaround;
production Cilium values retain `false`. The dedicated
[routing overlay](../lab/wsl/values/cilium-routing.yaml) now makes that boundary
explicit and adds socket LB to the desired lab configuration. The
[CI/render guard](../tools/check_host_routing.py) rejects enablement elsewhere,
including Argo Helm overrides. Native routing, kube-proxy replacement,
BPF masquerading and policies remain enabled. This matches Cilium's documented
[host-stack compatibility workaround](https://docs.cilium.io/en/stable/operations/performance/tuning/#ebpf-host-routing);
it is evidence of a successful local workaround, not a complete upstream RCA.
See [ADR-0024](architecture/adr/ADR-0024-wsl-host-routing.md) for the decision.
The 15:04 UTC refresh verified effective socket LB enabled/full coverage and
explicit ConfigMap `bpf-lb-sock: "true"` after the owned Helm reconciliation.
A WSL restart changed the active interface from `eth1` to `eth2`; manual
[device recovery](WSL_SETUP_GUIDE.md#after-a-wsl-restart-verify-the-routing-interface)
restored fresh reconciliation on `main`, all ten endpoint gates, retained
database data and the three node probes. Unattended reboot recovery remains
open. SPIFFE/SPIRE is disabled and was not validated by this policy test.

```bash
sudo bash lab/wsl/reconcile-host-routing.sh --check
# Existing owned lab only; explicitly requested change briefly rolls Cilium:
sudo bash lab/wsl/reconcile-host-routing.sh --apply
sudo bash lab/wsl/test-network.sh
```

```bash
cd /mnt/e/vCloud
sudo bash lab/wsl/enable-secret-encryption.sh --check
# Existing unencrypted owned lab only; documented K3s procedure restarts its API:
sudo bash lab/wsl/enable-secret-encryption.sh --enable
sudo python3 tools/wsl_git_dns.py
sudo bash lab/wsl/install-git-dns-timer.sh
sudo bash lab/wsl/reconcile-prerequisites.sh --repair
sudo python3 tools/wsl_db_test.py --restart
```

K3s encryption was initially disabled. The scoped helper enables it, updates
the server config, performs the documented reencryption and verifies matching
hashes. It refuses unknown/intermediate rotation states. New runtime passwords
and certificate private keys are generated in process memory and passed directly
to the encrypted Kubernetes API; existing Secrets are preserved. The local K3s
key is root-owned on this node, not a remote KMS; this is not a root-compromise
or production key-custody guarantee. Reencryption does not erase historical
plaintext from pre-existing filesystem snapshots or old datastore pages.

CNPG fsGroup=26 changes the mounted PV root from 0700 to 2770. The storage
guard permits those two private modes with the same UID/GID, filesystem and
finite size. No additional host directory or volume is adopted or formatted.

## M3: identity, gateway and CPU Knative service

```bash
sudo python3 tools/stage_wsl_endpoints.py
sudo bash lab/wsl/endpoints/deploy.sh
sudo bash lab/wsl/endpoints/access.sh start
curl --noproxy '*' --fail -H 'Host: demo-cpu-app.workload-apps.example.com' \
  http://127.0.0.1:18080/
# Expected HTTP 200 and: vcloud-knative-cpu-ok
```

The renderer relocates Knative/Kourier controllers, RBAC subjects and embedded
Service DNS into `workload-apps`. Control replicas are bounded to one; the demo
scales from zero to one with CPU only. Kourier uses an IPv4 bootstrap listener.
APISIX runs standalone file-backed data-plane mode with admin access disabled;
the route rewrites the requested lab Host to
`demo-cpu-app.workload-apps.vcloud.example.com`. This public CPU smoke route
does not claim production OIDC authorization or tenant isolation acceptance.

Keycloak imports the public Module 4b realm and uses its dedicated PostgreSQL
database/role with JDBC verify-full TLS. Its local hostname is
`https://localhost:18443`. Local cache and Recreate rollout match the single-node
lab. Human administrator access uses the separate
[secure admin bootstrap](keycloak-admin-access.md); no private credential is
published in Git or this runbook. Quarkus build output
is confined to tmpfs, retaining a read-only root filesystem. OpenBao also uses a
dedicated PostgreSQL database and verify-full TLS, with mlock disabled because
restricted Pods receive no IPC_LOCK capability. Both databases reuse CNPG's PV.

Under the measured WSL datapath, router probe packets arrive as `reserved:world`;
the router /32 rule alone did not match. The local endpoint policy therefore
permits world only on the selected health/listener ports. This is a documented
lab exception, not proof that those ports are accessible solely by kubelet.
The APISIX listener is intentionally reachable for local routing. DNS and all
component dependencies have explicit peer/port rules. Production policy must
resolve the node identity issue before reusing this profile.

## OpenBao initialization gate

Create the Service/Deployment before checking initialization. The normal
Service exposes **HTTPS 8200**. A second **HTTP 127.0.0.1:8201** listener exists
only inside the Pod namespace; it is not a Service port. The owned port-forward
binds that listener to **host 127.0.0.1:8200**, as required for the init API.
Do not expose the loopback operator endpoint on the LAN or APISIX.

```bash
sudo bash lab/wsl/endpoints/access.sh openbao
sudo bash lab/wsl/openbao-init.sh
```

The helper performs `GET /v1/sys/init` first. True prints status and exits zero
without reading keys or issuing POST. False requires these public key files:

```text
/etc/openbao/keys/operator1.asc
/etc/openbao/keys/operator2.asc
/etc/openbao/keys/operator3.asc
/etc/openbao/keys/root-secops.asc
```

Missing files print `ERROR: Initialization gated: Missing required PGP public key files.`
and return Linux exit **3**. Invalid/expired/non-encryption keys or private keys
fail closed. Three share recipients must be distinct. Armored public keys are
validated and exported as **binary OpenPGP**, then base64 encoded; base64 of the
ASCII armor is not a substitute for binary public-key bytes.

`openbao-init.sh --check-only` validates preflight without POST or Secret
creation even when all keys are valid. The acceptance runner always uses this
mode; the standalone command above is the explicit initialization operation.

Only valid recipients, encryption at rest, Secret creation permission and an
absent output Secret permit POST with 3 shares, threshold 2 and the separate root
recipient. The response must contain PGP ciphertext packet streams. Only validated
encrypted shares/token and public fingerprints are stored as immutable
`platform-services/openbao-init-encrypted`, key `init.json`. No plaintext
credentials enter stdout, argv, environment variables or host files.
An API storage failure after successful init is a fatal custody failure; never
retry initialization. Operator-private keys/unseal and root-token use remain
separate manual custody actions. The helper never generates recipients, enters
dev mode, decrypts output or unseals the server.

On 2026-10-07, GET returned false and all four files were absent. The real helper
returned the missing-key error; no initialization-output Secret was created.
Transport Ready probes use `/v1/sys/init`; Ready is explicitly not a claim that
OpenBao is initialized/unsealed or that dynamic-secret issuance is accepted.

## M4: metrics and traces

Prometheus Operator discovers ServiceMonitors via EndpointSlice. Dedicated
metrics ports are APISIX 9091, CNPG operator 8080 and Knative controller 9090.
Knative 1.23 metrics default to none; the profile explicitly sets
`metrics-protocol: prometheus` before controller startup. Scraping the API port
instead of a dedicated metrics port must fail acceptance, not be ignored.

The demo sends a real OTLP/HTTP span to the Collector on each request. Its batch
pipeline exports to the debug exporter; logs must contain `demo-cpu-app` and
`vcloud-demo-request`. The Collector accepts OTLP on 4317/4318 and offers a
Prometheus exporter on 9464. No Jaeger/Tempo GUI or durable trace store is claimed.
Grafana has an internal Prometheus datasource; its admin password is file-mounted
from a private Secret, never placed in environment variables. Prometheus's two-hour
retention and Grafana data are ephemeral local diagnostics, not durable production
observability or backup.

## M5: executable gates and publication

```bash
python3 tools/wsl_endpoints.py render
python3 tools/wsl_endpoints.py validate
.build/ci-linux-assets/bin/conftest test --namespace vcloud_wsl \
  --policy tests/ci/policy/wsl-endpoints.rego .build/wsl-endpoints/*.yaml
.build/ci-linux-assets/bin/shellcheck lab/wsl/endpoints/*.sh lab/wsl/test-e2e.sh \
  lab/wsl/openbao-init.sh lab/wsl/enable-secret-encryption.sh
python3 -m unittest discover -s tests -p test_openbao_pgp_init.py -v
python3 -m unittest discover -s tests -p test_wsl_endpoints.py -v
sudo bash lab/wsl/test-e2e.sh
```

`test-e2e.sh` writes a sanitized `.build/wsl-endpoints/acceptance.json` and exits
nonzero on any GitOps, database, ingress, telemetry or security failure. It
requires all three metric target groups present and up; HTTP 200 must return
the actual demo body. It checks generated live CNPG/Knative/Prometheus Pods too,
not just source templates, and rejects AI/HPC images, GPU allocations or enabled
Spinifex flags. The missing-operator-key gate is an expected security outcome,
recorded separately from unseal acceptance. It never turns a missing live service
into a skipped test. Check the dated result before claiming a live pass.

The GitOps gate requires both `vcloud-wsl-platform` and
`vcloud-wsl-endpoints` present, Synced/Healthy and without error conditions.
Knative admission defaults are explicit in the CPU Service so Argo can compare
desired/live specs without ignoring readiness, traffic or security differences.

Publish generated GitOps source with `python3 tools/wsl_endpoints_gitops.py`.
Activate `lab/wsl/endpoints/argocd.yaml` only after its Git revision is available
and CI passes. Scoped namespaced write Roles exclude Secrets, node/storage
resources and cluster write access; controller/CRD bootstrap stays separately
owned. Do not delete a tracked Git branch before verified cutover.

Both Application definitions target `main`. During candidate validation, pin
the endpoint Application to a CI-passed immutable SHA, then promote after merge.
The initial legacy Core source required a temporary `/spec/managed` ignore to
preserve the new role references. Remove that whole-role ignore on main cutover;
the explicit CNPG role defaults now match admission. Keep only bounded resource
scaling differences ignored. Do not add the temporary ignore back on `main`.

```bash
sudo kubectl --kubeconfig=/etc/vcloud-wsl/kubeconfig.yaml --context=vcloud-wsl-local \
  apply -f lab/wsl/endpoints/argocd.yaml
sudo bash lab/wsl/test-e2e.sh
```

The new writer Roles grant no Secret writes. The existing cluster discovery
Role permits read-only access to all resources, including Secrets. Narrowing
that pre-existing permission is a separate production security acceptance gate.

Primary references: [K3s existing-cluster encryption](https://docs.k3s.io/cli/secrets-encrypt),
[OpenBao PostgreSQL storage](https://openbao.org/docs/configuration/storage/postgresql/),
[APISIX deployment modes](https://apisix.apache.org/docs/apisix/deployment-modes/).
