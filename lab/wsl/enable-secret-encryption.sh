#!/usr/bin/env bash
# Scoped to the owned single-server lab. Follow K3s' existing-cluster procedure;
# never print/export encryption keys, disable encryption, or force a rotation.
set -euo pipefail
umask 077
ACTION=${1:---check}
[[ $# -le 1 && $ACTION =~ ^--(check|enable)$ ]] || exit 2
[[ $EUID == 0 && $(uname -r) == *microsoft* && -f /var/lib/vcloud-wsl/owner.json ]] || exit 1
export KUBECONFIG=/etc/vcloud-wsl/kubeconfig.yaml
api=$(python3 - <<'PY'
import yaml
with open('/etc/vcloud-wsl/kubeconfig.yaml') as f:c=yaml.safe_load(f)
assert c['current-context']=='vcloud-wsl-local'
print(c['clusters'][0]['cluster']['server'])
PY
)
k() { /usr/local/bin/k3s kubectl --context vcloud-wsl-local --request-timeout=30s "$@"; }
encrypt() { /usr/local/bin/k3s secrets-encrypt "$@" --server "$api"; }
k get nodes -o json | jq -e '.items | length == 1 and .[0].metadata.name == "vcloud-wsl-local"' >/dev/null
status=$(encrypt status)
if grep -q 'Encryption Status: Enabled' <<<"$status"; then
  if ! grep -q 'All hashes match' <<<"$status" \
    || ! grep -Eq 'Current Rotation Stage: (start|reencrypt_finished)$' <<<"$status"; then
    printf 'FAIL: encryption hashes or rotation stage are not stable.\n' >&2
    exit 1
  fi
  printf 'PASS: Kubernetes Secret encryption at rest enabled.\n'
  exit 0
fi
[[ $ACTION == --enable ]] || { printf 'FAIL: Kubernetes Secret encryption at rest disabled.\n' >&2; exit 1; }
# Only adopt the documented initial state. Intermediate/unknown rotation states
# require operator recovery rather than automatically rotating again.
grep -q 'Disabled, no configuration file found' <<<"$status" || { printf 'FAIL: unexpected encryption state.\n' >&2; exit 1; }
encrypt enable
python3 - <<'PY'
from pathlib import Path
import yaml
p=Path('/etc/rancher/k3s/config.yaml')
c=yaml.safe_load(p.read_text())
assert c['node-name']=='vcloud-wsl-local' and c['container-runtime-endpoint']=='unix:///run/containerd/containerd.sock'
c['secrets-encryption']=True
p.write_text(yaml.safe_dump(c,sort_keys=False));p.chmod(0o600)
PY
ready() { for ((i=0;i<60;i++)); do if k get --raw=/readyz >/dev/null 2>&1; then return 0; fi; sleep 2; done; return 1; }
systemctl restart k3s
ready
status=$(encrypt status)
grep -q 'Current Rotation Stage: start' <<<"$status"
encrypt rotate-keys
for ((i=0;i<90;i++)); do
  status=$(encrypt status)
  if grep -q 'Current Rotation Stage: reencrypt_finished' <<<"$status"; then break; fi
  sleep 2
done
grep -q 'Current Rotation Stage: reencrypt_finished' <<<"$status"
systemctl restart k3s
ready
status=$(encrypt status)
grep -q 'Encryption Status: Enabled' <<<"$status"
grep -q 'All hashes match' <<<"$status"
printf 'PASS: K3s encryption enabled and existing API Secrets reencrypted.\n'
