#!/usr/bin/env python3
"""Dependency-free manifest policy engine; shared by offline checks and host bootstrap."""
import argparse
import json
from pathlib import Path
import re
import sys


def flatten(objects):
    for obj in objects:
        if not obj:
            continue
        if obj.get('kind') == 'List':
            yield from flatten(obj.get('items', []))
        else:
            yield obj


def podspec(obj):
    if obj['kind'] == 'Pod':
        return obj.get('spec', {})
    if obj['kind'] == 'CronJob':
        return obj.get('spec', {}).get('jobTemplate', {}).get('spec', {}).get('template', {}).get('spec')
    return obj.get('spec', {}).get('template', {}).get('spec')


def security_context(context):
    defaults = dict(privileged=False, allowPrivilegeEscalation=True, runAsNonRoot=False,
                    runAsUser=None, runAsGroup=None, readOnlyRootFilesystem=False, procMount='Default')
    result = defaults | context
    caps = result.get('capabilities', {})
    result['capabilities'] = dict(add=sorted(caps.get('add', [])), drop=sorted(caps.get('drop', [])))
    return result


def mounts(values):
    return sorted([dict(readOnly=False, mountPropagation=None, subPath='', subPathExpr='') | v
                   for v in values], key=lambda v: v['name'])


def hostpaths(values):
    return sorted([dict(name=v['name'], hostPath=dict(type='') | v['hostPath'])
                   for v in values], key=lambda v: v['name'])


def pod_projection(obj):
    spec = podspec(obj)
    volumes = {v['name']: v for v in spec.get('volumes', []) if 'hostPath' in v}
    containers = []
    for category in ('containers', 'initContainers', 'ephemeralContainers'):
        for c in spec.get(category, []):
            containers.append(dict(name=c['name'], category=category, image=c.get('image', ''),
                command=c.get('command', []), args=c.get('args', []),
                securityContext=security_context(spec.get('securityContext', {}) | c.get('securityContext', {})),
                hostMounts=mounts([m for m in c.get('volumeMounts', []) if m['name'] in volumes])))
    return dict(hostNetwork=spec.get('hostNetwork', False), hostPID=spec.get('hostPID', False),
                hostIPC=spec.get('hostIPC', False), hostPaths=hostpaths(volumes.values()),
                containers=sorted(containers, key=lambda c: (c['category'], c['name'])))


def control_plane_problems(obj, expected):
    spec, issues = obj['spec'], []
    projection = pod_projection(obj)
    name = obj['metadata']['name']
    if not spec.get('hostNetwork') or spec.get('hostPID', False) or spec.get('hostIPC', False):
        issues.append('unapproved host namespace configuration')
    if spec.get('initContainers') or spec.get('ephemeralContainers') or len(spec.get('containers', [])) != 1:
        issues.append('unapproved control-plane container layout')
        return issues
    container = projection['containers'][0]
    if container['name'] != name or container['image'] != expected['image']:
        issues.append('unapproved control-plane container name/image')
    if not container['command'] or container['command'][0] != name or container['args']:
        issues.append('unapproved control-plane executable')
    sc = container['securityContext']
    allowed_keys = {'privileged', 'allowPrivilegeEscalation', 'runAsNonRoot', 'runAsUser', 'runAsGroup',
                    'readOnlyRootFilesystem', 'procMount', 'capabilities', 'seccompProfile'}
    if (set(sc) - allowed_keys or sc['privileged'] or sc['procMount'] != 'Default' or
            sc['capabilities']['add'] or sc['runAsUser'] not in (None, 0) or
            sc['runAsGroup'] not in (None, 0) or sc.get('seccompProfile') != {'type': 'RuntimeDefault'}):
        issues.append('unapproved control-plane security settings')
    allowed = expected['mounts']
    volumes = {v['name']: v['hostPath'] for v in projection['hostPaths']}
    seen = set()
    # No extra non-host volumes or mounts may hide a change in node interface usage.
    if len(volumes) != len(spec.get('volumes', [])):
        issues.append('unapproved control-plane volume type')
    for mount in container['hostMounts']:
        source = volumes[mount['name']]
        path = source['path']
        if path not in allowed:
            issues.append('unapproved control-plane host path: ' + path)
            continue
        rule = allowed[path]
        if (source['type'] != rule['type'] or mount['mountPath'] != path or
                mount['readOnly'] != rule['readOnly'] or mount['mountPropagation'] is not None or
                mount['subPath'] or mount['subPathExpr']):
            issues.append('unapproved access mode or target for ' + path)
        if path in seen:
            issues.append('duplicate control-plane host path: ' + path)
        seen.add(path)
    if len(container['hostMounts']) != len(spec['containers'][0].get('volumeMounts', [])):
        issues.append('unapproved control-plane mount')
    if len(container['hostMounts']) != len(volumes):
        issues.append('unmounted/duplicate control-plane host volume')
    for path, rule in allowed.items():
        if rule.get('required') and path not in seen:
            issues.append('missing required control-plane host path: ' + path)
    return issues


def audit_objects(objects, policy, mode='workloads'):
    registry = policy['registry']
    active = policy.get('status') == 'approved'
    agents = policy.get('agents', {}) if active else {}
    control = policy.get('controlPlane', {}) if active and mode == 'control-plane' else {}
    problems, inventory, accepted, seen = [], [], [], set()
    objects = list(flatten(objects))
    if not objects:
        problems.append('empty manifest input')
    for obj in objects:
        key = f"{obj.get('kind')}/{obj.get('metadata', {}).get('namespace', 'cluster')}/{obj.get('metadata', {}).get('name')}"
        if key in seen:
            problems.append(f'{key}: duplicate resource')
        seen.add(key)
        if re.search(r'/(v[0-9]+(?:alpha|beta)[0-9]+)$', obj.get('apiVersion', '')):
            problems.append(f'{key}: non-stable workload API')
        if obj.get('kind') == 'PersistentVolume':
            spec = obj.get('spec', {})
            if 'hostPath' in spec:
                problems.append(f'{key}: forbidden hostPath PV')
            if 'local' in spec and (not spec.get('nodeAffinity') or obj.get('metadata', {}).get('annotations', {}).get('vcloud.io/vetted') != 'true'):
                problems.append(f'{key}: Local PV requires documented vetting and nodeAffinity')
            if 'local' in spec:
                # An annotation alone is not approval to expose an arbitrary host path.
                vetted = policy.get('localPVs', {}).get(obj['metadata']['name'])
                scope = {k: spec.get(k) for k in ('local', 'nodeAffinity', 'accessModes', 'volumeMode', 'storageClassName')}
                if vetted != scope:
                    problems.append(f'{key}: Local PV outside vetted storage allowlist')
            if 'local' not in spec and 'csi' not in spec:
                problems.append(f'{key}: persistent storage requires CSI or vetted Local PV')
        spec = podspec(obj)
        if spec is None:
            continue
        entry = dict(resource=key, **pod_projection(obj))
        inventory.append(entry)
        scoped = key in agents or key in control
        if key in agents and mode == 'workloads':
            expected = agents[key]
            actual = {k: v for k, v in entry.items() if k != 'resource'}
            if actual != expected:
                problems.append(f'{key}: drift from approved node-agent images/mounts/security/container layout')
            else:
                accepted.append(key)
        elif key in control:
            issues = control_plane_problems(obj, control[key])
            problems.extend(f'{key}: {issue}' for issue in issues)
            if not issues:
                accepted.append(key)
        elif mode == 'control-plane':
            problems.append(f'{key}: resource outside approved static control plane')
        else:
            if entry['hostPaths']:
                problems.append(f'{key}: forbidden hostPath volume(s)')
            if entry['hostNetwork'] or entry['hostPID'] or entry['hostIPC']:
                problems.append(f'{key}: host namespaces outside approved node scope')
        for c in entry['containers']:
            image, sc = c['image'], c['securityContext']
            if not image.startswith(registry + '/'):
                problems.append(f'{key}/{c["name"]}: image outside SSoT registry')
            if not re.search(r'@sha256:[a-f0-9]{64}$|:v?\d+\.\d+\.\d+(?:[._+-][A-Za-z0-9._+-]+)?$', image):
                problems.append(f'{key}/{c["name"]}: image is not pinned to a digest or semantic version')
            if sc['privileged']:
                problems.append(f'{key}/{c["name"]}: privileged containers prohibited')
            if not scoped and (sc['runAsUser'] == 0 or not sc['runAsNonRoot']):
                problems.append(f'{key}/{c["name"]}: root execution outside approved node scope')
            if not scoped and sc['capabilities']['add']:
                problems.append(f'{key}/{c["name"]}: added capabilities outside approved node scope')
    if mode == 'control-plane' and set(control) != seen:
        problems.append('control-plane input must contain exactly the four approved static Pods')
    return dict(status='blocked' if problems else 'passed', authorization=policy.get('approval', 'none'),
                violations=problems, acceptedExceptions=accepted, resources=inventory)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--policy', type=Path, required=True)
    parser.add_argument('--mode', choices=['workloads', 'control-plane'], default='workloads')
    args = parser.parse_args()
    result = audit_objects(json.load(sys.stdin), json.loads(args.policy.read_text()), args.mode)
    print(f'SSoT contract: {result["status"]}; {len(result["violations"])} findings', file=sys.stderr)
    for finding in result['violations']:
        print(finding, file=sys.stderr)
    return 1 if result['violations'] else 0


if __name__ == '__main__':
    raise SystemExit(main())
