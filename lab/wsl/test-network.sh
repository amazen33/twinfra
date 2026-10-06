#!/usr/bin/env bash
# Live deny-all evidence: prove the server is healthy and DNS works, then tie
# denied Service and direct-Pod requests to Cilium Policy denied events.
set -euo pipefail
umask 077
ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
BUILD="$ROOT/.build/wsl-network"
mkdir -p "$BUILD"
export KUBECONFIG=/etc/vcloud-wsl/kubeconfig.yaml
kubectl() { /usr/local/bin/k3s kubectl --context vcloud-wsl-local "$@"; }
kubectl wait -n platform-services --for=condition=Ready pod/vcloud-lab-server --timeout=60s
kubectl wait -n hpc-compute --for=condition=Ready pod/vcloud-lab-denied --timeout=60s
SERVER_IP=$(kubectl get pod -n platform-services vcloud-lab-server -o jsonpath='{.status.podIP}')
DENIED_IP=$(kubectl get pod -n hpc-compute vcloud-lab-denied -o jsonpath='{.status.podIP}')
HOST=vcloud-lab-server.platform-services.svc.cluster.local
kubectl exec -n hpc-compute vcloud-lab-denied -- nslookup "$HOST" > "$BUILD/dns.txt"
kubectl exec -n workload-apps vcloud-lab-allowed -- wget -T 5 -qO- "http://$HOST:8080" | grep -qx vcloud-wsl-ok
timeout 18 kubectl exec -n kube-system daemonset/cilium -- cilium-dbg monitor --type drop > "$BUILD/cilium-drops.txt" 2>&1 &
MONITOR=$!
trap 'kill "$MONITOR" 2>/dev/null || true' EXIT
sleep 2
for target in "$HOST" "$SERVER_IP"; do
    if kubectl exec -n hpc-compute vcloud-lab-denied -- wget -T 3 -qO- "http://$target:8080" > "$BUILD/denied-$target.txt" 2>&1; then
        printf 'Unauthorized request succeeded: %s\n' "$target" >&2; exit 1
    fi
    grep -qi 'timed out' "$BUILD/denied-$target.txt" || { printf 'Unexpected probe failure\n' >&2; exit 1; }
done
sleep 1
kill "$MONITOR" 2>/dev/null || true
wait "$MONITOR" 2>/dev/null || true
python3 - "$BUILD" "$DENIED_IP" "$SERVER_IP" <<'PY'
from datetime import datetime,timezone
import json,pathlib,sys
build=pathlib.Path(sys.argv[1]); source,target=sys.argv[2:]
events=[line for line in (build/'cilium-drops.txt').read_text().splitlines()
        if 'Policy denied' in line and source in line and target in line]
if not events: raise SystemExit('No matching Cilium policy-drop event; refusing a timeout-only pass')
report={'status':'passed','timestampUTC':datetime.now(timezone.utc).isoformat(),
 'context':'vcloud-wsl-local','source':'hpc-compute/vcloud-lab-denied',
 'destination':'platform-services/vcloud-lab-server','port':8080,'protocol':'TCP',
 'dns':'passed','allowedControlHTTP':'passed','unauthorizedServiceHTTP':'blocked',
 'unauthorizedDirectPodHTTP':'blocked','matchingCiliumPolicyDrops':len(events),
 'dropEvents':events[:10]}
(build/'acceptance.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2))
PY
