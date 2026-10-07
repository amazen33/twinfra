#!/usr/bin/env python3
"""Fail closed on Cilium legacy host routing outside the single WSL values file.

Scans source YAML, including Argo single/multiple sources, inline values,
valuesObject, dotted Helm parameters, ConfigMaps and valueFiles references.
Generated output and vendor archives are inputs to separate render/schema gates.
"""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys

import yaml

ROOT = Path(__file__).resolve().parents[1]
LAB = Path('lab/wsl/values/cilium-routing.yaml')
BASE = Path('module-2/values/cilium.yaml')
OPTION_KEYS = {'hostLegacyRouting', 'bpf.hostLegacyRouting',
               'enableHostLegacyRouting', 'enable-host-legacy-routing',
               'CILIUM_ENABLE_HOST_LEGACY_ROUTING'}
LAB_VALUES = {'cluster': {'name': 'vcloud-wsl-local'},
              'bpf': {'masquerade': True, 'hostLegacyRouting': True},
              'kubeProxyReplacement': True, 'routingMode': 'native',
              'socketLB': {'enabled': True}}
SKIP = {'.git', '.build', '.tools', '__pycache__', 'node_modules', 'schemas', 'vendor'}


class UniqueLoader(yaml.SafeLoader):
    """Reject duplicate fields that otherwise allow scanner/Helm disagreement."""


def unique_mapping(loader, node, deep=False):
    result = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in result:
            raise ValueError(f'Duplicate YAML field: {key}')
        result[key] = loader.construct_object(value_node, deep=deep)
    return result


UniqueLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, unique_mapping)


def documents(text):
    return list(yaml.load_all(text, Loader=UniqueLoader))


def inspect(value, *, allowed=False, trail=(), active=None):
    # Reject cyclic YAML aliases; do not recurse indefinitely on untrusted YAML.
    active = set() if active is None else active
    if isinstance(value, str):
        # Daemon extraArgs and string-embedded Helm configuration cannot evade
        # the structural checks above. Conservative rejection is intentional.
        if re.search(r'(?:--|\b)(?:enable-host-legacy-routing|enableHostLegacyRouting|bpf\.hostLegacyRouting|CILIUM_ENABLE_HOST_LEGACY_ROUTING)\s*[=:]\s*(?:true|1|yes|on)\b', value, re.IGNORECASE):
            raise ValueError('Legacy host-routing option embedded in a string')
        if re.search(r'--enable-host-legacy-routing(?![\w-])(?!=false(?:\s|$))', value):
            raise ValueError('Legacy host-routing option embedded in a string')
        return
    if not isinstance(value, (dict, list)):
        return
    if id(value) in active:
        raise ValueError('Cyclic YAML alias')
    active.add(id(value))
    try:
        if isinstance(value, list):
            for child in value:
                inspect(child, allowed=allowed, trail=trail, active=active)
            return
        for key, child in value.items():
            if key in OPTION_KEYS:
                if key == 'enableHostLegacyRouting':
                    raise ValueError('Unsupported Helm alias enableHostLegacyRouting; use bpf.hostLegacyRouting')
                if key == 'hostLegacyRouting' and (not trail or trail[-1] != 'bpf'):
                    raise ValueError('hostLegacyRouting must be nested under bpf')
                if key in ('enable-host-legacy-routing', 'CILIUM_ENABLE_HOST_LEGACY_ROUTING'):
                    if child not in ('false',) and not allowed:
                        raise ValueError('Legacy host routing ConfigMap override outside WSL values')
                elif type(child) is not bool:
                    raise ValueError('Helm host routing value must be a boolean, not a string/null/template')
                elif child and not allowed:
                    raise ValueError('Legacy host routing enabled outside WSL values')
            # Argo Helm parameters carry string values and dotted names.
            if key == 'name' and isinstance(child, str) and child in OPTION_KEYS:
                parameter = value.get('value')
                if child == 'enableHostLegacyRouting' or parameter != 'false' or value.get('forceString'):
                    raise ValueError('Forbidden or incorrectly typed Argo host-routing parameter')
            if key == 'path' and isinstance(child, str) and any(option in child for option in OPTION_KEYS):
                if value.get('value') not in (False, 'false'):
                    raise ValueError('Legacy host routing enabled by a JSON patch')
            if key == 'values' and isinstance(child, str):
                for embedded in documents(child):
                    inspect(embedded, allowed=False, active=active)
            if key == 'valueFiles' and isinstance(child, list):
                for ref in child:
                    normalized = str(ref).replace('\\', '/')
                    if LAB.name in normalized:
                        raise ValueError('WSL routing overlay cannot be referenced by an Argo Application')
            inspect(child, allowed=allowed, trail=(*trail, key), active=active)
    finally:
        active.remove(id(value))


def check_file(path, root):
    relative = path.relative_to(root)
    text = path.read_text(encoding='utf-8-sig')
    # Existing Helm/cloud-init templates are validated by their render gates.
    # Never skip a template attempting to configure one of the guarded options.
    templated = ('{{' in text and 'templates' in relative.parts) or relative.name.endswith('.template.yaml')
    if templated:
        if any(key in text for key in OPTION_KEYS) or LAB.name in text:
            raise ValueError('Host routing options in source templates require explicit reviewed rendering')
        return
    objects = documents(text)
    if relative == LAB:
        if len(objects) != 1 or json.dumps(objects[0], sort_keys=True) != json.dumps(LAB_VALUES, sort_keys=True):
            raise ValueError('WSL routing overlay differs from its narrow approved profile')
    for obj in objects:
        inspect(obj, allowed=(relative == LAB))


def check_repository(root):
    root = root.resolve()
    for required in (BASE, LAB):
        if not (root / required).is_file():
            raise ValueError(f'Missing required routing profile: {required.as_posix()}')
    base = documents((root / BASE).read_text(encoding='utf-8'))[0]
    if base.get('bpf', {}).get('hostLegacyRouting') is not False:
        raise ValueError('Base/production bpf.hostLegacyRouting must explicitly be false')
    count = 0
    for directory, folders, files in os.walk(root):
        folders[:] = sorted(folder for folder in folders if folder not in SKIP)
        for name in sorted(files):
            if Path(name).suffix not in ('.yaml', '.yml'):
                continue
            path = Path(directory) / name
            try:
                check_file(path, root)
            except (ValueError, yaml.YAMLError) as error:
                raise ValueError(f'{path.relative_to(root).as_posix()}: {error}') from error
            count += 1
    return count


def assert_config(objects, legacy, *, socket_lb=False):
    configs = [obj for obj in objects if obj and obj.get('kind') == 'ConfigMap'
               and obj.get('metadata', {}).get('name') == 'cilium-config']
    if len(configs) != 1:
        raise ValueError('Expected exactly one rendered cilium-config')
    expected = {'enable-host-legacy-routing': str(legacy).lower(),
                'enable-bpf-masquerade': 'true', 'kube-proxy-replacement': 'true',
                'routing-mode': 'native'}
    if socket_lb:
        expected['bpf-lb-sock'] = 'true'
    data = configs[0].get('data', {})
    if any(data.get(key) != value for key, value in expected.items()):
        raise ValueError(f'Rendered Cilium routing controls differ: expected {expected}')
    return {key: data[key] for key in expected}


def render_profiles(root, helm, build):
    build.mkdir(parents=True, exist_ok=True)
    command = [helm, 'template', 'cilium', str(root / 'module-2/vendor/cilium-1.20.2.tgz'),
               '--namespace', 'kube-system', '-f', str(root / BASE)]
    report = {}
    for name, legacy in [('production', False), ('vcloud-wsl-local', True)]:
        args = command + (['-f', str(root / LAB)] if legacy else [])
        output = subprocess.check_output(args, text=True, encoding='utf-8')
        report[name] = assert_config(documents(output), legacy, socket_lb=legacy)
        (build / f'{name}.yaml').write_text(output, encoding='utf-8', newline='\n')
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=ROOT)
    parser.add_argument('--helm', help='Also prove both profiles using the locked chart')
    parser.add_argument('--build', type=Path, default=ROOT / '.build/host-routing')
    args = parser.parse_args()
    try:
        count = check_repository(args.root)
        report = {'status': 'passed', 'scope': 'static governance and Helm rendering', 'yamlFiles': count}
        if args.helm:
            report['rendered'] = render_profiles(args.root, args.helm, args.build)
            (args.build / 'summary.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
        print(json.dumps(report, indent=2))
        return 0
    except (ValueError, yaml.YAMLError, OSError, subprocess.CalledProcessError) as error:
        print(f'Host-routing guard: {error}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
