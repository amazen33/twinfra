"""O-11 is a hash-anchored severity correction, never a wider R12 approval."""
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

RECORD='security/wo40-amendment-11a-approval.json'
PROPOSAL='security/proposals/wo40-amendment-11a-kev.json'
ACTIVE='security/vulnerability-exceptions.json'
FILES=(RECORD,PROPOSAL,ACTIVE,'security/security-wave-2026-10-approval.json',
       'security/proposals/r12-vulnerability-exceptions.json','security/licence-carry-log.json')


class Reapproval(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.original_record,cls.original,_=approved_content()
        cls.record=sc.read(ROOT/RECORD)
        cls.proposal=sc.read(ROOT/PROPOSAL)
        cls.current=r12.amendment_11a_batch(cls.original,cls.proposal,cls.record)

    def scratch(self,root):
        for filename in FILES:
            path=root/filename;path.parent.mkdir(parents=True,exist_ok=True)
            path.write_bytes((ROOT/filename).read_bytes())
        # Isolate O-11's original 420-row projection from the later O-12 batch.
        (root/ACTIVE).write_text(json.dumps(self.current,indent=2)+'\n',encoding='utf-8',newline='\n')

    def test_original_r12_anchor_and_scope_still_hold(self):
        self.assertEqual(r12.content_sha256(self.original),self.original_record['proposalSHA256'])
        self.assertEqual(self.record['r12ProposalSHA256'],self.original_record['proposalSHA256'])
        self.assertEqual(self.original_record['approvedScope']['High'],360)
        self.assertEqual(self.original_record['approvedScope']['kevRows'],1)

    def test_only_one_row_and_only_severity_and_attribution_change(self):
        expected=deepcopy(self.original)
        for row in expected['exceptions']:row['approvedBy']='amazen33'
        differences=[]
        for old,new in zip(expected['exceptions'],self.current['exceptions'],strict=True):
            if old!=new:
                differences.append({k:(old[k],new[k]) for k in old if old[k]!=new[k]})
                self.assertEqual(r12.identity(old),r12.identity(new))
                self.assertEqual(new,self.proposal['exceptions'][0]|
                                 {'approvedBy':self.record['approvedBy']})
        wanted={'severity':('Medium','High')}
        if not self.record['approvedBy']:wanted['approvedBy']=('amazen33','')
        self.assertEqual(differences,[wanted])
        self.assertEqual(len(self.current['exceptions']),420)
        self.assertEqual(sum(e['severity']=='High' for e in self.current['exceptions']),361)

    def test_hashes_bind_proposal_and_pending_and_approved_registry(self):
        self.assertEqual(hashlib.sha256((ROOT/PROPOSAL).read_bytes()).hexdigest(),
                         self.record['proposalSHA256'])
        record=deepcopy(self.record);record['approvedBy']=''
        pending=r12.amendment_11a_batch(self.original,self.proposal,record)
        self.assertEqual(r12.content_sha256(pending),record['proposedRegistrySHA256'])
        record['approvedBy']='amazen33'
        approved=r12.amendment_11a_batch(self.original,self.proposal,record)
        self.assertEqual(r12.content_sha256(approved),record['approvedRegistrySHA256'])
        sc.validate_exceptions(approved,ROOT,date(2026,10,31))

    def test_empty_approval_stays_blocking(self):
        record=deepcopy(self.record);record['approvedBy']=''
        pending=r12.amendment_11a_batch(self.original,self.proposal,record)
        with self.assertRaisesRegex(ValueError,'Malformed vulnerability exception'):
            sc.validate_exceptions(pending,ROOT,date(2026,10,31))

    def test_approved_scratch_passes_and_old_severity_fails_the_kev_gate(self):
        record=deepcopy(self.record);record['approvedBy']='amazen33'
        approved=r12.amendment_11a_batch(self.original,self.proposal,record)
        row=self.proposal['exceptions'][0]
        fields={k:row[k] for k in r12.KEYS}
        finding=fields|{'key':sc.sha(json.dumps(list(fields.values()),separators=(',',':')).encode()),
                       'severity':'High','aliases':[row['vulnerability']],
                       'fixAvailable':True,'fixVersions':['1.2.0-3ubuntu0.1'],'introduced':False}
        result={'findings':[finding]}
        kev={'catalogVersion':'2026-10-31','vulnerabilities':[{'cveID':row['vulnerability']}]}
        report=sc.evaluate(result,approved,kev,on=date(2026,10,31),root=ROOT)
        self.assertEqual(report['status'],'passed')
        self.assertEqual(report['findings'][0]['blockReason'],'KEV')
        old=deepcopy(approved)
        next(e for e in old['exceptions'] if r12.identity(e)==r12.identity(row))['severity']='Medium'
        with self.assertRaisesRegex(ValueError,'Exception severity differs'):
            sc.evaluate(result,old,kev,on=date(2026,10,31),root=ROOT)

    def test_other_fields_and_additional_rows_are_refused(self):
        for field,value in [('expires','2026-11-25'),('reason','changed reason'),
                            ('controls',['changed control']),('severity','Critical'),
                            ('target','quay.io/argoproj/argocd@sha256:'+'a'*64),
                            ('approvedBy','amazen33')]:
            bad=deepcopy(self.proposal);bad['exceptions'][0][field]=value
            record=deepcopy(self.record);record['proposalSHA256']=r12.content_sha256(bad)
            with self.subTest(field=field),self.assertRaisesRegex(ValueError,'proposal differs'):
                r12.amendment_11a_batch(self.original,bad,record)
        bad=deepcopy(self.proposal);bad['exceptions'].append(deepcopy(bad['exceptions'][0]))
        with self.assertRaisesRegex(ValueError,'proposal differs'):
            r12.amendment_11a_batch(self.original,bad,self.record)

    def test_approval_scope_and_hash_mutations_are_refused(self):
        for field in ('proposalSHA256','proposedRegistrySHA256','approvedRegistrySHA256',
                      'r12ProposalSHA256','decision','authority','approvedBy','scope'):
            bad=deepcopy(self.record);bad[field]='tampered'
            with self.subTest(field=field),self.assertRaises(ValueError):
                r12.amendment_11a_batch(self.original,self.proposal,bad)

    def test_original_or_active_row_tampering_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);self.scratch(root)
            active=sc.read(root/ACTIVE);active['exceptions'][0]['reason']='changed reason'
            (root/ACTIVE).write_text(json.dumps(active))
            with self.assertRaisesRegex(AssertionError,'Active registry differs'):
                current_exceptions(root)
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);self.scratch(root)
            with (root/PROPOSAL).open('ab') as stream:stream.write(b' ')
            with self.assertRaisesRegex(AssertionError,'content hash differs'):
                current_exceptions(root)

    def test_attribution_requires_the_separate_o11_record(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);self.scratch(root)
            record=sc.read(root/RECORD);record['approvedBy']=''
            r12_record=root/RECORD
            r12_record.write_text(json.dumps(record))
            active=sc.read(root/ACTIVE)
            next(e for e in active['exceptions'] if e['vulnerability']=='CVE-2026-111497')['approvedBy']='amazen33'
            (root/ACTIVE).write_text(json.dumps(active,indent=2)+'\n',newline='\n')
            with self.assertRaisesRegex(AssertionError,'content/approval'):
                current_exceptions(root)
            record['approvedBy']='amazen33';r12_record.write_text(json.dumps(record))
            _,approved=current_exceptions(root)
            self.assertTrue(all(e['approvedBy']=='amazen33' for e in approved['exceptions']))


if __name__=='__main__':unittest.main()
