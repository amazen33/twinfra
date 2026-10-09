"""Registry outage, DNS migration and offline-deployment guard regressions."""
import copy
import gzip
import io
import json
import os
from pathlib import Path
import ssl
import subprocess
import sys
import tempfile
import tomllib
import unittest
from unittest.mock import MagicMock, patch
from urllib.parse import urlsplit

import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools'))
import airgap
import node_registry as registry
import wsl_platform


class RegistryTests(unittest.TestCase):
    def test_all_upstreams_map_canonical_api_roots_without_public_fallback(self):
        for upstream in registry.UPSTREAMS:
            with self.subTest(upstream=upstream):
                data = tomllib.loads(registry.hosts_config(upstream, '/etc/ssl/vcloud-ca.crt'))
                url = 'https://' + registry.REGISTRY + '/v2/' + upstream
                self.assertEqual(data['server'], url)
                self.assertTrue(data['override_path'])
                self.assertEqual(data['capabilities'], ['pull', 'resolve'])
                host = data['host'][url]
                self.assertTrue(host['override_path'])
                self.assertEqual(host['ca'], data['ca'])
                self.assertNotIn('skip_verify', host)
                request = urlsplit(url).path + '/argoproj/argocd/manifests/v3.5.3'
                self.assertEqual(request, '/v2/' + upstream + '/argoproj/argocd/manifests/v3.5.3')

    def test_canonical_and_default_names_do_not_double_prefix(self):
        files = registry.registry_files()
        self.assertEqual(len(files), len(registry.UPSTREAMS) + 2)
        for name in ('_default', registry.REGISTRY):
            data = tomllib.loads(files[name + '/hosts.toml'])
            self.assertEqual(data['server'], 'https://' + registry.REGISTRY)
            self.assertNotIn('override_path', data)

    def test_invalid_registry_and_ca_inputs_rejected(self):
        with self.assertRaises(ValueError):
            registry.hosts_config('untrusted.example.com')
        for path in ('relative.crt', '/tmp/a"\nserver=bad', '/tmp/a\\b'):
            with self.subTest(path=path), self.assertRaises(ValueError):
                registry.hosts_config('quay.io', path)

    def test_config_preserves_other_runtime_fields_and_is_idempotent(self):
        for version, plugin in ((2, 'io.containerd.grpc.v1.cri'), (3, 'io.containerd.cri.v1.images')):
            text = 'version = ' + str(version) + '\n[plugins."' + plugin + '".registry]\n  config_path = ""\n[plugins."runtime"]\nkeep = "nvidia"\n'
            result = registry.cri_config(text)
            self.assertEqual(tomllib.loads(result)['plugins']['runtime']['keep'], 'nvidia')
            self.assertEqual(result, registry.cri_config(result))

    def test_imported_or_disabled_cri_configuration_rejected(self):
        for text in ('version=3\nimports=["/tmp/other.toml"]', 'version=3\ndisabled_plugins=["cri"]', 'version=1'):
            with self.subTest(text=text), self.assertRaises(ValueError):
                registry.cri_config(text)

    def test_dns_fallback_preserves_aliases_and_is_idempotent(self):
        text = '127.0.0.1 localhost\n10.0.0.1 ' + registry.REGISTRY + ' keep.example.com\n'
        result = registry.hosts_fallback(text, '10.0.0.2')
        self.assertIn('10.0.0.1\tkeep.example.com', result)
        self.assertIn('10.0.0.2\t' + registry.REGISTRY, result)
        self.assertEqual(result, registry.hosts_fallback(result, '10.0.0.2'))
        with self.assertRaises(ValueError):
            registry.hosts_fallback(text, '0.0.0.0')

    def test_failed_tls_prevents_any_dns_or_config_write(self):
        with tempfile.TemporaryDirectory() as directory:
            config, hosts = Path(directory) / 'config.toml', Path(directory) / 'hosts'
            config.write_text('version=3\n')
            hosts.write_text('127.0.0.1 localhost\n')
            with patch.object(registry, 'tls_probe', side_effect=ssl.SSLCertVerificationError()), self.assertRaises(ssl.SSLCertVerificationError):
                registry.configure(config, Path(directory) / 'certs', hosts, address='10.0.0.2', apply=True)
            self.assertEqual(config.read_text(), 'version=3\n')
            self.assertEqual(hosts.read_text(), '127.0.0.1 localhost\n')

    def test_configuration_repeat_keeps_first_backup(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(registry, 'network_status', return_value={'dns': 'failed'}):
            config, hosts = Path(directory) / 'config.toml', Path(directory) / 'hosts'
            original = 'version=3\n'
            config.write_text(original)
            hosts.write_text('127.0.0.1 localhost\n')
            first = registry.configure(config, Path(directory) / 'certs', hosts, apply=True)
            second = registry.configure(config, Path(directory) / 'certs', hosts, apply=True)
            self.assertTrue(first['daemonConfigChanged'])
            self.assertEqual(first['caFile'], '')
            self.assertFalse(second['daemonConfigChanged'])
            self.assertEqual(config.with_name('config.toml.vcloud-registry-original').read_text(), original)

    def test_custom_auth_and_existing_ca_cannot_be_dropped(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'hosts.toml'
            for original in ('[host."https://mirror"]\nheader={Authorization="secret"}\n',
                             registry.MARKER + '\n[host."https://mirror"]\nheader={Authorization="secret"}\n',
                             'server="https://mirror"\nca="/etc/existing.crt"\n'):
                path.write_text(original)
                with self.assertRaises(ValueError):
                    registry.write_owned(path, registry.hosts_config())
                self.assertEqual(path.read_text(), original)

    def test_symlink_configuration_is_rejected(self):
        with patch.object(Path, 'is_symlink', return_value=True), self.assertRaises(ValueError):
            registry.write_owned(Path('/etc/hosts'), 'replacement')

    def test_missing_mirror_alias_is_a_cache_failure(self):
        image = airgap.argocd_image()
        result = registry.cache_status([image], {'images': [{'repoDigests': [image.replace(registry.REGISTRY + '/', '')]}]})
        self.assertEqual(result['status'], 'failed')
        self.assertEqual(result['missing'], [image])

    def test_exact_cached_digest_is_accepted(self):
        image = airgap.argocd_image()
        self.assertEqual(registry.cache_status([image], {'images': [{'repoDigests': [image]}]})['status'], 'passed')
        with self.assertRaises(ValueError):
            registry.cache_status([], {'images': []})
        for result in ({}, {'images': ['malformed']}, []):
            with self.subTest(result=result), self.assertRaises(ValueError):
                registry.cache_status([image], result)

    def test_tls_probe_preserves_registry_sni_and_checks_api_status(self):
        context = MagicMock()
        response = MagicMock()
        with patch.object(registry.ssl, 'create_default_context', return_value=context) as create, \
             patch.object(registry.socket, 'create_connection'), patch.object(registry.http.client, 'HTTPResponse', return_value=response):
            response.status = 401
            self.assertEqual(registry.tls_probe('10.0.0.2', '/etc/public-ca.crt'), 401)
            create.assert_called_with(cafile='/etc/public-ca.crt')
            self.assertEqual(context.wrap_socket.call_args.kwargs['server_hostname'], registry.REGISTRY)
            response.status = 403
            with self.assertRaises(ValueError):
                registry.tls_probe('10.0.0.2', '/etc/public-ca.crt')

    def test_registry_outage_is_tolerated_only_with_complete_cache(self):
        for mode, cached, expected in (([], 'passed', 1), (['--cache-only'], 'passed', 0), (['--cache-only'], 'failed', 1)):
            with self.subTest(mode=mode, cached=cached), patch.object(sys, 'argv', ['node_registry.py', 'check', *mode]), \
                 patch.object(registry, 'network_status', return_value={'dns': 'failed', 'tcpTls443': 'not_checked'}), \
                 patch.object(registry, 'inspect_cache', return_value={'status': cached}), patch('sys.stdout', new=io.StringIO()):
                self.assertEqual(registry.main(), expected)

    def test_dns_failure_does_not_attempt_tcp(self):
        with patch.object(registry.subprocess, 'run', side_effect=subprocess.CalledProcessError(2, ['getent'])), patch.object(registry, 'tls_probe') as tls:
            self.assertEqual(registry.network_status()['dns'], 'failed')
            tls.assert_not_called()

    def test_cache_inspection_uses_explicit_socket_and_never_pulls(self):
        image = airgap.argocd_image()
        with patch.object(registry.shutil, 'which', return_value='/usr/bin/crictl'), patch.object(registry.subprocess, 'run') as run:
            run.return_value.stdout = json.dumps({'images': [{'repoDigests': [image]}]})
            self.assertEqual(registry.inspect_cache([image], 'unix:///run/containerd/containerd.sock')['status'], 'passed')
            self.assertEqual(run.call_args.args[0][-3:], ['images', '-o', 'json'])
            self.assertNotIn('pull', run.call_args.args[0])
        with self.assertRaises(ValueError):
            registry.inspect_cache([image], 'tcp://remote:1234')

    def test_wsl_core_uses_the_same_immutable_image_and_fallback(self):
        objects = wsl_platform.infrastructure()
        for obj in objects:
            spec = wsl_platform.podspec(obj)
            if spec and obj['metadata']['name'].startswith('argocd-'):
                self.assertIn({'name': 'vcloud-registry-cred'}, spec['imagePullSecrets'])
                for group in ('containers', 'initContainers'):
                    for container in spec.get(group, []):
                        self.assertEqual(container['imagePullPolicy'], 'IfNotPresent')
                        if '/argoproj/argocd' in container['image']:
                            self.assertEqual(container['image'], airgap.argocd_image())

    def test_rendered_security_and_policy_drift_are_rejected(self):
        obj = next(o for o in wsl_platform.infrastructure() if o['metadata']['name'] == 'argocd-repo-server' and o['kind'] == 'Deployment')
        self.assertEqual(airgap.audit([obj]), 1)
        for field, value in (('imagePullPolicy', 'Always'), ('image', 'registry.vcloud.example.com/quay.io/argoproj/argocd:v3.5.3')):
            bad = copy.deepcopy(obj)
            bad['spec']['template']['spec']['containers'][0][field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                airgap.audit([bad])
        bad = copy.deepcopy(obj)
        bad['spec']['template']['spec']['containers'][0]['securityContext']['privileged'] = True
        with self.assertRaises(ValueError):
            airgap.audit([bad])
        with self.assertRaises(ValueError):
            airgap.audit([obj], require_full=True)

    def test_pinned_base_and_image_inventory_are_consistent(self):
        airgap.check_base()
        lock = json.loads((ROOT / 'deploy/registry-images.lock.json').read_text())
        self.assertEqual(registry.required_images(), sorted(v['canonical'] for v in lock['images'].values()))
        for obj in yaml.safe_load_all(airgap.BASE.read_text()):
            spec = wsl_platform.podspec(obj)
            if spec:
                for group in ('containers', 'initContainers'):
                    for container in spec.get(group, []):
                        self.assertEqual(container['imagePullPolicy'], 'IfNotPresent')

    def test_valkey_base_and_every_overlay_render_without_upstream_cache_image(self):
        kustomize = os.environ.get('KUSTOMIZE_BINARY', 'kustomize')
        paths = [ROOT / 'deploy/kustomize/base/argocd']
        paths += [p.parent for p in sorted((ROOT / 'deploy/kustomize/overlays').glob('*/kustomization.yaml'))]
        for path in paths:
            with self.subTest(path=path):
                output = subprocess.check_output([kustomize, 'build', str(path)], text=True)
                self.assertNotIn('library/redis', output)
                objects = [obj for obj in yaml.safe_load_all(output) if obj]
                mirror = 'overlays' in path.parts
                airgap.check_cache(objects, mirror)
                cache = next(obj for obj in objects if obj['kind'] == 'Deployment'
                             and obj['metadata']['name'] == 'argocd-redis')
                spec = cache['spec']['template']['spec']
                container = spec['containers'][0]
                self.assertEqual(spec['securityContext']['runAsUser'], 999)
                self.assertTrue(container['securityContext']['readOnlyRootFilesystem'])
                self.assertEqual(container['args'], ['--save', '', '--appendonly', 'no',
                                                     '--requirepass $(REDIS_PASSWORD)'])
                self.assertEqual(container['env'][0]['valueFrom']['secretKeyRef'],
                                 {'key': 'auth', 'name': 'argocd-redis'})
                bad = copy.deepcopy(cache)
                bad['spec']['template']['spec']['containers'][0]['image'] = 'public.ecr.aws/docker/library/redis:8.2.3-alpine'
                with self.assertRaisesRegex(ValueError, 'deployable output'):
                    airgap.check_cache([bad], mirror)

    def test_preserved_upstream_sources_still_contain_transform_match_image(self):
        lock = json.loads(airgap.LOCK.read_text())
        source = 'public.ecr.aws/docker/library/redis:8.2.3-alpine'
        self.assertIn(source, airgap.BASE.read_text())
        self.assertIn(source, gzip.decompress((ROOT / lock['manifest']['vendor']).read_bytes()).decode())
        airgap.check_base()  # Preserved source and its reviewed archive must not drift.

    def test_valkey_pin_age_and_active_inventories(self):
        from datetime import datetime, date
        lock = json.loads(airgap.LOCK.read_text())['images']['valkey']
        self.assertEqual(lock['tag'], '8.1.10-alpine')
        self.assertTrue(lock['source'].endswith('@' + lock['digest']))
        self.assertTrue(lock['canonical'].endswith('@' + lock['digest']))
        published = datetime.fromisoformat(lock['publishedAt']).date()
        self.assertGreaterEqual((date.fromisoformat(lock['verifiedOn']) - published).days, 14)
        for path in ('deploy/registry-images.lock.json', 'deploy/required-images.txt',
                     'lab/wsl/platform-images.txt', 'security/licence-register.json',
                     'security/licence-baseline.json'):
            self.assertNotIn('library/redis', (ROOT / path).read_text())


if __name__ == '__main__':
    unittest.main(verbosity=2)
