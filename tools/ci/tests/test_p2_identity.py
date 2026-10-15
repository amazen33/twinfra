"""WO-34 3a risk identities and approval carry; all inputs are synthetic/offline."""
import copy
from datetime import date
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

CI=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(CI))
import supply_chain as sc
import supply_chain_report as reporter
import promote_p2 as promotion

ON=date(2026,10,15)
KEV=dict(catalogVersion='fixture',vulnerabilities=[])
EMPTY=dict(version=1,exceptions=[])
OLD='registry.k8s.io/example@sha256:'+'a'*64
NEW='registry.k8s.io/example@sha256:'+'b'*64
COMP='deploy/common/bootstrap-images.lock.json:example'


def finding(target,package='stdlib',version='v1',cve='CVE-2026-1000',severity='High'):
    return sc.finding(target,package,version,[cve],severity,True,'fixture',True,['v9'])


def classify(current,old,components=None,previous_component=COMP,base=True):
    item=dict(target=NEW,origins=components or [COMP],previousInputs=[dict(component=previous_component,target=OLD)])
    return sc.classify_image_findings(current,old,[item],base)


def result(values):return dict(findings=values,inventory=dict(images=[],coverage=[]))


class ImageIdentities(unittest.TestCase):
    def test_carried_identity_not_introduced_even_new_digest_and_version(self):
        old=finding(OLD);new=finding(NEW,version='v2')
        classify([new],[old])
        self.assertFalse(new['introduced']);self.assertEqual(new['previousKeys'],[old['key']])
        report=sc.evaluate(result([new]),EMPTY,KEV,state={old['key']:'2026-10-01'},on=ON)
        self.assertEqual(report['findings'][0]['firstSeen'],'2026-10-01')
        self.assertEqual(report['findings'][0]['blockReason'],'High with fix aged 14 days')

    def test_genuinely_new_identity_on_changed_digest_blocks_immediately(self):
        for fault in (dict(cve='CVE-2026-2000'),dict(package='different-package')):
            new=finding(NEW,**fault);classify([new],[finding(OLD)])
            self.assertTrue(new['introduced'])
            self.assertEqual(sc.evaluate(result([new]),EMPTY,KEV,on=ON)['status'],'failed')

    def test_carried_critical_without_exact_carried_exception_still_blocks(self):
        old=finding(OLD,severity='Critical');new=finding(NEW,version='v2',severity='Critical');classify([new],[old])
        self.assertFalse(new['introduced'])
        self.assertEqual(sc.evaluate(result([new]),EMPTY,KEV,on=ON)['status'],'failed')

    def test_other_component_or_missing_baseline_cannot_lend_identity(self):
        for previous in ('other-component',None):
            new=finding(NEW);classify([new],[finding(OLD)],previous_component=previous)
            self.assertTrue(new['introduced'])

    def test_clock_persists_across_digest_change_issue_roundtrip_and_nightly(self):
        old=finding(OLD);new=finding(NEW,version='v2');classify([new],[old])
        report=sc.evaluate(result([new]),EMPTY,KEV,state={old['key']:'2026-10-05'},on=ON)
        report['markdown']=sc.markdown(report)
        with patch.object(reporter,'request',side_effect=[{'name':'security'},[],{'html_url':'issue/1'}]) as api:
            reporter.publish(report,sc.TITLE,'https://github.com/amazen33/twinfra/actions/runs/123','fixture')
            body=api.call_args.args[2]['body']
        issue=dict(title=sc.TITLE,user=dict(login='github-actions[bot]'),labels=[dict(name='security')],body=body,html_url='issue/1')
        with patch.object(sc,'fetch',return_value=json.dumps([issue]).encode()):state,_=sc.previous_state()
        nightly=finding(NEW,version='v3');nightly['introduced']=False;classify([nightly],[],base=False)
        future=sc.evaluate(result([nightly]),EMPTY,KEV,state=state,on=date(2026,10,20))
        self.assertEqual(future['findings'][0]['firstSeen'],'2026-10-05')
        self.assertEqual(future['status'],'failed')

    def test_first_nightly_migrates_old_issue_records_before_component_keys_exist(self):
        old=finding(OLD);new=finding(NEW,version='v2');new['introduced']=False
        sc.classify_image_findings([new],[],[dict(target=NEW,origins=[COMP],historicalTargets=[OLD])],False)
        state=sc.FirstSeenState({old['key']:'2026-10-01'})
        state.identities={old['key']:[old[k] for k in ('target','package','version','vulnerability')]}
        report=sc.evaluate(result([new]),EMPTY,KEV,state=state,on=ON)
        self.assertEqual(report['findings'][0]['firstSeen'],'2026-10-01');self.assertEqual(report['status'],'failed')

    def test_changed_images_scan_baseline_and_candidate_against_one_database(self):
        item=dict(target=NEW,source='registry:'+NEW,digest='sha256:'+'b'*64,origins=[COMP],introduced=True,
                  previousInputs=[dict(component=COMP,target=OLD,source='registry:'+OLD,digest='sha256:'+'a'*64)])
        plan=dict(images=[item],lockfiles=[],base='c'*40)
        calls=[]
        def sboms(value,tools,cache,out):
            self.assertEqual({v['target'] for v in value['images']},{OLD,NEW})
            return [dict(v,sbom=v['target']) for v in value['images']]
        def run(command,output,**kwargs):
            calls.append(command)
            match=dict(vulnerability=dict(id='CVE-2026-1000',severity='High',fix=dict(state='fixed',versions=['v9'])),
                       artifact=dict(name='stdlib',version='v2' if NEW in str(command) else 'v1'))
            Path(output).write_text(json.dumps(dict(matches=[match])) if str(output).endswith('.grype.json') else '{}')
        with tempfile.TemporaryDirectory() as directory,patch.object(sc,'sboms',side_effect=sboms),patch.object(sc,'run',side_effect=run):
            report=sc.scan(plan,dict(grype='fixture'),Path(directory)/'cache',Path(directory))
        self.assertEqual(sum(cmd[1:3]==['db','update'] for cmd in calls),1)
        self.assertFalse(report['findings'][0]['introduced']);self.assertEqual(len(report['previousFindings']),1)


class CarriedExceptions(unittest.TestCase):
    def fixtures(self):
        rows=[];ledger=[]
        for name in promotion.PINS:
            old=finding(OLD+name,severity='Critical');new=finding(NEW+name,version='v2',severity='Critical')
            fixed=finding(OLD+name,package='fixed',cve='CVE-2026-2000',severity='Critical')
            for side,values in [('before',[old,fixed]),('after',[new])]:
                rows.append(dict(name=name+'-'+side,reference=(OLD if side=='before' else NEW)+name,
                                 coverage='complete-oci-archive-linux-amd64',findings=values))
            for f in (old,fixed):
                ledger.append({k:f[k] for k in ('target','package','version','vulnerability','severity')}|
                    dict(reason='Unchanged owner-approved reason.',approvedBy='amazen33',owner='amazen33',workOrder='WO-34',
                         createdOn='2026-10-13',expires='2026-11-12'))
        return dict(images=rows),dict(version=1,exceptions=ledger)

    def test_carry_preserves_reason_owner_dates_and_closes_fixed_identities(self):
        comparison,ledger=self.fixtures();new,carried,closed=promotion.carry_exceptions(comparison,ledger)
        self.assertEqual((len(carried),len(closed),len(new['exceptions'])),(2,2,2))
        for entry in carried:
            for key in ('reason','approvedBy','owner','createdOn','expires','vulnerability','severity'):
                self.assertEqual(entry['before'][key],entry['after'][key])
            self.assertNotEqual(entry['before']['target'],entry['after']['target'])
            self.assertNotEqual(entry['before']['version'],entry['after']['version'])

    def test_new_candidate_identity_and_missing_critical_approval_stop(self):
        comparison,ledger=self.fixtures()
        row=next(v for v in comparison['images'] if v['name']=='coredns-after')
        row['findings'].append(finding(NEW+'coredns',cve='CVE-2026-9999'))
        with self.assertRaisesRegex(ValueError,'strict'):promotion.carry_exceptions(comparison,ledger)
        row['findings'][-1]['severity']='Medium'
        with self.assertRaisesRegex(ValueError,'new vulnerability identity'):promotion.carry_exceptions(comparison,ledger)
        comparison,ledger=self.fixtures();ledger['exceptions']=[]
        with self.assertRaisesRegex(ValueError,'lacks an existing'):promotion.carry_exceptions(comparison,ledger)

    def test_go_entries_receive_controls_per_affected_package_without_renewal(self):
        comparison,ledger=self.fixtures()
        for row in comparison['images']:
            for f in row['findings']:
                if f['package']=='stdlib':f['aliases'].append('GO-2026-6612')
        _,carried,_=promotion.carry_exceptions(comparison,ledger)
        for entry in carried:
            self.assertEqual(entry['after']['controls'],promotion.CONTROLS)
            self.assertEqual(entry['after']['expires'],'2026-11-12')


if __name__=='__main__':unittest.main()
