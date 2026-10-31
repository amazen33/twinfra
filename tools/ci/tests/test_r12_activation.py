"""The owner's approval changes attribution only, never the approved risk rows."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'tools/ci'))
sys.path.insert(0,str(ROOT/'tests'))
import activate_r12 as activation
import supply_chain as sc
from r12_receipts import approved_content, current_exceptions


class Activation(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.record,cls.proposal,cls.carry_log=approved_content()

    def test_active_rows_equal_the_exact_approved_proposal_plus_attribution(self):
        current=sc.read(ROOT/activation.PROPOSAL)
        self.assertEqual(hashlib.sha256((ROOT/activation.PROPOSAL).read_bytes()).hexdigest(),
                         self.record['proposalSHA256'])
        self.assertEqual(current,self.proposal)
        expected=activation.approved_batch(current,self.proposal)
        self.assertTrue(all(e['approvedBy']=='' for e in current['exceptions']))
        sc.validate_exceptions(expected,ROOT)
        # The original R12 batch remains immutable; only the separately anchored
        # O-11 projection may change its KEV severity and attribution.
        _,amended=current_exceptions()
        self.assertEqual(sc.read(ROOT/'security/vulnerability-exceptions.json'),amended)

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
        raw=(ROOT/activation.CARRY_LOG).read_bytes()
        self.assertEqual((ROOT/activation.CARRY_LOG).read_bytes(),raw)
        self.assertEqual(json.loads(raw),self.carry_log)
        self.assertEqual(hashlib.sha256(raw).hexdigest(),record['carryLogSHA256'])
        self.assertEqual(record['ownerDecisionDate'],'2026-10-29')
        self.assertEqual(record['approvedBy'],'amazen33')
        policy=sc.read(ROOT/'security/licence-policy.json')
        for event in json.loads(raw)['events']:
            actual=policy['ladder']['legacy'][event['to']]
            self.assertEqual(actual['due'],event['originalDue'])
            self.assertEqual(actual['approvalDate'],record['recordedAtUTC'][:10])
            self.assertEqual(actual['approvedBy'],'amazen33')

    def test_content_hash_or_scope_tampering_is_rejected(self):
        files=(activation.APPROVAL,activation.PROPOSAL,activation.CARRY_LOG)
        for changed in files:
            with self.subTest(changed=changed),tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp)
                for filename in files:
                    target=root/filename;target.parent.mkdir(parents=True,exist_ok=True)
                    target.write_bytes((ROOT/filename).read_bytes())
                if changed==activation.APPROVAL:
                    record=sc.read(root/changed);record['approvedScope']['High']+=1
                    (root/changed).write_text(json.dumps(record))
                else:
                    with (root/changed).open('ab') as stream:stream.write(b' ')
                with self.assertRaisesRegex(AssertionError,'hash differs|scope differs'):
                    approved_content(root)

    def test_approved_commit_is_provenance_not_an_input(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            for filename in (activation.APPROVAL,activation.PROPOSAL,activation.CARRY_LOG):
                target=root/filename;target.parent.mkdir(parents=True,exist_ok=True)
                target.write_bytes((ROOT/filename).read_bytes())
            record=sc.read(root/activation.APPROVAL);record['approvedCommit']='provenance-only'
            (root/activation.APPROVAL).write_text(json.dumps(record))
            _,proposal,log=approved_content(root)
            self.assertEqual(proposal,self.proposal)
            self.assertEqual(log,self.carry_log)


if __name__=='__main__':unittest.main()
