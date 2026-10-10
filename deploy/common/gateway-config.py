# SPDX-License-Identifier: MIT
"""APISIX init container: insert mounted credentials into memory-backed conf only."""
import copy
import json
from pathlib import Path
import shutil


def configure(source, auth, target, tls=None):
    data = json.loads((source / 'apisix.template.json').read_text())
    for route in data['routes']:
        oidc = route['plugins']['openid-connect']
        oidc['client_secret'] = (auth / 'client_secret').read_text().strip()
        oidc['session']['secret'] = (auth / 'session_secret').read_text().strip()
        if not oidc['client_secret'] or len(oidc['session']['secret']) < 32:
            raise ValueError('Missing OIDC credentials; gateway remains gated')
    if tls is not None:
        data['ssls'] = [{'id': 1, 'snis': sorted({r['host'] for r in data['routes']}),
                         'cert': (tls / 'tls.crt').read_text(), 'key': (tls / 'tls.key').read_text()}]
    # YAML accepts JSON; the APISIX standalone loader requires its EOF sentinel.
    config = target / 'apisix.yaml'
    config.write_text(json.dumps(data, indent=2) + '\n#END\n')
    config.chmod(0o600)
    shutil.copyfile(source / 'config.yaml', target / 'config.yaml')


if __name__ == '__main__':
    configure(Path('/source'), Path('/auth'), Path('/conf'), Path('/tls'))
