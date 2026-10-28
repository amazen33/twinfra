"""R12 batch boundaries, explicit pending approval and unchanged expiry gates."""
from copy import deepcopy
from datetime import date, timedelta
import json
from pathlib import Path
import sys
import unittest

ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'tools/ci'))
import r12_exceptions as r12
import supply_chain as sc
from refresh_security_wave import validate_comparison, CASES_SELECTED


class R12(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.batch=r12.read(ROOT/'security/proposals/r12-vulnerability-exceptions.json')
        cls.report=r12.read(ROOT/'security/security-wave-2026-10-review.json')

    def test_pending_batch_cannot_pass_the_active_gate(self):
        self.assertTrue(all(e['approvedBy']=='' for e in self.batch['exceptions']))
        with self.assertRaisesRegex(ValueError,'Malformed vulnerability exception'):
            sc.validate_exceptions(self.batch,ROOT,r12.ON)
        active=r12.read(ROOT/'security/vulnerability-exceptions.json')
        self.assertFalse(any(e['vulnerability'] in ('CVE-2026-55797','CVE-2026-77459') for e in active['exceptions']))

    def test_generator_outputs_cannot_escape_the_repository(self):
        from refresh_security_wave import save as save_refresh
        for writer in (save_refresh,r12.save):
            with self.assertRaises(ValueError):writer(ROOT/'..'/'outside-r12.json',{'data':'fixture'})

    def test_individual_renewals_fix_versions_and_controls(self):
        rows=self.batch['exceptions']
        self.assertEqual(len(rows),420)
        self.assertEqual(len({r12.identity(e) for e in rows}),len(rows))
        self.assertEqual(sum(e['severity']=='Critical' for e in rows),59)
        for entry in rows:
            self.assertEqual(entry['workOrder'],'WO-46')
            self.assertEqual(entry['owner'],'amazen33')
            span=(date.fromisoformat(entry['expires'])-date.fromisoformat(entry['createdOn'])).days
            self.assertLessEqual(span,30 if entry['severity']=='Critical' else 60)
            self.assertTrue(entry['controls'])
            self.assertNotIn('*',entry['vulnerability'])
        for row in self.report['ledger']:
            self.assertTrue(row['fixVersions'])
            self.assertTrue(row['evidence']['advisorySources'])
            self.assertTrue(row['reachability'].startswith('Potentially reachable:'))
            self.assertNotIn('not reachable',row['reachability'])

    def test_calendar_kev_term_and_checkpoint(self):
        rows=self.batch['exceptions']
        result=r12.calendar(rows,date(2026,10,30))
        self.assertEqual(result[-1]['date'],'2026-11-16')
        self.assertEqual(result[-1]['nearestExpiryDays'],8)
        kev=next(e for e in rows if e['vulnerability']=='CVE-2026-111497')
        self.assertEqual(kev['expires'],'2026-11-24')
        self.assertIn('checkpoint 2026-11-13',kev['reason'])
        bad=deepcopy(rows);next(e for e in bad if e['vulnerability']=='CVE-2026-111497')['expires']='2026-11-13'
        with self.assertRaises(ValueError):r12.calendar(bad,date(2026,10,30))
        with self.assertRaises(ValueError):r12.calendar(rows,date(2026,10,31))
        late=deepcopy(rows)
        next(e for e in late if e['vulnerability']=='CVE-2026-111497')['expires']='2026-11-28'
        with self.assertRaisesRegex(ValueError,'within seven days'):
            r12.calendar(late,date(2026,11,3))

    def test_toolchain_and_normal_routes_are_separate(self):
        ledger={r12.identity(v):v for v in self.report['ledger']}
        for entry in self.batch['exceptions']:
            row=ledger[r12.identity(entry)]
            self.assertEqual('toolchainWave' in entry,row['route']=='toolchain-wave')
            if row['package'] in ('google.golang.org/grpc','go.etcd.io/etcd/client/pkg/v3','go.opentelemetry.io/otel/sdk'):
                self.assertEqual(row['route'],'normal')
        self.assertEqual(self.report['counts'],{'normal':149,'toolchain-wave':270,'KEV':1})

    def test_closed_rows_have_scan_evidence_and_grace_risk_is_visible(self):
        closed=self.report['closedExceptions']
        self.assertEqual({e['entry']['vulnerability'] for e in closed},
                         {'CVE-2026-19445','CVE-2026-55797','CVE-2026-77459'})
        self.assertTrue(all(e['evidence']==r12.AFTER_RUN for e in closed))
        self.assertEqual(len(self.report['outOfScopeGraceFindings']),6)
        self.assertTrue(all(not e['blocked'] for e in self.report['outOfScopeGraceFindings']))
        self.assertFalse(any(e['target'].startswith('lockfile:') for e in self.batch['exceptions']))

    def test_only_three_owner_candidates_and_no_guava_introduction(self):
        self.assertEqual(set(CASES_SELECTED),{'argocd355','ministack1533','keycloak2681'})
        images=r12.read(ROOT/'security/security-wave-2026-10-images.json')['images']
        self.assertEqual(set(images),{'argocd','keycloak','ministack'})
        for row in images.values():
            self.assertTrue(row['comparison']['strictImprovement'])
            self.assertFalse(row['comparison']['introduced'])
        # Exercise the same shared promotion boundary with a forged comparison.
        from security_wave_2026_10 import CASES
        name,release,ref=CASES['keycloak2681']
        old='quay.io/keycloak/keycloak@sha256:'+'a'*64
        f=lambda pkg,cve:{'package':pkg,'vulnerability':cve,'severity':'High','fixAvailable':True}
        report={'component':name,'release':release,'imageCodeExecuted':False,'executionContractUnchanged':True,
            'images':[{'reference':old,'coverage':'complete-oci-archive-linux-amd64','findings':[f('other','CVE-old')]},
                      {'reference':ref,'coverage':'complete-oci-archive-linux-amd64','findings':[f('guava','CVE-new')]}]}
        with self.assertRaisesRegex(ValueError,'introduces risk'):
            validate_comparison(report,'keycloak2681',{'source':old,'digest':'sha256:'+'a'*64})

    def test_argocd_controls_and_source_boundaries(self):
        sys.path.insert(0,str(ROOT/'tools'))
        import platform_dev as dev
        policies={e['metadata']['name']:e['spec'] for e in dev.network() if e['kind']=='CiliumNetworkPolicy'}
        server=policies['twinfra-argocd-server-network']
        self.assertEqual(server['ingress'],[{'fromEntities':['host','remote-node','health'],
            'toPorts':[{'ports':[{'port':'8080','protocol':'TCP'}]}]}])
        repo=policies['twinfra-argocd-repo-server-network']
        self.assertEqual([r for r in repo['egress'] if 'toFQDNs' in r],
            [{'toFQDNs':[{'matchName':'github.com'}],'toPorts':[{'ports':[{'port':'443','protocol':'TCP'}]}]}])
        for name in ('twinfra-argocd-server-network','twinfra-argocd-application-controller-network'):
            self.assertFalse(any('toFQDNs' in r or 'toCIDR' in r or r.get('toEntities')==['world'] for r in policies[name]['egress']))
        root,children=dev.applications()
        project=next(e for e in root if e['kind']=='AppProject')
        self.assertEqual(project['spec']['sourceRepos'],['https://github.com/amazen33/twinfra.git'])
        for item in [*root,*children]:
            if item['kind']!='Application':continue
            self.assertEqual(item['metadata']['annotations']['argocd.argoproj.io/compare-options'],
                             'ServerSideDiff=true,IncludeMutationWebhook=true')
            self.assertEqual(set(item['spec']['source']),{'repoURL','targetRevision','path'})


if __name__=='__main__':unittest.main()
