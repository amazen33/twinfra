"""Portal authorization, read-only data boundaries and Kubernetes regression gates."""
import base64
import copy
import hashlib
import hmac
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import Mock
from unittest.mock import patch
import urllib.error
import urllib.request
import zipfile

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec, rsa

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
builder = load('console_builder', ROOT / 'tools/build_console_image.py')

# Ephemeral keys exist only in this test process, never as committed fixtures.
RSA = rsa.generate_private_key(public_exponent=65537, key_size=2048)
OTHER_RSA = rsa.generate_private_key(public_exponent=65537, key_size=2048)
EC = ec.generate_private_key(ec.SECP256R1())


def jwk(key=RSA, kid='rsa-key', algorithm='RS256'):
    converter = jwt.algorithms.RSAAlgorithm if algorithm == 'RS256' else jwt.algorithms.ECAlgorithm
    result = json.loads(converter.to_jwk(key.public_key()))
    result.update(kid=kid, alg=algorithm, use='sig', key_ops=['verify'])
    return result

def claims(key=RSA, kid='rsa-key', algorithm='RS256', **changes):
    obj = {'sub': 'subject', 'preferred_username': 'operator', 'iss': server.ISSUER,
           'aud': server.CLIENT, 'exp': time.time() + 120,
           'resource_access': {server.CLIENT: {'roles': ['console.viewer']}}}
    obj.update(changes)
    return jwt.encode(obj, key, algorithm=algorithm, headers={'kid': kid})


def public_key_hmac_token():
    # Construct the attack independently: PyJWT itself refuses asymmetric HMAC keys.
    public = RSA.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
    encode = lambda raw: base64.urlsafe_b64encode(raw).rstrip(b'=')
    body = encode(b'{"alg":"HS256","kid":"rsa-key"}') + b'.' + encode(json.dumps({
        'iss':server.ISSUER,'aud':server.CLIENT,'sub':'subject','exp':time.time()+120,
        'resource_access':{server.CLIENT:{'roles':['console.admin']}}}).encode())
    return (body+b'.'+encode(hmac.new(public,body,hashlib.sha256).digest())).decode()


def unauthorized_tokens():
    return {
        'forged signature': claims(key=OTHER_RSA), 'unknown kid': claims(kid='unknown'),
        'expired': claims(exp=time.time()-server.LEEWAY-60),
        'not yet valid': claims(nbf=time.time()+server.LEEWAY+60),
        'wrong issuer': claims(iss='https://attacker.invalid'), 'wrong audience': claims(aud='other'),
        'alg none': claims(key=None, algorithm='none'),
        'HS256 public key': public_key_hmac_token(),
        'malformed header': 'not.a.jwt', 'missing header': None,
    }


class PortalTests(unittest.TestCase):
    def setUp(self):
        self.fetch = Mock(return_value={'keys': [jwk(), jwk(EC, 'ec-key', 'ES256')]})
        self.cache = server.JWKSCache(fetch=self.fetch)
        self.patcher = patch.object(server, 'JWKS', self.cache)
        self.patcher.start(); self.addCleanup(self.patcher.stop)
    def test_sources_and_image_inputs_are_current(self):
        renderer.publish(True); renderer.image()

    def test_identity_is_minimal_and_contains_no_tokens(self):
        result = server.identity(claims(access_token='private', refresh_token='private'))
        self.assertEqual(result['roles'], ['console.viewer'])
        self.assertEqual(set(result), {'username', 'roles', 'issuer', 'client', 'adminUrl'})

    def test_work_order_401_matrix(self):
        for name, token in unauthorized_tokens().items():
            with self.subTest(case=name), self.assertRaises(server.Unauthorized): server.identity(token)

    def test_es256_and_authorized_party_client_are_accepted(self):
        self.assertEqual(server.identity(claims(key=EC, kid='ec-key', algorithm='ES256'))['roles'], ['console.viewer'])
        self.assertEqual(server.identity(claims(aud='account', azp=server.CLIENT))['client'], server.CLIENT)
        self.assertEqual(server.identity(claims(aud=[], azp=server.CLIENT))['client'], server.CLIENT)
        token=jwt.encode({'iss':server.ISSUER,'sub':'subject','azp':server.CLIENT,'exp':time.time()+120,
                          'resource_access':{server.CLIENT:{'roles':['console.viewer']}}},
                         RSA,algorithm='RS256',headers={'kid':'rsa-key'})
        self.assertEqual(server.identity(token)['client'],server.CLIENT)

    def test_time_claims_required_typed_and_bounded_leeway(self):
        for values in ({'exp': None}, {'exp': 'bad'}, {'exp': True}, {'exp': float('inf')},
                       {'nbf': 'bad'}, {'nbf': float('nan')}, {'iss': server.ISSUER+'/'}, {'aud': [42]}, {'azp':'other','aud':'other'}):
            with self.subTest(case=tuple(values)), self.assertRaises(server.Unauthorized): server.identity(claims(**values))
        token = jwt.encode({'iss': server.ISSUER, 'sub':'subject', 'aud':server.CLIENT}, RSA, algorithm='RS256', headers={'kid':'rsa-key'})
        with self.assertRaises(server.Unauthorized): server.identity(token)
        self.assertLessEqual(server.LEEWAY, 60)
        self.assertEqual(server.identity(claims(exp=time.time()-server.LEEWAY+5))['client'],server.CLIENT)
        self.assertEqual(server.identity(claims(nbf=time.time()+server.LEEWAY-5))['client'],server.CLIENT)

    def test_bad_header_algorithms_never_trigger_key_fetch(self):
        cases = [claims(key=None,algorithm='none'), public_key_hmac_token(),
                 claims(key=b'test'*12,algorithm='HS384'), claims(key=b'test'*16,algorithm='HS512'),
                 claims(algorithm='RS512'),
                 jwt.encode({'exp':time.time()+60}, RSA, algorithm='RS256'),
                 claims(headers='unused')+' ', 'x'*32769, 'not.a.jwt']
        for token in cases:
            with self.assertRaises(server.Unauthorized): server.identity(token)
        self.fetch.assert_not_called()

    def test_unknown_kid_rotation_refresh_rate_is_global(self):
        clock = Mock(return_value=0)
        fetch = Mock(side_effect=[{'keys':[jwk()]}, {'keys':[jwk(OTHER_RSA, 'rotated')]}])
        cache = server.JWKSCache(fetch=fetch,clock=clock)
        with patch.object(server,'JWKS',cache):
            server.identity(claims())
            with self.assertRaises(server.Unauthorized): server.identity(claims(key=OTHER_RSA,kid='rotated'))
            self.assertEqual(fetch.call_count,1)
            clock.return_value=60
            self.assertEqual(server.identity(claims(key=OTHER_RSA,kid='rotated'))['client'],server.CLIENT)
            for number in range(10):
                with self.assertRaises(server.Unauthorized): server.identity(claims(kid='unknown-'+str(number)))
            self.assertEqual(fetch.call_count,2)
            with self.assertRaises(server.Unauthorized): server.identity(claims())  # Removed key revoked on refresh.

    def test_expired_cache_and_failed_fetch_are_fail_closed_and_rate_limited(self):
        clock=Mock(return_value=0); fetch=Mock(side_effect=[{'keys':[jwk()]}, OSError('offline')])
        cache=server.JWKSCache(fetch=fetch,clock=clock)
        with patch.object(server,'JWKS',cache):
            server.identity(claims())
            clock.return_value=301
            with self.assertRaises(server.Unauthorized): server.identity(claims())
            clock.return_value=320
            with self.assertRaises(server.Unauthorized): server.identity(claims())
            self.assertEqual(fetch.call_count,2)

    def test_jwks_key_type_curve_usage_and_ambiguity_rejected(self):
        invalid = [[], [jwk(),jwk()], [dict(jwk(),kty='oct')], [dict(jwk(),alg='HS256')],
                   [dict(jwk(),use='enc')], [dict(jwk(),key_ops=['sign'])], [dict(jwk(),d='private')],
                   [dict(jwk(EC,'ec-key','ES256'),crv='P-384')]]
        for keys in invalid:
            with self.subTest(case=len(keys)), patch.object(server,'JWKS',server.JWKSCache(fetch=lambda:{'keys':keys})):
                token=claims(key=EC,kid='ec-key',algorithm='ES256') if keys and keys[0].get('kid')=='ec-key' else claims()
                with self.assertRaises(server.Unauthorized): server.identity(token)

    def test_jwks_uses_fixed_url_private_ca_no_redirect_and_bounded_response(self):
        import ssl
        context=ssl.create_default_context()
        self.assertTrue(context.check_hostname); self.assertEqual(context.verify_mode,ssl.CERT_REQUIRED)
        response=Mock(); response.__enter__=Mock(return_value=response); response.__exit__=Mock(return_value=False)
        response.read.return_value=b'{"keys":[]}'
        opener=Mock(); opener.open.return_value=response
        with patch.object(server.ssl,'create_default_context',return_value=context) as trust, patch.object(server.urllib.request,'build_opener',return_value=opener) as create:
            server.fetch_jwks()
            trust.assert_called_once_with(cafile=str(server.OIDC_CA))
            opener.open.assert_called_once_with(server.JWKS_URL,timeout=4)
            self.assertIsInstance(create.call_args.args[0],server.NoRedirect)
            self.assertIsNone(create.call_args.args[0].redirect_request(None,None,None,None,None,None))
            response.read.assert_called_once_with(65537)
            response.read.return_value=b'x'*65537
            with self.assertRaises(ValueError): server.fetch_jwks()

    def test_jwks_tls_failure_returns_unauthorized(self):
        import ssl
        with patch.object(server,'JWKS',server.JWKSCache(fetch=Mock(side_effect=ssl.SSLError('untrusted')))):
            with self.assertRaises(server.Unauthorized): server.identity(claims())

    def test_concurrent_unknown_kids_do_not_multiply_fetches(self):
        clock=Mock(return_value=0); fetch=Mock(return_value={'keys':[jwk()]})
        cache=server.JWKSCache(fetch=fetch,clock=clock)
        errors=[]
        def attempt(number):
            try: cache.key('unknown-'+str(number),'RS256')
            except ValueError: errors.append(number)
        threads=[threading.Thread(target=attempt,args=(number,)) for number in range(12)]
        for thread in threads:thread.start()
        for thread in threads:thread.join()
        self.assertEqual(len(errors),12); self.assertEqual(fetch.call_count,1)

    def test_dependency_payload_preserves_notices_and_rejects_bad_artifacts(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp); (root/'console').mkdir(); wheels=root/'wheels'; wheels.mkdir()
            path=wheels/'sample-1.0-py3-none-any.whl'
            def fixture(member='sample/__init__.py', altered_hash=False):
                with zipfile.ZipFile(path,'w') as archive:
                    archive.writestr(member,b'# fixture')
                    archive.writestr('sample-1.0.dist-info/licenses/LICENSE',b'fixture licence notice')
                value='0'*64 if altered_hash else hashlib.sha256(path.read_bytes()).hexdigest()
                (root/'console/requirements.txt').write_text('sample==1.0 --hash=sha256:'+value+'\n')
            with patch.object(builder,'ROOT',root):
                fixture()
                self.assertEqual(builder.dependencies(wheels)['app/vendor/sample-1.0.dist-info/licenses/LICENSE'],b'fixture licence notice')
                for member,changed in [('sample/__init__.py',True),('../escape.py',False),('startup.pth',False)]:
                    fixture(member,changed)
                    with self.assertRaises(ValueError): builder.dependencies(wheels)
                path.unlink()
                with self.assertRaises(ValueError): builder.dependencies(wheels)

    def test_roleless_authenticated_user_is_forbidden(self):
        for roles in ([], ['realm-admin'], ['console.admin-other'], None, [{}]):
            with self.assertRaises(server.Forbidden): server.identity(claims(resource_access={server.CLIENT: {'roles': roles}}))

    def test_admin_and_array_audience_are_accepted(self):
        result = server.identity(claims(aud=['other', server.CLIENT], resource_access={server.CLIENT: {'roles': ['console.admin', 'unrelated']}}))
        self.assertEqual(result['roles'], ['console.admin'])

    def test_query_cannot_supply_endpoints_credentials_or_duplicate_backend(self):
        for query in ({'url': ['https://attacker.invalid']}, {'backend': ['other']}, {'backend': ['ministack','other']}, {'bucket': ['../secrets']}, {'table': ['a/b']}):
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
            self.assertIn('Cookie',rewrite['headers']['remove']); self.assertIn('X-ID-Token',rewrite['headers']['remove'])
            self.assertNotIn('X-Access-Token',rewrite['headers']['remove'])
            self.assertTrue(conf['set_access_token_header']); self.assertFalse(conf['set_id_token_header'])
            scrub=next(p['config']['functions'][0] for p in rule['plugins'] if p['name']=='serverless-pre-function')
            self.assertIn("'X-Access-Token'",scrub); self.assertIn("'X-ID-Token'",scrub)
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
        self.assertEqual(role['config']['access.token.claim'],'true')
        audience=next(m for m in c['protocolMappers'] if m['name']=='console-audience')
        self.assertEqual(audience['config']['included.client.audience'],server.CLIENT)
        self.assertEqual(audience['config']['access.token.claim'],'true')

    def test_password_change_provider_registered_and_idempotent_without_user_reset(self):
        actions=[]; calls=[]
        def request(path, **kwargs):
            calls.append((path,kwargs))
            if not kwargs: return copy.deepcopy(actions)
            if kwargs['method']=='POST':
                self.assertEqual(path,'/authentication/register-required-action')
                self.assertEqual(kwargs['value'],{'providerId':'UPDATE_PASSWORD','name':'Update Password'})
                actions.append({'alias':'UPDATE_PASSWORD','providerId':'UPDATE_PASSWORD','enabled':False})
            else:
                self.assertEqual(path,'/authentication/required-actions/UPDATE_PASSWORD')
                self.assertEqual(kwargs['method'],'PUT')
                actions[0]=copy.deepcopy(kwargs['value'])
        provisioning.ensure_password_action(request)
        provisioning.ensure_password_action(request)
        self.assertEqual(sum(bool(kwargs) for _,kwargs in calls),2)
        self.assertTrue(actions[0]['enabled']); self.assertFalse(actions[0]['defaultAction'])
        self.assertTrue(all('/users' not in path for path,_ in calls))

    def test_disabled_password_change_provider_enabled_without_default_action_drift(self):
        actions=[{'alias':'UPDATE_PASSWORD','providerId':'UPDATE_PASSWORD','enabled':False,'defaultAction':False,'priority':31}]
        def request(path, **kwargs):
            if not kwargs: return copy.deepcopy(actions)
            self.assertEqual(path,'/authentication/required-actions/UPDATE_PASSWORD')
            self.assertEqual(kwargs['method'],'PUT')
            actions[0]=copy.deepcopy(kwargs['value'])
        provisioning.ensure_password_action(request)
        self.assertTrue(actions[0]['enabled']); self.assertEqual(actions[0]['priority'],31)
        self.assertFalse(actions[0]['defaultAction'])

    def test_custom_password_action_alias_refused_without_mutation(self):
        def request(path,**kwargs):
            self.assertFalse(kwargs)
            return [{'alias':'UPDATE_PASSWORD','providerId':'unowned-custom','enabled':False}]
        with self.assertRaises(ValueError):provisioning.ensure_password_action(request)

    def test_callback_guard_precedes_oidc_and_never_weakens_token_validation(self):
        for route in renderer.routes():
            plugins=route['spec']['http'][0]['plugins']
            pre=next(p['config'] for p in plugins if p['name']=='serverless-pre-function')
            self.assertEqual(pre['_meta']['priority'],10000)
            self.assertIn('resty.session',pre['functions'][1])
            self.assertIn('/console/callback',pre['functions'][1])
            self.assertNotIn('get_uri_args',pre['functions'][1])
            self.assertNotIn('ngx.redirect',pre['functions'][1])
            oidc=next(p['config'] for p in plugins if p['name']=='openid-connect')
            self.assertTrue(oidc['use_pkce']); self.assertFalse(oidc['accept_none_alg'])
            self.assertEqual(oidc['session']['idling_timeout'],900)
            headers=next(p['config']['headers']['set'] for p in plugins if p['name']=='response-rewrite')
            self.assertEqual(headers['Referrer-Policy'],'no-referrer')

    def test_gateway_ca_volume_contains_only_public_certificate(self):
        import yaml
        dep=next(o for o in application() if o['kind']=='Deployment' and o['metadata']['name']=='apisix')
        trust=next(v for v in dep['spec']['template']['spec']['volumes'] if v['name']=='oidc-trust')
        self.assertEqual(trust['secret']['items'],[{'key':'tls.crt','path':'tls.crt'}])
        config=next(o for o in application() if o['kind']=='ConfigMap' and o['metadata']['name']=='vcloud-apisix')
        value=yaml.safe_load(config['data']['config.yaml'])
        self.assertEqual(value['apisix']['ssl']['ssl_trusted_certificate'],'/oidc-trust/tls.crt')
        self.assertNotIn('$request_uri',value['nginx_config']['http']['access_log_format'])

    def test_backend_has_public_ca_and_only_scoped_keycloak_egress(self):
        pod=renderer.workloads()[0]['spec']['template']['spec']
        trust=next(v for v in pod['volumes'] if v['name']=='oidc-trust')
        self.assertEqual(trust['secret']['items'],[{'key':'tls.crt','path':'tls.crt'}])
        policies={v['metadata']['name']:v['spec'] for v in renderer.bootstrap() if v['kind']=='CiliumNetworkPolicy'}
        outgoing=policies['vcloud-portal']['egress']
        self.assertTrue(any(r.get('toEndpoints',[{}])[0].get('matchLabels',{}).get('k8s:app.kubernetes.io/name')=='keycloak'
                            and r['toPorts'][0]['ports']==[{'port':'8443','protocol':'TCP'}] for r in outgoing))
        self.assertFalse(any('world' in r.get('toEntities',[]) for r in outgoing))
        allowed=policies['vcloud-portal-keycloak']['ingress'][0]['fromEndpoints']
        self.assertEqual({p['matchLabels']['k8s:app.kubernetes.io/name'] for p in allowed},{'apisix','vcloud-console'})

    def test_http_auth_static_traversal_and_readonly_methods(self):
        with tempfile.TemporaryDirectory() as temp:
            static=Path(temp); (static/'index.html').write_text('<title>Twinfra</title>')
            http=server.ThreadingHTTPServer(('127.0.0.1',0),server.Handler)
            thread=threading.Thread(target=http.serve_forever,daemon=True); thread.start()
            origin='http://127.0.0.1:'+str(http.server_port)
            try:
                with patch.object(server,'STATIC',static):
                    for path,headers,expected in [('/console/',{},401),('/console/',{'X-Access-Token':claims()},200),
                        ('/healthz',{},200),('/console/assets/../../server.py',{'X-Access-Token':claims()},404)]:
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

    def test_http_work_order_matrix_json_errors_and_direct_spoof_rejection(self):
        from http.client import HTTPConnection
        http=server.ThreadingHTTPServer(('127.0.0.1',0),server.Handler)
        thread=threading.Thread(target=http.serve_forever,daemon=True); thread.start()
        try:
            tests=[(name, [] if token is None else [('X-Access-Token',token)],401)
                   for name,token in unauthorized_tokens().items()]
            tests += [('old unsigned header',[('X-ID-Token',base64.b64encode(b'{"role":"console.admin"}').decode())],401),
                      ('duplicate header',[('X-Access-Token',claims()),('X-Access-Token',claims())],401),
                      ('roleless',[('X-Access-Token',claims(resource_access={}))],403),
                      ('valid',[('X-Access-Token',claims())],200)]
            for name,headers,expected in tests:
                with self.subTest(case=name):
                    conn=HTTPConnection('127.0.0.1',http.server_port,timeout=2)
                    try:
                        conn.putrequest('GET','/console/api/identity')
                        for header,value in headers:conn.putheader(header,value)
                        conn.endheaders(); response=conn.getresponse(); body=json.loads(response.read())
                        self.assertEqual(response.status,expected)
                        if expected!=200:self.assertEqual(body,{'error':'Console role required' if expected==403 else 'Session required'})
                        self.assertFalse(any(value and value in json.dumps(body) for _,value in headers))
                    finally:conn.close()
        finally:http.shutdown(); http.server_close(); thread.join()


if __name__=='__main__': unittest.main()
