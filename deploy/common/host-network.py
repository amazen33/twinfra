#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""WO-36 root-only, detached netplan transaction. Import performs no IO.

Only the three named files are changed. The worker retains netplan's stdin
pipe (not /dev/null) until an independently authenticated controller confirms.
"""
import base64
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import stat
import subprocess
import sys
import tempfile
import time
import uuid

ROOT=Path('/')
STATE_DIR='/var/lib/twinfra/host-network'
STATIC='/etc/netplan/60-twinfra-static.yaml'
CLOUD='/etc/cloud/cloud.cfg.d/99-twinfra-disable-network-config.cfg'
DHCP='/etc/netplan/50-cloud-init.yaml'
FILES=(STATIC,CLOUD,DHCP)
OWNER='WO-36 twinfra-dev-cairo-1'


def path(name):return ROOT/name.lstrip('/')


def secure(p):
    for item in (p,*p.parents):
        if item==ROOT.parent:break
        if item.is_symlink():raise ValueError('Linked network path refused')
        if item.exists() and (item.stat().st_uid!=0 or item.stat().st_mode & 0o022):
            raise ValueError('Unowned/insecure network path')


def write(name,raw):
    p=path(name);secure(p);p.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=p.parent,delete=False) as file:
        file.write(raw);candidate=file.name
    os.chmod(candidate,0o600);os.replace(candidate,p)


def load(name):
    p=path(name);secure(p)
    return json.loads(p.read_text()) if p.exists() else None


def save(name,data):write(name,(json.dumps(data,sort_keys=True)+'\n').encode())


def snapshot():
    found={}
    for name in FILES:
        p=path(name);secure(p)
        found[name]=None if not p.exists() else {'data':base64.b64encode(p.read_bytes()).decode(),'mode':stat.S_IMODE(p.stat().st_mode)}
    return found


def restore(files):
    if set(files)!=set(FILES):raise ValueError('Foreign network snapshot')
    for name,item in files.items():
        p=path(name);secure(p)
        if item is None:
            if p.exists():p.unlink()
        else:
            write(name,base64.b64decode(item['data'],validate=True));os.chmod(p,item['mode'])


def run(args):
    result=subprocess.run(args,capture_output=True,text=True,timeout=15)
    if result.returncode:raise ValueError('Network verification command failed: '+args[0])
    return result.stdout


def effective(data):
    addr=json.loads(run(['ip','-j','-4','address','show','dev','eno1']))
    # ip -4 address omits link-layer fields; query the MAC independently.
    links=json.loads(run(['ip','-j','link','show','dev','eno1']))
    routes=json.loads(run(['ip','-j','-4','route','show','default','dev','eno1']))
    dns=run(['resolvectl','dns','eno1']).strip().split(':',1)[-1].split()
    nodes=json.loads(run(['kubectl','--kubeconfig','/etc/kubernetes/admin.conf','--request-timeout=5s','get','nodes','-o','json']))['items']
    node=[n for n in nodes if n['metadata']['name']==data['node']]
    internal=[a['address'] for n in node for a in n['status']['addresses'] if a['type']=='InternalIP']
    addresses=[a for iface in addr for a in iface['addr_info'] if a.get('family')=='inet' and a['local']==data['ip']]
    return {'address':data['ip'],'present':len(addresses)==1,
        'static':len(addresses)==1 and not addresses[0].get('dynamic',False) and 'dynamic' not in addresses[0].get('flags',[]),
        'prefixLength':addresses[0]['prefixlen'] if addresses else None,
        'mac':links[0].get('address') if len(links)==1 else None,
        'gateways':[r.get('gateway') for r in routes],'dns':dns,'nodeInternalIP':internal}


def matches(info,data,mode='apply',baseline=None):
    good=info['present'] and info['mac']==data['mac'] and info['nodeInternalIP']==[data['ip']]
    if mode=='apply':
        return good and info['static'] and info['prefixLength']==24 and info['gateways']==[data['gateway']] and info['dns']==data['dns']
    return good and info['gateways']==baseline['effective']['gateways'] and info['dns']==baseline['effective']['dns']


def owned():
    baseline=load(STATE_DIR+'/baseline.json');committed=load(STATE_DIR+'/committed.json')
    if baseline is None:
        if path(STATIC).exists() or path(CLOUD).exists():raise ValueError('Unowned network destination; no adoption')
        return None
    if baseline.get('owner')!=OWNER or set(baseline.get('files',{}))!=set(FILES):raise ValueError('Invalid network baseline ownership')
    backup=path(STATE_DIR+'/50-cloud-init.yaml');secure(backup)
    if not backup.is_file() or base64.b64encode(backup.read_bytes()).decode()!=baseline['files'][DHCP]['data']:
        raise ValueError('Saved DHCP copy differs')
    if committed:
        if committed.get('owner')!=OWNER or snapshot()!=committed.get('files'):raise ValueError('Owned network files differ; no adoption')
    elif snapshot()!=baseline['files']:
        raise ValueError('Incomplete network transaction; inspect journal and saved files locally')
    return baseline


def integrity():
    try:
        baseline=owned();committed=load(STATE_DIR+'/committed.json')
        if not baseline:return {'status':'WARN','detail':'Static network not yet owned; owner host-network apply pending'}
        if not committed:return {'status':'WARN','detail':'Saved DHCP verified; no accepted network transaction'}
        mode=committed['mode']
        return {'status':'PASS','detail':'Owned network files verified ('+mode+')'}
    except (ValueError,OSError,KeyError,TypeError):return {'status':'BLOCK','detail':'Owned network integrity verification failed'}


def check(data):
    info=effective(data);integrity_result=integrity()
    passed=matches(info,data) and integrity_result['status']=='PASS' and path(STATIC).is_file()
    return {'status':'passed' if passed else 'failed','mode':'static-check','network':info,'integrity':integrity_result}


@contextmanager
def lock(wait=False):
    import fcntl
    p=path('/run/twinfra-host-network.lock');secure(p)
    with p.open('a') as handle:
        try:fcntl.flock(handle,fcntl.LOCK_EX|(0 if wait else fcntl.LOCK_NB))
        except BlockingIOError:raise ValueError('Network transaction active; second run refused') from None
        yield


def state(data):
    name=data['unit']
    if not re.fullmatch(r'twinfra-network-[a-f0-9]{32}',name):raise ValueError('Foreign network unit')
    report=load(STATE_DIR+'/transaction.json')
    if not report or report.get('owner')!=OWNER or report.get('unit')!=name:raise ValueError('Network unit ownership mismatch')
    return report


def unit_active(unit):
    raw=run(['systemctl','show',unit,'--property=ActiveState','--value']).strip()
    return raw in ('active','activating','deactivating','reloading')


def start(data,source):
    with lock():
        if path('/run/netplan/netplan-try.ready').exists():raise ValueError('Another netplan try is active')
        previous=load(STATE_DIR+'/transaction.json')
        if previous and (previous.get('owner')!=OWNER or not re.fullmatch(r'twinfra-network-[a-f0-9]{32}',previous.get('unit',''))):
            raise ValueError('Foreign network transaction receipt')
        if previous and (unit_active(previous['unit']) or previous['status'] in ('running','awaiting-confirmation')):
            raise ValueError('Network transaction active or incomplete; second run refused')
        baseline=owned();mode=data['mode'];info=effective(data)
        if mode not in ('apply','rollback'):raise ValueError('Invalid network mode')
        if info['mac']!=data['mac'] or not info['present']:raise ValueError('Host NIC/address identity differs')
        if mode=='apply' and baseline and matches(info,data) and path(STATIC).is_file():return check(data)
        if not baseline:
            if mode=='rollback':raise ValueError('No saved owned DHCP configuration')
            before=snapshot()
            if before[DHCP] is None:raise ValueError('Missing 50-cloud-init.yaml; no DHCP configuration to preserve')
            baseline={'owner':OWNER,'files':before,'effective':info}
            write(STATE_DIR+'/50-cloud-init.yaml',base64.b64decode(before[DHCP]['data']))
            save(STATE_DIR+'/baseline.json',baseline)
        worker=path(STATE_DIR+'/worker.py');secure(worker)
        marker=load(STATE_DIR+'/worker.json')
        if worker.exists() and (not marker or hashlib.sha256(worker.read_bytes()).hexdigest()!=marker.get('sha256')):
            raise ValueError('Unowned network worker; no adoption')
        write(STATE_DIR+'/worker.py',source.encode());save(STATE_DIR+'/worker.json',{'sha256':hashlib.sha256(source.encode()).hexdigest()})
        unit='twinfra-network-'+uuid.uuid4().hex
        report={'owner':OWNER,'unit':unit,'mode':mode,'status':'running','before':snapshot(),'data':data}
        save(STATE_DIR+'/transaction.json',report)
        try:
            run(['systemd-run','--unit='+unit,'--no-block','--property=Type=oneshot',
                 '--property=TimeoutStartSec=infinity','--property=RuntimeMaxSec=infinity',
                 '--property=StandardOutput=journal','--property=StandardError=journal',
                 '/usr/bin/python3',STATE_DIR+'/worker.py',unit])
        except Exception:
            report['status']='failed';save(STATE_DIR+'/transaction.json',report);raise
        return public(report)


def public(report):
    return {k:report[k] for k in ('status','mode','unit','recoveryRequired') if k in report}|{'message':'Logs: journalctl -u '+report['unit']}


def poll(data):
    report=state(data)
    if report['status'] in ('running','awaiting-confirmation') and not unit_active(report['unit']):
        return public(report)|{'status':'failed','message':'Network unit exited unexpectedly; inspect journal and saved files locally'}
    if report['status']=='passed':
        if unit_active(report['unit']):return public(report)|{'status':'running'}
        if run(['systemctl','show',report['unit'],'--property=ExecMainStatus','--value']).strip()!='0':
            return public(report)|{'status':'failed','message':'Network unit exit code did not confirm success; inspect journal'}
    return public(report)


def confirm(data):
    report=state(data)
    if report['status']!='awaiting-confirmation' or time.monotonic()-report['readyAt']>90 or not unit_active(report['unit']):
        raise ValueError('Network confirmation window closed')
    if snapshot()!=report.get('candidate'):raise ValueError('Candidate network files changed; confirmation refused')
    if not matches(effective(data),data,report['mode'],load(STATE_DIR+'/baseline.json')):raise ValueError('Applied network verification failed; confirmation refused')
    # This request itself arrived over a new key-only SSH connection. Verify TLS
    # and the existing kubeadm identity; never disable CA/hostname verification.
    if run(['kubectl','--kubeconfig','/etc/kubernetes/admin.conf','--server=https://192.168.1.3:6443',
            '--insecure-skip-tls-verify=false','--request-timeout=5s','get','--raw=/readyz']).strip()!='ok':raise ValueError('HTTPS API readiness failed; confirmation refused')
    save(STATE_DIR+'/confirm.json',{'unit':report['unit']})
    return public(report)|{'status':'running'}


def worker(unit):
    with lock(wait=True):
        report=state({'unit':unit});data=report['data'];baseline=load(STATE_DIR+'/baseline.json')
        if report['status']!='running':raise ValueError('Network worker replay refused')
        child=None;accepted=False
        try:
            if report['mode']=='apply':
                write(STATIC,data['config'].encode());write(CLOUD,b'network: {config: disabled}\n')
                path(DHCP).unlink()  # exact saved copy remains in the owned directory
            else:restore(baseline['files'])
            report['candidate']=snapshot();save(STATE_DIR+'/transaction.json',report)
            ready=path('/run/netplan/netplan-try.ready');secure(ready)
            if ready.exists():raise ValueError('Another netplan try is active')
            # A live pipe is essential: /dev/null makes netplan's select loop
            # see EOF immediately and can exhaust its timeout without waiting.
            with tempfile.TemporaryFile(mode='w+') as output:
                child=subprocess.Popen(['netplan','try','--timeout','120'],stdin=subprocess.PIPE,stdout=output,stderr=output,
                    text=True,env=dict(os.environ,LC_ALL='C'))
                began=time.monotonic();sent=False
                while child.poll() is None:
                    now=time.monotonic()
                    if ready.exists() and report['status']=='running':
                        report.update(status='awaiting-confirmation',readyAt=now);save(STATE_DIR+'/transaction.json',report)
                    confirm_data=load(STATE_DIR+'/confirm.json')
                    if not sent and report['status']=='awaiting-confirmation' and now-report['readyAt']<95 and confirm_data=={'unit':unit}:
                        child.stdin.write('\n');child.stdin.flush();sent=True
                    if now-began>150:
                        child.send_signal(signal.SIGINT);child.wait(timeout=30);break
                    time.sleep(0.5)
                child.wait(timeout=5);output.seek(0)
                # netplan can return 0 after reverting! Require its explicit
                # acceptance acknowledgement as well as exit code and checks.
                accepted=sent and child.returncode==0 and 'Configuration accepted.' in output.read()
            if not accepted or snapshot()!=report['candidate'] or not matches(effective(data),data,report['mode'],baseline):raise ValueError('Netplan did not accept verified configuration')
            save(STATE_DIR+'/committed.json',{'owner':OWNER,'mode':report['mode'],'files':snapshot()})
            report['status']='passed'
        except Exception:
            if child and child.poll() is None:
                try:child.send_signal(signal.SIGINT);child.wait(timeout=30)
                except (OSError,subprocess.TimeoutExpired):report['recoveryRequired']=True
            # netplan try restores runtime on refusal/timeout; also restore the
            # exact files on disk so reboot cannot apply an unconfirmed change.
            # After explicit acceptance a later verification failure is surfaced
            # for local recovery rather than falsely claiming runtime rollback.
            if not accepted:restore(report['before'])
            report['status']='failed'
        finally:
            save(STATE_DIR+'/transaction.json',report)
            print(json.dumps(public(report)),flush=True)
    return 0 if report['status']=='passed' else 1


if __name__=='__main__':
    if os.geteuid()!=0:raise SystemExit('Network worker requires root')
    raise SystemExit(worker(sys.argv[1]))
