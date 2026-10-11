#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
# Dev-only post-bootstrap configuration; shared Module -1 stays unchanged.
set -Eeuo pipefail
[[ $EUID == 0 ]] || { echo 'Dev log caps require root' >&2; exit 1; }
config=/etc/twinfra-host.env
[[ -f $config && ! -L $config && $(stat -c %u "$config") == 0 ]] || exit 1
[[ $(stat -c %a "$config") =~ ^(600|644)$ ]] || exit 1
# Runtime root-owned configuration is unavailable during offline lint.
# shellcheck source=/dev/null
source "$config"
[[ ${PLATFORM_PROFILE:-} == dev-cairo-1 || ${PLATFORM_PROFILE:-} == dev-cairo-2 ]] || {
    echo 'Log caps are dev-only' >&2; exit 1;
}
python3 - <<'PY'
import os, re, stat, subprocess, tempfile
from pathlib import Path

def update(path, raw):
    path = Path(path)
    if path.is_symlink() or path.exists() and (path.stat().st_uid != 0 or path.stat().st_mode & 0o022):
        raise SystemExit('Unowned/insecure log-cap destination')
    if path.exists() and path.read_text() == raw:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as f:
        f.write(raw.encode()); name=f.name
    os.chmod(name, 0o644); os.replace(name, path)
    return True

config=Path('/var/lib/kubelet/config.yaml')
if not config.is_file() or config.is_symlink() or config.stat().st_uid != 0:
    raise SystemExit('Wait for the shared bootstrap to create kubelet configuration')
raw=config.read_text()
for key,value in [('containerLogMaxSize','10Mi'),('containerLogMaxFiles','3')]:
    pattern=r'(?m)^'+key+r':[^\n]*\n?'
    if len(re.findall(pattern,raw))>1:raise SystemExit('Ambiguous kubelet log configuration')
    raw=re.sub(pattern,key+': '+value+'\n',raw) if re.search(pattern,raw) else raw.rstrip()+'\n'+key+': '+value+'\n'
changed=update(config,raw)
journal=update('/etc/systemd/journald.conf.d/10-twinfra-dev.conf','[Journal]\nSystemMaxUse=500M\n')
marker=Path('/var/lib/twinfra/dev-log-caps.ready')
if marker.is_symlink():raise SystemExit('Unowned log-cap marker')
if journal or not marker.exists():subprocess.run(['systemctl','restart','systemd-journald'],check=True)
if changed:subprocess.run(['systemctl','try-restart','kubelet'],check=True)
if not marker.exists():update(marker,'WO-31 dev log caps\n')
print('PASS: dev log caps'+(' applied' if changed or journal else ' verified; no configuration changes'))
PY
