#!/usr/bin/env bash
# Operate only the owned local lab. GET runs before PGP checks; missing keys
# return code 3. This helper never unseals OpenBao or obtains a plaintext token.
set -euo pipefail
umask 077
ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
[[ $# -eq 0 || ( $# -eq 1 && $1 == --check-only ) ]] || exit 2
[[ $EUID == 0 && $(uname -r) == *microsoft* && -f /var/lib/vcloud-wsl/owner.json ]] || exit 1
for command in python3 kubectl jq; do command -v "$command" >/dev/null || { printf 'Missing dependency: %s\n' "$command" >&2; exit 1; }; done
export KUBECONFIG=/etc/vcloud-wsl/kubeconfig.yaml
kubectl --context vcloud-wsl-local get nodes -o json | jq -e '.items | length == 1 and .[0].metadata.name == "vcloud-wsl-local"' >/dev/null
kubectl --context vcloud-wsl-local get service openbao -n platform-services >/dev/null
exec python3 "$ROOT/tools/openbao_pgp_init.py" "$@"
