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
        self.assertEqual(len(revisions.matrix(current, lock)['include']), len(lock['baselines']) + 1)
        selected = dict(label='requested-pr-1', commit=lock['baselines'][0]['commit'])
        self.assertEqual(len(revisions.matrix(selected, lock)['include']), len(lock['baselines']))

    def test_reviewed_merged_pr_baselines_are_immutable(self):
        lock = json.loads((ROOT / 'pr-baselines.json').read_text())
        self.assertEqual([p['number'] for p in lock['baselines']], [1, 2, 3, 4, 5, 6])
        for baseline in lock['baselines']:
            self.assertRegex(baseline['commit'], r'^[a-f0-9]{40}$')
            self.assertEqual(baseline['url'], f"https://github.com/amazen33/vCloud/pull/{baseline['number']}")

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

    def baseline_fixture(self, source):
        for name in ('00-setup-ubuntu-host.sh', 'user-data.yaml', 'tests/test_bootstrap.py',
                     'tools/render_ssot.py', 'tools/render_cloud_init.py', 'docs/module-1-topology.md',
                     'tools/module2.py', 'tests/test_module2.py', 'module-2/vendor/cilium-1.20.2.tgz'):
            target = source / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.touch()

    def test_document_only_roadmap_does_not_require_future_automation(self):
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp)
            self.baseline_fixture(source)
            (source / 'MILESTONES.md').touch()
            self.assertEqual(checks.coverage(source)['roadmap-automation'], 'not_present_in_revision')
            (source / 'tools/create_roadmap_issues.py').touch()
            with self.assertRaisesRegex(ValueError, 'Incomplete roadmap-automation'):
                checks.coverage(source)
            (source / 'tests/test_roadmap_issues.py').touch()
            self.assertEqual(checks.coverage(source)['roadmap-automation'], 'present')

    def test_old_wsl_profile_does_not_require_future_proxy_repair(self):
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp)
            self.baseline_fixture(source)
            for name in checks.OPTIONAL['lab/wsl']:
                target = source / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.touch()
            self.assertEqual(checks.coverage(source)['lab/wsl'], 'present')
            self.assertEqual(checks.coverage(source)['lab/wsl/proxy-marks'], 'not_present_in_revision')
            (source / 'tools/wsl_proxy_marks.py').touch()
            with self.assertRaisesRegex(ValueError, 'Incomplete lab/wsl/proxy-marks'):
                checks.coverage(source)
            for name in checks.OPTIONAL['lab/wsl/proxy-marks']:
                (source / name).touch()
            self.assertEqual(checks.coverage(source)['lab/wsl/proxy-marks'], 'present')

    def test_zero_tests_skipped_tests_and_failed_suites_rejected(self):
        self.assertEqual(checks.require_complete_tests('Ran 42 tests in 1.0s\n\nOK\n'), 42)
        for output in ('', 'Ran 0 tests in 1s\nOK\n', 'Ran 1 test in 1s\nOK (skipped=1)\n', 'Ran 5 tests in 1s\nFAILED (failures=1)\n'):
            with self.subTest(output=output), self.assertRaises(ValueError):
                    checks.require_complete_tests(output)

    def test_host_routing_bundle_is_optional_only_for_historical_revisions(self):
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp)
            self.baseline_fixture(source)
            self.assertEqual(checks.coverage(source)['lab/wsl/values'], 'not_present_in_revision')
            (source / 'tools/check_host_routing.py').touch()
            with self.assertRaisesRegex(ValueError, 'Incomplete lab/wsl/values'):
                checks.coverage(source)
            for name in checks.OPTIONAL['lab/wsl/values']:
                path = source / name; path.parent.mkdir(parents=True, exist_ok=True); path.touch()
            for name in checks.OPTIONAL['lab/wsl']:
                path = source / name; path.parent.mkdir(parents=True, exist_ok=True); path.touch()
            self.assertEqual(checks.coverage(source)['lab/wsl/values'], 'present')

    def test_candidate_routing_guard_runs_before_historical_gates(self):
        workflow = yaml.safe_load((ROOT.parents[1] / '.github/workflows/pr-tests.yaml').read_text())
        steps = workflow['jobs']['test']['steps']
        guard_step = next(s for s in steps if s.get('name') == 'Validate candidate WSL routing boundary')
        self.assertNotIn('if', guard_step)
        self.assertIn('.ci-control/tools/check_host_routing.py --root .ci-control', guard_step['run'])
        self.assertLess(steps.index(guard_step), next(i for i, s in enumerate(steps) if s.get('name') == 'Run offline module gates and air-gapped Kustomize/schema/policy checks'))

    def test_hpc_coverage_cannot_be_omitted(self):
        self.assertIn('module-5b', checks.OPTIONAL)
        self.assertIn('tests/test_module5b.py', checks.OPTIONAL['module-5b'])
        self.assertIn('tests/module5b-alerts.test.yaml', checks.OPTIONAL['module-5b'])

    def test_airgap_coverage_and_tools_cannot_be_omitted(self):
        self.assertIn('tests/ci/test_airgap.py', checks.OPTIONAL['deploy/kustomize'])
        self.assertIn('tests/ci/policy/airgap.rego', checks.OPTIONAL['deploy/kustomize'])
        self.assertIn('tests/ci/policy/airgap_test.rego', checks.OPTIONAL['deploy/kustomize'])
        artifacts = json.loads((ROOT / 'toolchain.lock.json').read_text())['artifacts']
        for name in ('kustomize', 'conftest'):
            self.assertRegex(artifacts[name]['sha256'], r'^[a-f0-9]{64}$')
            self.assertEqual(artifacts[name]['output'], 'bin/' + name)

    def test_platform_probe_bundle_cannot_omit_tests_or_manifests(self):
        bundle = checks.OPTIONAL['deploy/network/platform-probes']
        for name in ('cilium-platform-probes.yaml', 'k8s-platform-probes.yaml', 'apply-and-verify.sh', 'recover.sh', 'README.md'):
            self.assertIn('deploy/network/platform-probes/' + name, bundle)
        self.assertIn('tests/test_platform_probes.py', bundle)

    def test_rag_coverage_cannot_be_omitted(self):
        self.assertIn('tests/test_module5a.py', checks.OPTIONAL['module-5a'])
        self.assertIn('module-5a/requirements-runtime.lock.txt', checks.OPTIONAL['module-5a'])
        self.assertIn('module-5a/rag/pipeline.py', checks.OPTIONAL['module-5a'])

    def test_rag_dependencies_are_hashed_and_installed_only_when_present(self):
        lines=(ROOT/'rag-requirements.txt').read_text().splitlines()
        packages=[line for line in lines if line and not line.startswith('#')]
        self.assertEqual(len(packages),43)
        for line in packages:
            self.assertRegex(line,r'^[A-Za-z0-9_.-]+==[^ ]+ --hash=sha256:[a-f0-9]{64}')
            self.assertNotIn('torch==',line)
        workflow=yaml.safe_load((ROOT.parents[1]/'.github/workflows/pr-tests.yaml').read_text())
        step=next(s for s in workflow['jobs']['test']['steps'] if s.get('name')=='Install trusted pinned RAG client test dependencies')
        self.assertIn("hashFiles('source/module-5a/config/rag.yaml')",step['if'])
        self.assertIn('--require-hashes',step['run']);self.assertIn('.ci-control/tools/ci/rag-requirements.txt',step['run'])

    def test_hpc_dependencies_are_hashed_and_installed_only_when_present(self):
        lines = (ROOT / 'hpc-requirements.txt').read_text().splitlines()
        self.assertEqual(len(lines), 7)
        for line in lines:
            self.assertRegex(line, r'^[a-z0-9-]+==[0-9]+\.[0-9]+\.[0-9]+(?:\.post[0-9]+)? --hash=sha256:[a-f0-9]{64}$')
        workflow = yaml.safe_load((ROOT.parents[1] / '.github/workflows/pr-tests.yaml').read_text())
        step = next(s for s in workflow['jobs']['test']['steps'] if s.get('name') == 'Install trusted pinned HPC test dependencies')
        self.assertIn("hashFiles('source/module-5b/reference-profile.json')", step['if'])
        self.assertIn('--require-hashes', step['run']); self.assertIn('.ci-control/tools/ci/hpc-requirements.txt', step['run'])

    def test_fresh_workspace_has_empty_schema_cache(self):
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp)
            checks.prepare_workspace(source)
            cache = source / '.tools/schema-cache'
            self.assertTrue(cache.is_dir())
            self.assertEqual(list(cache.iterdir()), [])
            checks.prepare_workspace(source)

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

    def test_console_bundle_cannot_omit_identity_gate_or_tests(self):
        files = checks.OPTIONAL['lab/wsl/console']
        for path in ('tools/wsl_console_preflight.py', 'tests/test_wsl_console.py',
                     'lab/wsl/console/apisix-routes.yaml', 'lab/wsl/console/ui.py',
                     'lab/wsl/console/apply.sh', 'lab/wsl/console/verify.sh'):
            self.assertIn(path, files)

    def test_keycloak_admin_bundle_cannot_omit_runtime_or_tests(self):
        files = checks.OPTIONAL['keycloak-admin-bootstrap']
        for path in ('tools/wsl_keycloak_admin.py', 'tests/test_wsl_keycloak_admin.py',
                     'lab/wsl/endpoints/copy-keycloak-password.ps1', 'docs/keycloak-admin-access.md'):
            self.assertIn(path, files)

    def test_localstack_bundle_cannot_omit_runtime_or_tests(self):
        files=checks.OPTIONAL['lab/wsl/localstack']
        self.assertIn('tests/test_wsl_localstack.py',files)
        self.assertIn('lab/wsl/localstack/deploy.sh',files)
        with tempfile.TemporaryDirectory() as directory:
            source=Path(directory)
            # Reuse the actual baseline inventory, then remove one optional gate.
            for name in ['00-setup-ubuntu-host.sh','user-data.yaml','tests/test_bootstrap.py',
                         'tools/render_ssot.py','tools/render_cloud_init.py','docs/module-1-topology.md',
                         'tools/module2.py','tests/test_module2.py','module-2/vendor/cilium-1.20.2.tgz']+files[:-1]:
                path=source/name;path.parent.mkdir(parents=True,exist_ok=True);path.touch()
            with self.assertRaisesRegex(ValueError,'Incomplete lab/wsl/localstack'):checks.coverage(source)


if __name__ == '__main__':
    unittest.main(verbosity=2)
