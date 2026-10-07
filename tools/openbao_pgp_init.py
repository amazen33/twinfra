#!/usr/bin/env python3
"""Initialize the local OpenBao listener only with validated operator PGP keys.

Credentials and the HTTP response stay in process memory; only PGP ciphertext
is sent to the Kubernetes API. Public keys are normalized to binary OpenPGP
before base64 encoding. No key generation, token export, unseal or dev mode.
"""
import base64
import argparse
import json
from pathlib import Path
import subprocess
import tempfile
import time
import urllib.error
import urllib.request

KEYS = [Path('/etc/openbao/keys') / name for name in
        ('operator1.asc', 'operator2.asc', 'operator3.asc', 'root-secops.asc')]
URL = 'http://127.0.0.1:8200/v1/sys/init'
K = ['/usr/local/bin/k3s', 'kubectl', '--kubeconfig=/etc/vcloud-wsl/kubeconfig.yaml',
     '--context=vcloud-wsl-local', '--request-timeout=30s', '-n', 'platform-services']


def request(method, payload=None):
    data = None if payload is None else json.dumps(payload).encode()
    req = urllib.request.Request(URL, data=data, method=method, headers={'Content-Type': 'application/json'})
    # The permitted HTTP endpoint is loopback-only; never use an inherited proxy.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(req, timeout=30) as response:
        raw = response.read(1024 * 1024 + 1)
    if len(raw) > 1024 * 1024:
        raise ValueError('Oversized initialization response')
    return json.loads(raw)


def public_key(path, homedir):
    raw = path.read_bytes()
    if not raw or len(raw) > 1024 * 1024:
        raise ValueError('Invalid public key file size')
    command = ['gpg', '--batch', '--no-tty', '--homedir', str(homedir)]
    result = subprocess.run(command + ['--with-colons', '--import-options', 'show-only', '--dry-run', '--import'],
                            input=raw, capture_output=True, check=False)
    if result.returncode != 0:
        raise ValueError('Invalid PGP public key file')
    records = [line.split(':') for line in result.stdout.decode().splitlines()]
    if any(r[0] in ('sec', 'ssb') for r in records) or sum(r[0] == 'pub' for r in records) != 1:
        raise ValueError('Require one public key per recipient, never private keys')
    eligible = [r for r in records if r[0] in ('pub', 'sub') and 'e' in r[11].lower()
                and r[1] not in ('r', 'e', 'd') and (not r[6] or int(r[6]) > time.time())]
    if not eligible:
        raise ValueError('Public key has no usable encryption capability')
    fingerprints = [r[9] for r in records if r[0] == 'fpr']
    if not fingerprints:
        raise ValueError('Missing recipient fingerprint')
    imported = subprocess.run(command + ['--import'], input=raw, capture_output=True, check=False)
    if imported.returncode != 0:
        raise ValueError('Could not normalize public key')
    binary = subprocess.check_output(command + ['--export', fingerprints[0]], stderr=subprocess.DEVNULL)
    return fingerprints[0], base64.b64encode(binary).decode()


def packet_tags(ciphertext):
    """Check a complete OpenPGP packet stream, including an encrypted body."""
    data = base64.b64decode(ciphertext, validate=True)
    tags = []
    offset = 0
    while offset < len(data):
        head = data[offset]; offset += 1
        if not head & 0x80:
            raise ValueError('Initialization response is not OpenPGP ciphertext')
        if head & 0x40:
            tag = head & 0x3f
            if offset >= len(data):raise ValueError('Truncated OpenPGP length')
            length = data[offset]; offset += 1
            if 192 <= length < 224:
                if offset >= len(data):raise ValueError('Truncated OpenPGP length')
                length = ((length - 192) << 8) + data[offset] + 192; offset += 1
            elif length == 255:
                if offset+4 > len(data):raise ValueError('Truncated OpenPGP length')
                length = int.from_bytes(data[offset:offset+4], 'big'); offset += 4
            elif length >= 224:
                raise ValueError('Unsupported partial OpenPGP packet length')
        else:
            tag = (head >> 2) & 15
            count = (1, 2, 4, 0)[head & 3]
            if not count:
                raise ValueError('Indeterminate OpenPGP packet length')
            if offset+count > len(data):raise ValueError('Truncated OpenPGP length')
            length = int.from_bytes(data[offset:offset+count], 'big'); offset += count
        if not length or offset + length > len(data):
            raise ValueError('Truncated OpenPGP ciphertext')
        offset += length; tags.append(tag)
    if not tags or tags[0] != 1 or not any(t in (9, 18, 20) for t in tags) or any(t not in (1, 9, 18, 20) for t in tags):
        raise ValueError('Initialization output must be public-key encrypted')
    return tags


def initialize(keys=KEYS, api=request, run=subprocess.run,check_only=False):
    status = api('GET')
    if status.get('initialized') is True:
        print('OpenBao already initialized: initialization aborted; no state changed.')
        return 0
    if status.get('initialized') is not False:
        raise ValueError('Invalid initialization status response')
    if len(keys) != 4 or any(not p.is_file() for p in keys):
        print('ERROR: Initialization gated: Missing required PGP public key files.')
        return 3
    # GnuPG metadata/public-key keyring is created only on Linux tmpfs.
    with tempfile.TemporaryDirectory(prefix='vcloud-pgp-', dir='/dev/shm') as home:
        recipients = [public_key(p, Path(home)) for p in keys]
    if len({f for f, _ in recipients[:3]}) != 3:
        raise ValueError('Share recipients must be three distinct operators')
    # Fail BEFORE initialization if storage permissions are absent or an output
    # Secret already exists. Do not clobber previously encrypted custody data.
    encryption=run(['bash',str(Path(__file__).resolve().parents[1]/'lab/wsl/enable-secret-encryption.sh'),'--check'],capture_output=True,check=False)
    if encryption.returncode:raise ValueError('Kubernetes Secret encryption must be enabled before initialization')
    permitted = run(K + ['auth', 'can-i', 'create', 'secrets'], capture_output=True, check=False)
    if permitted.returncode or permitted.stdout.strip() != b'yes':
        raise ValueError('Cannot store encrypted initialization output')
    existing = run(K + ['get', 'secret', 'openbao-init-encrypted', '--ignore-not-found', '-o', 'name'],
                   capture_output=True, check=False)
    if existing.returncode or existing.stdout.strip():
        raise ValueError('Output Secret exists or cannot be checked; refusing initialization')
    if check_only:
        print('PASS: operator PGP and custody preflight valid; check-only mode issued no initialization POST.')
        return 0
    response = api('POST', {'secret_shares': 3, 'secret_threshold': 2,
                           'pgp_keys': [k for _, k in recipients[:3]], 'root_token_pgp_key': recipients[3][1]})
    shares = response.get('keys_base64', [])
    if len(shares) != 3 or response.get('secret_threshold') != 2 or response.get('secret_shares') != 3:
        raise ValueError('Initialization returned an unexpected share configuration')
    for encrypted in shares + [response.get('root_token', '')]:
        packet_tags(encrypted)
    # The legacy keys field duplicates encrypted shares; retain only validated
    # ciphertext and public custody metadata, never arbitrary response fields.
    encrypted = {'keys_base64': shares, 'root_token': response['root_token'],
                 'secret_shares': 3, 'secret_threshold': 2,
                 'recipient_fingerprints': [f for f, _ in recipients]}
    secret = {'apiVersion': 'v1', 'kind': 'Secret', 'type': 'Opaque', 'immutable': True,
              'metadata': {'name': 'openbao-init-encrypted', 'namespace': 'platform-services',
                           'labels': {'vcloud.io/custody': 'pgp-encrypted'}},
              'data': {'init.json': base64.b64encode(json.dumps(encrypted).encode()).decode()}}
    for attempt in range(3):
        saved = run(K + ['create', '-f', '-'], input=json.dumps(secret).encode(), capture_output=True, check=False)
        if saved.returncode == 0:
            print('PASS: PGP-encrypted 3-share/2-threshold output stored in Secret/openbao-init-encrypted.')
            return 0
        # The API may have created it before the connection was lost. Verify
        # this exact encrypted payload in memory; never retry initialization.
        observed=run(K+['get','secret','openbao-init-encrypted','--ignore-not-found','-o','json'],
                     capture_output=True,check=False)
        if observed.returncode==0 and observed.stdout.strip():
            try:stored=json.loads(observed.stdout)
            except (ValueError,TypeError):stored={}
            if stored.get('data')==secret['data'] and stored.get('immutable') is True:
                print('PASS: verified PGP-encrypted output custody after an uncertain create response.')
                return 0
        time.sleep(1)
    # Never print the HTTP response, credentials or kubectl stderr on failure.
    raise RuntimeError('Initialization succeeded but encrypted output storage failed; operator recovery required')


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check-only',action='store_true',help='Validate gates without initialization or Secret creation')
    args=parser.parse_args()
    try:
        raise SystemExit(initialize(check_only=args.check_only))
    except (ValueError, RuntimeError, OSError, urllib.error.URLError, subprocess.SubprocessError):
        print('ERROR: Initialization gated or failed validation; no credentials printed.')
        raise SystemExit(1)
