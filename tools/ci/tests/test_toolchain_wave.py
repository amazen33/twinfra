"""Package/fix-version wave evidence never confers owner approval."""
from copy import deepcopy
from datetime import date
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import supply_chain as sc
import toolchain_wave as wave

TODAY = date(2026, 10, 16)


class Wave(unittest.TestCase):
    def setUp(self):
        self.value = dict(target='quay.io/example/image@sha256:'+'a'*64,
            package='golang.org/x/net', version='v0.58.0', vulnerability='CVE-2026-78663',
            aliases=['GO-2026-6612'], severity='Critical', fixVersions=['0.60.0'],
            fixAvailable=True, blocked=True, introduced=True, kev=False)
        self.controls = dict(clusterOrLanOnly=True, noExternalService=True,
                             externalEgress='Kubernetes API server only')

    def review(self, findings=None, **kwargs):
        return wave.review(findings if findings is not None else [self.value],
            eligible_fixed_release=kwargs.get('eligible', False),
            controls=kwargs.get('controls', self.controls),
            upstream_evidence='https://github.com/cert-manager/cert-manager/releases', on=TODAY)

    def test_exact_image_package_cve_and_unapproved_batch(self):
        report=self.review();entry=report['proposedExceptions'][0]
        self.assertEqual(report['status'], 'owner-review-required')
        self.assertEqual(entry['approvedBy'], '')
        self.assertEqual(entry['expires'], '2026-11-15')
        self.assertEqual(entry['target'], self.value['target'])
        # Empty approval is useful review data, but NEVER an active exception.
        with self.assertRaises(ValueError):
            sc.validate_exceptions(dict(version=1, exceptions=[entry]), on=TODAY)

    def test_all_five_previously_unlisted_stdlib_highs_qualify(self):
        for advisory in ('6605','6607','6608','6609','6613'):
            value=self.value | dict(package='stdlib', version='go1.26.8',
                vulnerability='CVE-2026-'+advisory, aliases=['GO-2026-'+advisory],
                severity='High', fixVersions=['1.26.9','1.27.2'])
            with self.subTest(advisory=advisory):
                entry=self.review([value])['proposedExceptions'][0]
                self.assertEqual(entry['expires'], '2026-12-15')

    def test_identity_list_does_not_override_package_or_fix(self):
        for change in (dict(package='google.golang.org/grpc'), dict(package='example.org/crypto'),
                       dict(package='libssl3'), dict(package='golang.org/x/unknown-owner'),
                       dict(fixVersions=[]), dict(fixVersions=['v0.58.0']),
                       dict(fixVersions=['unfixed']), dict(fixAvailable=False)):
            with self.subTest(change=change):
                report=self.review([self.value | change])
                self.assertEqual(report['status'], 'blocked')
                self.assertEqual(len(report['nonQualifying']), 1)
                self.assertFalse(report['proposedExceptions'])

    def test_stdlib_requires_latest_patch_of_built_line(self):
        base=self.value | dict(package='stdlib', version='go1.26.8')
        for versions in (['1.27.2'], ['1.26.8'], ['1.26.10'], []):
            with self.subTest(versions=versions):
                self.assertEqual(self.review([base | dict(fixVersions=versions)])['status'], 'blocked')
        self.assertEqual(self.review([base | dict(fixVersions=['1.26.9'])])['status'], 'owner-review-required')

    def test_go_team_mod_and_similar_modules_use_scanner_fix(self):
        for module in ('mod','crypto','text','sys','sync','tools'):
            value=self.value | dict(package='golang.org/x/'+module, version='v0.1.0', fixVersions=['0.2.0'])
            with self.subTest(module=module):
                self.assertEqual(self.review([value])['status'], 'owner-review-required')

    def test_kev_fixed_release_or_missing_controls_blocks_whole_batch(self):
        for values, opts in (([self.value | dict(kev=True)], {}), ([self.value], dict(eligible=True)),
            ([self.value], dict(eligible=None)), ([self.value], dict(controls=self.controls | dict(noExternalService=False)))):
            with self.subTest(opts=opts):
                result=self.review(values, **opts)
                self.assertEqual(result['status'], 'blocked')
                self.assertFalse(result['proposedExceptions'])

    def test_mixed_batch_lists_every_nonqualifying_finding(self):
        others=[self.value | dict(package=p) for p in ('grpc','libssl3','application')]
        report=self.review([self.value, *others])
        self.assertEqual(report['nonQualifying'], others)
        self.assertFalse(report['proposedExceptions'])

    def test_per_image_and_per_package_entries_remain_separate(self):
        other=self.value | dict(target='quay.io/example/other@sha256:'+'b'*64)
        entries=self.review([self.value, other])['proposedExceptions']
        self.assertEqual(len(entries), 2)
        with self.assertRaises(ValueError):
            self.review([self.value | dict(target='images a,b')])

    def test_gate_accepts_owner_approved_qualifying_exception(self):
        entry=self.review()['proposedExceptions'][0] | dict(approvedBy='amazen33')
        value=self.value | dict(key='c'*64)
        result=dict(findings=[value])
        report=sc.evaluate(result, dict(version=1, exceptions=[entry]),
                           dict(catalogVersion='2026-10-16', vulnerabilities=[]), on=TODAY)
        self.assertEqual(report['status'], 'passed')

    def test_gate_rejects_approved_nonqualifying_or_changed_evidence(self):
        entry=self.review()['proposedExceptions'][0] | dict(approvedBy='amazen33')
        for change in (dict(package='google.golang.org/grpc'), dict(kev=True), dict(fixVersions=['0.61.0'])):
            value=self.value | change
            with self.subTest(change=change), self.assertRaises(ValueError):
                wave.validate_entry(entry, value, wave.policy(), TODAY)
        for field, value in (('noEligibleFixedRelease',False), ('checkedOn','2026-09-01'),
                             ('upstreamEvidence','http://example.org')):
            bad=deepcopy(entry);bad['toolchainWave'][field]=value
            with self.subTest(field=field), self.assertRaises(ValueError):
                wave.validate_entry(bad, self.value, wave.policy(), TODAY)

    def test_already_approved_or_clean_findings_need_no_new_exception(self):
        self.assertEqual(self.review([])['status'], 'no-exception-needed')
        self.assertEqual(self.review([self.value | dict(blocked=False)])['status'], 'no-exception-needed')


if __name__ == '__main__':
    unittest.main()
