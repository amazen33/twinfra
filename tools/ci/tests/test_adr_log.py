"""Exercise canonical ADR invariants without dropping historical layout coverage."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

REPO = Path(__file__).resolve().parents[3]
CHECKER = REPO / 'tools/ci/check_docs.py'
SLUGS = ['kubernetes', 'knative-serving', 'cloudnativepg', 'pgvector', 'apisix',
         'argocd', 'tekton', 'prometheus', 'grafana', 'opentelemetry', 'openbao',
         'keycloak', 'kafka', 'strimzi', 'vllm', 'langchain', 'spinifex']
IDENTITY = ('vCloud-prod-01 vcloud-prod-01 vcloud.example.com amazen33/vCloud '
            'registry.vcloud.example.com platform-services workload-apps hpc-compute')


class ADRLog(unittest.TestCase):
    def fixture(self, directory, *, canonical=True):
        root = Path(directory)
        def write(name, content):
            path = root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding='utf-8')
        subprocess.run(['git', 'init', '-q', str(root)], check=True, capture_output=True)
        folder = 'docs/adr' if canonical else 'docs/adrs'
        for name in ('security/node-exceptions.json', 'docs/node-agent-inventory.json'):
            path = root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes((REPO / name).read_bytes())
        write('vcloud-ssot.yaml', 'policySHA256: d9799b19ff5fb101cde1870840f29b6d54d6e6cff2c22b389a62d9adfe7cd253\nadr: docs/adr/0001-node-host-mounts.md\n')
        names = []
        for number, slug in enumerate(SLUGS, 2):
            name = f'{number:04d}-{slug}.md'
            names.append(name)
            text = (f'# ADR-{number:04d}: fixture\n\n**Status:** Proposed\n'
                    '**Date:** 2026-10-05\n**Deciders:** owner\n'
                    '**Selection:** required by Module 1.\n**Scope:** test\n'
                    '**Classification:** Constraint\nhttps://example.com\n')
            for section in ('Context', 'Decision', 'Options considered', 'Trade-off analysis',
                            'Consequences', 'Action items and acceptance'):
                text += f'\n## {section}\n\nFixture.\n'
            if canonical and number in (10, 18):
                text = text.replace('**Status:** Proposed', '**Status:** Superseded')
                text += '\nADR-0034\n' if number == 10 else '\nADR-0029 ADR-0030\n'
            write(f'{folder}/{name}', text)
        if canonical:
            for number in [1, *range(19, 36)]:
                name = f'{number:04d}-fixture.md'
                names.append(name)
                text = f'# ADR-{number:04d}: fixture\n\n**Status:** Proposed\n'
                if number == 25:
                    text = text.replace('Proposed', 'Superseded') + '\nADR-0030 WO-06\n'
                if number in (26, 27):
                    text += '\nADR-0035 read-only decision only\n'
                write(f'{folder}/{name}', text)
            for old, target in [('docs/adrs', '../adr/README.md'),
                                ('docs/architecture/adr', '../../adr/README.md')]:
                write(f'{old}/README.md', f'[ADR log]({target}).\n')
            for number in range(1, 12):
                write(f'docs/work-orders/WO-{number:02d}-fixture.md', '# Work order\n')
            write('docs/work-orders/README.md', '# Handoff\n')
        write(f'{folder}/README.md', IDENTITY + '\n' + '\n'.join(names) +
              '\nProposed Accepted (lab) Accepted (production) Superseded Constraint **0036**\n')
        for name in ('docs/module-1-topology.md', 'docs/module-1-summary.md', 'README.md'):
            write(name, '# Fixture\n')
        write('mermaid.json', json.dumps({'status': 'passed'}))
        return root

    def check(self, root):
        return subprocess.run([sys.executable, str(CHECKER), str(root),
                               str(root / 'report.json'), str(root / 'mermaid.json')],
                              capture_output=True, text=True)

    def test_canonical_log_and_legacy_17_component_layout_pass(self):
        for canonical in (True, False):
            with self.subTest(canonical=canonical), tempfile.TemporaryDirectory() as directory:
                root = self.fixture(directory, canonical=canonical)
                result = self.check(root)
                self.assertEqual(result.returncode, 0, result.stderr)
                report = json.loads((root / 'report.json').read_text())
                self.assertEqual(report['adrCount'], 35 if canonical else 17)
                self.assertEqual(report['adrLayout'], 'canonical' if canonical else 'historical')

    def test_canonical_duplicates_fail(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self.fixture(directory)
            (root / 'docs/adr/0020-duplicate.md').write_text('# ADR-0020: duplicate\n')
            result = self.check(root)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('duplicate/gapped ADR numbers', result.stderr)

    def test_stage_b_index_uses_selected_revision_repository(self):
        for canonical in (True, False):
            with self.subTest(canonical=canonical), tempfile.TemporaryDirectory() as directory:
                root = self.fixture(directory, canonical=canonical)
                ssot = root / 'vcloud-ssot.yaml'
                ssot.write_text(ssot.read_text() + 'cluster:\n  gitOpsRepository: amazen33/twinfra\n')
                index = root / ('docs/adr/README.md' if canonical else 'docs/adrs/README.md')
                # Old index references cannot satisfy a renamed current contract.
                self.assertNotEqual(self.check(root).returncode, 0)
                index.write_text(index.read_text().replace('amazen33/vCloud', 'amazen33/twinfra'))
                result = self.check(root)
                self.assertEqual(result.returncode, 0, result.stderr)

    def test_approved_valkey_order_preserves_historical_work_order_requirements(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self.fixture(directory)
            order = root / 'docs/work-orders/WO-25-redis-to-valkey.md'
            order.write_text('# WO-25: Replace Redis with Valkey\n')
            result = self.check(root)
            self.assertEqual(result.returncode, 0, result.stderr)
            (root / 'docs/work-orders/WO-06-fixture.md').unlink()
            self.assertNotEqual(self.check(root).returncode, 0)

    def test_rename_pair_with_remaining_reserved_adrs_passes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self.fixture(directory)
            names = ['0036-product-name-twinfra.md', '0042-fixture.md',
                     '0043-fixture.md', '0044-fixture.md']
            for name in names:
                (root / 'docs/adr' / name).write_text(
                    f'# ADR-{name[:4]}: fixture\n\n**Status:** Accepted (owner)\n', encoding='utf-8')
            index = root / 'docs/adr/README.md'
            index.write_text(index.read_text().replace('**0036**', '**0045**') +
                             '\n'.join(names) + '\n**0037–0041**\n', encoding='utf-8')
            (root / 'docs/work-orders/WO-20-rename-to-twinfra.md').write_text('# WO-20: Rename\n')
            result = self.check(root)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads((root / 'report.json').read_text())['adrCount'], 39)
            index.write_text(index.read_text(encoding='utf-8').replace('**0037–0041**', '**0036–0041**'), encoding='utf-8')
            result = self.check(root)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('missing reserved ADR range', result.stderr)

    def test_incomplete_rename_pair_fails(self):
        for missing in ('adr', 'order'):
            with self.subTest(missing=missing), tempfile.TemporaryDirectory() as directory:
                root = self.fixture(directory)
                if missing == 'adr':
                    (root / 'docs/work-orders/WO-20-rename-to-twinfra.md').write_text('# WO-20: Rename\n')
                else:
                    name = '0036-product-name-twinfra.md'
                    (root / 'docs/adr' / name).write_text('# ADR-0036: fixture\n\n**Status:** Accepted (owner)\n')
                result = self.check(root)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn('incomplete WO-20 / ADR-0036 pair', result.stderr)

    def test_valkey_image_requires_its_work_order(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self.fixture(directory)
            (root / 'deploy').mkdir()
            (root / 'deploy/registry-images.lock.json').write_text('{"images":{"valkey":{}}}')
            result = self.check(root)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('missing WO-25 work order', result.stderr)

    def test_duplicate_number_hidden_in_title_fails(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self.fixture(directory)
            path = root / 'docs/adr/0035-fixture.md'
            path.write_text(path.read_text().replace('# ADR-0035:', '# ADR-0020:'))
            result = self.check(root)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('ADR title/filename mismatch', result.stderr)

    def test_partial_canonical_log_cannot_fall_back_to_legacy(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self.fixture(directory, canonical=False)
            (root / 'docs/adr').mkdir()
            self.assertNotEqual(self.check(root).returncode, 0)

    def test_lab_status_without_receipt_fails(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self.fixture(directory)
            path = root / 'docs/adr/0003-knative-serving.md'
            path.write_text(path.read_text().replace('**Status:** Proposed', '**Status:** Accepted (lab)'))
            result = self.check(root)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('missing lab receipt', result.stderr)

    def test_broken_link_outside_component_docs_fails(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self.fixture(directory)
            (root / 'docs/work-orders/README.md').write_text('[missing](absent.md)\n')
            result = self.check(root)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('absent.md', result.stderr)

    def test_stale_individual_stub_and_missing_work_order_fail(self):
        for fault in ('stub', 'order'):
            with self.subTest(fault=fault), tempfile.TemporaryDirectory() as directory:
                root = self.fixture(directory)
                if fault == 'stub':
                    (root / 'docs/adrs/0002-kubernetes.md').write_text('[moved](../adr/0002-kubernetes.md)\n')
                else:
                    (root / 'docs/work-orders/WO-06-fixture.md').unlink()
                self.assertNotEqual(self.check(root).returncode, 0)

    def test_link_to_existing_file_with_missing_heading_fails(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self.fixture(directory)
            (root / 'docs/work-orders/README.md').write_text('[broken](WO-01-fixture.md#absent)\n')
            result = self.check(root)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('missing heading anchor', result.stderr)

    def test_wrong_next_number_or_missing_successor_fails(self):
        for fault in ('next', 'successor'):
            with self.subTest(fault=fault), tempfile.TemporaryDirectory() as directory:
                root = self.fixture(directory)
                path = root / ('docs/adr/README.md' if fault == 'next' else 'docs/adr/0018-spinifex.md')
                path.write_text(path.read_text().replace('**0036**', '**0035**') if fault == 'next'
                                else path.read_text().replace('ADR-0030', 'removed'))
                self.assertNotEqual(self.check(root).returncode, 0)


if __name__ == '__main__':
    unittest.main()
