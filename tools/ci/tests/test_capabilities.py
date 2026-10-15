"""Evidence-first assertions, including the frozen-revision boundary."""
from pathlib import Path
import sys
import tempfile
import unittest
import subprocess

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from check_capabilities import BUNDLE, check, count_text


class Capabilities(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        for name in BUNDLE:
            self.write(name, '# Fixture\n')
        self.adr = BUNDLE[1]
        self.write(self.adr, '# ADR-0052: Fixture\n\n**Status:** Accepted (owner)\n')
        self.write('docs/adr/README.md',
                   '| ADR | Status | Acceptance receipt |\n| --- | --- | --- |\n'
                   '| [0052](0052-evidence-first-foundation-1-0.md) | Accepted (design) | None |\n')
        self.write('README.md', count_text(1))
        self.claim('Planned', '')

    def write(self, name, text):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding='utf-8')

    def claim(self, status, evidence):
        self.write('docs/capabilities.md', '| Capability | Status | Evidence | Work order |\n'
                   '| --- | --- | --- | --- |\n'
                   f'| Kubernetes | {status} | {evidence} | WO-37 |\n')

    def receipt(self, *, result='Accepted', environment='twinfra-dev-cairo-1', name='current.md'):
        self.write('docs/acceptance/' + name, f'# Receipt\n\nEnvironment: `{environment}`\n\n'
                   '## Tester sign-off\nTester: Ahmed Mazen (@amazen33)\n'
                   f'Result: {result}\nDate (UTC): 2026-10-16\n')
        return f'[receipt](acceptance/{name})'

    def assertFails(self, message):
        result = check(self.root)
        self.assertEqual(result['status'], 'failed', result)
        self.assertIn(message, ' '.join(result['findings']))

    def test_clean_index_pending_capabilities_pass(self):
        self.assertEqual(check(self.root)['status'], 'passed')

    def test_missing_receipt_fails(self):
        self.claim('Dev-verified', '[missing](acceptance/missing.md)')
        self.assertFails('missing receipt')

    def test_pending_tester_signoff_fails(self):
        self.claim('Dev-verified', self.receipt(result='Pending'))
        self.assertFails('not Accepted')

    def test_accepted_wsl_only_receipt_fails_even_without_wsl_filename(self):
        self.claim('Dev-verified', self.receipt(environment='owned mirrored WSL2 vcloud-wsl-local'))
        self.assertFails('Historical (retired environment)')

    def test_explicit_historical_link_never_counts(self):
        self.claim('Real', self.receipt().replace('[receipt]', '[Historical (retired environment)]'))
        self.assertFails('Historical (retired environment)')

    def test_all_live_claims_require_accepted_current_receipt(self):
        for status in ('Dev-verified', 'Real', 'Parity-tested', '**Real**', 'Dev-verified (scoped)'):
            with self.subTest(status=status):
                self.claim(status, self.receipt())
                result = check(self.root)
                self.assertEqual(result['status'], 'passed', result)
                self.assertEqual(result['liveClaimsChecked'], 1)
                self.claim(status, '')
                self.assertFails('missing Accepted receipt')

    def test_production_needs_production_receipt(self):
        self.claim('Production-accepted', self.receipt())
        self.assertFails('matching live environment')
        self.claim('Production-accepted', self.receipt(environment='production eu-1'))
        self.assertEqual(check(self.root)['status'], 'passed')

    def test_receipt_outside_acceptance_and_external_link_fail(self):
        for target in ('[static](../README.md)', '[external](https://example.org/receipt.md)',
                       '[template](acceptance/README.md)'):
            self.claim('Real', target)
            self.assertFails('receipt')

    def test_accepted_outside_signoff_or_example_does_not_count(self):
        self.receipt(result='Pending')
        path = self.root / 'docs/acceptance/current.md'
        path.write_text('Result: Accepted\n' + path.read_text() +
                        '\n```markdown\n## Tester sign-off\nResult: Accepted\n```\n')
        self.claim('Real', '[current](acceptance/current.md)')
        self.assertFails('not Accepted')

    def test_adr_live_status_header_and_index_are_checked(self):
        self.write(self.adr, '# ADR-0052: fixture\n\n**Status:** Dev-verified\n')
        self.assertFails('missing Accepted receipt')
        self.write(self.adr, '# ADR-0052: fixture\n\n**Status:** Accepted (owner)\n')
        index = self.root / 'docs/adr/README.md'
        index.write_text(index.read_text().replace('Accepted (design)', 'Dev-verified'))
        self.assertFails('missing Accepted receipt')

    def test_count_generated_from_index_and_duplicates_fail(self):
        self.write('README.md', count_text(39))
        self.assertFails('count drift')
        self.assertEqual(check(self.root, write=True)['status'], 'passed')
        self.assertIn(count_text(1), (self.root/'README.md').read_text())
        index = self.root/'docs/adr/README.md'
        index.write_text(index.read_text() + index.read_text().splitlines()[-1] + '\n')
        self.assertFails('exactly once')

    def test_legacy_revision_absent_but_partial_new_bundle_fails(self):
        for name in BUNDLE:
            (self.root/name).unlink()
        self.assertEqual(check(self.root)['status'], 'not_present_in_revision')
        self.write(BUNDLE[0], '# Partial\n')
        self.assertFails('incomplete WO-37')

    def test_retired_evidence_requires_label_in_index(self):
        self.receipt(name='wsl-old.md', environment='WSL2')
        index = self.root/'docs/adr/README.md'
        index.write_text(index.read_text().replace('| None |', '| [old](../acceptance/wsl-old.md) |'))
        self.assertFails('unlabelled retired WSL')
        index.write_text(index.read_text().replace('[old]', '[Historical (retired environment)]'))
        self.assertEqual(check(self.root)['status'], 'passed')

    def test_ci_document_gate_cannot_skip_evidence_check(self):
        repo = Path(__file__).resolve().parents[3]
        checker = (repo/'tools/ci/check_docs.py').read_text()
        runner = (repo/'tools/ci/run_checks.py').read_text()
        self.assertIn("evidence = check_capabilities(root)", checker)
        self.assertIn("assert evidence['status'] != 'failed'", checker)
        self.assertIn("run('candidate-capability-evidence'", runner)

    def test_full_docs_gate_accepts_signed_lifecycle_and_rejects_pending(self):
        from test_adr_log import ADRLog, IDENTITY
        repo = Path(__file__).resolve().parents[3]
        # Retain the original fixture's historical structure/security checks,
        # then add the complete current evidence model rather than skipping it.
        with tempfile.TemporaryDirectory() as directory:
            root = ADRLog().fixture(directory)
            additions = [36, 38, *range(42, 54)]
            for number in additions:
                name = {36: '0036-product-name-twinfra.md',
                        52: Path(BUNDLE[1]).name}.get(number, f'{number:04d}-fixture.md')
                (root/'docs/adr'/name).write_text(f'# ADR-{number:04d}: fixture\n\n**Status:** Proposed\n')
            for order in (20, 37):
                name = 'WO-20-rename-to-twinfra.md' if order == 20 else Path(BUNDLE[2]).name
                (root/'docs/work-orders'/name).write_text('# Work order\n')
            (root/'docs/capabilities.md').write_text('# Capabilities\n')
            rows = '\n'.join(f'| [{path.stem[:4]}]({path.name}) | Proposed | None |'
                             for path in sorted((root/'docs/adr').glob('[0-9]*.md')))
            (root/'docs/adr/README.md').write_text(
                IDENTITY + '\n**0054** **0037** **0039–0041**\n' + '\n'.join(
                    ('Proposed', 'Accepted (design)', 'Dev-verified', 'Production-accepted',
                     'Deferred (reference design)', 'Superseded')) +
                '\n| ADR | Status | Evidence |\n| --- | --- | --- |\n' + rows + '\n')
            (root/'README.md').write_text(count_text(49))
            receipt = root/'docs/acceptance/current.md'
            receipt.parent.mkdir()
            accepted = ('Environment: twinfra-dev-cairo-1\n\n## Tester sign-off\n'
                        'Tester: Ahmed Mazen (@amazen33)\nResult: Accepted\n')
            receipt.write_text(accepted)
            adr = root/'docs/adr/0002-kubernetes.md'
            adr.write_text(adr.read_text().replace('**Status:** Proposed', '**Status:** Dev-verified') +
                           '\n[receipt](../acceptance/current.md)\n')
            def run():
                return subprocess.run([sys.executable, str(repo/'tools/ci/check_docs.py'), str(root),
                                       str(root/'docs.json'), str(root/'mermaid.json')],
                                      text=True, capture_output=True)
            result = run()
            self.assertEqual(result.returncode, 0, result.stderr)
            receipt.write_text(accepted.replace('Result: Accepted', 'Result: Pending'))
            result = run()
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('tester sign-off is not Accepted', result.stderr)


if __name__ == '__main__':
    unittest.main()
