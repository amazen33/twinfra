#!/usr/bin/env python3
"""Linux CI tool staging: fixed URLs, verified bytes, and explicit archive members.

Nothing is extracted wholesale or installed on the host. A checksum failure is
fatal; mutable upstream URLs never silently advance the selected dependency.
"""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import shlex
import tarfile
import urllib.request

ROOT = Path(__file__).resolve().parent


def verified(data, digest):
    if hashlib.sha256(data).hexdigest() != digest:
        raise ValueError('Downloaded artifact SHA256 mismatch')
    return data


def extract_member(archive, member):
    path = PurePosixPath(member)
    if path.is_absolute() or '..' in path.parts:
        raise ValueError('Unsafe archive member path')
    with tarfile.open(archive, 'r:*') as stream:
        info = stream.getmember(member)
        if not info.isfile() or info.issym() or info.islnk():
            raise ValueError('Only a regular archive file may be staged')
        return stream.extractfile(info).read()


def stage(destination):
    destination.mkdir(parents=True, exist_ok=True)
    lock = json.loads((ROOT / 'toolchain.lock.json').read_text())
    for name, artifact in lock['artifacts'].items():
        relative = PurePosixPath(artifact['output'])
        if relative.is_absolute() or '..' in relative.parts:
            raise ValueError('Unsafe artifact output path')
        cache = destination / 'downloads' / name
        cache.parent.mkdir(parents=True, exist_ok=True)
        if cache.exists():
            data = verified(cache.read_bytes(), artifact['sha256'])
        else:
            with urllib.request.urlopen(artifact['url'], timeout=120) as response:
                data = verified(response.read(), artifact['sha256'])
            cache.write_bytes(data)
        output = destination / relative
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(extract_member(cache, artifact['member']) if artifact.get('member') else data)
        if relative.parts[0] == 'bin':
            output.chmod(0o755)
        print('Verified ' + name, flush=True)


def wrapper(destination, source):
    # The bootstrap's embedded post-renderer requests default schemas. Prepend
    # local strict schemas so the tests exercise it without schema network calls.
    templates = [destination / 'schemas' / '{{.ResourceKind}}.json',
                 source / 'module-2/schemas' / '{{.Group}}/{{.ResourceKind}}_{{.ResourceAPIVersion}}.json',
                 source / 'module-2/schemas' / '{{.ResourceKind}}_{{.ResourceAPIVersion}}.json']
    # Module 2's actual schema locations are included explicitly by its validator.
    flags = ' '.join('-schema-location ' + shlex.quote(str(path)) for path in templates)
    script = '#!/usr/bin/env bash\nset -Eeuo pipefail\nexec ' + shlex.quote(str(destination / 'bin/kubeconform-real')) + ' ' + flags + ' "$@"\n'
    target = destination / 'bin/kubeconform'
    target.write_text(script, encoding='utf-8', newline='\n')
    target.chmod(0o755)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--destination', type=Path, required=True)
    parser.add_argument('--source', type=Path, required=True)
    args = parser.parse_args()
    stage(args.destination.resolve())
    wrapper(args.destination.resolve(), args.source.resolve())
