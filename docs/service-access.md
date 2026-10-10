# Twinfra service URLs and browser access

The current target is **twinfra-dev-cairo-1**, namespace
`twinfra-platform-services`, under [ADR-0046](adr/0046-naming-dev-environment-and-regions.md).
Follow the [dev environment runbook](dev-environment.md) for provisioning,
image staging, dev CA trust, DNS and loopback SSH tunnels. These addresses are
configured targets; live acceptance is **Pending**. Earlier WSL results remain
in the unchanged [acceptance receipts](acceptance/README.md).

## Unified Twinfra console profile

| Browser URL | Function | Live status |
| --- | --- | --- |
| <https://console.dev.cairo-1.twinfra.example.com:18444/console/overview> | Namespace workload health | Pending |
| <https://console.dev.cairo-1.twinfra.example.com:18444/console/storage> | MiniStack S3 buckets and up to 100 object keys | Pending |
| <https://console.dev.cairo-1.twinfra.example.com:18444/console/cloud> | MiniStack health and EC2 instance metadata | Pending |
| <https://console.dev.cairo-1.twinfra.example.com:18444/console/dynamodb> | MiniStack table names and metadata | Pending |
| <https://console.dev.cairo-1.twinfra.example.com:18444/console/gitops> | Argo Application sync/health | Pending |
| <https://console.dev.cairo-1.twinfra.example.com:18444/console/iam> | Keycloak identity and console roles | Pending |
| <https://console.dev.cairo-1.twinfra.example.com:18444/console/metrics/> | Perses delivery and health dashboards | Pending; dev Prometheus under WO-10 |
| <https://auth.dev.cairo-1.twinfra.example.com:18443/admin/> | Native Keycloak administration; separate realm permissions | Pending |
| <https://gitops.dev.cairo-1.twinfra.example.com:18081/> | Native Argo CD server | Pending |

The portal has one AWS emulator, MiniStack. The emulator selector was removed;
the AWS tab uses `/console/cloud`. S3/EC2/DynamoDB views remain read-only and
SigV4 requests use the fixed internal MiniStack endpoint. The console verifies
signed Keycloak tokens and console roles; passwords and tokens stay out of Git
and public evidence. See the [portal reference](../console/README.md).

## Start, check and stop access

Use steps 13–15 of the [dev runbook](dev-environment.md) for gateway/identity
tunnels and name-constrained CA trust. After owner authorization, a separate
MiniStack API forward can verify that port 4566 reaches MiniStack.

On the VM, with its verified local kubeadm configuration:

```bash
sudo kubectl --kubeconfig /etc/kubernetes/admin.conf -n twinfra-platform-services \
  port-forward --address 127.0.0.1 svc/twinfra-ministack 4566:4566
```

In a separate Windows terminal:

```powershell
ssh -N -o ExitOnForwardFailure=yes -L 127.0.0.1:4566:127.0.0.1:4566 twinfra-operator@10.50.0.10
Invoke-RestMethod http://127.0.0.1:4566/_ministack/health
```

Keep the forward and SSH tunnel in separate terminal sessions. Stop them with
Ctrl-C. Expected: HTTP 200 from MiniStack's health endpoint. API roots return
JSON/XML, rather than a browser dashboard. Raw SDK/CLI clients must sign the
direct endpoint; prefixed APISIX routes are not a universal SigV4 endpoint.

WO-06 performed no live removal or forwarding. Before any cleanup, the owner
must inspect the actual dev inventory and approve removal of any obsolete
Deployment, Service, route or owned forward. Do not apply the retired WSL
procedures to this environment. The new
[removal receipt](acceptance/localstack-removal-2026-10-10.md) leaves before/after
live state and browser acceptance Pending.

## Services with no working browser endpoint

GPU/vLLM, Spinifex offloading, Knative and durable trace storage are
excluded from the rebuilt dev profile. No billing console, real EC2 instances
or additional AWS services were added by WO-06. MiniStack remains an ephemeral
development emulator. The previous emulator's module, runtime routes and
pending-removal licence authorization have been removed from the repository.

WO-07 replaces Grafana with [Perses](../deploy/observability/perses/README.md)
behind APISIX OIDC. There is no direct Perses browser forward. Dashboard data
and viewer acceptance remain [Pending](acceptance/perses-2026-10-10.md).

## OpenBao operator endpoint

Use the [dev runbook](dev-environment.md) for verified TLS and the operator key
ceremony gate. Ready transport does not establish initialization, unseal or
secrets acceptance. These gates remain Pending; WO-06 changes none of them.
