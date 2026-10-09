#!/usr/bin/env python3
"""Build a deterministic OCI application layer on the already vetted Python base.

Equivalent runtime payload to console/Dockerfile. No Docker daemon, socket,
privileged build Pod, root execution in the image, or host mount
is required. Execute after npm ci/test/build. --import is owned-WSL-only.
"""
import argparse
import copy
import gzip
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import subprocess
import tarfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
BASE = 'registry.vcloud.example.com/docker.io/library/python:3.14.1-slim-trixie@sha256:b823ded4377ebb5ff1af5926702df2284e53cecbc6e3549e93a19d8632a1897e'
TAG = 'registry.vcloud.example.com/vcloud/vcloud-console:1.0.0'


def encoded(value): return json.dumps(value, sort_keys=True, separators=(',', ':')).encode()
def digest(raw): return 'sha256:' + hashlib.sha256(raw).hexdigest()
def descriptor(raw, kind): return {'mediaType': kind, 'digest': digest(raw), 'size': len(raw)}


def dependencies(wheels):
    """Unpack exactly the hash-locked Linux wheels, retaining dist-info licences.

    No wheel code, installer hooks, or .pth files execute during this build.
    Filenames/versions/tags and archive paths are checked before composition.
    """
    expected = {}
    for line in (ROOT / 'console/requirements.txt').read_text().splitlines():
        if not line or line.startswith('#'): continue
        match = re.fullmatch(r'([\w.-]+)==([^ ]+)((?: --hash=sha256:[a-f0-9]{64})+)', line)
        if not match: raise ValueError('Invalid console dependency lock')
        expected[match[1].lower().replace('-', '_')] = (match[2], re.findall(r'sha256:([a-f0-9]{64})', line))
    files, seen = {}, set()
    for wheel in sorted(wheels.glob('*.whl')):
        name, version, python, abi, platform = wheel.name.removesuffix('.whl').split('-')
        if name not in expected or name in seen or version != expected[name][0]: raise ValueError('Unexpected wheel')
        if hashlib.sha256(wheel.read_bytes()).hexdigest() not in expected[name][1]: raise ValueError('Wheel hash differs')
        if not ((python, abi, platform) == ('py3', 'none', 'any') or
                python in ('cp311', 'cp314') and abi in ('abi3', 'cp314') and
                all(tag.startswith('manylinux') and tag.endswith('_x86_64') for tag in platform.split('.'))):
            raise ValueError('Linux amd64 / CPython 3.14 wheel required')
        seen.add(name)
        with zipfile.ZipFile(wheel) as archive:
            for item in archive.infolist():
                if item.is_dir(): continue
                path = PurePosixPath(item.filename)
                if (path.is_absolute() or '..' in path.parts or '\\' in item.filename
                        or stat.S_ISLNK(item.external_attr >> 16) or path.suffix == '.pth'
                        or '.data' in path.parts[0]):
                    raise ValueError('Unsafe or unsupported wheel member')
                target = 'app/vendor/' + str(path)
                if target in files: raise ValueError('Duplicate wheel member')
                files[target] = archive.read(item)
    if seen != set(expected): raise ValueError('Missing locked console wheels')
    return files


def payload(wheels):
    dist = ROOT / 'console/dist'
    if not (dist / 'index.html').is_file(): raise ValueError('Run npm ci/test/build in console first')
    files = {'app/server.py': ROOT / 'console/server.py', 'app/aws_views.py': ROOT / 'lab/wsl/console/ui.py',
             'app/requirements.txt': ROOT / 'console/requirements.txt'}
    files.update({'app/public/' + str(p.relative_to(dist)).replace('\\', '/'): p for p in dist.rglob('*') if p.is_file()})
    if any(p.is_symlink() for p in files.values()): raise ValueError('Symlinks forbidden in application layer')
    files = {name: path.read_bytes() for name, path in files.items()}
    files.update(dependencies(wheels))
    return files


def build(base_path, target, wheels=ROOT / '.build/console/wheels'):
    with tarfile.open(base_path) as archive:
        members = {m.name: m for m in archive.getmembers() if m.isfile() and m.name.startswith('blobs/sha256/')}
        def blob(desc):
            name = 'blobs/sha256/' + desc['digest'].split(':', 1)[1]
            raw = archive.extractfile(members[name]).read()
            if digest(raw) != desc['digest'] or len(raw) != desc['size']: raise ValueError('OCI blob differs')
            return raw
        index = json.load(archive.extractfile('index.json'))
        def manifest(desc):
            value = json.loads(blob(desc))
            if 'manifests' not in value: return value
            choices = [d for d in value['manifests'] if d.get('platform', {}).get('os') == 'linux' and d.get('platform', {}).get('architecture') == 'amd64']
            if len(choices) != 1: raise ValueError('Single linux/amd64 base required')
            return manifest(choices[0])
        roots = index['manifests']
        if len(roots) != 1 or roots[0]['digest'] != BASE.split('@')[1]: raise ValueError('Unvetted base digest')
        base_manifest = manifest(roots[0])
        config = json.loads(blob(base_manifest['config']))
        if config['os'] != 'linux' or config['architecture'] != 'amd64': raise ValueError('Wrong base architecture')
        application = io.BytesIO()
        files = payload(wheels)
        with tarfile.open(fileobj=application, mode='w', format=tarfile.USTAR_FORMAT) as layer:
            for name, raw in sorted(files.items()):
                item = tarfile.TarInfo(name); item.size = len(raw); item.mode = 0o444
                item.uid = item.gid = 65532; item.mtime = 0
                layer.addfile(item, io.BytesIO(raw))
        plain = application.getvalue()
        compressed = gzip.compress(plain, mtime=0)
        layer_desc = descriptor(compressed, 'application/vnd.oci.image.layer.v1.tar+gzip')
        config['rootfs']['diff_ids'].append(digest(plain))
        config['created'] = '2026-10-08T00:00:00Z'
        config.setdefault('history', []).append({'created': config['created'], 'created_by': 'vcloud-console deterministic application layer'})
        c = config['config']
        c.update(User='65532:65532', WorkingDir='/app', Entrypoint=['python', '-B', '/app/server.py'], Cmd=None,
                 ExposedPorts={'3000/tcp': {}}, Labels={'org.opencontainers.image.title': 'vcloud-console', 'org.opencontainers.image.version': '1.0.0'})
        c['Env'] = [e for e in c.get('Env', []) if e.split('=')[0] not in ('PORT', 'PYTHONDONTWRITEBYTECODE', 'PYTHONUNBUFFERED', 'PYTHONPATH')]
        c['Env'] += ['PORT=3000', 'PYTHONDONTWRITEBYTECODE=1', 'PYTHONUNBUFFERED=1', 'PYTHONPATH=/app/vendor']
        cfg = encoded(config); cfg_desc = descriptor(cfg, 'application/vnd.oci.image.config.v1+json')
        output = {'schemaVersion': 2, 'mediaType': 'application/vnd.oci.image.manifest.v1+json',
                  'config': cfg_desc, 'layers': base_manifest['layers'] + [layer_desc]}
        raw_manifest = encoded(output); result = descriptor(raw_manifest, output['mediaType'])
        result.update(annotations={'org.opencontainers.image.ref.name': TAG}, platform={'os': 'linux', 'architecture': 'amd64'})
        target.parent.mkdir(parents=True, exist_ok=True)
        with tarfile.open(target, 'w') as out:
            def add(name, raw):
                item = tarfile.TarInfo(name); item.size = len(raw); item.mode = 0o644; item.mtime = 0
                out.addfile(item, io.BytesIO(raw))
            for name, member in sorted(members.items()): add(name, archive.extractfile(member).read())
            for raw in (compressed, cfg, raw_manifest): add('blobs/sha256/' + hashlib.sha256(raw).hexdigest(), raw)
            add('oci-layout', encoded({'imageLayoutVersion': '1.0.0'}))
            add('index.json', encoded({'schemaVersion': 2, 'manifests': [result]}))
    inputs = [ROOT / p for p in ('console/package.json', 'console/package-lock.json', 'console/requirements.txt',
                               'console/server.py', 'lab/wsl/console/ui.py', 'tools/build_console_image.py')]
    inputs += sorted((ROOT / 'console/src').rglob('*'))
    inputs += [ROOT / 'console/index.html', ROOT / 'console/vite.config.ts', ROOT / 'console/tsconfig.json', ROOT / 'console/Dockerfile']
    receipt = {'base': BASE, 'tag': TAG, 'digest': result['digest'], 'canonical': TAG.split(':')[0] + '@' + result['digest'],
               'filesSHA256': {str(p.relative_to(ROOT)).replace('\\', '/'): hashlib.sha256(p.read_bytes()).hexdigest() for p in inputs if p.is_file()}}
    return receipt


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base', type=Path, default=Path('/tmp/vcloud-console-python-base.oci.tar'))
    parser.add_argument('--output', type=Path, default=Path('/tmp/vcloud-console.oci.tar'))
    parser.add_argument('--wheels', type=Path, default=ROOT / '.build/console/wheels')
    parser.add_argument('--import', dest='import_image', action='store_true')
    args = parser.parse_args()
    if args.import_image:
        if os.geteuid() != 0 or 'microsoft' not in os.uname().release or not Path('/var/lib/vcloud-wsl/owner.json').is_file():
            raise SystemExit('Owned root WSL lab required')
        args.base.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(['ctr', '-n', 'k8s.io', 'images', 'export', '--platform', 'linux/amd64', str(args.base), BASE], check=True, stdout=subprocess.DEVNULL)
    lock = build(args.base, args.output, args.wheels)
    if args.import_image:
        subprocess.run(['ctr', '-n', 'k8s.io', 'images', 'import', '--digests', '--platform', 'linux/amd64', str(args.output)], check=True, stdout=subprocess.DEVNULL)
        subprocess.run(['ctr', '-n', 'k8s.io', 'images', 'tag', '--force', TAG, lock['canonical']], check=True, stdout=subprocess.DEVNULL)
    (ROOT / 'console/image.lock.json').write_text(json.dumps(lock, indent=2) + '\n')
    print('PASS: deterministic OCI image ' + lock['canonical'])
