#!/usr/bin/env bash
# Repair only the existing owned lab's vetted Argo bindings and await its DB.
# No new filesystem, storage adoption, cluster-admin grant or credentials export.
set -euo pipefail
umask 077
ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
ACTION=${1:---check}
[[ $# -le 1 && $ACTION =~ ^--(check|repair)$ ]] || exit 2
[[ $EUID == 0 && $(uname -r) == *microsoft* && -f /var/lib/vcloud-wsl/owner.json ]] || exit 1
export KUBECONFIG=/etc/vcloud-wsl/kubeconfig.yaml
k() { /usr/local/bin/k3s kubectl --context vcloud-wsl-local --request-timeout=60s "$@"; }
for command in jq python3 curl; do command -v "$command" >/dev/null; done
k get nodes -o json | jq -e '.items | length == 1 and .[0].metadata.name == "vcloud-wsl-local"' >/dev/null
# Storage and exact images are checked BEFORE restoring automated reconciliation.
bash "$ROOT/lab/wsl/prepare-storage.sh" --check
BUILD="$ROOT/.build/wsl-prerequisites"
python3 "$ROOT/tools/wsl_platform.py" render --build "$BUILD"
python3 "$ROOT/tools/wsl_platform.py" validate --build "$BUILD" \
  --kubeconform "$ROOT/.build/ci-linux-assets/bin/kubeconform" \
  --schemas "$ROOT/.build/ci-linux-assets/schemas"
bash "$ROOT/scripts/validate-node.sh" --cache-only --manifest "$BUILD/workload.yaml"
bash "$ROOT/scripts/validate-node.sh" --cache-only --manifest "$BUILD/git-dns.yaml"
k get statefulsets -A -l app.kubernetes.io/name=argocd-application-controller -o json \
  | jq -e '.items | length == 1 and .[0].metadata.namespace == "platform-services"' >/dev/null
k get clusterrolebinding argocd-application-controller -o json \
  | jq -e '.roleRef == {apiGroup:"rbac.authorization.k8s.io",kind:"ClusterRole",name:"argocd-application-controller"}
    and (.subjects | length == 1 and .[0].kind == "ServiceAccount"
      and .[0].name == "argocd-application-controller"
      and (.[0].namespace == "argocd" or .[0].namespace == "platform-services"))' >/dev/null
k get cnp vcloud-wsl-argo-repo vcloud-wsl-git-dns -n platform-services -o json > "$BUILD/live-dns-policy.json"
python3 - "$BUILD" <<'PY'
from pathlib import Path
import sys,yaml
build=Path(sys.argv[1])
selected=[]
for obj in yaml.safe_load_all((build/'infrastructure.yaml').read_text()):
    if (obj['kind'] in ('ClusterRole','ClusterRoleBinding') and obj['metadata']['name']=='argocd-application-controller') or (
        obj['kind'] in ('Role','RoleBinding') and obj['metadata']['name']=='vcloud-wsl-gitops-writer'):
        selected.append(obj)
assert len(selected)==4
role=next(o for o in selected if o['kind']=='ClusterRole')
assert role['rules']==[{'apiGroups':['*'],'resources':['*'],'verbs':['get','list','watch']}]
for obj in selected:
    if 'subjects' in obj:
        assert obj['subjects']==[{'kind':'ServiceAccount','name':'argocd-application-controller','namespace':'platform-services'}]
(build/'discovery-repair.yaml').write_text(yaml.safe_dump_all(selected,sort_keys=False))
dns_rules=[o for o in yaml.safe_load_all((build/'network.yaml').read_text())
           if o['metadata']['name'] in ('vcloud-wsl-git-dns','vcloud-wsl-argo-repo')]
assert len(dns_rules)==2
import json
live={o['metadata']['name']:o for o in json.loads((build/'live-dns-policy.json').read_text())['items']}
def canonical(value):
    if isinstance(value,dict):return {k:canonical(v) for k,v in sorted(value.items())}
    if isinstance(value,list):return sorted((canonical(v) for v in value),key=lambda v:json.dumps(v,sort_keys=True))
    return value
for obj in dns_rules:
    actual=live[obj['metadata']['name']]['spec']
    assert canonical(actual['egress'])==canonical(obj['spec']['egress']), 'Unreviewed DNS egress difference'
    # Preserve live rule ordering for SSA co-ownership, and leave the existing
    # ingress/router exception with its current manager.
    obj['spec']={'endpointSelector':actual['endpointSelector'],'egress':actual['egress']}
(build/'git-dns-policy.yaml').write_text(yaml.safe_dump_all(dns_rules,sort_keys=False))
PY
k apply --server-side --dry-run=server -f "$BUILD/discovery-repair.yaml" >/dev/null
if [[ $ACTION == --repair ]]; then
  for file in git-dns-policy.yaml git-dns.yaml; do
    k apply --server-side --field-manager=vcloud-wsl-prerequisites --dry-run=server -f "$BUILD/$file" >/dev/null
    k apply --server-side --field-manager=vcloud-wsl-prerequisites -f "$BUILD/$file"
  done
  k rollout status deployment/vcloud-git-dns -n platform-services --timeout=120s
  bash "$ROOT/lab/wsl/install-git-dns-timer.sh"
  k apply --server-side -f "$BUILD/discovery-repair.yaml"
  k annotate application vcloud-wsl-platform -n platform-services argocd.argoproj.io/refresh=hard --overwrite >/dev/null
fi
[[ $(k auth can-i list nodes --as=system:serviceaccount:platform-services:argocd-application-controller) == yes ]]
# A missing Cluster fails --check; --repair allows the already published app to create it.
for ((attempt=0; attempt<120; attempt++)); do
  app=$(k get application vcloud-wsl-platform -n platform-services -o json)
  if jq -e '.status.sync.status == "Synced" and .status.health.status == "Healthy" and
      ([.status.conditions[]? | select(.type == "ComparisonError" or .type == "SyncError")] | length == 0)' <<<"$app" >/dev/null; then
    k wait --for=condition=Ready cluster/vcloud-wsl-postgres -n platform-services --timeout=300s
    printf 'PASS: GitOps Synced/Healthy and CNPG Ready; run the TLS/pgvector persistence test next.\n'
    exit 0
  fi
  [[ $ACTION == --repair ]] || break
  sleep 5
done
printf 'FAIL: prerequisite reconciliation did not reach Synced/Healthy.\n' >&2
k get application vcloud-wsl-platform -n platform-services -o json \
  | jq '{sync:.status.sync.status,health:.status.health.status,conditions:.status.conditions,operation:.status.operationState.phase}'
exit 1
