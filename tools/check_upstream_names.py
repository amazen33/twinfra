#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""ADR-0047: validate new environment renders against digest-verified upstream sources.

ADR-0038 migration keeps the existing WSL/reference profiles unchanged. Every
deploy/environments profile with a root.yaml is rendered; reserved CIDR rows and
seed-only second-region rehearsals are not installations.
"""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import subprocess
import yaml

ROOT = Path(__file__).resolve().parents[1]


def source_objects(root, project, helm):
    objects = []
    for source in project['sources']:
        file = root / source['path']
        raw = file.read_bytes()
        if hashlib.sha256(raw).hexdigest() != source['sha256']:
            raise ValueError('Upstream source digest differs: ' + source['path'])
        if source['format'] == 'chart':
            raw = subprocess.check_output([str(helm), 'template', project['release'], str(file),
                '--namespace', project['namespace']], text=True, encoding='utf-8')
        elif source['format'] == 'gzip':
            raw = gzip.decompress(raw).decode('utf-8')
        else:
            raw = raw.decode('utf-8')
        objects += [o for o in yaml.safe_load_all(raw) if o and isinstance(o, dict) and 'kind' in o]
    return objects


def validate(objects, registry, sources):
    allowed = set()
    for project in registry['projects']:
        present = {(o['kind'], o['metadata']['name']) for o in sources[project['project']]}
        for entry in project['names']:
            key = (entry['kind'], entry['name'])
            if key not in present:
                raise ValueError('Registered upstream name absent from pinned source: ' + str(key))
            allowed.add(key)
    for obj in objects:
        kind, name = obj['kind'], obj['metadata']['name']
        if name.startswith('twinfra-'):
            if any(word in name.lower() for word in ('lab', 'wsl', 'vcloud')):
                raise ValueError('Forbidden Twinfra-owned name: ' + name)
        elif (kind, name) not in allowed or kind in ('Application', 'AppProject'):
            raise ValueError('Unregistered or Twinfra-owned resource name: ' + name)
        for key in ('twinfra.io/environment', 'twinfra.io/region', 'twinfra.io/component'):
            if key not in obj['metadata'].get('labels', {}):
                raise ValueError('Missing environment label: ' + name + '/' + key)


def renders(root, kustomize):
    objects = []
    profiles = sorted((root / 'deploy/environments').glob('*/*/root.yaml'))
    if not profiles:
        raise ValueError('No deployable environment profiles')
    for profile in profiles:
        objects += [o for o in yaml.safe_load_all(profile.read_text()) if o]
        objects += [o for o in yaml.safe_load_all((profile.parent / 'apps/applications.yaml').read_text()) if o]
        for directory in ('platform', 'services'):
            raw = subprocess.check_output([str(kustomize), 'build', str(profile.parent / directory)], text=True, encoding='utf-8')
            objects += [o for o in yaml.safe_load_all(raw) if o]
    return objects


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=ROOT)
    parser.add_argument('--helm', default='helm')
    parser.add_argument('--kustomize', default='kustomize')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    registry = json.loads((args.root / 'deploy/upstream-names.json').read_text())
    sources = {p['project']: source_objects(args.root, p, args.helm) for p in registry['projects']}
    objects = renders(args.root, args.kustomize)
    validate(objects, registry, sources)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(yaml.safe_dump_all(objects, sort_keys=False), encoding='utf-8', newline='\n')
    print(f'PASS: {len(objects)} new-environment objects; upstream names present in pinned sources')


if __name__ == '__main__':
    main()
