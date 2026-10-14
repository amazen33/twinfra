#!/usr/bin/env python3
"""WO-34 source call graphs at tagged source and binary-matched Go toolchains.

This never builds or executes an application binary. Only the hash-locked Go
SDK and govulncheck run; dependencies are checked by upstream go.sum/SumDB.
"""
import argparse
import gzip
import hashlib
import io
import json
import os
from pathlib import Path
import re
import subprocess
import tarfile

from stage_govulncheck import download, extract_sdk, safe_target, verified
from triage_go_image import go_files, messages
from registry_export import export_public
from platform_pg_image import Export

ROOT = Path(__file__).resolve().parents[2]
TARGET = 'GO-2026-6612'


def build_info(raw):
    """Read Go 1.18+ inline build info as data, including the module sentinels."""
    index = raw.find(b'\xff Go buildinf:')
    if index < 0 or len(raw) < index + 32 or not raw[index + 15] & 2:
        raise ValueError('Inline Go build info required')

    def string(data):
        length = 0
        for offset, value in enumerate(data[:10]):
            length |= (value & 127) << (offset * 7)
            if value < 128:
                end = offset + 1 + length
                if end > len(data):
                    raise ValueError('Truncated Go build info')
                return data[offset + 1:end], data[end:]
        raise ValueError('Invalid Go build info length')

    version, remaining = string(raw[index + 32:])
    module, _ = string(remaining)
    version = version.decode()
    if not re.fullmatch(r'go1\.\d+\.\d+', version) or len(module) < 32:
        raise ValueError('Invalid Go build metadata')
    return version, module[16:-16].decode()


def extract_source(raw, destination):
    total = 0
    with tarfile.open(fileobj=io.BytesIO(raw), mode='r:*') as archive:
        roots = set()
        for member in archive:
            target = safe_target(destination, member.name)
            roots.add(member.name.split('/')[0])
            if member.isdir():
                continue
            if not member.isfile():
                # Project sources may contain documented symlinks unrelated to
                # Go packages. Do not materialize links or follow their targets.
                if member.issym():
                    continue
                raise ValueError('Source archive regular files required')
            total += member.size
            if total > 1024**3:
                raise ValueError('Source archive exceeds bounds')
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(archive.extractfile(member).read())
        if len(roots) != 1:
            raise ValueError('One source archive root required')
        return destination / roots.pop()


def findings(raw):
    result = []
    config = None
    for message in messages(raw):
        if 'config' in message:
            config = message['config']
        entry = message.get('finding')
        if entry and entry['osv'] == TARGET:
            trace = entry.get('trace', [])
            if not trace:
                raise ValueError('Source finding has no trace')
            result.append(dict(module=trace[0].get('module'),
                               version=trace[0].get('version'),
                               fixedVersion=entry.get('fixed_version'),
                               reachable=bool(trace[0].get('function')),
                               callStack=trace))
    if not config or config.get('scan_mode') != 'source':
        raise ValueError('Completed source-mode scan required')
    return config, result


def analyze(name, scanner, out):
    lock = json.loads((ROOT / 'tools/ci/toolchain.lock.json').read_text())
    verified(scanner.read_bytes(), lock['builds']['govulncheck']['binarySHA256'])
    inputs = lock['sourceAnalysis']
    project = next(p for p in inputs['projects'] if p['name'] == name)
    out.mkdir(parents=True, exist_ok=True)
    image = out / 'image.oci.tar'
    export_public(project['candidateReference'], image)
    source = Export(image)
    try:
        binaries = go_files(source)
    finally:
        source.archive.close()
    tagged = extract_source(download(dict(url=project['sourceURL'], sha256=project['sourceSHA256']),
                                    out / 'source.tar.gz'), out / 'source')
    report = dict(project=name, tag=project['tag'], image=project['candidateReference'],
                  sourceSHA256=project['sourceSHA256'], applicationBinaryBuilt=False,
                  applicationCodeExecuted=False, analyses=[])
    for number, entry in enumerate(project['analyses']):
        raw = binaries[entry['binaryPath']]
        version, metadata = build_info(raw)
        if version != entry['goVersion'] or hashlib.sha256(raw).hexdigest() != entry['binarySHA256']:
            raise ValueError('Analysis toolchain must match locked binary build info')
        sdk = out / version
        extract_sdk(download(inputs['sdks'][version], out / (version + '.tar.gz')), sdk, False)
        goroot = sdk / 'go'
        env = dict(os.environ, PATH=str(goroot / 'bin') + os.pathsep + os.environ['PATH'],
                   GOROOT=str(goroot), GOTOOLCHAIN=version, GOTELEMETRY='off', GOENV='off',
                   GOOS='linux', GOARCH='amd64', CGO_ENABLED='0', GOFLAGS='-mod=readonly',
                   GOWORK='off', GOPROXY='https://proxy.golang.org', GOSUMDB='sum.golang.org',
                   GOPATH=str(out / 'gopath'), GOCACHE=str(out / 'go-cache'))
        cwd = safe_target(tagged, entry['moduleDirectory'])
        go = str(goroot / 'bin/go')
        check = subprocess.run([go, 'version'], env=env, capture_output=True, text=True, check=True)
        if check.stdout.strip() != 'go version ' + version + ' linux/amd64':
            raise ValueError('Wrong source-analysis Go SDK')
        manifest = subprocess.run([go, 'list', '-m', '-json', 'all'], cwd=cwd, env=env,
                                  capture_output=True, text=True, check=True)
        modules = list(messages(manifest.stdout))
        # Ensure tagged-source MVS resolves the same affected module version as
        # the binary. Refuse an apparent clean result from different inputs.
        for module in entry['affectedModules']:
            if not any(v['Path'] == module['path'] and v.get('Version') == module['version'] for v in modules):
                raise ValueError('Tagged source differs from binary affected module version')
        run = subprocess.run([str(scanner.resolve()), '-mode=source', '-json', *entry['patterns']],
                             cwd=cwd, env=env, capture_output=True, text=True)
        prefix = out / ('analysis-' + str(number))
        prefix.with_suffix('.json.gz').write_bytes(gzip.compress(run.stdout.encode(), mtime=0))
        prefix.with_suffix('.log').write_text(run.stderr)
        if run.returncode:
            raise ValueError('Source analysis failed: ' + entry['binaryPath'])
        config, found = findings(run.stdout)
        report['analyses'].append(dict(binaryPath=entry['binaryPath'], goVersion=version,
                                      GOTOOLCHAIN=env['GOTOOLCHAIN'], buildInfo=metadata,
                                      moduleDirectory=entry['moduleDirectory'], patterns=entry['patterns'],
                                      database=config.get('db'), databaseLastModified=config.get('db_last_modified'),
                                      findings=found, classification='reachable' if any(v['reachable'] for v in found)
                                      else 'not-reachable-in-selected-source-configuration'))
        (out / 'summary.json').write_text(json.dumps(report, indent=2) + '\n')
    image.unlink()
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project', choices=['argocd', 'coredns', 'etcd'], required=True)
    parser.add_argument('--scanner', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    analyze(args.project, args.scanner, args.out.resolve())
