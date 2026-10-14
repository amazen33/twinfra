#!/usr/bin/env python3
"""Build a deterministic OCI application layer on the already vetted Python base.

Equivalent runtime payload to console/Dockerfile. No Docker daemon, socket,
privileged build Pod, root execution in the image, or host mount
is required. Execute after npm ci/test/build; input downloads require explicit opt-in.
"""
import argparse
import gzip
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import re
import stat
import subprocess
import sys
import tarfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
BASE = 'registry.twinfra.example.com/docker.io/library/python:3.14.8-slim-trixie@sha256:a2b82f3c48559aa0a8446d9af49826b6e2b2016f4cd2afabfe6013ec53729170'
TAG = 'registry.twinfra.example.com/docker.io/twinfra/twinfra-console:1.0.0'
RELEASE_EVIDENCE = {'softwareVersion': '3.14.8', 'softwareReleasedOn': '2026-09-30',
                    'officialDigestPublishedOn': '2026-10-09',
                    'ageBasis': 'upstream-software-release',
                    'decision': 'WO-34 Amendment 1'}
DEFAULT_BASE = ROOT / '.build/console/python-base.oci.tar'


def stage_frontend():
    """Verified source-bound build input; image code is never run."""
    lock = json.loads((ROOT / 'console/frontend.lock.json').read_text())
    archive = ROOT / 'console/frontend.tar.gz'
    if hashlib.sha256(archive.read_bytes()).hexdigest() != lock['archiveSHA256']:
        raise ValueError('Frontend archive checksum differs')
    for name, expected in lock['sourcesSHA256'].items():
        if hashlib.sha256((ROOT / name).read_bytes()).hexdigest() != expected:
            raise ValueError('Frontend source changed: ' + name)
    with tarfile.open(archive) as stream:
        files = {}
        for member in stream:
            path = PurePosixPath(member.name)
            if not member.isfile() or path.is_absolute() or '..' in path.parts or '\\' in member.name or member.name in files:
                raise ValueError('Unsafe frontend archive member')
            files[member.name] = stream.extractfile(member).read()
    if {name: hashlib.sha256(raw).hexdigest() for name, raw in files.items()} != lock['filesSHA256']:
        raise ValueError('Frontend archive content differs')
    dist = ROOT / 'console/dist'
    existing = {p.relative_to(dist).as_posix() for p in dist.rglob('*') if p.is_file()}
    for name in existing - files.keys():
        (dist / name).unlink()
    for name, raw in files.items():
        path = dist / name; path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(raw)


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
    # Verify local references without executing npm or any frontend code.
    for reference in re.findall(r'(?:src|href)="(/console/assets/[^"]+)"',
                                (dist / 'index.html').read_text(encoding='utf-8')):
        relative=PurePosixPath(reference.removeprefix('/console/'))
        if '..' in relative.parts or not (dist / relative).is_file():
            raise ValueError('Missing/unsafe built frontend asset')
    files = {'app/server.py': ROOT / 'console/server.py', 'app/aws_views.py': ROOT / 'console/aws_views.py',
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
        config.setdefault('history', []).append({'created': config['created'], 'created_by': 'twinfra-console deterministic application layer'})
        c = config['config']
        c.update(User='65532:65532', WorkingDir='/app', Entrypoint=['python', '-B', '/app/server.py'], Cmd=None,
                 ExposedPorts={'3000/tcp': {}}, Labels={'org.opencontainers.image.title': 'twinfra-console', 'org.opencontainers.image.version': '1.0.0'})
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
                               'console/server.py', 'console/aws_views.py', 'tools/build_console_image.py',
                               'tools/platform_oci.py')]
    inputs += sorted((ROOT / 'console/src').rglob('*'))
    inputs += [ROOT / 'console/index.html', ROOT / 'console/vite.config.ts', ROOT / 'console/tsconfig.json', ROOT / 'console/Dockerfile']
    receipt = {'base': BASE, 'tag': TAG, 'digest': result['digest'], 'canonical': TAG.split(':')[0] + '@' + result['digest'],
               'filesSHA256': {str(p.relative_to(ROOT)).replace('\\', '/'): hashlib.sha256(p.read_bytes()).hexdigest() for p in inputs if p.is_file()}}
    receipt['releaseEvidence'] = dict(RELEASE_EVIDENCE)
    return receipt


def download_inputs(base_path=DEFAULT_BASE, wheels=ROOT / '.build/console/wheels'):
    """Owner-requested download only; no installations, container runtime or npm."""
    from platform_oci import export_dockerhub
    export_dockerhub(BASE.removeprefix('registry.twinfra.example.com/'),base_path)
    wheels.mkdir(parents=True,exist_ok=True)
    subprocess.run([sys.executable,'-m','pip','download','--require-hashes','--only-binary=:all:',
        '--platform','manylinux_2_28_x86_64','--platform','manylinux2014_x86_64',
        '--platform','manylinux_2_17_x86_64','--implementation','cp','--python-version','3.14',
        '--abi','cp314','--abi','abi3','--abi','none','-r',str(ROOT/'console/requirements.txt'),
        '--dest',str(wheels)],check=True)
    dependencies(wheels)  # Refuse stale, additional or corrupt wheels as well.


def verify_receipt(receipt, refresh=False):
    """Amendment 9a: refresh tooling/names only AFTER reproducing the pinned image."""
    expected=json.loads((ROOT/'console/image.lock.json').read_text())
    images=json.loads((ROOT/'deploy/common/images.lock.json').read_text())['images']
    if receipt['digest']!=expected['digest'] or receipt['digest']!=images['console']['digest']:
        raise ValueError('Console digest did not reproduce: expected '+expected['digest']+'; built '+receipt['digest'])
    if receipt['canonical']!=images['console']['canonical'] or receipt['base']!=images['python']['canonical']:
        raise ValueError('Console receipt names differ from dev image lock')
    if refresh:
        tooling={'tools/build_console_image.py','tools/platform_oci.py'}
        old={k:v for k,v in expected['filesSHA256'].items() if k not in tooling}
        new={k:v for k,v in receipt['filesSHA256'].items() if k not in tooling}
        if old!=new:raise ValueError('Console source hashes changed; receipt refresh refused')
    elif receipt!=expected:
        raise ValueError('Console build receipt differs')
    return receipt


def verify_patch_refresh(receipt):
    """WO-34: permit a new base/metadata digest while preserving application bytes."""
    expected = json.loads((ROOT / 'console/image.lock.json').read_text())
    allowed = {'tools/build_console_image.py', 'tools/platform_oci.py', 'console/Dockerfile'}
    old = {k: v for k, v in expected['filesSHA256'].items() if k not in allowed}
    new = {k: v for k, v in receipt['filesSHA256'].items() if k not in allowed}
    if old != new:
        raise ValueError('Console patch refresh changed application sources')
    before = re.search(r'python:(\d+)\.(\d+)\.(\d+)-slim-trixie@', expected['base'])
    after = re.search(r'python:(\d+)\.(\d+)\.(\d+)-slim-trixie@', receipt['base'])
    if not before or not after or before.groups()[:2] != after.groups()[:2] or int(after[3]) < int(before[3]):
        raise ValueError('Console refresh must remain on the same Python minor')
    if receipt['base'] != BASE or receipt['tag'] != TAG:
        raise ValueError('Console patch refresh differs from the reviewed builder pins')
    return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base', type=Path, default=DEFAULT_BASE)
    parser.add_argument('--output', type=Path, default=ROOT / '.build/dev-images/console.oci.tar')
    parser.add_argument('--wheels', type=Path, default=ROOT / '.build/console/wheels')
    parser.add_argument('--download-inputs', action='store_true', help='Owner-only public pinned input download')
    parser.add_argument('--check', action='store_true', help='Check the receipt; never rewrite it (default)')
    parser.add_argument('--stage-frontend', action='store_true', help='Use the source/hash-verified frontend input archive')
    parser.add_argument('--refresh-receipt', action='store_true', help='Approved tooling/name metadata refresh only after exact digest reproduction')
    args = parser.parse_args()
    if args.check and args.refresh_receipt:parser.error('--check and --refresh-receipt are mutually exclusive')
    if args.download_inputs:download_inputs(args.base,args.wheels)
    if args.stage_frontend:stage_frontend()
    lock = verify_receipt(build(args.base, args.output, args.wheels),refresh=args.refresh_receipt)
    from platform_image_staging import validate_archive
    validate_archive(args.output,lock['digest'])
    if args.refresh_receipt:
        (ROOT / 'console/image.lock.json').write_text(json.dumps(lock, indent=2) + '\n',encoding='utf-8',newline='\n')
    print('PASS: deterministic OCI image ' + lock['canonical'])
    return 0


if __name__ == '__main__':raise SystemExit(main())
