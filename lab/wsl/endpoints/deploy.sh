#!/usr/bin/env bash
# Deploy only into the single owned WSL lab, after static/cache/security gates.
set -euo pipefail
umask 077
ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)
cd "$ROOT"
BUILD="$ROOT/.build/wsl-endpoints"
[[ $EUID == 0 && $(uname -r) == *microsoft* && -f /var/lib/vcloud-wsl/owner.json ]] || exit 1
export KUBECONFIG=/etc/vcloud-wsl/kubeconfig.yaml
k() { /usr/local/bin/k3s kubectl --context vcloud-wsl-local --request-timeout=60s "$@"; }
k get nodes -o json | jq -e '.items | length == 1 and .[0].metadata.name == "vcloud-wsl-local"' >/dev/null
for ns in platform-services workload-apps hpc-compute; do
  k get namespace "$ns" -o json | jq -e '.metadata.labels["pod-security.kubernetes.io/enforce"]=="restricted" and .metadata.labels["pod-security.kubernetes.io/enforce-version"]=="v1.30"' >/dev/null
done
bash "$ROOT/lab/wsl/enable-secret-encryption.sh" --check
bash "$ROOT/lab/wsl/reconcile-host-routing.sh" --check
bash "$ROOT/lab/wsl/prepare-storage.sh" --check
router=$(ip -j addr show cilium_host | jq -er '.[0].addr_info[] | select(.family=="inet") | .local')
python3 "$ROOT/tools/wsl_endpoints.py" render --router "$router"
python3 "$ROOT/tools/wsl_endpoints.py" validate
bash "$ROOT/scripts/validate-node.sh" --cache-only --images-file "$BUILD/images.txt"
for file in controllers.yaml identity.yaml application.yaml observability.yaml; do
  bash "$ROOT/scripts/validate-node.sh" --cache-only --manifest "$BUILD/$file"
done
python3 "$ROOT/tools/wsl_runtime_secrets.py"
# Password values stay in Secret mounts. The declarative role refs have no keys.
python3 - "$BUILD" <<'PY'
import json,sys
from pathlib import Path
sys.path.insert(0,str(Path.cwd()/'tools'))
from wsl_platform import workload
roles=workload()[0]['spec']['managed']
(Path(sys.argv[1])/'roles-patch.json').write_text(json.dumps({'spec':{'managed':roles}}))
PY
k -n platform-services patch cluster vcloud-wsl-postgres --type=merge --patch-file "$BUILD/roles-patch.json"
# Preserve externally managed roles until this source is published in GitOps.
if [[ $(k -n platform-services get application vcloud-wsl-platform -o jsonpath='{.spec.source.targetRevision}') != main ]] \
  && ! k -n platform-services get application vcloud-wsl-platform -o json | jq -e '.spec.ignoreDifferences[0].jsonPointers | index("/spec/managed") != null' >/dev/null; then
  k -n platform-services patch application vcloud-wsl-platform --type=json -p \
    '[{"op":"add","path":"/spec/ignoreDifferences/0/jsonPointers/-","value":"/spec/managed"}]'
fi
for file in crds.yaml network.yaml; do
  k apply --server-side --field-manager=vcloud-wsl-endpoints --dry-run=server -f "$BUILD/$file" >/dev/null
  k apply --server-side --field-manager=vcloud-wsl-endpoints -f "$BUILD/$file" >/dev/null
done
k wait --for=condition=Established --timeout=120s -f "$BUILD/crds.yaml" >/dev/null
for file in controllers.yaml identity.yaml; do
  if [[ $file == identity.yaml ]]; then
    for name in openbao keycloak; do
      if [[ $(k -n platform-services get deployment "$name" --ignore-not-found -o jsonpath='{.spec.strategy.type}') == RollingUpdate ]]; then
        k -n platform-services patch deployment "$name" --type=merge -p '{"spec":{"strategy":{"type":"Recreate","rollingUpdate":null}}}'
      fi
    done
  fi
  k apply --server-side --field-manager=vcloud-wsl-endpoints --dry-run=server -f "$BUILD/$file" >/dev/null
  k apply --server-side --field-manager=vcloud-wsl-endpoints -f "$BUILD/$file"
done
k -n platform-services rollout status deployment/openbao --timeout=300s
# Initialization remains a SEPARATE, fail-closed operator step after Service creation.
for name in controller webhook activator autoscaler net-kourier-controller 3scale-kourier-gateway; do
  k -n workload-apps rollout status deployment/"$name" --timeout=300s
done
for file in observability.yaml application.yaml; do
  k apply --server-side --field-manager=vcloud-wsl-endpoints --dry-run=server -f "$BUILD/$file" >/dev/null
  k apply --server-side --field-manager=vcloud-wsl-endpoints -f "$BUILD/$file"
done
for name in keycloak apisix twinfra-perses-operator twinfra-perses otel-collector prometheus-operator; do
  k -n platform-services rollout status deployment/"$name" --timeout=300s
done
k -n platform-services rollout status statefulset/prometheus-vcloud --timeout=300s
k -n workload-apps wait --for=condition=Ready service.serving.knative.dev/demo-cpu-app --timeout=300s
printf 'PASS: local endpoint resources deployed; run lab/wsl/test-e2e.sh for acceptance.\n'
