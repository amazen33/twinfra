"""Offline transport/command checks; real kubeadm phases execute in hosted CI."""
import hashlib
import importlib.util
import json
from pathlib import Path, PurePosixPath
import tempfile
import unittest
from unittest.mock import patch

import yaml

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('kubeadm_guard', ROOT / 'kubeadm_dry_run.py')
guard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guard)


class KubeadmGuardTests(unittest.TestCase):
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


if __name__ == '__main__':
    unittest.main()
