"""Carry-forward is an anchored security refresh, never a renewed backfill."""
from copy import deepcopy
from datetime import date
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
import json
import hashlib
import tempfile

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import licence_carry as carry
from licence_ladder import fingerprint


class Carry(unittest.TestCase):
    def setUp(self):
        self.original={'id':'pip|certifi|2026.7.22','ecosystem':'pip','name':'certifi',
            'version':'2026.7.22','spdx':'MPL-2.0','class':'weak-copyleft','tier':3,
            'licenceSource':'https://pypi.org/pypi/certifi/2026.7.22/json',
            'enterpriseGrade':{'status':'legacy-pending','due':'2027-01-14'}}
        self.policy={'ladder':{'never':['AGPL-*','SSPL-*','BUSL-*'],'legacy':{}}}
        self.events=[]

    def add(self,old,version):
        new=deepcopy(old);new['version']=version;new['id']='pip|certifi|'+version
        new['licenceSource']='https://pypi.org/pypi/certifi/'+version+'/json'
        event=dict(**{'from':old['id'],'to':new['id']},record=new,originalDue='2027-01-14',
            fromVersion=old['version'],toVersion=version,advisoriesCleared=['GHSA-test'],
            netImprovement=True,licenceSHA256='a'*64,evidence='https://github.com/example/run')
        self.events.append(event)
        self.policy['ladder']['legacy'].pop(old['id'],None)
        self.policy['ladder']['legacy'][new['id']]={'sha256':fingerprint(new),'tier':3,
            'due':'2027-01-14','carriedFrom':old['id'],'advisoriesCleared':['GHSA-test'],
            'approvedBy':'','approvalDate':''}
        return new

    def validate(self):
        return carry.validate_log(self.policy,{'version':1,'events':self.events},{self.original['id']:self.original})

    def test_due_date_equals_original_and_second_carry_cannot_move_it(self):
        first=self.add(self.original,'2026.10.18');self.validate()
        second=self.add(first,'2026.10.23');self.validate()
        second['enterpriseGrade']['due']='2027-04-16'
        with self.assertRaisesRegex(ValueError,'original due'):self.validate()

    def test_log_due_cannot_be_changed_instead_of_the_record(self):
        self.add(self.original,'2026.10.18');self.events[0]['originalDue']='2027-04-16'
        with self.assertRaisesRegex(ValueError,'original due'):self.validate()

    def test_never_licence_and_tier_or_class_changes_refused(self):
        for field,value in [('spdx','AGPL-3.0-only'),('tier',2),('class','build-tool')]:
            with self.subTest(field=field):
                self.setUp();new=self.add(self.original,'2026.10.18');new[field]=value
                with self.assertRaises(ValueError):self.validate()
        self.setUp();self.original['spdx']='AGPL-3.0-only';self.add(self.original,'2026.10.18')
        with self.assertRaisesRegex(ValueError,'Never'):self.validate()

    def test_major_minor_upgrade_and_downgrade_refused(self):
        for before,after in [('1.5.17','1.6.0'),('1.5.17','2.0.0'),('1.5.17','1.5.16')]:
            with self.assertRaises(ValueError):carry.same_line('ministack',before,after)
        carry.same_line('ministack','1.5.17','1.5.33')
        carry.same_line('certifi','2026.7.22','2026.10.23')

    def test_security_evidence_and_owner_approval_are_required(self):
        new=self.add(self.original,'2026.10.18');self.events[0]['advisoriesCleared']=[]
        with self.assertRaisesRegex(ValueError,'security fix'):self.validate()
        record=self.policy['ladder']['legacy'][new['id']]
        with self.assertRaisesRegex(ValueError,'owner batch'):carry.approval(record,date(2026,10,28))
        record.update(approvedBy='amazen33',approvalDate='2026-10-28')
        carry.approval(record,date(2026,10,28))

    def test_map_predecessor_must_be_removed(self):
        self.add(self.original,'2026.10.18')
        self.policy['ladder']['legacy'][self.original['id']]={}
        with self.assertRaisesRegex(ValueError,'predecessor'):self.validate()

    def test_committed_events_are_append_only(self):
        self.add(self.original,'2026.10.18')
        anchor='a'*40
        original_policy={'ladder':{'legacy':{self.original['id']:{'due':'2027-01-14'}}}}
        log={'version':1,'anchorCommit':anchor,'events':deepcopy(self.events),
             'anchorLegacySHA256':hashlib.sha256(json.dumps(original_policy['ladder']['legacy'],sort_keys=True).encode()).hexdigest()}
        self.policy['ladder']['carryLog']='security/licence-carry-log.json'
        def git(args,**kwargs):
            if 'log' in args:return 'b'*40
            ref=args[-1]
            if ref==anchor+':security/licence-policy.json':return json.dumps(original_policy)
            if ref==anchor+':security/licence-register.json':return json.dumps({'components':[self.original]})
            return json.dumps(log)
        with tempfile.TemporaryDirectory() as directory, patch.object(carry.subprocess,'check_output',side_effect=git):
            root=Path(directory);(root/'security').mkdir()
            file=root/'security/licence-carry-log.json'
            file.write_text(json.dumps(log),encoding='utf-8')
            carry.check(root,self.policy)
            changed=deepcopy(log);changed['events'][0]['licenceSHA256']='b'*64
            file.write_text(json.dumps(changed),encoding='utf-8')
            with self.assertRaisesRegex(ValueError,'append-only'):carry.check(root,self.policy)
            changed['events']=[]
            file.write_text(json.dumps(changed),encoding='utf-8')
            with self.assertRaisesRegex(ValueError,'append-only'):carry.check(root,self.policy)


if __name__=='__main__':unittest.main()
