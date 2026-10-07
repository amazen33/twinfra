#!/usr/bin/env bash
# Install the vetted local database and headless GitOps infrastructure only.
# GitOps activation is a separate target after its source branch is published.
set -euo pipefail
umask 077
ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
BUILD="$ROOT/.build/wsl-platform"
[[ $EUID == 0 && $(uname -r) == *microsoft* && -f /var/lib/vcloud-wsl/owner.json ]] || exit 1
export KUBECONFIG=/etc/vcloud-wsl/kubeconfig.yaml
kubectl() { /usr/local/bin/k3s kubectl --context vcloud-wsl-local "$@"; }
mkdir -p "$BUILD"
python3 "$ROOT/tools/wsl_platform.py" render
python3 "$ROOT/tools/wsl_platform.py" validate --kubeconform "$ROOT/.tools/wsl-lab/kubeconform"
# Gate exact images through the ACTIVE external CRI before any live storage or
# controller write. A cache-only lab may tolerate mirror DNS degradation only
# when every image in this render is already present under its canonical alias.
bash "$ROOT/scripts/validate-node.sh" --cache-only --manifest "$BUILD/infrastructure.yaml"
bash "$ROOT/lab/wsl/prepare-storage.sh" --apply
bash "$ROOT/lab/wsl/prepare-tls.sh"
# Only the public metrics serving CA is read into the bootstrap APIService.
kubectl get secret vcloud-metrics-tls -n kube-system -o jsonpath='{.data.ca\.crt}' > "$BUILD/metrics-public-ca.base64"
python3 - "$BUILD" <<'PY'
import pathlib,sys,yaml
build=pathlib.Path(sys.argv[1]);path=build/'infrastructure.yaml'
objects=list(yaml.safe_load_all(path.read_text()))
for obj in objects:
    if obj['kind']=='APIService':obj['spec']['caBundle']=(build/'metrics-public-ca.base64').read_text()
path.write_text(yaml.safe_dump_all(objects,sort_keys=False))
crds=[o for o in objects if o['kind']=='CustomResourceDefinition']
others=[o for o in objects if o['kind']!='CustomResourceDefinition']
(build/'crds.yaml').write_text(yaml.safe_dump_all(crds,sort_keys=False))
(build/'controllers.yaml').write_text(yaml.safe_dump_all(others,sort_keys=False))
PY
python3 "$ROOT/tools/wsl_platform.py" validate --kubeconform "$ROOT/.tools/wsl-lab/kubeconform"
kubectl apply --server-side --dry-run=server -f "$BUILD/crds.yaml" > /dev/null
kubectl apply --server-side -f "$BUILD/crds.yaml" > /dev/null
kubectl wait --for=condition=Established --timeout=120s -f "$BUILD/crds.yaml" > /dev/null
for file in network.yaml git-dns.yaml storage.yaml controllers.yaml; do
    kubectl apply --server-side --dry-run=server -f "$BUILD/$file" > /dev/null
    kubectl apply --server-side -f "$BUILD/$file"
done
for name in cnpg-controller-manager argocd-repo-server argocd-redis vcloud-git-dns; do
    kubectl rollout status deployment/"$name" -n platform-services --timeout=300s
done
kubectl rollout status statefulset/argocd-application-controller -n platform-services --timeout=300s
kubectl rollout status deployment/metrics-server -n kube-system --timeout=300s
kubectl wait --for=condition=Available apiservice/v1beta1.metrics.k8s.io --timeout=120s
kubectl apply --server-side --dry-run=server -f "$BUILD/workload.yaml" > /dev/null
kubectl apply --server-side -f "$BUILD/workload.yaml"
kubectl wait --for=condition=Ready cluster/vcloud-wsl-postgres -n platform-services --timeout=600s
kubectl get pvc vcloud-wsl-postgres-1 -n platform-services
printf 'Local infrastructure and PostgreSQL deployed; publish GitOps source before activating application.yaml.\n'
