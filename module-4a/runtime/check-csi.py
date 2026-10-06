#!/usr/bin/env python3
"""Readiness checks file pairing/permissions, not a database authentication claim."""
from pathlib import Path
import json
import os
import re
import stat


def check(directory=Path('/run/vcloud-secrets')):
    database=directory/'database.json';api_key=directory/'api-key'
    for path in (database,api_key):
        mode=path.stat().st_mode
        if not stat.S_ISREG(mode) or mode & 0o007 or not os.access(path,os.R_OK):
            raise ValueError('Secret file type, access or permissions failed')
    obj=json.loads(database.read_text())
    if not re.fullmatch(r'vcloud_dyn_[A-Za-z0-9]{20}',obj['data']['username']) or not obj['data']['password']:
        raise ValueError('Invalid paired credentials')
    if not obj['lease_id'].startswith('database/creds/vcloud-app-readonly/') or obj['lease_duration']<=0:
        raise ValueError('Invalid application lease metadata')
    if not api_key.read_bytes().strip():raise ValueError('Missing static API key')
    return True


if __name__=='__main__':
    try:check()
    except Exception:raise SystemExit('CSI readiness failed; secret values redacted')
