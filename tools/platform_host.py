#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""WO-31 host inputs and explicit SSH actions. Import/render never connects."""
import hashlib
import json
from pathlib import Path
import re
import subprocess
import yaml
from platform_resources import ROOT
from platform_image_staging import SSH

TARGET=ROOT/'deploy/environments/dev/cairo-1'
COMMON=ROOT/'deploy/common'


def ssh_config():
    return 'PasswordAuthentication no\nKbdInteractiveAuthentication no\nPermitRootLogin no\n'


def firewall():
    # Atomic replacement of our own table only; never change foreign tables.
    rules='''        iifname "eno1" ct state established,related accept
        iifname "eno1" meta l4proto { icmp, ipv6-icmp } accept
        iifname "eno1" udp sport 67 udp dport 68 accept
        iifname "eno1" ip saddr 192.168.1.0/24 tcp dport { 22, 6443 } accept
        iifname "eno1" drop
'''
    return ('# WO-31: only the Dell physical interface is filtered.\n'
        'destroy table inet twinfra_host\ntable inet twinfra_host {\n'+
        ''.join('    chain '+name+' {\n        type filter hook '+name+' priority 10; policy accept;\n'+rules+'    }\n'
                for name in ('input','forward'))+'}\n')


def firewall_unit():
    return ('[Unit]\nDescription=Twinfra owned eno1 firewall\nAfter=network-pre.target\nBefore=network.target\n'
        '[Service]\nType=oneshot\nRemainAfterExit=yes\nExecStart=/usr/sbin/nft -f /etc/twinfra/host-firewall.nft\n'
        'ExecReload=/usr/sbin/nft -f /etc/twinfra/host-firewall.nft\n[Install]\nWantedBy=multi-user.target\n')


def expected():
    ssot=yaml.safe_load((ROOT/'vcloud-ssot.yaml').read_text())
    row=next(r for r in ssot['addressPlan'] if r['environment']=='dev' and r['region']=='cairo-1')
    if row.get('delivery')!='bare-metal' or row['ipAddress']!='192.168.1.3' or row.get('interface')!='eno1':
        raise ValueError('Unapproved WO-31 host profile')
    version=re.search(r'^KUBERNETES_VERSION=(\S+)',(TARGET/'host.env').read_text(),re.M)[1]
    return {'context':'twinfra-dev-cairo-1','node':'twinfra-node','ip':row['ipAddress'],'interface':row['interface'],
            'endpoint':'api.dev.cairo-1.twinfra.example.com:6443','kubernetes':version}


def request(ssh, action, **values):
    data=expected()|{'action':action}|values
    code=(COMMON/'host-admin.py').read_text()
    if action=='bootstrap-preflight':
        # Source the exact Module -1 helpers in memory; --check writes no files.
        code='BOOTSTRAP_SOURCE='+repr((ROOT/'00-setup-ubuntu-host.sh').read_text())+'\n'+code
    raw=ssh.run(['sudo','-n','python3','-',json.dumps(data,separators=(',',':'))],payload=code.encode())
    try:return json.loads(raw)
    except (ValueError,TypeError):raise ValueError('Host returned an invalid action report') from None


def bootstrap(ssh, check=False, copier=subprocess.run):
    files={'host.env':TARGET/'host.env','00-setup-ubuntu-host.sh':ROOT/'00-setup-ubuntu-host.sh',
        'bootstrap-images.lock.json':COMMON/'bootstrap-images.lock.json','stage-images.py':COMMON/'stage-images.py',
        'dev-log-caps.sh':COMMON/'dev-log-caps.sh'}
    hashes={name:hashlib.sha256(path.read_bytes()).hexdigest() for name,path in files.items()}
    state=request(ssh,'bootstrap-state',hashes=hashes)
    if state['status']!='passed':return state
    if check:return request(ssh,'bootstrap-preflight',environment=(TARGET/'host.env').read_text())
    if state['ready']:return state  # validated with the shared --validate; no transfer or writes
    incoming=ssh.run(['mktemp','-d','/tmp/twinfra-inputs.XXXXXXXX']).decode().strip()
    if not re.fullmatch(r'/tmp/twinfra-inputs\.[A-Za-z0-9]{8}',incoming):
        raise ValueError('Invalid private staging path')
    target=ssh.prefix[-1]
    options=ssh.prefix[2:-1]
    for name,path in files.items():
        result=copier(['scp',*options,'--',str(path),target+':'+incoming+'/'+name],capture_output=True,timeout=120)
        if result.returncode:raise ValueError('SCP failed; bootstrap was not run')
    return request(ssh,'bootstrap',incoming=incoming,operator=target.split('@')[0],hashes=hashes)


def execute(action, ssh, check=False, apply=False):
    if action=='host-bootstrap':return bootstrap(ssh,check)
    if action=='host-check':return request(ssh,'check')
    if action not in ('host-ssh','host-firewall','host-storage'):raise ValueError('Unknown host action')
    if not apply:return {'status':'planned','message':'Supply --apply for this owner-only mutation'}
    # Every apply requires a just-completed key-only connection. No multiplexed session.
    ssh.run(['true'])
    if action=='host-ssh':return request(ssh,'ssh',config=ssh_config())
    if action=='host-storage':return request(ssh,'storage')
    report=request(ssh,'firewall',rules=firewall(),unit=firewall_unit())
    # A failed fresh connection leaves the timer armed. Never cancel on error.
    ssh.run(['true'])
    return request(ssh,'firewall-confirm',rollback=report['rollback'])


def action(name, context, target, check=False, apply=False):
    if context!='twinfra-dev-cairo-1':raise ValueError('Use explicit --context twinfra-dev-cairo-1')
    report=execute(name,SSH(target,context),check,apply)
    print(json.dumps(report,indent=2))
    return 20 if report['status']=='reboot-required' else int(report['status']=='failed')
