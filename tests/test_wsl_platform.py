"""Local platform security, finite storage and bounded automatic growth gates."""
import copy
from datetime import datetime,timezone
import json
from pathlib import Path
import re
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tools'))
import wsl_platform as platform
from wsl_db_scaler import plan,quantity
from wsl_db_test import manifest as sql_client


class PlatformTests(unittest.TestCase):
    def setUp(self):
        self.now=1800000000
        self.cluster={'metadata':{'name':platform.DB,'resourceVersion':'10'},'spec':{'instances':1,
            'resources':{'requests':{'cpu':'500m','memory':'512Mi'},'limits':{'cpu':'500m','memory':'512Mi'}}},
            'status':{'phase':'Cluster in healthy state','readyInstances':1,'currentPrimary':platform.DB+'-1','targetPrimary':platform.DB+'-1'}}
        self.samples=[{'metadata':{'name':platform.DB+'-1'},'timestamp':datetime.fromtimestamp(self.now-3+i,timezone.utc).isoformat(),
                       'containers':[{'name':'postgres','usage':{'cpu':'490000000n','memory':'200Mi'}}]} for i in range(3)]

    def test_all_rendered_groups_keep_node_contract(self):
        for group in [platform.infrastructure(),platform.storage(),platform.network(),platform.git_dns(),platform.workload(),platform.application()]:platform.audit(group)

    def test_storage_path_cannot_be_annotated_into_allowlist(self):
        objects=platform.storage();objects[1]['spec']['local']['path']='/etc'
        with self.assertRaises(ValueError):platform.audit(objects)

    def test_storage_node_cannot_be_changed(self):
        objects=platform.storage();objects[1]['spec']['nodeAffinity']['required']['nodeSelectorTerms'][0]['matchExpressions'][0]['values']=['other-node']
        with self.assertRaises(ValueError):platform.audit(objects)

    def test_no_privileged_controller(self):
        objects=platform.infrastructure();obj=next(o for o in objects if o['kind']=='Deployment')
        obj['spec']['template']['spec']['containers'][0]['securityContext']['privileged']=True
        with self.assertRaises(ValueError):platform.audit(objects)

    def test_metrics_tls_is_verified(self):
        service=next(o for o in platform.infrastructure() if o['kind']=='APIService')
        self.assertNotIn('insecureSkipTLSVerify',service['spec'])
        dep=next(o for o in platform.infrastructure() if o['kind']=='Deployment' and o['metadata']['name']=='metrics-server')
        args=dep['spec']['template']['spec']['containers'][0]['args']
        self.assertTrue(any(a.startswith('--kubelet-certificate-authority=') for a in args))
        self.assertNotIn('--kubelet-insecure-tls',args)

    def test_gitops_preserves_scaler_and_storage_ownership(self):
        project,app=platform.application();self.assertEqual(project['spec']['clusterResourceWhitelist'],[])
        self.assertFalse(app['spec']['syncPolicy']['automated']['prune'])
        self.assertIn('/spec/resources',app['spec']['ignoreDifferences'][0]['jsonPointers'])
        self.assertIn('RespectIgnoreDifferences=true',app['spec']['syncPolicy']['syncOptions'])

    def test_github_egress_is_not_wildcard(self):
        policy=next(p for p in platform.network() if p['metadata']['name']=='vcloud-wsl-argo-repo')
        fqdn=[r['toFQDNs'] for r in policy['spec']['egress'] if 'toFQDNs' in r]
        self.assertEqual(fqdn,[[{'matchName':'github.com'}]])

    def test_renderer_drift_is_detectable(self):
        with tempfile.TemporaryDirectory() as directory:
            platform.render(Path(directory))
            self.assertEqual((ROOT/'lab/wsl/gitops/workload.yaml').read_bytes(),(Path(directory)/'workload.yaml').read_bytes())

    def test_cpu_pressure_grows_only_cluster(self):
        patch,_=plan(self.cluster,self.samples,self.now)
        self.assertEqual(patch[2]['value']['requests'],{'cpu':'625m','memory':'512Mi'})
        self.assertEqual(patch[0]['op'],'test');self.assertEqual(patch[1]['op'],'test')

    def test_memory_pressure_has_bounded_growth(self):
        for sample in self.samples:sample['containers'][0]['usage']={'cpu':'1m','memory':'480Mi'}
        patch,_=plan(self.cluster,self.samples,self.now)
        self.assertEqual(patch[2]['value']['requests'],{'cpu':'500m','memory':'640Mi'})

    def test_sql_client_does_not_mount_ca_key_or_expose_password_env(self):
        obj=sql_client();platform.audit([obj])
        ca=next(v for v in obj['spec']['volumes'] if v['name']=='ca')
        self.assertEqual(ca['secret']['items'],[{'key':'ca.crt','path':'ca.crt'}])
        self.assertNotIn('env',obj['spec']['containers'][0])

    def test_transient_cpu_spike_does_not_scale(self):
        self.samples[1]['containers'][0]['usage']['cpu']='10m'
        self.assertIsNone(plan(self.cluster,self.samples,self.now)[0])

    def test_no_metrics_age_bypass(self):
        self.samples[0]['timestamp']=datetime.fromtimestamp(self.now-180,timezone.utc).isoformat()
        self.assertIsNone(plan(self.cluster,self.samples,self.now)[0])

    def test_cached_metric_is_not_three_samples(self):
        self.samples[1]['timestamp']=self.samples[0]['timestamp']
        self.assertEqual(plan(self.cluster,self.samples,self.now)[1],'Metrics did not advance')

    def test_no_other_primary_metrics(self):
        self.samples[1]['metadata']['name']='another-db'
        self.assertIsNone(plan(self.cluster,self.samples,self.now)[0])

    def test_unhealthy_cluster_not_scaled(self):
        self.cluster['status']['readyInstances']=0
        self.assertIsNone(plan(self.cluster,self.samples,self.now)[0])

    def test_no_shrink(self):
        for sample in self.samples:sample['containers'][0]['usage']['cpu']='1m'
        self.assertIsNone(plan(self.cluster,self.samples,self.now)[0])

    def test_maximum_cannot_be_exceeded(self):
        for kind in ('requests','limits'):self.cluster['spec']['resources'][kind]={'cpu':'1','memory':'1Gi'}
        for sample in self.samples:sample['containers'][0]['usage']={'cpu':'990m','memory':'1000Mi'}
        self.assertIsNone(plan(self.cluster,self.samples,self.now)[0])

    def test_cooldown(self):
        self.cluster['metadata']['annotations']={'vcloud.io/resources-last-scaled':datetime.fromtimestamp(self.now-60,timezone.utc).isoformat()}
        self.assertEqual(plan(self.cluster,self.samples,self.now)[1],'cooldown')

    def test_cpu_nanocores_and_negative_values(self):
        self.assertEqual(quantity('1000000n'),quantity('1m'))
        with self.assertRaises(ValueError):quantity('-1m')

    def test_embedded_host_python_compiles(self):
        for name in ('prepare-storage.sh','platform.sh','test-network.sh'):
            for block in re.findall(r"<<'PY'\n(.*?)\nPY",(ROOT/'lab/wsl'/name).read_text(),re.S):compile(block,name,'exec')


if __name__=='__main__':unittest.main()
