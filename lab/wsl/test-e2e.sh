#!/usr/bin/env bash
# Live, CPU-only acceptance. Missing dependencies are failures, never skips.
set -euo pipefail
umask 077
ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
[[ $EUID == 0 && $(uname -r) == *microsoft* && -f /var/lib/vcloud-wsl/owner.json ]] || exit 1
for command in jq curl kubectl python3 ip gpg; do command -v "$command" >/dev/null || { printf 'Missing dependency: %s\n' "$command" >&2; exit 1; }; done
bash "$ROOT/lab/wsl/enable-secret-encryption.sh" --check
bash "$ROOT/lab/wsl/endpoints/access.sh" start
exec python3 "$ROOT/tools/wsl_endpoint_acceptance.py"
