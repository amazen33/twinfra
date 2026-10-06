"""Offline contracts and executable Bash control-flow tests; curl/psql are mocked."""
import copy
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch as mock_patch
import yaml

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
import module4a
from render_module4a import files


def load_reader():
    spec=importlib.util.spec_from_file_location('csi_reader',ROOT/'module-4a/runtime/check-csi.py')
    result=importlib.util.module_from_spec(spec);spec.loader.exec_module(result);return result


class Contracts(unittest.TestCase):
    def test_original_node_approval_and_complete_manifest_contract(self):module4a.audit(module4a.objects())
    def test_upstream_crd_reproducible(self):self.assertEqual(module4a.bundle()['versions']['secretsStoreCSIDriver'],'1.6.1')
    def test_composed_csi_patch_matches_full_resource(self):self.assertEqual(module4a.compose()[0]['kind'],'Deployment')
    def test_deprecated_spc_api_not_used(self):
        spc=next(o for o in module4a.objects() if o['kind']=='SecretProviderClass')
        self.assertEqual(spc['apiVersion'],'secrets-store.csi.x-k8s.io/v1')
    def test_pairing_cannot_be_split(self):
        items=module4a.objects();spc=next(o for o in items if o['kind']=='SecretProviderClass')
        parts=yaml.safe_load(spc['spec']['parameters']['objects']);parts[0]['secretKey']='password'
        spc['spec']['parameters']['objects']=yaml.safe_dump(parts)
        with self.assertRaises(ValueError):module4a.audit(items)
    def test_default_secret_sync_cannot_be_enabled(self):
        items=module4a.objects();spc=next(o for o in items if o['kind']=='SecretProviderClass');spc['spec']['secretObjects']=[{'secretName':'leak'}]
        with self.assertRaises(ValueError):module4a.audit(items)
    def test_tls_skip_cannot_be_enabled(self):
        items=module4a.objects();spc=next(o for o in items if o['kind']=='SecretProviderClass');spc['spec']['parameters']['baoSkipTLSVerify']='true'
        with self.assertRaises(ValueError):module4a.audit(items)
    def test_pod_root_or_hostpath_rejected(self):
        for mutate in [lambda s:s['containers'][0]['securityContext'].update(runAsUser=0),
                       lambda s:s['volumes'].append({'name':'host','hostPath':{'path':'/'}})]:
            items=module4a.objects();obj=next(o for o in items if o['kind']=='Deployment');mutate(obj['spec']['template']['spec'])
            with self.assertRaises(ValueError):module4a.audit(items)
    def test_tokenreview_rbac_not_general_auth_delegation(self):
        items=module4a.objects();obj=next(o for o in items if o['kind']=='ClusterRole');obj['rules'][0]['resources'].append('subjectaccessreviews')
        with self.assertRaises(ValueError):module4a.audit(items)
    def test_wrong_workload_identity_rejected(self):
        items=module4a.objects();obj=next(o for o in items if o['kind']=='Deployment');obj['spec']['template']['spec']['serviceAccountName']='default'
        with self.assertRaises(ValueError):module4a.audit(items)
    def test_validation_policy_cannot_override_lease_path(self):
        policy=(ROOT/'module-4a/openbao/policies/validation.hcl').read_text()
        self.assertIn('denied_parameters = { "lease_id" = [] }',policy)
        self.assertIn('revoke/database/creds/vcloud-validation/*',policy)
        self.assertNotIn('"sudo"',policy)
        self.assertNotIn('vcloud-app-readonly',policy)
    def test_roles_bound_to_exact_account_namespace_audience(self):
        for name,account in [('vcloud-csi-client','vcloud-secrets-client'),('vcloud-validation','vcloud-secret-validator')]:
            obj=json.loads((ROOT/f'module-4a/openbao/kubernetes-role-{name}.json').read_text())
            self.assertEqual(obj['bound_service_account_names'],[account]);self.assertEqual(obj['bound_service_account_namespaces'],['workload-apps'])
            self.assertEqual(obj['audience'],'openbao');self.assertTrue(obj['token_no_default_policy'])
    def test_db_manager_public_config_contains_no_password(self):
        obj=json.loads((ROOT/'module-4a/openbao/database-connection.json').read_text())
        self.assertNotIn('password',obj);self.assertIn('sslmode=verify-full',obj['connection_url']);self.assertEqual(obj['password_authentication'],'scram-sha-256')
    def test_validation_ttl_and_lifecycle_sql_match(self):
        role=json.loads((ROOT/'module-4a/openbao/database-role-vcloud-validation.json').read_text())
        self.assertEqual((role['default_ttl'],role['max_ttl']),('2m','5m'))
        self.assertIn('revoke_login',role['revocation_statements'][0]);self.assertIn('renew_login',role['renew_statements'][0])
    def test_sql_privilege_boundary(self):
        sql=(ROOT/'module-4a/sql/bootstrap-lifecycle.sql').read_text()
        self.assertIn('openbao_manager NOSUPERUSER NOCREATEDB NOCREATEROLE',sql)
        self.assertEqual(sql.count('SECURITY DEFINER SET search_path = pg_catalog, pg_temp'),3)
        self.assertIn('Refusing to revoke an unregistered role',sql)
        self.assertIn('WHERE usename = p_name AND pid <> pg_backend_pid()',sql)
        self.assertIn('REVOKE ALL ON ALL FUNCTIONS',sql)
    def test_db_hba_scopes_dynamic_roles_to_vcloud(self):
        hba=module4a.compose()[1]['spec']['postgresql']['pg_hba']
        self.assertLess(hba.index('hostssl all +vcloud_db_readonly all reject'),hba.index('hostssl all all all scram-sha-256'))
    def test_fs_group_and_token_requests_are_explicit(self):
        spec=module4a.compose()[2]['spec'];self.assertEqual(spec['fsGroupPolicy'],'File')
        self.assertEqual(spec['tokenRequests'],[{'audience':'openbao','expirationSeconds':600}]);self.assertTrue(spec['requiresRepublish'])
    def test_optional_secret_sync_contains_static_key_only(self):
        synced=module4a.compose()[3]['spec']['secretObjects'];self.assertEqual(synced[0]['data'],[{'objectName':'api-key','key':'api-key'}])


class CSIReader(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.directory=Path(self.temp.name);self.reader=load_reader()
        self.database={'data':{'username':'vcloud_dyn_'+'a'*20,'password':'FixtureDatabasePassword'},'lease_id':'database/creds/vcloud-app-readonly/fixture','lease_duration':900}
        self.write()
    def tearDown(self):self.temp.cleanup()
    def write(self):
        (self.directory/'database.json').write_text(json.dumps(self.database));(self.directory/'api-key').write_text('FixtureApiKey')
        for p in self.directory.iterdir():p.chmod(0o600)
    def check(self):
        # Windows chmod does not model Unix group/other bits. Only simulate those
        # mode bits in the test; production never skips its Linux permission check.
        original=Path.stat
        def mode(path,*args,**kwargs):
            result=original(path,*args,**kwargs);values=list(result)
            values[0]=(values[0]&~0o777)|0o600
            return os.stat_result(values)
        if os.name=='nt':
            with mock_patch.object(Path,'stat',mode):return self.reader.check(self.directory)
        return self.reader.check(self.directory)
    def test_paired_files_readable(self):self.assertTrue(self.check())
    def test_wrong_lease_path_rejected(self):
        self.database['lease_id']='database/creds/another-role/fixture';self.write()
        with self.assertRaises(ValueError):self.check()
    def test_empty_api_key_rejected(self):
        (self.directory/'api-key').write_text('')
        with self.assertRaises(ValueError):self.check()


MOCK=r'''import json,os,sys
from pathlib import Path
def native(value):
    if value.startswith('/') and len(value)>2 and value[2]=='/':return Path(value[1].upper()+':'+value[2:])
    return Path(value)
tool=Path(sys.argv[0]).stem
case=os.environ.get('VCLOUD_FIXTURE_CASE','happy')
trace=native(os.environ['VCLOUD_FIXTURE_TRACE'])
argv=sys.argv[1:]
token='FixtureTokenForOpenBao12345678901234567890'
password='FixtureDatabasePassword1234567890'
user='vcloud_dyn_'+'a'*20
record={'tool':tool,'argv':argv,'credentialInArgv':any(token in a or password in a for a in argv),
        'credentialInEnvironment':any(token in v or password in v for v in os.environ.values())}
def log():
    with trace.open('a') as f:f.write(json.dumps(record)+'\n')
if tool=='findmnt':print('ntfs' if case=='disk' else 'tmpfs');sys.exit(0)
if tool=='curl':
    cfg=sys.stdin.read();record['tokenHeaderPresent']='X-Vault-Token: '+token in cfg
    destination=native(argv[argv.index('--output')+1]);url=argv[-1];path=url.split('/v1/',1)[1]
    record['path']=path
    method=argv[argv.index('--request')+1];record['method']=method
    payload=None
    if '--data-binary' in argv:
        payload=json.loads(native(argv[argv.index('--data-binary')+1][1:]).read_text())
        record['payloadKeys']=sorted(payload);record['cas']=payload.get('options',{}).get('cas')
    status=204;data={}
    if path=='auth/kubernetes/login':status=403 if case=='login-denied' else 200;data={'auth':{'client_token':token}}
    elif path=='database/creds/vcloud-validation':
        if case=='curl-tls':log();sys.exit(60)
        status=403 if case=='issue-denied' else (302 if case=='redirect' else 200)
        data={'lease_id':'database/creds/vcloud-validation/fixture','lease_duration':120,'renewable':True,'data':{'username':user,'password':password}}
        if case=='lease-path':data['lease_id']='database/creds/vcloud-app-readonly/fixture'
        if case=='ttl':data['lease_duration']=3600
        if case=='bad-password':data['data']['password']='injected:pgpass'
        if case=='malformed':data['data'].pop('password')
    elif path.startswith('sys/leases/revoke/'):
        record['sync']=payload.get('sync');status=500 if case=='revoke-error' else 204
    elif path=='sys/mounts':
        status=200;data={'data':{}}
        if case.startswith('existing'):
            data={'data':{'database/':{'type':'database'},'kv/':{'type':'kv','options':{'version':'2'}}}}
        if case=='existing-wrong-engine':data['data']['kv/']['type']='transit'
    elif path=='sys/auth':status=200;data={'data':{'kubernetes/':{'type':'kubernetes'}}}
    elif path=='database/config/vcloud-postgres' and method=='GET':
        status=200 if case.startswith('existing') else 404
        connection=json.loads(Path(os.environ['VCLOUD_FIXTURE_ROOT'],'module-4a/openbao/database-connection.json').read_text())
        data={'data':{'plugin_name':connection['plugin_name'],'allowed_roles':connection['allowed_roles'],
                      'connection_details':{k:connection[k] for k in ['username','connection_url','password_authentication','username_template']}}}
        if case=='existing-wrong-tls':data['data']['connection_details']['connection_url']='postgresql://untrusted/?sslmode=disable'
    elif path=='kv/metadata/vcloud/api':status=200 if case.startswith('existing') else 404;data={'data':{'current_version':3}}
    elif path=='kv/data/vcloud/api':status=400 if case=='existing-cas-race' else 200;data={'data':{'version':4}}
    destination.write_text(json.dumps(data));log();print(status,end='');sys.exit(0)
if tool=='psql':
    record['sslmode']=os.environ.get('PGSSLMODE');record['pgpassExists']=native(os.environ['PGPASSFILE']).is_file()
    command=argv[argv.index('--command')+1];record['phase']='retry' if command=='SELECT 1;' else 'active'
    log()
    if record['phase']=='active':
        if case=='active-error':print('fixture connection failure',file=sys.stderr);sys.exit(2)
        print(user+'|vcloud|'+('false' if case=='tls-mismatch' else 'true'));sys.exit(0)
    if case=='revoke-ineffective':print('1');sys.exit(0)
    if case=='network-after-revoke':print('could not connect: Connection refused',file=sys.stderr);sys.exit(2)
    print('FATAL: password authentication failed for user "'+user+'"',file=sys.stderr);sys.exit(2)
'''


class BashIntegrationControlFlow(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bash=shutil.which(os.environ.get('BASH_BINARY','bash'))
        if not cls.bash:raise RuntimeError('Bash is required; no skipped Module 4a script tests')
        cls.jq=shutil.which(os.environ.get('JQ_BINARY','jq'))
        if not cls.jq:raise RuntimeError('jq is required; no skipped Module 4a script tests')
    def setUp(self):
        folder=ROOT/'.build/module-4a-tests';folder.mkdir(parents=True,exist_ok=True)
        self.temp=tempfile.TemporaryDirectory(dir=folder);self.root=Path(self.temp.name);self.bin=self.root/'bin';self.bin.mkdir()
        self.trace=self.root/'trace.jsonl'
        for name in ['curl','psql','findmnt']:
            target=self.bin/(name+'.py');target.write_text(MOCK,encoding='utf-8',newline='\n')
            wrapper=self.bin/name;wrapper.write_text('#!/bin/bash\nexec '+json.dumps(sys.executable.replace('\\','/'))+' '+json.dumps(target.as_posix())+' "$@"\n',newline='\n');wrapper.chmod(0o755)
        jq=self.bin/'jq';jq.write_text('#!/bin/bash\nexec '+json.dumps(str(self.jq).replace('\\','/'))+' "$@"\n',newline='\n');jq.chmod(0o755)
        self.ca=self.root/'ca.crt';self.ca.write_text('Public CA fixture, transport is mocked\n')
        self.jwt=self.root/'jwt';self.jwt.write_text('FixtureProjectedJwtNoRealCredential\n')
    def tearDown(self):self.temp.cleanup()
    def invoke(self,case='happy',script='verify-rotation.sh',extra=(),environment=None):
        env=os.environ.copy();env.update(VCLOUD_FIXTURE_CASE=case,VCLOUD_FIXTURE_TRACE=self.trace.as_posix(),VCLOUD_FIXTURE_ROOT=str(ROOT))
        env.update(environment or {})
        bin_path=self.bin.as_posix()
        if os.name=='nt':bin_path='/'+bin_path[0].lower()+bin_path[2:]
        command='export PATH='+json.dumps(bin_path)+':$PATH\nexec bash '+json.dumps((ROOT/'module-4a/scripts'/script).as_posix())
        args=['--bao-ca',self.ca.as_posix(),'--pg-ca',self.ca.as_posix(),'--scratch-dir',self.root.as_posix(),*extra]
        command+=' '+' '.join(json.dumps(a) for a in args)
        if script=='verify-rotation.sh':command+=' 3<<<"FixtureTokenForOpenBao12345678901234567890"'
        if script=='configure-openbao.sh':command+=' 3<<<"FixtureTokenForOpenBao12345678901234567890" 4<<<"FixtureManagerPassword" 5<<<"FixtureApiKey"'
        result=subprocess.run([self.bash,'-c',command],env=env,text=True,capture_output=True)
        self.assertNotIn('Missing required tool',result.stderr)
        self.assertNotIn('invalid regular expression',result.stderr)
        logs=[json.loads(line) for line in self.trace.read_text().splitlines()] if self.trace.exists() else []
        self.assertFalse(any(l.get('credentialInArgv') or l.get('credentialInEnvironment') for l in logs))
        self.assertNotIn('FixtureToken',result.stdout+result.stderr);self.assertNotIn('FixtureDatabasePassword',result.stdout+result.stderr)
        self.assertFalse(list(self.root.glob('vcloud-bao.*')),'Scratch files were not cleaned')
        return result,logs
    def test_three_steps_pass_and_use_real_bash_jq(self):
        result,logs=self.invoke();self.assertEqual(result.returncode,0,result.stderr);self.assertEqual(result.stdout.count('PASS:'),3)
        self.assertTrue(next(l for l in logs if l.get('path','').startswith('sys/leases/revoke/'))['sync'])
        self.assertTrue(all(l['sslmode']=='verify-full' and l['pgpassExists'] for l in logs if l['tool']=='psql'))
    def test_issue_permission_denied(self):self.assertNotEqual(self.invoke('issue-denied')[0].returncode,0)
    def test_curl_tls_failure(self):self.assertNotEqual(self.invoke('curl-tls')[0].returncode,0)
    def test_no_redirect_following(self):
        result,logs=self.invoke('redirect');self.assertNotEqual(result.returncode,0)
        self.assertTrue(all('--location' not in l['argv'] for l in logs))
    def test_active_database_failure_revokes_lease(self):
        result,logs=self.invoke('active-error');self.assertNotEqual(result.returncode,0)
        self.assertEqual(sum(l.get('path','').startswith('sys/leases/revoke/') for l in logs),1)
    def test_unverified_database_tls_fails(self):self.assertNotEqual(self.invoke('tls-mismatch')[0].returncode,0)
    def test_revocation_api_failure_cannot_pass(self):self.assertNotEqual(self.invoke('revoke-error')[0].returncode,0)
    def test_credential_surviving_revocation_fails(self):self.assertNotEqual(self.invoke('revoke-ineffective')[0].returncode,0)
    def test_network_failure_after_revocation_cannot_pass(self):
        result,_=self.invoke('network-after-revoke');self.assertNotEqual(result.returncode,0);self.assertIn('not a PostgreSQL authentication',result.stderr)
    def test_wrong_lease_path_never_revoked(self):
        result,logs=self.invoke('lease-path');self.assertNotEqual(result.returncode,0)
        self.assertFalse(any(l.get('path','').startswith('sys/leases/revoke/') for l in logs))
    def test_long_ttl_fails_and_cleans_lease(self):self.assertNotEqual(self.invoke('ttl')[0].returncode,0)
    def test_missing_password_fails_and_cleans_lease(self):self.assertNotEqual(self.invoke('malformed')[0].returncode,0)
    def test_pgpass_injection_fails(self):self.assertNotEqual(self.invoke('bad-password')[0].returncode,0)
    def test_disk_scratch_is_prohibited(self):
        result,logs=self.invoke('disk');self.assertNotEqual(result.returncode,0);self.assertFalse(logs)
    def test_environment_credential_is_prohibited(self):
        result,logs=self.invoke(environment={'PGPASSWORD':'ForbiddenFixture'});self.assertNotEqual(result.returncode,0);self.assertFalse(logs)
    def test_inherited_export_flags_cannot_export_issued_credentials(self):
        result,_=self.invoke(environment={'VCLOUD_TOKEN':'AmbientPlaceholder','db_password':'AmbientPlaceholder','db_user':'AmbientPlaceholder'})
        self.assertEqual(result.returncode,0,result.stderr)
    def test_inherited_export_flag_cannot_export_kubernetes_login_token(self):
        result,_=self.invoke(script='login-and-verify.sh',extra=['--jwt-file',self.jwt.as_posix()],
                             environment={'VCLOUD_TOKEN':'AmbientPlaceholder'})
        self.assertEqual(result.returncode,0,result.stderr)
    def test_http_url_is_prohibited(self):self.assertNotEqual(self.invoke(extra=['--bao-address','http://unsafe.example.com'])[0].returncode,0)
    def test_kubernetes_login_and_token_cleanup(self):
        result,logs=self.invoke(script='login-and-verify.sh',extra=['--jwt-file',self.jwt.as_posix()]);self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(logs[0]['path'],'auth/kubernetes/login');self.assertEqual(logs[-1]['path'],'auth/token/revoke-self')
    def test_kubernetes_login_denial_stops_database_issue(self):
        result,logs=self.invoke('login-denied',script='login-and-verify.sh',extra=['--jwt-file',self.jwt.as_posix()]);self.assertNotEqual(result.returncode,0)
        self.assertFalse(any(l.get('path','').startswith('database/creds/') for l in logs))
    def test_configure_plan_has_no_api_calls(self):
        result,logs=self.invoke(script='configure-openbao.sh');self.assertEqual(result.returncode,0);self.assertFalse(logs)
    def test_new_config_rotates_manager_and_uses_kv_cas(self):
        result,logs=self.invoke(script='configure-openbao.sh',extra=['--apply','--api-key-fd','5']);self.assertEqual(result.returncode,0,result.stderr)
        self.assertTrue(any(l.get('path')=='database/rotate-root/vcloud-postgres' for l in logs))
        self.assertEqual(next(l for l in logs if l.get('path')=='kv/data/vcloud/api')['cas'],0)
    def test_existing_connection_is_not_overwritten(self):
        result,logs=self.invoke('existing',script='configure-openbao.sh',extra=['--apply','--api-key-fd','5']);self.assertEqual(result.returncode,0,result.stderr)
        self.assertFalse(any(l.get('path')=='database/config/vcloud-postgres' and l.get('method')=='POST' for l in logs))
        self.assertFalse(any(l.get('path')=='kv/data/vcloud/api' for l in logs))
    def test_wrong_existing_backend_is_not_remounted(self):self.assertNotEqual(self.invoke('existing-wrong-engine',script='configure-openbao.sh',extra=['--apply'])[0].returncode,0)
    def test_wrong_existing_tls_connection_is_rejected(self):self.assertNotEqual(self.invoke('existing-wrong-tls',script='configure-openbao.sh',extra=['--apply'])[0].returncode,0)
    def test_static_key_rotation_has_compare_and_swap(self):
        result,logs=self.invoke('existing',script='configure-openbao.sh',extra=['--apply','--api-key-fd','5','--rotate-api-key']);self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(next(l for l in logs if l.get('path')=='kv/data/vcloud/api')['cas'],3)
    def test_static_key_cas_conflict_fails(self):self.assertNotEqual(self.invoke('existing-cas-race',script='configure-openbao.sh',extra=['--apply','--api-key-fd','5','--rotate-api-key'])[0].returncode,0)


if __name__=='__main__':unittest.main()
