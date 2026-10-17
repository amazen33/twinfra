#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""WO-31 owner-only SSH agent. No action at import; fixture-injectable IO."""
import hashlib
from contextlib import contextmanager
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import tempfile
import uuid

ROOT=Path('/')
GIB=1024**3
PORTS={6443:'kube-apiserver',2379:'etcd',2380:'etcd',10250:'kubelet'}
BOOTSTRAP_FILES={'host.env','00-setup-ubuntu-host.sh','bootstrap-images.lock.json','stage-images.py','dev-log-caps.sh'}


def at(name):return ROOT/name.lstrip('/')


def read(name, default=''):
    path=at(name)
    return path.read_text() if path.is_file() else default


def command(args, input_text=None, allowed=(0,)):
    result=subprocess.run(args,input=input_text,capture_output=True,text=True,timeout=900)
    if result.returncode not in allowed:raise ValueError('Host command failed: '+args[0])
    return result


def run(args):return command(args).stdout


def secure(path):
    if path.is_symlink() or path.exists() and (path.stat().st_uid!=0 or path.stat().st_mode & 0o022):
        raise ValueError('Unowned/insecure host path')
    for parent in path.parents:
        if parent==ROOT.parent:break
        if parent.is_symlink():raise ValueError('Linked host path refused')


def write(name, raw, mode=0o644):
    path=at(name);secure(path)
    if path.exists() and path.read_text()==raw:return False
    path.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent,delete=False) as file:
        file.write(raw.encode());candidate=file.name
    os.chmod(candidate,mode);os.replace(candidate,path)
    return True


def fields(raw):
    result={}
    for line in raw.splitlines():
        if '=' in line:
            key,value=line.split('=',1);result[key]=value.strip().strip('"')
    return result


def config_value(raw,key):
    found=re.findall(r'(?m)^'+key+r':\s*([^\r\n]+)',raw)
    return found[0].strip().strip('\"\'') if len(found)==1 else None


def inventory(expected):
    """All commands and file accesses here are read-only; stdout excludes secrets."""
    cpu=read('/proc/cpuinfo');mem=re.search(r'^MemTotal:\s+(\d+)',read('/proc/meminfo'),re.M)
    secureboot=at('/sys/firmware/efi/efivars/SecureBoot-8be4df61-93ca-11d2-aa0d-00e098032b8c')
    boot=secureboot.read_bytes() if secureboot.is_file() else b''
    addresses=json.loads(run(['ip','-j','-4','address','show','dev',expected['interface']]))
    vg=json.loads(run(['vgs','--reportformat','json','--units','b','--nosuffix','-o','vg_name,vg_free']))
    listener_text=run(['ss','-ltnpH']);listeners=[]
    for line in listener_text.splitlines():
        parts=line.split()
        if len(parts)<5:continue
        try:port=int(parts[3].rsplit(':',1)[1])
        except (ValueError,IndexError):continue
        if port in PORTS:listeners.append({'port':port,'owners':re.findall(r'"([^\"]+)",pid=\d+',line)})
    result_path=at('/var/lib/vcloud-host/result.json');result=None
    if result_path.exists():
        secure(result_path);result=json.loads(result_path.read_text())
    settings=run(['sshd','-T'])
    # Only three effective SSH values are reported. Never expose key material.
    ssh={line.split()[0]:line.split()[1] for line in settings.splitlines()
         if line.split() and line.split()[0] in ('passwordauthentication','kbdinteractiveauthentication','permitrootlogin')}
    admin=at('/etc/kubernetes/admin.conf');secure(admin)
    state={'os':fields(read('/etc/os-release')),'architecture':run(['uname','-m']).strip(),
        'vtX':bool(re.search(r'\bvmx\b',cpu)),'kvm':at('/dev/kvm').exists(),
        'ramGiB':int(mem[1])/1024**2 if mem else 0,
        'rootFreeGiB':int(run(['df','-B1','--output=avail','/']).splitlines()[-1])/GIB,
        'vgFreeGiB':next((float(v['vg_free'])/GIB for v in vg['report'][0]['vg'] if v['vg_name']=='ubuntu-vg'),0),
        'swap':read('/proc/swaps').splitlines()[1:],
        'timeSynced':run(['timedatectl','show','-p','NTPSynchronized','--value']).strip()=='yes',
        'addresses':[a['local'] for iface in addresses for a in iface['addr_info'] if a.get('family')=='inet'],
        'secureBoot':len(boot)==5 and boot[4]==1,'lockdown':read('/sys/kernel/security/lockdown').strip(),
        'sshd':ssh,'listeners':listeners,'result':result,'adminConf':admin.is_file(),'cluster':{},'nodes':[]}
    if result and admin.is_file():
        cm=json.loads(run(['kubectl','--kubeconfig','/etc/kubernetes/admin.conf','-n','kube-system','get','configmap','kubeadm-config','-o','json']))
        raw=cm.get('data',{}).get('ClusterConfiguration','')
        state['cluster']={key:config_value(raw,key) for key in ('clusterName','controlPlaneEndpoint')}
        state['nodes']=json.loads(run(['kubectl','--kubeconfig','/etc/kubernetes/admin.conf','get','nodes','-o','json']))['items']
    return state


def evaluate(state, expected):
    checks=[]
    def add(name,passed,detail):checks.append({'name':name,'status':'PASS' if passed else 'BLOCK','detail':detail})
    add('OS',state['os'].get('ID')=='ubuntu' and state['os'].get('VERSION_ID')=='24.04',state['os'].get('PRETTY_NAME','unknown'))
    add('Architecture / VT-x / KVM',state['architecture']=='x86_64' and state['vtX'] and state['kvm'],state['architecture'])
    add('RAM',state['ramGiB']>=24,str(round(state['ramGiB'],1))+' GiB; need 24 GiB')
    add('Root and VG free space',state['rootFreeGiB']>=20 and state['vgFreeGiB']>=20,
        str(round(state['rootFreeGiB'],1))+' GiB root / '+str(round(state['vgFreeGiB'],1))+' GiB VG')
    add('Time sync',state['timeSynced'],'synchronized' if state['timeSynced'] else 'not synchronized')
    add('eno1 address',expected['ip'] in state['addresses'],', '.join(state['addresses']))
    add('Secure Boot / lockdown',state['secureBoot'] and '[integrity]' in state['lockdown'],state['lockdown'])
    checks.append({'name':'Swap','status':'WARN' if state['swap'] else 'PASS','detail':'active; shared bootstrap disables it' if state['swap'] else 'off'})
    checks.append({'name':'sshd effective settings','status':'INFO','detail':state['sshd']})
    if 'networkIntegrity' in state:
        checks.append({'name':'Owned network files',**state['networkIntegrity']})
        checks.extend(state['networkWarnings'])
    checks.extend(state.get('graphicsChecks',[]))
    result=state['result'];post=bool(result and result.get('status')=='ready')
    resume=bool(isinstance(result,dict) and isinstance(result.get('status'),str) and not post and state.get('adminConf'))
    mode='post-bootstrap' if post else 'resume' if resume else 'pre-bootstrap'
    if not post and not resume:
        free=not state['listeners'] and not state.get('adminConf')
        detail='admin.conf exists without a valid bootstrap result' if state.get('adminConf') else 'free' if free else 'occupied before verified bootstrap'
        add('Reserved ports',free,detail)
    else:
        ready=bool(state.get('adminConf'))
        if post:ready=ready and result.get('kubernetes')==expected['kubernetes'] and result.get('mirror_status')=='staged-verified'
        cluster=state['cluster']
        ready=ready and cluster.get('clusterName')==expected['context'] and cluster.get('controlPlaneEndpoint')==expected['endpoint']
        nodes=[n for n in state['nodes'] if n.get('metadata',{}).get('name')==expected['node']]
        ready=ready and len(nodes)==1 and [a['address'] for a in nodes[0]['status']['addresses'] if a['type']=='InternalIP']==[expected['ip']]
        if post and nodes:ready=ready and any(c.get('type')=='Ready' and c.get('status')=='True' for c in nodes[0]['status'].get('conditions',[]))
        for port,owner in PORTS.items():
            matches=[l for l in state['listeners'] if l['port']==port]
            ready=ready and bool(matches) and all(set(l['owners'])=={owner} for l in matches)
        detail='bootstrap-owned cluster, incomplete' if resume else 'bootstrap-owned cluster verified'
        add('Reserved ports / cluster ownership',bool(ready),detail if ready else 'bootstrap identity/version/listener verification failed')
    return {'status':'failed' if any(c['status']=='BLOCK' for c in checks) else 'passed','mode':mode,'checks':checks}


def network_agent():
    import types
    module=types.ModuleType('host_network')
    exec(NETWORK_SOURCE,module.__dict__)
    module.ROOT=ROOT
    return module


def graphics_agent():
    import types
    module=types.ModuleType('host_graphics')
    exec(GRAPHICS_SOURCE,module.__dict__)
    module.ROOT=ROOT
    return module


def network_warnings():
    """Since-boot journal counters and retained CRI restart attempts, no raw logs."""
    checks=[]
    try:
        result=command(['journalctl','-b','--no-pager','-o','json','--case-sensitive=no',
                        '--grep=eno1.*(lost carrier|link is down|DHCP.*lease lost|DHCP.*lost lease)'],allowed=(0,1))
        entries=[json.loads(line).get('MESSAGE','') for line in result.stdout.splitlines() if line.strip()]
        for name,pattern in [('eno1 carrier losses',r'lost carrier|link is down'),('eno1 DHCP lease losses',r'DHCP.*(?:lease lost|lost lease)')]:
            count=sum(bool(re.search(pattern,str(message),re.I)) for message in entries)
            checks.append({'name':name,'status':'WARN' if count else 'PASS','detail':{'since':'boot','count':count}})
    except (ValueError,OSError,subprocess.TimeoutExpired):
        checks.append({'name':'eno1 network loss counters','status':'WARN','detail':'Since-boot journal unavailable; not a host-check failure'})
    try:
        boot=int(re.search(r'^btime (\d+)$',read('/proc/stat'),re.M)[1])*10**9
        containers=json.loads(run(['crictl','--runtime-endpoint=unix:///run/containerd/containerd.sock','ps','-a','-o','json']))['containers']
        counts={name:0 for name in ('kube-apiserver','kube-controller-manager','kube-scheduler','etcd')}
        for container in containers:
            meta=container.get('metadata',{});name=meta.get('name');labels=container.get('labels',{})
            if name in counts and labels.get('io.kubernetes.pod.namespace')=='kube-system' and labels.get('io.kubernetes.pod.name','')==name+'-twinfra-dev-cairo-1':
                if int(container.get('createdAt',0))>=boot and int(meta.get('attempt',0))>0:counts[name]+=1
        checks.append({'name':'Control-plane static-pod restarts','status':'WARN' if any(counts.values()) else 'PASS',
                       'detail':{'since':'boot','retainedAttempts':counts,'coverage':'lower bound; CRI garbage collection may remove old attempts'}})
    except (ValueError,OSError,KeyError,TypeError,subprocess.TimeoutExpired):
        checks.append({'name':'Control-plane static-pod restarts','status':'WARN','detail':'Since-boot CRI history unavailable; not a host-check failure'})
    return checks


def owned_file(name,marker):
    path=at(name);receipt=at('/var/lib/twinfra/host-hardening/'+marker+'.json')
    secure(path);secure(receipt)
    if path.exists() and not receipt.exists():raise ValueError('Unowned host-hardening destination')
    if receipt.exists():
        old=json.loads(receipt.read_text())
        if old.get('path')!=name or not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest()!=old.get('sha256'):
            raise ValueError('Owned host-hardening file differs; no adoption')
    return receipt


def record(name,marker):
    write('/var/lib/twinfra/host-hardening/'+marker+'.json',json.dumps({'path':name,'sha256':hashlib.sha256(at(name).read_bytes()).hexdigest()})+'\n',0o600)


def ssh_harden(data):
    name='/etc/ssh/sshd_config.d/10-twinfra-hardening.conf';owned_file(name,'ssh')
    old=read(name);changed=write(name,data['config'])
    try:
        run(['sshd','-t'])
        if changed:run(['systemctl','reload','ssh'])
        settings=run(['sshd','-T'])
        for key in ('passwordauthentication','kbdinteractiveauthentication','permitrootlogin'):
            if not re.search(r'(?m)^'+key+r' no$',settings):raise ValueError('Effective sshd hardening did not match')
    except Exception:
        if old:write(name,old)
        elif changed:at(name).unlink()
        run(['systemctl','reload','ssh']);raise
    record(name,'ssh')
    return {'status':'passed','message':'Key login succeeded before apply; sshd -t / reload / -T passed'}


def firewall_apply(data):
    if command(['systemctl','is-enabled','nftables.service'],allowed=(0,1,3,4)).stdout.strip() not in ('disabled','masked','not-found',''):
        raise ValueError('Stock nftables.service enabled; owner must resolve it first')
    if command(['systemctl','is-active','nftables.service'],allowed=(0,1,3,4)).returncode==0:
        raise ValueError('Stock nftables.service active; owner must resolve it first')
    name='/etc/twinfra/host-firewall.nft';owned_file(name,'firewall')
    unit='/etc/systemd/system/twinfra-host-firewall.service';owned_file(unit,'firewall-unit')
    exists=command(['nft','list','table','inet','twinfra_host'],allowed=(0,1)).returncode==0
    if exists and not at('/var/lib/twinfra/host-hardening/firewall.json').exists():raise ValueError('Unowned firewall table')
    # Validate syntax before scheduling/loading. Only our file/table can change.
    write(name,data['rules']);write(unit,data['unit']);run(['nft','-c','-f',name])
    rollback='twinfra-firewall-rollback-'+uuid.uuid4().hex
    # Disable persistence even if deletion finds the owned table already gone.
    run(['systemd-run','--unit='+rollback,'--on-active=120','/bin/sh','-c',
         '/usr/sbin/nft delete table inet twinfra_host; /usr/bin/systemctl disable twinfra-host-firewall.service'])
    run(['nft','-f',name])
    record(name,'firewall');record(unit,'firewall-unit')
    run(['systemctl','daemon-reload'])
    return {'status':'passed','rollback':rollback,'message':'Rollback armed; fresh key connection required to cancel'}


def storage_plan(state):
    if state.get('symlink'):raise ValueError('Linked storage refused')
    if (state['lvExists'] or state['directoryExists']) and not state.get('marker'):
        raise ValueError('Existing unowned volume/directory; no adoption')
    if state.get('marker'):
        marker=state['marker']
        if marker.get('owner')!='WO-31 twinfra-dev-cairo-1' or marker.get('bytes')!=20*GIB or not re.fullmatch(r'[a-fA-F0-9-]{36}',marker.get('uuid','')):
            raise ValueError('Invalid storage ownership marker')
        if not state['lvExists'] or state.get('lvBytes')!=20*GIB or state.get('uuid')!=marker['uuid']:
            raise ValueError('Owned storage differs; no adoption')
        if state['vgFreeBytes']<20*GIB:raise ValueError('Volume group must retain 20 GiB free')
        return 'verify'
    if state['vgFreeBytes']-20*GIB<20*GIB:raise ValueError('Volume group must retain 20 GiB free')
    return 'create'


def storage_apply():
    mount='/var/lib/twinfra/local-pv/postgres-1';lv='/dev/ubuntu-vg/twinfra-postgres-1'
    marker_path='/var/lib/twinfra/host-hardening/storage.json'
    # A verified database mount is deliberately UID 26, not root. Root-owned
    # markers plus LV/UUID/mount checks establish its ownership; links never do.
    if at(mount).is_symlink() or any(parent.is_symlink() for parent in at(mount).parents):
        raise ValueError('Linked storage mount refused')
    secure(at(marker_path))
    vg=json.loads(run(['vgs','ubuntu-vg','--reportformat','json','--units','b','--nosuffix','-o','vg_free']))
    lvs=json.loads(run(['lvs','--reportformat','json','--units','b','--nosuffix','-o','vg_name,lv_name,lv_size']))['report'][0]['lv']
    matches=[x for x in lvs if x['vg_name']=='ubuntu-vg' and x['lv_name']=='twinfra-postgres-1']
    if len(matches)>1:raise ValueError('Duplicate storage volume')
    marker=json.loads(read(marker_path)) if at(marker_path).exists() else None
    found=run(['blkid','-s','UUID','-o','value',lv]).strip() if matches else ''
    state={'lvExists':bool(matches),'lvBytes':int(float(matches[0]['lv_size'])) if matches else 0,
        'directoryExists':at(mount).exists(),'marker':marker,'uuid':found,
        'vgFreeBytes':int(float(vg['report'][0]['vg'][0]['vg_free']))}
    decision=storage_plan(state)
    if decision=='create':
        run(['lvcreate','--yes','--size','20G','--name','twinfra-postgres-1','ubuntu-vg'])
        run(['mkfs.ext4',lv]);found=run(['blkid','-s','UUID','-o','value',lv]).strip()
        if not re.fullmatch(r'[a-fA-F0-9-]{36}',found):raise ValueError('Invalid ext4 UUID')
        write(marker_path,json.dumps({'owner':'WO-31 twinfra-dev-cairo-1','bytes':20*GIB,'uuid':found})+'\n',0o600)
    if not at(mount).exists():at(mount).mkdir(parents=True,exist_ok=False)
    fstab=read('/etc/fstab');line='UUID='+found+' '+mount+' ext4 nodev,nosuid,noexec,noatime,nofail,x-systemd.device-timeout=30s 0 2'
    entries=[row for row in fstab.splitlines() if not row.lstrip().startswith('#') and mount in row.split()]
    if entries and entries!=[line]:raise ValueError('Foreign fstab entry at owned mount')
    if not entries:write('/etc/fstab',fstab.rstrip()+'\n'+line+'\n')
    mounted=command(['findmnt','-n','-o','UUID,SIZE,FSTYPE,OPTIONS','--bytes','--mountpoint',mount],allowed=(0,1))
    if mounted.returncode:
        if any(at(mount).iterdir()):raise ValueError('Unmounted non-empty directory refused')
        run(['mount',mount])
    verified=run(['findmnt','-n','-o','UUID,FSTYPE,OPTIONS','--mountpoint',mount]).split()
    if len(verified)!=3 or verified[:2]!=[found,'ext4'] or not {'nodev','nosuid','noexec','noatime'}.issubset(verified[2].split(',')):
        raise ValueError('Storage mount identity/options do not match')
    permissions=at(mount).stat()
    if (permissions.st_uid,permissions.st_gid)!=(26,26):os.chown(at(mount),26,26)
    if stat.S_IMODE(permissions.st_mode)!=0o700:os.chmod(at(mount),0o700)
    changed=write('/etc/systemd/system/kubelet.service.d/20-twinfra-storage.conf','[Unit]\nRequiresMountsFor='+mount+'\n')
    if changed:run(['systemctl','daemon-reload'])
    return {'status':'passed','message':'20 GiB owned ext4 LV / UUID mount; 26:26 0700; kubelet mount dependency'}


def bootstrap_state(data):
    refuse_active_bootstrap()
    report=evaluate(inventory(data),data)
    report['ready']=False
    stage=at('/var/lib/twinfra/host-bootstrap')
    if report['status']=='passed' and report['mode']=='post-bootstrap' and stage.exists():
        secure(stage)
        receipt=stage/'receipt.json';secure(receipt)
        if not receipt.is_file() or json.loads(receipt.read_text())!=data['hashes']:raise ValueError('Unowned/different bootstrap staging')
        for name,sha in data['hashes'].items():
            path=stage/name;secure(path)
            if hashlib.sha256(path.read_bytes()).hexdigest()!=sha:raise ValueError('Bootstrap staged hash mismatch')
        for name,target in {'host.env':'/etc/twinfra-host.env','bootstrap-images.lock.json':'/etc/twinfra/bootstrap-images.lock.json',
            'stage-images.py':'/usr/local/lib/twinfra/stage-images.py','dev-log-caps.sh':'/usr/local/lib/twinfra/dev-log-caps.sh'}.items():
            path=at(target);secure(path)
            if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest()!=data['hashes'][name]:
                raise ValueError('Deployed bootstrap input differs')
        run(['env','VCLOUD_CONFIG_FILE=/etc/twinfra-host.env','bash',str(stage/'00-setup-ubuntu-host.sh'),'--validate'])
        completion=stage/'complete.json';secure(completion)
        report['ready']=completion.is_file() and json.loads(completion.read_text())==data['hashes']
        report['message']='Healthy owned bootstrap verified'+('; no changes' if report['ready'] else '; finishing dev post-bootstrap steps required')
    return report


def api_mapping(data):
    """Deliver the same local API mapping the NoCloud path already supplies."""
    name=data['endpoint'].split(':')[0];raw=read('/etc/hosts')
    matching=[line.split('#',1)[0].split() for line in raw.splitlines() if name in line.split('#',1)[0].split()[1:]]
    if matching and any(row[0]!=data['ip'] for row in matching):
        raise ValueError('Existing API hostname maps to a foreign address')
    if not matching:write('/etc/hosts',raw.rstrip()+'\n'+data['ip']+' '+name+'\n')


def bootstrap_apply(data):
    # Lock covers staging and unit creation, including simultaneous SSH clients.
    with bootstrap_lock():
        refuse_active_bootstrap()
        return bootstrap_start(data)


@contextmanager
def bootstrap_lock():
    import fcntl  # Ubuntu base OS; imported only during an owner action.
    path=at('/run/twinfra-bootstrap.lock');secure(path)
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('a') as lock:
        os.chmod(path,0o600)
        try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:raise ValueError('Bootstrap already starting or finishing; second run refused') from None
        try:yield
        finally:fcntl.flock(lock,fcntl.LOCK_UN)


def refuse_active_bootstrap():
    raw=run(['systemctl','list-units','--all','--type=service','--plain','--no-legend','twinfra-bootstrap-*.service'])
    for line in raw.splitlines():
        fields=line.split()
        if len(fields)<4:raise ValueError('Invalid bootstrap unit inventory')
        unit,_,active,sub=fields[:4]
        if active in ('activating','deactivating','reloading') or active=='active' and sub!='exited':
            raise ValueError('Bootstrap already active; second run refused. Logs: journalctl -u '+unit)


def bootstrap_status(data):
    unit=data['unit']
    if not re.fullmatch(r'twinfra-bootstrap-[a-f0-9]{32}',unit):raise ValueError('Foreign bootstrap unit')
    receipt=at('/var/lib/twinfra/host-bootstrap/unit.json');secure(receipt)
    if not receipt.is_file() or json.loads(receipt.read_text())!={'unit':unit,'hashes':data['hashes']}:
        raise ValueError('Unowned/different bootstrap unit')
    fields=dict(line.split('=',1) for line in run(['systemctl','show',unit+'.service',
        '--property=LoadState,ActiveState,SubState,ExecMainCode,ExecMainStatus,Result']).splitlines() if '=' in line)
    report={'unit':unit,'message':'Logs: journalctl -u '+unit+'.service',
            'activeState':fields.get('ActiveState'),'subState':fields.get('SubState')}
    if fields.get('LoadState')!='loaded':return report|{'status':'failed','message':'Bootstrap unit unavailable; '+report['message']}
    if fields.get('ActiveState') in ('activating','deactivating','reloading') or fields.get('ActiveState')=='active' and fields.get('SubState')!='exited':
        return report|{'status':'running'}
    # ExecMainCode=1 is CLD_EXITED. A signal or never-started process is failure,
    # even if ExecMainStatus happens to be zero.
    code=fields.get('ExecMainStatus')
    status='failed'
    if fields.get('ExecMainCode')=='1':
        if code=='0' and fields.get('Result')=='success':status='passed'
        elif code=='20':
            # A tool (notably argocd) can also return 20 for a generic failure.
            # Only the shared bootstrap's owned result can request a reboot.
            result=at('/var/lib/vcloud-host/result.json')
            try:
                secure(result)
                recorded=json.loads(result.read_text()) if result.is_file() else None
                if isinstance(recorded,dict) and recorded.get('status')=='reboot-required':
                    status='reboot-required'
            except (OSError,ValueError):
                pass  # Missing, invalid or unowned evidence remains failed, with journal guidance.
    report|={'status':status,'exitCode':int(code) if code and code.isdecimal() else None}
    if status=='reboot-required':report['message']='Shared bootstrap requests reboot; owner reboots and reruns. '+report['message']
    return report


def bootstrap_start(data):
    import pwd
    if not re.fullmatch(r'/tmp/twinfra-inputs\.[A-Za-z0-9]{8}',data['incoming']):raise ValueError('Unsafe staging path')
    incoming=at(data['incoming'])
    if incoming.is_symlink():raise ValueError('Unsafe staging path')
    if incoming.stat().st_uid!=pwd.getpwnam(data['operator']).pw_uid or stat.S_IMODE(incoming.stat().st_mode)!=0o700:
        raise ValueError('Unowned private upload directory')
    # Verify ALL input bytes before copying, sourcing configuration or running bootstrap.
    expected_names=BOOTSTRAP_FILES
    if set(data['hashes'])!=expected_names:raise ValueError('Unexpected bootstrap file inventory')
    for name,sha in data['hashes'].items():
        file=incoming/name
        if not file.is_file() or file.is_symlink() or hashlib.sha256(file.read_bytes()).hexdigest()!=sha:
            raise ValueError('Copied bootstrap input SHA256 mismatch')
    stage=at('/var/lib/twinfra/host-bootstrap');secure(stage)
    if stage.exists():
        receipt=stage/'receipt.json';secure(receipt)
        if not receipt.is_file():raise ValueError('Unowned bootstrap staging directory')
        previous=json.loads(receipt.read_text())
        if not isinstance(previous,dict) or set(previous)!=expected_names or any(not isinstance(sha,str) or not re.fullmatch(r'[a-f0-9]{64}',sha) for sha in previous.values()):
            raise ValueError('Invalid owned bootstrap receipt')
        for name,sha in previous.items():
            path=stage/name;secure(path)
            if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest()!=sha:
                raise ValueError('Previous bootstrap staged input differs from owned receipt')
        if previous!=data['hashes']:
            # Amendment 2 permits recovery of a failed first run, never upgrades.
            completion=stage/'complete.json'
            if completion.exists() or completion.is_symlink():raise ValueError('Completed bootstrap with different inputs; upgrades refused')
            refuse_active_bootstrap()
            result=at('/var/lib/vcloud-host/result.json');secure(result)
            if result.exists():
                if not result.is_file():raise ValueError('Invalid previous bootstrap result')
                status=json.loads(result.read_text())
                if not isinstance(status,dict) or not isinstance(status.get('status'),str):raise ValueError('Invalid previous bootstrap result')
                if status['status']=='ready':raise ValueError('Ready bootstrap with different inputs; upgrades refused')
    stage.mkdir(parents=True,exist_ok=True);os.chmod(stage,0o700)
    for name in expected_names:
        write('/var/lib/twinfra/host-bootstrap/'+name,(incoming/name).read_text(),0o600)
        if hashlib.sha256((stage/name).read_bytes()).hexdigest()!=data['hashes'][name]:raise ValueError('Installed bootstrap SHA256 mismatch')
    write('/var/lib/twinfra/host-bootstrap/receipt.json',json.dumps(data['hashes'])+'\n',0o600)
    write('/etc/twinfra-host.env',(stage/'host.env').read_text(),0o600)
    write('/etc/twinfra/bootstrap-images.lock.json',(stage/'bootstrap-images.lock.json').read_text())
    write('/usr/local/lib/twinfra/stage-images.py',(stage/'stage-images.py').read_text())
    write('/usr/local/lib/twinfra/dev-log-caps.sh',(stage/'dev-log-caps.sh').read_text(),0o755)
    api_mapping(data)
    healthy=evaluate(inventory(data),data)
    if healthy['status']!='passed':raise ValueError('Host checks failed before shared bootstrap')
    flag='--validate' if healthy['mode']=='post-bootstrap' else '--apply'
    unit='twinfra-bootstrap-'+uuid.uuid4().hex
    write('/var/lib/twinfra/host-bootstrap/unit.json',json.dumps({'unit':unit,'hashes':data['hashes']})+'\n',0o600)
    # No --wait/--pipe or runtime timeout: PID 1 owns the unchanged bootstrap.
    # RemainAfterExit retains its exit status for subsequent fresh SSH queries.
    run(['systemd-run','--unit='+unit,'--no-block','--property=Type=oneshot',
         '--property=RemainAfterExit=yes','--property=TimeoutStartSec=infinity',
         '--property=RuntimeMaxSec=infinity','--property=StandardOutput=journal','--property=StandardError=journal',
         '/usr/bin/env','VCLOUD_CONFIG_FILE=/etc/twinfra-host.env','/usr/bin/bash',str(stage/'00-setup-ubuntu-host.sh'),flag])
    return {'status':'running','unit':unit,'message':'Bootstrap detached. Logs: journalctl -u '+unit+'.service'}


def bootstrap_finish(data):
    with bootstrap_lock():
        report=bootstrap_status(data)
        if report['status']!='passed':return report
        return bootstrap_complete(data,report)


def bootstrap_complete(data,report):
    run(['/usr/local/lib/twinfra/dev-log-caps.sh'])
    run(['kubectl','--kubeconfig','/etc/kubernetes/admin.conf','label','node',data['node'],
         'topology.kubernetes.io/zone=cairo-1a','twinfra.io/environment=dev','twinfra.io/region=cairo-1','--overwrite'])
    graphics=None
    if re.search(r'(?m)^DISABLE_NOUVEAU=true$',read('/etc/twinfra-host.env')):
        graphics=graphics_agent().bootstrap()
    write('/var/lib/twinfra/host-bootstrap/complete.json',json.dumps(data['hashes'])+'\n',0o600)
    if graphics:return report|graphics
    return report|{'message':'Shared bootstrap, pinned staging and dev log caps completed. '+report['message']}


def dispatch(data):
    if data.get('context')!='twinfra-dev-cairo-1' or data.get('ip')!='192.168.1.3' or data.get('interface')!='eno1':
        raise ValueError('Unapproved host context')
    action=data['action']
    if action=='check':
        current=inventory(data)
        current.update(networkIntegrity=network_agent().integrity(),networkWarnings=network_warnings())
        current['graphicsChecks']=graphics_agent().health_checks()
        return evaluate(current,data)
    if action.startswith('graphics-'):
        identity=evaluate(inventory(data),data)
        if identity['status']!='passed' or identity['mode']!='post-bootstrap':
            raise ValueError('Graphics action requires identity-verified ready WO-31 host')
        module=graphics_agent()
        if action=='graphics-check':return module.check()
        if action in ('graphics-apply','graphics-rollback'):return module.change(action.removeprefix('graphics-'))
        raise ValueError('Unknown graphics action')
    if action.startswith('network-'):
        module=network_agent()
        if action=='network-status':return module.poll(data)
        identity=evaluate(inventory(data),data)
        if identity['status']!='passed' or identity['mode']!='post-bootstrap':
            raise ValueError('Network action requires identity-verified ready WO-31 host')
        if action=='network-check':return module.check(data)
        if action=='network-start':return module.start(data,NETWORK_SOURCE)
        if action=='network-confirm':return module.confirm(data)
        raise ValueError('Unknown network action')
    if action=='bootstrap-state':return bootstrap_state(data)
    if action=='bootstrap-preflight':
        code=BOOTSTRAP_SOURCE+'\nset -Eeuo pipefail\n'+data['environment']+'\nVCLOUD_CONFIG_FILE=/dev/null\nload_config\nvalidate_config\npreflight\n'
        command(['bash','-s'],input_text=code)
        return {'status':'passed','message':'Only unchanged Module -1 preflight ran; no file or runtime writes'}
    if action=='bootstrap':return bootstrap_apply(data)
    if action=='bootstrap-status':return bootstrap_status(data)
    if action=='bootstrap-finish':return bootstrap_finish(data)
    if action=='ssh':return ssh_harden(data)
    if action=='firewall':return firewall_apply(data)
    if action=='firewall-confirm':
        if not re.fullmatch(r'twinfra-firewall-rollback-[a-f0-9]{32}',data['rollback']):raise ValueError('Foreign rollback unit')
        run(['systemctl','stop',data['rollback']+'.timer'])
        # A timer that already fired cannot authorize persistent firewall state.
        if command(['systemctl','show',data['rollback']+'.service','--property=ExecMainStartTimestampMonotonic','--value'],allowed=(0,1,4)).stdout.strip() not in ('0',''):
            raise ValueError('Firewall rollback already ran; apply again after inspecting host state')
        run(['systemctl','enable','twinfra-host-firewall.service'])
        return {'status':'passed','message':'Fresh key login verified; rollback timer cancelled; owned firewall service enabled'}
    if action=='storage':return storage_apply()
    raise ValueError('Unknown host action')


def main():
    try:
        if os.geteuid()!=0:raise ValueError('Owner action requires sudo -n')
        report=dispatch(json.loads(sys.argv[1]))
    except ValueError as error:
        # These validation/command errors contain only public guard names, never
        # captured stderr, kubeconfigs, environment dumps or credential material.
        report={'status':'failed','message':str(error)}
    except (OSError,KeyError,subprocess.TimeoutExpired):
        # Secrets/raw command output never enter evidence.
        report={'status':'failed','message':'Host action refused or failed; inspect owned state locally before retrying'}
    print(json.dumps(report))
    # Keep failure reports readable by the client, which propagates their status.


if __name__=='__main__':main()
