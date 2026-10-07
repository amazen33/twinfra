#!/usr/bin/env bash
# Private local access. Root reads only the lab kubeconfig; all listeners bind
# 127.0.0.1. Refuse unknown occupied ports and never stop another service.
set -euo pipefail
umask 077
ACTION=${1:-start}
[[ $ACTION == start || $ACTION == openbao ]] || exit 2
[[ $EUID == 0 && $(uname -r) == *microsoft* && -f /var/lib/vcloud-wsl/owner.json ]] || exit 1
CFG=/etc/vcloud-wsl/kubeconfig.yaml
export KUBECONFIG=$CFG
k() { /usr/local/bin/k3s kubectl --context vcloud-wsl-local --request-timeout=30s "$@"; }
k get nodes -o json | jq -e '.items | length == 1 and .[0].metadata.name == "vcloud-wsl-local"' >/dev/null
forward() {
  local unit=$1 resource=$2 mapping=$3 ns=${4:-platform-services} port=${3%%:*}
  if systemctl is-active --quiet "$unit"; then return; fi
  [[ -z $(ss -H -ltn "sport = :$port") ]] || { printf 'FAIL: unknown listener on port %s\n' "$port" >&2; exit 1; }
  systemd-run --unit="$unit" --collect --property=Restart=on-failure --property=RestartSec=3 \
    --property=NoNewPrivileges=yes --property=ProtectSystem=strict --property=ProtectHome=yes \
    --property=PrivateTmp=yes --property=MemoryMax=256M \
    /usr/local/bin/k3s kubectl --kubeconfig="$CFG" --context=vcloud-wsl-local \
    -n "$ns" port-forward --address=127.0.0.1 "$resource" "$mapping"
}
# HTTP listener lives exclusively on Pod loopback, never in a Service port.
forward vcloud-wsl-openbao-init.service deployment/openbao 8200:8201
if [[ $ACTION == openbao ]]; then exit 0; fi
# Replace the EXACT known earlier smoke unit only when APISIX is Ready.
k -n platform-services rollout status deployment/apisix --timeout=60s
if systemctl is-active --quiet vcloud-wsl-http-access.service; then
  systemctl stop vcloud-wsl-http-access.service
fi
forward vcloud-wsl-apisix-access.service svc/apisix 18080:9080
forward vcloud-wsl-prometheus-access.service svc/prometheus 9090:9090
forward vcloud-wsl-grafana-access.service svc/grafana 3000:3000
forward vcloud-wsl-keycloak-access.service svc/keycloak 18443:443
printf 'Local listeners started; verify HTTP/API responses with lab/wsl/test-e2e.sh.\n'
