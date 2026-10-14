#!/usr/bin/env python3
"""Build the checksum-locked, BSD govulncheck tool without a global install.

Discovery produces a binary checksum only. It never executes govulncheck;
analysis requires that checksum to be committed in the reviewed tool lock.
"""
import argparse
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import platform
import re
import subprocess
import tarfile
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[2]


def verified(raw, expected):
    if not isinstance(expected, str) or not re.fullmatch(r'[a-f0-9]{64}', expected) or hashlib.sha256(raw).hexdigest() != expected:
        raise ValueError('Go build input checksum mismatch')
    return raw


def download(item, cache):
    if not item['url'].startswith('https://'):
        raise ValueError('HTTPS build input required')
    cache.parent.mkdir(parents=True, exist_ok=True)
    if cache.exists():
        return verified(cache.read_bytes(), item['sha256'])
    with urllib.request.urlopen(item['url'], timeout=120) as response:
        raw = verified(response.read(), item['sha256'])
    cache.write_bytes(raw)
    return raw


def safe_target(root, name):
    path = PurePosixPath(name)
    if path.is_absolute() or '..' in path.parts or '\\' in name or ':' in name:
        raise ValueError('Unsafe Go build archive path')
    target = (root / Path(*path.parts)).resolve()
    if not target.is_relative_to(root.resolve()):
        raise ValueError('Go archive escapes build directory')
    return target


def extract_sdk(raw, root, windows):
    total = 0
    if windows:
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            for item in archive.infolist():
                target = safe_target(root, item.filename)
                if item.is_dir():
                    continue
                if (item.external_attr >> 16) & 0o170000 == 0o120000:
                    raise ValueError('Go SDK symlinks forbidden')
                total += item.file_size
                if total > 1024**3:
                    raise ValueError('Go SDK exceeds bounds')
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(archive.read(item))
    else:
        with tarfile.open(fileobj=io.BytesIO(raw), mode='r:*') as archive:
            for item in archive:
                target = safe_target(root, item.name)
                if item.isdir():
                    continue
                if not item.isfile() or item.issym() or item.islnk():
                    raise ValueError('Go SDK regular files required')
                total += item.size
                if total > 1024**3:
                    raise ValueError('Go SDK exceeds bounds')
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(archive.extractfile(item).read())
                target.chmod(item.mode & 0o777)


def stage(destination, discover=False, root=ROOT):
    lock = json.loads((root / 'tools/ci/toolchain.lock.json').read_text())['builds']['govulncheck']
    if lock['module'] != 'golang.org/x/vuln/cmd/govulncheck' or lock['version'] != 'v1.1.4':
        raise ValueError('Unreviewed govulncheck source selection')
    if not discover and not re.fullmatch(r'[a-f0-9]{64}', lock.get('binarySHA256') or ''):
        raise ValueError('govulncheck binary checksum must be recorded before analysis')
    if platform.system() not in ('Windows', 'Linux'):
        raise ValueError('Only Windows and Linux build hosts are locked')
    windows = platform.system() == 'Windows'
    host = 'windows-amd64' if windows else 'linux-amd64'
    if platform.machine().lower() not in ('amd64', 'x86_64'):
        raise ValueError('Only amd64 Go SDK is locked')
    sdk = lock['sdks'][host]
    destination = Path(destination).resolve()
    destination.mkdir(parents=True, exist_ok=True)
    raw = download(sdk, destination / 'downloads' / host)
    extract_sdk(raw, destination / 'sdk', windows)
    goroot = destination / 'sdk/go'
    compiler = goroot / ('bin/go.exe' if windows else 'bin/go')
    if (goroot / 'VERSION').read_text().splitlines()[0] != lock['goVersion']:
        raise ValueError('Go SDK version differs')
    proxy = destination / 'proxy'
    versions = {}
    for item in lock['inputs']:
        prefix = 'https://proxy.golang.org/'
        if not item['url'].startswith(prefix):
            raise ValueError('Unreviewed Go module proxy')
        path = safe_target(proxy, item['url'].removeprefix(prefix))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(download(item, destination / 'downloads' / item['sha256']))
        match = re.fullmatch(r'(.+)/@v/([^/]+)\.(?:mod|info|zip)', item['url'].removeprefix(prefix))
        if not match:
            raise ValueError('Invalid pinned Go proxy record')
        versions.setdefault(match[1], set()).add(match[2])
    # The Go install command checks module deprecation through the version list.
    # Expose only reviewed versions, without requesting a floating remote latest.
    for module, values in versions.items():
        listing = safe_target(proxy, module + '/@v/list')
        listing.write_text('\n'.join(sorted(values)) + '\n', encoding='utf-8')
    env = dict(os.environ, GOROOT=str(goroot), GOPATH=str(destination / 'gopath'),
               GOCACHE=str(destination / 'cache'), GOPROXY=proxy.as_uri(),
               GOSUMDB='off', GOTOOLCHAIN='local', CGO_ENABLED='0', GOOS='linux',
               GOARCH='amd64', GOAMD64='v1', GOTELEMETRY='off', GOENV='off', GOFLAGS='')
    env.pop('GOBIN', None)
    command = [str(compiler), 'install', '-trimpath', '-ldflags=-buildid=',
               lock['module'] + '@' + lock['version']]
    subprocess.run(command, env=env, cwd=destination, check=True)
    built = destination / 'gopath' / ('bin/linux_amd64/govulncheck' if windows else 'bin/govulncheck')
    binary = built.read_bytes()
    if not discover:
        verified(binary, lock['binarySHA256'])
    result = {'version': lock['version'], 'goVersion': lock['goVersion'],
              'binarySHA256': hashlib.sha256(binary).hexdigest(), 'discoveryOnly': discover,
              'sourceInputs': len(lock['inputs']), 'scannerExecuted': False}
    output = destination / 'govulncheck'
    output.write_bytes(binary)
    output.chmod(0o755)
    (destination / 'govulncheck-build.json').write_text(json.dumps(result, indent=2) + '\n')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--destination', type=Path, required=True)
    parser.add_argument('--discover', action='store_true')
    args = parser.parse_args()
    print(json.dumps(stage(args.destination, args.discover), indent=2))


if __name__ == '__main__':
    main()
