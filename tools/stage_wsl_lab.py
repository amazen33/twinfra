#!/usr/bin/env python3
"""Fetch hash-locked public bootstrap artifacts; never read cluster credentials."""
import argparse
import concurrent.futures
import hashlib
import json
from pathlib import Path
import tarfile
import urllib.request

ROOT = Path(__file__).resolve().parents[1]


def stage(cache, offline=False):
    cache.mkdir(parents=True, exist_ok=True)
    artifacts = json.loads((ROOT / 'lab/wsl/profile.json').read_text())['artifacts']
    tools = json.loads((ROOT / 'tools/ci/toolchain.lock.json').read_text())['artifacts']
    artifacts.update({name + '.tar.gz': tools[name] for name in ('helm', 'kubeconform')})

    def fetch(item):
        name, lock = item
        target = cache / name
        if not target.is_file() or hashlib.sha256(target.read_bytes()).hexdigest() != lock['sha256']:
            if offline:
                raise ValueError('Verified offline artifact missing: ' + name)
            temporary = cache / (name + '.part')
            with urllib.request.urlopen(lock['url'], timeout=60) as response, temporary.open('wb') as output:
                while chunk := response.read(1024**2):
                    output.write(chunk)
            if hashlib.sha256(temporary.read_bytes()).hexdigest() != lock['sha256']:
                raise ValueError('Artifact hash differs: ' + name)
            temporary.replace(target)
        if 'member' in lock:
            with tarfile.open(target, 'r:gz') as archive:
                member = archive.extractfile(lock['member'])
                if member is None:
                    raise ValueError('Expected binary absent: ' + name)
                binary = cache / name.removesuffix('.tar.gz')
                binary.write_bytes(member.read())
                binary.chmod(0o755)
        print(name + ': hash verified', flush=True)

    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        list(pool.map(fetch, artifacts.items()))
    (cache / 'k3s').chmod(0o755)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cache', type=Path, required=True)
    parser.add_argument('--offline', action='store_true')
    options = parser.parse_args()
    stage(options.cache, options.offline)
