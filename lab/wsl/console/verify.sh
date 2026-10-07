#!/usr/bin/env bash
# Public negative-auth check; never infer acceptance from a generic gateway 200.
set -euo pipefail
for tool in curl jq; do command -v "$tool" >/dev/null || { echo "Missing dependency: $tool" >&2; exit 1; }; done
tmp=$(mktemp -d)
trap 'rm -f -- "$tmp/headers" "$tmp/body"; rmdir -- "$tmp"' EXIT
for path in / /storage/ /dynamodb/ /ministack/_ministack/health /localstack/_localstack/health; do
  code=$(curl --silent --show-error --max-time 10 --resolve console.vcloud.local:18080:127.0.0.1 \
    -D "$tmp/headers" -o "$tmp/body" -w '%{http_code}' "http://console.vcloud.local:18080$path")
  [[ $code == 302 || $code == 401 ]] || { echo "FAIL: unauthenticated $path returned $code" >&2; exit 1; }
  if [[ $code == 302 ]]; then
    tr -d '\r' < "$tmp/headers" | grep -Eqi '^location: https://auth\.vcloud\.example\.com/realms/vcloud/protocol/openid-connect/auth\?' || {
      echo 'FAIL: unexpected OIDC redirect' >&2; exit 1;
    }
  fi
  echo "PASS: unauthorized $path -> HTTP $code"
done
echo 'Anonymous gate passed. Browser login, both backend views, refresh/logout and WebSocket acceptance remain required.'
