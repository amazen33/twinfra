"""O-12 appends three exact risks without reopening any O-11/R12 approval."""
from copy import deepcopy
from datetime import date
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

RECORD='security/wo40-amendment-11c-approval.json'
PROPOSAL='security/proposals/wo40-amendment-11c.json'
PREVIOUS='security/wo40-amendment-11a-approval.json'
ACTIVE='security/vulnerability-exceptions.json'
FILES=(RECORD,PROPOSAL,PREVIOUS,ACTIVE,
       'security/proposals/wo40-amendment-11a-kev.json',
       'security/security-wave-2026-10-approval.json',
       'security/proposals/r12-vulnerability-exceptions.json','security/licence-carry-log.json')


def save(path,value):
    path.write_text(json.dumps(value,indent=2)+'\n',encoding='utf-8',newline='\n')


class Reapproval(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _,original,_=approved_content()
        cls.previous=sc.read(ROOT/PREVIOUS)
        cls.base=r12.amendment_11a_batch(original,
            sc.read(ROOT/'security/proposals/wo40-amendment-11a-kev.json'),cls.previous)
        cls.proposal=sc.read(ROOT/PROPOSAL)
        cls.record=sc.read(ROOT/RECORD)

    def project(self,approved):
        previous=deepcopy(self.previous);previous['approvedBy']='amazen33' if approved else ''
        base=deepcopy(self.base)
        next(e for e in base['exceptions'] if e['vulnerability']=='CVE-2026-111497')['approvedBy']=previous['approvedBy']
        record=deepcopy(self.record);record['approvedBy']=previous['approvedBy']
        return r12.amendment_11c_batch(base,self.proposal,record,previous)

    def scratch(self,root):
        for filename in FILES:
            target=root/filename;target.parent.mkdir(parents=True,exist_ok=True)
            target.write_bytes((ROOT/filename).read_bytes())

    def test_exact_three_individual_rows_and_unchanged_420_row_prefix(self):
        pending=self.project(False)
        self.assertEqual(len(self.proposal['exceptions']),3)
        self.assertEqual(len(pending['exceptions']),423)
        self.assertEqual(len({r12.identity(e) for e in pending['exceptions']}),423)
        self.assertEqual(pending['exceptions'][420:],self.proposal['exceptions'])
        base=deepcopy(self.base)
        next(e for e in base['exceptions'] if e['vulnerability']=='CVE-2026-111497')['approvedBy']=''
        self.assertEqual(pending['exceptions'][:420],base['exceptions'])
        self.assertEqual(sum(e['severity']=='Critical' for e in pending['exceptions']),61)
        self.assertEqual(sum(e['severity']=='High' for e in pending['exceptions']),362)
        for row,scope in zip(self.proposal['exceptions'],r12.AMENDMENT_11C_SCOPE,strict=True):
            self.assertEqual(r12.identity(row),r12.identity(scope))
            self.assertEqual(row['createdOn'],'2026-10-31')
            self.assertEqual(row['expires'],'2026-11-27')
            self.assertEqual(row['workOrder'],'WO-46')
            self.assertEqual(row['approvedBy'],'')

    def test_hashes_bind_proposal_both_states_and_unchanged_o11_anchors(self):
        self.assertEqual(hashlib.sha256((ROOT/PROPOSAL).read_bytes()).hexdigest(),self.record['proposalSHA256'])
        self.assertEqual(r12.content_sha256(self.project(False)),self.record['proposedRegistrySHA256'])
        self.assertEqual(r12.content_sha256(self.project(True)),self.record['approvedRegistrySHA256'])
        for new,old in (('amendment11aProposalSHA256','proposalSHA256'),
                        ('baseProposedRegistrySHA256','proposedRegistrySHA256'),
                        ('baseApprovedRegistrySHA256','approvedRegistrySHA256')):
            self.assertEqual(self.record[new],self.previous[old])

    def test_pending_stays_blocking_and_only_four_row_attributions_activate(self):
        pending=self.project(False);approved=self.project(True)
        with self.assertRaisesRegex(ValueError,'Malformed vulnerability exception'):
            sc.validate_exceptions(pending,ROOT,date(2026,10,31))
        sc.validate_exceptions(approved,ROOT,date(2026,10,31))
        changed=[]
        for before,after in zip(pending['exceptions'],approved['exceptions'],strict=True):
            if before!=after:
                self.assertEqual(before|{'approvedBy':'amazen33'},after)
                self.assertEqual(before['approvedBy'],'')
                changed.append(r12.identity(before))
        self.assertEqual(set(changed),{r12.identity(e) for e in self.proposal['exceptions']}|
            {r12.identity(next(e for e in pending['exceptions'] if e['vulnerability']=='CVE-2026-111497'))})
        self.assertEqual(len(changed),4)

    def test_four_approved_findings_pass_without_weakening_kev_or_high_age(self):
        approved=self.project(True)
        rows=[e for e in approved['exceptions'] if r12.identity(e) in
              {r12.identity(v) for v in self.proposal['exceptions']} or e['vulnerability']=='CVE-2026-111497']
        findings=[];state={}
        for row in rows:
            fields={k:row[k] for k in r12.KEYS}
            key=sc.sha(json.dumps(list(fields.values()),separators=(',',':')).encode())
            fixes=({'libbrotli1':['1.2.0-3ubuntu0.1'],'lodash-es':['4.18.0']}
                   .get(row['package'],['3.13.18','3.14.10']))
            findings.append(fields|dict(key=key,severity=row['severity'],aliases=[row['vulnerability']],
                fixAvailable=True,fixVersions=fixes,introduced=False))
            state[key]='2026-10-17' if row['package']=='lodash-es' else '2026-10-30'
        kev=dict(catalogVersion='2026.10.30',vulnerabilities=[dict(cveID='CVE-2026-111497')])
        report=sc.evaluate(dict(findings=findings),approved,kev,state,on=date(2026,10,31),root=ROOT)
        self.assertEqual(report['status'],'passed')
        self.assertEqual([e['blockReason'] for e in report['findings']],
                         ['KEV','Critical with fix','Critical with fix','High with fix aged 14 days'])
        without=deepcopy(approved);without['exceptions']=without['exceptions'][:-3]
        blocked=sc.evaluate(dict(findings=findings),without,kev,state,on=date(2026,10,31),root=ROOT)
        self.assertEqual(sum(e['blocked'] for e in blocked['findings']),3)

    def test_other_row_fields_or_additional_missing_reordered_rows_are_refused(self):
        for index in range(3):
            for field,value in [('target','another-target'),('package','another-package'),
                    ('version','another-version'),('vulnerability','CVE-OTHER'),('severity','Medium'),
                    ('expires','2026-11-28'),('createdOn','2026-10-30'),('workOrder','WO-47'),
                    ('owner','another-owner'),('approvedBy','amazen33'),('controls',[]),('reason','changed risk')]:
                bad=deepcopy(self.proposal);bad['exceptions'][index][field]=value
                record=deepcopy(self.record);record['proposalSHA256']=r12.content_sha256(bad)
                with self.subTest(index=index,field=field),self.assertRaises(ValueError):
                    r12.amendment_11c_batch(self.base,bad,record,self.previous)
        variants=[self.proposal['exceptions'][:-1],self.proposal['exceptions'][::-1],
                  self.proposal['exceptions']+[self.proposal['exceptions'][0]]]
        for rows in variants:
            bad={'version':1,'exceptions':rows}
            record=deepcopy(self.record);record['proposalSHA256']=r12.content_sha256(bad)
            with self.assertRaises(ValueError):r12.amendment_11c_batch(self.base,bad,record,self.previous)

    def test_every_existing_row_remains_bound_to_its_o11_hash(self):
        for index in (0,419):
            bad=deepcopy(self.base);bad['exceptions'][index]['reason']='changed existing risk'
            with self.assertRaisesRegex(ValueError,'existing row'):
                r12.amendment_11c_batch(bad,self.proposal,self.record,self.previous)

    def test_record_hash_scope_authority_and_partial_activation_are_refused(self):
        for field in self.record:
            bad=deepcopy(self.record);bad[field]='tampered'
            with self.subTest(field=field),self.assertRaises(ValueError):
                r12.amendment_11c_batch(self.base,self.proposal,bad,self.previous)
        for previous_by,record_by in (('amazen33',''),('','amazen33')):
            previous=deepcopy(self.previous);record=deepcopy(self.record)
            previous['approvedBy']=previous_by;record['approvedBy']=record_by
            with self.assertRaisesRegex(ValueError,'Exact Amendment 11c approval record required'):
                r12.amendment_11c_batch(self.base,self.proposal,record,previous)

    def test_risk_gaps_fixes_eligibility_and_build_scope_are_explicit(self):
        for row,scope in zip(self.proposal['exceptions'],r12.AMENDMENT_11C_SCOPE,strict=True):
            for text in (scope['fixedVersion'],scope['eligibleOn'],
                         'live enforcement and trust Secrets not verified','after stable, before 2026-11-20'):
                self.assertIn(text,row['reason'])
        self.assertEqual(self.proposal['exceptions'][2]['scope'],'build')
        self.assertIn('2026-04-01T21:04:15.518Z',self.proposal['exceptions'][2]['reason'])
        self.assertIn('4.18.0',self.proposal['exceptions'][2]['reason'])
        for index in (0,1):self.assertNotIn('scope',self.proposal['exceptions'][index])
        bad=self.project(True);bad['exceptions'][-1]['scope']='runtime'
        with self.assertRaisesRegex(ValueError,'Malformed vulnerability exception'):
            sc.validate_exceptions(bad,ROOT,date(2026,10,31))

    def test_active_and_proposal_bytes_and_incomplete_bundles_are_refused(self):
        for changed in (ACTIVE,PROPOSAL,RECORD):
            with self.subTest(changed=changed),tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp);self.scratch(root)
                if changed==RECORD:
                    record=sc.read(root/changed);record['proposalSHA256']='0'*64;save(root/changed,record)
                else:
                    with (root/changed).open('ab') as stream:stream.write(b' ')
                with self.assertRaises(AssertionError):current_exceptions(root)
        for missing in (RECORD,PROPOSAL):
            with tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp);self.scratch(root);(root/missing).unlink()
                with self.assertRaisesRegex(AssertionError,'Incomplete'):current_exceptions(root)
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);self.scratch(root)
            for missing in (RECORD,PROPOSAL):(root/missing).unlink()
            with self.assertRaisesRegex(AssertionError,'Active registry differs'):current_exceptions(root)

    def test_complete_activation_and_original_r12_approval_still_validate(self):
        _,actual=current_exceptions()
        self.assertEqual(actual,sc.read(ROOT/ACTIVE))
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);self.scratch(root)
            for filename in (PREVIOUS,RECORD):
                record=sc.read(root/filename);record['approvedBy']='amazen33';save(root/filename,record)
            save(root/ACTIVE,self.project(True))
            _,actual=current_exceptions(root)
            self.assertEqual(actual,self.project(True))
            record,_,_=approved_content(root)
            self.assertEqual(record['approvedScope']['vulnerabilityRows'],420)


if __name__=='__main__':unittest.main()
