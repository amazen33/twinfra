"""Portal authorization, read-only data boundaries and Kubernetes regression gates."""
import base64
import copy
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import vcloud_console as renderer
import configure_console_identity as provisioning
from wsl_endpoints import check, application

def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec); spec.loader.exec_module(value)
    return value
aws = load('aws_views', ROOT / 'lab/wsl/console/ui.py')
sys.modules['aws_views'] = aws
server = load('portal_server', ROOT / 'console/server.py')

def claims(**changes):
    obj = {'sub': 'subject', 'preferred_username': 'operator', 'iss': server.ISSUER,
           'aud': server.CLIENT, 'exp': time.time() + 120,
           'resource_access': {server.CLIENT: {'roles': ['console.viewer']}}}
    obj.update(changes)
    return base64.b64encode(json.dumps(obj).encode()).decode()


class PortalTests(unittest.TestCase):
    def test_sources_and_image_inputs_are_current(self):
        renderer.publish(True); renderer.image()

    def test_identity_is_minimal_and_contains_no_tokens(self):
        result = server.identity(claims(access_token='private', refresh_token='private'))
        self.assertEqual(result['roles'], ['console.viewer'])
        self.assertEqual(set(result), {'username', 'roles', 'issuer', 'client', 'adminUrl'})

    def test_missing_malformed_expired_wrong_issuer_or_audience_rejected(self):
        for value in (None, 'bad-base64', 'e30=', claims(exp=time.time()-1), claims(iss='https://attacker.invalid'), claims(aud='other'), claims(exp='bad')):
            with self.subTest(value=bool(value)), self.assertRaises(server.Unauthorized): server.identity(value)

    def test_roleless_authenticated_user_is_forbidden(self):
        for roles in ([], ['realm-admin'], ['console.admin-other'], None):
            with self.assertRaises(server.Forbidden): server.identity(claims(resource_access={server.CLIENT: {'roles': roles}}))

    def test_admin_and_array_audience_are_accepted(self):
        result = server.identity(claims(aud=['other', server.CLIENT], resource_access={server.CLIENT: {'roles': ['console.admin', 'unrelated']}}))
        self.assertEqual(result['roles'], ['console.admin'])

    def test_query_cannot_supply_endpoints_credentials_or_duplicate_backend(self):
        for query in ({'url': ['https://attacker.invalid']}, {'backend': ['other']}, {'backend': ['ministack','localstack']}, {'bucket': ['../secrets']}, {'table': ['a/b']}):
            with self.assertRaises(ValueError): server.valid_query(query)

    def test_storage_reads_only_bucket_names_and_bounded_object_keys(self):
        with patch.object(server, 'read', return_value=b'<Result><Name>bucket</Name></Result>'):
            self.assertEqual(server.api_response('storage', {}, {})['buckets'], ['bucket'])
        with patch.object(server, 'signed_request', wraps=aws.signed_request) as signer, patch.object(server, 'read', return_value=b'<Result><Key>object</Key></Result>'):
            value = server.api_response('storage', {'bucket':['bucket']}, {})
            self.assertEqual(value['objects'], ['object'])
            self.assertEqual(signer.call_args.kwargs['query']['max-keys'], '100')
            self.assertNotIn('contents', value)

    def test_dynamodb_metadata_has_no_scan_or_write(self):
        with patch.object(server, 'signed_request', wraps=aws.signed_request) as signer, patch.object(server, 'read', return_value=b'{"Table":{"TableName":"users"}}'):
            result = server.api_response('dynamodb', {'table':['users']}, {})
            self.assertEqual(signer.call_args.kwargs['target'], 'DynamoDB_20120810.DescribeTable')
            self.assertEqual(result['metadata'], {'TableName':'users'})

    def test_cloud_reads_ec2_state_and_never_launches_instances(self):
        raw = b'<Result><instancesSet><item><instanceId>i-local</instanceId><instanceType>test</instanceType><instanceState><name>running</name></instanceState></item></instancesSet></Result>'
        with patch.object(server, 'read', side_effect=[b'{"services":{"ec2":"running"}}', raw]), patch.object(server, 'signed_request', wraps=aws.signed_request) as signer:
            value = server.api_response('cloud', {}, {})
            self.assertEqual(value['instances'][0]['id'], 'i-local')
            self.assertIn(b'Action=DescribeInstances', signer.call_args.kwargs['payload'])
            self.assertTrue(value['ephemeral'])

    def test_kubernetes_data_is_reduced_to_status_not_pod_specs(self):
        data = [{'items':[{'status':{'phase':'Running','conditions':[{'type':'Ready','status':'True'}]},'spec':{'private':'hidden'}}, {'status':{'phase':'Succeeded'}}]},
                {'items':[{'spec':{'replicas':1},'status':{'availableReplicas':1}}]}]
        with patch.object(server, 'kube', side_effect=data) as kube:
            result = server.api_response('overview', {}, {})
            self.assertEqual(result['pods'],1); self.assertEqual(result['ready'],1)
            self.assertNotIn('hidden',json.dumps(result))
            self.assertTrue(all('platform-services' in c.args[0] for c in kube.call_args_list))

    def test_reader_has_no_secret_exec_write_or_cluster_authority(self):
        role = next(o for o in renderer.bootstrap() if o['kind']=='Role')
        self.assertEqual({r for rule in role['rules'] for r in rule['resources']}, {'pods','deployments','applications'})
        self.assertTrue(all(rule['verbs']==['get','list'] for rule in role['rules']))
        self.assertFalse(any(o['kind'].startswith('ClusterRole') for o in renderer.bootstrap()))
        pod = renderer.workloads()[0]['spec']['template']['spec']
        self.assertFalse(pod['automountServiceAccountToken'])
        self.assertEqual(pod['serviceAccountName'], 'vcloud-console')
        self.assertEqual(pod['volumes'][0]['projected']['sources'][0]['serviceAccountToken']['expirationSeconds'],3600)

    def test_pss_mutation_is_rejected(self):
        obj = renderer.workloads()[0]
        obj['spec']['template']['spec']['containers'][0]['securityContext']['allowPrivilegeEscalation']=True
        with self.assertRaises(ValueError): check([obj])

    def test_gateway_uses_private_session_exact_origin_tls_and_role_schema(self):
        for obj in renderer.routes():
            rule = obj['spec']['http'][0]
            oidc = next(p for p in rule['plugins'] if p['name']=='openid-connect')
            self.assertEqual(oidc['secretRef'], 'vcloud-console-oidc')
            conf = oidc['config']; self.assertTrue(conf['ssl_verify']); self.assertTrue(conf['use_pkce'])
            self.assertEqual(conf['redirect_uri'], 'http://localhost:18080/console/callback')
            self.assertTrue(conf['session']['cookie_http_only'])
            self.assertEqual(conf['session']['cookie_path'],'/console')
            self.assertIn('resource_access',json.dumps(conf['claim_schema']))
            self.assertNotIn('client_secret',conf)
            rewrite=next(p['config'] for p in rule['plugins'] if p['name']=='proxy-rewrite')
            self.assertIn('Cookie',rewrite['headers']['remove']); self.assertNotIn('X-ID-Token',rewrite['headers']['remove'])
            self.assertFalse(any(p['name']=='cors' for p in rule['plugins']))

    def test_route_priority_and_prefix_boundaries(self):
        import re
        api = next(o for o in renderer.routes() if o['metadata']['name']=='vcloud-portal-api')['spec']['http'][0]
        self.assertEqual(api['plugins'][1]['config']['unauth_action'],'deny')
        for o in renderer.routes():
            rewrite=next(p['config'] for p in o['spec']['http'][0]['plugins'] if p['name']=='proxy-rewrite')
            if 'regex_uri' in rewrite:
                regex = rewrite['regex_uri'][0]
                name=o['spec']['http'][0]['name'].removesuffix('-view')
                self.assertIsNotNone(re.fullmatch(regex,'/console/proxy/'+name+'/path'))
                self.assertIsNone(re.fullmatch(regex,'/console/proxy/'+name+'-other/path'))

    def test_keycloak_client_isolated_and_no_password_or_service_account_grants(self):
        c=provisioning.client_spec()
        self.assertFalse(c['directAccessGrantsEnabled']); self.assertFalse(c['serviceAccountsEnabled']); self.assertFalse(c['fullScopeAllowed'])
        self.assertEqual(c['redirectUris'],['http://localhost:18080/console/callback'])
        self.assertNotIn('secret',c)
        role=next(m for m in c['protocolMappers'] if m['name']=='console-roles')
        self.assertEqual(role['config']['claim.name'],'resource_access.vcloud-console.roles')

    def test_gateway_ca_volume_contains_only_public_certificate(self):
        import yaml
        dep=next(o for o in application() if o['kind']=='Deployment' and o['metadata']['name']=='apisix')
        trust=next(v for v in dep['spec']['template']['spec']['volumes'] if v['name']=='oidc-trust')
        self.assertEqual(trust['secret']['items'],[{'key':'tls.crt','path':'tls.crt'}])
        config=next(o for o in application() if o['kind']=='ConfigMap' and o['metadata']['name']=='vcloud-apisix')
        value=yaml.safe_load(config['data']['config.yaml'])
        self.assertEqual(value['apisix']['ssl']['ssl_trusted_certificate'],'/oidc-trust/tls.crt')
        self.assertNotIn('$request_uri',value['nginx_config']['http']['access_log_format'])

    def test_http_auth_static_traversal_and_readonly_methods(self):
        with tempfile.TemporaryDirectory() as temp:
            static=Path(temp); (static/'index.html').write_text('<title>vCloud</title>')
            http=server.ThreadingHTTPServer(('127.0.0.1',0),server.Handler)
            thread=threading.Thread(target=http.serve_forever,daemon=True); thread.start()
            origin='http://127.0.0.1:'+str(http.server_port)
            try:
                with patch.object(server,'STATIC',static):
                    for path,headers,expected in [('/console/',{},401),('/console/',{'X-ID-Token':claims()},200),
                        ('/healthz',{},200),('/console/assets/../../server.py',{'X-ID-Token':claims()},404)]:
                        req=urllib.request.Request(origin+path,headers=headers)
                        try: response=urllib.request.urlopen(req,timeout=2)
                        except urllib.error.HTTPError as e: response=e
                        self.assertEqual(response.status,expected)
                        self.assertIn("frame-ancestors 'self'",response.headers['Content-Security-Policy'])
                        response.close()
                    with self.assertRaises(urllib.error.HTTPError) as error:
                        urllib.request.urlopen(urllib.request.Request(origin+'/console/api/cloud',data=b'{}'),timeout=2)
                    self.assertEqual(error.exception.code,405)
                    self.assertEqual(error.exception.headers['Connection'],'close')
                    error.exception.close()
            finally: http.shutdown(); http.server_close(); thread.join()


if __name__=='__main__': unittest.main()
