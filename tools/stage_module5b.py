#!/usr/bin/env python3
"""Verify offline wheels; --download explicitly stages public hash-locked artifacts."""
import argparse
import hashlib
import json
from pathlib import Path
import urllib.request
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]


def verified(raw, digest):
    if hashlib.sha256(raw).hexdigest() != digest: raise ValueError('Wheel checksum mismatch')
    return raw


def main():
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument('--download', action='store_true'); args = parser.parse_args()
    lock = json.loads((ROOT / 'module-5b/python-wheels.lock.json').read_text())
    target = ROOT / '.build/module-5b/wheels'; target.mkdir(parents=True, exist_ok=True)
    for entry in lock['packages']:
        filename = entry['filename']; endpoint = urlsplit(entry['url'])
        if Path(filename).name != filename or not filename.endswith('-none-any.whl') or endpoint.scheme != 'https' or endpoint.hostname != 'files.pythonhosted.org':
            raise ValueError('Unexpected wheel source or filename')
        path = target / filename
        if not path.is_file():
            if not args.download: raise ValueError('Missing offline wheel: ' + filename + '; run the explicit staging target in a connected environment')
            with urllib.request.urlopen(entry['url'], timeout=30) as response: raw = response.read(32 * 1024 * 1024)
            path.write_bytes(verified(raw, entry['sha256']))
        verified(path.read_bytes(), entry['sha256'])
    if {p.name for p in target.iterdir()} != {p['filename'] for p in lock['packages']}:
        raise ValueError('Unexpected wheel in offline build directory')
    print('Verified ' + str(len(lock['packages'])) + ' pinned offline wheels')


if __name__ == '__main__': main()
