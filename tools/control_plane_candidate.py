#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""WO-40c offline candidates and preview guards. Never executes cluster commands.

Inputs are JSON exported by the already-pinned yq/kubectl. Output JSON documents
are also valid YAML; no new Python dependency is needed on the host.
"""
import argparse
import copy
import difflib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
API = 'kubeadm.k8s.io/v1beta4'
TAGS = {'coredns': 'v1.14.7', 'etcd': '3.6.15-0'}
TAG_PATHS = {('dns', 'imageTag'), ('etcd', 'local', 'imageTag')}


def checked_path(path, directory):
    path, directory = Path(path), Path(directory).resolve()
    if '..' in path.parts or path.is_symlink():
        raise ValueError('Unsafe maintenance path')
    resolved = path.resolve()
    if not resolved.is_relative_to(directory):
        raise ValueError('Path must stay in the maintenance directory')
    return resolved


def read(path, directory):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError('Duplicate JSON key: ' + key)
            result[key] = value
        return result
    return json.loads(checked_path(path, directory).read_text(encoding='utf-8'), object_pairs_hook=unique)


def one(value):
    if isinstance(value, list) and len(value) == 1:
        value = value[0]
    if not isinstance(value, dict):
        raise ValueError('Expected one object')
    return value


def changes(before, after, prefix=()):
    if isinstance(before, dict) and isinstance(after, dict):
        result = set()
        for key in before.keys() | after.keys():
            if key not in before or key not in after:
                result.add(prefix + (key,))
            else:
                result |= changes(before[key], after[key], prefix + (key,))
        return result
    return set() if before == after else {prefix}


def without_tags(value):
    result = copy.deepcopy(value)
    for path in TAG_PATHS:
        node = result
        parents = []
        for key in path[:-1]:
            parents.append((node, key))
            node = node.get(key, {})
            if not isinstance(node, dict):
                raise ValueError('Malformed image-tag parent')
        node.pop(path[-1], None)
        for parent, key in reversed(parents):
            if parent.get(key) == {}:
                parent.pop(key)
    return result


def set_tag(value, component, tag):
    path = ('dns',) if component == 'coredns' else ('etcd', 'local')
    node = value
    for key in path:
        node = node.setdefault(key, {})
    node['imageTag'] = tag


def image(lock, component, digest=False):
    row = lock['images'][component]
    canonical = row['canonical']
    expected = 'registry.twinfra.example.com/registry.k8s.io/' + component + ':' + TAGS[component]
    if canonical != expected or lock['versions']['kubernetes'] != 'v1.36.5':
        raise ValueError('Maintenance lock identity/version differs')
    return canonical.rsplit(':', 1)[0] + '@' + row['digest'] if digest else canonical


def base_documents(base):
    if not isinstance(base, list) or any(not isinstance(doc, dict) for doc in base):
        raise ValueError('Base must be an array of configuration documents')
    kinds = [doc.get('kind') for doc in base]
    if len(kinds) != len(set(kinds)) or set(kinds) != {
            'InitConfiguration', 'ClusterConfiguration', 'KubeletConfiguration'}:
        raise ValueError('Unexpected/duplicate bootstrap documents')
    cluster = base[kinds.index('ClusterConfiguration')]
    init = base[kinds.index('InitConfiguration')]
    if cluster.get('apiVersion') != API or init.get('apiVersion') != API:
        raise ValueError('Require v1beta4 bootstrap configuration')
    expected = {'kubernetesVersion': 'v1.36.5', 'clusterName': 'twinfra-dev-cairo-1',
                'controlPlaneEndpoint': 'api.dev.cairo-1.twinfra.example.com:6443',
                'imageRepository': 'registry.twinfra.example.com/registry.k8s.io'}
    if any(cluster.get(key) != value for key, value in expected.items()):
        raise ValueError('Unexpected cluster identity/version/registry')
    if init.get('nodeRegistration', {}).get('name') != 'twinfra-dev-cairo-1':
        raise ValueError('Unexpected node identity')
    if init.get('patches', {}).get('directory') != '/var/lib/vcloud-host/kubeadm-patches':
        raise ValueError('Require original host patches directory')
    return cluster, kinds


def candidate(base, stored, lock):
    cluster, kinds = base_documents(base)
    drift = changes(without_tags(cluster), without_tags(one(stored)))
    if drift:
        raise ValueError('Stored ClusterConfiguration differs outside tags: ' +
                         ', '.join('.'.join(path) for path in sorted(drift)))
    result = copy.deepcopy(base)
    target = result[kinds.index('ClusterConfiguration')]
    for component, tag in TAGS.items():
        image(lock, component)
        set_tag(target, component, tag)
    if not changes(cluster, target).issubset(TAG_PATHS) and without_tags(cluster) != without_tags(target):
        raise ValueError('Candidate changed an unapproved field')
    if [doc for doc in base if doc is not cluster] != [doc for doc in result if doc is not target]:
        raise ValueError('Candidate changed a non-cluster document')
    return result, target


def encoded(value):
    return json.dumps(value, indent=2, sort_keys=True) + '\n'


def config_patch(before, after):
    return [{'op': 'test', 'path': '/data/ClusterConfiguration', 'value': before},
            {'op': 'replace', 'path': '/data/ClusterConfiguration', 'value': after}]


def stored_document(configmap):
    if (configmap.get('kind') != 'ConfigMap' or
        configmap.get('metadata', {}).get('name') != 'kubeadm-config' or
        configmap.get('metadata', {}).get('namespace') != 'kube-system'):
        raise ValueError('Expected saved kube-system/kubeadm-config ConfigMap')
    raw = configmap['data']['ClusterConfiguration']
    try:
        return one(json.loads(raw))
    except json.JSONDecodeError:
        # yq is already pinned and installed by Module -1; no pip install.
        parsed = subprocess.run(['yq', 'eval', '-o=json', '.', '-'], input=raw,
                                text=True, capture_output=True, timeout=30, check=True)
        return one(json.loads(parsed.stdout))


def write_candidate(base, stored, configmap, lock, output, workspace):
    if stored != stored_document(configmap):
        raise ValueError('Stored export differs from saved ConfigMap')
    result, target = candidate(base, stored, lock)
    original = configmap['data']['ClusterConfiguration']
    # The stored JSON export must be bound to this exact saved ConfigMap, not
    # a separately edited object. JSON is used for the equality check via yq.
    output = checked_path(output, workspace)
    if output.exists():
        raise ValueError('Output directory already exists; preserve prior candidates')
    after_etcd = copy.deepcopy(stored)
    set_tag(after_etcd, 'etcd', TAGS['etcd'])
    after_both = copy.deepcopy(after_etcd)
    set_tag(after_both, 'coredns', TAGS['coredns'])
    etcd_text, final_text = encoded(after_etcd), encoded(after_both)
    files = {'candidate.yaml': '---\n'.join(encoded(doc) for doc in result),
             'cluster.yaml': encoded(target),
             'etcd-configmap.patch.json': encoded(config_patch(original, etcd_text)),
             'dns-configmap.patch.json': encoded(config_patch(etcd_text, final_text)),
             'rollback-etcd-configmap.patch.json': encoded(config_patch(etcd_text, original)),
             'rollback-dns-configmap.patch.json': encoded(config_patch(final_text, etcd_text))}
    output.mkdir(mode=0o700)
    for name, text in files.items():
        with (output / name).open('x', encoding='utf-8') as stream:
            stream.write(text)
        (output / name).chmod(0o600)
    print(''.join(difflib.unified_diff(encoded(base).splitlines(True),
          encoded(result).splitlines(True), fromfile='host bootstrap', tofile='candidate')), end='')
    print('PASS: candidate differs only in approved image tags; no cluster writes')


def verify_etcd(live, preview, expected):
    live, preview = one(live), one(preview)
    if live.get('kind') != 'Pod' or live.get('metadata', {}).get('name') != 'etcd':
        raise ValueError('Expected saved etcd static Pod file, not API mirror Pod')
    containers = preview.get('spec', {}).get('containers', [])
    if len(containers) != 1 or containers[0].get('name') != 'etcd' or containers[0].get('image') != expected:
        raise ValueError('Unexpected etcd preview image/container')
    old = live['spec']['containers']
    if len(old) != 1 or old[0].get('name') != 'etcd':
        raise ValueError('Unexpected live etcd container')
    restored = copy.deepcopy(preview)
    restored['spec']['containers'][0]['image'] = old[0]['image']
    if restored != live:
        raise ValueError('STOP: etcd preview differs beyond image')
    mounts = [m for m in containers[0].get('volumeMounts', []) if m.get('name') == 'etcd-certs']
    if len(mounts) != 1 or mounts[0].get('readOnly') is not True:
        raise ValueError('STOP: missing unique read-only etcd certificate mount')
    print('PASS: etcd preview is image-only; all other fields and certificate mount preserved')


def parser():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument('--lock', type=Path, default=ROOT / 'deploy/common/bootstrap-images.lock.json')
    actions = cli.add_subparsers(dest='action', required=True)
    create = actions.add_parser('generate')
    for name in ('base', 'stored', 'configmap', 'out'):
        create.add_argument('--' + name, required=True, type=Path)
    verify = actions.add_parser('verify-etcd')
    for name in ('live', 'preview'):
        verify.add_argument('--' + name, required=True, type=Path)
    show = actions.add_parser('image')
    show.add_argument('component', choices=sorted(TAGS))
    show.add_argument('--digest', action='store_true')
    return cli


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        workspace = Path(__file__).resolve().parent
        lock_root = ROOT if args.lock == ROOT / 'deploy/common/bootstrap-images.lock.json' else workspace
        lock = read(args.lock, lock_root)
        if args.action == 'generate':
            write_candidate(read(args.base, workspace), read(args.stored, workspace),
                            read(args.configmap, workspace), lock, args.out, workspace)
        elif args.action == 'verify-etcd':
            verify_etcd(read(args.live, workspace), read(args.preview, workspace), image(lock, 'etcd'))
        else:
            print(image(lock, args.component, args.digest))
        return 0
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as error:
        print('STOP: ' + str(error), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
