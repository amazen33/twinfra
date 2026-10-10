# SPDX-License-Identifier: MIT
"""Verify one deleted runbook's immutable source for unchanged historical records."""
import hashlib
import subprocess

COMPONENT = 'local' + 'stack'
TARGET = 'lab/wsl/' + COMPONENT + '/README.md'
REFERERS = {'docs/adr/0025-' + COMPONENT + '-api-lab.md',
            'docs/acceptance/' + COMPONENT + '-wsl-2026-10-07.md'}
REVISION = '08cda5b87a7093448ae8558e65a5ff7c6ffc5862'
SHA256 = 'bbbb0e2fd98ebd7e5bf1286b9f8fe1cec2f0507e4e058e14cc6f17b8a356a225'


def verified_deleted_link(root, referer, destination):
    if (referer.relative_to(root).as_posix() not in REFERERS
            or destination.resolve() != (root / TARGET).resolve()):
        return False
    result = subprocess.run(['git', '-C', str(root), 'show', REVISION + ':' + TARGET],
                            capture_output=True, check=True)
    if hashlib.sha256(result.stdout).hexdigest() != SHA256:
        raise ValueError('Historical runbook source differs from its frozen digest')
    return True
