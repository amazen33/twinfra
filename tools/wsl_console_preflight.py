#!/usr/bin/env python3
"""Fail closed before an ADC full snapshot can contain incomplete OIDC config."""
import base64
import json
from pathlib import Path
import subprocess
import sys
from wsl_console import profile

K = ['/usr/local/bin/k3s', 'kubectl', '--kubeconfig=/etc/vcloud-wsl/kubeconfig.yaml',
     '--context=vcloud-wsl-local', '--request-timeout=15s', '-n', 'platform-services']


def validate_secret(obj):
    data = obj.get('data', {})
    # Pinned controller 2.2.0 inserts dotted Secret keys into nested plugin config.
    if set(data) != {'client_secret', 'session.secret'}:
        raise ValueError('OIDC Secret must contain only client_secret and session.secret')
    try:
        client = base64.b64decode(data['client_secret'], validate=True).decode()
        session = base64.b64decode(data['session.secret'], validate=True).decode()
    except (ValueError, UnicodeError):
        raise ValueError('OIDC Secret contains invalid encoding') from None
    if len(client.strip()) < 16 or len(session.strip()) < 32:
        raise ValueError('OIDC Secret values are missing or too short')
    # Do not return, print, store, put in argv/env or log these private values.


def get(args):
    result = subprocess.run(K + args, capture_output=True, check=False)
    if result.returncode:
        raise ValueError('Required Kubernetes object unavailable')
    return json.loads(result.stdout)


def main():
    if not Path('/var/lib/vcloud-wsl/owner.json').is_file():
        raise ValueError('Owned WSL lab required')
    nodes = get(['get', 'nodes', '-o', 'json'])['items']
    if len(nodes) != 1 or nodes[0]['metadata']['name'] != 'vcloud-wsl-local':
        raise ValueError('Console activation is limited to the single-node WSL lab')
    labels = get(['get', 'namespace', 'platform-services', '-o', 'json'])['metadata']['labels']
    if labels.get('pod-security.kubernetes.io/enforce') != 'restricted' or labels.get('pod-security.kubernetes.io/enforce-version') != 'v1.30':
        raise ValueError('restricted:v1.30 namespace required')
    secret = get(['get', 'secret', profile()['oidc']['secret'], '-o', 'json'])
    validate_secret(secret)
    for name in ('vcloud-console-shell', 'storage-ui', 'dynamodb-admin', 'ministack'):
        get(['get', 'service', name, '-o', 'json'])
        slices = get(['get', 'endpointslices', '-l', 'kubernetes.io/service-name=' + name, '-o', 'json'])
        if not any(e.get('conditions', {}).get('ready') is True for s in slices['items'] for e in s.get('endpoints', [])):
            raise ValueError('Backend has no ready endpoint: ' + name)
    print('PASS: OIDC Secret shape, restricted namespace and backend readiness')
    print('Required next gate: verified issuer discovery/trust and browser callback acceptance; see README.')


if __name__ == '__main__':
    try:
        main()
    except ValueError as error:
        print('Console activation gated: ' + str(error), file=sys.stderr)
        sys.exit(3)
