"""WO-29 static/offline tests; no SSH, VM, runtime import, CA file or cluster writes."""
import contextlib
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import patch

import yaml
from cryptography import x509
from cryptography.hazmat.primitives import serialization
from cryptography.x509.oid import ExtendedKeyUsageOID

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import platform_dev as dev
import platform_dev_ca as ca
import platform_image_staging as ssh_stage
from manifest_contract import podspec

spec = importlib.util.spec_from_file_location('stager', ROOT / 'deploy/common/stage-images.py')
stager = importlib.util.module_from_spec(spec)
spec.loader.exec_module(stager)


def locked(name='sample'):
    sha = 'sha256:' + 'a' * 64
    return {'source': 'quay.io/example/' + name + '@' + sha,
            'canonical': 'registry.twinfra.example.com/quay.io/example/' + name + '@' + sha, 'digest': sha}


class FakeCtr:
    def __init__(self, state=None, bad_pull=False, missing_after_tag=False, cri_missing=False):
        self.state = state or {}
        self.commands = []
        self.bad_pull, self.missing_after_tag, self.cri_missing = bad_pull, missing_after_tag, cri_missing

    def __call__(self, cmd):
        self.commands.append(cmd)
        if cmd[:2] == ['crictl', 'inspecti']:
            return json.dumps({'status': {'repoDigests': [] if self.cri_missing else [cmd[2].split('@')[0] + '@' + self.state[cmd[2]]]}})
        action = cmd[4]
        if action == 'list':
            return '\n'.join(name + ' manifest ' + sha + ' 1 KiB linux/amd64 -' for name, sha in self.state.items())
        if action == 'pull':
            assert '--local' in cmd and cmd[cmd.index('--platform') + 1] == 'linux/amd64'
            directory = Path(cmd[cmd.index('--hosts-dir') + 1])
            assert directory.is_dir() and not list(directory.iterdir())
            self.state[cmd[-1]] = 'sha256:' + 'b' * 64 if self.bad_pull else cmd[-1].split('@')[1]
        elif action == 'tag':
            if not self.missing_after_tag:
                self.state[cmd[-1]] = self.state[cmd[-2]]
        elif action == 'label':
            pass
        else:
            raise AssertionError('Unexpected fake runtime action')
        return ''


class BootstrapStaging(unittest.TestCase):
    def test_digest_mismatch_stops_before_tag(self):
        ctr = FakeCtr(bad_pull=True)
        with self.assertRaisesRegex(ValueError, 'Upstream digest mismatch'):
            stager.stage({'images': {'sample': locked()}}, runner=ctr)
        self.assertFalse(any(c[4] == 'tag' for c in ctr.commands if c[0] == 'ctr'))

    def test_missing_image_after_staging_stops(self):
        with self.assertRaisesRegex(ValueError, 'after staging'):
            stager.stage({'images': {'sample': locked()}}, runner=FakeCtr(missing_after_tag=True))

    def test_cri_missing_after_staging_stops(self):
        with self.assertRaisesRegex(ValueError, 'CRI missing'):
            stager.stage({'images': {'sample': locked()}}, runner=FakeCtr(cri_missing=True))

    def test_rerun_is_noop(self):
        item = locked();ctr = FakeCtr({item['canonical']: item['digest']})
        self.assertEqual(stager.stage({'images': {'sample': item}}, runner=ctr), [])
        self.assertTrue(all(c[0] == 'crictl' or c[4] == 'list' for c in ctr.commands))

    def test_check_lists_missing_and_mismatch_without_writes(self):
        item = locked();other = locked('other')
        ctr = FakeCtr({item['canonical']: 'sha256:' + 'b' * 64})
        with patch.object(stager.tempfile, 'TemporaryDirectory', side_effect=AssertionError('check wrote temp file')):
            problems = stager.stage({'images': {'sample': item, 'other': other}}, check=True, runner=ctr)
        self.assertEqual([p['reason'] for p in problems], ['digest mismatch', 'missing'])
        self.assertTrue(all(c[4] == 'list' for c in ctr.commands))


class FakeSSH:
    def __init__(self, ctr):
        self.ctr = ctr
        self.calls = []

    def agent(self, lock, check=False):
        self.calls.append(('agent', check))
        problems = stager.stage(lock, check=check, runner=self.ctr)
        return {'status': 'failed' if problems else 'passed', 'images': len(lock['images']), 'problems': problems}

    def run(self, cmd, archive=None):
        self.calls.append(('command', cmd))
        cmd = cmd[2:]  # sudo -n; tests never invoke it
        if cmd[4] == 'import':
            with tarfile.open(archive) as content:
                desc = json.load(content.extractfile('index.json'))['manifests'][0]
            self.ctr.state[desc['annotations']['org.opencontainers.image.ref.name']] = desc['digest']
            return b''
        return self.ctr(cmd).encode()


class ApplicationStaging(unittest.TestCase):
    def fixture(self):
        data = json.loads((dev.COMMON / 'images.lock.json').read_text())
        return {e['canonical']: e['digest'] for e in data['images'].values()}

    def test_fake_ssh_already_staged_is_noop(self):
        ctr = FakeCtr(self.fixture());ssh = FakeSSH(ctr)
        report = ssh_stage.stage_applications('twinfra-dev-cairo-1', 'operator@10.50.0.10', transport=ssh)
        self.assertEqual(report['problems'], [])
        self.assertTrue(all(c[0] == 'crictl' or c[4] == 'list' for c in ctr.commands))

    def test_fake_ssh_digest_mismatch_fails_before_mutation(self):
        state = self.fixture();state[next(iter(state))] = 'sha256:' + 'b' * 64
        ssh = FakeSSH(FakeCtr(state))
        with self.assertRaisesRegex(ValueError, 'mismatch'):
            ssh_stage.stage_applications('twinfra-dev-cairo-1', 'operator@10.50.0.10', transport=ssh)
        self.assertEqual(ssh.calls, [('agent', True)])

    def test_fake_ssh_check_is_readonly(self):
        ctr = FakeCtr();ssh = FakeSSH(ctr)
        report = ssh_stage.stage_applications('twinfra-dev-cairo-1', 'operator@10.50.0.10', check=True, transport=ssh)
        self.assertEqual(len(report['problems']), 10)
        self.assertEqual(ssh.calls, [('agent', True)])
        self.assertTrue(all(c[4] == 'list' for c in ctr.commands))

    def test_wrong_context_or_ssh_target_refused(self):
        for target, context in [('root@foreign', 'twinfra-dev-cairo-1'), ('root@10.50.0.10', 'production')]:
            with self.assertRaisesRegex(ValueError, 'explicit'):
                ssh_stage.SSH(target, context)

    def test_missing_local_archive_fails_before_pulling_upstream(self):
        ctr = FakeCtr();ssh = FakeSSH(ctr)
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError, 'Missing OCI archive'):
                ssh_stage.stage_applications('twinfra-dev-cairo-1', 'operator@10.50.0.10', archive_dir=Path(directory), transport=ssh)
        self.assertEqual(ssh.calls, [('agent', True)])

    def test_ssh_transport_quotes_command_and_uses_stdin(self):
        transport = ssh_stage.SSH('twinfra-operator@10.50.0.10', 'twinfra-dev-cairo-1')
        with patch.object(ssh_stage.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0, b'{}')) as run:
            transport.run(['sudo', '-n', 'python3', '-c', 'print("fixture")'], payload=b'{}')
        args, options = run.call_args
        self.assertEqual(options['input'], b'{}')
        self.assertNotIn('shell', options)
        self.assertIn('StrictHostKeyChecking=yes', args[0])
        self.assertEqual(args[0][-1], "sudo -n python3 -c 'print(\"fixture\")'")

    def test_verified_local_archive_import_and_retag(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory);common = root / 'deploy/common';common.mkdir(parents=True)
            config = json.dumps({'os':'linux','architecture':'amd64'}).encode()
            config_desc = {'digest':'sha256:' + hashlib.sha256(config).hexdigest(),'size':len(config)}
            manifest = json.dumps({'config':config_desc,'layers':[]}).encode()
            sha = 'sha256:' + hashlib.sha256(manifest).hexdigest()
            imported = 'registry.twinfra.example.com/twinfra/postgres:test'
            desc = {'digest':sha,'size':len(manifest),'annotations':{'org.opencontainers.image.ref.name':imported}}
            parts = {'index.json':json.dumps({'manifests':[desc]}).encode(), 'oci-layout':b'{"imageLayoutVersion":"1.0.0"}',
                     'blobs/sha256/' + sha[7:]:manifest, 'blobs/sha256/' + config_desc['digest'][7:]:config}
            archive = root / 'postgresql-pgvector.tar'
            with tarfile.open(archive, 'w') as content:
                for name, raw in parts.items():
                    info = tarfile.TarInfo(name);info.size=len(raw);content.addfile(info,io.BytesIO(raw))
            lock = json.loads((dev.COMMON / 'images.lock.json').read_text())
            pg = lock['images']['postgres'];pg['digest'] = sha
            pg['source'] = pg['source'].split('@')[0] + '@' + sha
            pg['canonical'] = pg['canonical'].split('@')[0] + '@' + sha
            (common / 'images.lock.json').write_text(json.dumps(lock))
            state = {e['canonical']:e['digest'] for n,e in lock['images'].items() if n != 'postgres'}
            ssh = FakeSSH(FakeCtr(state))
            with patch.object(ssh_stage, 'ROOT', root):
                result = ssh_stage.stage_applications('twinfra-dev-cairo-1','operator@10.50.0.10',archive_dir=root,transport=ssh)
            self.assertEqual(result['problems'], [])
            self.assertEqual(ssh.ctr.state[pg['canonical']], sha)
            with self.assertRaisesRegex(ValueError, 'differs'):
                ssh_stage.validate_archive(archive, 'sha256:' + 'b' * 64)


class Certificates(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.files = ca.generate()

    def test_ca_p256_ten_years_and_ca_key_usage(self):
        cert = x509.load_pem_x509_certificate(self.files['ca.crt'])
        self.assertEqual(cert.public_key().curve.name, 'secp256r1')
        self.assertEqual(cert.not_valid_after_utc.year - cert.not_valid_before_utc.year, 10)
        self.assertTrue(cert.extensions.get_extension_for_class(x509.BasicConstraints).value.ca)
        usage = cert.extensions.get_extension_for_class(x509.KeyUsage).value
        self.assertTrue(usage.key_cert_sign and usage.crl_sign)

    def test_leaf_sans_server_auth_and_digital_signature(self):
        ca.validate(self.files, 'cairo-1')
        for name, hosts in ca.sans().items():
            cert = x509.load_pem_x509_certificate(self.files[name + '.crt'])
            self.assertEqual(set(cert.extensions.get_extension_for_class(x509.SubjectAlternativeName).value.get_values_for_type(x509.DNSName)), set(hosts))
            self.assertEqual(list(cert.extensions.get_extension_for_class(x509.ExtendedKeyUsage).value), [ExtendedKeyUsageOID.SERVER_AUTH])
            self.assertTrue(cert.extensions.get_extension_for_class(x509.KeyUsage).value.digital_signature)
            self.assertFalse(cert.extensions.get_extension_for_class(x509.BasicConstraints).value.ca)

    def test_cairo2_gateway_san(self):
        files = ca.generate('cairo-2');ca.validate(files, 'cairo-2')
        cert = x509.load_pem_x509_certificate(files['twinfra-gateway-tls.crt'])
        self.assertEqual(cert.extensions.get_extension_for_class(x509.SubjectAlternativeName).value.get_values_for_type(x509.DNSName), ['console.dev.cairo-2.twinfra.example.com'])

    def test_refuses_output_in_repo_before_any_write(self):
        with patch.object(ca, 'generate', side_effect=AssertionError('generated private keys')):
            with self.assertRaisesRegex(ValueError, 'Git working tree'):
                ca.write(ROOT / '.build/forbidden-ca', 'cairo-1')

    def test_acl_failure_stops_before_key_generation(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            with patch.object(ca, 'outside_repository', return_value=output), patch.object(ca, 'owner_only', side_effect=OSError('fixture ACL failure')), patch.object(ca, 'generate') as generate:
                with self.assertRaises(OSError):
                    ca.write(output, 'cairo-1')
                generate.assert_not_called()
                self.assertEqual(list(output.iterdir()), [])

    def test_other_git_tree_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            repository = Path(directory); (repository / '.git').mkdir()
            with self.assertRaisesRegex(ValueError, 'Git working tree'):
                ca.outside_repository(repository / 'secret-output')

    def test_apply_uses_stdin_names_only_and_preserves_argocd_secret(self):
        commands = []
        def kubectl(cmd, **kwargs):
            commands.append((cmd, kwargs))
            return subprocess.CompletedProcess(cmd, 0, b'secret/argocd-secret' if 'argocd-secret' in cmd and 'get' in cmd else b'')
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            ca.apply(self.files, 'cairo-1', 'twinfra-dev-cairo-1', kubectl)
        self.assertEqual(output.getvalue().splitlines(), list(ca.sans()))
        patch_cmd = next((cmd, opts) for cmd, opts in commands if 'patch' in cmd)
        self.assertEqual(set(json.loads(patch_cmd[1]['input'])), {'data'})
        for cmd, opts in commands:
            self.assertNotIn('PRIVATE KEY', ' '.join(cmd))
            if 'input' in opts:self.assertTrue(cmd[-1] == '-')
        with self.assertRaisesRegex(ValueError, 'matching explicit'):
            ca.apply(self.files, 'cairo-1', 'production', kubectl)


class HTTPSProfile(unittest.TestCase):
    def test_realm_and_routes_use_https_and_secure_cookie(self):
        realm = json.loads((dev.COMMON / 'keycloak-realm.json').read_text())
        client = realm['clients'][0]
        self.assertEqual(client['redirectUris'], ['https://console.dev.cairo-1.twinfra.example.com:18444/console/callback'])
        for r in json.loads((dev.COMMON / 'apisix-routes.json').read_text())['routes']:
            oidc = r['plugins']['openid-connect']
            self.assertTrue(oidc['session']['cookie_secure'])
            self.assertEqual(oidc['redirect_uri'], client['redirectUris'][0])
        self.assertNotIn('http://console', str(dev.gateway()))

    def test_gateway_only_9443_and_no_registry_secret(self):
        service = next(o for o in dev.gateway() if o['kind'] == 'Service')
        self.assertEqual([p['port'] for p in service['spec']['ports']], [9443])
        deployment = next(o for o in dev.gateway() if o['kind'] == 'Deployment')
        self.assertEqual(podspec(deployment)['containers'][0]['readinessProbe']['tcpSocket']['port'], 9443)
        for obj in dev.controllers() + dev.endpoints() + dev.portal() + dev.gateway() + dev.database():
            self.assertNotIn('twinfra-registry-cred', str(obj))

    def test_generated_seed_embeds_verified_lock_and_dev_switch(self):
        row = yaml.safe_load((ROOT / 'vcloud-ssot.yaml').read_text())['addressPlan'][0]
        data = yaml.safe_load(dev.seed(row)['user-data'])
        files = {f['path']: f['content'] for f in data['write_files']}
        self.assertIn('IMAGE_STAGING=true', files['/etc/twinfra-host.env'])
        self.assertIn('MIRROR_REQUIRED=true', files['/etc/twinfra-host.env'])
        self.assertEqual(json.loads(files['/etc/twinfra/bootstrap-images.lock.json']), json.loads((dev.COMMON / 'bootstrap-images.lock.json').read_text()))
        self.assertIn('VCLOUD_CONFIG_FILE=/etc/twinfra-host.env', files['/etc/systemd/system/vcloud-host-bootstrap.service'])


class SharedBootstrap(unittest.TestCase):
    def bash(self, code, **values):
        env = dict(os.environ, VCLOUD_CONFIG_FILE='/nonexistent', **values)
        return subprocess.run([env.get('BASH_BINARY','bash'),'-c','source "$1"; load_config; ' + code,'_',
                               (ROOT / '00-setup-ubuntu-host.sh').as_posix()],env=env,capture_output=True,text=True,encoding='utf-8')

    def test_production_staging_refused_and_false_allowed(self):
        rejected = self.bash('validate_ssot_identity', IMAGE_STAGING='true')
        self.assertEqual(rejected.returncode, 2)
        self.assertEqual(self.bash('validate_ssot_identity', IMAGE_STAGING='false').returncode, 0)

    def test_dev_true_and_false_pass_identity_guard(self):
        for staging in ('true','false'):
            result = self.bash('validate_ssot_identity', IMAGE_STAGING=staging, PLATFORM_PROFILE='dev-cairo-1',
                CLUSTER_NAME='twinfra-dev-cairo-1',CLUSTER_DNS_NAME='twinfra-dev-cairo-1',BASE_DOMAIN='twinfra.example.com',
                IMAGE_REGISTRY='registry.twinfra.example.com',REGISTRY_MIRROR='https://registry.twinfra.example.com')
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_production_renders_byte_identical(self):
        fixture = json.loads((ROOT / 'tests/fixtures/wo29-production-render-sha256.json').read_text())
        for code, expected in fixture['sha256'].items():
            result = self.bash(code, IMAGE_STAGING='false', NODE_IP='192.168.50.10', NODE_NAME='vcloud01')
            self.assertEqual(result.returncode, 0, result.stderr)
            if code == 'render_kubeadm':
                # Existing production behavior selects the host's real resolver file.
                # Keep both pre-change byte hashes rather than normalize away that branch.
                resolver = '/run/systemd/resolve/resolv.conf' if Path('/run/systemd/resolve/resolv.conf').exists() else '/etc/resolv.conf'
                self.assertIn('resolvConf: "' + resolver + '"', result.stdout)
                if resolver != '/etc/resolv.conf':
                    expected = fixture['systemdResolvedKubeadmSHA256']
            self.assertEqual(hashlib.sha256(result.stdout.replace('\r\n','\n').encode()).hexdigest(), expected, code)

    def test_staging_replaces_only_probe_and_false_keeps_it(self):
        code = r'''
set -Eeuo pipefail
WORK_DIR=$(mktemp -d)
trap 'rm -rf -- "$WORK_DIR"' EXIT
STATE_DIR=$WORK_DIR
mkdir() { :; }; touch() { :; }; systemctl() { :; }; timeout() { :; }
containerd() { if [[ $1 == --version ]]; then echo 'containerd github.com/containerd/containerd 1.7.28'; fi; }
write_file() { cat >/dev/null; FILE_CHANGED=false; }
curl() { echo 'mirror-probe'; }
crictl() { if [[ $1 == info ]]; then echo '{"status":{"conditions":[{"type":"RuntimeReady","status":true}]}}'; else echo 'mirror-cri-pull'; fi; }
jq() { "$JQ_BINARY" "$@"; }
stage_bootstrap_images() { echo 'stage-bootstrap'; MIRROR_STATUS=staged-verified; }
configure_containerd
echo "status=$MIRROR_STATUS"
'''
        for value in ('true', 'false'):
            result = self.bash(code, IMAGE_STAGING=value, PLATFORM_PROFILE='dev-cairo-1',
                IMAGE_REGISTRY='registry.twinfra.example.com',REGISTRY_MIRROR='https://registry.twinfra.example.com',
                JQ_BINARY=os.environ.get('JQ_BINARY','jq'))
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual('stage-bootstrap' in result.stdout, value == 'true')
            self.assertEqual('mirror-probe' in result.stdout, value == 'false')
            self.assertEqual('mirror-cri-pull' in result.stdout, value == 'false')


if __name__ == '__main__':
    unittest.main()
