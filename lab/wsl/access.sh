#!/usr/bin/env bash
# Local browser access to the existing WSL Core installation; no cluster install.
# Root is required only to read the lab's private, root-owned kubeconfig.
set -euo pipefail
umask 077
ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
ACTION=${1:-status}
DASH=vcloud-wsl-argocd-dashboard.service
HTTP=vcloud-wsl-http-access.service
STATE=/var/lib/vcloud-wsl/access
CLI="$STATE/argocd-v3.5.3"
export KUBECONFIG=/etc/vcloud-wsl/kubeconfig.yaml
k() { /usr/local/bin/k3s kubectl --context vcloud-wsl-local --request-timeout=60s "$@"; }
fail() { printf 'FAIL: %s\n' "$*" >&2; exit 1; }
[[ $# -le 1 && $ACTION =~ ^(start|status|stop)$ ]] || fail 'Usage: access.sh start|status|stop'
[[ $EUID == 0 && $(uname -r) == *microsoft* && -f /var/lib/vcloud-wsl/owner.json ]] \
  || fail 'Run with sudo inside the owned vcloud-wsl-local WSL distribution.'
for command in curl jq systemctl; do command -v "$command" >/dev/null || fail "Missing: $command"; done

status() {
  systemctl is-active "$DASH" "$HTTP" || return 1
  # Check data as well as the HTML shell: an empty/unreachable API is not a UI pass.
  curl --noproxy '*' --fail --silent --show-error --max-time 10 http://127.0.0.1:8080/ >/dev/null
  curl --noproxy '*' --fail --silent --show-error --max-time 15 http://127.0.0.1:8080/api/v1/applications \
    | jq -e '[.items[]? | {name:.metadata.name,sync:.status.sync.status,health:.status.health.status}]'
  [[ $(curl --noproxy '*' --fail --silent --show-error --max-time 10 http://127.0.0.1:18080/) == vcloud-wsl-ok ]] \
    || fail 'The lab HTTP service returned an unexpected body.'
  printf 'Argo CD Core UI: http://127.0.0.1:8080/applications\nLab HTTP smoke: http://127.0.0.1:18080/\n'
}

if [[ $ACTION == stop ]]; then
  # Only stop our two exact transient units, never arbitrary listeners or Pods.
  for unit in "$DASH" "$HTTP"; do
    if [[ $(systemctl show "$unit" --property=LoadState --value) == loaded ]]; then
      systemctl stop "$unit"
    fi
  done
  exit 0
elif [[ $ACTION == status ]]; then
  status
  exit 0
fi

for command in ss sha256sum systemd-run; do command -v "$command" >/dev/null || fail "Missing: $command"; done
k get nodes -o json | jq -e '.items | length == 1 and .[0].metadata.name == "vcloud-wsl-local"' >/dev/null \
  || fail 'Context does not point to the single owned WSL lab node.'
k -n platform-services wait --for=condition=Ready pod -l app.kubernetes.io/name=argocd-repo-server --timeout=45s >/dev/null
k -n platform-services wait --for=condition=Ready pod/vcloud-lab-server --timeout=45s >/dev/null

# Refuse to displace another process. Repeated starts retain our healthy units.
for pair in "$DASH:8080" "$HTTP:18080"; do
  unit=${pair%:*}; port=${pair##*:}
  if ! systemctl is-active --quiet "$unit" && [[ -n $(ss -H -ltn "sport = :$port") ]]; then
    fail "Port $port is already occupied; no process was stopped."
  fi
done

# Reuse the already cached, digest-pinned image; no floating CLI download needed.
pod=$(k -n platform-services get pods -l app.kubernetes.io/name=argocd-repo-server -o json \
  | jq -er '.items[] | select(any(.status.conditions[]?; .type=="Ready" and .status=="True")) | .metadata.name' | head -n 1)
image=$(k -n platform-services get pod "$pod" -o json \
  | jq -er '.spec.containers[] | select(.name=="argocd-repo-server") | .image')
image_id=$(k -n platform-services get pod "$pod" -o json \
  | jq -er '.status.containerStatuses[] | select(.name=="argocd-repo-server") | .imageID')
expected_image=$(jq -er '.images.argocd.canonical' "$ROOT/deploy/registry-images.lock.json")
expected_tag="${expected_image%@*}:v3.5.3"
# Older lab renders have a pinned tag alias; validate the actual runtime digest too.
[[ ( $image == "$expected_image" || $image == "$expected_tag" ) && $image_id == "$expected_image" ]] \
  || fail 'Repo-server does not run the locked Argo CD image digest.'
expected_sha=$(k -n platform-services exec "$pod" -c argocd-repo-server -- sha256sum /usr/local/bin/argocd | awk '{print $1}')
[[ $expected_sha =~ ^[0-9a-f]{64}$ ]] || fail 'Unable to verify the cached CLI binary hash.'
install -d -o root -g root -m 0700 "$STATE"
if [[ ! -f $CLI || $(sha256sum "$CLI" | awk '{print $1}') != "$expected_sha" ]]; then
  staging=$(mktemp "$STATE/.argocd.XXXXXX")
  trap 'rm -f -- "${staging:-}"' EXIT
  k -n platform-services exec "$pod" -c argocd-repo-server -- cat /usr/local/bin/argocd > "$staging"
  [[ $(sha256sum "$staging" | awk '{print $1}') == "$expected_sha" ]] || fail 'CLI copy hash mismatch.'
  install -o root -g root -m 0755 "$staging" "$CLI"
fi
[[ $("$CLI" version --client --short) == 'argocd: v3.5.3' ]] || fail 'Unexpected CLI version.'

# Transient units keep access alive after the shell exits, until WSL stops.
# Core's upstream dashboard uses Kubernetes credentials and has no login prompt.
# Bind only loopback; do not expose this admin session on a LAN/public interface.
properties=(--collect --property=Restart=on-failure --property=RestartSec=5
  --property=User=root --property=SetLoginEnvironment=yes
  --property=NoNewPrivileges=yes --property=ProtectSystem=strict
  --property=ProtectHome=yes --property=PrivateTmp=yes --property=MemoryMax=1G
  --setenv="KUBECONFIG=$KUBECONFIG")
if ! systemctl is-active --quiet "$DASH"; then
  systemd-run --unit="$DASH" "${properties[@]}" \
    "$CLI" --config "$STATE/argocd-config" admin dashboard \
    --kubeconfig "$KUBECONFIG" --context vcloud-wsl-local --namespace platform-services \
    --address 127.0.0.1 --port 8080
fi
if ! systemctl is-active --quiet "$HTTP"; then
  systemd-run --unit="$HTTP" "${properties[@]}" \
    /usr/local/bin/k3s kubectl --kubeconfig "$KUBECONFIG" --context vcloud-wsl-local \
    -n platform-services port-forward --address 127.0.0.1 svc/vcloud-lab-server 18080:8080
fi
for ((attempt=0; attempt<45; attempt++)); do
  if curl --noproxy '*' --fail --silent --max-time 1 http://127.0.0.1:8080/api/version >/dev/null \
    && curl --noproxy '*' --fail --silent --max-time 1 http://127.0.0.1:18080/ >/dev/null; then
    status
    exit 0
  fi
  sleep 1
done
fail 'Access did not start. Inspect journalctl -u vcloud-wsl-argocd-dashboard -u vcloud-wsl-http-access.'
