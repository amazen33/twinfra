#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Isolated WO-40c renderer proof; no cluster or host provisioning."""
import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import sys
import urllib.request

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
from kubeadm_dry_run import execute, verify_binary, URL, VERSION

CONTROL_ROOT = Path(__file__).resolve().parents[2]

def cluster_document(documents):
    clusters = [doc for doc in documents if doc.get('kind') == 'ClusterConfiguration']
    if len(clusters) != 1:
        raise ValueError('Expected one ClusterConfiguration')
    return clusters[0]


def uploaded_cluster(log):
    objects = []
    for attached in log.split('[dryrun] Attached object:\n')[1:]:
        document = yaml.safe_load(attached.split('\n[', 1)[0])
        if isinstance(document, dict) and document.get('kind') == 'ConfigMap':
            if document.get('metadata', {}).get('name') == 'kubeadm-config':
                objects.append(yaml.safe_load(document['data']['ClusterConfiguration']))
    if len(objects) != 1:
        raise ValueError('Cannot prove the exact would-upload ClusterConfiguration')
    return objects[0]


def upload_preview(binary, config, work):
    from http.server import BaseHTTPRequestHandler, HTTPServer
    from threading import Thread
    calls = []
    class ReadOnlyAPI(BaseHTTPRequestHandler):
        def do_GET(self):
            calls.append('GET')
            self.send_response(404)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(b'{"apiVersion":"v1","kind":"Status","status":"Failure","reason":"NotFound","code":404}')

        def do_POST(self):
            calls.append('WRITE')
            self.send_error(405)

        do_PUT = do_PATCH = do_DELETE = do_POST

        def log_message(self, *args):
            pass
    with HTTPServer(('127.0.0.1', 0), ReadOnlyAPI) as server:
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        preview = work / 'upload-preview'
        preview.mkdir(mode=0o700)
        kubeconfig = {'apiVersion': 'v1', 'kind': 'Config', 'current-context': 'offline',
            'clusters': [{'name': 'offline', 'cluster': {'server': 'http://127.0.0.1:' + str(server.server_port)}}],
            'users': [{'name': 'offline', 'user': {}}],
            'contexts': [{'name': 'offline', 'context': {'cluster': 'offline', 'user': 'offline'}}]}
        (preview / 'admin.conf').write_text(yaml.safe_dump(kubeconfig))
        (preview / 'admin.conf').chmod(0o600)
        try:
            log = execute(['sudo', '-n', 'env', 'KUBEADM_INIT_DRYRUN_DIR=' + str(preview),
                str(binary), 'init', 'phase', 'upload-config', 'kubeadm', '--config', str(config), '--dry-run'],
                work / 'upload-preview.log')
        finally:
            server.shutdown()
            thread.join(timeout=5)
            (preview / 'admin.conf').unlink()
    if not calls or set(calls) != {'GET'}:
        raise ValueError('Dry-run upload must use only the loopback read-only API stub')
    return uploaded_cluster(log)


def etcd_preview(binary, config, directory, name):
    preview = directory / name
    preview.mkdir()
    execute(['sudo', '-n', 'env', 'KUBEADM_INIT_DRYRUN_DIR=' + str(preview),
             str(binary), 'init', 'phase', 'etcd', 'local', '--config', str(config), '--dry-run'],
            directory / (name + '.log'))
    manifest = preview / 'etcd.yaml'
    execute(['sudo', '-n', 'chown', str(os.getuid()) + ':' + str(os.getgid()), str(manifest)],
            directory / (name + '-owner.log'))
    return yaml.safe_load(manifest.read_text())


def prove_candidate(source, binary, config, work, guard):
    base = list(yaml.safe_load_all(config.read_text()))
    migrated = guard.normalise(base, binary, work, 'proof')
    uploaded = upload_preview(binary, config, work)
    if guard.without_tags(migrated) != guard.without_tags(uploaded):
        raise ValueError('STOP: migrate does not equal init would-upload ClusterConfiguration')
    (work / 'normalised-cluster.json').write_text(json.dumps(migrated, indent=2) + '\n')
    (work / 'would-upload-cluster.json').write_text(json.dumps(uploaded, indent=2) + '\n')
    stored = copy.deepcopy(uploaded)
    old_cluster = cluster_document(base)
    for component, tag in [('etcd', '3.6.8-0'), ('coredns', 'v1.14.2')]:
        guard.set_tag(old_cluster, component, tag)
        guard.set_tag(stored, component, tag)
    before = work / 'before.yaml'
    before.write_text(yaml.safe_dump_all(base))
    lock = json.loads((source / 'deploy/common/bootstrap-images.lock.json').read_text())
    cm = {'kind': 'ConfigMap', 'metadata': {'name': 'kubeadm-config', 'namespace': 'kube-system'},
          'data': {'ClusterConfiguration': guard.encoded(stored)}}
    output = work / 'candidate'
    guard.write_candidate(base, stored, cm, lock, output, work, kubeadm=binary,
                          patches_directory=base[0]['patches']['directory'])
    candidate = output / 'candidate.yaml'
    digest = hashlib.sha256(candidate.read_bytes()).hexdigest()
    execute([str(binary), 'config', 'validate', '--config', str(candidate)], work / 'candidate-validate.log')
    old = etcd_preview(binary, before, work, 'before')
    after = etcd_preview(binary, candidate, work, 'after')
    guard.verify_etcd(old, after, guard.image(lock, 'etcd'))
    if hashlib.sha256(candidate.read_bytes()).hexdigest() != digest:
        raise ValueError('Exact generated candidate bytes changed during validation')
    return digest


def maintenance_preview(source, binary, config, directory):
    import importlib.util
    helper = source / 'tools/control_plane_candidate.py'
    spec = importlib.util.spec_from_file_location('maintenance_candidate', helper)
    guard = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(guard)
    work = directory / 'maintenance'
    work.mkdir(mode=0o700)
    try:
        digest = prove_candidate(source, binary, config, work, guard)
    finally:
        # Raw migrate output may contain a generated bootstrap token. Never
        # upload it as a CI artifact, even when an assertion or command fails.
        for label in ('proof', 'host', 'stored'):
            for suffix in ('-input.yaml', '.yaml'):
                (work / ('.migrate-' + label + suffix)).unlink(missing_ok=True)
    (work / 'summary.json').write_text(json.dumps({'status': 'passed',
        'scope': 'isolated renderer/upload-config proof, not Dell acceptance',
        'normalisation': 'migrate equals init upload-config dry-run apart from two tags',
        'etcdDiff': 'image only', 'candidateSHA256': digest,
        'exactCandidateValidatedAndDryRun': True, 'loopbackAPI': 'read-only GET stub'}) + '\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('source', 'assets', 'config', 'out'):
        parser.add_argument('--' + name, required=True, type=Path)
    args = parser.parse_args()
    binary = args.assets.resolve() / 'bin/kubeadm'
    with urllib.request.urlopen(URL + '.sha256', timeout=60) as response:
        verify_binary(binary, response.read(1024))
    report_root = CONTROL_ROOT / '.build/ci-report'
    output, config = args.out.resolve(), args.config.resolve()
    if not output.is_relative_to(report_root) or not config.is_relative_to(report_root):
        raise ValueError('Maintenance preview paths must stay in the CI report directory')
    output.mkdir(parents=True, exist_ok=True)
    if execute([str(binary), 'version', '-o', 'short'], output / 'version.log') != VERSION:
        raise ValueError('Unexpected maintenance preview kubeadm version')
    maintenance_preview(args.source.resolve(), binary, config, output)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
