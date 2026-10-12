"""WO-31 static fixtures only. No SSH, sudo, host inventory or VM execution."""
import copy
from contextlib import nullcontext
import hashlib
import gzip
import importlib.util
import io
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

import yaml

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
import platform_dev as dev
import platform_host as host
import platform_image_staging as images
from test_dev_runnable import FakeCtr, FakeSSH, locked, stager

spec=importlib.util.spec_from_file_location('host_agent',ROOT/'deploy/common/host-admin.py')
agent=importlib.util.module_from_spec(spec);spec.loader.exec_module(agent)
MAIN='968f336f9335739c35b79ed838dc7cfaeebff235'
AMENDMENT_2_BASE='a8f4f434c7bed890311793590952dd5295d2e97e'
AMENDMENT_3_BASE='a7512ed9ab059857b60e9b4848fad2287e4549ab'


def mask_bpffs_script(raw):
    """Only Amendment 2's BPF helper/setup and mount dependency may differ."""
    raw=raw.replace('\r\n','\n')
    raw=raw.replace('    check_bpffs_migration # WO-31: read-only ownership guard before any apply writes.\n','')
    raw=re.sub(r'(?ms)^# BEGIN WO-31 BPFFS COMPATIBILITY\n.*?^# END WO-31 BPFFS COMPATIBILITY\n\n','',raw)
    raw=re.sub(r"(?ms)^        mkdir -p /sys/fs/bpf\n.*?^        \[\[ \$\(findmnt -n -o FSTYPE --target /sys/fs/bpf\) == bpf \]\] \|\| die 'Unexpected filesystem at /sys/fs/bpf'\n",'        @@BPFFS_SETUP@@\n',raw)
    raw=raw.replace('        prepare_bpffs\n','        @@BPFFS_SETUP@@\n')
    raw=raw.replace('Requires=sys-fs-bpf.mount\nAfter=sys-fs-bpf.mount\n','@@BPFFS_DEPENDENCY@@\n')
    raw=raw.replace('RequiresMountsFor=/sys/fs/bpf\n','@@BPFFS_DEPENDENCY@@\n')
    if raw.count('@@BPFFS_SETUP@@')!=1 or raw.count('@@BPFFS_DEPENDENCY@@')!=1:
        raise ValueError('BPF mask does not match the exact approved blocks')
    return raw


def fixture(post=False):
    state={'os':{'ID':'ubuntu','VERSION_ID':'24.04','PRETTY_NAME':'Ubuntu 24.04.5 LTS'},
        'architecture':'x86_64','vtX':True,'kvm':True,'ramGiB':31,'rootFreeGiB':80,
        'vgFreeGiB':120.5,'swap':[],'timeSynced':True,'addresses':['192.168.1.3'],
        'secureBoot':True,'lockdown':'none [integrity] confidentiality',
        'sshd':{'passwordauthentication':'no','kbdinteractiveauthentication':'no','permitrootlogin':'no'},
        'listeners':[],'result':None,'cluster':{},'nodes':[]}
    if post:
        state.update(result={'status':'ready','kubernetes':'v1.36.5','mirror_status':'staged-verified'},
            cluster={'clusterName':'twinfra-dev-cairo-1','controlPlaneEndpoint':'api.dev.cairo-1.twinfra.example.com:6443'},
            listeners=[{'port':p,'owners':[name]} for p,name in agent.PORTS.items()],
            nodes=[{'metadata':{'name':'twinfra-dev-cairo-1'},'status':{'addresses':[{'type':'InternalIP','address':'192.168.1.3'}],
                'conditions':[{'type':'Ready','status':'True'}]}}])
    return state


class HostSSH:
    def __init__(self,state=None,fail_probe=0,sudo_failure=False,ready=False,unit_states=None,busy=False):
        self.state=state or fixture();self.calls=[];self.probes=0
        self.fail_probe,self.sudo_failure,self.ready=fail_probe,sudo_failure,ready
        self.unit_states=list(unit_states or [{'status':'passed','exitCode':0}]);self.busy=busy
        self.prefix=images.SSH('twinfra-operator@192.168.1.3','twinfra-dev-cairo-1').prefix

    def run(self,cmd,payload=None):
        self.calls.append((cmd,payload))
        if cmd==['true']:
            self.probes+=1
            if self.probes==self.fail_probe:raise ValueError('Key-login probe failed')
            return b''
        if cmd[0]=='mktemp':return b'/tmp/twinfra-inputs.ABCDEF12\n'
        self.assert_command(cmd)
        if self.sudo_failure:raise ValueError('sudo -n refused')
        data=json.loads(cmd[-1]);action=data['action']
        if action in ('check','bootstrap-state'):
            result=agent.evaluate(self.state,data)
            if action=='bootstrap-state':result['ready']=self.ready
            if self.busy:result={'status':'failed','message':'Bootstrap already active; second run refused'}
        elif action=='bootstrap':result={'status':'running','unit':'twinfra-bootstrap-'+'a'*32,'message':'Logs: journalctl -u twinfra-bootstrap-'+'a'*32}
        elif action=='bootstrap-status':result=self.unit_states.pop(0)
        elif action=='firewall':result={'status':'passed','rollback':'twinfra-firewall-rollback-'+'a'*32}
        else:result={'status':'passed'}
        return json.dumps(result).encode()

    @staticmethod
    def assert_command(cmd):
        assert cmd[:4]==['sudo','-n','python3','-']


class HostChecks(unittest.TestCase):
    def test_inventory_only_reads_and_parses_real_ss_shape(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            contents={'etc/os-release':'ID=ubuntu\nVERSION_ID="24.04"\n','proc/cpuinfo':'flags: vmx\n',
                'proc/meminfo':'MemTotal: 32505856 kB\n','proc/swaps':'Filename Type Size Used Priority\n',
                'sys/kernel/security/lockdown':'none [integrity] confidentiality',
                'dev/kvm':'fixture','var/lib/vcloud-host/result.json':json.dumps(fixture(True)['result'])}
            for name,raw in contents.items():
                file=root/name;file.parent.mkdir(parents=True,exist_ok=True);file.write_text(raw)
            file=root/'sys/firmware/efi/efivars/SecureBoot-8be4df61-93ca-11d2-aa0d-00e098032b8c'
            file.parent.mkdir(parents=True);file.write_bytes(b'\x07\0\0\0\x01')
            before={str(f.relative_to(root)):f.read_bytes() for f in root.rglob('*') if f.is_file()}
            calls=[]
            def run(cmd):
                calls.append(cmd)
                if cmd[0]=='uname':return 'x86_64\n'
                if cmd[0]=='df':return 'Avail\n'+str(80*agent.GIB)+'\n'
                if cmd[0]=='vgs':return json.dumps({'report':[{'vg':[{'vg_name':'ubuntu-vg','vg_free':str(120*agent.GIB)}]}]})
                if cmd[0]=='timedatectl':return 'yes\n'
                if cmd[0]=='ip':return json.dumps([{'addr_info':[{'family':'inet','local':'192.168.1.3'}]}])
                if cmd[0]=='ss':return '\n'.join('LISTEN 0 4096 0.0.0.0:'+str(p)+' 0.0.0.0:* users:(("'+n+'",pid=1,fd=3))' for p,n in agent.PORTS.items())
                if cmd[0]=='sshd':return 'passwordauthentication no\nkbdinteractiveauthentication no\npermitrootlogin no\n'
                if 'configmap' in cmd:return json.dumps({'data':{'ClusterConfiguration':'clusterName: twinfra-dev-cairo-1\ncontrolPlaneEndpoint: api.dev.cairo-1.twinfra.example.com:6443\n'}})
                if 'nodes' in cmd:return json.dumps({'items':fixture(True)['nodes']})
                raise AssertionError('Unexpected command: '+str(cmd))
            with patch.object(agent,'ROOT',root),patch.object(agent,'secure'),patch.object(agent,'run',side_effect=run):
                state=agent.inventory(host.expected())
                self.assertEqual(agent.evaluate(state,host.expected())['status'],'passed')
            self.assertTrue(all(c[0] in ('uname','df','vgs','timedatectl','ip','ss','sshd','kubectl') for c in calls))
            self.assertEqual(before,{str(f.relative_to(root)):f.read_bytes() for f in root.rglob('*') if f.is_file()})

    def check(self,state):
        ssh=HostSSH(state);report=host.execute('host-check',ssh)
        self.assertEqual(len(ssh.calls),1)
        command,code=ssh.calls[0]
        self.assertEqual(json.loads(command[-1])['action'],'check')
        self.assertIn(b'def inventory',code)
        return report

    def test_fresh_host_readonly_pass(self):
        report=self.check(fixture());self.assertEqual(report['status'],'passed');self.assertEqual(report['mode'],'pre-bootstrap')
        self.assertEqual(report,json.loads((ROOT/'tests/fixtures/wo31-host-check.json').read_text())['before'])

    def test_before_bootstrap_port_taken_blocks(self):
        state=fixture();state['listeners']=[{'port':6443,'owners':['foreign']}]
        self.assertEqual(self.check(state)['status'],'failed')

    def test_verified_post_bootstrap_pass(self):
        report=self.check(fixture(True));self.assertEqual(report['status'],'passed')
        self.assertEqual(report['checks'][-1]['detail'],'bootstrap-owned cluster verified')
        self.assertEqual(report,json.loads((ROOT/'tests/fixtures/wo31-host-check.json').read_text())['after'])

    def test_not_ready_result_blocks_occupied_ports(self):
        state=fixture(True);state['result']['status']='reboot-required'
        self.assertEqual(self.check(state)['status'],'failed')

    def test_all_post_bootstrap_ownership_inputs_are_mandatory(self):
        mutations=[('result','kubernetes','v1.35.0'),('result','mirror_status','reachable'),
            ('cluster','clusterName','foreign'),('cluster','controlPlaneEndpoint','192.168.1.3:6443')]
        for section,key,value in mutations:
            with self.subTest(key=key):
                state=fixture(True);state[section][key]=value
                self.assertEqual(self.check(state)['status'],'failed')
        state=fixture(True);state['nodes'][0]['status']['addresses'][0]['address']='192.168.1.4'
        self.assertEqual(self.check(state)['status'],'failed')

    def test_listener_processes_must_match_exactly(self):
        for port in agent.PORTS:
            state=fixture(True);next(l for l in state['listeners'] if l['port']==port)['owners']=['foreign']
            self.assertEqual(self.check(state)['status'],'failed')
        state=fixture(True);state['listeners']=state['listeners'][1:]
        self.assertEqual(self.check(state)['status'],'failed')

    def test_hardware_and_lockdown_blockers(self):
        for key,value in [('ramGiB',23.9),('rootFreeGiB',19),('vgFreeGiB',19),('vtX',False),('kvm',False),
            ('timeSynced',False),('secureBoot',False),('lockdown','[none] integrity'),('addresses',['10.50.0.10'])]:
            state=fixture();state[key]=value
            self.assertEqual(self.check(state)['status'],'failed',key)

    def test_cli_default_target_key_only_and_wrong_context_refused(self):
        transport=images.SSH('twinfra-operator@192.168.1.3','twinfra-dev-cairo-1')
        for option in ('BatchMode=yes','StrictHostKeyChecking=yes','PreferredAuthentications=publickey','PasswordAuthentication=no','ControlPath=none'):
            self.assertIn(option,transport.prefix)
        for target,context in [('operator@10.50.0.10','twinfra-dev-cairo-1'),('operator@192.168.1.3','production')]:
            with self.assertRaises(ValueError):images.SSH(target,context)


class HostBootstrap(unittest.TestCase):
    def test_staging_replacement_only_for_owned_incomplete_run(self):
        for condition in ('incomplete','complete','active','unowned','ready','invalid-receipt','tampered-input'):
            with self.subTest(condition=condition),tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp);incoming=root/'tmp/twinfra-inputs.ABCDEF12';incoming.mkdir(parents=True)
                stage=root/'var/lib/twinfra/host-bootstrap';stage.mkdir(parents=True)
                for name in agent.BOOTSTRAP_FILES:
                    (stage/name).write_text('old '+name+'\n',newline='\n')
                    (incoming/name).write_text('new '+name+'\n',newline='\n')
                previous={name:hashlib.sha256((stage/name).read_bytes()).hexdigest() for name in agent.BOOTSTRAP_FILES}
                hashes={name:hashlib.sha256((incoming/name).read_bytes()).hexdigest() for name in agent.BOOTSTRAP_FILES}
                receipt=stage/'receipt.json';receipt.write_text(json.dumps(previous))
                result=root/'var/lib/vcloud-host/result.json';result.parent.mkdir(parents=True)
                result.write_text(json.dumps({'status':'ready' if condition=='ready' else 'failed','phase':'containerd'}))
                if condition=='complete':(stage/'complete.json').write_text(json.dumps(previous))
                if condition=='invalid-receipt':receipt.write_text(json.dumps({'host.env':'invalid'}))
                if condition=='tampered-input':(stage/'host.env').write_text('foreign changes')
                data=host.expected()|{'incoming':'/tmp/twinfra-inputs.ABCDEF12','operator':'synthetic','hashes':hashes}
                fake_pwd=types.SimpleNamespace(getpwnam=lambda name:types.SimpleNamespace(pw_uid=incoming.stat().st_uid))
                def secure(path):
                    if condition=='unowned' and path==receipt:raise ValueError('Unowned/insecure host path')
                calls=[]
                def command(cmd,**kw):
                    calls.append(cmd)
                    raw='twinfra-bootstrap-'+'a'*32+'.service loaded activating start Bootstrap\n' if condition=='active' and 'list-units' in cmd else ''
                    return subprocess.CompletedProcess(cmd,0,raw,'')
                before={str(f.relative_to(root)):f.read_bytes() for f in root.rglob('*') if f.is_file()}
                with patch.dict(sys.modules,{'pwd':fake_pwd}),patch.object(agent,'ROOT',root),patch.object(agent,'secure',side_effect=secure),patch.object(agent.stat,'S_IMODE',return_value=0o700),patch.object(agent,'inventory',return_value=fixture()),patch.object(agent,'command',side_effect=command),patch.object(agent,'bootstrap_lock',side_effect=nullcontext):
                    if condition=='incomplete':
                        self.assertEqual(agent.bootstrap_apply(data)['status'],'running')
                        self.assertEqual(json.loads(receipt.read_text()),hashes)
                        for name,sha in hashes.items():self.assertEqual(hashlib.sha256((stage/name).read_bytes()).hexdigest(),sha)
                        self.assertTrue(any(c[0]=='systemd-run' for c in calls))
                        self.assertFalse((stage/'complete.json').exists())
                    else:
                        with self.assertRaises(ValueError):agent.bootstrap_apply(data)
                        self.assertEqual(before,{str(f.relative_to(root)):f.read_bytes() for f in root.rglob('*') if f.is_file()})
                        self.assertFalse(any(c[0]=='systemd-run' for c in calls))

    def test_api_input_mapping_preserves_foreign_lines_and_refuses_conflict(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);path=root/'etc/hosts';path.parent.mkdir();path.write_text('127.0.0.1 localhost\n')
            with patch.object(agent,'ROOT',root),patch.object(agent,'secure'):
                agent.api_mapping(host.expected())
                first=path.read_bytes();agent.api_mapping(host.expected());self.assertEqual(path.read_bytes(),first)
                self.assertTrue(path.read_text().startswith('127.0.0.1 localhost\n'))
                path.write_text('192.168.1.9 api.dev.cairo-1.twinfra.example.com\n')
                with self.assertRaisesRegex(ValueError,'foreign'):agent.api_mapping(host.expected())

    def test_successful_copy_verifies_installed_bytes_and_shared_entrypoint(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);incoming=root/'tmp/twinfra-inputs.ABCDEF12';incoming.mkdir(parents=True)
            names=['host.env','00-setup-ubuntu-host.sh','bootstrap-images.lock.json','stage-images.py','dev-log-caps.sh']
            for name in names:(incoming/name).write_text('fixture '+name+'\n',newline='\n')
            hashes={name:hashlib.sha256((incoming/name).read_bytes()).hexdigest() for name in names}
            data=host.expected()|{'incoming':'/tmp/twinfra-inputs.ABCDEF12','operator':'synthetic','hashes':hashes}
            fake_pwd=types.SimpleNamespace(getpwnam=lambda name:types.SimpleNamespace(pw_uid=incoming.stat().st_uid))
            calls=[]
            def command(cmd,**kw):
                calls.append(cmd)
                out='LoadState=loaded\nActiveState=active\nSubState=exited\nExecMainCode=1\nExecMainStatus=0\nResult=success\n' if cmd[:2]==['systemctl','show'] else ''
                return subprocess.CompletedProcess(cmd,0,out,'')
            with patch.dict(sys.modules,{'pwd':fake_pwd}),patch.object(agent,'ROOT',root),patch.object(agent,'secure'),patch.object(agent.stat,'S_IMODE',return_value=0o700),patch.object(agent,'inventory',return_value=fixture()),patch.object(agent,'command',side_effect=command),patch.object(agent,'bootstrap_lock',side_effect=nullcontext):
                report=agent.bootstrap_apply(data)
                self.assertEqual(report['status'],'running')
                self.assertFalse((root/'var/lib/twinfra/host-bootstrap/complete.json').exists())
                self.assertEqual(agent.bootstrap_finish(data|{'unit':report['unit']})['status'],'passed')
            stage=root/'var/lib/twinfra/host-bootstrap'
            for name,sha in hashes.items():self.assertEqual(hashlib.sha256((stage/name).read_bytes()).hexdigest(),sha)
            self.assertEqual(json.loads((stage/'complete.json').read_text()),hashes)
            launch=next(c for c in calls if c[0]=='systemd-run')
            for option in ('--no-block','--property=Type=oneshot','--property=RemainAfterExit=yes','--property=TimeoutStartSec=infinity','--property=RuntimeMaxSec=infinity'):
                self.assertIn(option,launch)
            self.assertEqual(launch[-1],'--apply')
            self.assertNotIn('--wait',launch);self.assertNotIn('--pipe',launch)
            self.assertFalse(any(c[0] in ('env','bash','/usr/bin/env','/usr/bin/bash') and c[-1]=='--apply' for c in calls))
            labels=next(c for c in calls if c[0]=='kubectl')
            self.assertEqual(labels[5],'twinfra-dev-cairo-1')
            before={str(f.relative_to(root)):f.read_bytes() for f in root.rglob('*') if f.is_file()}
            calls.clear()
            with patch.object(agent,'ROOT',root),patch.object(agent,'secure'),patch.object(agent,'inventory',return_value=fixture(True)),patch.object(agent,'command',side_effect=command):
                self.assertTrue(agent.bootstrap_state(data)['ready'])
            self.assertEqual(len(calls),2);self.assertEqual(calls[-1][-1],'--validate')
            self.assertEqual(before,{str(f.relative_to(root)):f.read_bytes() for f in root.rglob('*') if f.is_file()})

    def test_sudo_denied_before_scp_or_bootstrap(self):
        ssh=HostSSH(sudo_failure=True)
        with patch.object(host.subprocess,'run',side_effect=AssertionError('SCP invoked')):
            with self.assertRaisesRegex(ValueError,'sudo'):host.bootstrap(ssh)
        self.assertEqual(len(ssh.calls),1)

    def test_check_streams_only_shared_preflight_no_transfers(self):
        ssh=HostSSH()
        with patch.object(host.subprocess,'run',side_effect=AssertionError('SCP invoked')):
            self.assertEqual(host.bootstrap(ssh,check=True)['status'],'passed')
        self.assertEqual([json.loads(c[-1])['action'] for c,p in ssh.calls],['bootstrap-state','bootstrap-preflight'])
        self.assertIn(repr((ROOT/'00-setup-ubuntu-host.sh').read_text()).encode(),ssh.calls[-1][1])

    def test_transferred_hash_inventory_and_private_staging(self):
        ssh=HostSSH();copies=[]
        def scp(cmd,**kwargs):copies.append(cmd);return subprocess.CompletedProcess(cmd,0,b'',b'')
        self.assertEqual(host.bootstrap(ssh,copier=scp,sleeper=lambda _:None)['status'],'passed')
        self.assertEqual(len(copies),5)
        for cmd in copies:self.assertIn('StrictHostKeyChecking=yes',cmd)
        data=next(json.loads(c[-1]) for c,p in ssh.calls if c[0]=='sudo' and json.loads(c[-1])['action']=='bootstrap')
        self.assertEqual(data['hashes']['00-setup-ubuntu-host.sh'],hashlib.sha256((ROOT/'00-setup-ubuntu-host.sh').read_bytes()).hexdigest())
        self.assertEqual(data['incoming'],'/tmp/twinfra-inputs.ABCDEF12')

    def test_healthy_rerun_no_scp_no_mutations(self):
        ssh=HostSSH(fixture(True),ready=True)
        with patch.object(host.subprocess,'run',side_effect=AssertionError('SCP invoked')):
            self.assertTrue(host.bootstrap(ssh)['ready'])
        self.assertEqual(len(ssh.calls),1)

    def test_hash_mismatch_refused_before_install_or_bootstrap(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);incoming=root/'tmp/twinfra-inputs.ABCDEF12';incoming.mkdir(parents=True);incoming.chmod(0o700)
            names=['host.env','00-setup-ubuntu-host.sh','bootstrap-images.lock.json','stage-images.py','dev-log-caps.sh']
            for name in names:(incoming/name).write_text('fixture')
            data={'incoming':'/tmp/twinfra-inputs.ABCDEF12','operator':'synthetic','hashes':{name:'a'*64 for name in names}}
            fake_pwd=types.SimpleNamespace(getpwnam=lambda name:types.SimpleNamespace(pw_uid=incoming.stat().st_uid))
            # NTFS has no POSIX mode bits; supply the private 0700 metadata fixture.
            with patch.dict(sys.modules,{'pwd':fake_pwd}),patch.object(agent,'ROOT',root),patch.object(agent.stat,'S_IMODE',return_value=0o700),patch.object(agent,'refuse_active_bootstrap'),patch.object(agent,'bootstrap_lock',side_effect=nullcontext),patch.object(agent,'command',side_effect=AssertionError('Bootstrap ran')):
                with self.assertRaisesRegex(ValueError,'SHA256'):agent.bootstrap_apply(data)
            self.assertFalse((root/'var/lib/twinfra/host-bootstrap').exists())

    def test_fresh_key_polling_running_then_success(self):
        ssh=HostSSH(unit_states=[{'status':'running'},{'status':'running'},{'status':'passed','exitCode':0}])
        with patch.object(host,'request',wraps=host.request),patch('sys.stderr',new=io.StringIO()) as output:
            result=host.bootstrap(ssh,copier=lambda *a,**k:subprocess.CompletedProcess(a,0),sleeper=lambda _:None)
        self.assertEqual(result['status'],'passed')
        actions=[json.loads(c[-1])['action'] for c,p in ssh.calls if c[0]=='sudo']
        self.assertEqual(actions,['bootstrap-state','bootstrap','bootstrap-status','bootstrap-status','bootstrap-status','bootstrap-finish'])
        self.assertIn('journalctl -u',output.getvalue())
        for option in ('ControlMaster=no','ControlPath=none','BatchMode=yes','PreferredAuthentications=publickey'):
            self.assertIn(option,ssh.prefix)

    def test_reboot_required_and_failure_do_not_finish(self):
        for status,code in (('reboot-required',20),('failed',1)):
            with self.subTest(status=status):
                ssh=HostSSH(unit_states=[{'status':status,'exitCode':code}])
                result=host.bootstrap(ssh,copier=lambda *a,**k:subprocess.CompletedProcess(a,0),sleeper=lambda _:None)
                self.assertEqual(result,{'status':status,'exitCode':code})
                self.assertNotIn('bootstrap-finish',[json.loads(c[-1])['action'] for c,p in ssh.calls if c[0]=='sudo'])
                with patch.object(host,'execute',return_value=result),patch('sys.stdout',new=io.StringIO()):
                    self.assertEqual(host.action('host-bootstrap','twinfra-dev-cairo-1','operator@192.168.1.3'),code)

    def test_concurrent_refusal_before_transfer(self):
        ssh=HostSSH(busy=True)
        with patch.object(host.subprocess,'run',side_effect=AssertionError('SCP invoked')):
            self.assertEqual(host.bootstrap(ssh)['status'],'failed')
        self.assertEqual(len(ssh.calls),1)
        for active,sub in (('activating','start'),('active','running'),('deactivating','stop')):
            with patch.object(agent,'run',return_value='twinfra-bootstrap-'+'a'*32+'.service loaded '+active+' '+sub+' Bootstrap\n'):
                with self.assertRaisesRegex(ValueError,'second run refused'):agent.refuse_active_bootstrap()

    def test_unit_exit_code_signal_and_unavailable_reports(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);unit='twinfra-bootstrap-'+'a'*32;data={'unit':unit,'hashes':{}}
            file=root/'var/lib/twinfra/host-bootstrap/unit.json';file.parent.mkdir(parents=True);file.write_text(json.dumps(data))
            for active,sub,code,status,result,expected in (
                ('activating','start',0,0,'success','running'),('active','exited',1,0,'success','passed'),
                ('failed','failed',1,20,'exit-code','reboot-required'),('failed','failed',1,1,'exit-code','failed'),
                ('failed','failed',2,9,'signal','failed'),('inactive','dead',0,0,'success','failed')):
                raw=f'LoadState=loaded\nActiveState={active}\nSubState={sub}\nExecMainCode={code}\nExecMainStatus={status}\nResult={result}\n'
                with patch.object(agent,'ROOT',root),patch.object(agent,'secure'),patch.object(agent,'run',return_value=raw):
                    self.assertEqual(agent.bootstrap_status(data)['status'],expected)
                    if expected!='passed':
                        with patch.object(agent,'bootstrap_lock',side_effect=nullcontext),patch.object(agent,'bootstrap_complete',side_effect=AssertionError('Finished prematurely')):
                            self.assertEqual(agent.bootstrap_finish(data)['status'],expected)
            with patch.object(agent,'ROOT',root),patch.object(agent,'secure'),patch.object(agent,'run',return_value='LoadState=not-found\n'):
                self.assertEqual(agent.bootstrap_status(data)['status'],'failed')

    def test_unit_start_lock_refuses_simultaneous_client(self):
        fake=types.SimpleNamespace(LOCK_EX=2,LOCK_NB=4,LOCK_UN=8,flock=lambda *a:(_ for _ in ()).throw(BlockingIOError()))
        with tempfile.TemporaryDirectory() as tmp,patch.dict(sys.modules,{'fcntl':fake}),patch.object(agent,'ROOT',Path(tmp)),patch.object(agent,'secure'):
            with self.assertRaisesRegex(ValueError,'second run refused'):
                with agent.bootstrap_lock():self.fail('Lock granted')

    def test_non_root_action_returns_json_failure(self):
        with patch.object(agent.os,'geteuid',return_value=1000,create=True),patch('sys.stdout',new=io.StringIO()) as output:
            agent.main()
        self.assertEqual(json.loads(output.getvalue()),{'status':'failed','message':'Owner action requires sudo -n'})


class Hardening(unittest.TestCase):
    def test_owned_storage_rerun_preserves_uid26_and_all_file_bytes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);mount=root/'var/lib/twinfra/local-pv/postgres-1';mount.mkdir(parents=True)
            uuid='11111111-1111-1111-1111-111111111111';calls=[]
            files={'var/lib/twinfra/host-hardening/storage.json':json.dumps({'owner':'WO-31 twinfra-dev-cairo-1','bytes':20*agent.GIB,'uuid':uuid}),
                'etc/fstab':'UUID='+uuid+' /var/lib/twinfra/local-pv/postgres-1 ext4 nodev,nosuid,noexec,noatime,nofail,x-systemd.device-timeout=30s 0 2\n',
                'etc/systemd/system/kubelet.service.d/20-twinfra-storage.conf':'[Unit]\nRequiresMountsFor=/var/lib/twinfra/local-pv/postgres-1\n'}
            for name,raw in files.items():
                p=root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(raw,newline='\n')
            before={n:(root/n).read_bytes() for n in files}
            original_stat=Path.stat
            def owned_stat(path,*args,**kwargs):
                value=original_stat(path,*args,**kwargs)
                if path==mount:
                    values=list(value);values[0]=(value.st_mode & ~0o777)|0o700;values[4]=26;values[5]=26
                    return os.stat_result(values)
                return value
            def command(cmd,**kwargs):
                calls.append(cmd)
                if cmd[0]=='vgs':out=json.dumps({'report':[{'vg':[{'vg_free':str(60*agent.GIB)}]}]})
                elif cmd[0]=='lvs':out=json.dumps({'report':[{'lv':[{'vg_name':'ubuntu-vg','lv_name':'twinfra-postgres-1','lv_size':str(20*agent.GIB)}]}]})
                elif cmd[0]=='blkid':out=uuid+'\n'
                elif cmd[0]=='findmnt':out=uuid+(' '+str(20*agent.GIB) if '--bytes' in cmd else '')+' ext4 rw,nodev,nosuid,noexec,noatime\n'
                else:raise AssertionError('Unexpected mutation '+str(cmd))
                return subprocess.CompletedProcess(cmd,0,out,'')
            with patch.object(agent,'ROOT',root),patch.object(agent,'secure'),patch.object(agent,'command',side_effect=command),patch.object(Path,'stat',new=owned_stat),patch.object(agent.os,'chown',create=True) as chown:
                self.assertEqual(agent.storage_apply()['status'],'passed')
            chown.assert_not_called();self.assertEqual(before,{n:(root/n).read_bytes() for n in files})

    def test_ssh_invalid_config_restores_before_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);calls=[]
            def run(cmd):
                calls.append(cmd)
                if cmd==['sshd','-t']:raise ValueError('sshd validation refused')
                return ''
            with patch.object(agent,'ROOT',root),patch.object(agent,'secure'),patch.object(agent,'run',side_effect=run):
                with self.assertRaisesRegex(ValueError,'validation'):agent.ssh_harden({'config':host.ssh_config()})
            self.assertFalse((root/'etc/ssh/sshd_config.d/10-twinfra-hardening.conf').exists())
            self.assertFalse((root/'var/lib/twinfra/host-hardening/ssh.json').exists())

    def test_ssh_exact_dropin_and_failed_key_probe_blocks_apply(self):
        self.assertEqual(host.ssh_config(),'PasswordAuthentication no\nKbdInteractiveAuthentication no\nPermitRootLogin no\n')
        ssh=HostSSH(fail_probe=1)
        with self.assertRaisesRegex(ValueError,'Key-login'):host.execute('host-ssh',ssh,apply=True)
        self.assertEqual(ssh.calls,[(['true'],None)])

    def test_firewall_scope_and_no_global_flush(self):
        rules=host.firewall()
        self.assertNotIn('flush ruleset',rules)
        statements=[l.strip() for l in rules.splitlines() if l.strip().startswith('iifname')]
        self.assertEqual(len(statements),6)
        self.assertTrue(all(l.startswith('iifname "eno1"') for l in statements))
        self.assertIn('ip saddr 192.168.1.0/24 tcp dport { 22, 6443 }',rules)
        self.assertNotIn('cilium_',rules);self.assertNotIn('lxc',rules)
        self.assertIn('policy accept',rules)
        self.assertNotIn('hook forward',rules);self.assertNotIn('chain forward',rules)
        self.assertIn('hook prerouting priority -150',rules)
        profile=yaml.safe_load((ROOT/'vcloud-ssot.yaml').read_text())['environments']['dev']
        self.assertEqual(statements[-1],'iifname "eno1" ip daddr { '+profile['podCidr']+', '+profile['serviceCidr']+' } ct state new drop')
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);ssot={'environments':{'dev':profile|{'podCidr':'10.112.0.0/16','serviceCidr':'10.113.0.0/16'}}}
            (root/'vcloud-ssot.yaml').write_text(yaml.safe_dump(ssot))
            with patch.object(host,'ROOT',root):changed=host.firewall()
            self.assertIn('ip daddr { 10.112.0.0/16, 10.113.0.0/16 } ct state new drop',changed)
            self.assertNotIn(profile['podCidr'],changed);self.assertNotIn(profile['serviceCidr'],changed)

    def test_rollback_armed_before_load_and_only_fresh_login_cancels(self):
        with tempfile.TemporaryDirectory() as tmp:
            calls=[]
            def command(cmd,**kwargs):
                calls.append(cmd)
                if cmd[:2]==['systemctl','is-enabled']:return subprocess.CompletedProcess(cmd,1,'disabled\n','')
                if cmd[:2]==['systemctl','is-active']:return subprocess.CompletedProcess(cmd,3,'inactive\n','')
                if cmd[:3]==['nft','list','table']:return subprocess.CompletedProcess(cmd,1,'','')
                return subprocess.CompletedProcess(cmd,0,'','')
            with patch.object(agent,'ROOT',Path(tmp)),patch.object(agent,'secure'),patch.object(agent,'command',side_effect=command):
                agent.firewall_apply({'rules':host.firewall(),'unit':host.firewall_unit()})
            timer=next(i for i,c in enumerate(calls) if c[0]=='systemd-run')
            load=next(i for i,c in enumerate(calls) if c[:2]==['nft','-f'])
            self.assertLess(timer,load);self.assertIn('--on-active=120',calls[timer])
            self.assertFalse(any(c==['systemctl','enable','nftables.service'] for c in calls))
            self.assertNotIn(['systemctl','enable','twinfra-host-firewall.service'],calls)
            self.assertIn('/usr/bin/systemctl disable twinfra-host-firewall.service',calls[timer][-1])
            self.assertTrue(calls[timer][-1].startswith('/usr/sbin/nft delete table inet twinfra_host;'))
        ssh=HostSSH(fail_probe=2)
        with self.assertRaisesRegex(ValueError,'Key-login'):host.execute('host-firewall',ssh,apply=True)
        self.assertNotIn('firewall-confirm',[json.loads(c[-1])['action'] for c,p in ssh.calls if c[0]=='sudo'])
        ssh=HostSSH();host.execute('host-firewall',ssh,apply=True)
        self.assertEqual(ssh.probes,2)

    def test_firewall_confirm_enables_only_after_timer_cancel(self):
        rollback='twinfra-firewall-rollback-'+'a'*32
        calls=[]
        def command(cmd,**kw):
            calls.append(cmd);return subprocess.CompletedProcess(cmd,0,'0\n' if 'show' in cmd else '','')
        with patch.object(agent,'command',side_effect=command):
            self.assertEqual(agent.dispatch(host.expected()|{'action':'firewall-confirm','rollback':rollback})['status'],'passed')
        self.assertEqual(calls[0],['systemctl','stop',rollback+'.timer'])
        self.assertEqual(calls[-1],['systemctl','enable','twinfra-host-firewall.service'])
        with patch.object(agent,'run',return_value=''),patch.object(agent,'command',return_value=subprocess.CompletedProcess([],0,'123\n','')):
            with self.assertRaisesRegex(ValueError,'already ran'):
                agent.dispatch(host.expected()|{'action':'firewall-confirm','rollback':rollback})

    def test_rollback_deletes_owned_table_and_disables_service_on_delete_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            calls=[]
            def command(cmd,**kw):
                calls.append(cmd)
                return subprocess.CompletedProcess(cmd,1 if cmd[0] in ('nft','systemctl') and cmd[1] in ('list','is-active','is-enabled') else 0,'disabled\n' if 'is-enabled' in cmd else '','')
            with patch.object(agent,'ROOT',Path(tmp)),patch.object(agent,'secure'),patch.object(agent,'command',side_effect=command):
                agent.firewall_apply({'rules':host.firewall(),'unit':host.firewall_unit()})
            rollback=next(c[-1] for c in calls if c[0]=='systemd-run')
            # Exercise the emitted shell flow with fake commands only: persistence
            # must be disabled whether deletion succeeds or the table is gone.
            script=rollback.replace('/usr/sbin/nft','fake_nft').replace('/usr/bin/systemctl','fake_systemctl')
            self.assertNotIn('/usr/sbin/nft',script);self.assertNotIn('/usr/bin/systemctl',script)
            for deletion_exit in (0,1):
                functions='fake_nft() { printf "nft:%s\\n" "$*"; return '+str(deletion_exit)+'; }; fake_systemctl() { printf "systemctl:%s\\n" "$*"; }; '
                result=subprocess.run([os.environ.get('BASH_BINARY','bash'),'-c',functions+script],capture_output=True,text=True,timeout=10)
                self.assertEqual(result.returncode,0,result.stderr)
                self.assertEqual(result.stdout.splitlines(),['nft:delete table inet twinfra_host','systemctl:disable twinfra-host-firewall.service'])

    def test_storage_no_adoption_reserve_and_owned_rerun(self):
        state={'lvExists':False,'directoryExists':False,'vgFreeBytes':40*agent.GIB}
        self.assertEqual(agent.storage_plan(state),'create')
        for change in ({'lvExists':True},{'directoryExists':True},{'vgFreeBytes':40*agent.GIB-1},{'symlink':True}):
            with self.assertRaises(ValueError):agent.storage_plan(state|change)
        uuid='11111111-1111-1111-1111-111111111111'
        state.update(lvExists=True,directoryExists=True,lvBytes=20*agent.GIB,uuid=uuid,
            marker={'owner':'WO-31 twinfra-dev-cairo-1','bytes':20*agent.GIB,'uuid':uuid})
        self.assertEqual(agent.storage_plan(state),'verify')
        with self.assertRaises(ValueError):agent.storage_plan(state|{'uuid':'foreign'})

    def test_storage_fstab_mount_and_kubelet_dependency(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);calls=[];uuid='11111111-1111-1111-1111-111111111111'
            def command(cmd,**kwargs):
                calls.append(cmd);out='';code=0
                if cmd[0]=='vgs':out=json.dumps({'report':[{'vg':[{'vg_free':str(60*agent.GIB)}]}]})
                elif cmd[0]=='lvs':out=json.dumps({'report':[{'lv':[]}]})
                elif cmd[0]=='blkid':out=uuid+'\n'
                elif cmd[0]=='findmnt':
                    if '--bytes' in cmd:code=1
                    else:out=uuid+' ext4 rw,nodev,nosuid,noexec,noatime\n'
                return subprocess.CompletedProcess(cmd,code,out,'')
            with patch.object(agent,'ROOT',root),patch.object(agent,'secure'),patch.object(agent,'command',side_effect=command),patch.object(agent.os,'chown',create=True) as chown:
                self.assertEqual(agent.storage_apply()['status'],'passed')
            self.assertIn(['lvcreate','--yes','--size','20G','--name','twinfra-postgres-1','ubuntu-vg'],calls)
            self.assertIn('ext4 nodev,nosuid,noexec,noatime,nofail,x-systemd.device-timeout=30s 0 2',(root/'etc/fstab').read_text())
            self.assertIn('RequiresMountsFor=/var/lib/twinfra/local-pv/postgres-1',(root/'etc/systemd/system/kubelet.service.d/20-twinfra-storage.conf').read_text())
            chown.assert_called_once_with(root/'var/lib/twinfra/local-pv/postgres-1',26,26)


class PinsAndProfiles(unittest.TestCase):
    def test_shared_log_helper_guard_and_exact_limits(self):
        raw=(ROOT/'deploy/common/dev-log-caps.sh').read_text()
        self.assertIn('dev-cairo-1',raw);self.assertIn('dev-cairo-2',raw)
        self.assertLess(raw.index('Log caps are dev-only'),raw.index('python3 -'))
        for limit in ('SystemMaxUse=500M',"('containerLogMaxSize','10Mi')","('containerLogMaxFiles','3')"):
            self.assertIn(limit,raw)

    def test_bootstrap_pins_cache_and_rejects_unpinned_inspection(self):
        item=locked();ctr=FakeCtr(ignore_pin=True)
        with patch.object(stager.time,'sleep'):
            with self.assertRaisesRegex(ValueError,'unpinned'):stager.stage({'images':{'sample':item}},runner=ctr)
        self.assertTrue(any('io.cri-containerd.pinned=pinned' in c for c in ctr.commands))
        ctr=FakeCtr({item['canonical']:item['digest']},pinned=[])
        self.assertEqual(stager.stage({'images':{'sample':item}},check=True,runner=ctr)[0]['reason'],'unpinned')
        self.assertEqual(stager.stage({'images':{'sample':item}},runner=ctr),[])
        self.assertFalse(any(c[0]=='ctr' and c[4]=='pull' for c in ctr.commands))

    def test_application_pins_existing_cache_without_pull(self):
        lock=json.loads((dev.COMMON/'images.lock.json').read_text());state={i['canonical']:i['digest'] for i in lock['images'].values()}
        ctr=FakeCtr(state,pinned=[]);ssh=FakeSSH(ctr)
        self.assertEqual(images.stage_applications('twinfra-dev-cairo-1','operator@192.168.1.3',transport=ssh)['problems'],[])
        self.assertTrue(all(i['canonical'] in ctr.pinned for i in lock['images'].values()))

    def test_profile_and_protected_ranges(self):
        row=yaml.safe_load((ROOT/'vcloud-ssot.yaml').read_text())['addressPlan'][0]
        raw=dev.host_environment(row)
        for value in ('NODE_IP=192.168.1.3','NODE_INTERFACE=eno1','PLATFORM_PROFILE=dev-cairo-1','IMAGE_STAGING=true',
            'NODE_NAME=twinfra-dev-cairo-1',
            'POD_CIDR=10.110.0.0/16','SERVICE_CIDR=10.111.0.0/16','CONTROL_PLANE_ENDPOINT=api.dev.cairo-1.twinfra.example.com:6443'):
            self.assertIn(value,raw)
        self.assertEqual(host.expected()['node'],yaml.safe_load((ROOT/'vcloud-ssot.yaml').read_text())['environments']['dev']['context'])
        pv=next(o for o in dev.database() if o['kind']=='PersistentVolume')
        self.assertEqual(pv['spec']['nodeAffinity']['required']['nodeSelectorTerms'][0]['matchExpressions'][0]['values'],['twinfra-dev-cairo-1'])
        for field in ('podCidr','serviceCidr'):
            for cidr in ('192.168.1.0/24','10.20.0.0/24','10.50.0.0/24'):
                with self.assertRaisesRegex(ValueError,'overlap'):dev.host_environment(row|{field:cidr})
        with self.assertRaises(ValueError):dev.seed(row)
        self.assertFalse((dev.TARGET/'seed').exists())

    def test_masked_byte_comparisons_against_main(self):
        def base(name):return subprocess.check_output(['git','-C',str(ROOT),'show',MAIN+':'+name])
        self.assertEqual(mask_bpffs_script((ROOT/'00-setup-ubuntu-host.sh').read_text()),mask_bpffs_script(base('00-setup-ubuntu-host.sh').decode()))
        self.assertEqual((ROOT/'host.env.example').read_bytes().replace(b'\r\n',b'\n'),base('host.env.example'))
        production_base=lambda name:subprocess.check_output(['git','-C',str(ROOT),'show',AMENDMENT_2_BASE+':'+name])
        def production_mask(raw,remote=False):
            raw=raw.decode().replace('\r\n','\n')
            raw=re.sub(r'(?m)^# Generated; script SHA256=[a-f0-9]{64}\.$','# Generated; script SHA256=@@DERIVED@@.',raw)
            if remote:
                return re.sub(r"(?m)^(      expected=')[a-f0-9]{64}('$)",r'\1@@DERIVED@@\2',raw)
            data=yaml.safe_load(raw)
            embedded=next(f['content'] for f in data['write_files'] if f['path']=='/usr/local/sbin/00-setup-ubuntu-host.sh')
            literal='\n'.join('      '+line if line else '' for line in embedded.rstrip('\n').split('\n'))
            self.assertEqual(raw.count(literal),1)
            masked=mask_bpffs_script(embedded)
            replacement='\n'.join('      '+line if line else '' for line in masked.rstrip('\n').split('\n'))
            return raw.replace(literal,replacement,1)
        for name in ('user-data.yaml','user-data-remote.yaml'):
            self.assertEqual(production_mask((ROOT/name).read_bytes(),name.endswith('remote.yaml')),production_mask(production_base(name),name.endswith('remote.yaml')),name)
            self.assertNotIn(b'containerLogMaxSize: 10Mi',base(name))
        self.assertEqual(gzip.decompress((ROOT/'user-data.yaml.gz').read_bytes()),(ROOT/'user-data.yaml').read_bytes())
        self.assertEqual(production_mask(gzip.decompress((ROOT/'user-data.yaml.gz').read_bytes())),production_mask(gzip.decompress(production_base('user-data.yaml.gz'))))
        path='deploy/environments/dev/cairo-2/seed/user-data'
        def mask(raw):
            raw=raw.replace(b'\r\n',b'\n')
            # Check every inner non-BPF byte before masking its YAML serialization.
            data=yaml.safe_load(raw)
            embedded=next(f['content'] for f in data['write_files'] if f['path']=='/usr/local/sbin/00-setup-ubuntu-host.sh')
            self.assertEqual(mask_bpffs_script(embedded),mask_bpffs_script(base('00-setup-ubuntu-host.sh').decode()))
            raw,count=re.subn(rb'(?ms)(^- path: /usr/local/sbin/00-setup-ubuntu-host.sh\n  owner: root:root\n  permissions: [^\n]+\n  content: ).*?(?=^- path:|^[A-Za-z_][A-Za-z_]*:)',rb'\1@@SHARED_BPFFS_SCRIPT@@\n',raw)
            self.assertEqual(count,1)
            # Preserve path/permissions, mask only the existing agent content value.
            raw,count=re.subn(rb'(?ms)(^- path: /usr/local/lib/twinfra/stage-images.py\n  permissions: [^\n]+\n  content: ).*?(?=^- path:|^[A-Za-z_][A-Za-z_]*:)',rb'\1@@SHARED_AGENT@@\n',raw)
            self.assertEqual(count,1)
            for name in (b'/usr/local/lib/twinfra/dev-log-caps.sh',b'/etc/systemd/journald.conf.d/10-twinfra-dev.conf',b'/etc/systemd/system/twinfra-dev-log-caps.service'):
                raw=re.sub(rb'(?ms)^- path: '+re.escape(name)+rb'\n.*?(?=^- path:|^[A-Za-z_][A-Za-z_]*:)',b'',raw)
            raw=raw.replace(b'- - systemctl\n  - enable\n  - --now\n  - twinfra-dev-log-caps.service\n',b'')
            return raw
        self.assertEqual(mask((ROOT/path).read_bytes()),mask(base(path)))
        for name in ('meta-data','network-config'):
            path='deploy/environments/dev/cairo-2/seed/'+name
            self.assertEqual((ROOT/path).read_bytes().replace(b'\r\n',b'\n'),base(path))

    def test_amendment_2_changes_only_approved_blocks_against_current_main(self):
        base=lambda name:subprocess.check_output(['git','-C',str(ROOT),'show',AMENDMENT_2_BASE+':'+name]).decode()
        current=(ROOT/'00-setup-ubuntu-host.sh').read_text()
        self.assertEqual(mask_bpffs_script(current),mask_bpffs_script(base('00-setup-ubuntu-host.sh')))
        self.assertNotEqual(current,base('00-setup-ubuntu-host.sh'))
        for name in ('host.env.example','deploy/environments/dev/cairo-1/host.env',
                     'deploy/environments/dev/cairo-2/seed/network-config','deploy/environments/dev/cairo-2/seed/meta-data'):
            self.assertEqual((ROOT/name).read_text(),base(name))

    def test_amendment_2_licence_evidence_preserves_policy_and_expiry(self):
        name='security/licence-baseline.json'
        baseline=json.loads(subprocess.check_output(['git','-C',str(ROOT),'show',AMENDMENT_2_BASE+':'+name]))
        current=json.loads((ROOT/name).read_text())
        before=next(f for f in baseline['findings'] if f['id']=='image-digest:00-setup-ubuntu-host.sh')
        after=next(f for f in current['findings'] if f['id']==before['id'])
        expected=hashlib.sha256((ROOT/'00-setup-ubuntu-host.sh').read_bytes().replace(b'\r\n',b'\n')).hexdigest()
        self.assertEqual(after['fingerprint'],expected)
        before['fingerprint']=after['fingerprint'];before['reason']=after['reason']
        self.assertEqual(current,baseline)
        for frozen in ('security/licence-register.json','security/licence-policy.json','tools/ci/pr-baselines.json'):
            self.assertEqual((ROOT/frozen).read_bytes().replace(b'\r\n',b'\n'),subprocess.check_output(['git','-C',str(ROOT),'show',AMENDMENT_2_BASE+':'+frozen]))


    def test_amendment_3_changes_only_cairo_2_embedded_staging_agent(self):
        def base(name):return subprocess.check_output(['git','-C',str(ROOT),'show',AMENDMENT_3_BASE+':'+name])
        for name in ('00-setup-ubuntu-host.sh','host.env.example','user-data.yaml','user-data-remote.yaml',
                     'deploy/common/images.lock.json','deploy/common/bootstrap-images.lock.json',
                     'deploy/environments/dev/cairo-1/host.env','deploy/environments/dev/cairo-2/seed/meta-data',
                     'deploy/environments/dev/cairo-2/seed/network-config','security/licence-baseline.json',
                     'security/licence-register.json','security/licence-policy.json','tools/ci/pr-baselines.json'):
            self.assertEqual((ROOT/name).read_bytes().replace(b'\r\n',b'\n'),base(name),name)
        self.assertEqual((ROOT/'user-data.yaml.gz').read_bytes(),base('user-data.yaml.gz'))
        path='deploy/environments/dev/cairo-2/seed/user-data'
        def mask(raw):
            raw=raw.replace(b'\r\n',b'\n')
            raw,count=re.subn(rb'(?ms)(^- path: /usr/local/lib/twinfra/stage-images.py\n  permissions: [^\n]+\n  content: ).*?(?=^- path:|^[A-Za-z_][A-Za-z_]*:)',rb'\1@@AMENDMENT_3_AGENT@@\n',raw)
            self.assertEqual(count,1)
            return raw
        current=(ROOT/path).read_bytes();self.assertNotEqual(current.replace(b'\r\n',b'\n'),base(path))
        self.assertEqual(mask(current),mask(base(path)))
        data=yaml.safe_load(current)
        agent_code=next(f['content'] for f in data['write_files'] if f['path']=='/usr/local/lib/twinfra/stage-images.py')
        self.assertEqual(agent_code,(ROOT/'deploy/common/stage-images.py').read_text())


if __name__=='__main__':unittest.main()
