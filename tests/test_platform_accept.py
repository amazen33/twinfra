"""WO-40a offline failure injection. No kubectl, SSH, host or browser operations."""
import copy
import ast
from datetime import date, datetime, timedelta, timezone
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import platform_accept as ac
import platform_dev as dev
import platform_host as host

NOW = datetime(2026, 10, 16, 12, tzinfo=timezone.utc)
REVISION = 'a' * 40
DIGEST = 'sha256:' + 'b' * 64
CONFIG = 'sha256:' + 'c' * 64
REF = 'registry.twinfra.example.com/example/image@' + DIGEST
COOKIE = 'twinfra_portal=PRIVATE-COOKIE-FIXTURE'
TOKEN = 'e30.eyJzdWIiOiJyb2xlbGVzcyJ9.Zml4dHVyZQ'


def pod(name, label='app.kubernetes.io/name', namespace=ac.NS):
    return {'metadata': {'name': name + '-pod', 'namespace': namespace, 'uid': name,
                         'labels': {label: name}},
            'spec': {'containers': [{'name': 'container', 'image': REF}]},
            'status': {'phase': 'Running', 'podIP': '10.50.1.' + str(len(name)),
                       'conditions': [{'type': 'Ready', 'status': 'True'}],
                       'containerStatuses': [{'name': 'container', 'imageID': 'containerd://' + CONFIG,
                                              'restartCount': 0}]}}


class FakeClient:
    def __init__(self):
        self.pods = [pod(n) for n in (*ac.ARGO, 'argocd-redis', 'twinfra-console', 'twinfra-keycloak', 'twinfra-openbao')]
        self.pods += [pod('cilium', 'k8s-app', 'kube-system'), pod('kube-dns', 'k8s-app', 'kube-system'),
                      pod('etcd', 'component', 'kube-system'), pod('cloudnative-pg'),
                      pod('twinfra-postgres', 'cnpg.io/cluster')]
        self.node = {'metadata': {'name': ac.CONTEXT, 'labels': {'twinfra.io/environment': 'dev',
                     'twinfra.io/region': 'cairo-1', 'topology.kubernetes.io/zone': 'cairo-1a'}},
                     'status': {'conditions': [{'type': 'Ready', 'status': 'True'}],
                     'addresses': [{'type': 'InternalIP', 'address': '192.168.1.3'}],
                     'nodeInfo': {'kubeletVersion': 'v1.36.5', 'containerRuntimeVersion': 'containerd://2.2.1'}}}
        self.apps = [{'metadata': {'name': n}, 'status': {'sync': {'status': 'Synced', 'revision': REVISION},
                     'health': {'status': 'Healthy'}, 'reconciledAt': NOW.isoformat()}} for n in ac.APPS]
        self.calls, self.restarted = [], False
        self.auth = True
        self.codes = [401, 401, 401, 403]

    def get(self, resource, *args):
        self.calls.append(('get', resource, *args))
        return copy.deepcopy({'items': [self.node] if resource == 'nodes' else self.pods if resource == 'pods' else self.apps})

    def exec(self, p, container, *command, payload=None):
        self.calls.append(('exec', *command))
        if command[0] == 'python':
            assert json.loads(payload)['roleless'] == TOKEN
            return json.dumps(self.codes)
        if command[0] == 'valkey-cli':
            return 'NOAUTH Authentication required.\n' if self.auth else 'PONG\n'
        if command[-1] == 'PING':
            return 'PONG\n'
        return '\n'.join('addr=' + ac.one_pod(self.pods, n)['status']['podIP'] + ':12345' for n in ac.ARGO)

    def call(self, *args, payload=None):
        self.calls.append(args)
        if 'delete' in args:
            self.restarted = True
            ac.one_pod(self.pods, 'argocd-redis')['metadata']['uid'] = 'replacement-cache'
            for app in self.apps:
                app['status']['reconciledAt'] = (NOW + timedelta(seconds=1)).isoformat()
        return 'fixture-version\n'


class FakeSSH:
    def __init__(self):
        self.calls = []
        self.status = 'passed'

    def agent(self, lock, check=False):
        assert check is True
        self.calls.append(('agent', check))
        return {'status': self.status, 'problems': []}

    def run(self, command):
        self.calls.append(tuple(command))
        assert command[:4] == ['sudo', '-n', 'crictl', 'inspecti']
        return json.dumps({'status': {'id': CONFIG, 'repoDigests': [REF]}}).encode()


class Acceptance(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        common = self.root / 'deploy/common'
        common.mkdir(parents=True)
        lock = {'images': {'fixture': {'canonical': REF, 'digest': DIGEST}}}
        for filename in ('images.lock.json', 'bootstrap-images.lock.json'):
            (common / filename).write_text(json.dumps(lock))
        (self.root / 'security').mkdir()
        (self.root / 'security/vulnerability-exceptions.json').write_text('{"exceptions":[]}')
        self.client, self.ssh = FakeClient(), FakeSSH()
        self.args = SimpleNamespace(context=ac.CONTEXT, expected_revision=REVISION, since=None,
              timeout=5, session_file='private-cookie', roleless_token_file='private-token',
              ca_file='public-ca', ssh='twinfra-operator@192.168.1.3', with_restart=False)

    def run_accept(self, **kwargs):
        defaults = dict(client=self.client, transport=self.ssh, host=lambda *a, **k: {'status': 'passed'},
                        health=lambda *a: True, now=lambda: NOW, sleeper=lambda _: None)
        defaults.update(kwargs)
        with patch.object(ac, 'ROOT', self.root), patch.object(ac, 'private_input', side_effect=[COOKIE, TOKEN]):
            return ac.accept(self.args, **defaults)

    def test_read_only_run_is_incomplete_without_restart_and_never_mutates(self):
        result = self.run_accept()
        self.assertEqual(result['status'], 'incomplete', result)
        self.assertEqual(result['checks']['valkeyRestart']['status'], 'pending')
        self.assertFalse(self.client.restarted)
        self.assertEqual(result['testerSignOff'], 'Pending')
        self.assertEqual(len(result['versions']), 12)
        self.assertNotIn(COOKIE, json.dumps(result))
        self.assertNotIn(TOKEN, json.dumps(result))

    def test_owner_restart_proves_new_pod_fresh_sync_and_all_three_client_connections(self):
        self.args.with_restart = True
        result = self.run_accept()
        self.assertEqual(result['status'], 'passed', result)
        deletes = [c for c in self.client.calls if 'delete' in c]
        self.assertEqual(len(deletes), 1)
        self.assertEqual(deletes[0], ('-n', ac.NS, 'delete', 'pod', 'argocd-redis-pod', '--wait=false'))

    def test_restart_is_refused_after_any_failed_precheck(self):
        self.args.with_restart = True
        self.client.node['status']['conditions'][0]['status'] = 'False'
        result = self.run_accept()
        self.assertEqual(result['status'], 'failed')
        self.assertFalse(self.client.restarted)

    def test_wrong_zone_label_ip_and_missing_app_fail(self):
        for field in ('zone', 'label', 'ip', 'app'):
            self.client = FakeClient()
            if field == 'zone':self.client.node['metadata']['labels']['topology.kubernetes.io/zone'] = 'cairo-2a'
            if field == 'label':self.client.node['metadata']['labels']['twinfra.io/environment'] = 'prod'
            if field == 'ip':self.client.node['status']['addresses'][0]['address'] = '192.168.1.4'
            if field == 'app':self.client.apps.pop()
            with self.subTest(field=field):self.assertEqual(self.run_accept()['status'], 'failed')

    def test_wrong_revision_outofsync_and_unhealthy_fail(self):
        for field in ('revision', 'status', 'health'):
            self.client = FakeClient()
            target = self.client.apps[0]['status']
            if field == 'health':target['health']['status'] = 'Degraded'
            else:target['sync'][field] = 'wrong'
            with self.subTest(field=field):self.assertEqual(self.run_accept()['status'], 'failed')

    def test_host_network_staging_and_https_fail_closed(self):
        self.assertEqual(self.run_accept(host=lambda *a, **k: {'status': 'failed'})['status'], 'failed')
        self.assertEqual(self.run_accept(health=lambda *a: False)['status'], 'failed')
        self.ssh.status = 'failed'
        self.assertEqual(self.run_accept()['status'], 'failed')

    def test_token_negatives_and_noauth_bypass_fail(self):
        self.client.codes[-1] = 200
        self.assertEqual(self.run_accept()['checks']['tokenNegatives']['status'], 'failed')
        self.client.codes = [401, 401, 401, 403]
        self.client.auth = False
        self.assertEqual(self.run_accept()['checks']['valkey']['status'], 'failed')

    def test_missing_reconnect_or_stale_app_revision_fails(self):
        self.args.with_restart = True
        original = self.client.call
        def stale(*args, **kwargs):
            result = original(*args, **kwargs)
            for app in self.client.apps:app['status']['reconciledAt'] = NOW.isoformat()
            return result
        self.client.call = stale
        self.assertEqual(self.run_accept()['checks']['valkeyRestart']['status'], 'failed')

    def test_secret_bearing_subprocess_error_is_never_reported(self):
        def fail(*args):raise ValueError('PRIVATE-COOKIE-FIXTURE ' + TOKEN)
        self.client.get = fail
        result = self.run_accept()
        self.assertEqual(result['status'], 'failed')
        self.assertNotIn('PRIVATE-COOKIE-FIXTURE', json.dumps(result))
        self.assertNotIn(TOKEN, json.dumps(result))

    def test_calendar_failure_refuses_restart_warning_is_reported(self):
        path = self.root / 'security/vulnerability-exceptions.json'
        entry = dict(target='fixture', package='p', version='1', vulnerability='CVE-fixture', expires='2026-10-23')
        path.write_text(json.dumps({'exceptions': [entry]}))
        self.args.with_restart = True
        result = self.run_accept()
        self.assertEqual(result['checks']['exceptionCalendar']['status'], 'failed')
        self.assertFalse(self.client.restarted)
        entry['expires'] = '2026-11-02'
        path.write_text(json.dumps({'exceptions': [entry]}))
        result = self.run_accept()
        self.assertEqual(result['status'], 'passed')
        self.assertEqual(result['warnings'], 1)
        self.assertEqual(result['exceptionCalendar'][0]['daysLeft'], 17)

    def test_wrong_context_revision_future_start_and_timeout_refuse_before_remote(self):
        for key, value in [('context', 'prod'), ('expected_revision', 'main'),
                           ('since', '2026-10-17T00:00:00Z'), ('timeout', 901)]:
            args = copy.copy(self.args)
            setattr(self.args, key, value)
            with self.subTest(key=key):
                self.assertEqual(self.run_accept()['status'], 'failed')
                self.assertEqual(self.client.calls, [])
            self.args = args


class Contracts(unittest.TestCase):
    def test_calendar_boundaries_and_expired_all_printed(self):
        today = date(2026, 10, 16)
        entries = [dict(target='fixture', package='p', version='1', vulnerability='CVE-fixture-' + str(n),
                        expires=(today + timedelta(days=n)).isoformat()) for n in (-1, 0, 7, 8, 21, 22)]
        values = ac.calendar(entries, today)
        self.assertEqual([v['daysLeft'] for v in values], [-1, 0, 7, 8, 21, 22])
        self.assertEqual([v['status'] for v in values], ['failed'] * 3 + ['warning'] * 2 + ['passed'])

    def test_terminal_pending_and_restarted_pods_fail(self):
        p = pod('fixture')
        for phase in ('Pending', 'Succeeded', 'Failed', 'Unknown'):
            p['status']['phase'] = phase
            self.assertTrue(ac.pod_problems([p], NOW))
        p['status']['phase'] = 'Running'
        p['status']['containerStatuses'][0]['lastState'] = {'terminated': {'finishedAt': NOW.isoformat()}}
        self.assertTrue(ac.pod_problems([p], NOW))
        p['status']['containerStatuses'][0].pop('lastState')
        before = ac.snapshot([p])
        p['status']['containerStatuses'][0]['restartCount'] = 1
        self.assertTrue(ac.pod_problems([p], NOW, before))
        p['status']['containerStatuses'][0]['restartCount'] = 0
        p['metadata']['creationTimestamp'] = NOW.isoformat()
        self.assertTrue(ac.pod_problems([p], NOW))

    def test_platform_manifest_is_bound_to_admitted_parent_cri_identity(self):
        p = pod('fixture')
        child = 'registry.twinfra.example.com/example/image@sha256:' + 'd' * 64
        p['status']['containerStatuses'][0]['imageID'] = child
        lock = {'images': {'fixture': {'canonical': REF, 'digest': DIGEST}}}
        self.assertFalse(ac.image_problems([p], lock, {REF: CONFIG, child: CONFIG})[0])
        self.assertTrue(ac.image_problems([p], lock, {REF: CONFIG, child: 'sha256:' + 'e' * 64})[0])

    def test_every_container_kind_unknown_ref_and_wrong_runtime_id_fail(self):
        p = pod('fixture')
        lock = {'images': {'fixture': {'canonical': REF, 'digest': DIGEST}}}
        for field, statuses in [('containers','containerStatuses'), ('initContainers','initContainerStatuses'),
                                 ('ephemeralContainers','ephemeralContainerStatuses')]:
            q = copy.deepcopy(p)
            q['spec'] = {field: copy.deepcopy(p['spec']['containers'])}
            q['status'] = {statuses: p['status']['containerStatuses']}
            self.assertEqual(ac.image_problems([q], lock, {REF: CONFIG})[0], [])
            self.assertTrue(ac.image_problems([q], lock, {REF: 'sha256:' + 'd' * 64})[0])
            q['spec'][field][0]['image'] = 'upstream.example/unlocked:latest'
            self.assertTrue(ac.image_problems([q], lock, {REF: CONFIG})[0])

    def test_tag_digest_normalization_and_exact_bootstrap_tag(self):
        p = pod('fixture')
        p['spec']['containers'][0]['image'] = REF.replace('@', ':1.2.3@')
        lock = {'images': {'fixture': {'canonical': REF, 'digest': DIGEST}}}
        self.assertFalse(ac.image_problems([p], lock, {REF: CONFIG})[0])
        p['spec']['containers'][0]['image'] = 'registry.twinfra.example.com/registry.k8s.io/pause:3.10.1'
        self.assertTrue(ac.image_problems([p], lock, {REF: CONFIG})[0])

    def test_client_never_echoes_subprocess_error_or_secret(self):
        def run(*args, **kwargs):return SimpleNamespace(returncode=1, stdout=TOKEN.encode(), stderr=COOKIE.encode())
        with self.assertRaisesRegex(ValueError, '^Kubernetes acceptance operation failed$'):
            ac.Client(ac.CONTEXT, run).call('get', 'nodes')

    def test_client_deadline_prevents_further_exec_after_poll_timeout(self):
        runner = MagicMock()
        client = ac.Client(ac.CONTEXT, runner)
        client.deadline = 0
        with self.assertRaises(ValueError):client.call('get', 'pods')
        runner.assert_not_called()

    def test_private_file_in_git_or_multiline_and_group_readable_refused(self):
        with self.assertRaises(ValueError):ac.private_input(ROOT / 'VERSION')
        # A real non-Git fixture is needed even when the test runner's TEMP is .build.
        native_temp = Path(os.environ['LOCALAPPDATA']) / 'Temp' if os.name == 'nt' else Path('/tmp')
        with tempfile.TemporaryDirectory(dir=native_temp) as tmp:
            p = Path(tmp) / 'token'
            p.write_text('line1\nline2')
            p.chmod(0o600)
            with self.assertRaises(ValueError):ac.private_input(p)
            p.write_text(TOKEN)
            self.assertEqual(ac.private_input(p), TOKEN)
            if os.name != 'nt':
                p.chmod(0o644)
                with self.assertRaises(ValueError):ac.private_input(p)

    def test_receipt_is_new_build_fragment_never_signed_receipt_or_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(ac, 'ROOT', Path(tmp)):
            path = Path(tmp) / '.build/receipt.json'
            ac.write_fragment(path, {'status': 'incomplete', 'testerSignOff': 'Pending'})
            with self.assertRaises(ValueError):ac.write_fragment(path, {})
            with self.assertRaises(ValueError):ac.write_fragment(Path(tmp) / 'docs/acceptance/signed.md', {})

    def test_cli_excludes_mutation_flags_and_invalid_receipt_before_any_accept(self):
        with patch.object(ac, 'accept') as remote:
            for extra in ('--apply', '--rollback', '--check', '--download-inputs'):
                with patch.object(sys, 'argv', ['platform_dev.py', 'accept', extra]), patch('sys.stderr', new_callable=io.StringIO), self.assertRaises(SystemExit):
                    dev.main()
            with patch.object(sys, 'argv', ['platform_dev.py', 'accept', '--receipt', str(ROOT / 'README.md')]), patch('sys.stdout', new_callable=io.StringIO):
                self.assertEqual(dev.main(), 1)
            remote.assert_not_called()

    def test_https_tunnel_verifies_ca_does_not_follow_redirects_or_accept_remote_dns(self):
        connection = MagicMock()
        response = connection.getresponse.return_value
        response.status = 200
        response.read.return_value = b'{"environment":"dev"}'
        address = [(2, 1, 6, '', ('127.0.0.1', 18444))]
        with patch.object(ac.socket, 'getaddrinfo', return_value=address), \
             patch.object(ac.ssl, 'create_default_context') as ca, \
             patch.object(ac.http.client, 'HTTPSConnection', return_value=connection):
            self.assertTrue(ac.console_health('public-ca', COOKIE))
            ca.assert_called_once_with(cafile='public-ca')
            response.status = 302
            response.read.return_value = b''
            self.assertFalse(ac.console_health('public-ca', COOKIE))
            self.assertEqual(connection.request.call_count, 2)
            address[0] = (2, 1, 6, '', ('192.168.1.3', 18444))
            with self.assertRaises(ValueError):ac.console_health('public-ca', COOKIE)
            self.assertEqual(connection.request.call_count, 2)

    def test_token_probe_sends_duplicate_wire_headers_and_prints_only_codes(self):
        sent = []
        class Connection:
            def __init__(self, *a, **k):self.headers = [];sent.append(self.headers)
            def putrequest(self, *a):pass
            def putheader(self, key, value):self.headers.append((key, value))
            def endheaders(self):pass
            def getresponse(self):
                return SimpleNamespace(status=403 if self.headers == [('X-Access-Token', TOKEN)] else 401,
                                       read=lambda n: b'')
            def close(self):pass
        with patch.object(ac.http.client, 'HTTPConnection', Connection), \
             patch('sys.stdin', io.StringIO(json.dumps({'roleless': TOKEN}))), \
             patch('sys.stdout', new_callable=io.StringIO) as output:
            exec(ac.TOKEN_PROBE, {})
        self.assertEqual(json.loads(output.getvalue()), [401, 401, 401, 403])
        self.assertEqual(len(sent[2]), 2)
        self.assertNotIn(TOKEN, output.getvalue())

    def test_readonly_network_check_cannot_adopt_or_start_a_transaction(self):
        class Capture:
            def run(self, command, payload=None):
                self.payload = payload.decode()
                return b'{"status":"passed"}'
        ssh = Capture()
        host.execute('host-network', ac.ReadOnlyNetwork(ssh), check=True)
        assignment = ast.parse(ssh.payload).body[0]
        namespace = {'__name__': 'offline_network_guard'}
        exec(ast.literal_eval(assignment.value), namespace)
        with self.assertRaisesRegex(ValueError, 'Read-only acceptance refuses network adoption'):
            namespace['adoptable']({}, {})
        with self.assertRaises(ValueError):host.execute('host-network', ac.ReadOnlyNetwork(ssh), apply=True)


if __name__ == '__main__':unittest.main()
