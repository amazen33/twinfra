#!/usr/bin/env bash
# Stage prerequisites first. Argo CD owns the later gateway configuration/route cutover.
set -euo pipefail
umask 077
root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../../.." && pwd)
cd "$root"
[[ $EUID == 0 && $(uname -r) == *microsoft* && -f /var/lib/vcloud-wsl/owner.json ]] || exit 1
export KUBECONFIG=/etc/vcloud-wsl/kubeconfig.yaml
k() { /usr/local/bin/k3s kubectl --context=vcloud-wsl-local --request-timeout=60s "$@"; }
k get nodes -o json | jq -e '.items | length==1 and .[0].metadata.name=="vcloud-wsl-local"' >/dev/null
k get namespace platform-services -o json | jq -e '.metadata.labels["pod-security.kubernetes.io/enforce"]=="restricted" and .metadata.labels["pod-security.kubernetes.io/enforce-version"]=="v1.30"' >/dev/null
router=$(ip -j addr show cilium_host | jq -er '.[0].addr_info[] | select(.family=="inet") | .local')
python3 tools/wsl_endpoints.py render --build .build/localstack/rendered --router "$router"
python3 tools/wsl_endpoints.py validate --build .build/localstack/rendered
python3 tools/wsl_runtime_secrets.py
python3 - "$router" <<'PY'
import sys,yaml
from pathlib import Path
sys.path.insert(0,'tools')
import wsl_localstack as aws
for filename,objects in [('crds',aws.crds()),('bootstrap',aws.controller()),
                         ('network',aws.network(sys.argv[1])),('api',aws.workloads())]:
    Path('.build/localstack/'+filename+'.yaml').write_text(yaml.safe_dump_all(objects,sort_keys=False))
Path('.build/localstack/images.txt').write_text('\n'.join(i['canonical'] for i in aws.lock()['images'].values())+'\n')
PY
bash scripts/validate-node.sh --cache-only --images-file .build/localstack/images.txt
for file in crds network bootstrap api; do
  k apply --server-side --field-manager=vcloud-wsl-endpoints --dry-run=server -f ".build/localstack/$file.yaml" >/dev/null
  k apply --server-side --field-manager=vcloud-wsl-endpoints -f ".build/localstack/$file.yaml"
  if [[ $file == crds ]]; then k wait --for=condition=Established --timeout=120s -f .build/localstack/crds.yaml >/dev/null; fi
done
k -n platform-services rollout status deployment/localstack-aws-console --timeout=300s
echo 'Prerequisites staged. Publish the tested GitOps source and reconcile before running verify.sh.'
