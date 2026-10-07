# LocalStack Community AWS API lab

Operator-selected **Community 4.14.0** emulates S3, EC2, IAM and DynamoDB in
`platform-services`. All images, including APISIX Ingress Controller 2.2.0 and
ADC 0.27.1, are pinned by digest in [artifacts.lock.json](artifacts.lock.json).
This is an API validation endpoint; the name `localstack-aws-console` does not
mean an AWS browser console is installed. The LocalStack Web Application is a
separate service. No license token is required by this pinned legacy profile.

## Provision and reconcile

```bash
cd /mnt/e/vCloud
# Connected staging into the CRI cache; no public runtime fallback is enabled.
sudo python3 tools/wsl_localstack.py --stage
# Requires pinned CI assets in .build/ci-linux-assets (including IngressClass schema).
sudo bash lab/wsl/localstack/deploy.sh
# Publish and pass GitHub CI before activating the updated GitOps source on main.
sudo kubectl --kubeconfig=/etc/vcloud-wsl/kubeconfig.yaml --context=vcloud-wsl-local \
  apply -f lab/wsl/endpoints/argocd.yaml
sudo bash lab/wsl/endpoints/access.sh start
sudo bash lab/wsl/localstack/verify.sh
sudo bash lab/wsl/test-e2e.sh
```

`deploy.sh` stages only the new controller, CRDs, policies and API workloads. It
does not switch existing APISIX routes. The updated endpoint Application owns
the later APISIX configuration and `ApisixRoute` reconciliation. CRDs, controller
RBAC and node-dependent Cilium policies stay bootstrap-owned. The first
deployment must complete these prerequisites before Argo receives the new source.
The demo route lives in `workload-apps` beside the real Kourier Service. An
ExternalName bridge has no usable upstream nodes under controller 2.2.0 and must
not replace this same-namespace backend. A candidate local trial pins an
immutable published commit; promotion to tracking `main` waits for hosted CI.

## Test endpoints

```bash
curl --fail http://127.0.0.1:4566/_localstack/health
curl -i -H 'Host: aws.platform.example.com' http://127.0.0.1:18080/
curl --fail -H 'Host: aws.platform.example.com' http://127.0.0.1:18080/_localstack/health
# Resolve only for this command; do not alter Windows DNS or expose admin ports.
curl --resolve aws.platform.example.com:18080:127.0.0.1 \
  http://aws.platform.example.com:18080/_localstack/health
```

Acceptance requires all four states to equal `running`, HTTP 200 for signed
`ListBuckets`, `DescribeInstances`, `ListUsers` and `ListTables`, root ingress
200/302, and matching health JSON through APISIX. A generic smoke HTTP 200 is
insufficient. `verify.sh` writes non-secret evidence under `.build/localstack/`.
The dedicated `vcloud-wsl-localstack-access.service` binds port 4566 to loopback;
stop it with `sudo systemctl stop vcloud-wsl-localstack-access.service`.

## Security, state and limits

LocalStack runs as UID/GID 65532, with no added capabilities or privilege
escalation, RuntimeDefault seccomp and a read-only root filesystem. Bounded
memory volumes provide HOME, cache, temporary files and ephemeral service
state. Exec probes do not require network-policy ingress exceptions. Only
APISIX may reach the API port. LocalStack has no service-account token, external
egress, Docker socket, hostPath, VM manager, persistence or real AWS credentials.
API test credentials are the fixed fake values `test`/`test` used inside the
LocalStack process; they must never be replaced with production AWS credentials.
EC2 calls emulate state; they do not launch VMs. GPU/vLLM/Spinifex remain disabled.

The controller uses authenticated API-driven standalone APISIX, with no etcd.
Admin port 9180 is private, TLS verified against a mounted CA, and allowed only
from the controller. Random admin credentials and TLS keys are create-only K3s
Secrets with verified encryption at rest; private bytes never reach Git, host
files, argv or environment variables. The init container composes private
APISIX configuration in tmpfs. Certificates expire after 90 days: operator
renewal is required before expiry; rerunning provisioning preserves existing
Secrets and does not rotate them. ADC receives only the public CA in its trust
mount. The controller/ADC use writable container filesystems for upstream
runtime compatibility and otherwise meet restricted PSS.

Upstream 2.2.0 uses cluster-wide informers, including read-only Secret discovery.
Its bootstrap ClusterRole grants `get/list/watch` to Secrets but no Secret
writes. Namespace-scoped Secret caching/least-privilege review is an open
production gate. Argo's new route grants exclude Secret and cluster-RBAC writes.
No new node privilege exception is granted.

## Recovery

If readiness fails, inspect `kubectl logs deployment/localstack-aws-console`
and its events, then verify writable HOME/cache and preinstalled DynamoDB JVM
assets. Do not solve startup with root, a Docker socket or public egress. If
APISIX routing fails, inspect controller status and `ApisixRoute` conditions;
verify the private admin certificate trust and network-policy path. Never print
the admin Secret or generated private config.

To roll back the gateway cutover, target the endpoint Application at the last
tested file-driven source revision `0acd2d1e8734b90b4edaecc4f343b4caba3e4e23`,
hard-refresh and verify demo HTTP 200 before removing only the new LocalStack
routes/controller resources. Prune is disabled: removed-source objects are not
automatically deleted. Do not delete shared CRDs, namespaces, database resources
or unrelated workloads. A pod replacement loses this emulator's data.

References: [LocalStack v4.14.0 source](https://github.com/localstack/localstack/tree/v4.14.0),
[separate Web Application](https://docs.localstack.cloud/aws/connecting/console/instance-management/),
[APISIX controller installation](https://apisix.apache.org/docs/ingress-controller/install/).
