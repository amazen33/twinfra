#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Offline equality check: rendered dev bootstrap images versus its verified lock."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile

import yaml

from platform_resources import ROOT
from platform_dev import seed
from manifest_contract import podspec


def inventory(bash='bash', helm='helm', region='cairo-1'):
    row = next(r for r in yaml.safe_load((ROOT / 'vcloud-ssot.yaml').read_text())['addressPlan']
               if r['environment'] == 'dev' and r['region'] == region)
    data = yaml.safe_load(seed(row)['user-data'])
    raw = next(f['content'] for f in data['write_files'] if f['path'] == '/etc/twinfra-host.env')
    values = dict(line.split('=', 1) for line in raw.splitlines() if line and not line.startswith('#') and '=' in line)
    env = dict(os.environ, **values, VCLOUD_CONFIG_FILE='/nonexistent')
    def render(command):
        return subprocess.check_output([bash, '-c', 'source "$1"; load_config; ' + command, '_',
                (ROOT / '00-setup-ubuntu-host.sh').as_posix()], env=env, text=True, encoding='utf-8')
    kube = list(yaml.safe_load_all(render('render_kubeadm')))[1]
    lock = json.loads((ROOT / 'deploy/common/bootstrap-images.lock.json').read_text())
    if lock['versions'] != {'kubernetes': kube['kubernetesVersion'], 'cilium': values['CILIUM_VERSION']}:
        raise ValueError('Bootstrap version/lock drift')
    derivation = lock['kubeadmSource']
    source = (ROOT / derivation['path']).read_text().encode()
    if hashlib.sha256(source).hexdigest() != derivation['sha256']:
        raise ValueError('Pinned kubeadm constants source differs')
    text = source.decode()
    def constant(name):
        return re.search(r'\b' + name + r'\s*=\s*"([^"]+)"', text)[1]
    repository = kube['imageRepository']
    expected = {repository + '/' + n + ':' + kube['kubernetesVersion']
                for n in ('kube-apiserver', 'kube-controller-manager', 'kube-scheduler')}
    if not kube.get('proxy', {}).get('disabled', False):
        expected.add(repository + '/kube-proxy:' + kube['kubernetesVersion'])
    expected |= {repository + '/etcd:' + constant('DefaultEtcdVersion'),
                 repository + '/coredns:' + constant('CoreDNSVersion'),
                 repository + '/pause:' + constant('PauseVersion')}
    containerd = render('render_containerd 1.7.28')
    expected.add(re.search(r'sandbox_image = "([^"]+)"', containerd)[1])
    expected.add(values.get('REGISTRY_PROBE_IMAGE', values['IMAGE_REGISTRY'] + '/docker.io/library/busybox:1.37.0'))
    if values['RUN_SMOKE_TESTS'] == 'true':
        for obj in yaml.safe_load_all(render('render_smoke')):
            pod = podspec(obj) if obj else None
            if pod:
                expected |= {c['image'] for c in pod.get('containers', []) + pod.get('initContainers', [])}
    with tempfile.TemporaryDirectory() as directory:
        file = Path(directory) / 'values.yaml'
        file.write_text(render('render_cilium_values'), encoding='utf-8')
        chart = subprocess.check_output([helm, 'template', 'cilium', (ROOT / 'module-2/vendor/cilium-1.20.2.tgz').as_posix(),
                '--namespace', 'kube-system', '-f', str(file)], text=True, encoding='utf-8')
    for obj in yaml.safe_load_all(chart):
        pod = podspec(obj) if obj else None
        if pod:
            expected |= {c['image'] for c in pod.get('containers', []) + pod.get('initContainers', [])}
    actual = {e['canonical'] for e in lock['images'].values()}
    if expected != actual:
        raise ValueError('Bootstrap image set differs: missing=' + str(sorted(expected - actual)) + '; unexpected=' + str(sorted(actual - expected)))
    print('PASS: ' + region + ' bootstrap inventory; ' + str(len(actual)) + ' verified images; no kube-proxy or disabled smoke images')
    return expected


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bash', default='bash')
    parser.add_argument('--helm', default='helm')
    args = parser.parse_args()
    for region in ('cairo-1', 'cairo-2'):
        inventory(args.bash, args.helm, region)
