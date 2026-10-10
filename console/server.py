#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Read-only console BFF. Only the authenticated APISIX identity boundary may reach it.

The gateway validates signed OIDC tokens, scrubs spoofed identity headers, and
enforces console roles. Cilium admits only APISIX. This server repeats claim/RBAC
checks after independently verifying the signed access token against Keycloak JWKS.
No token, cookie, password, query string or upstream response is logged.
"""
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import math
import mimetypes
import os
from pathlib import Path
import re
import ssl
import threading
import time
from urllib.parse import parse_qs, quote, urlsplit
import urllib.request
import xml.etree.ElementTree as ET

import jwt

from aws_views import read, signed_request, xml_values

NS = os.environ.get('PLATFORM_NAMESPACE', 'platform-services')
ISSUER = os.environ.get('OIDC_ISSUER', 'https://localhost:18443/realms/vcloud')
CLIENT = os.environ.get('OIDC_CLIENT', 'vcloud-console')
ROLES = {'console.viewer', 'console.admin'}
STATIC = Path(os.environ.get('VCLOUD_STATIC', '/app/public'))
SA = Path(os.environ.get('PLATFORM_SERVICE_ACCOUNT_PATH', '/var/run/secrets/vcloud'))
MAX_BYTES = 1024 * 1024
JWKS_URL = os.environ.get('OIDC_JWKS_URL', 'https://keycloak.platform-services.svc.cluster.local/realms/vcloud/protocol/openid-connect/certs')
OIDC_CA = Path('/oidc-trust/tls.crt')
ALGORITHMS = {'RS256': 'RSA', 'ES256': 'EC'}
LEEWAY = 30  # Seconds, never more than the work order's 60-second limit.


class Unauthorized(ValueError): pass
class Forbidden(ValueError): pass


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args): return None


def fetch_jwks():
    # Fixed private TLS endpoint: never follow token-provided jku/x5u or redirects.
    context = ssl.create_default_context(cafile=str(OIDC_CA))
    opener = urllib.request.build_opener(NoRedirect(), urllib.request.HTTPSHandler(context=context))
    with opener.open(JWKS_URL, timeout=4) as response:
        raw = response.read(65537)
    if len(raw) > 65536: raise ValueError('Bounded JWKS response exceeded')
    return json.loads(raw)


class JWKSCache:
    """Thread-safe, five-minute key cache; all fetch attempts have a 60s cooldown.

    Unknown kids can request a refresh after the cooldown, including during key
    rotation. Failed fetches also consume the cooldown and never renew stale keys.
    """
    def __init__(self, fetch=None, clock=None):
        self.fetch = fetch or fetch_jwks
        self.clock = clock or time.monotonic
        self.keys = {}
        self.fetched_at = float('-inf')
        self.attempted_at = float('-inf')
        self.lock = threading.Lock()

    def key(self, kid, algorithm):
        with self.lock:
            now = self.clock()
            fresh = now - self.fetched_at < 300
            if (not fresh or kid not in self.keys) and now - self.attempted_at >= 60:
                self.attempted_at = now
                value = self.fetch()
                keys = value.get('keys') if isinstance(value, dict) else None
                if not isinstance(keys, list) or not 1 <= len(keys) <= 64:
                    raise ValueError('Invalid JWKS')
                accepted = {}
                for key in keys:
                    if not isinstance(key, dict): raise ValueError('Invalid JWK')
                    key_id = key.get('kid')
                    if not isinstance(key_id, str) or not 1 <= len(key_id) <= 256:
                        raise ValueError('Invalid key ID')
                    if key_id in accepted: raise ValueError('Ambiguous key ID')
                    accepted[key_id] = key
                self.keys, self.fetched_at = accepted, now
                fresh = True
            if not fresh or kid not in self.keys: raise ValueError('Unknown or stale key')
            key = self.keys[kid]
            if (key.get('kty') != ALGORITHMS[algorithm] or key.get('alg', algorithm) != algorithm
                    or key.get('use', 'sig') != 'sig' or 'd' in key
                    or ('key_ops' in key and key['key_ops'] != ['verify'])
                    or (algorithm == 'ES256' and key.get('crv') != 'P-256')):
                raise ValueError('Incompatible signing key')
            return jwt.PyJWK.from_dict(key, algorithm=algorithm).key


JWKS = JWKSCache()


def identity(header):
    try:
        if not isinstance(header, str) or len(header) > 32768 or not re.fullmatch(r'[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+', header):
            raise ValueError('Malformed or missing token')
        untrusted = jwt.get_unverified_header(header)
        algorithm, kid = untrusted.get('alg'), untrusted.get('kid')
        if (algorithm not in ALGORITHMS or not isinstance(kid, str) or not 1 <= len(kid) <= 256
                or untrusted.get('crit') or untrusted.get('b64') is False):
            raise ValueError('Unsupported signing header')
        claims = jwt.decode(header, JWKS.key(kid, algorithm), algorithms=[algorithm],
            issuer=ISSUER, leeway=LEEWAY, options={'require': ['iss', 'exp', 'sub'], 'verify_aud': False})
        audience = claims.get('aud', [])
        if isinstance(audience, str): audience = [audience]
        if not isinstance(audience, list) or not all(isinstance(v, str) for v in audience):
            raise ValueError('Malformed audience')
        if CLIENT not in audience and claims.get('azp') != CLIENT:
            raise ValueError('Wrong client')
        # Reject non-finite/coerced NumericDates, not just expired/future values.
        for name in ('exp', 'nbf'):
            if name in claims and (type(claims[name]) not in (int, float) or not math.isfinite(claims[name])):
                raise ValueError('Invalid time claim')
    except Exception:
        # Library/network/TLS errors are fail-closed and never expose token data.
        raise Unauthorized('Invalid gateway session') from None
    access = claims.get('resource_access', {})
    client = access.get(CLIENT, {}) if isinstance(access, dict) else {}
    roles = client.get('roles', []) if isinstance(client, dict) else []
    roles = {r for r in roles if isinstance(r, str)} if isinstance(roles, list) else set()
    if not ROLES.intersection(roles): raise Forbidden('Console role required')
    return {'username': str(claims.get('preferred_username') or claims['sub'])[:128],
            'roles': sorted(ROLES.intersection(roles)), 'issuer': ISSUER,
            'client': CLIENT, 'adminUrl': os.environ.get('KEYCLOAK_ADMIN_URL','https://localhost:18443/admin/')}


def kube(path):
    # Paths are fixed in api_response; neither URL nor namespace is user-controlled.
    host = os.environ.get('KUBERNETES_SERVICE_HOST', '')
    port = os.environ.get('KUBERNETES_SERVICE_PORT_HTTPS', '443')
    context = ssl.create_default_context(cafile=str(SA / 'ca.crt'))
    request = urllib.request.Request(f'https://{host}:{port}' + path,
        headers={'Authorization': 'Bearer ' + (SA / 'token').read_text().strip()})
    opener = urllib.request.build_opener(NoRedirect(), urllib.request.HTTPSHandler(context=context))
    with opener.open(request, timeout=4) as response:
        raw = response.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES: raise ValueError('Bounded response exceeded')
    return json.loads(raw)


def valid_query(query):
    if set(query) - {'backend', 'bucket', 'table'} or any(len(values) != 1 for values in query.values()):
        raise ValueError('Invalid query')
    backend = query.get('backend', [os.environ.get('PLATFORM_DEFAULT_BACKEND','localstack')])[0]
    if backend not in os.environ.get('PLATFORM_BACKENDS','localstack,ministack').split(','): raise ValueError('Unsupported backend')
    for name in ('bucket', 'table'):
        value = query.get(name, [''])[0]
        if len(value) > 255 or '/' in value or '..' in value or any(ord(c) < 32 for c in value):
            raise ValueError('Invalid resource')
    return backend


def api_response(view, query, user):
    if view == 'identity': return dict(user, environment=os.environ.get('PLATFORM_ENVIRONMENT','dev'), region=os.environ.get('PLATFORM_REGION',''), backends=os.environ.get('PLATFORM_BACKENDS','localstack,ministack').split(','))
    if view == 'overview':
        pods = kube('/api/v1/namespaces/' + NS + '/pods')['items']
        # Finished diagnostic jobs do not indicate unhealthy platform services.
        active = [p for p in pods if p.get('status', {}).get('phase') not in ('Succeeded', 'Failed')]
        deployments = kube('/apis/apps/v1/namespaces/' + NS + '/deployments')['items']
        desired = [d for d in deployments if d['spec'].get('replicas', 1) > 0]
        return {'namespace': NS, 'pods': len(active), 'ready': sum(any(c['type'] == 'Ready' and c['status'] == 'True'
            for c in p.get('status', {}).get('conditions', [])) for p in active),
            'deployments': len(desired), 'healthyDeployments': sum(d.get('status', {}).get('availableReplicas', 0) >= d['spec'].get('replicas', 1) for d in desired),
            'checkedAt': datetime.now(timezone.utc).isoformat()}
    if view == 'gitops':
        apps = kube('/apis/argoproj.io/v1alpha1/namespaces/' + NS + '/applications')['items']
        return [{'name': a['metadata']['name'], 'sync': a.get('status', {}).get('sync', {}).get('status', 'Unknown'),
            'health': a.get('status', {}).get('health', {}).get('status', 'Unknown'),
            'revision': a.get('status', {}).get('sync', {}).get('revision', ''),
            'message': a.get('status', {}).get('health', {}).get('message', '')[:512]} for a in apps]
    backend = valid_query(query)
    if view == 'storage':
        bucket = query.get('bucket', [''])[0]
        if bucket:
            raw = read(signed_request(backend, 's3', path='/' + bucket, query={'list-type': '2', 'max-keys': '100'}))
            return {'backend': backend, 'bucket': bucket, 'buckets': [], 'objects': xml_values(raw, 'Key')[:100]}
        return {'backend': backend, 'bucket': '', 'buckets': xml_values(read(signed_request(backend, 's3')), 'Name')[:100], 'objects': []}
    if view == 'dynamodb':
        table = query.get('table', [''])[0]
        value = json.loads(read(signed_request(backend, 'dynamodb', 'POST',
            payload=json.dumps({'TableName': table} if table else {'Limit': 100}).encode(),
            target='DynamoDB_20120810.' + ('DescribeTable' if table else 'ListTables'))))
        return {'backend': backend, 'tables': value.get('TableNames', [])[:100], 'metadata': value.get('Table') if table else None}
    if view == 'cloud':
        # Fixed health endpoint. No client-chosen path/URL or credentials.
        from aws_views import ENDPOINTS
        request = urllib.request.Request(ENDPOINTS[backend] + '/_' + backend + '/health')
        health = json.loads(read(request)).get('services', {})
        raw = read(signed_request(backend, 'ec2', 'POST', payload=b'Action=DescribeInstances&Version=2016-11-15'))
        if b'<!DOCTYPE' in raw.upper() or b'<!ENTITY' in raw.upper(): raise ValueError('Invalid XML')
        root = ET.fromstring(raw)
        instances = []
        for el in root.iter():
            if el.tag.rsplit('}', 1)[-1] != 'instancesSet': continue
            for item in el:
                pick = lambda tag: next((n.text or '' for n in item.iter() if n.tag.rsplit('}', 1)[-1] == tag), '')
                instances.append({'id': pick('instanceId'), 'type': pick('instanceType'), 'state': pick('name')})
        return {'backend': backend, 'services': {s: health.get(s, 'unknown') for s in ('s3', 'ec2', 'iam', 'dynamodb')},
                'instances': instances[:100], 'ephemeral': True}
    raise KeyError('Unknown view')


class Handler(BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'
    def log_message(self, *args): pass
    def respond(self, status, body, content='application/json'):
        self.send_response(status)
        self.send_header('Content-Type', content)
        self.send_header('Content-Length', str(len(body)))
        if self.close_connection: self.send_header('Connection', 'close')
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Frame-Options', 'SAMEORIGIN')
        self.send_header('Content-Security-Policy', "default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'self'; base-uri 'self'; form-action 'self'")
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Referrer-Policy', 'same-origin')
        self.end_headers()
        self.wfile.write(body)
    def do_GET(self):
        try:
            url = urlsplit(self.path)
            if url.path == '/healthz':
                self.respond(200, b'{"status":"running"}'); return
            headers = self.headers.get_all('X-Access-Token', [])
            if len(headers) != 1: raise Unauthorized('Missing or ambiguous token')
            user = identity(headers[0])
            if url.path.startswith('/console/api/'):
                view = url.path.removeprefix('/console/api/')
                query = parse_qs(url.query, max_num_fields=4, strict_parsing=True)
                self.respond(200, json.dumps(api_response(view, query, user)).encode()); return
            if url.path.startswith('/console/assets/'):
                file = STATIC / url.path.removeprefix('/console/')
                if not file.resolve().is_relative_to(STATIC.resolve()) or not file.is_file(): raise KeyError('Unknown asset')
                self.respond(200, file.read_bytes(), mimetypes.guess_type(file.name)[0] or 'application/octet-stream'); return
            if url.path in ('/console', '/console/') or url.path in ['/console/' + x for x in ('overview', 'storage', 'localstack', 'dynamodb', 'gitops', 'iam')]:
                self.respond(200, (STATIC / 'index.html').read_bytes(), 'text/html; charset=utf-8'); return
            raise KeyError('Unknown path')
        except Unauthorized: self.respond(401, b'{"error":"Session required"}')
        except Forbidden: self.respond(403, b'{"error":"Console role required"}')
        except KeyError: self.respond(404, b'{"error":"Not found"}')
        except ValueError: self.respond(400, b'{"error":"Invalid request"}')
        except Exception: self.respond(503, b'{"error":"Backend unavailable"}')
    def do_POST(self):
        # Do not reuse a connection with an unread rejected request body.
        self.close_connection = True
        self.respond(405, b'{"error":"Read-only API"}')
    do_PUT = do_POST
    do_PATCH = do_POST
    do_DELETE = do_POST


if __name__ == '__main__':
    ThreadingHTTPServer(('0.0.0.0', int(os.environ.get('PORT', '3000'))), Handler).serve_forever()
