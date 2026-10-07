#!/usr/bin/env bash
# Root-owned, loopback-only AWS API access on the explicitly owned WSL lab.
set -euo pipefail
[[ ${EUID} -eq 0 && $(uname -r) == *microsoft* && -f /var/lib/vcloud-wsl/owner.json ]] || { echo 'Refusing access outside the owned WSL lab' >&2; exit 1; }
export KUBECONFIG=/etc/vcloud-wsl/kubeconfig.yaml
/usr/local/bin/k3s kubectl --context=vcloud-wsl-local get nodes -o json | jq -e '.items | length==1 and .[0].metadata.name=="vcloud-wsl-local"' >/dev/null
unit=vcloud-wsl-localstack-access.service
if ! systemctl is-active --quiet "$unit"; then
  if ss -ltn '( sport = :4566 )' | tail -n +2 | grep -q .; then
    echo 'Refusing to replace an unknown listener on port 4566' >&2; exit 1
  fi
  systemd-run --unit="$unit" --collect --property=Restart=on-failure \
    --property=NoNewPrivileges=yes --property=ProtectSystem=strict --property=ProtectHome=yes \
    --property=PrivateTmp=yes --property=MemoryMax=256M \
    /usr/local/bin/k3s kubectl --kubeconfig="$KUBECONFIG" --context=vcloud-wsl-local \
    -n platform-services port-forward --address=127.0.0.1 svc/localstack-aws-console 4566:4566
fi
echo 'LocalStack AWS API: http://127.0.0.1:4566 (loopback only)'
