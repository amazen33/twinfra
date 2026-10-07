#!/usr/bin/env bash
# Never apply incomplete OIDC config to the shared ADC-managed gateway.
set -euo pipefail
root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../../.." && pwd)
cd "$root"
python3 tools/wsl_console.py --check
python3 tools/wsl_console_preflight.py
[[ ${VCLOUD_CONSOLE_ISSUER_VERIFIED:-false} == true ]] || {
  echo 'Console activation gated: verify Keycloak issuer, APISIX CA trust and callback first (README).' >&2
  exit 3
}
k() { /usr/local/bin/k3s kubectl --kubeconfig=/etc/vcloud-wsl/kubeconfig.yaml --context=vcloud-wsl-local --request-timeout=30s "$@"; }
k apply --server-side --dry-run=server -f lab/wsl/console/reference/argocd.yaml >/dev/null
k apply --server-side --field-manager=vcloud-console-bootstrap -f lab/wsl/console/reference/argocd.yaml
echo 'Console Application activated. Run verify.sh and authenticated browser acceptance.'
