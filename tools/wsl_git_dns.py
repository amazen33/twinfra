#!/usr/bin/env python3
"""Refresh GitHub-only DNS answers from WSL's host DNS tunnelling resolver.

The virtual 10.255.255.254 resolver works on the WSL host but is unreachable
from this Cilium Pod network. Publish only fresh public GitHub addresses to
the dedicated restricted CoreDNS ConfigMap; keep cluster DNS in-cluster.
"""
import argparse
import ipaddress
import json
from pathlib import Path
import socket
import subprocess

K = ['/usr/local/bin/k3s', 'kubectl', '--kubeconfig=/etc/vcloud-wsl/kubeconfig.yaml',
     '--context=vcloud-wsl-local', '--request-timeout=30s', '-n', 'platform-services']


def corefile(addresses):
    validated = sorted({str(ipaddress.ip_address(a)) for a in addresses})
    if not validated or any(not ipaddress.ip_address(a).is_global for a in validated):
        raise ValueError('Refusing missing or non-public GitHub DNS answers')
    records = ''.join(f'  {a} github.com\n' for a in validated)
    return ('github.com:1053 {\n hosts {\n' + records + '  ttl 30\n }\n errors\n}\n'
            'cluster.local:1053 {\n forward . 10.43.0.10\n cache 30\n errors\n}\n'
            '_grpclb._tcp.localhost:1053 {\n template ANY ANY {\n  rcode NXDOMAIN\n }\n cache 30\n errors\n}\n')


def refresh():
    if not Path('/var/lib/vcloud-wsl/owner.json').is_file():
        raise ValueError('Not the owned WSL lab')
    nodes=json.loads(subprocess.check_output(K+['get','nodes','-o','json']))['items']
    if len(nodes)!=1 or nodes[0]['metadata']['name']!='vcloud-wsl-local':raise ValueError('Unexpected target Node')
    addresses = [a[4][0] for a in socket.getaddrinfo('github.com', 443, type=socket.SOCK_STREAM)]
    current = json.loads(subprocess.check_output(K + ['get', 'configmap', 'vcloud-git-dns', '-o', 'json']))
    if current['data']['Corefile'] == corefile(addresses):
        print('PASS: GitHub-only DNS answers current')
        return
    patch = {'data': {'Corefile': corefile(addresses)}}
    subprocess.run(K + ['patch', 'configmap', 'vcloud-git-dns', '--type=merge', '-p', json.dumps(patch)], check=True)
    # The upstream Corefile has no reload plugin. Restart only this owned DNS
    # Deployment when records change, never the Argo applications/controllers.
    subprocess.run(K + ['rollout', 'restart', 'deployment/vcloud-git-dns'], check=True)
    subprocess.run(K + ['rollout', 'status', 'deployment/vcloud-git-dns', '--timeout=120s'], check=True)
    print('PASS: GitHub-only DNS answers refreshed')


if __name__ == '__main__':
    argparse.ArgumentParser(description=__doc__).parse_args()
    refresh()
