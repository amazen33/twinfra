#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Stage the dev application's locked images over OpenSSH. Never a runtime fallback."""
import hashlib
import json
import re
import shlex
import subprocess
import tarfile
import time
from pathlib import Path

from platform_resources import ROOT


def validate_archive(path, expected):
    """Validate the entire OCI graph before transferring/importing any bytes."""
    with tarfile.open(path) as archive:
        members = {}
        for member in archive:
            if not member.isfile() or member.name in members or not re.fullmatch(
                    r'oci-layout|index.json|blobs/sha256/[a-f0-9]{64}', member.name):
                raise ValueError('Unsafe/duplicate OCI archive member')
            members[member.name] = member
        def blob(desc):
            name = 'blobs/sha256/' + desc['digest'].removeprefix('sha256:')
            raw = archive.extractfile(members[name]).read()
            if len(raw) != desc['size'] or 'sha256:' + hashlib.sha256(raw).hexdigest() != desc['digest']:
                raise ValueError('OCI blob digest/size mismatch')
            return raw
        index = json.load(archive.extractfile(members['index.json']))
        if len(index['manifests']) != 1 or index['manifests'][0]['digest'] != expected:
            raise ValueError('Locally built OCI digest differs from image lock')
        desc = index['manifests'][0]
        manifest = json.loads(blob(desc))
        config = json.loads(blob(manifest['config']))
        if (config['os'], config['architecture']) != ('linux', 'amd64'):
            raise ValueError('Locally built image must be linux/amd64')
        for layer in manifest['layers']:
            blob(layer)
        reference = desc['annotations']['org.opencontainers.image.ref.name']
        if not re.fullmatch(r'registry\.(?:vcloud|twinfra)\.example\.com/[a-zA-Z0-9._/:@+-]+', reference):
            raise ValueError('Unapproved locally built image name')
        return reference


class SSH:
    def __init__(self, target, context):
        if context != 'twinfra-dev-cairo-1' or not re.fullmatch(r'[a-z_][a-z0-9_-]*@10\.50\.0\.10', target):
            raise ValueError('Use the explicit twinfra-dev-cairo-1 context and user@10.50.0.10')
        self.prefix = ['ssh', '-T', '-o', 'BatchMode=yes', '-o', 'StrictHostKeyChecking=yes',
                       '-o', 'ConnectTimeout=15', target]

    def run(self, command, payload=None, archive=None, accept_report=False):
        args = self.prefix + [shlex.join(command)]
        if archive:
            with archive.open('rb') as stream:
                result = subprocess.run(args, stdin=stream, capture_output=True, timeout=900)
        else:
            result = subprocess.run(args, input=payload, capture_output=True, timeout=900)
        if result.returncode and not (accept_report and result.returncode == 1):
            raise ValueError('SSH staging command failed; verify host key, VM connectivity and passwordless sudo')
        return result.stdout

    def agent(self, lock, check=False):
        code = (ROOT / 'deploy/common/stage-images.py').read_text()
        cmd = ['sudo', '-n', 'python3', '-c', code, '--stdin']
        if check:
            cmd.append('--check')
        raw = self.run(cmd, json.dumps(lock).encode(), accept_report=check)
        try:
            return json.loads(raw)
        except ValueError:
            raise ValueError('VM did not return a valid image-staging report') from None


def stage_applications(context, target, check=False, archive_dir=None, transport=None):
    ssh = transport or SSH(target, context)
    lock = json.loads((ROOT / 'deploy/common/images.lock.json').read_text())
    # Older lock entries use a tag only; the pull always uses the separately pinned digest.
    for item in lock['images'].values():
        item['source'] = item['source'].split('@')[0].rsplit(':', 1)[0] + '@' + item['digest']
    report = ssh.agent(lock, check=True)
    if check:
        return report
    if any(p['reason'] != 'missing' for p in report['problems']):
        raise ValueError('Staging refused: existing canonical image/CRI digest mismatch')
    missing = {p['name'] for p in report['problems']}
    directory = archive_dir or ROOT / '.build/dev-images'
    archives = {}
    for name, filename in [('console', 'console.oci.tar'), ('postgres', 'postgresql-pgvector.tar')]:
        if name not in missing:
            continue
        path = directory / filename
        if not path.is_file():
            raise ValueError('Missing OCI archive: ' + str(path) + '; build it with the existing repository generator')
        archives[name] = (path, validate_archive(path, lock['images'][name]['digest']))
    upstream = {name: item for name, item in lock['images'].items() if not item.get('buildReceipt')}
    ssh.agent({'images': upstream})
    for name, (path, imported) in archives.items():
        ssh.run(['sudo', '-n', 'ctr', '-n', 'k8s.io', 'images', 'import', '--local', '--platform', 'linux/amd64', '--digests', '-'], archive=path)
        # Verify the imported target before tagging, then verify canonical CRI identity below.
        lines = ssh.run(['sudo', '-n', 'ctr', '-n', 'k8s.io', 'images', 'list']).decode().splitlines()
        actual = {f[0]: f[2] for line in lines if len(f := line.split()) >= 3 and f[2].startswith('sha256:')}
        item = lock['images'][name]
        if actual.get(imported) != item['digest']:
            raise ValueError('Imported OCI digest mismatch: ' + name)
        ssh.run(['sudo', '-n', 'ctr', '-n', 'k8s.io', 'images', 'tag', imported, item['canonical']])
        ssh.run(['sudo', '-n', 'ctr', '-n', 'k8s.io', 'images', 'label', item['canonical'], 'io.cri-containerd.image=managed'])
    # CRI learns new managed image records asynchronously. Bound read-only retries;
    # --check above remains a single snapshot and never enters this staging path.
    for attempt in range(5):
        result = ssh.agent(lock, check=True)
        if not result['problems']:
            break
        if attempt != 4:
            time.sleep(0.5)
    if result['problems']:
        raise ValueError('Application image cache incomplete after staging')
    return result
