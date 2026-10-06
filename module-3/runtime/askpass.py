#!/usr/bin/env python3
"""Read a short-lived GitHub App token only for the fixed GitHub HTTPS credential request."""
import os
from pathlib import Path
import sys
import re

prompt = sys.argv[1]
if not re.fullmatch(r"(?:Username|Password) for 'https://(?:x-access-token@)?github\.com':\s*",prompt):
    raise SystemExit('Credential host rejected')
if prompt.startswith('Username'):
    print('x-access-token')
elif prompt.startswith('Password'):
    print((Path(os.environ['VCLOUD_GIT_SECRET_DIRECTORY']) / 'token').read_text().strip())
else:
    raise SystemExit('Credential prompt rejected')
