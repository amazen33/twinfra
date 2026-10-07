#!/usr/bin/env python3
"""Create the first lab administrator without credential argv/env/host files.

The offline recovery CLI receives its password through an echo-disabled Pod
terminal. Only encrypted Kubernetes Secrets retain initial credentials. A
temporary recovery account is removed after the permanent account is verified.
"""
import argparse
import base64
import copy
import json
import os
from pathlib import Path
import secrets
import ssl
import subprocess
import time
import re
import urllib.parse
import urllib.request
import urllib.error
import uuid

from wsl_endpoints import check, image, identity

ROOT = Path(__file__).resolve().parents[1]
NS = 'platform-services'
APP = 'vcloud-wsl-endpoints'
ADMIN = 'vcloud-admin'
RECOVERY = 'vcloud-bootstrap-admin'
ADMIN_SECRET = 'vcloud-wsl-keycloak-admin'
RECOVERY_SECRET = 'vcloud-wsl-keycloak-recovery'
POD = 'vcloud-keycloak-admin-bootstrap'
OWNER = {'vcloud.io/component': 'keycloak-admin-bootstrap'}
SKIP = 'argocd.argoproj.io/skip-reconcile'
K = ['/usr/local/bin/k3s', 'kubectl', '--kubeconfig=/etc/vcloud-wsl/kubeconfig.yaml',
     '--context=vcloud-wsl-local', '--request-timeout=30s', '-n', NS]
BASE = 'https://localhost:18443'


def k(args, payload=None, timeout=65):
    result = subprocess.run(K + args, input=payload, capture_output=True, timeout=timeout)
    if result.returncode:
        raise RuntimeError('Kubernetes ' + args[0] + ' failed; private output withheld')
    return result.stdout


def obj(args):
    return json.loads(k(args))


def patch(kind, name, payload):
    # Patches contain only public control state, never credential values.
    return k(['patch', kind, name, '--type=merge', '-p', json.dumps(payload)])


def credential(value, username):
    if not all(value.get('metadata', {}).get('labels', {}).get(key) == val for key, val in OWNER.items()):
        raise ValueError('Refusing an unowned administrator Secret')
    data = value.get('data', {})
    user = base64.b64decode(data['admin-user'], validate=True).decode()
    password = base64.b64decode(data['admin-password'], validate=True).decode()
    if user != username or len(password) < 32 or any(c in password for c in '\r\n\x00'):
        raise ValueError('Invalid administrator credential reference')
    return password


def secret(name, username):
    raw = k(['get', 'secret', name, '--ignore-not-found', '-o', 'json'])
    if raw.strip():
        return credential(json.loads(raw), username)
    password = secrets.token_urlsafe(48)
    value = {'apiVersion': 'v1', 'kind': 'Secret', 'type': 'Opaque',
             'metadata': {'name': name, 'namespace': NS, 'labels': OWNER},
             'data': {key: base64.b64encode(text.encode()).decode() for key, text in
                      {'admin-user': username, 'admin-password': password}.items()}}
    k(['create', '-f', '-'], json.dumps(value).encode())
    return password


def bootstrap_pod(deployment, run_id):
    spec = copy.deepcopy(deployment['spec']['template']['spec'])
    if len(spec['containers']) != 1 or spec['containers'][0]['name'] != 'keycloak':
        raise ValueError('Expected the single owned Keycloak container')
    if spec['containers'][0]['image'] != image('keycloak'):
        raise ValueError('Keycloak image must match the immutable lab lock')
    c = spec['containers'][0]
    for key in ('livenessProbe', 'startupProbe', 'readinessProbe', 'ports', 'env', 'envFrom'):
        c.pop(key, None)
    c['command'] = ['sh', '-ec']
    c['args'] = ["stty -echo; printf 'VCLOUD_PRIVATE_INPUT_READY\\n'; exec /opt/keycloak/bin/kc.sh --config-file=/runtime/keycloak.conf "
                 'bootstrap-admin user --username ' + RECOVERY]
    c['stdin'] = True
    c['tty'] = True
    # Never advertise the offline CLI as a Ready HTTPS Service endpoint.
    c['readinessProbe'] = {'exec': {'command': ['sh', '-c', 'exit 1']}, 'periodSeconds': 5}
    spec['restartPolicy'] = 'Never'
    spec['activeDeadlineSeconds'] = 240
    spec['automountServiceAccountToken'] = False
    value = {'apiVersion': 'v1', 'kind': 'Pod', 'metadata': {'name': POD, 'namespace': NS,
        'labels': {**OWNER, 'app.kubernetes.io/name': 'keycloak', 'vcloud.io/test-run': run_id}}, 'spec': spec}
    check([value])
    return value


def master_users():
    primary = obj(['get', 'cluster', 'vcloud-wsl-postgres', '-o', 'json'])['status']['currentPrimary']
    sql = "SELECT username FROM user_entity u JOIN realm r ON r.id=u.realm_id WHERE r.name='master';"
    output = k(['exec', '-i', primary, '-c', 'postgres', '--', 'psql', '-X', '-U', 'postgres',
                '-d', 'keycloak', '-tA', '-v', 'ON_ERROR_STOP=1'], sql.encode())
    return set(output.decode().split())


def private_input(password):
    """Attach using a real local terminal; retain no transcript or secret argv."""
    import pty
    import select
    import termios
    master, slave = pty.openpty()
    attributes = termios.tcgetattr(slave)
    attributes[3] &= ~termios.ECHO
    termios.tcsetattr(slave, termios.TCSANOW, attributes)
    process = subprocess.Popen(K + ['attach', '-i', '-t', '--quiet', POD, '-c', 'keycloak'],
                               stdin=slave, stdout=slave, stderr=slave, start_new_session=True)
    os.close(slave)
    try:
        time.sleep(1)
        os.write(master, (password + '\n' + password + '\n').encode())
        deadline = time.monotonic() + 200
        size = 0
        while process.poll() is None:
            if time.monotonic() > deadline:
                raise RuntimeError('Private terminal attachment timed out')
            if select.select([master], [], [], 1)[0]:
                try:
                    size += len(os.read(master, 65536))
                except OSError:
                    break
                if size > 2 * 1024 * 1024:
                    raise RuntimeError('Private terminal output limit exceeded')
        process.wait(timeout=10)
        if process.returncode:
            raise RuntimeError('Private terminal attachment failed')
    finally:
        if process.poll() is None:
            process.kill()
            process.wait()
        os.close(master)


def offline(deployment, password):
    app = obj(['get', 'application', APP, '-o', 'json'])
    previous = app['metadata'].get('annotations', {}).get(SKIP)
    if previous == 'true' or app.get('status', {}).get('operationState', {}).get('phase') == 'Running':
        raise ValueError('Refusing an already paused or actively syncing Application')
    if deployment['spec']['replicas'] != 1:
        raise ValueError('Only the single-replica WSL Keycloak is supported')
    run_id = uuid.uuid4().hex
    pod = bootstrap_pod(deployment, run_id)
    k(['create', '--dry-run=server', '-f', '-'], json.dumps(pod).encode())
    uid = None
    stage = 'pause'
    patch('application', APP, {'metadata': {'annotations': {SKIP: 'true'}}})
    try:
        time.sleep(5)
        if obj(['get', 'application', APP, '-o', 'json']).get('status', {}).get('operationState', {}).get('phase') == 'Running':
            raise ValueError('Application sync is still active')
        stage = 'stop server'
        patch('deployment', 'keycloak', {'spec': {'replicas': 0}})
        for _ in range(45):
            if not obj(['get', 'pods', '-l', 'app.kubernetes.io/name=keycloak', '-o', 'json'])['items']:
                break
            time.sleep(2)
        else:
            raise RuntimeError('Keycloak did not stop; offline command was not started')
        stage = 'start offline Pod'
        uid = json.loads(k(['create', '-f', '-', '-o', 'json'], json.dumps(pod).encode()))['metadata']['uid']
        for _ in range(90):
            value = obj(['get', 'pod', POD, '-o', 'json'])
            states = value.get('status', {}).get('containerStatuses', [])
            if any('running' in s.get('state', {}) for s in states) and b'VCLOUD_PRIVATE_INPUT_READY' in k(['logs', POD, '-c', 'keycloak']):
                break
            if value.get('status', {}).get('phase') in ('Failed', 'Succeeded'):
                raise RuntimeError('Offline recovery terminated before its private input')
            time.sleep(1)
        else:
            raise RuntimeError('Offline recovery Pod failed to start')
        # The Pod PTY has echo disabled for its entire lifetime. Password input
        # is only an in-memory stdin pipe, never a command argument or env var.
        stage = 'private terminal input'
        private_input(password)
        stage = 'offline completion'
        for _ in range(15):
            value = obj(['get', 'pod', POD, '-o', 'json'])
            if value.get('status', {}).get('phase') == 'Succeeded':
                break
            if value.get('status', {}).get('phase') == 'Failed':
                raise RuntimeError('Offline recovery failed; output withheld')
            time.sleep(1)
        else:
            raise RuntimeError('Offline recovery did not complete')
    except Exception as error:
        print('Offline recovery stopped during: ' + stage + ' (' + type(error).__name__ + '; private output withheld)', flush=True)
        if uid:
            logs = k(['logs', POD, '-c', 'keycloak'])
            patterns = {'missing_terminal_tool': rb'stty.*not found', 'no_console': rb'(?i)console.*(not|unavailable)',
                        'database_connection': rb'(?i)(JDBC|connection refused)', 'password_confirmation': rb'(?i)password.*match',
                        'unsupported_option': rb'(?i)(unknown option|unmatched argument)', 'missing_password': rb'(?i)password.*(missing|not specified)'}
            print('Public failure classifications: ' + ', '.join(name for name, pattern in patterns.items() if re.search(pattern, logs)), flush=True)
            state = obj(['get', 'pod', POD, '-o', 'json']).get('status', {})
            print('Offline Pod phase: ' + state.get('phase', 'unknown') + '; prompt count: ' + str(logs.lower().count(b'password')), flush=True)
        raise
    finally:
        # Delete only this invocation's Pod, restore the replica, then reconcile.
        try:
            if uid:
                raw = k(['get', 'pod', POD, '--ignore-not-found', '-o', 'json'])
                if raw.strip() and json.loads(raw)['metadata']['uid'] == uid:
                    k(['delete', 'pod', POD, '--wait=true', '--timeout=45s'])
        finally:
            try:
                patch('deployment', 'keycloak', {'spec': {'replicas': 1}})
                k(['rollout', 'status', 'deployment/keycloak', '--timeout=300s'], timeout=320)
            finally:
                patch('application', APP, {'metadata': {'annotations': {SKIP: previous}}})
                # Existing helper refuses foreign listeners and binds loopback.
                result = subprocess.run(['bash', str(ROOT / 'lab/wsl/endpoints/access.sh'), 'start'], capture_output=True, timeout=90)
                if result.returncode:
                    raise RuntimeError('Keycloak access restoration failed; output withheld')


class API:
    def __init__(self):
        # Fetch only public certificate data, never the Secret's private key.
        public = k(['get', 'secret', 'vcloud-wsl-keycloak-tls', '-o', 'jsonpath={.data.tls\\.crt}'])
        self.context = ssl.create_default_context(cadata=base64.b64decode(public).decode())

    def request(self, path, token=None, value=None, method='GET', form=None):
        if not path.startswith('/') or path.startswith('//'):
            raise ValueError('Only fixed local Keycloak API paths are allowed')
        headers = {}
        body = None
        if token:
            headers['Authorization'] = 'Bearer ' + token
        if form is not None:
            body = urllib.parse.urlencode(form).encode()
            headers['Content-Type'] = 'application/x-www-form-urlencoded'
        elif value is not None:
            body = json.dumps(value).encode()
            headers['Content-Type'] = 'application/json'
        request = urllib.request.Request(BASE + path, data=body, headers=headers, method=method)
        # No cross-origin redirect may receive a password or bearer token.
        class NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, *args):
                return None
        opener = urllib.request.build_opener(NoRedirect(), urllib.request.HTTPSHandler(context=self.context))
        with opener.open(request, timeout=15) as response:
            raw = response.read(1024 * 1024 + 1)
            if len(raw) > 1024 * 1024:
                raise ValueError('Oversized Keycloak response')
            return json.loads(raw) if raw else None

    def login(self, username, password):
        return self.request('/realms/master/protocol/openid-connect/token', method='POST', form={
            'grant_type': 'password', 'client_id': 'admin-cli', 'username': username, 'password': password})['access_token']


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--check', action='store_true', help='Read-only preflight; create no credential or account')
    mode.add_argument('--render-pod', type=Path, help='Offline public Pod fixture for schema/policy validation')
    args = parser.parse_args()
    if args.render_pod:
        deployment = next(o for o in identity() if o['kind'] == 'Deployment' and o['metadata']['name'] == 'keycloak')
        args.render_pod.parent.mkdir(parents=True, exist_ok=True)
        args.render_pod.write_text(json.dumps(bootstrap_pod(deployment, 'schema-fixture'), indent=2) + '\n', encoding='utf-8')
        return
    if os.geteuid() != 0 or 'microsoft' not in os.uname().release or not Path('/var/lib/vcloud-wsl/owner.json').is_file():
        raise ValueError('Owned root WSL lab required')
    nodes = obj(['get', 'nodes', '-o', 'json'])['items']
    if len(nodes) != 1 or nodes[0]['metadata']['name'] != 'vcloud-wsl-local':
        raise ValueError('Unexpected Kubernetes cluster')
    result = subprocess.run(['bash', str(ROOT / 'lab/wsl/enable-secret-encryption.sh'), '--check'], capture_output=True)
    if result.returncode:
        raise ValueError('Verified stable Secret encryption at rest is required')
    ns = obj(['get', 'namespace', NS, '-o', 'json'])['metadata']['labels']
    if ns.get('pod-security.kubernetes.io/enforce') != 'restricted' or ns.get('pod-security.kubernetes.io/enforce-version') != 'v1.30':
        raise ValueError('Restricted:v1.30 admission is required')
    deployment = obj(['get', 'deployment', 'keycloak', '-o', 'json'])
    bootstrap_pod(deployment, 'preflight')
    if k(['get', 'pod', POD, '--ignore-not-found', '-o', 'name']).strip():
        raise ValueError('Refusing a pre-existing recovery Pod')
    users = master_users()
    if users - {ADMIN, RECOVERY}:
        raise ValueError('Existing master-realm accounts require operator review; no reset attempted')
    for username, name in ((ADMIN, ADMIN_SECRET), (RECOVERY, RECOVERY_SECRET)):
        if username in users:
            credential(obj(['get', 'secret', name, '-o', 'json']), username)
    print('PASS: owned cluster, restricted profile, encrypted Secrets and account preflight', flush=True)
    if args.check:
        return
    api = API()
    if ADMIN in users and RECOVERY not in users:
        raw = k(['get', 'secret', ADMIN_SECRET, '-o', 'json'])
        password = credential(json.loads(raw), ADMIN)
        token = api.login(ADMIN, password)
        api.request('/admin/realms/master', token)
        print('PASS: existing vcloud-admin login/administration verified; password preserved', flush=True)
        return
    password = secret(ADMIN_SECRET, ADMIN)
    recovery_password = secret(RECOVERY_SECRET, RECOVERY)
    if RECOVERY not in users:
        print('Creating temporary offline recovery account; Keycloak will briefly restart', flush=True)
        offline(deployment, recovery_password)
    for attempt in range(15):
        try:
            recovery_token = api.login(RECOVERY, recovery_password)
            break
        except (OSError, urllib.error.URLError):
            if attempt == 14:
                raise RuntimeError('Recovery login unavailable; credentials retained in encrypted Secrets') from None
            time.sleep(2)
    if ADMIN not in users:
        api.request('/admin/realms/master/users', recovery_token, method='POST', value={
            'username': ADMIN, 'firstName': 'vCloud', 'lastName': 'Lab Administrator', 'enabled': True,
            'credentials': [{'type': 'password', 'value': password, 'temporary': False}]})
    admin = api.request('/admin/realms/master/users?username=' + ADMIN + '&exact=true', recovery_token)
    if len(admin) != 1:
        raise RuntimeError('Permanent account lookup failed')
    role = api.request('/admin/realms/master/roles/admin', recovery_token)
    api.request('/admin/realms/master/users/' + admin[0]['id'] + '/role-mappings/realm', recovery_token,
                method='POST', value=[role])
    token = api.login(ADMIN, password)
    api.request('/admin/realms/master', token)
    recovery = api.request('/admin/realms/master/users?username=' + RECOVERY + '&exact=true', token)
    if len(recovery) != 1:
        raise RuntimeError('Temporary recovery account lookup failed')
    api.request('/admin/realms/master/users/' + recovery[0]['id'], token, method='DELETE')
    k(['delete', 'secret', RECOVERY_SECRET])
    print('PASS: vcloud-admin login and administration verified; recovery user/Secret removed', flush=True)
    print('Password: encrypted Secret/platform-services/' + ADMIN_SECRET + ' (values withheld)', flush=True)


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        # Credential-bearing HTTP/subprocess exception bodies are never printed.
        raise SystemExit('FAIL: Keycloak admin bootstrap did not pass (' + type(error).__name__ + '); private details withheld') from None
