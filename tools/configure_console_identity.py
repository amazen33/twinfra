#!/usr/bin/env python3
"""Provision only the dedicated console client/roles and approved realm account.

Private API inputs/outputs remain in process memory; Kubernetes private writes
use stdin and captured output. No passwords/tokens are printed, stored on the
host, passed in argv/env, or written to Git. Secret encryption must pass first.
Existing user/client credentials are preserved; never reset a working account.
"""
import argparse
import base64
import copy
import json
import os
from pathlib import Path
import secrets
import subprocess
import urllib.parse

from wsl_keycloak_admin import API, ADMIN, ADMIN_SECRET, credential, k, obj
from vcloud_console import profile

ROOT = Path(__file__).resolve().parents[1]
OWNER = {'vcloud.io/component': 'vcloud-console-identity'}
USER_SECRET = 'vcloud-wsl-console-admin'


def private_secret(name, values=None):
    raw = k(['get', 'secret', name, '--ignore-not-found', '-o', 'json'])
    if raw.strip():
        value = json.loads(raw)
        if not all(value.get('metadata', {}).get('labels', {}).get(key) == val for key, val in OWNER.items()):
            raise ValueError('Refusing an unowned console Secret')
        return {key: base64.b64decode(v, validate=True).decode() for key, v in value.get('data', {}).items()}
    if values is None: return None
    value = {'apiVersion': 'v1', 'kind': 'Secret', 'type': 'Opaque', 'metadata': {
        'name': name, 'namespace': 'platform-services', 'labels': OWNER},
        'data': {key: base64.b64encode(v.encode()).decode() for key, v in values.items()}}
    k(['create', '-f', '-'], json.dumps(value).encode())
    return values


def client_spec():
    p = profile()
    return {'clientId': p['client'], 'name': 'vCloud control plane', 'enabled': True, 'protocol': 'openid-connect',
        'publicClient': False, 'standardFlowEnabled': True, 'implicitFlowEnabled': False,
        'directAccessGrantsEnabled': False, 'serviceAccountsEnabled': False, 'fullScopeAllowed': False,
        'redirectUris': [p['origin'] + '/console/callback'], 'webOrigins': [p['origin']],
        'attributes': {'pkce.code.challenge.method': 'S256', 'post.logout.redirect.uris': p['origin'] + '/console/'},
        'protocolMappers': [
            {'name': 'console-audience', 'protocol': 'openid-connect', 'protocolMapper': 'oidc-audience-mapper',
             'config': {'included.client.audience': p['client'], 'id.token.claim': 'true', 'access.token.claim': 'true'}},
            {'name': 'console-roles', 'protocol': 'openid-connect', 'protocolMapper': 'oidc-usermodel-client-role-mapper',
             'config': {'usermodel.clientRoleMapping.clientId': p['client'], 'claim.name': 'resource_access.' + p['client'] + '.roles',
                        'jsonType.label': 'String', 'multivalued': 'true', 'id.token.claim': 'true', 'access.token.claim': 'true'}},
            {'name': 'console-username', 'protocol': 'openid-connect', 'protocolMapper': 'oidc-usermodel-property-mapper',
             'config': {'user.attribute': 'username', 'claim.name': 'preferred_username', 'jsonType.label': 'String',
                        'id.token.claim': 'true', 'access.token.claim': 'true'}}]}


def guard():
    if os.geteuid() != 0 or 'microsoft' not in os.uname().release or not Path('/var/lib/vcloud-wsl/owner.json').is_file():
        raise ValueError('Owned root WSL lab required')
    nodes = obj(['get', 'nodes', '-o', 'json'])['items']
    if len(nodes) != 1 or nodes[0]['metadata']['name'] != 'vcloud-wsl-local': raise ValueError('Unexpected cluster')
    result = subprocess.run(['bash', str(ROOT / 'lab/wsl/enable-secret-encryption.sh'), '--check'], capture_output=True)
    if result.returncode: raise ValueError('Verified stable Kubernetes Secret encryption required')


def configure(create_admin=False):
    guard(); p = profile(); api = API()
    token = api.login(ADMIN, credential(obj(['get', 'secret', ADMIN_SECRET, '-o', 'json']), ADMIN))
    base = '/admin/realms/vcloud'
    request = lambda path, **kwargs: api.request(base + path, token, **kwargs)
    request('')  # Realm must already exist; do not import/reset identity state.
    matches = request('/clients?clientId=' + p['client'])
    expected = client_spec()
    if not matches:
        request('/clients', value=expected, method='POST')
        matches = request('/clients?clientId=' + p['client'])
    if len(matches) != 1: raise ValueError('Ambiguous console client')
    cid = matches[0]['id']; prefix = '/clients/' + cid
    # This dedicated client is owned by this module. Preserve its private secret.
    current = request(prefix)
    if current.get('name') not in ('vCloud control plane', 'vCloud local console'): raise ValueError('Refusing an unowned client')
    updated = copy.deepcopy(current); updated.update(expected)
    request(prefix, value=updated, method='PUT')
    roles = request(prefix + '/roles')
    for role in p['roles']:
        if not any(r['name'] == role for r in roles): request(prefix + '/roles', value={'name': role, 'description': 'Read-only vCloud portal access'}, method='POST')
    roles = [r for r in request(prefix + '/roles') if r['name'] in p['roles']]
    request(prefix + '/scope-mappings/clients/' + cid, value=roles, method='POST')
    client_secret = request(prefix + '/client-secret')['value']
    existing = private_secret(p['secret'])
    if existing is not None and existing.get('client_secret') != client_secret:
        raise ValueError('Existing OIDC Secret differs; credential rotation needs a separate operation')
    private_secret(p['secret'], {'client_secret': client_secret, 'session.secret': secrets.token_urlsafe(48)})
    if create_admin:
        users = request('/users?username=vcloud-admin&exact=true')
        stored = private_secret(USER_SECRET)
        if users and stored is None: raise ValueError('Existing realm user has no owned credential reference; refusing adoption/reset')
        if not users:
            values = stored or private_secret(USER_SECRET, {'admin-user': 'vcloud-admin', 'admin-password': secrets.token_urlsafe(48), 'realm': 'vcloud'})
            if values.get('admin-user') != 'vcloud-admin' or values.get('realm') != 'vcloud': raise ValueError('Invalid realm credential reference')
            required = [r['alias'] for r in request('/authentication/required-actions') if r.get('enabled') and r.get('defaultAction')]
            request('/users', method='POST', value={'username': 'vcloud-admin', 'enabled': True, 'requiredActions': sorted(set(required + ['UPDATE_PASSWORD'])),
                'credentials': [{'type': 'password', 'value': values['admin-password'], 'temporary': True}]})
            users = request('/users?username=vcloud-admin&exact=true')
        if len(users) != 1: raise ValueError('Ambiguous console realm user')
        account = request('/users/' + users[0]['id'])
        credentials = request('/users/' + users[0]['id'] + '/credentials')
        if not any(c.get('type') == 'otp' for c in credentials) and 'CONFIGURE_TOTP' not in account.get('requiredActions', []):
            # Retain the existing realm's mandatory new-user MFA policy.
            account['requiredActions'] = sorted(set(account.get('requiredActions', []) + ['CONFIGURE_TOTP']))
            request('/users/' + users[0]['id'], method='PUT', value=account)
        admin_role = next(r for r in roles if r['name'] == 'console.admin')
        request('/users/' + users[0]['id'] + '/role-mappings/clients/' + cid, method='POST', value=[admin_role])
    # Public validation only. Never print the client object (it includes a secret).
    print('PASS: confidential PKCE console client, exact callback, audience, isolated roles; private Secret references persisted')
    if create_admin: print('PASS: vcloud/vcloud-admin -> console.admin; temporary password change required on first login')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--create-admin', action='store_true')
    parser.add_argument('--render-client', type=Path)
    args = parser.parse_args()
    try:
        if args.render_client:
            args.render_client.write_text(json.dumps(client_spec(), indent=2) + '\n')
        else: configure(args.create_admin)
    except Exception:
        # HTTP errors could contain private OAuth responses. Never print them.
        print('FAIL: console identity provisioning failed; private output withheld', flush=True)
        raise SystemExit(1)
