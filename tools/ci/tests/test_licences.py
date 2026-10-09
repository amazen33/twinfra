"""Mutation tests for SPDX evaluation, inventory coverage and the evidence ratchet."""
from copy import deepcopy
from datetime import date
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'tools/ci'))
import check_licences as gate
import licence_inventory as inventory

TODAY = date(2026, 10, 10)


class Licences(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.policy = json.loads((ROOT / 'security/licence-policy.json').read_text())
        self.baseline = {}
        self.entry = dict(id='pip|alpha|1.0', ecosystem='pip', name='alpha', version='1.0',
                          spdx='MIT', **{'class': 'allowed'}, verifiedOn='2026-10-09',
                          recordedOn='2026-10-09', licenceSource='https://example.com/alpha/1.0/LICENSE',
                          locations=['requirements.txt'], integrities=[])
        self.component = dict(self.entry, observations=[dict(path='requirements.txt')])
        self.write('module-5a/config/rag.yaml', 'enabled: false\n')
        self.write('module-5b/reference-profile.json', json.dumps(dict(offload_enabled=False, agent_batch_submission_enabled=False)))
        self.write('module-5b/manifests/queues.yaml', 'spec:\n  nominalQuota: 0\n')
        self.write('module-5b/manifests/workloads.yaml', 'spec:\n  replicas: 0\n')
        self.write('00-setup-ubuntu-host.sh', ': "${ENABLE_GPU:=false}"\n')
        self.write('host.env.example', 'ENABLE_GPU=false\n')
        self.write('notice.txt', 'Package notice\n')

    def write(self, path, text):
        target = self.root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding='utf-8')

    def check(self):
        return gate.check_component(self.entry, self.component, self.policy, self.root, TODAY, self.baseline)

    def test_spdx_or_and_precedence(self):
        permitted = self.policy['permitted']
        for text, expected in [('GPL-3.0-only OR MIT', True), ('GPL-3.0-only AND MIT', False),
                               ('MIT OR (GPL-3.0-only AND Apache-2.0)', True),
                               ('MPL-2.0 AND (Apache-2.0 OR MIT)', False)]:
            with self.subTest(text=text):
                self.assertEqual(gate.evaluate(gate.expression(text), permitted, []), expected)

    def test_with_requires_both_base_and_exception(self):
        for text, expected in [('Apache-2.0 WITH LLVM-exception', True),
                               ('GPL-3.0-only WITH GCC-exception-3.1', False),
                               ('MIT WITH Fake-exception', False)]:
            self.assertEqual(gate.evaluate(gate.expression(text), self.policy['permitted'],
                                          self.policy['permittedExceptions']), expected)

    def test_boost_is_not_business_source(self):
        self.assertTrue(gate.evaluate(gate.expression('BSL-1.0'), self.policy['permitted'], []))
        self.assertFalse(gate.evaluate(gate.expression('BUSL-1.1'), self.policy['permitted'], []))

    def test_malformed_expression_fails_closed(self):
        for text in ('', 'MIT OR', '(MIT', 'MIT)', 'MIT AND OR Apache-2.0', 'MIT;exec', 'MIT WITH', 'MIT Apache-2.0'):
            with self.subTest(text=text), self.assertRaises(ValueError):
                gate.expression(text)

    def test_mpl_conjunction_only_passes_as_weak_copyleft(self):
        self.entry['spdx'] = 'MPL-2.0 AND (Apache-2.0 OR MIT)'
        with self.assertRaises(ValueError):
            self.check()
        self.entry.update(**{'class': 'weak-copyleft'}, unmodified=True, separateUnit=True, notice='notice.txt')
        self.entry['integrities'] = ['sha256:' + 'a' * 64]
        self.component['observations'][0]['hashes'] = ['a' * 64]
        self.check()
        self.entry['unmodified'] = False
        with self.assertRaises(ValueError):
            self.check()

    def test_weak_copyleft_rejects_lgpl_and_missing_notice(self):
        self.entry.update(spdx='MPL-2.0 AND LGPL-3.0-only', **{'class': 'weak-copyleft'},
                          unmodified=True, separateUnit=True, notice='notice.txt')
        self.baseline['artifact-integrity:' + self.entry['id']] = {}
        with self.assertRaises(ValueError):
            self.check()
        self.entry.update(spdx='MPL-2.0', notice='missing.txt')
        with self.assertRaises(ValueError):
            self.check()

    def test_gpl_tool_conditions_and_agpl_rejection(self):
        self.entry.update(ecosystem='tool', name='shellcheck', spdx='GPL-3.0-only', **{'class': 'build-tool'}, unmodified=True)
        self.component.update(ecosystem='tool', locations=['tools/ci/toolchain.lock.json'])
        self.check()
        self.component['locations'].append('module-3/toolchain.lock.json')
        with self.assertRaises(ValueError):
            self.check()
        self.component['locations'].pop()
        self.entry['spdx'] = 'AGPL-3.0-only'
        with self.assertRaises(ValueError):
            self.check()
        self.entry.update(spdx='GPL-3.0-only', **{'class': 'allowed'})
        with self.assertRaises(ValueError):
            self.check()

    def test_build_npm_must_be_dev_and_unreachable(self):
        self.entry.update(ecosystem='npm', spdx='MPL-2.0', **{'class': 'build-tool'}, unmodified=True)
        self.component.update(ecosystem='npm', observations=[dict(dev=True, production=False)])
        self.check()
        for mutation in (dict(dev=False, production=False), dict(dev=True, production=True)):
            self.component['observations'] = [mutation]
            with self.assertRaises(ValueError):
                self.check()

    def test_nested_optional_and_peer_production_reachability(self):
        packages = {'': {'dependencies': {'react': '1'}},
                    'node_modules/react': {'optionalDependencies': {'helper': '1'}},
                    'node_modules/helper': {'peerDependencies': {'bad': '1'}},
                    'node_modules/helper/node_modules/bad': {'dev': True},
                    'node_modules/build-only': {'dev': True}}
        reached = inventory.production_npm(packages)
        self.assertIn('node_modules/helper/node_modules/bad', reached)
        self.assertNotIn('node_modules/build-only', reached)

    def test_disabled_module_off_on_and_escape(self):
        self.entry.update(spdx='LGPL-2.1-or-later', **{'class': 'disabled-module'}, module='module-5a/')
        self.component['locations'] = ['module-5a/requirements-runtime.lock.txt', 'tools/ci/rag-requirements.txt']
        self.check()
        self.write('module-5a/config/rag.yaml', 'enabled: true\n')
        with self.assertRaises(ValueError):
            self.check()
        self.write('module-5a/config/rag.yaml', 'enabled: false\n')
        self.component['locations'].append('lab/wsl/deployment.yaml')
        with self.assertRaises(ValueError):
            self.check()

    def test_hpc_flags_quotas_and_replicas_are_all_required_off(self):
        self.assertTrue(gate.module_off(self.root, 'module-5b/'))
        for path, bad, good in [('module-5b/manifests/queues.yaml', 'nominalQuota: 1', 'nominalQuota: 0'),
                                ('module-5b/manifests/workloads.yaml', 'replicas: 1', 'replicas: 0'),
                                ('module-5b/reference-profile.json', '{"offload_enabled":true}',
                                 '{"offload_enabled":false,"agent_batch_submission_enabled":false}')]:
            self.write(path, bad)
            self.assertFalse(gate.module_off(self.root, 'module-5b/'))
            self.write(path, good)

    def test_gpu_operator_reference_and_base_prohibition(self):
        self.entry.update(name='docker.io/nvidia/cuda', spdx='LicenseRef-NVIDIA-CUDA-EULA',
                          **{'class': 'operator-pulled'}, notice='notice.txt')
        self.check()
        for default in ('auto', 'true'):
            self.write('00-setup-ubuntu-host.sh', ': "${ENABLE_GPU:=' + default + '}"')
            with self.assertRaises(ValueError):
                self.check()
        self.write('00-setup-ubuntu-host.sh', ': "${ENABLE_GPU:=false}"')
        self.component['locations'] = ['module-5b/images/worker.Dockerfile']
        with self.assertRaises(ValueError):
            self.check()

    def test_base_os_allows_gpl_but_not_agpl(self):
        self.entry.update(name='docker.io/library/busybox', spdx='GPL-2.0-only', **{'class': 'base-os'}, unmodified=True)
        self.component['ecosystem'] = 'oci-image'
        self.check()
        for text in ('AGPL-3.0-only', 'SSPL-1.0', 'BUSL-1.1', 'Elastic-2.0', 'LicenseRef-EULA'):
            self.entry['spdx'] = text
            with self.assertRaises(ValueError):
                self.check()

    def test_redis_expiry_and_unapproved_pending_removal(self):
        self.entry.update(name='public.ecr.aws/docker/library/redis', spdx='AGPL-3.0-only',
                          **{'class': 'pending-removal'}, expires='2026-12-08')
        self.check()
        with self.assertRaises(ValueError):
            gate.check_component(self.entry, self.component, self.policy, self.root, date(2026, 12, 8), {})
        self.entry['name'] = 'new-agpl-image'
        with self.assertRaises(ValueError):
            self.check()

    def test_runtime_exception_fails_when_module_enabled(self):
        self.entry.update(name='psycopg', spdx='LGPL-3.0-only', **{'class': 'exception'}, adr='0043', expires='2027-02-06')
        self.check()
        self.write('module-5a/config/rag.yaml', 'enabled: true')
        with self.assertRaises(ValueError):
            self.check()

    def test_baseline_cannot_override_known_blocked_licence(self):
        self.entry.update(spdx='AGPL-3.0-only', evidencePending=True)
        self.baseline['licence-source:' + self.entry['id']] = {}
        with self.assertRaises(ValueError):
            self.check()
        self.entry['class'] = 'blocked'
        with self.assertRaises(ValueError):
            self.check()

    def fixture(self):
        self.write('requirements.txt', 'alpha==1.0\n')
        for path in ('licence-policy.json', 'licence-register.schema.json'):
            self.write('security/' + path, (ROOT / 'security' / path).read_text())
        self.write('security/licence-register.json', json.dumps(dict(version=1, components=[self.entry])))
        self.write('security/licence-baseline.json', json.dumps(dict(version=1, findings=[])))
        self.write('security/licences/rag-notices.lock.json', '{}')
        self.write('module-5a/images/rag.Dockerfile', 'COPY security/licences/rag/ /usr/share/licenses/vcloud-rag/\n')

    def test_new_component_and_changed_integrity_fail_inventory(self):
        self.fixture()
        with patch.object(inventory, 'files', return_value=['requirements.txt']):
            self.assertEqual(gate.audit(self.root, TODAY)['status'], 'passed')
            self.write('requirements.txt', 'alpha==1.0\nbeta==2.0\n')
            self.assertIn('Unregistered component', '\n'.join(gate.audit(self.root, TODAY)['errors']))
            self.write('requirements.txt', 'alpha==1.0 --hash=sha256:' + 'b'*64 + '\n')
            self.assertIn('integrity changed', '\n'.join(gate.audit(self.root, TODAY)['errors']))

    def test_expired_baseline_and_unlisted_finding_fail(self):
        self.fixture()
        self.write('app/Dockerfile', 'RUN apt-get install -y curl\n')
        with patch.object(inventory, 'files', return_value=['requirements.txt', 'app/Dockerfile']):
            report = gate.audit(self.root, TODAY)
            self.assertIn('New/changed evidence finding', '\n'.join(report['errors']))
            item = dict(id='apt-pins:app/Dockerfile', kind='apt-pins', owner='owner', reason='pins',
                        requiredEvidence='snapshot', recordedOn='2026-10-09', expires='2027-01-07',
                        fingerprint=inventory.digest(self.root/'app/Dockerfile'))
            self.write('security/licence-baseline.json', json.dumps(dict(version=1, findings=[item])))
            self.assertEqual(gate.audit(self.root, TODAY)['status'], 'passed')
            self.assertEqual(gate.audit(self.root, date(2027, 1, 7))['status'], 'failed')
            self.write('app/Dockerfile', 'RUN apt-get install -y curl git\n')
            self.assertEqual(gate.audit(self.root, TODAY)['status'], 'failed')

    def test_locked_source_new_version_and_rendered_image_are_enumerated(self):
        self.write('artifacts.lock.json', json.dumps({'sources':[{'url':'https://raw.githubusercontent.com/org/project/v1/file.yaml','sha256':'a'*64}]}))
        self.write('render.yaml', 'kind: Pod\nspec:\n  containers:\n  - name: test\n    image: quay.io/new/image@sha256:'+'b'*64)
        with patch.object(inventory, 'files', return_value=['artifacts.lock.json']):
            entries, _ = inventory.enumerate_inputs(self.root, [self.root/'render.yaml'])
            self.assertIn('manifest|org/project/file.yaml|v1', entries)
            self.assertIn('oci-image|quay.io/new/image|sha256:'+'b'*64, entries)

    def test_reviewed_sbom_can_close_baseline_but_changed_evidence_fails(self):
        self.entry.update(id='oci-image|quay.io/alpha|sha256:' + 'a'*64,
                          ecosystem='oci-image', name='quay.io/alpha', version='sha256:' + 'a'*64,
                          locations=['deployment.yaml'], integrities=['sha256:' + 'a'*64])
        self.fixture()
        self.write('deployment.yaml', 'kind: Pod\nspec:\n  containers:\n  - name: app\n    image: quay.io/alpha@sha256:' + 'a'*64)
        with patch.object(inventory, 'files', return_value=['deployment.yaml']):
            self.assertIn('Missing image SBOM', '\n'.join(gate.audit(self.root, TODAY)['errors']))
            self.write('evidence/sbom.json', '{"reviewed":true}\n')
            self.entry['imageSBOM'] = dict(path='evidence/sbom.json', sha256=inventory.digest(self.root/'evidence/sbom.json'))
            self.write('security/licence-register.json', json.dumps(dict(version=1, components=[self.entry])))
            self.assertEqual(gate.audit(self.root, TODAY)['status'], 'passed')
            self.write('evidence/sbom.json', '{"changed":true}\n')
            self.assertIn('Missing/changed reviewed image SBOM', '\n'.join(gate.audit(self.root, TODAY)['errors']))

    def test_notice_bundle_is_required_and_candidate_boundary_is_explicit(self):
        self.fixture()
        self.write('module-5a/images/rag.Dockerfile', 'FROM nothing\n')
        with patch.object(inventory, 'files', return_value=['requirements.txt']):
            self.assertIn('RAG image omits', '\n'.join(gate.audit(self.root, TODAY)['errors']))
        runner = (ROOT/'tools/ci/run_checks.py').read_text()
        self.assertIn("ROOT / 'check_licences.py', '--root', ROOT.parents[1]", runner)
        baseline = json.loads((ROOT/'tools/ci/pr-baselines.json').read_text())
        self.assertEqual(len(baseline['baselines']), 6)


if __name__ == '__main__':
    unittest.main()
