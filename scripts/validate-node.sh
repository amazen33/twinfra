#!/usr/bin/env bash
# Read-only: DNS, verified HTTPS:443 and exact canonical CRI cache aliases.
# Default requires mirror AND cache. --cache-only is for an explicitly offline
# node with every required image already imported; it never allows missing images.
set -euo pipefail
ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
exec python3 "$ROOT/tools/node_registry.py" check "$@"
