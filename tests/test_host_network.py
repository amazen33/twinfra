"""WO-36 offline failure/rollback fixtures. Never connects or runs netplan."""
import copy
from contextlib import nullcontext
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import yaml

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'tools'),str(ROOT/'tools/ci')]
import platform_dev as dev
import platform_host as host
import check_staging as staging

spec=importlib.util.spec_from_file_location('network_agent',ROOT/'deploy/common/host-network.py')
net=importlib.util.module_from_spec(spec);spec.loader.exec_module(net)
spec=importlib.util.spec_from_file_location('host_agent_wo36',ROOT/'deploy/common/host-admin.py')
agent=importlib.util.module_from_spec(spec);spec.loader.exec_module(agent)

DATA=host.expected()|{'mac':'64:00:6a:86:5c:4f','gateway':'192.168.1.1','dns':['192.168.1.1','1.1.1.1'],'mode':'apply','config':'network: {version: 2}\n'}
INFO={'address':'192.168.1.3','present':True,'static':True,'prefixLength':24,'mac':DATA['mac'],
      'gateways':['192.168.1.1'],'dns':DATA['dns'],'nodeInternalIP':['192.168.1.3']}
UNIT='twinfra-network-'+'a'*32


class Files(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.addCleanup(patch.stopall)
        patch.object(net,'ROOT',self.root).start()
        # Windows has no POSIX ownership/mode bits; production security checks
        # have separate malicious-path fixtures below.
        patch.object(net,'secure',lambda p:None).start()
        patch.object(net,'lock',lambda **_:nullcontext()).start()
        patch.object(net,'effective',lambda _:copy.deepcopy(INFO)).start()
        self.calls=[]
        patch.object(net,'run',lambda args:self.calls.append(args) or ('inactive\n' if args[0]=='systemctl' else '')).start()
        self.put(net.DHCP,b'network:\n  version: 2\n  ethernets:\n    eno1: {dhcp4: true}\n')
    def put(self,name,raw):
        p=net.path(name);p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(raw)
    def begin(self,mode='apply'):
        return net.start(DATA|{'mode':mode},(ROOT/'deploy/common/host-network.py').read_text(encoding='utf-8'))

    def test_check_is_readonly_and_refuses_unowned_static_files(self):
        before=list(self.root.rglob('*'));self.assertEqual(net.check(DATA)['status'],'failed')
        self.assertEqual(list(self.root.rglob('*')),before);self.assertEqual(self.calls,[])
        self.put(net.STATIC,b'unowned');self.assertEqual(net.integrity()['status'],'BLOCK')
        with self.assertRaisesRegex(ValueError,'Unowned'):self.begin()

    def test_start_saves_exact_dhcp_and_uses_detached_unit_without_netplan_over_ssh(self):
        before=net.path(net.DHCP).read_bytes();report=self.begin()
        self.assertEqual(report['status'],'running');self.assertEqual(net.path(net.STATE_DIR+'/50-cloud-init.yaml').read_bytes(),before)
        self.assertEqual(net.path(net.DHCP).read_bytes(),before)
        args=self.calls[-1];self.assertEqual(args[0],'systemd-run');self.assertIn('--no-block',args)
        self.assertIn('--property=TimeoutStartSec=infinity',args);self.assertNotIn('netplan',args)
        self.assertNotIn('before',report);self.assertNotIn('data',report)

    def test_concurrent_and_external_netplan_refused(self):
        self.begin()
        with self.assertRaisesRegex(ValueError,'active or incomplete'):self.begin()
        self.put('/run/netplan/netplan-try.ready',b'')
        with self.assertRaisesRegex(ValueError,'Another'):self.begin()

    def test_passed_report_requires_systemd_exit_zero_and_failed_start_changes_no_network_files(self):
        report=self.begin();full=net.load(net.STATE_DIR+'/transaction.json');full['status']='passed'
        net.save(net.STATE_DIR+'/transaction.json',full)
        with patch.object(net,'unit_active',return_value=False),patch.object(net,'run',return_value='1'):
            self.assertEqual(net.poll(DATA|{'unit':report['unit']})['status'],'failed')
        with patch.object(net,'unit_active',return_value=False),patch.object(net,'run',return_value='0'):
            self.assertEqual(net.poll(DATA|{'unit':report['unit']})['status'],'passed')
        before=net.snapshot()
        def fail(args):
            if args[0]=='systemd-run':raise ValueError('start failed')
            return 'inactive'
        with patch.object(net,'run',side_effect=fail):
            with self.assertRaisesRegex(ValueError,'start failed'):self.begin()
        self.assertEqual(net.snapshot(),before)

    def test_foreign_unit_and_missing_dhcp_refused(self):
        with self.assertRaisesRegex(ValueError,'Foreign'):net.state({'unit':'ssh.service'})
        net.path(net.DHCP).unlink()
        with self.assertRaisesRegex(ValueError,'Missing'):self.begin()

    def test_rollback_without_owned_backup_and_changed_mac_refused(self):
        with self.assertRaisesRegex(ValueError,'No saved'):self.begin('rollback')
        with patch.object(net,'effective',return_value=INFO|{'mac':'00:00:00:00:00:00'}):
            with self.assertRaisesRegex(ValueError,'identity'):self.begin()

    def awaiting(self):
        report=self.begin();full=net.load(net.STATE_DIR+'/transaction.json')
        full.update(status='awaiting-confirmation',readyAt=10)
        net.save(net.STATE_DIR+'/transaction.json',full)
        return report,full

    def test_confirm_requires_live_window_and_exact_network_and_verified_https(self):
        report,_=self.awaiting()
        data=DATA|{'unit':report['unit']}
        with patch.object(net,'unit_active',return_value=True),patch.object(net.time,'monotonic',return_value=20):
            with patch.object(net,'effective',return_value=INFO|{'static':False}):
                with self.assertRaisesRegex(ValueError,'verification failed'):net.confirm(data)
            with patch.object(net,'run',return_value='no'):
                with self.assertRaisesRegex(ValueError,'readiness'):net.confirm(data)
            self.assertFalse(net.path(net.STATE_DIR+'/confirm.json').exists())
            with patch.object(net,'run',return_value='ok') as run:
                self.assertEqual(net.confirm(data)['status'],'running')
                args=run.call_args.args[0];self.assertIn('--server=https://192.168.1.3:6443',args)
                self.assertIn('--insecure-skip-tls-verify=false',args)
                self.assertNotIn('--insecure-skip-tls-verify=true',args)
            self.assertEqual(net.load(net.STATE_DIR+'/confirm.json'),{'unit':report['unit']})
        with patch.object(net.time,'monotonic',return_value=111):
            with self.assertRaisesRegex(ValueError,'window closed'):net.confirm(data)

    def worker_case(self,accept=False,fail_spawn=False,mode='apply'):
        report=self.begin(mode);unit=report['unit'];before=net.snapshot();self.tick=0
        owner=self
        class Child:
            returncode=None
            def __init__(self,*args,**kwargs):
                if fail_spawn:raise OSError('fixture spawn failure')
                owner.assertEqual(args[0],['netplan','try','--timeout','120'])
                owner.assertEqual(kwargs['stdin'],subprocess.PIPE)
                self.output=kwargs['stdout'];self.stdin=self;self.count=0
                net.path('/run/netplan').mkdir(parents=True,exist_ok=True)
                owner.put('/run/netplan/netplan-try.ready',b'')
            def poll(self):
                self.count+=1
                if self.count>2:
                    if self.returncode is None:self.output.write('Reverting.\n');self.output.flush();self.returncode=0
                return self.returncode
            def write(self,raw):
                owner.assertEqual(raw,'\n');self.returncode=0;self.output.write('Configuration accepted.\n');self.output.flush()
            def flush(self):pass
            def wait(self,timeout):
                ready=net.path('/run/netplan/netplan-try.ready')
                if ready.exists():ready.unlink()
                return self.returncode
        def pause(_):
            if accept:net.save(net.STATE_DIR+'/confirm.json',{'unit':unit})
        with patch.object(net.subprocess,'Popen',Child),patch.object(net.time,'sleep',pause),patch.object(net.time,'monotonic',return_value=10):
            code=net.worker(unit)
        return code,before,net.load(net.STATE_DIR+'/transaction.json')

    def test_worker_timeout_zero_exit_restores_disk_and_does_not_commit(self):
        code,before,report=self.worker_case()
        self.assertEqual(code,1);self.assertEqual(report['status'],'failed');self.assertEqual(net.snapshot(),before)
        self.assertFalse(net.path(net.STATE_DIR+'/committed.json').exists())

    def test_worker_spawn_failure_restores_disk(self):
        code,before,_=self.worker_case(fail_spawn=True);self.assertEqual(code,1);self.assertEqual(net.snapshot(),before)

    def test_confirmed_apply_owns_both_files_and_idempotently_checks(self):
        code,_,report=self.worker_case(accept=True)
        self.assertEqual(code,0);self.assertEqual(report['status'],'passed')
        self.assertFalse(net.path(net.DHCP).exists());self.assertTrue(net.path(net.CLOUD).exists())
        self.assertEqual(net.check(DATA)['status'],'passed')
        self.calls=[];self.assertEqual(self.begin()['status'],'passed');self.assertTrue(all(c[0]=='systemctl' for c in self.calls))
        self.put(net.CLOUD,b'tampered');self.assertEqual(net.integrity()['status'],'BLOCK')

    def test_successful_rollback_restores_saved_config_and_has_same_confirmation_gate(self):
        self.worker_case(accept=True);saved=net.path(net.STATE_DIR+'/50-cloud-init.yaml').read_bytes()
        net.path('/run/netplan/netplan-try.ready').unlink(missing_ok=True)
        code,_,report=self.worker_case(accept=True,mode='rollback')
        self.assertEqual(code,0);self.assertEqual(report['mode'],'rollback')
        self.assertEqual(net.path(net.DHCP).read_bytes(),saved);self.assertFalse(net.path(net.STATIC).exists())
        self.assertFalse(net.path(net.CLOUD).exists());self.assertEqual(net.integrity()['status'],'PASS')

    def test_failed_rollback_restores_static_files_and_ownership(self):
        self.worker_case(accept=True);before=net.snapshot();net.path('/run/netplan/netplan-try.ready').unlink(missing_ok=True)
        code,_,_=self.worker_case(mode='rollback')
        self.assertEqual(code,1);self.assertEqual(net.snapshot(),before);self.assertEqual(net.integrity()['status'],'PASS')

    def test_backup_and_worker_tampering_refused(self):
        self.worker_case(accept=True);net.path('/run/netplan/netplan-try.ready').unlink(missing_ok=True)
        self.put(net.STATE_DIR+'/50-cloud-init.yaml',b'tamper')
        with self.assertRaisesRegex(ValueError,'DHCP copy differs'):self.begin('rollback')


class Controller(unittest.TestCase):
    def test_rendered_netplan_matches_the_ssot_and_retains_address_without_carrier(self):
        captured=[]
        with patch.object(host,'request',side_effect=lambda ssh,action,**data:captured.append(data) or {'status':'passed'}):
            host.network(None,'apply')
        config=yaml.safe_load(captured[0]['config'])
        self.assertEqual(config,{'network':{'version':2,'renderer':'networkd','ethernets':{'eno1':{
            'dhcp4':False,'dhcp6':False,'ignore-carrier':True,'addresses':['192.168.1.3/24'],
            'routes':[{'to':'default','via':'192.168.1.1'}],'nameservers':{'addresses':['192.168.1.1','1.1.1.1']}}}}})

    def test_effective_lookup_rejects_dynamic_wrong_routes_dns_internal_ip(self):
        for mutation in ({'static':False},{'dns':['1.1.1.1','192.168.1.1']},{'gateways':['192.168.1.2']},
                         {'nodeInternalIP':['192.168.1.4']},{'prefixLength':16}):
            self.assertFalse(net.matches(INFO|mutation,DATA))

    def test_symlink_and_unowned_paths_are_rejected(self):
        with patch.object(Path,'is_symlink',return_value=True):
            with self.assertRaisesRegex(ValueError,'Linked'):net.secure(Path('/tmp/fixture'))
        with patch.object(Path,'is_symlink',return_value=False),patch.object(Path,'exists',return_value=True),patch.object(Path,'stat',return_value=type('Stat',(),{'st_uid':1001,'st_mode':0o600})()):
            with self.assertRaisesRegex(ValueError,'Unowned'):net.secure(Path('/tmp/fixture'))

    def test_fresh_connection_precedes_confirm_and_failure_never_confirms(self):
        calls=[];states=iter(['awaiting-confirmation','running','passed'])
        def request(ssh,action,**data):
            calls.append(action)
            if action=='network-start':return {'status':'running','unit':UNIT,'message':'fixture'}
            if action=='network-status':return {'status':next(states),'unit':UNIT}
            return {'status':'running'}
        class SSH:
            def run(self,args):calls.append('fresh-login')
        with patch.object(host,'request',request):self.assertEqual(host.network(SSH(),'apply',lambda _:None)['status'],'passed')
        self.assertEqual(calls[calls.index('network-confirm')-1],'fresh-login')
        class FailedSSH:
            def run(self,args):raise ValueError('fresh login failed')
        calls=[];states=iter(['awaiting-confirmation'])
        with patch.object(host,'request',request):
            with self.assertRaisesRegex(ValueError,'fresh login'):host.network(FailedSSH(),'apply',lambda _:None)
        self.assertNotIn('network-confirm',calls)

    def test_missing_or_conflicting_modes_refused_without_ssh(self):
        for flags in ({},{'check':True,'apply':True}):
            with self.assertRaisesRegex(ValueError,'exactly one'):host.execute('host-network',None,**flags)

    def test_existing_identity_checks_guard_network_mutations(self):
        from test_bare_metal import fixture
        agent.NETWORK_SOURCE=(ROOT/'deploy/common/host-network.py').read_text(encoding='utf-8')
        for state in (fixture(),fixture(True)|{'addresses':['192.168.1.4']}):
            with patch.object(agent,'inventory',return_value=state):
                with self.assertRaisesRegex(ValueError,'identity-verified'):agent.dispatch(DATA|{'action':'network-start'})

    def test_since_boot_network_and_restart_warnings_never_block(self):
        entries=[{'MESSAGE':'eno1: Lost carrier'},{'MESSAGE':'eno1: DHCP lease lost'}]
        containers=[{'metadata':{'name':'etcd','attempt':2},'labels':{'io.kubernetes.pod.namespace':'kube-system','io.kubernetes.pod.name':'etcd-twinfra-dev-cairo-1'},'createdAt':110*10**9},
                    {'metadata':{'name':'kube-apiserver','attempt':3},'labels':{'io.kubernetes.pod.namespace':'kube-system','io.kubernetes.pod.name':'kube-apiserver-twinfra-dev-cairo-1'},'createdAt':90*10**9}]
        with patch.object(agent,'command',return_value=type('Result',(),{'stdout':'\n'.join(json.dumps(e) for e in entries)})()),patch.object(agent,'read',return_value='btime 100\n'),patch.object(agent,'run',return_value=json.dumps({'containers':containers})):
            warnings=agent.network_warnings()
        self.assertEqual([w['status'] for w in warnings],['WARN']*3)
        self.assertEqual(warnings[-1]['detail']['retainedAttempts']['etcd'],1)
        self.assertEqual(warnings[-1]['detail']['retainedAttempts']['kube-apiserver'],0)
        from test_bare_metal import fixture
        state=fixture(True)|{'networkIntegrity':{'status':'PASS','detail':'owned'},'networkWarnings':warnings}
        self.assertEqual(agent.evaluate(state,host.expected())['status'],'passed')
        state['networkIntegrity']['status']='BLOCK';self.assertEqual(agent.evaluate(state,host.expected())['status'],'failed')

    def test_unavailable_warning_sources_do_not_fail_host_check(self):
        with patch.object(agent,'command',side_effect=ValueError('unavailable')),patch.object(agent,'read',return_value=''),patch.object(agent,'run',side_effect=ValueError('unavailable')):
            self.assertTrue(all(c['status']=='WARN' for c in agent.network_warnings()))


class Staging(unittest.TestCase):
    def test_locks_and_rendered_images_require_exact_attestation(self):
        self.assertTrue(staging.required({'deploy/common/images.lock.json':['{}','{}']}))
        for field in ('image','imageName','imageTag'):
            self.assertTrue(staging.required({'deploy/environments/dev/cairo-1/services/workloads.yaml':[field+': old',field+': new']}))
        self.assertTrue(staging.required({'deploy/environments/dev/cairo-1/x.yaml':['env: [{name: OPERATOR_IMAGE_NAME, value: old}]','env: [{name: OPERATOR_IMAGE_NAME, value: new}]']}))
        self.assertTrue(staging.required({'deploy/environments/dev/cairo-2/seed/user-data':['write_files: [{content: "image: old\n"}]','write_files: [{content: "image: new\n"}]']}))
        for body in ('', 'Staging: PASS (stage-images --check, <UTC date>)','Staging: PASS (stage-images --check, 2026-02-30)','prefix Staging: PASS (stage-images --check, 2026-10-15)'):
            self.assertFalse(staging.attest(body))
        self.assertTrue(staging.attest('text\nStaging: PASS (stage-images --check, 2026-10-15)\ntext'))

    def test_unrelated_and_strategy_only_changes_need_no_attestation(self):
        self.assertEqual(staging.required({'docs/runbook.md':['old','new']}),[])
        self.assertEqual(staging.required({'deploy/environments/dev/cairo-1/workloads.yaml':['image: same\nstrategy: Recreate','image: same\nstrategy: RollingUpdate']}),[])

    def test_gate_reads_pr_body_as_data_not_shell_and_validates_refs(self):
        event={'pull_request':{'base':{'sha':'a'*40},'head':{'sha':'b'*40},'body':'$(bad)'}}
        with patch.object(staging,'git',return_value=b'deploy/common/images.lock.json\0'),patch.object(staging.subprocess,'run',return_value=type('Result',(),{'returncode':1})()):
            self.assertEqual(staging.check(event)['status'],'failed')
            event['pull_request']['body']='Staging: PASS (stage-images --check, 2026-10-15)'
            self.assertEqual(staging.check(event)['status'],'passed')
        event['pull_request']['head']['sha']='--bad'
        with self.assertRaisesRegex(ValueError,'identity'):staging.check(event)

    def test_workflow_is_lightweight_readonly_and_rechecks_body_edits(self):
        raw=(ROOT/'.github/workflows/staging-check.yaml').read_text(encoding='utf-8');workflow=yaml.safe_load(raw)
        self.assertEqual(workflow['permissions'],{'contents':'read'})
        self.assertEqual(workflow.get('on',workflow.get(True))['pull_request']['types'],['opened','synchronize','reopened','edited'])
        self.assertNotIn('secrets',raw);self.assertNotIn('pull_request_target',raw)
        self.assertNotIn('stage-images --context',raw);self.assertNotIn('compare_',raw)


class Render(unittest.TestCase):
    def test_runbook_step8_has_no_frozen_image_digest(self):
        text=(ROOT/'docs/dev-environment.md').read_text(encoding='utf-8')
        section=text[text.index('8. **Owner: application images.**'):text.index('9. **Owner: dev CA and TLS.**')]
        self.assertNotIn('385934466c',section);self.assertNotRegex(section,r'sha256:[a-f0-9]{64}')
        self.assertIn('deploy/common/images.lock.json',section)

    def test_only_network_hooks_and_site_metadata_change_original_host_sources(self):
        from wo36_receipts import receipt
        for name in ('vcloud-ssot.yaml','deploy/common/host-admin.py','tools/platform_host.py',
                     'deploy/environments/dev/cairo-1/services/workloads.yaml'):receipt(name)

    def test_every_recreate_has_an_exact_documented_reason_and_stateless_rolls_safely(self):
        reasons=json.loads((dev.COMMON/'dev-update-strategies.json').read_text())
        deployments=[o for o in dev.endpoints()+dev.portal()+dev.gateway() if o['kind']=='Deployment']
        found={}
        for o in deployments:
            name=o['metadata']['name'];strategy=o['spec']['strategy']
            if strategy['type']=='Recreate':found[name]=reasons[name];self.assertGreater(len(reasons[name]),40)
            else:self.assertEqual(strategy,{'type':'RollingUpdate','rollingUpdate':{'maxUnavailable':0,'maxSurge':1}})
        self.assertEqual(set(found),set(reasons))
        runtime=(dev.COMMON/'runtime-config.py').read_text();self.assertIn('cache=local',runtime)
        self.assertEqual(set(found),{'twinfra-keycloak','twinfra-openbao'})

    def test_production_wsl_locks_and_baselines_are_identical_to_pre_wo36(self):
        for name in ('00-setup-ubuntu-host.sh','user-data.yaml','user-data-remote.yaml','user-data.yaml.gz','tools/ci/pr-baselines.json',
                     'deploy/common/images.lock.json','deploy/common/bootstrap-images.lock.json','lab/wsl/console/workloads.yaml'):
            before=subprocess.check_output(['git','-C',str(ROOT),'show','7e5d017:'+name])
            actual=(ROOT/name).read_bytes()
            if not name.endswith('.gz'):actual=actual.replace(b'\r\n',b'\n')
            self.assertEqual(actual,before,name)


if __name__=='__main__':unittest.main()
