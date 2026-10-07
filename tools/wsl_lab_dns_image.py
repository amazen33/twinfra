#!/usr/bin/env python3
"""Build a deterministic, non-root CoreDNS image with no file capabilities.

The source is the canonical alias of the hash-verified K3s airgap image. Copying
the exact binary bytes into a fresh OCI layer intentionally drops its setcap
xattr, so drop-ALL containers can execute it on port 1053. No build Pod, Docker
daemon, upstream fetch, privilege exception or executable code change is used.
"""
import argparse
import hashlib
import io
import json
from pathlib import Path
import subprocess
import tarfile

IMAGE = 'registry.vcloud.example.com/vcloud/coredns:1.14.7-vcloud-wsl.1'


def encoded(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':')).encode()


def digest(data):
    return 'sha256:' + hashlib.sha256(data).hexdigest()


def binary_from_export(source):
    with tarfile.open(source) as outer:
        def blob(descriptor):
            path = 'blobs/sha256/' + descriptor['digest'].split(':')[1]
            data = outer.extractfile(path).read()
            if digest(data) != descriptor['digest']:
                raise ValueError('Source OCI content hash differs')
            return data
        index = json.load(outer.extractfile('index.json'))
        descriptor = index['manifests'][0]
        manifest = json.loads(blob(descriptor))
        while 'manifests' in manifest:
            descriptor = next(d for d in manifest['manifests'] if d.get('platform', {}).get('os') == 'linux' and d.get('platform', {}).get('architecture') == 'amd64')
            manifest = json.loads(blob(descriptor))
        binary = None
        for layer in manifest['layers']:
            with tarfile.open(fileobj=io.BytesIO(blob(layer)), mode='r:*') as files:
                for member in files.getmembers():
                    if member.name.lstrip('./') == 'coredns':
                        if not member.isfile():
                            raise ValueError('CoreDNS binary must be a regular file')
                        binary = files.extractfile(member).read()
        if not binary:
            raise ValueError('Verified source lacks CoreDNS binary')
        return binary, descriptor['digest']


def build(binary, output):
    layer_output = io.BytesIO()
    with tarfile.open(fileobj=layer_output, mode='w', format=tarfile.USTAR_FORMAT) as archive:
        member = tarfile.TarInfo('coredns')
        member.mode, member.uid, member.gid, member.mtime = 0o555, 65532, 65532, 0
        member.size = len(binary)
        archive.addfile(member, io.BytesIO(binary))
    layer = layer_output.getvalue()
    config = encoded({'architecture': 'amd64', 'os': 'linux',
        'config': {'User': '65532:65532', 'Entrypoint': ['/coredns']},
        'rootfs': {'type': 'layers', 'diff_ids': [digest(layer)]}})
    manifest = encoded({'schemaVersion': 2, 'mediaType': 'application/vnd.oci.image.manifest.v1+json',
        'config': {'mediaType': 'application/vnd.oci.image.config.v1+json', 'digest': digest(config), 'size': len(config)},
        'layers': [{'mediaType': 'application/vnd.oci.image.layer.v1.tar', 'digest': digest(layer), 'size': len(layer)}]})
    index = encoded({'schemaVersion': 2, 'manifests': [{'mediaType': 'application/vnd.oci.image.manifest.v1+json',
        'digest': digest(manifest), 'size': len(manifest), 'platform': {'os': 'linux', 'architecture': 'amd64'},
        'annotations': {'org.opencontainers.image.ref.name': IMAGE}}]})
    data = {'oci-layout': encoded({'imageLayoutVersion': '1.0.0'}), 'index.json': index}
    for item in (config, layer, manifest):
        data['blobs/sha256/' + digest(item).split(':')[1]] = item
    with tarfile.open(output, 'w', format=tarfile.USTAR_FORMAT) as archive:
        for name, content in sorted(data.items()):
            member = tarfile.TarInfo(name); member.size = len(content); member.mode = 0o644
            archive.addfile(member, io.BytesIO(content))
    return {'image': IMAGE, 'manifestDigest': digest(manifest), 'binarySHA256': hashlib.sha256(binary).hexdigest(),
            'user': '65532:65532', 'fileCapabilities': 'none'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cache', type=Path, required=True)
    options = parser.parse_args()
    source = options.cache / 'coredns-source.tar'
    subprocess.run(['ctr', '-n', 'k8s.io', 'images', 'export', '--local', '--platform', 'linux/amd64', str(source),
                    'registry.vcloud.example.com/docker.io/rancher/mirrored-coredns-coredns:1.14.7'], check=True)
    binary, parent = binary_from_export(source)
    target = options.cache / 'coredns-nonroot.tar'
    report = build(binary, target)
    report['sourceManifestDigest'] = parent
    subprocess.run(['ctr', '-n', 'k8s.io', 'images', 'import', '--platform', 'linux/amd64', str(target)], check=True)
    (options.cache / 'coredns-image.json').write_text(json.dumps(report, indent=2) + '\n')
    print('CoreDNS non-root derivative imported: ' + report['manifestDigest'])
