#!/usr/bin/env bash
# The approved WSL workaround traverses netfilter without disabling native CNI,
# BPF masquerading, kube-proxy replacement or policy. --apply briefly rolls Cilium.
set -euo pipefail
ACTION=${1:---check}
[[ $# -le 1 && $ACTION =~ ^--(check|apply)$ ]] || exit 2
[[ $EUID == 0 && $(uname -r) == *microsoft* && -f /var/lib/vcloud-wsl/owner.json ]] || exit 1
export KUBECONFIG=/etc/vcloud-wsl/kubeconfig.yaml
k() { /usr/local/bin/k3s kubectl --context=vcloud-wsl-local --request-timeout=40s "$@"; }
k get nodes -o json | jq -e '.items | length == 1 and .[0].metadata.name=="vcloud-wsl-local"' >/dev/null
data=$(k -n kube-system get configmap cilium-config -o json)
jq -e '.data | .["kube-proxy-replacement"]=="true" and .["enable-bpf-masquerade"]=="true"
    and .["routing-mode"]=="native"' <<<"$data" >/dev/null
before=$(jq -er '.data["enable-host-legacy-routing"]' <<<"$data")
if [[ $before == true ]]; then printf 'PASS: measured WSL host routing enabled; native BPF CNI retained.\n'; exit 0; fi
[[ $before == false && $ACTION == --apply ]] || { printf 'FAIL: WSL host routing requires explicit --apply.\n' >&2; exit 1; }
restore() {
  k -n kube-system patch configmap cilium-config --type=merge -p '{"data":{"enable-host-legacy-routing":"false"}}'
  k -n kube-system rollout restart daemonset/cilium
  k -n kube-system rollout status daemonset/cilium --timeout=180s
}
trap restore EXIT
k -n kube-system patch configmap cilium-config --type=merge -p '{"data":{"enable-host-legacy-routing":"true"}}'
k -n kube-system rollout restart daemonset/cilium
k -n kube-system rollout status daemonset/cilium --timeout=180s
k -n platform-services exec deployment/argocd-repo-server -- timeout 25 git ls-remote https://github.com/amazen33/twinfra.git HEAD
trap - EXIT
printf 'PASS: GitHub fetch succeeded; WSL host-routing workaround retained.\n'
