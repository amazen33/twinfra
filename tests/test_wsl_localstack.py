"""Fail-closed lab image, API routing and restricted-security regression gates."""
import copy
import importlib.util
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
import yaml

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
import wsl_localstack as aws
import wsl_endpoints as endpoints


class LocalStackTests(unittest.TestCase):
    def test_frozen_images_and_generated_sources(self):
        aws.lock()
        for name,objects in [('deployment.yaml',[aws.workloads()[0]]),('service.yaml',[aws.workloads()[1]]),
                             ('apisix-route.yaml',[aws.routes()[2]])]:
            self.assertEqual(list(yaml.safe_load_all((aws.HERE/name).read_text())),objects)

    def test_pod_security_mutations_fail(self):
        for change in ('privileged','root','escalate','hostpath','docker','gpu','pull'):
            objects=aws.workloads();pod=objects[0]['spec']['template']['spec'];container=pod['containers'][0]
            if change=='privileged':container['securityContext']['privileged']=True
            elif change=='root':container['securityContext']['runAsUser']=0
            elif change=='escalate':container['securityContext']['allowPrivilegeEscalation']=True
            elif change in ('hostpath','docker'):pod['volumes'].append({'name':'bad','hostPath':{'path':'/var/run/docker.sock' if change=='docker' else '/etc'}})
            elif change=='gpu':container['resources']['limits']['nvidia.com/gpu']=1
            else:container['imagePullPolicy']='Always'
            with self.subTest(change=change),self.assertRaises(ValueError):endpoints.check(objects)

    def test_routing_auth_and_tls(self):
        objects=aws.routes();gateway=next(o for o in objects if o['kind']=='GatewayProxy')
        cp=gateway['spec']['provider']['controlPlane']
        self.assertTrue(cp['tlsVerify']);self.assertTrue(all(e.startswith('https://') for e in cp['endpoints']))
        self.assertEqual(cp['auth']['adminKey']['valueFrom']['secretKeyRef'],{'name':aws.ADMIN_SECRET,'key':'admin-key'})
        route=next(o for o in objects if o['metadata']['name']==aws.NAME)
        rule=route['spec']['http'][0]
        self.assertEqual(rule['match']['hosts'],['aws.platform.example.com'])
        self.assertEqual(rule['backends'][0]['serviceName'],aws.NAME)
        self.assertEqual(rule['backends'][0]['servicePort'],4566)

    def test_no_node_or_world_ingress_to_aws(self):
        policy=aws.network('10.42.0.1')[0]['spec']
        self.assertEqual(policy['egress'],[])
        self.assertEqual(len(policy['ingress']),1)
        self.assertEqual(set(policy['ingress'][0]),{'fromEndpoints','toPorts'})
        self.assertEqual(policy['ingress'][0]['fromEndpoints'][0]['matchLabels']['k8s:app.kubernetes.io/name'],'apisix')

    def test_controller_never_writes_secrets_or_uses_wildcard_rbac(self):
        for obj in aws.controller():
            if obj['kind'] in ('Role','ClusterRole'):
                for rule in obj['rules']:
                    self.assertNotIn('*',rule['resources']);self.assertNotIn('*',rule['verbs'])
                    if 'secrets' in rule['resources']:self.assertEqual(rule['verbs'],['get','list','watch'])

    def test_health_rejects_disabled_or_missing_service(self):
        spec=importlib.util.spec_from_file_location('localstack_api_test',aws.HERE/'test-api.py')
        # Health logic is independently exercised without a real AWS SDK connection.
        module=importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules,{'boto3':__import__('types').ModuleType('boto3'),
             'botocore.config':__import__('types').SimpleNamespace(Config=object)}):spec.loader.exec_module(module)
        valid={'services':dict.fromkeys(aws.SERVICES,'running')}
        self.assertEqual(module.check_health(valid),valid['services'])
        for state in ('available','stopped',None):
            bad=copy.deepcopy(valid);bad['services']['ec2']=state
            with self.subTest(state=state),self.assertRaises(RuntimeError):module.check_health(bad)

    def test_no_real_aws_or_license_credentials_in_profile(self):
        pod=aws.workloads()[0]['spec']['template']['spec'];env={e['name']:e.get('value') for e in pod['containers'][0]['env']}
        self.assertFalse(set(env)&{'LOCALSTACK_AUTH_TOKEN','AWS_ACCESS_KEY_ID','AWS_SECRET_ACCESS_KEY'})
        self.assertEqual(env['SERVICES'],'s3,ec2,iam,dynamodb')
        self.assertEqual(env['SKIP_INFRA_DOWNLOADS'],'1')
        self.assertFalse(pod['automountServiceAccountToken'])


if __name__=='__main__':unittest.main()
