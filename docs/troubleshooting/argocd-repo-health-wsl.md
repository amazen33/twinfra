# Argo CD repo-server full-health DNS timeout on mirrored WSL2

Validated on `vcloud-wsl-local`, Cilium 1.20.2 and Argo CD 3.5.3 on
2026-10-07. This is an owned WSL lab repair, not production readiness.

The failing request was repo-server's `http://POD_IP:8084/healthz?full=true`.
CNPG's HTTPS `/readyz` returning 200 did not establish repo-server health.
Repo-server accepted TCP, its basic `/healthz` returned 200, and direct local
gRPC version calls succeeded. Its full check nevertheless exceeded five seconds
even from inside the Pod. Liveness then terminated the process and caused
restart backoff; connection refusal while the container was stopped was a
consequence of that cycle.

## Confirmed causes and repair

[Argo CD's pinned full-health implementation](https://github.com/argoproj/argo-cd/blob/v3.5.3/cmd/argocd-repo-server/commands/argocd_repo_server.go)
calls its own gRPC service at `localhost:8081`. Hubble recorded **DROPPED** SRV
queries for `_grpclb._tcp.localhost`. The dedicated Git DNS policy omitted that
name and the DNS server had no local answer for it. `GRPC_ENABLE_TXT_SERVICE_CONFIG`
was already `false`; disabling TXT lookup alone did not avoid the SRV lookup.
[gRPC's resolver](https://github.com/grpc/grpc-go/blob/v1.81.1/internal/resolver/dns/dns_resolver.go)
performs SRV lookup before host lookup when SRV discovery is enabled.

The renderer now permits exactly `_grpclb._tcp.localhost` to the Git DNS backend
on TCP/UDP 1053. A local CoreDNS zone answers NXDOMAIN without forwarding that
lookup externally. This negative answer lets gRPC continue to the localhost
addresses in `/etc/hosts`. CoreDNS's underscore-zone syntax warning is expected
for this service-discovery name; the zone successfully answered the queries.

Hubble also recorded dropped Redis A/AAAA lookups. The former
`*.svc.cluster.local` pattern did not match
`argocd-redis.platform-services.svc.cluster.local`. The renderer uses that exact
Redis name. External DNS/HTTPS permission remains limited to `github.com` in
the repo-specific policy.

Those DNS fixes alone did **not** resolve full health. Node nftables inspection
identified a second cause:

```nft
chain WSLOUTPUT {
    type filter hook output priority filter; policy accept;
    meta mark set 0x00000001
}
```

This WSL rule destroyed the Cilium proxy skb marks. Cilium's DNS proxy could log
an upstream answer, while the application received no reply. Connected and
unconnected UDP socket tests, TCP DNS tests, and endpoint traces confirmed the
return-path failure. Two scoped return rules before the overwrite fixed it:

```nft
meta mark & 0x00000e00 == 0x00000800 counter return
meta mark & 0x00000e00 == 0x00000a00 counter return
```

These retain Cilium's upstream/return proxy mark classes. They add no firewall
ACCEPT rule. Host Firewall, L7 proxy, native routing and full kube-proxy
replacement remain enabled. DNS then returned from the correct requested
address/port and the unchanged full health endpoint returned HTTP 200 in about
7–8 ms. Preserving marks for ordinary host traffic is outside this repair;
the previously approved WSL probe-ingress exception still applies.

Changing DNS transparent socket mode and adding scoped IP-routing rules did
not resolve the issue. Both diagnostic changes were rolled back. No blanket
loopback route or disabled Cilium feature remains from those experiments.

## Reproduce the repair on the owned lab

Run the following from the prepared WSL node. The mark helper checks root access,
the Microsoft kernel, mirrored networking and the exact bootstrap ownership
profile hash. It validates the known WSLOUTPUT shape and refuses unfamiliar or
tampered rules. The default operation prints a checked plan.

```bash
set -euo pipefail
cd /mnt/e/vCloud
export KUBECONFIG=/etc/vcloud-wsl/kubeconfig.yaml
export KUBE_CONTEXT=vcloud-wsl-local
kubectl() { command kubectl --context "$KUBE_CONTEXT" --request-timeout=15s "$@"; }
kubectl get nodes -o json | jq -e '.items | length > 0 and all(.[];
  .metadata.labels["vcloud.io/environment"] == "local-validation")' >/dev/null

# nftables supplies the reader/netlink CLI; the compatibility helper owns its
# two tagged rules, not a replacement global firewall ruleset.
sudo apt-get install -y --no-install-recommends nftables
sudo python3 tools/wsl_proxy_marks.py --plan
sudo python3 tools/wsl_proxy_marks.py --apply

# Render and validate the existing platform bundle; apply only the two DNS
# dependency objects, not storage, database or other controller resources.
python3 tools/wsl_platform.py render --build .build/wsl-platform
python3 tools/wsl_platform.py validate --build .build/wsl-platform \
  --kubeconform .tools/wsl-lab/kubeconform
python3 - <<'PY'
from pathlib import Path
import yaml
build = Path('.build/wsl-platform')
objects = []
for file, kind, name in [('network.yaml', 'CiliumNetworkPolicy', 'vcloud-wsl-argo-repo'),
                         ('git-dns.yaml', 'ConfigMap', 'vcloud-git-dns')]:
    objects.append(next(o for o in yaml.safe_load_all((build/file).read_text())
                        if o['kind'] == kind and o['metadata']['name'] == name))
(build/'repo-dns-fix.yaml').write_text(yaml.safe_dump_all(objects, sort_keys=False))
PY
kubectl apply --dry-run=server -f .build/wsl-platform/repo-dns-fix.yaml
kubectl apply -f .build/wsl-platform/repo-dns-fix.yaml
kubectl rollout restart deployment/vcloud-git-dns -n platform-services
kubectl rollout status deployment/vcloud-git-dns -n platform-services --timeout=90s

# Once dependencies work, replace the repo Pod to clear any prior backoff.
kubectl rollout restart deployment/argocd-repo-server -n platform-services
kubectl rollout status deployment/argocd-repo-server -n platform-services --timeout=90s
bash deploy/network/platform-probes/apply-and-verify.sh --verify-only
sudo bash lab/wsl/test-network.sh
```

Argo controller restart remains available through the existing
[recovery helper](../../deploy/network/platform-probes/README.md).
Restarting a workload before repairing its dependency simply repeats the failure.
Read event timestamps and Pod UIDs: warnings from previous Pods or before the
repair do not establish a current failure.

## Reconcile after WSL recreates its chain

Bootstrap now installs the helper and these units. For an existing lab, the
following targeted installation is sufficient; rerunning the full bootstrap
is unnecessary:

```bash
sudo install -m 0750 tools/wsl_proxy_marks.py /usr/local/libexec/vcloud-wsl-proxy-marks
sudo install -m 0644 lab/wsl/vcloud-wsl-proxy-marks.service /etc/systemd/system/
sudo install -m 0644 lab/wsl/vcloud-wsl-proxy-marks.timer /etc/systemd/system/
sudo systemd-analyze verify /etc/systemd/system/vcloud-wsl-proxy-marks.service \
  /etc/systemd/system/vcloud-wsl-proxy-marks.timer
sudo systemctl daemon-reload
sudo systemctl enable --now vcloud-wsl-proxy-marks.timer
sudo systemctl start vcloud-wsl-proxy-marks.service
sudo systemctl show vcloud-wsl-proxy-marks.service -p Result -p ExecMainStatus
sudo systemctl show vcloud-wsl-proxy-marks.timer -p ActiveState -p SubState
```

The timer checks every minute and after boot. Repeated application leaves the
same two rules in place. It can therefore repair a recreated WSL output chain.
The host netlink update needs root/CAP_NET_ADMIN; it adds no privileged Pod,
hostPath mount or root workload exception. The service bounds its capability to
CAP_NET_ADMIN and uses a root-owned installed copy of the helper.

For rollback, disable the timer and remove only its verified tagged rules:

```bash
sudo systemctl disable --now vcloud-wsl-proxy-marks.timer
sudo python3 /usr/local/libexec/vcloud-wsl-proxy-marks --remove
```

Removing them reinstates the observed DNS mark conflict. DNS manifest rollback
should use the reviewed prior Git version of the two dependency objects.

## TLS and acceptance evidence

The original CNPG `curl -k` warning reflected skipped certificate verification.
Access by Pod IP also differs from the certificate's service hostname. A
subsequent check with the **public webhook CA bundle**, service hostname and
`curl --resolve` returned HTTP 200 with `ssl_verify_result=0`; no private key or
credential was read. The kubelet-style probe diagnostic still uses `-k` for its
unauthenticated endpoint check and does not claim to validate TLS trust.

Evidence is stored locally under `.build/repo-health-rca/`:

| Check | Observed result |
| --- | --- |
| Full three-workload verifier | PASS; every local probe 200, Ready, stable UID/restart counters |
| CNPG strict CA/hostname check | HTTP 200; TLS verification result 0 |
| Denied Service and direct-Pod requests | Blocked; six matching Cilium Policy denied events |
| Helper and systemd units | Idempotent; service exit 0; reconciliation timer active |
| Final snapshot at 00:07:25 UTC | All three Ready; repo restart count 1 from the prior failure; last warning 00:00:30 UTC |
| WSL/platform/CI unit suites | 35 + 24 + 22 tests passed |
| Rendered platform kubeconform | 84 valid; 0 invalid, errors or skipped |
| ShellCheck | Clean for bootstrap and both probe/recovery scripts |

A WSL restart was not performed; boot-time recovery has an installed, validated
timer but a separate reboot acceptance remains. This proves the recorded local
health and deny-all scenarios, not production availability or the entire GitOps,
database, GPU/HPC or disaster-recovery stack.

The probe manifest was edited independently during the investigation. Its
ingress-only structure differed from three older tests. The subsequent DevSecOps
review restored WSL scope metadata and aligned those tests with the separate
component dependency policies. A fixture with explicit egress still proves that
CIDR injection preserves its input. Complete-suite and hosted-CI results are
recorded in the [correction review](../correction-review.md).
