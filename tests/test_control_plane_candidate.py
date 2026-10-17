"""WO-40c is offline: synthetic configuration/manifest and transport fixtures."""
import contextlib
import copy
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import control_plane_candidate as guard

ROOT = Path(__file__).resolve().parents[1]


def fixtures():
    cluster = dict(apiVersion=guard.API, kind='ClusterConfiguration',
                   kubernetesVersion='v1.36.5', clusterName='twinfra-dev-cairo-1',
                   controlPlaneEndpoint='api.dev.cairo-1.twinfra.example.com:6443',
                   imageRepository='registry.twinfra.example.com/registry.k8s.io',
                   networking=dict(podSubnet='10.110.0.0/16', serviceSubnet='10.111.0.0/16'),
                   dns=dict(imageTag='v1.14.2'),
                   etcd=dict(local=dict(imageTag='3.6.8-0', dataDir='/var/lib/etcd')))
    base = [dict(apiVersion=guard.API, kind='InitConfiguration',
                 nodeRegistration=dict(name='twinfra-dev-cairo-1'),
                 patches=dict(directory='/var/lib/vcloud-host/kubeadm-patches')),
            cluster, dict(apiVersion='kubelet.config.k8s.io/v1beta1',
                          kind='KubeletConfiguration', cgroupDriver='systemd')]
    cm = dict(kind='ConfigMap', metadata=dict(name='kubeadm-config', namespace='kube-system'),
              data=dict(ClusterConfiguration=guard.encoded(cluster), unrelated='preserved'))
    return base, copy.deepcopy(cluster), cm, guard.read(ROOT / 'deploy/common/bootstrap-images.lock.json', ROOT)


def etcd():
    return dict(kind='Pod', metadata=dict(name='etcd'), spec=dict(hostNetwork=True,
                containers=[dict(name='etcd', image='old', command=['etcd', '--name=twinfra-dev-cairo-1'],
                                 volumeMounts=[dict(name='etcd-certs', mountPath='/etc/kubernetes/pki/etcd', readOnly=True)])]))


class CandidateTests(unittest.TestCase):
    def test_exactly_two_tags_and_all_other_documents_unchanged(self):
        base, stored, _, lock = fixtures()
        saved = copy.deepcopy(base)
        result, cluster = guard.candidate(base, stored, lock)
        self.assertEqual(guard.changes(base[1], cluster), guard.TAG_PATHS)
        self.assertEqual(result[0], base[0])
        self.assertEqual(result[2], base[2])
        self.assertEqual(base, saved)

    def test_injected_non_tag_candidate_change_is_refused(self):
        base, stored, _, lock = fixtures()
        real = guard.set_tag
        def tamper(value, component, tag):
            real(value, component, tag)
            value['networking']['podSubnet'] = '10.0.0.0/8'
        with patch.object(guard, 'set_tag', side_effect=tamper):
            with self.assertRaisesRegex(ValueError, 'unapproved field'):
                guard.candidate(base, stored, lock)

    def test_stored_and_base_differ_elsewhere_refused(self):
        for path in [('networking', 'podSubnet'), ('etcd', 'local', 'dataDir'),
                     ('dns', 'imageRepository'), ('certificatesDir',)]:
            with self.subTest(path=path):
                base, stored, _, lock = fixtures()
                node = stored
                for part in path[:-1]:
                    node = node.setdefault(part, {})
                node[path[-1]] = 'different'
                with self.assertRaisesRegex(ValueError, 'outside tags'):
                    guard.candidate(base, stored, lock)

    def test_even_materialized_default_difference_is_not_silently_ignored(self):
        base, stored, _, lock = fixtures()
        stored['certificatesDir'] = '/etc/kubernetes/pki'
        with self.assertRaisesRegex(ValueError, 'certificatesDir'):
            guard.candidate(base, stored, lock)

    def test_host_tags_may_already_be_newer_than_stored(self):
        base, stored, _, lock = fixtures()
        for key, tag in guard.TAGS.items():
            guard.set_tag(base[1], key, tag)
        result, _ = guard.candidate(base, stored, lock)
        self.assertEqual(result, base)

    def test_missing_tags_are_added_without_ignoring_other_nested_fields(self):
        base, stored, _, lock = fixtures()
        del base[1]['dns']
        del stored['etcd']['local']['imageTag']
        result, cluster = guard.candidate(base, stored, lock)
        self.assertEqual(cluster['dns']['imageTag'], 'v1.14.7')
        self.assertEqual(result[1]['etcd']['local']['dataDir'], '/var/lib/etcd')

    def test_duplicate_or_missing_or_unknown_document_refused(self):
        for mutate in (lambda b: b.append(b[0]), lambda b: b.pop(), lambda b: b.append(dict(kind='Secret'))):
            base, stored, _, lock = fixtures()
            mutate(base)
            with self.assertRaises(ValueError):
                guard.candidate(base, stored, lock)

    def test_foreign_identity_and_patch_directory_refused(self):
        for field in ('clusterName', 'kubernetesVersion', 'controlPlaneEndpoint', 'imageRepository'):
            base, stored, _, lock = fixtures()
            base[1][field] = 'foreign'
            with self.assertRaises(ValueError):
                guard.candidate(base, stored, lock)
        base, stored, _, lock = fixtures()
        base[0]['patches']['directory'] = '/other'
        with self.assertRaisesRegex(ValueError, 'patches'):
            guard.candidate(base, stored, lock)

    def test_image_selection_comes_from_unchanged_lock(self):
        _, _, _, lock = fixtures()
        self.assertTrue(guard.image(lock, 'coredns', True).endswith('@' + lock['images']['coredns']['digest']))
        lock['images']['etcd']['canonical'] = 'upstream:latest'
        with self.assertRaisesRegex(ValueError, 'lock'):
            guard.image(lock, 'etcd')

    def test_candidate_diff_and_per_component_cas_and_rollback(self):
        base, stored, cm, lock = fixtures()
        with tempfile.TemporaryDirectory() as temp, contextlib.redirect_stdout(io.StringIO()) as log:
            out = Path(temp) / 'candidate'
            guard.write_candidate(base, stored, cm, lock, out, Path(temp))
            self.assertIn('3.6.15-0', log.getvalue())
            self.assertIn('v1.14.7', log.getvalue())
            first = guard.read(out / 'etcd-configmap.patch.json', out)
            second = guard.read(out / 'dns-configmap.patch.json', out)
            self.assertEqual(first[0]['value'], cm['data']['ClusterConfiguration'])
            self.assertEqual(second[0]['value'], first[1]['value'])
            etcd_cluster = json.loads(first[1]['value'])
            final_cluster = json.loads(second[1]['value'])
            self.assertEqual(guard.changes(stored, etcd_cluster), {('etcd', 'local', 'imageTag')})
            self.assertEqual(guard.changes(etcd_cluster, final_cluster), {('dns', 'imageTag')})
            for component, forward in [('etcd', first), ('dns', second)]:
                backward = guard.read(out / ('rollback-' + component + '-configmap.patch.json'), out)
                self.assertEqual(backward[0]['value'], forward[1]['value'])
                self.assertEqual(backward[1]['value'], forward[0]['value'])
            with self.assertRaisesRegex(ValueError, 'already exists'):
                guard.write_candidate(base, stored, cm, lock, out, Path(temp))

    def test_saved_configmap_and_parsed_export_must_match(self):
        base, stored, cm, lock = fixtures()
        stored['clusterName'] = 'edited'
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaisesRegex(ValueError, 'saved ConfigMap'):
                guard.write_candidate(base, stored, cm, lock, Path(temp) / 'out', Path(temp))
            self.assertFalse((Path(temp) / 'out').exists())

    def test_yaml_stored_config_uses_existing_yq_read_only(self):
        _, stored, cm, _ = fixtures()
        cm['data']['ClusterConfiguration'] = 'kind: ClusterConfiguration'
        result = guard.subprocess.CompletedProcess([], 0, json.dumps(stored), '')
        with patch.object(guard.subprocess, 'run', return_value=result) as run:
            self.assertEqual(guard.stored_document(cm), stored)
        self.assertEqual(run.call_args.args[0], ['yq', 'eval', '-o=json', '.', '-'])
        self.assertTrue(run.call_args.kwargs['check'])

    def test_duplicate_json_keys_refused(self):
        with tempfile.TemporaryDirectory() as temp:
            file = Path(temp) / 'input.json'
            file.write_text('{"kind":"a","kind":"b"}')
            with self.assertRaisesRegex(ValueError, 'Duplicate'):
                guard.read(file, Path(temp))

    def test_inputs_and_output_cannot_escape_maintenance_directory(self):
        with tempfile.TemporaryDirectory() as temp:
            work = Path(temp) / 'work'
            work.mkdir()
            outside = Path(temp) / 'outside.json'
            outside.write_text('{}')
            with self.assertRaisesRegex(ValueError, 'maintenance directory'):
                guard.read(outside, work)
            traversal = work / '..' / 'outside.json'
            with self.assertRaisesRegex(ValueError, 'Unsafe maintenance path'):
                guard.read(traversal, work)
            base, stored, cm, lock = fixtures()
            out = Path(temp) / 'outside-output'
            with self.assertRaisesRegex(ValueError, 'maintenance directory'):
                guard.write_candidate(base, stored, cm, lock, out, work)
            self.assertFalse(out.exists())

    def test_cli_failure_is_nonzero_and_creates_no_candidate(self):
        with tempfile.TemporaryDirectory() as temp, contextlib.redirect_stderr(io.StringIO()) as errors:
            missing = str(Path(temp) / 'missing')
            status = guard.main(['--lock', missing, 'image', 'etcd'])
        self.assertEqual(status, 1)
        self.assertIn('STOP:', errors.getvalue())


class PreviewTests(unittest.TestCase):
    def test_only_image_change_passes(self):
        live = etcd()
        preview = copy.deepcopy(live)
        preview['spec']['containers'][0]['image'] = 'new'
        with contextlib.redirect_stdout(io.StringIO()):
            guard.verify_etcd([live], [preview], 'new')

    def test_any_other_manifest_change_refused(self):
        for mutate in (lambda p: p['metadata'].update(name='foreign'),
                       lambda p: p['spec'].update(hostNetwork=False),
                       lambda p: p['spec']['containers'][0].update(command=['etcd']),
                       lambda p: p['spec']['containers'][0]['volumeMounts'][0].update(readOnly=False),
                       lambda p: p['spec']['containers'][0]['volumeMounts'][0].update(mountPath='/other')):
            live = etcd()
            preview = copy.deepcopy(live)
            preview['spec']['containers'][0]['image'] = 'new'
            mutate(preview)
            with self.assertRaisesRegex(ValueError, 'beyond image'):
                guard.verify_etcd(live, preview, 'new')

    def test_missing_read_only_mount_and_wrong_image_refused(self):
        live = etcd()
        live['spec']['containers'][0]['volumeMounts'] = []
        with self.assertRaisesRegex(ValueError, 'certificate mount'):
            guard.verify_etcd(live, live, 'old')
        first, second = etcd(), etcd()
        with self.assertRaisesRegex(ValueError, 'image/container'):
            guard.verify_etcd(first, second, 'other')

    def test_api_mirror_pod_runtime_metadata_is_not_ignored(self):
        live = etcd()
        preview = copy.deepcopy(live)
        live['metadata']['uid'] = 'server-owned'
        with self.assertRaisesRegex(ValueError, 'beyond image'):
            guard.verify_etcd(live, preview, 'old')

    def test_runbook_commands_are_single_command_blocks_and_no_full_bootstrap(self):
        import re
        text = (ROOT / 'docs/maintenance/etcd-coredns-2026-10.md').read_text(encoding='utf-8')
        blocks = re.findall(r'```(?:bash|powershell)\n(.*?)\n```', text, re.S)
        self.assertGreater(len(blocks), 30)
        for block in blocks:
            self.assertEqual(len(block.splitlines()), 1, block)
            self.assertNotRegex(block, r'kubeadm (?:reset|upgrade|init(?! phase))\b')
        self.assertIn('set image deployment/coredns', text)
        self.assertIn('base-configuration', text)

    def test_documented_jq_digest_and_image_assertions_execute(self):
        import re
        import shlex
        import shutil
        import subprocess
        text = (ROOT / 'docs/maintenance/etcd-coredns-2026-10.md').read_text(encoding='utf-8')
        commands = re.findall(r'```bash\n(jq -e .*?)\n```', text)
        self.assertEqual(len(commands), 4)
        lock = fixtures()[3]
        def pod(component):
            row = lock['images'][component]
            return dict(spec=dict(containers=[dict(name=component, image=row['canonical'])]),
                        status=dict(containerStatuses=[dict(name=component, imageID='containerd://' + row['canonical'].split(':')[0] + '@' + row['amd64Digest'])]))
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            (directory / 'bootstrap-images.lock.json').write_text(json.dumps(lock))
            (directory / 'etcd.after.json').write_text(json.dumps(pod('etcd')))
            (directory / 'dns.after.json').write_text(json.dumps(dict(items=[pod('coredns')])))
            for command in commands:
                argv = shlex.split(command.replace('$MAINT', directory.as_posix()))
                argv[0] = shutil.which('jq') or str(ROOT / '.tools/jq/jq.exe')
                result = subprocess.run(argv, text=True, capture_output=True, check=False)
                self.assertEqual(result.returncode, 0, result.stderr)
            (directory / 'etcd.after.json').write_text(json.dumps(pod('coredns')))
            argv = shlex.split(commands[0].replace('$MAINT', directory.as_posix()))
            argv[0] = shutil.which('jq') or str(ROOT / '.tools/jq/jq.exe')
            bad = subprocess.run(argv, text=True, capture_output=True, check=False)
            self.assertNotEqual(bad.returncode, 0)


if __name__ == '__main__':
    unittest.main()
