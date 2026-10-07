#!/usr/bin/env bash
# Run on a Kubernetes node, with kubectl credentials for the intended cluster.
# WSL probe-port policy exception; no privileged pods or host firewall changes.
set -euo pipefail
umask 077
HERE=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
NAMESPACE=platform-services
SELECTOR='app.kubernetes.io/name in (cloudnative-pg,argocd-repo-server,argocd-application-controller)'
WORKLOADS=(cloudnative-pg argocd-repo-server argocd-application-controller)
MODE=apply
USE_CILIUM=true
for argument in "$@"; do
  case "$argument" in
    --plan) MODE=plan ;;
    --verify-only) MODE=verify ;;
    --kubernetes-only) USE_CILIUM=false ;;
    *) printf 'Usage: apply-and-verify.sh [--plan|--verify-only] [--kubernetes-only]\n' >&2; exit 2 ;;
  esac
done
die() { printf '%s\n' "$*" >&2; exit 1; }
command -v jq >/dev/null || die 'Missing dependency: jq. Install with: sudo apt-get update && sudo apt-get install -y jq'
for dependency in kubectl curl ip; do
  command -v "$dependency" >/dev/null || die "Missing dependency: $dependency"
done
TIMEOUT_SECONDS=${TIMEOUT_SECONDS:-180}
POLL_SECONDS=${POLL_SECONDS:-5}
[[ $TIMEOUT_SECONDS =~ ^[1-9][0-9]*$ && $POLL_SECONDS =~ ^[1-9][0-9]*$ ]] || die 'Timeouts must be positive integers.'
(( TIMEOUT_SECONDS <= 900 && POLL_SECONDS <= 30 )) || die 'Maximum timeout is 900 seconds; maximum poll interval is 30 seconds.'
CONTEXT=${KUBE_CONTEXT:-$(kubectl config current-context)}
[[ -n $CONTEXT ]] || die 'Set KUBE_CONTEXT or select a kubectl context.'
k() { command kubectl --context "$CONTEXT" --request-timeout=10s "$@"; }
WORK=$(mktemp -d)
trap 'rm -f -- "$WORK/nodes.json" "$WORK/pods.json" "$WORK/fallback.json" "$WORK/cilium.json" "$WORK/body.out"
      rmdir -- "$WORK"' EXIT

# Verify that curl will execute on a real node of this cluster, never in a pod.
k get nodes -o json > "$WORK/nodes.json"
local_ips=$(ip -j address show | jq -c '[.[].addr_info[]?.local]')
mapfile -t local_nodes < <(jq -r --argjson ips "$local_ips" '
  .items[] | select(any(.status.addresses[]?;
    .type == "InternalIP" and (.address as $addr | $ips | index($addr) != null)))
  | .metadata.name' "$WORK/nodes.json")
if [[ -n ${PROBE_NODE_NAME:-} ]]; then
  printf '%s\n' "${local_nodes[@]}" | grep -Fxq -- "$PROBE_NODE_NAME" || die 'PROBE_NODE_NAME does not match a local Node InternalIP.'
  LOCAL_NODE=$PROBE_NODE_NAME
else
  (( ${#local_nodes[@]} == 1 )) || die 'Run on one cluster node, or set PROBE_NODE_NAME when several node IPs are local.'
  LOCAL_NODE=${local_nodes[0]}
fi
printf 'Context: %s; namespace: %s; curl node: %s\n' "$CONTEXT" "$NAMESPACE" "$LOCAL_NODE"
k get pods -n "$NAMESPACE" -l "$SELECTOR" -o json > "$WORK/pods.json"
for workload in "${WORKLOADS[@]}"; do
  jq -e --arg workload "$workload" --arg node "$LOCAL_NODE" '
    any(.items[]; .metadata.deletionTimestamp == null and .spec.nodeName == $node
      and .metadata.labels["app.kubernetes.io/name"] == $workload)' "$WORK/pods.json" >/dev/null \
    || die "No $workload pod scheduled on $LOCAL_NODE; run verification on its node."
done

if [[ $MODE != verify ]]; then
  if [[ $MODE == apply ]]; then
    jq -e '.items | length > 0 and all(.[];
      .metadata.labels["vcloud.io/environment"] == "local-validation")' "$WORK/nodes.json" >/dev/null \
      || die 'This broad probe-port exception is for the local-validation cluster only; refusing an unlabelled or mixed production profile.'
  fi
  # These are node-assigned POD subnets, not the management LAN or Service CIDR.
  # Preserve the requested 10.42.0.0/16 reference and add actual node allocations.
  pod_cidrs=$(jq -ce '[.items[] | (if (.spec.podCIDRs // [] | length) > 0
        then .spec.podCIDRs else [.spec.podCIDR] end)[] | select(. != null and . != "")]
    | unique | if length == 0 then error("No Node spec.podCIDR/spec.podCIDRs; refusing to guess") else . end
    | if all(.[]; type == "string" and (split("/") | length == 2)
        and (split("/")[1] | tonumber) > 0
        and (split("/")[1] | tonumber) <= (if contains(":") then 128 else 32 end))
      then . else error("Invalid or default-route node PodCIDR") end' "$WORK/nodes.json")
  printf 'Detected node PodCIDRs: %s\n' "$pod_cidrs"
  if [[ $USE_CILIUM == true ]]; then
    k create --dry-run=client --validate=false -f "$HERE/cilium-platform-probes.yaml" -o json \
      | jq -se --argjson cidrs "$pod_cidrs" '
        [.[] | if .kind == "List" then .items[] else . end]
        | if length == 1 then .[0] else error("Expected one Cilium policy") end
        | .spec.ingress |= map(if has("fromCIDRSet")
            then .fromCIDRSet = ((.fromCIDRSet + ($cidrs | map({cidr: .}))) | unique_by(.cidr))
            elif has("fromCIDR") then .fromCIDR = ((.fromCIDR + $cidrs) | unique)
            else . end)
        | .metadata.annotations["vcloud.io/detected-node-pod-cidrs"] = ($cidrs | tojson)' > "$WORK/cilium.json"
  fi
  # kubectl versions emit a JSON stream or a List. Normalize either to ONE List.
  k create --dry-run=client --validate=false -f "$HERE/k8s-platform-probes.yaml" -o json \
    | jq -s --argjson cidrs "$pod_cidrs" '
      [.[] | if .kind == "List" then .items[] else . end]
      | map(.metadata.annotations["vcloud.io/detected-node-pod-cidrs"] = ($cidrs | tojson))
      | {apiVersion: "v1", kind: "List", items: .}' > "$WORK/fallback.json"
  if [[ $MODE == plan ]]; then
    if [[ $USE_CILIUM == true ]]; then cat "$WORK/cilium.json"; fi
    cat "$WORK/fallback.json"
    exit 0
  fi
  # Check BOTH objects on the server before either is changed.
  if [[ $USE_CILIUM == true ]]; then
    k apply --dry-run=server -f "$WORK/cilium.json" >/dev/null
  fi
  k apply --dry-run=server -f "$WORK/fallback.json" >/dev/null
  if [[ $USE_CILIUM == true ]]; then k apply -f "$WORK/cilium.json"; fi
  k apply -f "$WORK/fallback.json"
fi

deadline=$((SECONDS + TIMEOUT_SECONDS))
stable=0
previous=''
while (( SECONDS < deadline )); do
  k get pods -n "$NAMESPACE" -l "$SELECTOR" -o json > "$WORK/pods.json"
  jq -r '.items[] | select(.metadata.deletionTimestamp == null)
    | [.metadata.name, .status.phase,
       ([.status.containerStatuses[]? | .restartCount] | add // 0),
       ([.status.conditions[]? | select(.type == "Ready") | .status][0] // "Unknown")]
    | @tsv' "$WORK/pods.json"
  healthy=true
  if ! jq -e '.items | map(select(.metadata.deletionTimestamp == null))
    | length > 0 and all(.[]; .status.phase == "Running"
        and any(.status.conditions[]?; .type == "Ready" and .status == "True"))' "$WORK/pods.json" >/dev/null; then
    healthy=false
  fi
  # Require all three workloads on this node in every poll, including rollouts.
  for workload in "${WORKLOADS[@]}"; do
    if ! jq -e --arg workload "$workload" --arg node "$LOCAL_NODE" '
      any(.items[]; .metadata.deletionTimestamp == null and .spec.nodeName == $node
        and .metadata.labels["app.kubernetes.io/name"] == $workload)' "$WORK/pods.json" >/dev/null; then
      healthy=false
    fi
  done
  while IFS=$'\t' read -r name workload pod_ip; do
    if [[ -z $pod_ip || $pod_ip == null ]]; then healthy=false; continue; fi
    authority=$pod_ip
    if [[ $pod_ip == *:* ]]; then authority="[$pod_ip]"; fi
    case "$workload" in
      cloudnative-pg) url="https://$authority:9443/readyz" ;;
      argocd-repo-server) url="http://$authority:8084/healthz?full=true" ;;
      argocd-application-controller) url="http://$authority:8082/healthz" ;;
      *) die "Unexpected selected workload: $workload" ;;
    esac
    # -k is limited to this unauthenticated kubelet-style diagnostic. No OpenBao
    # request, API bearer token, credentials or redirects are involved.
    if code=$(curl -k -v --noproxy '*' --max-time 5 --connect-timeout 5 \
      --proto '=http,https' -o "$WORK/body.out" -w '%{http_code}' "$url"); then
      printf 'Node probe %s: HTTP %s\n' "$name" "$code"
      if [[ $code != 200 ]]; then healthy=false; fi
    else
      printf 'Node probe %s: connection failed\n' "$name" >&2
      healthy=false
    fi
  done < <(jq -r --arg node "$LOCAL_NODE" '.items[]
    | select(.metadata.deletionTimestamp == null and .spec.nodeName == $node)
    | [.metadata.name, .metadata.labels["app.kubernetes.io/name"], .status.podIP] | @tsv' "$WORK/pods.json")
  current=$(jq -c '[.items[] | select(.metadata.deletionTimestamp == null)
    | {uid: .metadata.uid, restarts: [.status.containerStatuses[]? | .restartCount]}] | sort_by(.uid)' "$WORK/pods.json")
  if [[ $healthy == true ]]; then
    if [[ $current == "$previous" ]]; then stable=$((stable + 1)); else stable=1; fi
    if (( stable >= 2 )); then
      printf 'PASS: all three workloads Ready, all local pod probes HTTP 200, stable restart counters across two polls.\n'
      exit 0
    fi
  else
    stable=0
  fi
  previous=$current
  if (( SECONDS < deadline )); then sleep "$POLL_SECONDS"; fi
done
printf 'FAIL: probe/readiness acceptance did not pass within %ss.\n' "$TIMEOUT_SECONDS" >&2
k get events -n "$NAMESPACE" --field-selector type=Warning --sort-by=.lastTimestamp || true
printf 'Inspect Cilium drops/source identities, host egress policy, routes and listeners; explicit deny rules override allows.\n' >&2
exit 1
