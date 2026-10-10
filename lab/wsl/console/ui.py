#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Small read-only console views. No arbitrary endpoints, writes or real AWS keys."""
import hashlib
import hmac
from html import escape
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
from urllib.parse import parse_qs, quote, urlencode, urlsplit
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

ENDPOINTS = {
    'ministack': os.environ.get('MINISTACK_ENDPOINT','http://ministack.platform-services.svc.cluster.local:4566'),
}
MAX_RESPONSE = 1024 * 1024


def signed_request(backend, service, method='GET', path='/', query=None, payload=b'', target=None, now=None):
    """SigV4 is computed AFTER selecting the direct, fixed in-cluster endpoint.

    These literal test/test emulator credentials are public fixtures, never real
    AWS credentials. Container egress policy admits only the MiniStack Pod endpoint.
    """
    endpoint = ENDPOINTS[backend]  # no user-provided URL / SSRF
    host = urlsplit(endpoint).netloc
    path = '/' + quote(path.lstrip('/'), safe='/~')
    pairs = sorted((str(k), str(v)) for k, v in (query or {}).items())
    qs = '&'.join(quote(k, safe='~') + '=' + quote(v, safe='~') for k, v in pairs)
    now = now or datetime.now(timezone.utc)
    date, stamp = now.strftime('%Y%m%d'), now.strftime('%Y%m%dT%H%M%SZ')
    digest = hashlib.sha256(payload).hexdigest()
    headers = {'host': host, 'x-amz-date': stamp, 'x-amz-content-sha256': digest}
    if target:
        headers.update({'content-type': 'application/x-amz-json-1.0', 'x-amz-target': target})
    keys = sorted(headers)
    canonical = '\n'.join([method, path, qs, ''.join(k + ':' + headers[k] + '\n' for k in keys),
                           ';'.join(keys), digest])
    scope = f'{date}/us-east-1/{service}/aws4_request'
    message = 'AWS4-HMAC-SHA256\n' + stamp + '\n' + scope + '\n' + hashlib.sha256(canonical.encode()).hexdigest()
    key = b'AWS4test'
    for part in (date, 'us-east-1', service, 'aws4_request'):
        key = hmac.new(key, part.encode(), hashlib.sha256).digest()
    signature = hmac.new(key, message.encode(), hashlib.sha256).hexdigest()
    headers['Authorization'] = f'AWS4-HMAC-SHA256 Credential=test/{scope}, SignedHeaders={";".join(keys)}, Signature={signature}'
    return urllib.request.Request(endpoint + path + ('?' + qs if qs else ''), data=payload if method == 'POST' else None,
                                  headers=headers, method=method)


def read(request):
    # Refuse redirects to other endpoints and bound memory/latency.
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            return None
    with urllib.request.build_opener(NoRedirect).open(request, timeout=4) as response:
        raw = response.read(MAX_RESPONSE + 1)
    if len(raw) > MAX_RESPONSE:
        raise ValueError('Response exceeds bounded preview')
    return raw


def xml_values(raw, tag):
    if b'<!DOCTYPE' in raw.upper() or b'<!ENTITY' in raw.upper():
        raise ValueError('XML entities forbidden')
    return [el.text or '' for el in ET.fromstring(raw).iter() if el.tag.rsplit('}', 1)[-1] == tag]


def browser(view, backend, selection='', mount=''):
    if backend not in ENDPOINTS or view not in ('storage', 'dynamodb'):
        raise ValueError('Unsupported browser/backend')
    base = (mount or '/' + view) + '/?backend=' + backend
    if view == 'storage':
        if selection:
            raw = read(signed_request(backend, 's3', path='/' + selection,
                                     query={'list-type': '2', 'max-keys': '100'}))
            items = xml_values(raw, 'Key')
            body = '<p>First 100 object keys in ' + escape(selection) + '</p><ul>' + ''.join('<li>' + escape(x) + '</li>' for x in items) + '</ul>'
        else:
            items = xml_values(read(signed_request(backend, 's3')), 'Name')
            body = '<ul>' + ''.join('<li><a href="' + base + '&bucket=' + quote(x, safe='') + '">' + escape(x) + '</a></li>' for x in items) + '</ul>'
    else:
        operation = 'DescribeTable' if selection else 'ListTables'
        payload = json.dumps({'TableName': selection} if selection else {'Limit': 100}).encode()
        result = json.loads(read(signed_request(backend, 'dynamodb', 'POST', payload=payload,
                                             target='DynamoDB_20120810.' + operation)))
        if selection:
            # Table metadata only: no scan that could disclose tenant row contents.
            body = '<pre>' + escape(json.dumps(result, indent=2)) + '</pre>'
        else:
            body = '<ul>' + ''.join('<li><a href="' + base + '&table=' + quote(x, safe='') + '">' + escape(x) + '</a></li>' for x in result.get('TableNames', [])) + '</ul>'
    if (view == 'storage' and not items) or (view == 'dynamodb' and not result):
        body += '<p>No resources found.</p>'
    return '<p><a href="' + base + '">Refresh</a></p>' + body


def page(title, body, mount=''):
    return ('<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
            '<title>' + escape(title) + ' · Twinfra</title><link rel="stylesheet" href="' + escape(mount) + '/console.css">'
            '<body><header><a href="' + ('/console/overview' if mount else '/') + '">Twinfra console</a></header><main><h1>' + escape(title) + '</h1>' + body + '</main></body></html>').encode()


def navigation(profile):
    cards = []
    for item in profile['backends']:
        name = item['name']
        href = '/' + name + '/'
        if name == 'ministack':
            href += '_' + name + '/health'
        action = '<a href="' + href + '">Open ' + escape(name) + '</a>' if item['enabled'] else '<span>Disabled reference</span>'
        cards.append('<article><h2>' + escape(name) + '</h2><p>' + escape(item['description']) + '</p><p>' + escape(item['license']) + '</p>' + action + '</article>')
    return page('Platform services', '<p>Read-only development navigation. Backend availability is checked when opened.</p>' + ''.join(cards))


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass  # never log cookies, OIDC codes, credentials or user query values

    def respond(self, status, body, content='text/html; charset=utf-8'):
        self.send_response(status)
        self.send_header('Content-Type', content)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Frame-Options', 'SAMEORIGIN')
        self.send_header('Content-Security-Policy', "default-src 'none'; style-src 'self'; frame-ancestors 'self'; base-uri 'none'; form-action 'self'")
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        url = urlsplit(self.path)
        if url.path == '/healthz':
            self.respond(200, b'{"status":"running"}', 'application/json')
            return
        if url.path == '/console.css':
            self.respond(200, b'body{font:16px system-ui;background:#101d2d;color:#edf5ff;margin:0}header,main{padding:24px;max-width:1100px;margin:auto}a{color:#91d3ff}article{display:inline-block;vertical-align:top;width:280px;border:1px solid #526780;border-radius:12px;padding:20px;margin:10px}pre{white-space:pre-wrap;overflow-wrap:anywhere}span{color:#c8b88d}', 'text/css')
            return
        if url.path != '/':
            self.respond(404, page('Not found', '<p>This path is not available.</p>'))
            return
        view = os.environ.get('VCLOUD_VIEW', 'shell')
        if view == 'shell':
            self.respond(200, navigation(json.loads(Path('/app/profile.json').read_text(encoding='utf-8'))))
            return
        try:
            # Only fixed gateway-owned mount prefixes can affect generated links.
            mount = self.headers.get('X-Forwarded-Prefix', '')
            if mount not in ('', '/console/proxy/storage', '/console/proxy/dynamodb'):
                mount = ''
            query = parse_qs(url.query, max_num_fields=5)
            backend = query.get('backend', ['ministack'])[0]
            selection = query.get('bucket' if view == 'storage' else 'table', [''])[0]
            if len(selection) > 255 or '/' in selection or '..' in selection:
                raise ValueError('Invalid selection')
            base = mount or '/' + view
            choose = '<p>MiniStack · Read-only</p>'
            self.respond(200, page(view.title(), choose + browser(view, backend, selection, mount), mount))
        except (ValueError, KeyError):
            self.respond(400, page('Invalid request', '<p>Choose a configured emulator and resource.</p>'))
        except Exception:
            self.respond(503, page('Backend unavailable', '<p>The selected emulator did not return a valid bounded response.</p>'))


if __name__ == '__main__':
    ThreadingHTTPServer(('0.0.0.0', int(os.environ.get('PORT', '3000'))), Handler).serve_forever()
