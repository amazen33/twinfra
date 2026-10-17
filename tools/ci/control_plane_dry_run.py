#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Isolated WO-40c renderer proof; no cluster or host provisioning."""
import argparse
import copy
import json
import os
from pathlib import Path
import sys
import urllib.request

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
from kubeadm_dry_run import execute, verify_binary, URL, VERSION

CONTROL_ROOT = Path(__file__).resolve().parents[2]

def maintenance_preview(source, binary, config, directory):
    """Prove image-only etcd re-render with the pinned binary, without a cluster."""
    helper = source / 'tools/control_plane_candidate.py'
    if not helper.is_file():
        raise ValueError('Missing maintenance candidate helper')
    import importlib.util
    spec = importlib.util.spec_from_file_location('maintenance_candidate', helper)
    guard = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(guard)
    work = directory / 'maintenance'
    work.mkdir()
    base = list(yaml.safe_load_all(config.read_text()))
    patches = base[0]['patches']['directory']
    base[0]['patches']['directory'] = '/var/lib/vcloud-host/kubeadm-patches'
    cluster = next(doc for doc in base if doc['kind'] == 'ClusterConfiguration')
    guard.set_tag(cluster, 'etcd', '3.6.8-0')
    guard.set_tag(cluster, 'coredns', 'v1.14.2')
    lock = json.loads((source / 'deploy/common/bootstrap-images.lock.json').read_text())
    candidate, _ = guard.candidate(base, cluster, lock)
    objects = []
    for name, docs in [('before', base), ('after', candidate)]:
        preview = work / name
        preview.mkdir()
        cfg = work / (name + '.yaml')
        # Redirect only the private patch path in these disposable CI inputs.
        # kubeadm forbids mixing --config and --patches; the host uses its
        # unchanged original InitConfiguration path, as documented.
        isolated = copy.deepcopy(docs)
        isolated[0]['patches']['directory'] = patches
        cfg.write_text(yaml.safe_dump_all(isolated))
        command = ['sudo', '-n', 'env', 'KUBEADM_INIT_DRYRUN_DIR=' + str(preview),
                   str(binary), 'init', 'phase', 'etcd', 'local', '--config', str(cfg),
                   '--dry-run']
        execute(command, work / (name + '.log'))
        execute(['sudo', '-n', 'chown', str(os.getuid()) + ':' + str(os.getgid()),
                 str(preview / 'etcd.yaml')], work / (name + '-owner.log'))
        objects.append(yaml.safe_load((preview / 'etcd.yaml').read_text()))
    guard.verify_etcd(*objects, guard.image(lock, 'etcd'))
    for phase in [('etcd', 'local'), ('addon', 'coredns')]:
        output = execute([str(binary), 'init', 'phase', *phase, '--help'],
                         work / ('-'.join(phase) + '-help.log'))
        if '--config' not in output or '--dry-run' not in output:
            raise ValueError('Required maintenance phase flags unavailable')
    (work / 'summary.json').write_text(json.dumps({'status': 'passed',
        'scope': 'isolated renderer comparison, not Dell acceptance',
        'etcdDiff': 'image only', 'flags': 'both phases accept config/dry-run'}) + '\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('source', 'assets', 'config', 'out'):
        parser.add_argument('--' + name, required=True, type=Path)
    args = parser.parse_args()
    binary = args.assets.resolve() / 'bin/kubeadm'
    with urllib.request.urlopen(URL + '.sha256', timeout=60) as response:
        verify_binary(binary, response.read(1024))
    report_root = CONTROL_ROOT / '.build/ci-report'
    output, config = args.out.resolve(), args.config.resolve()
    if not output.is_relative_to(report_root) or not config.is_relative_to(report_root):
        raise ValueError('Maintenance preview paths must stay in the CI report directory')
    output.mkdir(parents=True, exist_ok=True)
    if execute([str(binary), 'version', '-o', 'short'], output / 'version.log') != VERSION:
        raise ValueError('Unexpected maintenance preview kubeadm version')
    maintenance_preview(args.source.resolve(), binary, config, output)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
