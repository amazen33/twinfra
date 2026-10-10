#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
# Owner runs on the NEW worker. Preparation uses the shared Module -1 first.
set -Eeuo pipefail
[[ ${1:-} == --plan || ${1:-} == --join ]] || { echo 'Usage: join-worker.sh --plan|--join'; exit 2; }
: "${CONTROL_PLANE_ENDPOINT:?stable DNS authority:6443 required}"
: "${WORKER_IP:?worker underlay IP required}" "${CONTROL_PLANE_IP:?existing node underlay IP required}"
: "${NODE_NAME:?environment-neutral twinfra- node name required}"
[[ $CONTROL_PLANE_ENDPOINT =~ ^api\.dev\.cairo-1\.twinfra\.example\.com:6443$ ]] || exit 2
[[ $NODE_NAME =~ ^twinfra-[a-z0-9-]+$ && ! $NODE_NAME =~ lab|wsl|vcloud ]] || exit 2
# Direct node routes require a common L2, never an Internet/NAT path to the node.
route=$(ip -j route get "$CONTROL_PLANE_IP")
# $source is a jq variable bound by --arg, not a shell expansion.
# shellcheck disable=SC2016
"${JQ_BINARY:-jq}" -e --arg source "$WORKER_IP" 'length == 1 and (.[0].gateway == null) and (.[0].prefsrc == $source)' <<<"$route" >/dev/null || {
    echo 'Refused: nodes are not on a directly connected common L2; no join attempted.'; exit 2;
}
if [[ $1 == --plan ]]; then
    echo "PLAN: worker $NODE_NAME -> $CONTROL_PLANE_ENDPOINT; direct underlay checked; no join/token read"
    exit 0
fi
[[ $EUID == 0 ]] || { echo 'Root required only for kubeadm node provisioning'; exit 2; }
: "${JOIN_CONFIG:?0600 tmpfs kubeadm JoinConfiguration file required}"
[[ $JOIN_CONFIG == /run/twinfra/* && -f $JOIN_CONFIG && ! -L $JOIN_CONFIG && $(stat -c '%u:%a' "$JOIN_CONFIG") == 0:600 ]] || exit 2
[[ $(findmnt -n -o FSTYPE --target "$JOIN_CONFIG") == tmpfs ]] || { echo 'Join configuration must remain on tmpfs'; exit 2; }
# Never place the bootstrap token in argv, environment variables, Git or logs.
kubeadm config validate --config "$JOIN_CONFIG"
kubeadm join --config "$JOIN_CONFIG"
echo 'Owner: label the worker zone cairo-1a; re-check native routes and deny-all before scheduling.'
