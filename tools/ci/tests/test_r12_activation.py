"""The owner's approval changes attribution only, never the approved risk rows."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import unittest

ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'tools/ci'))
import activate_r12 as activation
import supply_chain as sc


class Activation(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.proposal=json.loads(subprocess.check_output(['git','-C',str(ROOT),'show',
            activation.APPROVED_COMMIT+':'+activation.PROPOSAL]))

    def test_active_rows_equal_the_exact_approved_proposal_plus_attribution(self):
        current=sc.read(ROOT/activation.PROPOSAL)
        self.assertEqual(current,self.proposal)
        expected=activation.approved_batch(current,self.proposal)
        self.assertEqual(sc.read(ROOT/'security/vulnerability-exceptions.json'),expected)
        self.assertTrue(all(e['approvedBy']=='' for e in current['exceptions']))
        sc.validate_exceptions(expected,ROOT)

    def test_changed_reason_expiry_identity_or_controls_needs_new_approval(self):
        for field,value in [('expires','2026-12-28'),('reason','changed reason'),
                            ('target','changed-target'),('controls',['changed control'])]:
            bad=deepcopy(self.proposal);bad['exceptions'][0][field]=value
            with self.subTest(field=field),self.assertRaisesRegex(ValueError,'new approval required'):
                activation.approved_batch(bad,self.proposal)

    def test_activation_cannot_overwrite_later_registry_changes(self):
        before={'exceptions':[]};approved={'exceptions':[{'approvedBy':'amazen33'}]}
        activation.require_original_or_approved(before,before,approved)
        activation.require_original_or_approved(approved,before,approved)
        with self.assertRaisesRegex(ValueError,'refusing overwrite'):
            activation.require_original_or_approved({'exceptions':[{'later':'owner-approved work'}]},before,approved)

    def test_carry_log_deadlines_and_utc_attribution_are_preserved(self):
        record=sc.read(ROOT/activation.APPROVAL)
        raw=subprocess.check_output(['git','-C',str(ROOT),'show',activation.APPROVED_COMMIT+':'+activation.CARRY_LOG])
        self.assertEqual((ROOT/activation.CARRY_LOG).read_bytes(),raw)
        self.assertEqual(hashlib.sha256(raw).hexdigest(),record['carryLogSHA256'])
        self.assertEqual(record['ownerDecisionDate'],'2026-10-29')
        self.assertEqual(record['approvedBy'],'amazen33')
        policy=sc.read(ROOT/'security/licence-policy.json')
        for event in json.loads(raw)['events']:
            actual=policy['ladder']['legacy'][event['to']]
            self.assertEqual(actual['due'],event['originalDue'])
            self.assertEqual(actual['approvalDate'],record['recordedAtUTC'][:10])
            self.assertEqual(actual['approvedBy'],'amazen33')


if __name__=='__main__':unittest.main()
