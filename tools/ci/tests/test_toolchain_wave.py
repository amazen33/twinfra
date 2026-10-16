"""Owner-named wave proposals are narrow; no automatic or blanket approval."""
from datetime import date
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from toolchain_wave import review


class Wave(unittest.TestCase):
    def setUp(self):
        self.value={'target':'example/image@sha256:'+'a'*64,'package':'golang.org/x/net',
            'version':'v0.58.0','vulnerability':'CVE-2026-78663','aliases':['GO-2026-6612'],
            'severity':'Critical','fixVersions':['0.60.0'],'blockReason':'new fixable finding'}
        self.controls={'clusterOrLanOnly':True,'externalEgress':'R2 endpoint','noExternalService':True}

    def check(self,values=None,**kw):
        return review(values or [self.value],eligible_fixed_release=kw.get('eligible',False),
                      controls=kw.get('controls',self.controls),on=date(2026,10,16))

    def test_exact_image_cve_proposals_pending_owner_and_thirty_days(self):
        report=self.check();self.assertEqual(report['status'],'owner-review-required')
        entry=report['proposedExceptions'][0]
        self.assertEqual(entry['expires'],'2026-11-15');self.assertEqual(entry['approvedBy'],'pending-owner')
        self.assertEqual(entry['target'],self.value['target'])

    def test_unlisted_stdlib_high_cannot_hide_behind_the_wave(self):
        value=self.value|{'package':'stdlib','severity':'High','vulnerability':'GO-2026-6605','aliases':[],'fixVersions':['1.26.9']}
        report=self.check([self.value,value]);self.assertEqual(report['status'],'blocked')
        self.assertFalse(report['proposedExceptions']);self.assertEqual(len(report['unlisted']),1)

    def test_named_core_high_and_exact_fix_only(self):
        value=self.value|{'severity':'High','vulnerability':'fixture','aliases':[],'package':'golang.org/x/crypto','fixVersions':['v0.56.0']}
        self.assertEqual(self.check([value])['status'],'owner-review-required')
        self.assertEqual(self.check([value|{'fixVersions':['0.55.0']}])['status'],'blocked')

    def test_already_approved_findings_are_not_proposed_again(self):
        self.assertEqual(self.check([self.value|{'blocked':False}])['status'],'no-exception-needed')

    def test_kev_eligible_fixed_release_or_missing_isolation_never_proposed(self):
        for values,kwargs in (([self.value|{'kev':True}],{}),([self.value],{'eligible':True}),
                              ([self.value],{'controls':self.controls|{'noExternalService':False}})):
            self.assertEqual(self.check(values,**kwargs)['status'],'blocked')


if __name__=='__main__':unittest.main()
