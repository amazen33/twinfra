"""WO-07 offline boundary and migration tests; no live deployment or login."""
import copy
import gzip
import json
from pathlib import Path
import sys
import tempfile
import unittest

import jsonschema
import yaml
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
import perses
import platform_dev
from check_dashboard_removal import violations
from vcloud_console import routes


class PersesTests(unittest.TestCase):
    def test_pinned_release_integrity_and_aged_images(self):
        perses.crds();perses.sboms()

    def test_tampered_sbom_chain_fails(self):
        entry=perses.lock()['images']['perses']
        original=json.loads(gzip.decompress((ROOT/entry['imageSBOM']['path']).read_bytes()))
        for part in ('index','attestation','statement'):
            obj=copy.deepcopy(original)
            if part=='index':obj[part]+=' '
            else:obj['platforms']['amd64'][part]+=' '
            with self.subTest(part=part),self.assertRaises(ValueError):perses.verify_sbom(obj,entry['digest'])

    def test_no_new_sbom_baselines_or_pending_removal(self):
        register=json.loads((ROOT/'security/licence-register.json').read_text())
        entries=[x for x in register['components'] if x['name'].startswith('quay.io/persesdev/')]
        self.assertEqual(len(entries),2)
        for entry in entries:self.assertEqual((entry['class'],entry['spdx']),('allowed','Apache-2.0'));self.assertIn('imageSBOM',entry)
        self.assertFalse(any('grafana' in x['name'] for x in register['components']))

    def test_module3_all_queries_preserved(self):
        from render_module3 import resources
        cm=next(x for x in resources()['module-3/manifests/observability.yaml'] if x['kind']=='ConfigMap')
        dashboard=json.loads(cm['data']['twinfra-delivery.json'])
        panels=dashboard['spec']['panels'].values()
        queries=[(x['spec']['display']['name'],x['spec']['queries'][0]['spec']['plugin']['spec']['query']) for x in panels]
        self.assertEqual(queries,perses.DELIVERY)

    def test_both_dashboards_provisioned_with_project_datasource(self):
        resources=perses.provisioned('http://prometheus:9090')
        self.assertEqual([x['kind'] for x in resources],['Project','Datasource','Dashboard','Dashboard'])
        self.assertEqual([len(x['spec']['panels']) for x in resources if x['kind']=='Dashboard'],[4,3])
        self.assertEqual(resources[1]['spec']['plugin']['spec']['proxy']['spec']['url'],'http://prometheus:9090')
        for d in resources[2:]:
            for item in d['spec']['layouts'][0]['spec']['items']:
                self.assertIn(item['content']['$ref'].rsplit('/',1)[1],d['spec']['panels'])

    def test_instance_matches_served_not_deprecated_schema(self):
        crd=next(x for x in perses.crds() if x['spec']['names']['kind']=='Perses')
        version=next(x for x in crd['spec']['versions'] if x['name']=='v1alpha2')
        self.assertTrue(version['served']);self.assertFalse(version.get('deprecated',False))
        instance=next(x for x in perses.objects(platform_dev.NS) if x['kind']=='Perses')
        self.assertEqual([e.message for e in jsonschema.Draft7Validator(version['schema']['openAPIV3Schema']).iter_errors(instance)],[])

    def test_server_nonroot_no_token_no_pvc_and_readonly_git_resources(self):
        objects=perses.objects(platform_dev.NS)
        instance=next(x for x in objects if x['kind']=='Perses')['spec']
        self.assertTrue(instance['podSecurityContext']['runAsNonRoot'])
        self.assertEqual(instance['podSecurityContext']['seccompProfile']['type'],'RuntimeDefault')
        self.assertTrue(instance['config']['security']['readonly'])
        self.assertEqual(instance['config']['api_prefix'],perses.PREFIX)
        self.assertNotIn('persistentVolumeClaimTemplate',instance['storage'])
        self.assertEqual(instance['config']['security']['encryption_key_file'],'/identity/encryption-key')
        self.assertFalse(next(x for x in objects if x['kind']=='ServiceAccount' and x['metadata']['name']=='twinfra-perses')['automountServiceAccountToken'])

    def test_operator_readonly_cluster_informers_namespaced_mutations(self):
        objects=perses.objects(platform_dev.NS)
        reader=next(x for x in objects if x['kind']=='ClusterRole')
        for rule in reader['rules']:self.assertEqual(rule['verbs'],['get','list','watch'])
        writer=next(x for x in objects if x['kind']=='Role')
        self.assertFalse(any('secrets' in x['resources'] for x in writer['rules']))
        self.assertEqual(writer['metadata']['namespace'],platform_dev.NS)

    def test_apisisix_preserves_prefix_strips_forged_headers_uses_secure_oidc(self):
        template=json.loads((platform_dev.COMMON/'apisix-routes.json').read_text())['routes'][0]
        route=perses.gateway_route(template,platform_dev.NS)
        self.assertEqual(route['uris'],[perses.PREFIX,perses.PREFIX+'/*'])
        oidc=route['plugins']['openid-connect']
        self.assertEqual(oidc['unauth_action'],'auth');self.assertTrue(oidc['ssl_verify'])
        self.assertTrue(oidc['session']['cookie_secure']);self.assertEqual(oidc['session']['cookie_path'],'/console')
        self.assertIn('claim_schema',oidc);self.assertEqual(oidc['token_signing_alg_values_expected'],'RS256')
        self.assertIn('ngx.req.clear_header',route['plugins']['serverless-pre-function']['functions'][0])
        rewrite=route['plugins']['proxy-rewrite']
        self.assertNotIn('regex_uri',rewrite);self.assertIn('X-Access-Token',rewrite['headers']['remove'])
        legacy=next(x for x in routes() if x['metadata']['name']=='vcloud-portal-metrics')['spec']['http'][0]
        self.assertEqual(legacy['priority'],200);self.assertEqual(legacy['backends'][0]['serviceName'],'twinfra-perses')

    def test_network_no_world_or_ingress_from_other_workloads(self):
        objects=perses.objects(platform_dev.NS)
        policy=next(x for x in objects if x['metadata']['name']=='twinfra-perses-network')['spec']
        self.assertEqual(policy['ingress'][0]['fromEndpoints'][0]['matchLabels']['k8s:app.kubernetes.io/name'],'twinfra-gateway')
        health=policy['ingress'][1]
        self.assertEqual(health['toPorts'][0]['rules']['http'],[{'method':'GET','path':perses.PREFIX+'/api/v1/health'}])
        self.assertNotIn('world',json.dumps(policy));self.assertNotIn('toCIDR',json.dumps(policy))
        deny=next(x for x in objects if x['kind']=='NetworkPolicy')['spec']
        self.assertEqual(deny['ingress'],[]);self.assertEqual(deny['egress'],[])

    def test_retained_wsl_gitops_has_no_bootstrap_authority(self):
        from wsl_endpoints import perses_groups
        groups=perses_groups()
        self.assertTrue(any(x['kind']=='Deployment' for x in groups['controllers']))
        self.assertFalse(any(x['kind'] in ('Deployment','ClusterRole','Role') for x in groups['workloads']))
        self.assertTrue(any(x['kind']=='Perses' for x in groups['workloads']))

    def test_removed_image_secret_access_and_generator_mutations_fail(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            for path,text in [('deploy/test.yaml','image: docker.io/grafana/grafana:13.2.3'),
                              ('tools/new_generator.py',"create('vcloud-wsl-grafana-admin',{})"),
                              ('lab/test.sh','port-forward svc/grafana 3000:3000'),
                              ('deploy/test.json','{"env":[{"name":"GF_AUTH_ANONYMOUS_ENABLED","value":"true"}]}')]:
                p=root/path;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(text)
                self.assertTrue(violations(root,[path]))

    def test_unchanged_history_is_not_deployable_input(self):
        self.assertEqual(violations(ROOT,['docs/adr/0010-grafana.md','tools/ci/check_docs.py','tools/ci/tests/test_licences.py']),[])


if __name__=='__main__':unittest.main()
