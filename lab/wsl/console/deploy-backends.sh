#!/usr/bin/env bash
# Reversible opt-in backend staging. No console auth bypass or gateway cutover.
set -euo pipefail
umask 077
root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../../.." && pwd)
cd "$root"
for tool in python3 jq curl; do command -v "$tool" >/dev/null || { echo "Missing dependency: $tool" >&2; exit 1; }; done
[[ $EUID == 0 && $(uname -r) == *microsoft* && -f /var/lib/vcloud-wsl/owner.json ]] || exit 1
k() { /usr/local/bin/k3s kubectl --kubeconfig=/etc/vcloud-wsl/kubeconfig.yaml --context=vcloud-wsl-local --request-timeout=30s "$@"; }
k get nodes -o json | jq -e '.items | length==1 and .[0].metadata.name=="vcloud-wsl-local"' >/dev/null
k get namespace platform-services -o json | jq -e '.metadata.labels["pod-security.kubernetes.io/enforce"]=="restricted" and .metadata.labels["pod-security.kubernetes.io/enforce-version"]=="v1.30"' >/dev/null
python3 tools/wsl_console.py --check
mkdir -p .build/console
python3 - <<'PY'
import sys
from pathlib import Path
sys.path.insert(0,'tools')
from wsl_console import image
from wsl_platform import PYTHON
Path('.build/console/images.txt').write_text(image()+'\n'+PYTHON+'\n')
PY
bash scripts/validate-node.sh --cache-only --images-file .build/console/images.txt
for file in network workloads; do
  k apply --server-side --field-manager=vcloud-console-bootstrap --dry-run=server -f "lab/wsl/console/$file.yaml" >/dev/null
  k apply --server-side --field-manager=vcloud-console-bootstrap -f "lab/wsl/console/$file.yaml"
done
for name in ministack vcloud-console-shell storage-ui dynamodb-admin; do
  k -n platform-services rollout status "deployment/$name" --timeout=180s
done
echo 'PASS: backends staged; console OIDC route activation remains gated.'
