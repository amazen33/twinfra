"""The WO-46 promotion closes or carries only the exact R13a risks."""
from copy import deepcopy
from datetime import date
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'tools/ci'))
sys.path.insert(0, str(ROOT / 'tests'))
import r12_exceptions as r12
import supply_chain as sc
from r12_receipts import assert_images, current_exceptions

RECORD = 'security/wo46-argocd-3.5.7-approval.json'
PROPOSAL = 'security/proposals/wo46-argocd-3.5.7.json'
OLD_RECORD = 'security/wo40-amendment-11f-approval.json'
REGISTRY = 'security/vulnerability-exceptions.json'
APPROVER = 'amazen33'


class ArgoCDPromotion(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.previous = sc.read(ROOT / OLD_RECORD)
        cls.record = sc.read(ROOT / RECORD)
        cls.proposal = sc.read(ROOT / PROPOSAL)
        _, cls.base = current_exceptions(ROOT, previous_r13a=True)

    def project(self, owner):
        return r12.wo46_argocd_batch(self.base, self.proposal,
                                     self.record | {'approvedBy': owner}, self.previous)

    def test_record_and_both_registry_projections(self):
        for owner, key in (('', 'proposedRegistrySHA256'), (APPROVER, 'approvedRegistrySHA256')):
            with self.subTest(owner=owner):
                record = self.record | {'approvedBy': owner}
                self.assertEqual(r12.content_sha256(record), r12.WO46_ARGOCD_RECORD_HASHES[owner])
                projection = self.project(owner)
                self.assertEqual(r12.content_sha256(projection), record[key])
                self.assertEqual(len(projection['exceptions']), 477)
                self.assertTrue(all(row['vulnerability'] != 'CVE-2026-111497'
                                    for row in projection['exceptions']))
                target = self.proposal['exceptions'][0]['target']
                carried = [row for row in projection['exceptions'] if row['target'] == target]
                self.assertEqual(len(carried), 173)
                self.assertEqual({row['approvedBy'] for row in carried}, {owner})
                self.assertEqual(sum(row['expires'] == '2026-11-27' for row in carried), 22)
                ssh = next(row for row in carried if row['vulnerability'] == 'CVE-2026-123158')
                self.assertEqual((ssh['version'], ssh['expires']), ('1:10.2p1-2ubuntu3.8', '2026-12-13'))

    def test_pending_is_invalid_for_the_gate_and_approved_is_valid(self):
        on = date(2026, 11, 14)
        self.assertEqual(len(sc.validate_exceptions(self.project(APPROVER), ROOT, on)), 477)
        with self.assertRaisesRegex(ValueError, 'Malformed vulnerability exception'):
            sc.validate_exceptions(self.project(''), ROOT, on)

    def test_predecessor_and_exact_proposal_are_required(self):
        for owner in ('', APPROVER):
            record = self.record | {'approvedBy': owner}
            with self.subTest(owner=owner):
                with self.assertRaisesRegex(ValueError, 'unchanged R13a'):
                    r12.wo46_argocd_batch(self.base, self.proposal, record, self.previous | {'approvedBy': ''})
                base = deepcopy(self.base)
                base['exceptions'][0]['reason'] += ' altered'
                with self.assertRaisesRegex(ValueError, 'unchanged R13a'):
                    r12.wo46_argocd_batch(base, self.proposal, record, self.previous)
                for field, value in (('expires', '2026-12-30'), ('reason', 'altered'),
                                     ('workOrder', 'WO-47'), ('approvedBy', APPROVER)):
                    proposal = deepcopy(self.proposal)
                    proposal['exceptions'][0][field] = value
                    with self.subTest(field=field), self.assertRaisesRegex(ValueError, 'Exact WO-46 Argo CD proposal'):
                        r12.wo46_argocd_batch(self.base, proposal, record, self.previous)
                with self.assertRaisesRegex(ValueError, 'Exact WO-46 Argo CD proposal'):
                    r12.wo46_argocd_batch(self.base, self.proposal | {'closed': []}, record, self.previous)

    def test_checked_in_bundle_and_exact_image(self):
        _, actual = current_exceptions(ROOT)
        self.assertEqual(actual, self.project(self.record['approvedBy']))
        self.assertEqual(actual, sc.read(ROOT / REGISTRY))
        _, lock = assert_images()
        target = self.proposal['exceptions'][0]['target']
        self.assertEqual(lock['images']['argocd']['source'], target)
        altered = deepcopy(lock)
        altered['images']['argocd']['digestSource'] += '?tampered'
        with self.assertRaisesRegex(AssertionError, 'verified promotion'):
            assert_images(altered)


if __name__ == '__main__':
    unittest.main()
