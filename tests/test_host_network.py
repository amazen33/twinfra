"""WO-36 offline failure/rollback fixtures. Never connects or runs netplan."""
import copy
from contextlib import nullcontext
import importlib.util
import json
from pathlib import Path
import re
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

DATA=host.expected()|{'mac':'64:00:6a:86:5c:4f','gateway':'192.168.1.1','dns':['192.168.1.1','1.1.1.1'],'mode':'apply','dhcpReservationConfirmed':True}
captured=[]
with patch.object(host,'request',side_effect=lambda ssh,action,**data:captured.append(data) or {'status':'passed'}):host.network(None,'check')
DATA['config']=captured[0]['config']
LEGACY=DATA['config'].replace('      accept-ra: false\n      link-local: []\n','').encode()
INFO={'address':'192.168.1.3','present':True,'static':True,'prefixLength':24,'mac':DATA['mac'],
      'gateways':['192.168.1.1'],'dns':DATA['dns'],'nodeInternalIP':['192.168.1.3']}
UNIT='twinfra-network-'+'a'*32


class NetworkFixture(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.addCleanup(patch.stopall)
        patch.object(net,'ROOT',self.root).start()
        # Windows has no POSIX ownership/mode bits; production security checks
        # have separate malicious-path fixtures below.
        patch.object(net,'secure',lambda p:None).start()
        patch.object(net,'root_private',return_value=True).start()
        snapshot=net.snapshot
        def modes():
            files=snapshot()
            if sys.platform=='win32':
                for item in files.values():
                    if item:item['mode']=0o600
            return files
        patch.object(net,'snapshot',modes).start()
        patch.object(net,'lock',lambda **_:nullcontext()).start()
        patch.object(net,'effective',lambda _:copy.deepcopy(INFO)).start()
        self.calls=[]
        patch.object(net,'run',lambda args:self.calls.append(args) or ('inactive\n' if args[0]=='systemctl' else '')).start()
        self.put(net.DHCP,b'network:\n  version: 2\n  ethernets:\n    eno1: {dhcp4: true}\n')

    def put(self,name,raw):
        p=net.path(name);p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(raw)

    def begin(self,mode='apply'):
        return net.start(DATA|{'mode':mode},(ROOT/'deploy/common/host-network.py').read_text(encoding='utf-8'))

    def awaiting(self):
        report=self.begin();full=net.load(net.STATE_DIR+'/transaction.json')
        full.update(status='awaiting-confirmation',readyAt=10,candidate=net.snapshot())
        net.save(net.STATE_DIR+'/transaction.json',full)
        return report,full

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


class Files(NetworkFixture):
    def test_check_is_readonly_and_refuses_unowned_static_files(self):
        before=list(self.root.rglob('*'));self.assertEqual(net.check(DATA)['status'],'failed')
        self.assertEqual(list(self.root.rglob('*')),before);self.assertEqual(self.calls,[])
        self.put(net.STATIC,b'unowned');self.assertEqual(net.integrity()['status'],'BLOCK')
        with self.assertRaisesRegex(ValueError,'adoption refused'):net.check(DATA)
        with self.assertRaisesRegex(ValueError,'Unowned'):self.begin()

    def test_start_saves_exact_dhcp_and_uses_detached_unit_without_netplan_over_ssh(self):
        before=net.path(net.DHCP).read_bytes();report=self.begin()
        self.assertEqual(report['status'],'running');self.assertEqual(net.load(net.STATE_DIR+'/transaction.json')['before'][net.DHCP]['data'],net.base64.b64encode(before).decode())
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
        with self.assertRaisesRegex(ValueError,'Unsafe fallback'):self.begin()

    def test_rollback_without_owned_backup_and_changed_mac_refused(self):
        with self.assertRaisesRegex(ValueError,'No saved'):self.begin('rollback')
        with patch.object(net,'effective',return_value=INFO|{'mac':'00:00:00:00:00:00'}):
            with self.assertRaisesRegex(ValueError,'identity'):self.begin()

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

    def test_confirmation_refuses_changed_candidate_and_worker_cannot_replay(self):
        report,_=self.awaiting();self.put(net.CLOUD,b'foreign edit')
        with patch.object(net,'unit_active',return_value=True),patch.object(net.time,'monotonic',return_value=20):
            with self.assertRaisesRegex(ValueError,'Candidate network files changed'):net.confirm(DATA|{'unit':report['unit']})
        self.assertFalse(net.path(net.STATE_DIR+'/confirm.json').exists())
        with self.assertRaisesRegex(ValueError,'replay refused'):net.worker(report['unit'])

    def test_worker_timeout_zero_exit_restores_disk_and_does_not_commit(self):
        code,before,report=self.worker_case()
        self.assertEqual(code,1);self.assertEqual(report['status'],'failed');self.assertEqual(net.snapshot(),before)
        self.assertFalse(net.path(net.OWNERSHIP).exists())

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
        self.worker_case(accept=True);saved=net.base64.b64decode(net.owned()['previous'][net.DHCP]['data'])
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
        self.put(net.CLOUD,b'tamper')
        with self.assertRaisesRegex(ValueError,'Owned network files differ'):self.begin('rollback')


class StaticAdoption(NetworkFixture):
    # Reuse transaction helpers but do not re-run the DHCP-oriented base tests.
    def setUp(self):
        super().setUp()
        self.put(net.STATIC,LEGACY);net.path(net.STATIC).chmod(0o600)
        self.put(net.CLOUD,b'network: {config: disabled}\n');net.path(net.CLOUD).chmod(0o600)
        net.path(net.DHCP).unlink()
        patch.object(net,'root_private',return_value=True).start()

    def test_exact_legacy_hash_adopted_with_warn_and_no_apply(self):
        self.assertEqual(len(LEGACY),308)
        self.assertEqual(net.hashlib.sha256(LEGACY).hexdigest(),net.LEGACY_SHA256)
        before=net.snapshot()
        self.assertEqual(net.check(DATA)['integrity'],{'status':'WARN','detail':'adopted (legacy profile; upgrade pending)'})
        self.assertEqual(net.check(DATA)['status'],'passed')
        self.assertEqual(net.snapshot(),before);self.assertEqual(self.calls,[])
        self.assertEqual(net.owned()['profile'],'legacy')

    def test_one_byte_different_refused_without_any_writes(self):
        self.put(net.STATIC,LEGACY+b'\n');net.path(net.STATIC).chmod(0o600)
        before={str(p):p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        for method in (lambda:net.check(DATA),lambda:self.begin()):
            with self.assertRaisesRegex(ValueError,'adoption refused'):method()
        self.assertEqual({str(p):p.read_bytes() for p in self.root.rglob('*') if p.is_file()},before)

    def test_permissions_effective_state_and_dns_mismatch_refuse_adoption(self):
        with patch.object(net,'root_private',return_value=False):
            with self.assertRaisesRegex(ValueError,'adoption refused'):net.check(DATA)
        with patch.object(net,'effective',return_value=INFO|{'dns':list(reversed(INFO['dns']))}):
            with self.assertRaisesRegex(ValueError,'adoption refused'):net.check(DATA)
        self.assertFalse(net.path(net.OWNERSHIP).exists())

    def test_upgrade_apply_and_rollback_keep_static_dot3_without_reservation(self):
        net.check(DATA)
        with patch.dict(DATA,dhcpReservationConfirmed=False):
            self.assertEqual(self.worker_case(accept=True)[0],0)
            self.assertEqual(net.owned()['profile'],'current')
            self.assertIn(b'accept-ra: false',net.path(net.STATIC).read_bytes())
            self.assertEqual(self.worker_case(accept=True,mode='rollback')[0],0)
        self.assertEqual(net.path(net.STATIC).read_bytes(),LEGACY)
        self.assertFalse(net.path(net.DHCP).exists())
        self.assertTrue(net.check(DATA)['network']['static'])
        self.assertEqual(net.check(DATA)['integrity']['status'],'WARN')

    def test_failed_upgrade_restores_legacy_static_not_old_dhcp_receipt(self):
        self.put(net.STATE_DIR+'/baseline.json',b'{"old": "DHCP recovery evidence"}')
        net.check(DATA);before=net.snapshot()
        with patch.dict(DATA,dhcpReservationConfirmed=False):self.assertEqual(self.worker_case()[0],1)
        self.assertEqual(net.snapshot(),before)
        self.assertEqual(net.load(net.STATE_DIR+'/baseline.json'),{'old':'DHCP recovery evidence'})
        self.assertEqual(net.integrity()['status'],'WARN')

    def test_corrected_static_adoption_and_apply_are_noop(self):
        self.put(net.STATIC,DATA['config'].encode());net.path(net.STATIC).chmod(0o600)
        before=net.snapshot()
        self.assertEqual(net.check(DATA)['status'],'passed')
        self.assertEqual(self.begin()['status'],'passed')
        self.assertEqual(net.snapshot(),before)
        self.assertFalse(any(c[0]=='systemd-run' for c in self.calls))


class Safety(NetworkFixture):
    def test_apply_and_rollback_without_safe_fallback_make_no_writes(self):
        before=net.snapshot();files=list(self.root.rglob('*'))
        with patch.dict(DATA,dhcpReservationConfirmed=False),patch.object(net,'lock',side_effect=AssertionError('lock must not be opened')):
            with self.assertRaisesRegex(ValueError,'Unsafe fallback'):self.begin()
        self.assertEqual(net.snapshot(),before);self.assertEqual(list(self.root.rglob('*')),files)
        self.worker_case(accept=True)
        before=net.snapshot();receipt=net.path(net.OWNERSHIP).read_bytes()
        with patch.dict(DATA,dhcpReservationConfirmed=False),patch.object(net,'lock',side_effect=AssertionError('lock must not be opened')):
            with self.assertRaisesRegex(ValueError,'Unsafe fallback'):self.begin('rollback')
        self.assertEqual(net.snapshot(),before);self.assertEqual(net.path(net.OWNERSHIP).read_bytes(),receipt)


class Controller(unittest.TestCase):
    def test_private_adoption_requires_root_group_and_exact_mode(self):
        for uid,gid,mode,expected in ((0,0,0o100600,True),(0,0,0o100644,False),(0,1,0o100600,False),(1,0,0o100600,False)):
            info=type('Stat',(),{'st_uid':uid,'st_gid':gid,'st_mode':mode})()
            with patch.object(net,'secure'),patch.object(Path,'stat',return_value=info):
                self.assertEqual(net.root_private(net.STATIC),expected)
        # A reserved-DHCP rollback preserves its original safe mode; adoption
        # of the owner-approved static file still requires exactly 0600.
        info=type('Stat',(),{'st_uid':0,'st_gid':0,'st_mode':0o100644})()
        with patch.object(net,'secure'),patch.object(Path,'stat',return_value=info):
            self.assertFalse(net.root_private(net.DHCP))
            self.assertTrue(net.root_private(net.DHCP,0o644))

    def test_vm_fixture_refuses_local_execution_and_workflow_is_restricted(self):
        spec=importlib.util.spec_from_file_location('network_vm',ROOT/'tools/ci/host_network_vm.py')
        vm=importlib.util.module_from_spec(spec);spec.loader.exec_module(vm)
        with patch.dict(vm.os.environ,{},clear=True):
            with self.assertRaisesRegex(ValueError,'Disposable GitHub-hosted'):vm.guard()
        raw=(ROOT/'.github/workflows/host-network-vm.yaml').read_text(encoding='utf-8');workflow=yaml.safe_load(raw)
        self.assertEqual(workflow['permissions'],{'contents':'read'})
        self.assertNotIn('pull_request_target',raw);self.assertNotIn('secrets',raw)
        for step in workflow['jobs']['netplan-vm']['steps']:
            if 'uses' in step:self.assertRegex(step['uses'],r'@[a-f0-9]{40}$')

    def test_vm_gap_bounds_fail_long_gaps_other_addresses_dhcp_and_missing_coverage(self):
        spec=importlib.util.spec_from_file_location('network_vm_bounds',ROOT/'tools/ci/host_network_vm.py')
        vm=importlib.util.module_from_spec(spec);spec.loader.exec_module(vm)
        def row(at,good=True):return {'at':str(at),'monotonic':at,'completed':at+.01,
            'addresses':[vm.IP] if good else [],'gateways':['192.168.1.1'] if good else [],'dhcpActive':False}
        samples=[row(0),row(.2,False),row(.4,False),row(.6)]
        self.assertEqual(vm.evaluate_samples(samples)['maxGapSecondsUpperBound'],.61)
        near=[row(i/5,False) for i in range(1,25)]
        self.assertLessEqual(vm.evaluate_samples([row(0),*near,row(4.9)])['maxGapSecondsUpperBound'],5)
        with self.assertRaisesRegex(ValueError,'five seconds'):vm.evaluate_samples([row(0),*near,row(5.01)])
        for mutation,error in (({'addresses':['192.168.1.102']},'Alternate'),({'dhcpActive':True},'DHCP'),
                               ({'error':'fixture'},'sampling failed')):
            with self.assertRaisesRegex(ValueError,error):vm.evaluate_samples([row(0),row(.2)|mutation,row(.4)])
        with self.assertRaisesRegex(ValueError,'coverage'):vm.evaluate_samples([row(0),row(1.1)])
        with self.assertRaisesRegex(ValueError,'recover'):vm.evaluate_samples([row(0),row(.2,False)])

    def test_real_ip_json_shapes_get_mac_from_link_not_ipv4_address_output(self):
        address=[{'ifindex':2,'ifname':'eno1','flags':['BROADCAST','MULTICAST','UP','LOWER_UP'],
                  'addr_info':[{'family':'inet','local':'192.168.1.3','prefixlen':24,'scope':'global'}]}]
        def run(args):
            if args[:4]==['ip','-j','-4','address']:return json.dumps(address)
            if args[:3]==['ip','-j','link']:return json.dumps([{'ifname':'eno1','address':DATA['mac'],'link_type':'ether'}])
            if args[:4]==['ip','-j','-4','route']:return json.dumps([{'dst':'default','gateway':'192.168.1.1','dev':'eno1'}])
            if args[0]=='resolvectl':return 'Link 2 (eno1): 192.168.1.1 1.1.1.1 fe80::1\n'
            if args[0]=='kubectl':return json.dumps({'items':[{'metadata':{'name':DATA['node']},'status':{'addresses':[{'type':'InternalIP','address':DATA['ip']}]}}]})
            raise AssertionError('Unexpected command '+str(args))
        with patch.object(net,'run',side_effect=run):
            self.assertEqual(net.effective(DATA),INFO)
            address[0]['addr_info'][0]['dynamic']=True
            self.assertFalse(net.effective(DATA)['static'])

    def test_rendered_netplan_matches_the_ssot_and_retains_address_without_carrier(self):
        captured=[]
        with patch.object(host,'request',side_effect=lambda ssh,action,**data:captured.append(data) or {'status':'passed'}):
            host.network(None,'apply')
        config=yaml.safe_load(captured[0]['config'])
        self.assertEqual(config,{'network':{'version':2,'renderer':'networkd','ethernets':{'eno1':{
            'dhcp4':False,'dhcp6':False,'ignore-carrier':True,'accept-ra':False,'link-local':[],'addresses':['192.168.1.3/24'],
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
        code=re.search(r'python -c "([^\n]+)"',section)[1]
        output=subprocess.check_output([sys.executable,'-c',code],cwd=ROOT,text=True)
        images=json.loads((dev.COMMON/'images.lock.json').read_text())['images']
        self.assertEqual(output.strip().splitlines(),[name+': '+images[name]['canonical'] for name in ('console','postgres')])

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
            if (ROOT/'security/security-wave-2026-10-images.json').is_file() and name in (
                    'deploy/common/images.lock.json','lab/wsl/console/workloads.yaml'):
                from r12_receipts import receipt as r12_receipt
                actual=r12_receipt(name)
            if not name.endswith('.gz'):actual=actual.replace(b'\r\n',b'\n')
            self.assertEqual(actual,before,name)


if __name__=='__main__':unittest.main()
