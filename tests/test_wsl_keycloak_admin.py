"""Security and recovery tests; synthetic passwords only, no live credentials."""
import base64
import copy
import json
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import wsl_keycloak_admin as admin
import wsl_endpoints as endpoints


class KeycloakAdminTests(unittest.TestCase):
    def value(self, username=admin.ADMIN, password='synthetic-private-fixture-' * 3):
        return {'metadata': {'labels': admin.OWNER.copy()}, 'data': {
            'admin-user': base64.b64encode(username.encode()).decode(),
            'admin-password': base64.b64encode(password.encode()).decode()}}

    def deployment(self):
        return next(o for o in endpoints.identity() if o['kind'] == 'Deployment' and o['metadata']['name'] == 'keycloak')

    def test_owned_credential_is_valid(self):
        self.assertEqual(admin.credential(self.value(), admin.ADMIN), 'synthetic-private-fixture-' * 3)

    def test_unowned_or_wrong_username_refused(self):
        obj = self.value(); obj['metadata']['labels'] = {}
        with self.assertRaises(ValueError): admin.credential(obj, admin.ADMIN)
        with self.assertRaises(ValueError): admin.credential(self.value('other'), admin.ADMIN)

    def test_short_and_control_character_passwords_refused(self):
        for password in ('short', 'a' * 40 + '\n', 'a' * 40 + '\x00'):
            with self.subTest(password=repr(password)), self.assertRaises(ValueError):
                admin.credential(self.value(password=password), admin.ADMIN)

    def test_create_secret_uses_only_stdin_and_preserves_existing(self):
        fixture = 'synthetic-private-fixture-' * 3
        with patch.object(admin, 'k', side_effect=[b'', b'']) as k, patch.object(admin.secrets, 'token_urlsafe', return_value=fixture):
            self.assertEqual(admin.secret(admin.ADMIN_SECRET, admin.ADMIN), fixture)
            args, payload = k.call_args.args
            self.assertEqual(args, ['create', '-f', '-'])
            self.assertNotIn(fixture, json.dumps(args))
            self.assertEqual(admin.credential(json.loads(payload), admin.ADMIN), fixture)
        with patch.object(admin, 'k', return_value=json.dumps(self.value()).encode()) as k:
            admin.secret(admin.ADMIN_SECRET, admin.ADMIN)
            self.assertEqual(k.call_count, 1)

    def test_failed_subprocess_does_not_leak_output(self):
        response = subprocess.CompletedProcess([], 1, b'synthetic-secret', b'synthetic-secret')
        with patch.object(admin.subprocess, 'run', return_value=response), self.assertRaises(RuntimeError) as err:
            admin.k(['create', '-f', '-'], b'synthetic-secret')
        self.assertNotIn('synthetic-secret', str(err.exception))

    def test_api_reads_only_public_certificate_and_verifies_tls(self):
        public = base64.b64encode(b'synthetic-public-certificate')
        with patch.object(admin, 'k', return_value=public) as k, patch.object(admin.ssl, 'create_default_context') as ctx:
            admin.API()
        self.assertEqual(k.call_args.args[0][-1], 'jsonpath={.data.tls\\.crt}')
        ctx.assert_called_once_with(cadata='synthetic-public-certificate')

    def test_login_keeps_password_in_http_body_and_disables_redirects(self):
        api = admin.API.__new__(admin.API); api.context = object()
        response = unittest.mock.MagicMock()
        response.__enter__.return_value.read.return_value = b'{"access_token":"synthetic-token"}'
        opener = unittest.mock.MagicMock(); opener.open.return_value = response
        with patch.object(admin.urllib.request, 'build_opener', return_value=opener) as build:
            self.assertEqual(api.login(admin.ADMIN, 'synthetic-private-password'), 'synthetic-token')
        request = opener.open.call_args.args[0]
        self.assertEqual(request.full_url, admin.BASE + '/realms/master/protocol/openid-connect/token')
        self.assertNotIn('synthetic-private-password', request.full_url)
        self.assertIn(b'password=synthetic-private-password', request.data)
        redirect = build.call_args.args[0]
        self.assertIsNone(redirect.redirect_request(None, None, 302, '', {}, 'https://other.invalid'))
        with self.assertRaises(ValueError): api.request('//other.invalid')

    def test_offline_pod_is_restricted_bounded_and_never_ready(self):
        dep = self.deployment(); before = copy.deepcopy(dep)
        pod = admin.bootstrap_pod(dep, 'test-run')
        self.assertEqual(dep, before)
        endpoints.check([pod])
        spec = pod['spec']; c = spec['containers'][0]
        self.assertEqual(spec['restartPolicy'], 'Never')
        self.assertEqual(spec['activeDeadlineSeconds'], 240)
        self.assertTrue(c['stdin'] and c['tty'])
        self.assertTrue(c['args'][0].startswith('stty -echo;'))
        self.assertNotIn('--password', c['args'][0])
        self.assertNotIn('env', c)
        self.assertNotIn('livenessProbe', c)
        self.assertEqual(c['readinessProbe']['exec']['command'], ['sh', '-c', 'exit 1'])
        self.assertEqual(pod['metadata']['labels']['app.kubernetes.io/name'], 'keycloak')

    def test_image_or_privilege_mutations_refused(self):
        for mutation in ('image', 'privilege', 'mount'):
            dep = self.deployment(); spec = dep['spec']['template']['spec']
            if mutation == 'image': spec['containers'][0]['image'] = 'other:latest'
            elif mutation == 'privilege': spec['containers'][0]['securityContext']['privileged'] = True
            else: spec['volumes'].append({'name': 'bad', 'hostPath': {'path': '/'}})
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                admin.bootstrap_pod(dep, 'test-run')

    def test_failure_restores_replica_and_gitops_skip_annotation(self):
        dep = self.deployment()
        app = {'metadata': {}, 'status': {'operationState': {'phase': 'Succeeded'}}}
        results = iter([app, app, {'items': []}])
        def read(args):
            if args[:2] == ['get', 'pod']: return {'status': {'phase': 'Running', 'containerStatuses': [{'state': {'running': {}}}]}}
            return next(results)
        def command(args, *rest, **kwargs):
            if args[:2] == ['create', '-f']: return b'{"metadata":{"uid":"owned-uid"}}'
            if args and args[0] == 'logs': return b'VCLOUD_PRIVATE_INPUT_READY'
            if args[:2] == ['get', 'pod']: return b'{"metadata":{"uid":"owned-uid"}}'
            return b''
        with patch.object(admin, 'obj', side_effect=read), patch.object(admin, 'k', side_effect=command), patch.object(admin, 'patch') as p, patch.object(admin.time, 'sleep'), patch.object(admin, 'private_input', side_effect=RuntimeError('synthetic input failure')), patch.object(admin.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0)), self.assertRaises(RuntimeError):
            admin.offline(dep, 'synthetic-private-fixture-' * 3)
        self.assertIn(unittest.mock.call('deployment', 'keycloak', {'spec': {'replicas': 1}}), p.call_args_list)
        self.assertIn(unittest.mock.call('application', admin.APP, {'metadata': {'annotations': {admin.SKIP: None}}}), p.call_args_list)


if __name__ == '__main__': unittest.main()
