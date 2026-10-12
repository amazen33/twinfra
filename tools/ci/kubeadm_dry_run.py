#!/usr/bin/env python3
"""Real kubeadm manifest preview on a disposable Ubuntu CI runner only.

No kubelet, CRI, image pull, cluster initialization or host provisioner is run.
Sudo generates manifests with --dry-run, then returns only those four public
Pod YAML files to the runner user for assertion and artifact upload.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shlex
import subprocess
import urllib.request

VERSION = 'v1.36.5'
URL = 'https://dl.k8s.io/release/' + VERSION + '/bin/linux/amd64/kubeadm'
SHA256 = 'be2f2c73cd6d3414b37aafb05016bc3a1da3e17c8393aa75c34636198fefa77c'
MANIFESTS = ('kube-apiserver.yaml', 'kube-controller-manager.yaml', 'kube-scheduler.yaml', 'etcd.yaml')


def verify_binary(binary, published):
    if published.decode('ascii').strip() != SHA256:
        raise ValueError('Published kubeadm SHA256 differs from the reviewed pin')
    if hashlib.sha256(binary.read_bytes()).hexdigest() != SHA256:
        raise ValueError('kubeadm binary SHA256 mismatch')


def phase_commands(binary, config, preview):
    return [['sudo', '-n', 'env', 'KUBEADM_INIT_DRYRUN_DIR=' + str(preview),
             str(binary), 'init', 'phase', *phase, '--config', str(config), '--dry-run']
            for phase in [('control-plane', 'all'), ('etcd', 'local')]]


def artifact_owner_command(preview, uid, gid):
    # kubeadm writes mode 0600 as root. Never recurse, change host paths, or
    # expose generated credentials: these are exactly four static Pod manifests.
    return ['sudo', '-n', 'chown', str(uid) + ':' + str(gid),
            *[str(preview / name) for name in MANIFESTS]]


def execute(command, log, *, env=None):
    result = subprocess.run(command, env=env, text=True, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, timeout=180)
    log.write_text(result.stdout, encoding='utf-8')
    if result.returncode:
        raise RuntimeError('Command failed: ' + shlex.join(command) + '\n' + result.stdout[-8000:])
    return result.stdout.strip()


def run(source, assets, report):
    source, assets, report = (p.resolve() for p in (source, assets, report))
    report.mkdir(parents=True, exist_ok=True)
    summary = dict(status='failed', scope='real kubeadm manifest dry-run; no live acceptance',
                   version=VERSION, sha256=SHA256, profiles=[])
    try:
        binary = assets / 'bin/kubeadm'
        with urllib.request.urlopen(URL + '.sha256', timeout=60) as response:
            verify_binary(binary, response.read(1024))
        if execute([str(binary), 'version', '-o', 'short'], report / 'version.log') != VERSION:
            raise ValueError('Unexpected kubeadm version')
        env = dict(os.environ, PATH=str(assets / 'bin') + os.pathsep + os.environ['PATH'])
        script = shlex.quote(str(source / '00-setup-ubuntu-host.sh'))
        for name in ('dev-cairo-1', 'production'):
            directory = report / name
            directory.mkdir(exist_ok=True)
            preview = directory / 'preview'
            preview.mkdir(exist_ok=True)
            config = directory / 'kubeadm.yaml'
            profile = ('source ' + shlex.quote(str(source / 'deploy/environments/dev/cairo-1/host.env'))
                       if name == 'dev-cairo-1' else 'NODE_IP=192.168.50.10; NODE_NAME=ci-production')
            prefix = ('set -Eeuo pipefail; source ' + script + '; '
                      'VCLOUD_CONFIG_FILE=/nonexistent-ci-config; load_config; ' + profile + '; '
                      'STATE_DIR=' + shlex.quote(str(directory)) + '; ')
            render = (prefix + 'mkdir -p "$STATE_DIR/kubeadm-patches"; '
                      'render_kubeadm > "$STATE_DIR/kubeadm.yaml"; '
                      'render_etcd_patch "$STATE_DIR/kubeadm.yaml" > "$STATE_DIR/kubeadm-patches/etcd+strategic.yaml"')
            execute(['bash', '-c', render], directory / 'render.log', env=env)
            for index, command in enumerate(phase_commands(binary, config, preview)):
                execute(command, directory / ('phase-' + str(index) + '.log'))
            if {p.name for p in preview.iterdir()} != set(MANIFESTS):
                raise ValueError('Dry-run did not produce exactly four static Pod manifests')
            if any(p.is_symlink() or not p.is_file() for p in preview.iterdir()):
                raise ValueError('Dry-run manifests must be regular files, not links')
            execute(artifact_owner_command(preview, os.getuid(), os.getgid()), directory / 'artifact-owner.log')
            execute(['bash', '-c', prefix + 'validate_etcd_cert_mount ' + shlex.quote(str(preview))],
                    directory / 'assert-etcd.log', env=env)
            summary['profiles'].append(dict(name=name, status='passed', phases=2, etcdMount='read-only; unique; config-derived'))
            print(name + ': real kubeadm control-plane/etcd dry-run and etcd mount assertion passed', flush=True)
        summary['status'] = 'passed'
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
        summary['error'] = str(error)
        print(str(error), flush=True)
    finally:
        (report / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n', encoding='utf-8')
    return int(summary['status'] != 'passed')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--assets', type=Path, required=True)
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    raise SystemExit(run(args.source, args.assets, args.report))
