"""Policy and configuration mutation gates for the bounded CPU lab profile."""
import copy
from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import wsl_endpoints as endpoints
from wsl_git_dns import corefile


class EndpointTests(unittest.TestCase):
    def test_all_resources_pass_contract(self):
        for objects in endpoints.groups().values():endpoints.check(objects)

    def test_privilege_mutation_fails(self):
        objects=endpoints.identity();dep=next(o for o in objects if o['kind']=='Deployment')
        dep['spec']['template']['spec']['containers'][0]['securityContext']['privileged']=True
        with self.assertRaises(ValueError):endpoints.check(objects)

    def test_floating_pull_policy_fails(self):
        objects=endpoints.identity();dep=next(o for o in objects if o['kind']=='Deployment')
        dep['spec']['template']['spec']['containers'][0]['imagePullPolicy']='Always'
        with self.assertRaises(ValueError):endpoints.check(objects)

    def test_gpu_allocation_fails(self):
        objects=endpoints.identity();dep=next(o for o in objects if o['kind']=='Deployment')
        dep['spec']['template']['spec']['containers'][0]['resources']['limits']['nvidia.com/gpu']=1
        with self.assertRaises(ValueError):endpoints.check(objects)

    def test_host_mount_fails(self):
        objects=endpoints.identity();dep=next(o for o in objects if o['kind']=='Deployment')
        dep['spec']['template']['spec']['volumes'].append({'name':'unapproved','hostPath':{'path':'/etc'}})
        with self.assertRaises(ValueError):endpoints.check(objects)

    def test_prometheus_image_and_security_mutations_fail(self):
        prom=next(o for o in endpoints.observability() if o['kind']=='Prometheus')
        for mutation in ('image','privilege','gpu'):
            obj=copy.deepcopy(prom)
            if mutation=='image':obj['spec']['image']='registry.vcloud.example.com/prometheus:latest'
            elif mutation=='privilege':obj['spec']['containers'][0]['securityContext']['privileged']=True
            else:obj['spec']['resources']['limits']['nvidia.com/gpu']=1
            with self.subTest(mutation=mutation),self.assertRaises(ValueError):endpoints.check([obj])

    def test_gateway_smoke_route_matches_existing_lab_labels(self):
        policy=next(o for o in endpoints.network() if o['metadata']['name']=='vcloud-wsl-smoke-gateway')
        self.assertEqual(policy['spec']['endpointSelector']['matchLabels'],{'k8s:vcloud.io/lab-role':'server'})

    def test_endpoint_gitops_grants_exclude_secrets_and_bootstrap_authority(self):
        from wsl_endpoints_gitops import definitions
        for obj in definitions():
            if obj['kind']=='Role':
                for rule in obj['rules']:
                    self.assertFalse(set(rule['resources']) & {'*','secrets','nodes','persistentvolumes','roles','rolebindings','ciliumnetworkpolicies'})
            if obj['kind']=='AppProject':self.assertEqual(obj['spec']['clusterResourceWhitelist'],[])

    def test_live_gitops_gate_requires_both_apps_healthy_without_conditions(self):
        from wsl_endpoint_acceptance import gitops
        apps=[{'metadata':{'name':name},'status':{'sync':{'status':'Synced','revision':'a'*40},'health':{'status':'Healthy'}}}
              for name in ('vcloud-wsl-platform','vcloud-wsl-endpoints')]
        self.assertEqual(len(gitops(apps)),2)
        with self.assertRaises(ValueError):gitops(apps[:1])
        for key in ('sync','health','conditions'):
            bad=copy.deepcopy(apps)
            if key=='conditions':bad[1]['status'][key]=[{'type':'ComparisonError'}]
            else:bad[1]['status'][key]['status']='Unknown'
            with self.subTest(key=key),self.assertRaises(ValueError):gitops(bad)

    def test_node_rbac_bindings_relocated(self):
        for o in endpoints.controllers():
            for s in o.get('subjects',[]):
                if s['kind']=='ServiceAccount':self.assertIn(s['namespace'],['platform-services','workload-apps'])

    def test_public_dns_only_and_no_private_answers(self):
        self.assertIn('140.82.121.4 github.com',corefile(['140.82.121.4']))
        for answers in ([],['127.0.0.1'],['10.0.0.1']):
            with self.assertRaises(ValueError):corefile(answers)

    def test_openbao_uses_persistent_postgres_verified_tls(self):
        code=(endpoints.HERE/'runtime-config.py').read_text()
        self.assertIn('sslmode=verify-full',code);self.assertIn('storage "postgresql"',code)
        self.assertIn('127.0.0.1:8201',code);self.assertIn('127.0.0.1:8202',code)
        self.assertNotIn('dev-root-token',code)

    def test_demo_bounded_cpu_scale_to_zero(self):
        demo=next(o for o in endpoints.application() if o['apiVersion']=='serving.knative.dev/v1')
        self.assertEqual(demo['spec']['template']['metadata']['annotations']['autoscaling.knative.dev/min-scale'],'0')
        self.assertEqual(demo['spec']['template']['metadata']['annotations']['autoscaling.knative.dev/max-scale'],'1')


if __name__=='__main__':unittest.main()
