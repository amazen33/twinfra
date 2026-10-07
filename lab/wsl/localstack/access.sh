#!/usr/bin/env bash
# Root-owned, loopback-only AWS API access on the explicitly owned WSL lab.
set -euo pipefail
for tool in jq curl ss systemctl systemd-run; do
  command -v "$tool" >/dev/null || { echo "Missing dependency: $tool" >&2; exit 1; }
done
[[ ${EUID} -eq 0 && $(uname -r) == *microsoft* && -f /var/lib/vcloud-wsl/owner.json ]] || { echo 'Refusing access outside the owned WSL lab' >&2; exit 1; }
export KUBECONFIG=/etc/vcloud-wsl/kubeconfig.yaml
k() { /usr/local/bin/k3s kubectl --context=vcloud-wsl-local --request-timeout=15s "$@"; }
k get nodes -o json | jq -e '.items | length==1 and .[0].metadata.name=="vcloud-wsl-local"' >/dev/null
k -n platform-services rollout status deployment/localstack-aws-console --timeout=90s >/dev/null
unit=vcloud-wsl-localstack-access.service
if ! systemctl is-active --quiet "$unit"; then
  if ss -ltn '( sport = :4566 )' | tail -n +2 | grep -q .; then
    echo 'Refusing to replace an unknown listener on port 4566' >&2; exit 1
  fi
  # A short API-server outage previously caused immediate retries to hit
  # systemd's start limit, permanently losing this owned loopback listener.
  systemd-run --unit="$unit" --collect --property=Restart=on-failure \
    --property=RestartSec=3 --property=StartLimitIntervalSec=0 \
    --property=NoNewPrivileges=yes --property=ProtectSystem=strict --property=ProtectHome=yes \
    --property=PrivateTmp=yes --property=MemoryMax=256M \
    /usr/local/bin/k3s kubectl --kubeconfig="$KUBECONFIG" --context=vcloud-wsl-local \
    -n platform-services port-forward --address=127.0.0.1 svc/localstack-aws-console 4566:4566
fi
# Starting a transient unit is asynchronous; return success only for the
# actual four-service backend, not an allocated unit name or a generic 200.
for _ in {1..20}; do
  if curl --fail --silent --show-error --max-time 3 http://127.0.0.1:4566/_localstack/health 2>/dev/null |
    jq -e '.services | [.s3,.ec2,.iam,.dynamodb] | all(.=="running")' >/dev/null; then
    echo 'LocalStack AWS API: http://127.0.0.1:4566 (loopback only; health verified)'
    exit 0
  fi
  sleep 1
done
echo "FAIL: LocalStack listener/backend unavailable; inspect journalctl -u $unit" >&2
exit 1
