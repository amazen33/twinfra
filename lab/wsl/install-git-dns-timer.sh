#!/usr/bin/env bash
# Install only the owned lab's exact two units; preserve unrelated services.
set -euo pipefail
ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
[[ $EUID == 0 && $(uname -r) == *microsoft* && -f /var/lib/vcloud-wsl/owner.json ]] || exit 1
for name in vcloud-wsl-git-dns.service vcloud-wsl-git-dns.timer; do
  if [[ -e /etc/systemd/system/$name ]]; then
    grep -q 'Description=vCloud owned WSL GitHub-only DNS refresh' "/etc/systemd/system/$name" || { printf 'Refusing unowned unit replacement\n' >&2; exit 1; }
  fi
done
install -d -o root -g root -m 0755 /usr/local/lib/vcloud-wsl
install -o root -g root -m 0644 "$ROOT/tools/wsl_git_dns.py" /usr/local/lib/vcloud-wsl/wsl_git_dns.py
for name in vcloud-wsl-git-dns.service vcloud-wsl-git-dns.timer; do
  install -o root -g root -m 0644 "$ROOT/lab/wsl/$name" "/etc/systemd/system/$name"
done
systemctl daemon-reload
systemctl enable --now vcloud-wsl-git-dns.timer
systemctl start vcloud-wsl-git-dns.service
systemctl is-active vcloud-wsl-git-dns.timer
