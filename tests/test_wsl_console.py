"""Console security, namespace, URL and bounded AWS browser regression gates."""
import base64
import copy
from datetime import datetime, timezone
import importlib.util
import json
from pathlib import Path
import sys
import threading
import unittest
from unittest.mock import patch
import urllib.error
import urllib.request
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import wsl_console as console
from wsl_console_preflight import validate_secret
from wsl_endpoints import check

spec = importlib.util.spec_from_file_location('console_ui', console.HERE / 'ui.py')
ui = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ui)


class ConsoleTests(unittest.TestCase):
    def test_sources_have_no_render_drift(self):
        console.publish(True)
        console.image()

    def test_routes_are_gated_with_same_namespace_backends(self):
        routes = console.routes()
        self.assertEqual(len(routes), 5)
        services = {o['metadata']['name'] for o in console.workloads() if o['kind'] == 'Service'}
        for obj in routes:
            self.assertEqual(obj['metadata']['namespace'], 'platform-services')
            rule = obj['spec']['http'][0]
            self.assertIn(rule['backends'][0]['serviceName'], services)
            self.assertEqual(rule['match']['hosts'], ['console.vcloud.local'])
            oidc = next(p for p in rule['plugins'] if p['name'] == 'openid-connect')
            self.assertEqual(oidc['secretRef'], 'vcloud-console-oidc')
            self.assertNotIn('client_secret', oidc['config'])
            self.assertNotIn('secret', oidc['config']['session'])
            self.assertTrue(oidc['config']['ssl_verify'])
            self.assertEqual(oidc['config']['unauth_action'], 'auth')
            self.assertEqual(oidc['config']['scope'], 'openid')
            self.assertFalse(oidc['config']['access_token_in_authorization_header'])
            self.assertTrue(oidc['config']['claim_validator']['audience']['required'])
        for obj in console.routes(True):
            self.assertEqual(obj['metadata']['namespace'], 'platform-system')
            self.assertEqual(obj['metadata']['annotations']['vcloud.io/activation'], 'disabled-reference-do-not-apply')

    def test_exact_prefix_rewrite_boundary_and_ports(self):
        import re
        for obj in console.routes() + console.routes(True):
            rule = obj['spec']['http'][0]
            if rule['name'] == 'shell':
                self.assertEqual(rule['priority'], 5)
                continue
            name = rule['name']
            regex, replacement = next(p['config']['regex_uri'] for p in rule['plugins'] if p['name'] == 'proxy-rewrite')
            self.assertEqual(replacement, '/$1')
            self.assertTrue(re.fullmatch(regex, '/' + name))
            self.assertEqual(re.fullmatch(regex, '/' + name + '/table/users').group(1), 'table/users')
            self.assertIsNone(re.fullmatch(regex, '/' + name + 'other/table'))
            self.assertEqual(rule['match']['paths'], ['/' + name, '/' + name + '/*'])

    def test_websocket_and_identity_headers_are_preserved(self):
        for obj in console.routes() + console.routes(True):
            rule = obj['spec']['http'][0]
            self.assertEqual(rule['websocket'], rule['name'] in ('spinifex', 'vault', 'dynamodb'))
            rewrite = next(p['config'] for p in rule['plugins'] if p['name'] == 'proxy-rewrite')
            self.assertNotIn('Connection', rewrite['headers']['set'])
            self.assertNotIn('Upgrade', rewrite['headers']['set'])
            scrub = next(p['config'] for p in rule['plugins'] if p['name'] == 'serverless-pre-function')
            self.assertGreater(scrub['_meta']['priority'], 2599)
            self.assertNotIn("clear_header('Authorization')", scrub['functions'][0])

    def test_cors_and_frame_headers_never_use_wildcards(self):
        for obj in console.routes() + console.routes(True):
            rule = obj['spec']['http'][0]
            cors = next(p['config'] for p in rule['plugins'] if p['name'] == 'cors')
            self.assertEqual(cors['allow_origins'], 'http://console.vcloud.local:18080')
            headers = next(p['config']['headers']['set'] for p in rule['plugins'] if p['name'] == 'response-rewrite')
            self.assertEqual(headers['X-Frame-Options'], 'SAMEORIGIN')
            self.assertNotEqual(headers['Access-Control-Allow-Origin'], '*')

    def test_pod_security_mutations_rejected(self):
        for mutation in ('root', 'privileged', 'privilege', 'pull', 'hostpath', 'gpu'):
            objects = console.workloads()
            obj = next(o for o in objects if o['kind'] == 'Deployment')
            pod = obj['spec']['template']['spec']; c = pod['containers'][0]
            if mutation == 'root': c['securityContext']['runAsUser'] = 0
            elif mutation == 'privileged': c['securityContext']['privileged'] = True
            elif mutation == 'privilege': c['securityContext']['allowPrivilegeEscalation'] = True
            elif mutation == 'pull': c['imagePullPolicy'] = 'Always'
            elif mutation == 'hostpath': pod['volumes'].append({'name': 'bad', 'hostPath': {'path': '/etc'}})
            else: c['resources']['limits']['nvidia.com/gpu'] = 1
            with self.subTest(mutation=mutation), self.assertRaises(ValueError): check(objects)

    def test_no_external_egress_or_world_probe_allows(self):
        for obj in console.network():
            for rule in obj['spec']['ingress'] + obj['spec']['egress']:
                self.assertNotIn('fromEntities', rule)
                self.assertNotIn('toEntities', rule)
                self.assertNotIn('toCIDR', rule)
        pod = next(o for o in console.workloads() if o['kind'] == 'Deployment' and o['metadata']['name'] == 'ministack')['spec']['template']['spec']
        self.assertFalse(pod['automountServiceAccountToken'])
        self.assertFalse(any(v.get('hostPath') for v in pod['volumes']))

    def test_missing_partial_or_overbroad_oidc_secret_fails(self):
        good = {'data': {k: base64.b64encode(b'a' * 48).decode() for k in ('client_secret', 'session.secret')}}
        validate_secret(good)
        for data in ({}, {'client_secret': good['data']['client_secret']}, dict(good['data'], ssl_verify='ZmFsc2U='),
                     dict(good['data'], client_secret='eA=='), dict(good['data'], client_secret='notbase64')):
            with self.subTest(keys=list(data)), self.assertRaises(ValueError): validate_secret({'data': data})

    def test_keycloak_callback_exact_and_no_privileged_grants(self):
        client = json.loads((console.HERE / 'keycloak-client.json').read_text())
        self.assertEqual(client['redirectUris'], ['http://console.vcloud.local:18080/oidc/callback'])
        self.assertFalse(client['publicClient']); self.assertFalse(client['directAccessGrantsEnabled'])
        project, app = console.definitions()
        self.assertEqual(project['spec']['clusterResourceWhitelist'], [])
        self.assertEqual(app['spec']['source']['targetRevision'], 'main')
        self.assertNotIn('Secret', {v['kind'] for v in project['spec']['namespaceResourceWhitelist']})

    def test_aws_signs_direct_backend_not_proxy_prefix(self):
        req = ui.signed_request('ministack', 's3', path='/test bucket', query={'list-type': '2', 'max-keys': '100'}, now=datetime(2026, 10, 7, tzinfo=timezone.utc))
        self.assertEqual(req.full_url, ui.ENDPOINTS['ministack'] + '/test%20bucket?list-type=2&max-keys=100')
        self.assertIn('Credential=test/20261007/us-east-1/s3/aws4_request', req.get_header('Authorization'))
        self.assertEqual(req.get_header('X-amz-content-sha256'), 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855')
        with self.assertRaises(KeyError): ui.signed_request('https://attacker.invalid', 's3')

    def test_s3_and_dynamodb_html_escapes_backend_data(self):
        with patch.object(ui, 'read', return_value=b'<ListAllMyBucketsResult><Buckets><Bucket><Name>&lt;script&gt;alert(1)&lt;/script&gt;</Name></Bucket></Buckets></ListAllMyBucketsResult>'):
            html = ui.browser('storage', 'localstack')
            self.assertNotIn('<script>', html); self.assertIn('&lt;script&gt;', html)
        with patch.object(ui, 'read', return_value=b'{"TableNames":["<script>"]}'):
            self.assertNotIn('<script>', ui.browser('dynamodb', 'ministack'))
        with self.assertRaises(ValueError): ui.xml_values(b'<!DOCTYPE foo><a/>', 'a')

    def test_navigation_shows_disabled_references_without_fake_links(self):
        body = ui.navigation(console.profile()).decode()
        self.assertIn('Twinfra console', body)
        self.assertNotIn('href="/spinifex/', body)
        self.assertNotIn('href="/vault/', body)
        self.assertIn('/ministack/_ministack/health', body)
        self.assertIn('/localstack/_localstack/health', body)

    def test_http_handler_bounded_views_and_invalid_backend(self):
        server = ui.ThreadingHTTPServer(('127.0.0.1', 0), ui.Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        root = 'http://127.0.0.1:' + str(server.server_port)
        try:
            with patch.dict('os.environ', {'VCLOUD_VIEW': 'storage'}), patch.object(ui, 'read', return_value=b'<ListAllMyBucketsResult><Name>acceptance</Name></ListAllMyBucketsResult>') as read:
                with urllib.request.urlopen(root + '/?backend=ministack', timeout=2) as response:
                    self.assertEqual(response.status, 200)
                    self.assertEqual(response.headers['X-Frame-Options'], 'SAMEORIGIN')
                    self.assertIn("frame-ancestors 'self'", response.headers['Content-Security-Policy'])
                    self.assertIn(b'acceptance', response.read())
                read.reset_mock()
                with self.assertRaises(urllib.error.HTTPError) as raised:
                    urllib.request.urlopen(root + '/?backend=https://attacker.invalid', timeout=2)
                self.assertEqual(raised.exception.code, 400)
                raised.exception.close()
                read.assert_not_called()
            with patch.dict('os.environ', {'VCLOUD_VIEW': 'dynamodb'}), patch.object(ui, 'read', side_effect=TimeoutError):
                with self.assertRaises(urllib.error.HTTPError) as raised:
                    urllib.request.urlopen(root + '/', timeout=2)
                self.assertEqual(raised.exception.code, 503)
                raised.exception.close()
        finally:
            server.shutdown(); server.server_close(); thread.join(timeout=2)


if __name__ == '__main__': unittest.main()
