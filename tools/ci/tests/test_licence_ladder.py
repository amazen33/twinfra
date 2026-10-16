"""ADR-0054 admission and dated, immutable legacy approvals."""
from copy import deepcopy
from datetime import date
import json
import jsonschema
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import licence_ladder as gate

ROOT = Path(__file__).resolve().parents[3]
TODAY = date(2026, 10, 16)


class Ladder(unittest.TestCase):
    def setUp(self):
        self.policy = json.loads((ROOT/'security/licence-policy.json').read_text())
        self.entry = {'id':'pip|candidate|1', 'ecosystem':'pip', 'name':'candidate',
                      'version':'1', 'class':'exception', 'tier':4, 'approvedBy':'amazen33',
                      'unmodified':True, 'separateUnit':True, 'notice':'notice.md',
                      'enterpriseGrade':{'status':'verified','criteria':{
                          k:{'result':'pass','evidence':'https://example.org/evidence','date':'2026-10-16'}
                          for k in gate.CRITERIA}},
                      'climbing':{'reviewedOn':'2026-10-16','reevaluateOn':'2027-04-16',
                                  'reviewAtMinorUpgrade':True,'rejectedCandidates':[
                                      {'name':'alternative','tier':2,'failedCriterion':'maturity',
                                       'evidence':'https://example.org/rejected'}]}}

    def validate(self, entry=None, on=TODAY, terms=('GPL-3.0-only',)):
        gate.validate(entry or self.entry, self.policy, terms, on)

    def test_tier_three_four_require_owner_grade_and_climbing(self):
        for tier, term in ((3,'LGPL-3.0-only'), (4,'GPL-3.0-only')):
            good=deepcopy(self.entry);good['tier']=tier
            self.validate(good, terms=(term,))
            for field in ('approvedBy','enterpriseGrade','climbing'):
                bad=deepcopy(good);bad.pop(field)
                with self.subTest(tier=tier,field=field), self.assertRaises(ValueError):
                    self.validate(bad, terms=(term,))

    def test_register_schema_requires_tier_three_four_admission_fields(self):
        schema=json.loads((ROOT/'security/licence-register.schema.json').read_text())
        original=self.entry|{'spdx':'GPL-3.0-only','licenceSource':'https://example.org/LICENSE',
                             'verifiedOn':'2026-10-16','recordedOn':'2026-10-16',
                             'locations':['fixture.txt'],'integrities':[], 'adr':'0054','expires':'2027-04-16'}
        for tier in (3,4):
            entry=deepcopy(original);entry['tier']=tier
            jsonschema.validate({'version':1,'components':[entry]},schema)
            for field in ('approvedBy','enterpriseGrade','climbing'):
                bad=deepcopy(entry);bad.pop(field)
                with self.subTest(tier=tier,field=field),self.assertRaises(jsonschema.ValidationError):
                    jsonschema.validate({'version':1,'components':[bad]},schema)

    def test_never_cannot_be_excepted_or_hidden_in_or_expression(self):
        for term in ('AGPL-3.0-only','SSPL-1.0','BUSL-1.1','Elastic-2.0',
                     'Commons-Clause','LicenseRef-Proprietary-EULA','account-gated','source-available'):
            with self.subTest(term=term), self.assertRaisesRegex(ValueError,'Never'):
                self.validate(terms=(term,'MIT'))

    def legacy(self):
        entry=deepcopy(self.entry);entry.pop('enterpriseGrade');entry.pop('climbing')
        self.policy['ladder']['legacy'][entry['id']]={'sha256':gate.fingerprint(entry),'tier':4,'due':'2027-01-14'}
        entry['enterpriseGrade']={'status':'legacy-pending','due':'2027-01-14'}
        return entry

    def test_unchanged_legacy_passes_before_deadline(self):
        self.validate(self.legacy())

    def test_legacy_fails_on_and_after_deadline(self):
        entry=self.legacy()
        for on in (date(2027,1,14),date(2027,1,15)):
            with self.assertRaisesRegex(ValueError,'overdue'):
                self.validate(entry,on)

    def test_changed_legacy_requires_full_records(self):
        original=self.legacy()
        for field,value in (('version','2'),('class','allowed'),('integrities',['sha256:'+'a'*64])):
            entry=deepcopy(original);entry[field]=value
            with self.subTest(field=field),self.assertRaisesRegex(ValueError,'Changed legacy'):
                self.validate(entry)

    def test_cannot_extend_legacy_due_date(self):
        entry=self.legacy();entry['enterpriseGrade']['due']='2027-04-16'
        with self.assertRaises(ValueError):self.validate(entry)

    def test_each_enterprise_criterion_must_pass(self):
        for criterion in gate.CRITERIA:
            entry=deepcopy(self.entry);entry['enterpriseGrade']['criteria'][criterion]['result']='fail'
            with self.subTest(criterion=criterion),self.assertRaises(ValueError):self.validate(entry)

    def test_re_evaluation_is_bounded_and_mandatory_at_minor_upgrade(self):
        for field,value in (('reevaluateOn','2027-04-17'),('reviewAtMinorUpgrade',False)):
            entry=deepcopy(self.entry);entry['climbing'][field]=value
            with self.assertRaises(ValueError):self.validate(entry)

    def test_all_grandfathered_runtime_entries_have_dated_backfill(self):
        entries=json.loads((ROOT/'security/licence-register.json').read_text())['components']
        for entry in entries:
            if entry['id'] not in self.policy['ladder']['legacy']:continue
            tier=entry['tier'];expected='2027-01-14' if tier>=3 else '2027-04-16'
            if entry['enterpriseGrade']['status']=='legacy-pending':
                self.assertEqual(entry['enterpriseGrade'],{'status':'legacy-pending','due':expected})
                self.assertEqual(gate.fingerprint(entry),self.policy['ladder']['legacy'][entry['id']]['sha256'])



if __name__=='__main__':unittest.main()
