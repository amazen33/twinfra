#!/usr/bin/env python3
"""Generate source-analysis provenance/SDK licences from verified data inputs."""
import copy
import hashlib
import json
from pathlib import Path
import urllib.request

ROOT = Path(__file__).resolve().parents[2]


def save(path, value):
    path.write_text(json.dumps(value, indent=2) + '\n', encoding='utf-8', newline='\n')


def refresh():
    data = json.loads((ROOT / '.build/wo-34/source-inputs/inputs.json').read_text())
    selections = {'argocd': [('usr/local/bin/argocd', '.', ['./cmd'])],
                  'coredns': [('coredns', '.', ['.'])],
                  'etcd': [('usr/local/bin/etcd', 'server', ['.']),
                           ('usr/local/bin/etcdctl', 'etcdctl', ['.']),
                           ('usr/local/bin/etcdutl', 'etcdutl', ['.'])]}
    projects = []
    versions = set()
    for row in data['projects']:
        project = {key: row[key] for key in ('name', 'repo', 'tag', 'image', 'sourceURL', 'sourceSHA256')}
        project['candidateReference'] = project.pop('image')
        project['analyses'] = []
        for path, directory, patterns in selections[row['name']]:
            binary = next(b for b in row['binaries'] if b['path'] == path)
            dependencies = []
            for line in binary['buildInfo'].splitlines():
                parts = line.split('\t')
                if len(parts) >= 3 and parts[0] == 'dep' and parts[1] == 'golang.org/x/net':
                    dependencies.append(dict(path=parts[1], version=parts[2]))
            versions.add(binary['goVersion'])
            project['analyses'].append(dict(binaryPath=path, binarySHA256=binary['sha256'],
                goVersion=binary['goVersion'], moduleDirectory=directory, patterns=patterns,
                affectedModules=dependencies))
        projects.append(project)
    lock_path = ROOT / 'tools/ci/toolchain.lock.json'
    lock = json.loads(lock_path.read_text())
    lock['sourceAnalysis'] = dict(projects=projects, sdks={v: data['sdks'][v] for v in sorted(versions)})
    save(lock_path, lock)
    register_path = ROOT / 'security/licence-register.json'
    register = json.loads(register_path.read_text())
    prior = next(c for c in register['components'] if c['id'] == 'tool|golang/go|go1.27.1')
    existing = {c['id'] for c in register['components']}
    for version in sorted(versions):
        key = 'tool|golang/go|' + version
        if key in existing:
            continue
        url = 'https://raw.githubusercontent.com/golang/go/' + version + '/LICENSE'
        with urllib.request.urlopen(url, timeout=60) as response:
            license_bytes = response.read()
        if b'Redistribution and use in source and binary forms' not in license_bytes or b'Neither the name' not in license_bytes:
            raise ValueError('Go SDK BSD-3-Clause licence cannot be verified')
        (ROOT / '.build/wo-34/source-inputs' / (version + '-LICENSE')).write_bytes(license_bytes)
        entry = copy.deepcopy(prior)
        entry.update(id=key, version=version, licenceSource=url,
                     integrities=['sha256:' + data['sdks'][version]['sha256']],
                     notes='WO-34 Amendment 2: analysis-only SDK matching published application binary build info; no application binary built.')
        register['components'].append(entry)
    register['components'].sort(key=lambda c: c['id'])
    save(register_path, register)
    path = ROOT / 'security/licence-baseline.json'
    baseline = json.loads(path.read_text())
    for entry in baseline['findings']:
        if entry['id'] == 'schema-source:tools/ci/toolchain.lock.json':
            entry['fingerprint'] = hashlib.sha256(lock_path.read_bytes()).hexdigest()
    save(path, baseline)


if __name__ == '__main__':
    refresh()
