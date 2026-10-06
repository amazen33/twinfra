"""Regression tests for historical revision selection and fail-closed CI controls."""
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import tarfile
import tempfile
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[1]


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


revisions, staging, checks = (load(name) for name in ('revisions', 'stage_tools', 'run_checks'))
SHA = 'a' * 40


class Controls(unittest.TestCase):
    def test_current_revision(self):
        self.assertEqual(revisions.resolve('', SHA, revisions.REPOSITORY, None)['commit'], SHA)

    def test_merged_pr_uses_merge_not_head(self):
        data = dict(number=1, merged=True, merge_commit_sha=SHA,
                    head=dict(sha='b' * 40), base=dict(repo=dict(full_name=revisions.REPOSITORY)))
        result = revisions.resolve('1', '', revisions.REPOSITORY, lambda _: data)
        self.assertEqual(result, dict(label='requested-pr-1', commit=SHA))

    def test_unmerged_pr_uses_head(self):
        data = dict(number=2, merged=False, merge_commit_sha=None,
                    head=dict(sha=SHA), base=dict(repo=dict(full_name=revisions.REPOSITORY)))
        self.assertEqual(revisions.resolve('2', '', revisions.REPOSITORY, lambda _: data)['commit'], SHA)

    def test_injection_and_invalid_numbers_fail_before_fetch(self):
        for value in ('0', '-1', '1;id', '${{ secrets.TOKEN }}', '1\n2', '0001', '1234567890'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                revisions.resolve(value, SHA, revisions.REPOSITORY, lambda _: self.fail('metadata fetch must not run'))

    def test_foreign_repository_and_mismatched_metadata_fail(self):
        with self.assertRaises(ValueError):
            revisions.resolve('', SHA, 'other/repo', None)
        for number, repository in [(2, revisions.REPOSITORY), (1, 'other/repo')]:
            with self.subTest(number=number, repository=repository), self.assertRaises(ValueError):
                revisions.resolve('1', SHA, revisions.REPOSITORY,
                                  lambda _: dict(number=number, base=dict(repo=dict(full_name=repository))))

    def test_mutable_or_malformed_commits_fail(self):
        for value in ('main', 'refs/pull/1/head', '../main', 'a' * 39, 'A' * 40, None):
            with self.subTest(value=value), self.assertRaises(ValueError):
                revisions.commit(value)

    def test_baseline_is_included_and_deduplicated(self):
        lock = json.loads((ROOT / 'pr-baselines.json').read_text())
        current = revisions.resolve('', SHA, revisions.REPOSITORY, None)
        self.assertEqual(len(revisions.matrix(current, lock)['include']), 2)
        selected = dict(label='requested-pr-1', commit=lock['baselines'][0]['commit'])
        self.assertEqual(len(revisions.matrix(selected, lock)['include']), 1)

    def test_checksum_failure(self):
        self.assertEqual(staging.verified(b'good', hashlib.sha256(b'good').hexdigest()), b'good')
        with self.assertRaises(ValueError):
            staging.verified(b'altered', hashlib.sha256(b'good').hexdigest())

    def test_archive_traversal_and_links_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            archive = Path(temp) / 'artifact.tgz'
            with tarfile.open(archive, 'w:gz') as stream:
                regular = tarfile.TarInfo('bin/tool'); regular.size = 4
                stream.addfile(regular, io.BytesIO(b'tool'))
                link = tarfile.TarInfo('link'); link.type = tarfile.SYMTYPE; link.linkname = '/etc/passwd'
                stream.addfile(link)
            self.assertEqual(staging.extract_member(archive, 'bin/tool'), b'tool')
            for member in ('../escape', '/etc/passwd', 'link'):
                with self.subTest(member=member), self.assertRaises(ValueError):
                    staging.extract_member(archive, member)

    def test_partial_new_modules_do_not_silently_disappear(self):
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp)
            required = ['00-setup-ubuntu-host.sh', 'user-data.yaml', 'tests/test_bootstrap.py',
                        'tools/render_ssot.py', 'tools/render_cloud_init.py', 'docs/module-1-topology.md',
                        'tools/module2.py', 'tests/test_module2.py', 'module-2/vendor/cilium-1.20.2.tgz']
            for name in required:
                target = source / name; target.parent.mkdir(parents=True, exist_ok=True); target.touch()
            self.assertEqual(checks.coverage(source)['module-4b'], 'not_present_in_revision')
            (source / 'module-4b').mkdir()
            with self.assertRaises(ValueError):
                checks.coverage(source)

    def test_zero_tests_skipped_tests_and_failed_suites_rejected(self):
        self.assertEqual(checks.require_complete_tests('Ran 42 tests in 1.0s\n\nOK\n'), 42)
        for output in ('', 'Ran 0 tests in 1s\nOK\n', 'Ran 1 test in 1s\nOK (skipped=1)\n', 'Ran 5 tests in 1s\nFAILED (failures=1)\n'):
            with self.subTest(output=output), self.assertRaises(ValueError):
                checks.require_complete_tests(output)

    def test_every_artifact_is_https_sha256_locked(self):
        lock = json.loads((ROOT / 'toolchain.lock.json').read_text())
        for artifact in lock['artifacts'].values():
            self.assertTrue(artifact['url'].startswith('https://'))
            self.assertRegex(artifact['sha256'], r'^[0-9a-f]{64}$')
            self.assertNotIn('latest', artifact['url'])

    def test_workflow_uses_read_only_permissions_and_sha_pins(self):
        path = ROOT.parents[1] / '.github/workflows/pr-tests.yaml'
        workflow = yaml.safe_load(path.read_text())
        self.assertEqual(workflow['permissions'], {'contents': 'read', 'pull-requests': 'read'})
        self.assertNotIn('pull_request_target', path.read_text())
        for job in workflow['jobs'].values():
            self.assertEqual(job['runs-on'], 'ubuntu-24.04')
            for step in job.get('steps', []):
                if 'uses' in step:
                    self.assertRegex(step['uses'], r'^[a-z-]+/[a-z-]+@[0-9a-f]{40}$')
                    if step['uses'].startswith('actions/checkout@'):
                        self.assertFalse(step['with']['persist-credentials'])

    def test_libraries_and_mermaid_lock_match_exact_versions(self):
        package = json.loads((ROOT / 'mermaid/package.json').read_text())
        lock = json.loads((ROOT / 'mermaid/package-lock.json').read_text())
        self.assertEqual(package['dependencies'], lock['packages']['']['dependencies'])
        for version in package['dependencies'].values():
            self.assertRegex(version, r'^\d+\.\d+\.\d+$')
        for line in (ROOT / 'requirements.txt').read_text().splitlines():
            if line and not line.startswith('#'):
                self.assertRegex(line, r'^[A-Za-z]+==\d+\.\d+\.\d+$')


if __name__ == '__main__':
    unittest.main(verbosity=2)
