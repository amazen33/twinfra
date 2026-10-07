#!/usr/bin/env python3
"""Private-only containerd routing, verified DNS fallback and read-only CRI gates.

No credentials, upstream fallback, insecure TLS, image pulls or cluster writes.
The configure action requires node administration; check is read-only.
"""
import argparse
import http.client
import ipaddress
import json
import os
from pathlib import Path
import re
import shutil
import socket
import ssl
import subprocess
import sys
import tempfile
import tomllib

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = 'registry.vcloud.example.com'
UPSTREAMS = ('quay.io', 'docker.io', 'registry.k8s.io', 'ghcr.io', 'public.ecr.aws', 'nvcr.io')
MARKER = '# Managed by vCloud registry bootstrap (ADR architecture/0020)'
DEFAULT_IMAGES = ROOT / 'deploy/required-images.txt'


def hosts_config(upstream=None, ca_file=''):
    """An API-root prefix maps upstream repo paths into canonical mirror repos.

    Configure BOTH the first host and final server with the explicit API root;
    server=quay.io would re-enable egress, and override_path alone adds no prefix.
    """
    if upstream is not None and upstream not in UPSTREAMS:
        raise ValueError('Unsupported upstream registry')
    if ca_file and (not str(ca_file).startswith('/') or re.search(r'["\n\r\\]', str(ca_file))):
        raise ValueError('CA must be an absolute public certificate path')
    url = 'https://' + REGISTRY + ('/v2/' + upstream if upstream else '')
    fields = 'capabilities = ["pull", "resolve"]\n'
    if upstream:
        fields += 'override_path = true\n'
    if ca_file:
        fields += 'ca = ' + json.dumps(str(ca_file)) + '\n'
    return MARKER + '\nserver = ' + json.dumps(url) + '\n' + fields + '\n[host.' + json.dumps(url) + ']\n' + fields


def registry_files(ca_file=''):
    return {name + '/hosts.toml': hosts_config(None if name in ('_default', REGISTRY) else name, ca_file)
            for name in ('_default', REGISTRY, *UPSTREAMS)}


def cri_config(text):
    """Change only the active CRI registry config_path, preserving other fields."""
    cfg = tomllib.loads(text)
    version = cfg.get('version', 1)
    if version not in (2, 3) or cfg.get('imports'):
        raise ValueError('Require explicit containerd config v2/v3 without competing imported configuration')
    if 'cri' in cfg.get('disabled_plugins', []):
        raise ValueError('CRI plugin is disabled')
    plugin = 'io.containerd.cri.v1.images' if version == 3 else 'io.containerd.grpc.v1.cri'
    table = '[plugins."' + plugin + '".registry]'
    pattern = r'(?ms)^\[plugins\.[\'\"]' + re.escape(plugin) + r'[\'\"]\.registry\][ \t]*\n(.*?)(?=^\[|\Z)'
    match = re.search(pattern, text)
    if match:
        body = match[1]
        line = '  config_path = "/etc/containerd/certs.d"'
        if re.search(r'(?m)^\s*config_path\s*=', body):
            body = re.sub(r'(?m)^[ \t]*config_path\s*=.*$', line, body)
        else:
            body = line + '\n' + body
        result = text[:match.start(1)] + body + text[match.end(1):]
    else:
        result = text.rstrip() + '\n\n' + table + '\n  config_path = "/etc/containerd/certs.d"\n'
    assert tomllib.loads(result)['plugins'][plugin]['registry']['config_path'] == '/etc/containerd/certs.d'
    return result


def hosts_fallback(text, address):
    address = str(ipaddress.ip_address(address))
    if ipaddress.ip_address(address).is_unspecified or ipaddress.ip_address(address).is_multicast:
        raise ValueError('Invalid registry address')
    lines = []
    for line in text.splitlines():
        fields = line.split('#', 1)[0].split()
        if REGISTRY in fields[1:]:
            # Preserve unrelated aliases sharing an existing /etc/hosts line.
            aliases = [name for name in fields[1:] if name != REGISTRY]
            if aliases:
                lines.append(fields[0] + '\t' + ' '.join(aliases))
        else:
            lines.append(line)
    return '\n'.join(lines).rstrip() + '\n' + address + '\t' + REGISTRY + ' # vCloud verified registry fallback\n'


def tls_probe(address, ca_file=''):
    """Probe an explicit IP with mirror hostname verification/SNI, never -k."""
    address = str(ipaddress.ip_address(address))
    context = ssl.create_default_context(cafile=ca_file or None)
    with socket.create_connection((address, 443), timeout=5) as tcp:
        with context.wrap_socket(tcp, server_hostname=REGISTRY) as stream:
            stream.sendall(('GET /v2/ HTTP/1.1\r\nHost: ' + REGISTRY + '\r\nConnection: close\r\n\r\n').encode('ascii'))
            response = http.client.HTTPResponse(stream)
            response.begin()
            status = response.status
            response.close()
    if status not in (200, 401):
        raise ValueError('Mirror /v2/ returned HTTP ' + str(status) + '; expected 200 or an authentication challenge')
    return status


def network_status(ca_file=''):
    result = {'dns': 'failed', 'tcpTls443': 'not_checked'}
    try:
        lookup = subprocess.run(['getent', 'ahosts', REGISTRY], capture_output=True, text=True, check=True, timeout=5)
        addresses = sorted({str(ipaddress.ip_address(line.split()[0])) for line in lookup.stdout.splitlines() if line.strip()})
        if not addresses:
            raise ValueError('No registry addresses returned')
        result.update(dns='passed', addresses=addresses)
        for address in addresses[:2]:
            try:
                result.update(httpStatus=tls_probe(address, ca_file), tcpTls443='passed')
                return result
            except (OSError, ValueError, http.client.HTTPException) as error:
                result['tcpTls443'] = 'failed'
                result['errorType'] = type(error).__name__
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        result['errorType'] = type(error).__name__
    return result


def cache_status(required, result):
    if not required:
        raise ValueError('Required image inventory is empty')
    if not isinstance(result, dict) or not isinstance(result.get('images'), list):
        raise ValueError('Malformed CRI image inventory')
    present = set()
    for image in result.get('images', []):
        if not isinstance(image, dict):
            raise ValueError('Malformed CRI image record')
        present.update(image.get('repoTags') or [])
        present.update(image.get('repoDigests') or [])
    missing = sorted(set(required) - present)
    return {'status': 'failed' if missing else 'passed', 'requiredCount': len(set(required)), 'missing': missing}


def required_images(path=DEFAULT_IMAGES, manifest=None):
    if manifest:
        import yaml
        from manifest_contract import flatten, podspec
        required = {c['image'] for obj in flatten(yaml.safe_load_all(Path(manifest).read_text()))
                    for group in ('containers', 'initContainers', 'ephemeralContainers')
                    for c in (podspec(obj) or {}).get(group, [])}
    else:
        required = {line.strip() for line in Path(path).read_text().splitlines() if line.strip() and not line.startswith('#')}
    if not required or any(not image.startswith(REGISTRY + '/') or
            not re.search(r'@sha256:[a-f0-9]{64}$|:v?\d+\.\d+\.\d+(?:[._+-][A-Za-z0-9._+-]+)?$', image)
            for image in required):
        raise ValueError('Required images must be a nonempty pinned canonical inventory')
    return sorted(required)


def inspect_cache(required, endpoint):
    if not re.fullmatch(r'unix:///[-a-zA-Z0-9_./]+', endpoint) or '..' in endpoint.split('/'):
        raise ValueError('CRI endpoint must be an explicit local Unix socket')
    cli = [shutil.which('crictl')] if shutil.which('crictl') else ['/usr/local/bin/k3s', 'crictl']
    response = subprocess.run([*cli, '--runtime-endpoint', endpoint, '--image-endpoint', endpoint, 'images', '-o', 'json'],
                              check=True, capture_output=True, text=True, timeout=20)
    return cache_status(required, json.loads(response.stdout))


def write_owned(path, text):
    """Idempotent atomic write; never follow symlinks or overwrite auth settings."""
    path = Path(path)
    if any(parent.is_symlink() for parent in (path, *path.parents)):
        raise ValueError('Refusing a symlink in node configuration path')
    old = path.read_text() if path.exists() else None
    if old == text:
        return False
    if path.name == 'hosts.toml' and old:
        cfg = tomllib.loads(old)
        allowed = {'capabilities', 'ca', 'override_path'}
        if set(cfg) - {'server', 'host', *allowed} or any(set(c) - allowed for c in cfg.get('host', {}).values()):
            raise ValueError('Existing custom registry authentication/options require reviewed migration')
        # Do not silently drop a pre-existing CA during an otherwise safe migration.
        old_cas = {str(c['ca']) for c in [cfg, *cfg.get('host', {}).values()] if c.get('ca')}
        new = tomllib.loads(text)
        if old_cas - {str(c['ca']) for c in [new, *new.get('host', {}).values()] if c.get('ca')}:
            raise ValueError('Pass the existing verified public CA file before migration')
    path.parent.mkdir(parents=True, exist_ok=True)
    if old is not None:
        backup = path.with_name(path.name + '.vcloud-registry-original')
        if backup.is_symlink():
            raise ValueError('Refusing symlink backup')
        if not backup.exists():
            descriptor = os.open(backup, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(descriptor, 'w') as stream:
                stream.write(old)
    mode = path.stat().st_mode & 0o777 if path.exists() else 0o644
    descriptor, name = tempfile.mkstemp(prefix='.vcloud-registry-', dir=path.parent)
    try:
        with os.fdopen(descriptor, 'w') as stream:
            stream.write(text)
        os.chmod(name, mode)
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)
    return True


def configure(config=Path('/etc/containerd/config.toml'), certs=Path('/etc/containerd/certs.d'),
              hosts=Path('/etc/hosts'), address='', ca_file='', apply=False):
    # Verify the target before modifying DNS; a guessed IP is never installed.
    if address:
        tls_probe(address, ca_file)
    files = registry_files(ca_file)
    report = {'action': 'apply' if apply else 'plan', 'registry': REGISTRY, 'caFile': str(ca_file),
              'hostFiles': list(files), 'daemonConfigChanged': False}
    if apply:
        if not config.exists():
            raise ValueError('Existing external containerd configuration is required')
        report['daemonConfigChanged'] = write_owned(config, cri_config(config.read_text()))
        for name, content in files.items():
            write_owned(certs / name, content)
        if address:
            write_owned(hosts, hosts_fallback(hosts.read_text(), address))
    report['network'] = network_status(ca_file)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['configure', 'check'])
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--registry-address', default='')
    parser.add_argument('--ca-file', default='')
    parser.add_argument('--cri-endpoint', default='unix:///run/containerd/containerd.sock')
    parser.add_argument('--images-file', type=Path, default=DEFAULT_IMAGES)
    parser.add_argument('--manifest', type=Path)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--cache-only', action='store_true')
    mode.add_argument('--network-only', action='store_true')
    args = parser.parse_args()
    try:
        if args.apply and (args.action != 'configure' or os.name != 'posix' or os.geteuid() != 0):
            raise ValueError('Only node administrators may apply registry configuration')
        if args.action == 'configure':
            report = configure(address=args.registry_address, ca_file=args.ca_file, apply=args.apply)
            code = 0
        else:
            network = network_status(args.ca_file)
            cache = {'status': 'not_checked'} if args.network_only else inspect_cache(required_images(args.images_file, args.manifest), args.cri_endpoint)
            code = int((not args.cache_only and network['tcpTls443'] != 'passed') or
                       (not args.network_only and cache['status'] != 'passed'))
            report = {'status': 'failed' if code else 'passed', 'mode': 'cache-only' if args.cache_only else 'network-only' if args.network_only else 'mirror-and-cache',
                      'network': network, 'cache': cache, 'scope': 'read-only node preflight; no pulls or rollout'}
        print(json.dumps(report, indent=2))
        return code
    except ValueError as error:
        print('Registry gate failed: ' + str(error), file=sys.stderr)
        return 1
    except (OSError, subprocess.SubprocessError, http.client.HTTPException) as error:
        # Do not echo transport stderr or certificate/credential-bearing config.
        print('Registry gate failed: ' + type(error).__name__, file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
