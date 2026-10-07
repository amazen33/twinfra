"""Restricted init container: compose authenticated APISIX config on tmpfs."""
from pathlib import Path
import re
import shutil

key = Path('/admin/admin-key').read_text().strip()
if not re.fullmatch('[a-f0-9]{64}', key):
    raise SystemExit('Invalid mounted APISIX admin credential')
for filename in ('config.yaml', 'apisix.yaml'):
    # Projected ConfigMaps also contain directory symlinks; copy only known files.
    shutil.copyfile(Path('/config') / filename, Path('/conf') / filename)
target = Path('/conf/config.yaml')
text = target.read_text()
if text.count('__VCLOUD_ADMIN_KEY__') != 1:
    raise SystemExit('APISIX credential placeholder must occur exactly once')
target.write_text(text.replace('__VCLOUD_ADMIN_KEY__', key))
target.chmod(0o600)
