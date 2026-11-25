"""O-14 binds nine risks to the unchanged, already activated O-12 registry."""
from copy import deepcopy
from datetime import date, timedelta
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'tools/ci'))
sys.path.insert(0,str(ROOT/'tests'))
import r12_exceptions as r12
import supply_chain as sc
from r12_receipts import approved_content, current_exceptions

RECORD='security/wo40-amendment-11d-approval.json'
PROPOSAL='security/proposals/wo40-amendment-11d.json'
PREVIOUS='security/wo40-amendment-11c-approval.json'
ACTIVE='security/vulnerability-exceptions.json'
FILES=(RECORD,PROPOSAL,PREVIOUS,ACTIVE,
       'security/proposals/wo40-amendment-11c.json',
       'security/wo40-amendment-11a-approval.json',
       'security/proposals/wo40-amendment-11a-kev.json',
       'security/security-wave-2026-10-approval.json',
       'security/proposals/r12-vulnerability-exceptions.json','security/licence-carry-log.json')


def save(path,value):
    path.write_text(json.dumps(value,indent=2)+'\n',encoding='utf-8',newline='\n')


class Reapproval(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _,original,_=approved_content()
        earlier=sc.read(ROOT/'security/wo40-amendment-11a-approval.json')
        earlier['approvedBy']='amazen33'
        cls.previous=sc.read(ROOT/PREVIOUS)
        cls.previous['approvedBy']='amazen33'
        base=r12.amendment_11a_batch(original,
            sc.read(ROOT/'security/proposals/wo40-amendment-11a-kev.json'),earlier)
        cls.base=r12.amendment_11c_batch(base,
            sc.read(ROOT/'security/proposals/wo40-amendment-11c.json'),cls.previous,earlier)
        cls.proposal=sc.read(ROOT/PROPOSAL)
        cls.record=sc.read(ROOT/RECORD)

    def project(self,approved):
        record=deepcopy(self.record);record['approvedBy']='amazen33' if approved else ''
        previous=deepcopy(self.previous);previous['approvedBy']='amazen33'
        return r12.amendment_11d_batch(self.base,self.proposal,record,previous)

    def scratch(self,root,approved):
        for filename in FILES:
            target=root/filename;target.parent.mkdir(parents=True,exist_ok=True)
            target.write_bytes((ROOT/filename).read_bytes())
        for filename in ('security/wo40-amendment-11a-approval.json',PREVIOUS):
            record=sc.read(root/filename);record['approvedBy']='amazen33';save(root/filename,record)
        record=deepcopy(self.record);record['approvedBy']='amazen33' if approved else ''
        save(root/RECORD,record);save(root/ACTIVE,self.project(approved))

    def test_exact_nine_rows_preserve_every_existing_row_and_order(self):
        self.assertEqual(len(self.base['exceptions']),423)
        self.assertEqual(r12.content_sha256(self.base),self.record['baseApprovedRegistrySHA256'])
        for approved in (False,True):
            result=self.project(approved)
            self.assertEqual(len(result['exceptions']),432)
            self.assertEqual(len({r12.identity(e) for e in result['exceptions']}),432)
            self.assertEqual(result['exceptions'][:423],self.base['exceptions'])
            expected=deepcopy(self.proposal['exceptions'])
            for row in expected:row['approvedBy']='amazen33' if approved else ''
            self.assertEqual(result['exceptions'][423:],expected)

    def test_hashes_bind_both_states_and_activated_predecessor(self):
        self.assertEqual(hashlib.sha256((ROOT/PROPOSAL).read_bytes()).hexdigest(),
                         '3af549ac9aa6697ec153816acfb74c26aaefd4d37f74dc4e1df2eb579abbd5a6')
        self.assertEqual(r12.content_sha256(self.previous),self.record['previousApprovalSHA256'])
        for approved,key in ((False,'proposedRegistrySHA256'),(True,'approvedRegistrySHA256')):
            record=deepcopy(self.record);record['approvedBy']='amazen33' if approved else ''
            self.assertEqual(r12.content_sha256(record),r12.AMENDMENT_11D_RECORD_HASHES[record['approvedBy']])
            self.assertEqual(r12.content_sha256(self.project(approved)),record[key])

    def test_only_nine_attributions_change_during_activation(self):
        differences=[]
        for before,after in zip(self.project(False)['exceptions'],self.project(True)['exceptions'],strict=True):
            if before!=after:
                self.assertEqual(before|{'approvedBy':'amazen33'},after)
                self.assertEqual(before['approvedBy'],'')
                differences.append(r12.identity(before))
        self.assertEqual(differences,[r12.identity(e) for e in self.proposal['exceptions']])
        self.assertEqual(self.previous['approvedBy'],'amazen33')

    def test_pending_rows_cannot_pass_the_gate(self):
        with self.assertRaisesRegex(ValueError,'Malformed vulnerability exception'):
            sc.validate_exceptions(self.project(False),ROOT,date(2026,11,7))
        sc.validate_exceptions(self.project(True),ROOT,date(2026,11,7))

    def test_nine_findings_replay_passes_through_november_10_only_when_approved(self):
        findings=[];state={}
        for row in self.proposal['exceptions']:
            fields={k:row[k] for k in r12.KEYS}
            key=sc.sha(json.dumps(list(fields.values()),separators=(',',':')).encode())
            first={'libsasl2-2':'2026-10-13','libsasl2-modules-db':'2026-10-13',
                   'java-21-openjdk-headless':'2026-10-23','undici':'2026-10-24',
                   'filelock':'2026-10-24','musl':'2026-10-22','musl-utils':'2026-10-22'}[row['package']]
            findings.append(fields|dict(key=key,severity='High',aliases=[row['vulnerability']],
                fixAvailable=True,fixVersions=['fixture-fixed-version'],introduced=False))
            state[key]=first
        kev=dict(catalogVersion='2026.11.06',vulnerabilities=[])
        for offset in range(5):
            on=date(2026,11,6)+timedelta(days=offset)
            with self.subTest(on=on):
                report=sc.evaluate(dict(findings=findings),self.project(True),kev,state,on=on,root=ROOT)
                self.assertEqual(report['status'],'passed')
                self.assertEqual(sum(e['blocked'] for e in report['findings']),0)
                self.assertEqual(sum(e['exception'] is not None for e in report['findings']),9)
                with self.assertRaisesRegex(ValueError,'Malformed vulnerability exception'):
                    sc.evaluate(dict(findings=findings),self.project(False),kev,state,on=on,root=ROOT)
                missing=sc.evaluate(dict(findings=findings),self.base,kev,state,on=on,root=ROOT)
                self.assertEqual(sum(e['blocked'] for e in missing['findings']),7 if offset==0 else 9)

    def test_any_changed_existing_row_is_refused(self):
        for index in range(423):
            bad=deepcopy(self.base);bad['exceptions'][index]['reason']='changed existing risk'
            with self.subTest(index=index),self.assertRaisesRegex(ValueError,'existing row'):
                r12.amendment_11d_batch(bad,self.proposal,self.record,self.previous)

    def test_extra_missing_or_reordered_proposal_rows_are_refused(self):
        rows=self.proposal['exceptions']
        for changed in (rows[:-1],rows[::-1],rows+[deepcopy(rows[0])]):
            bad={'version':1,'exceptions':changed}
            with self.assertRaisesRegex(ValueError,'nine anchored'):
                r12.amendment_11d_batch(self.base,bad,self.record,self.previous)

    def test_risk_text_deadline_work_order_controls_and_approval_are_immutable(self):
        for index in range(9):
            for field,value in [('reason','changed risk'),('expires','2026-11-28'),
                    ('workOrder','WO-47'),('controls',[]),('severity','Critical'),
                    ('approvedBy','amazen33')]:
                bad=deepcopy(self.proposal);bad['exceptions'][index][field]=value
                with self.subTest(index=index,field=field),self.assertRaises(ValueError):
                    r12.amendment_11d_batch(self.base,bad,self.record,self.previous)
                record=deepcopy(self.record);record['proposalSHA256']=r12.content_sha256(bad)
                with self.assertRaisesRegex(ValueError,'Exact Amendment 11d'):
                    r12.amendment_11d_batch(self.base,bad,record,self.previous)

    def test_record_fields_hashes_and_unknown_owner_are_refused(self):
        for field in self.record:
            bad=deepcopy(self.record);bad[field]='tampered'
            with self.subTest(field=field),self.assertRaisesRegex(ValueError,'Exact Amendment 11d'):
                r12.amendment_11d_batch(self.base,self.proposal,bad,self.previous)

    def test_unapproved_or_changed_predecessor_is_refused_in_both_states(self):
        for approved in ('','amazen33'):
            record=deepcopy(self.record);record['approvedBy']=approved
            for previous_by in ('','pending-owner'):
                previous=deepcopy(self.previous);previous['approvedBy']=previous_by
                with self.assertRaisesRegex(ValueError,'activated, unchanged O-12'):
                    r12.amendment_11d_batch(self.base,self.proposal,record,previous)
            previous=deepcopy(self.previous);previous['scope'][0]['expires']='2026-11-28'
            with self.assertRaisesRegex(ValueError,'activated, unchanged O-12'):
                r12.amendment_11d_batch(self.base,self.proposal,record,previous)

    def test_complete_bundle_accepts_pending_and_approved_states(self):
        for approved in (False,True):
            with self.subTest(approved=approved),tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp);self.scratch(root,approved)
                _,actual=current_exceptions(root)
                self.assertEqual(actual,self.project(approved))
                original,_,_=approved_content(root)
                self.assertEqual(original['approvedScope']['vulnerabilityRows'],420)

    def test_partial_activation_and_unapproved_active_rows_are_refused(self):
        for approved in (False,True):
            for index in range(423,432):
                with self.subTest(approved=approved,index=index),tempfile.TemporaryDirectory() as tmp:
                    root=Path(tmp);self.scratch(root,approved)
                    active=sc.read(root/ACTIVE)
                    active['exceptions'][index]['approvedBy']='' if approved else 'amazen33'
                    save(root/ACTIVE,active)
                    with self.assertRaisesRegex(AssertionError,'Active registry differs'):
                        current_exceptions(root)

    def test_mismatched_record_and_registry_activation_are_refused(self):
        for approved in (False,True):
            with tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp);self.scratch(root,approved)
                save(root/ACTIVE,self.project(not approved))
                with self.assertRaisesRegex(AssertionError,'Active registry differs'):
                    current_exceptions(root)

    def test_raw_content_hash_mismatches_are_refused(self):
        for approved in (False,True):
            for changed in (RECORD,PROPOSAL,PREVIOUS,ACTIVE):
                with self.subTest(approved=approved,changed=changed),tempfile.TemporaryDirectory() as tmp:
                    root=Path(tmp);self.scratch(root,approved)
                    with (root/changed).open('ab') as stream:stream.write(b' ')
                    with self.assertRaises(AssertionError):current_exceptions(root)

    def test_incomplete_bundles_and_missing_predecessors_are_refused(self):
        for missing in (RECORD,PROPOSAL,PREVIOUS,'security/proposals/wo40-amendment-11c.json'):
            with self.subTest(missing=missing),tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp);self.scratch(root,False);(root/missing).unlink()
                with self.assertRaisesRegex(AssertionError,'Incomplete'):current_exceptions(root)
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);self.scratch(root,False)
            for filename in (RECORD,PROPOSAL):(root/filename).unlink()
            with self.assertRaisesRegex(AssertionError,'Active registry differs'):current_exceptions(root)

    def test_repository_bundle_remains_bound_to_its_current_approval_state(self):
        # Preserve O-14's 432-row scratch projection after the later O-17 batch.
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);self.scratch(root,True)
            _,actual=current_exceptions(root)
            self.assertEqual(actual,sc.read(root/ACTIVE))
            self.assertEqual(len(actual['exceptions']),432)


if __name__=='__main__':unittest.main()
