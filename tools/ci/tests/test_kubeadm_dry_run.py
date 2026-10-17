"""Offline transport/command checks; real kubeadm phases execute in hosted CI."""
import hashlib
import importlib.util
import json
from pathlib import Path, PurePosixPath
import tempfile
import subprocess
import unittest
from unittest.mock import patch

import yaml

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('kubeadm_guard', ROOT / 'kubeadm_dry_run.py')
guard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guard)


class KubeadmGuardTests(unittest.TestCase):
    def test_maintenance_preview_uses_config_patch_directory_without_mixed_flags(self):
        repo = ROOT.parents[1]
        with tempfile.TemporaryDirectory() as temp:
            work = Path(temp)
            config = work / 'base.yaml'
            docs = [dict(apiVersion='kubeadm.k8s.io/v1beta4', kind='InitConfiguration',
                         nodeRegistration=dict(name='twinfra-dev-cairo-1'),
                         patches=dict(directory='/private-ci-patches')),
                    dict(apiVersion='kubeadm.k8s.io/v1beta4', kind='ClusterConfiguration',
                         clusterName='twinfra-dev-cairo-1', kubernetesVersion='v1.36.5',
                         controlPlaneEndpoint='api.dev.cairo-1.twinfra.example.com:6443',
                         imageRepository='registry.twinfra.example.com/registry.k8s.io'),
                    dict(kind='KubeletConfiguration')]
            config.write_text(yaml.safe_dump_all(docs))
            def execute(command, log):
                if '--help' in command:
                    return '--config --dry-run'
                if '--dry-run' in command:
                    self.assertNotIn('--patches', command)
                    path = Path(command[command.index('--config') + 1])
                    inputs = list(yaml.safe_load_all(path.read_text()))
                    self.assertEqual(inputs[0]['patches']['directory'], '/private-ci-patches')
                    preview = Path(command[3].split('=', 1)[1])
                    pod = dict(kind='Pod', metadata=dict(name='etcd'), spec=dict(containers=[
                        dict(name='etcd', image='registry.twinfra.example.com/registry.k8s.io/etcd:' +
                             inputs[1]['etcd']['local']['imageTag'],
                             volumeMounts=[dict(name='etcd-certs', readOnly=True)])]))
                    (preview / 'etcd.yaml').write_text(yaml.safe_dump(pod))
                return ''
            with patch.object(guard, 'execute', side_effect=execute), \
                 patch.object(guard.os, 'getuid', return_value=1001, create=True), \
                 patch.object(guard.os, 'getgid', return_value=1001, create=True):
                guard.maintenance_preview(repo, work / 'binary', config, work)
            self.assertEqual(json.loads((work / 'maintenance/summary.json').read_text())['etcdDiff'], 'image only')

    def test_cli_validation_clears_environment_and_uses_script_home_default(self):
        command=guard.cli_command(PurePosixPath('/ci/host.sh'),
            [PurePosixPath('/ci/pinned'),PurePosixPath('/ci/assets/bin')],['argocd','version','--client'])
        self.assertEqual(command[:7],['sudo','-n','env','-i','PATH=/ci/pinned:/ci/assets/bin:/usr/bin:/bin','bash','-c'])
        self.assertEqual(len(command),8)
        self.assertIn('[[ $EUID == 0 && ! -v HOME ]]',command[7])
        self.assertIn('source /ci/host.sh;',command[7])
        self.assertIn('load_config;',command[7])
        self.assertTrue(command[7].endswith('exec argocd version --client'))
        self.assertNotIn('export HOME',command[7])
        self.assertNotIn('HOME=',command[7])

    def test_every_installed_cli_help_and_version_uses_minimal_environment(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);source=root/'source';assets=root/'assets';report=root/'report'
            (source/'tools/ci').mkdir(parents=True);assets.mkdir();report.mkdir()
            script=source/'00-setup-ubuntu-host.sh'
            script.write_text((ROOT.parents[1]/script.name).read_text())
            (source/'tools/ci/host-cli.lock.json').write_text('{"artifacts":{}}')
            (source/'tools/ci/toolchain.lock.json').write_text(json.dumps(dict(artifacts=dict(kubectl=dict(
                url=guard.URL.removesuffix('kubeadm')+'kubectl',sha256='fixture')))))
            def output(command,log,**kwargs):
                self.assertNotIn('env',kwargs)
                if log.name!='cli-install.log':
                    self.assertEqual(command[:2],['sudo','-n'])
                    command=command[2:]
                self.assertEqual(command[:2],['env','-i'])
                self.assertEqual(command[3:5],['bash','-c'])
                self.assertNotIn('HOME=',command[2])
                self.assertNotIn('os.environ',command[5])
                if '--help' in command[5] and 'kubeconform' in command[5]:return 'Usage: kubeconform\n-v version'
                return 'fixture'
            with patch.object(guard,'execute',side_effect=output) as executed,patch.object(guard,'verify_cli_install'),\
                 patch.object(guard,'verify_binary'),patch.object(guard.urllib.request,'urlopen'):
                results=guard.validate_clis(source,assets,report)
            self.assertEqual(len(results),9)
            self.assertEqual(executed.call_count,19)
            summary=json.loads((report/'cli-summary.json').read_text())
            self.assertIn('HOME absent',summary['inputEnvironment'])

    def test_binary_and_published_checksum_are_both_required(self):
        with tempfile.TemporaryDirectory() as temp:
            binary = Path(temp) / 'kubeadm'
            binary.write_bytes(b'fixture')
            digest = hashlib.sha256(b'fixture').hexdigest()
            with patch.object(guard, 'SHA256', digest):
                guard.verify_binary(binary, (digest + '\n').encode())
                with self.assertRaisesRegex(ValueError, 'Published'):
                    guard.verify_binary(binary, b'wrong')
                binary.write_bytes(b'tampered')
                with self.assertRaisesRegex(ValueError, 'binary SHA256'):
                    guard.verify_binary(binary, digest.encode())

    def test_only_sudo_manifest_phases_with_dry_run_output_directory(self):
        commands = guard.phase_commands(PurePosixPath('/ci/kubeadm'), PurePosixPath('/ci/config'), PurePosixPath('/ci/preview'))
        self.assertEqual([c[5:10] for c in commands],
                         [['init', 'phase', 'control-plane', 'all', '--config'],
                          ['init', 'phase', 'etcd', 'local', '--config']])
        for command in commands:
            self.assertEqual(command[:5], ['sudo', '-n', 'env', 'KUBEADM_INIT_DRYRUN_DIR=/ci/preview', '/ci/kubeadm'])
            self.assertEqual(command[-1], '--dry-run')
            self.assertNotIn('preflight', command)

    def test_workflow_runs_real_guard_and_tool_matches_official_pin(self):
        lock = json.loads((ROOT / 'toolchain.lock.json').read_text())['artifacts']['kubeadm']
        self.assertEqual(lock, dict(url=guard.URL, sha256=guard.SHA256, output='bin/kubeadm'))
        workflow = yaml.safe_load((ROOT.parents[1] / '.github/workflows/pr-tests.yaml').read_text())
        step = next(s for s in workflow['jobs']['test']['steps'] if s.get('name', '').startswith('Real kubeadm'))
        self.assertNotIn('if', step)
        self.assertNotIn('continue-on-error', step)
        self.assertIn('--source .ci-control', step['run'])
        self.assertIn('/ci-report/kubeadm-dry-run', step['run'])

    def test_ownership_is_limited_to_four_public_preview_manifests(self):
        command = guard.artifact_owner_command(PurePosixPath('/ci/report/preview'), 1001, 1001)
        self.assertEqual(command[:4], ['sudo', '-n', 'chown', '1001:1001'])
        self.assertEqual(set(command[4:]), {'/ci/report/preview/' + name for name in guard.MANIFESTS})
        self.assertEqual(len(command[4:]), 4)
        self.assertNotIn('-R', command)
        self.assertNotIn('/etc/kubernetes', ' '.join(command))

    def test_version_commands_are_taken_from_shared_validation_and_client_only(self):
        source=ROOT.parents[1]/'00-setup-ubuntu-host.sh'
        commands=guard.version_commands(source)
        self.assertEqual(commands[0],['kubectl','version','--client'])
        self.assertIn(['tkn','version','--component','client'],commands)
        self.assertIn(['cilium','version','--client'],commands)
        self.assertIn(['argocd','version','--client'],commands)
        with tempfile.TemporaryDirectory() as tmp:
            bad=Path(tmp)/'host.sh';bad.write_text(source.read_text().replace('kubectl version --client;',''))
            with self.assertRaisesRegex(ValueError,'Missing/unexpected'):guard.version_commands(bad)

    def test_cli_archive_and_shared_binary_stamp_must_both_match(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);work=root/'work';state=root/'state';binaries=root/'bin'
            for folder in (work,state,binaries):folder.mkdir()
            (work/'release.tar.gz').write_bytes(b'archive');(binaries/'tkn').write_bytes(b'binary')
            archive=hashlib.sha256(b'archive').hexdigest();binary=hashlib.sha256(b'binary').hexdigest()
            lock=dict(artifacts=dict(tkn=dict(asset='release.tar.gz',sha256=archive,version='v0.46.1')))
            (state/'cli-tkn').write_text('v0.46.1/amd64\n'+binary+'\n')
            guard.verify_cli_install(work,state,binaries,lock)
            (binaries/'tkn').write_bytes(b'tampered')
            with self.assertRaisesRegex(ValueError,'stamp/version/binary'):guard.verify_cli_install(work,state,binaries,lock)
            (work/'release.tar.gz').write_bytes(b'tampered')
            with self.assertRaisesRegex(ValueError,'release checksum'):guard.verify_cli_install(work,state,binaries,lock)

    def test_version_nonzero_is_fatal_and_help_allowance_is_explicit(self):
        with tempfile.TemporaryDirectory() as tmp:
            log=Path(tmp)/'result.log'
            result=subprocess.CompletedProcess(['kubeconform'],1,'Usage: kubeconform\n  -v show version\n')
            with patch.object(guard.subprocess,'run',return_value=result):
                with self.assertRaises(RuntimeError):guard.execute(['kubeconform','-v'],log)
                self.assertIn('Usage:',guard.execute(['kubeconform','--help'],log,allowed=(0,1)))
            result.returncode=2
            with patch.object(guard.subprocess,'run',return_value=result):
                with self.assertRaises(RuntimeError):guard.execute(['kubeconform','--help'],log,allowed=(0,1))


if __name__ == '__main__':
    unittest.main()
