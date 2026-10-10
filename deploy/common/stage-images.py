#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Owner/VM staging agent. Imports execute only under an explicit staging command."""
import argparse
import json
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path


def run(args):
    result = subprocess.run(args, capture_output=True, text=True, timeout=900)
    if result.returncode:
        # Never echo registry responses, environment or credentials into evidence.
        raise ValueError('Image command failed: ' + ' '.join(args[:5]))
    return result.stdout


def entries(lock):
    result = lock['images']
    if not isinstance(result, dict) or not result:
        raise ValueError('Empty image staging lock')
    for key, item in result.items():
        sha = item.get('digest', '')
        if not re.fullmatch(r'sha256:[a-f0-9]{64}', sha):
            raise ValueError('Invalid locked digest: ' + key)
        for field in ('source', 'canonical'):
            if not re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9._/:@+-]+', item.get(field, '')):
                raise ValueError('Invalid image reference: ' + key)
        if not item['source'].endswith('@' + sha):
            raise ValueError('Upstream reference must include the locked digest: ' + key)
        if not item['canonical'].startswith('registry.twinfra.example.com/'):
            raise ValueError('Only dev canonical names may be staged')
    return result


def cached(runner):
    result = {}
    for line in runner(['ctr', '-n', 'k8s.io', 'images', 'list']).splitlines():
        fields = line.split()
        if len(fields) >= 3 and fields[2].startswith('sha256:'):
            result[fields[0]] = fields[2]
    return result


def inspect_cri(item, runner):
    try:
        info = json.loads(runner(['crictl', 'inspecti', item['canonical']]))
    except (ValueError, json.JSONDecodeError):
        return False
    digests = info.get('status', {}).get('repoDigests', [])
    return any(value.endswith('@' + item['digest']) for value in digests)


def stage(lock, check=False, verify_cri=True, runner=run):
    images = entries(lock)
    state = cached(runner)
    problems = []
    for key, item in images.items():
        actual = state.get(item['canonical'])
        if actual is None:
            problems.append({'name': key, 'reason': 'missing', 'image': item['canonical']})
        elif actual != item['digest']:
            problems.append({'name': key, 'reason': 'digest mismatch', 'image': item['canonical']})
        elif verify_cri and not inspect_cri(item, runner):
            problems.append({'name': key, 'reason': 'CRI missing or digest mismatch', 'image': item['canonical']})
    if check:
        # No temporary directory, pull, import, tag, file or runtime writes.
        return problems
    if any(p['reason'] != 'missing' for p in problems):
        raise ValueError('Staging refused: ' + ', '.join(p['name'] + ': ' + p['reason'] for p in problems))
    missing = {p['name'] for p in problems}
    for key, item in images.items():
        if key not in missing:
            continue
        if item.get('buildReceipt'):
            raise ValueError('Missing locally built image: ' + key + '; import its verified OCI archive first')
        # Explicit local client + empty hosts directory bypass CRI mirror configuration
        # only for this owner-requested staging pull, never for kubelet/runtime pulls.
        with tempfile.TemporaryDirectory(prefix='twinfra-empty-hosts-') as hosts:
            runner(['ctr', '-n', 'k8s.io', 'images', 'pull', '--local', '--platform', 'linux/amd64',
                    '--hosts-dir', hosts, item['source']])
        state = cached(runner)
        if state.get(item['source']) != item['digest']:
            raise ValueError('Upstream digest mismatch after pull: ' + key)
        runner(['ctr', '-n', 'k8s.io', 'images', 'tag', item['source'], item['canonical']])
        runner(['ctr', '-n', 'k8s.io', 'images', 'label', item['canonical'], 'io.cri-containerd.image=managed'])
    state = cached(runner)
    for key, item in images.items():
        if state.get(item['canonical']) != item['digest']:
            raise ValueError('Missing or mismatched image after staging: ' + key)
        if verify_cri:
            # CRI consumes containerd image events asynchronously. Bounded reads
            # avoid a false failure immediately after a successful tag/import.
            for attempt in range(5):
                if inspect_cri(item, runner):
                    break
                if attempt == 4:
                    raise ValueError('CRI missing or digest mismatch after staging: ' + key)
                time.sleep(0.5)
    return []


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--lock', type=Path)
    parser.add_argument('--stdin', action='store_true')
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    if bool(args.lock) == args.stdin:
        parser.error('Choose --lock or --stdin')
    lock = json.load(sys.stdin) if args.stdin else json.loads(args.lock.read_text())
    problems = stage(lock, args.check)
    print(json.dumps({'status': 'failed' if problems else 'passed', 'images': len(lock['images']), 'problems': problems}))
    return int(bool(problems))


if __name__ == '__main__':
    try:
        sys.exit(main())
    except (ValueError, OSError, subprocess.TimeoutExpired) as error:
        print('Image staging failed: ' + str(error), file=sys.stderr)
        sys.exit(1)
