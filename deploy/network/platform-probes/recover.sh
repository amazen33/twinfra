#!/usr/bin/env bash
# Run on the WSL Kubernetes node after fixing the probe-port policies.
# Replace the two Argo CD workloads to clear their old Pod restart backoff,
# then prove readiness and node-to-pod health; a restart alone is not acceptance.
set -Eeuo pipefail
umask 077
HERE=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
cd -- "$HERE/../../.."
MODE=apply
case "${1:-}" in
  '') ;;
  --plan) MODE=plan ;;
  *) printf 'Usage: recover.sh [--plan]\n' >&2; exit 2 ;;
esac
(( $# <= 1 )) || { printf 'Usage: recover.sh [--plan]\n' >&2; exit 2; }
die() { printf '%s\n' "$*" >&2; exit 1; }
command -v jq >/dev/null || die 'Missing dependency: jq. Install with: sudo apt-get update && sudo apt-get install -y jq'
for dependency in kubectl bash curl ip; do
  command -v "$dependency" >/dev/null || die "Missing dependency: $dependency"
done
ROLLOUT_TIMEOUT_SECONDS=${ROLLOUT_TIMEOUT_SECONDS:-180}
[[ $ROLLOUT_TIMEOUT_SECONDS =~ ^[1-9][0-9]*$ ]] || die 'ROLLOUT_TIMEOUT_SECONDS must be a positive integer.'
(( ROLLOUT_TIMEOUT_SECONDS <= 900 )) || die 'Maximum rollout timeout is 900 seconds.'
KUBE_CONTEXT=${KUBE_CONTEXT:-$(kubectl config current-context)}
[[ -n $KUBE_CONTEXT ]] || die 'Set KUBE_CONTEXT or select a kubectl context.'
export KUBE_CONTEXT
k() { command kubectl --context "$KUBE_CONTEXT" --request-timeout=10s "$@"; }
stage=preflight
trap 'printf "FAIL: recovery stopped during %s. See the platform probe runbook.\n" "$stage" >&2' ERR

# The native fallback and world allowance belong only to the owned WSL lab.
nodes=$(k get nodes -o json)
jq -e '.items | length > 0 and all(.[];
  .metadata.labels["vcloud.io/environment"] == "local-validation")' <<< "$nodes" >/dev/null \
  || die 'Recovery requires all Nodes labelled vcloud.io/environment=local-validation.'
k get deployment argocd-repo-server -n platform-services -o name >/dev/null
controller=$(k get statefulset argocd-application-controller -n platform-services -o json)
jq -e '(.spec.updateStrategy.type // "RollingUpdate") == "RollingUpdate"
  and (.spec.updateStrategy.rollingUpdate.partition // 0) == 0' <<< "$controller" >/dev/null \
  || die 'Controller recovery requires RollingUpdate with partition 0; no update strategy will be changed.'
# Validate node locality, all three scheduled workload types, CIDRs and CLIs
# before making any changes. The verifier's plan performs no writes or curls.
bash "$HERE/apply-and-verify.sh" --plan >/dev/null

if [[ $MODE == plan ]]; then
  printf 'Context: %s; namespace: platform-services; no changes made.\n' "$KUBE_CONTEXT"
  printf '%s\n' \
    '1. kubectl apply -f deploy/network/platform-probes/' \
    '2. kubectl rollout restart deployment argocd-repo-server -n platform-services' \
    '3. kubectl rollout restart statefulset argocd-application-controller -n platform-services' \
    "4. Wait for both rollouts (up to ${ROLLOUT_TIMEOUT_SECONDS}s each)." \
    '5. bash deploy/network/platform-probes/apply-and-verify.sh'
  exit 0
fi

stage=network-policy-apply
k apply --dry-run=server -f deploy/network/platform-probes/ >/dev/null
k apply -f deploy/network/platform-probes/
stage=argo-rollout-restart
k rollout restart deployment argocd-repo-server -n platform-services
k rollout restart statefulset argocd-application-controller -n platform-services
stage=argo-rollout-status
for target in deployment/argocd-repo-server statefulset/argocd-application-controller; do
  # A watch needs the rollout bound, rather than the short ordinary API bound.
  command kubectl --context "$KUBE_CONTEXT" --request-timeout="${ROLLOUT_TIMEOUT_SECONDS}s" \
    rollout status "$target" -n platform-services --timeout="${ROLLOUT_TIMEOUT_SECONDS}s"
done
stage=live-health-validation
# Reapply idempotently with detected PodCIDRs, then check all three workloads.
bash "$HERE/apply-and-verify.sh"
