"""Offline admission tests; candidate scans cannot mutate pins or approve findings."""
from pathlib import Path
import re
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import security_wave_2026_10 as wave


def finding(package='stdlib', vulnerability='CVE-2026-1', version='1',
            severity='High', fix=True):
    return dict(package=package, vulnerability=vulnerability, version=version,
                severity=severity, fixAvailable=fix)


class Admission(unittest.TestCase):
    def test_version_change_carries_identity_without_claiming_closure(self):
        result=wave.compare_identities([finding()], [finding(version='2')])
        self.assertTrue(result['subset'])
        self.assertFalse(result['strictImprovement'])
        self.assertEqual(result['closed'], [])
        self.assertEqual(result['carried'], [('stdlib', 'CVE-2026-1')])

    def test_removal_is_strict_improvement_and_new_identity_fails_subset(self):
        old=[finding(), finding(vulnerability='CVE-2026-2', severity='Critical')]
        result=wave.compare_identities(old, [finding()])
        self.assertTrue(result['subset'])
        self.assertTrue(result['strictImprovement'])
        self.assertEqual(result['closed'], [('stdlib', 'CVE-2026-2')])
        result=wave.compare_identities(old, [finding(package='new-package')])
        self.assertFalse(result['subset'])
        self.assertFalse(result['strictImprovement'])
        self.assertEqual(result['introduced'], [('new-package', 'CVE-2026-1')])

    def test_only_fixable_critical_high_identities_define_subset(self):
        after=[finding(severity='Medium'), finding(fix=False)]
        self.assertTrue(wave.compare_identities([], after)['subset'])

    def test_candidates_are_immutable_and_only_three_components(self):
        self.assertEqual({v[0] for v in wave.CASES.values()},
                         {'argocd', 'keycloak', 'ministack'})
        self.assertEqual({v[1] for v in wave.CASES.values()},
                         {'3.5.5', '3.5.6', '26.8.1', '1.5.33'})
        for _, _, reference in wave.CASES.values():
            self.assertIsNotNone(re.fullmatch(
                r'(?:quay|docker)\.io/[a-z0-9./-]+@sha256:[a-f0-9]{64}', reference))


if __name__=='__main__':
    unittest.main()
