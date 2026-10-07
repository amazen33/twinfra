#!/usr/bin/env bash
# Configure only containerd registry routing/DNS. Node administration is needed
# for /etc writes and a runtime restart only if daemon config_path changed.
# No package installs, image pulls, firewall changes or cluster deployment.
set -euo pipefail
ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
ACTION=${1:---plan}
case "$ACTION" in
  --plan) shift "$(( $# > 0 ? 1 : 0 ))"; exec python3 "$ROOT/tools/node_registry.py" configure "$@" ;;
  --apply) shift ;;
  *) printf 'Usage: bootstrap-node.sh --plan|--apply [--registry-address IP] [--ca-file PUBLIC_CA]\n' >&2; exit 2 ;;
esac
[[ $EUID == 0 ]] || { printf 'Node administrator access is required for --apply.\n' >&2; exit 2; }
REPORT=$(python3 "$ROOT/tools/node_registry.py" configure --apply "$@")
printf '%s\n' "$REPORT"
if printf '%s' "$REPORT" | python3 -c 'import json,sys; sys.exit(not json.load(sys.stdin)["daemonConfigChanged"])'; then
  systemctl restart containerd
fi
# Configuration completion is distinct from a reachable mirror acceptance gate.
registry_ca_file=$(printf '%s' "$REPORT" | python3 -c 'import json,sys; print(json.load(sys.stdin)["caFile"])')
exec bash "$ROOT/scripts/validate-node.sh" --network-only --ca-file "$registry_ca_file"
