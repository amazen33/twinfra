#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Real netplan proof on an expendable GitHub-hosted Ubuntu 24.04 VM ONLY.

Creates a dummy eno1, not a physical NIC. Protects the runner's original default
route in a separate routing table. Uses real SSH, TLS/kubectl, networkd, netplan
and the unmodified detached production worker. The Kubernetes Node/readyz API
is a fixture, not a cluster or a substitute for Dell acceptance.
"""
import argparse
import base64
import configparser
from datetime import datetime, timezone
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import importlib.util
import ipaddress
import json
import os
from pathlib import Path
import shlex
import shutil
import secrets
import ssl
import subprocess
import sys
import threading
import time

ROOT=Path(__file__).resolve().parents[2]
WORK=Path('/run/twinfra-network-ci')
TABLE='31236'
IP='192.168.1.3'


def run(args,**kwargs):
    return subprocess.run(args,check=True,capture_output=True,text=True,timeout=30,**kwargs).stdout.strip()


def guard():
    if os.environ.get('GITHUB_ACTIONS')!='true' or os.environ.get('RUNNER_ENVIRONMENT')!='github-hosted' or os.geteuid()!=0:
        raise ValueError('Disposable GitHub-hosted root runner required; never run on the Dell')
    release=Path('/etc/os-release').read_text()
    if 'VERSION_ID="24.04"' not in release or run(['systemd-detect-virt']) in ('none','wsl'):
        raise ValueError('Real Ubuntu 24.04 VM required')
    if Path('/sys/class/net/eno1').exists() or WORK.exists() or Path('/var/lib/twinfra').exists() or Path('/etc/kubernetes').exists():
        raise ValueError('Existing eno1 or Twinfra/Kubernetes state refused')
    routes=json.loads(run(['ip','-j','-4','route','show','table','all']))
    for route in routes:
        dst=route.get('dst','default')
        if dst!='default' and ipaddress.ip_network(dst,strict=False).overlaps(ipaddress.ip_network('192.168.1.0/24')):
            raise ValueError('Fixture subnet overlaps runner routing')
    table=subprocess.run(['ip','route','show','table',TABLE],capture_output=True,text=True,check=False)
    if table.stdout.strip() or table.returncode not in (0,2) or any(r.get('priority')==31236 for r in json.loads(run(['ip','-j','rule']))):
        raise ValueError('Fixture route table/rule already occupied')


class API(BaseHTTPRequestHandler):
    ready=True
    token=''
    def do_GET(self):
        if self.headers.get('Authorization')!='Bearer '+API.token:
            self.send_response(401);self.end_headers();return
        endpoint=self.path.partition('?')[0] # kubectl appends ?timeout=5s
        if endpoint=='/readyz':
            body=b'ok' if API.ready else b'not ready';status=200 if API.ready else 503
        elif endpoint=='/api/v1/nodes':
            body=json.dumps({'apiVersion':'v1','kind':'NodeList','items':[{'metadata':{'name':'twinfra-dev-cairo-1'},
                'status':{'addresses':[{'type':'InternalIP','address':IP}]}}]}).encode();status=200
        else:body=b'not found';status=404
        self.send_response(status);self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
    def log_message(self,*_):pass


def fixture_api():
    # Ephemeral server private key is tmpfs-only and never an artifact.
    run(['openssl','req','-x509','-newkey','rsa:2048','-noenc','-keyout',str(WORK/'tls.key'),
         '-out',str(WORK/'tls.crt'),'-days','1','-subj','/CN=network-ci',
         '-addext','subjectAltName=IP:'+IP])
    (WORK/'tls.key').chmod(0o600)
    ca=base64.b64encode((WORK/'tls.crt').read_bytes()).decode()
    API.token=secrets.token_urlsafe(32)
    (WORK/'api-token').write_text(API.token);(WORK/'api-token').chmod(0o600)
    kube={'apiVersion':'v1','kind':'Config','clusters':[{'name':'ci','cluster':{'server':'https://'+IP+':6443','certificate-authority-data':ca}}],
          'contexts':[{'name':'ci','context':{'cluster':'ci','user':'ci'}}],'current-context':'ci',
          'users':[{'name':'ci','user':{'tokenFile':str(WORK/'api-token')}}]}
    Path('/etc/kubernetes').mkdir();Path('/etc/kubernetes/admin.conf').write_text(json.dumps(kube))
    server=ThreadingHTTPServer((IP,6443),API);context=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.minimum_version=ssl.TLSVersion.TLSv1_2
    context.load_cert_chain(WORK/'tls.crt',WORK/'tls.key');server.socket=context.wrap_socket(server.socket,server_side=True)
    threading.Thread(target=server.serve_forever,daemon=True).start()
    return server


def fixture_ssh():
    for name in ('host','client'):run(['ssh-keygen','-q','-t','ed25519','-N','','-f',str(WORK/name)])
    (WORK/'authorized_keys').write_bytes((WORK/'client.pub').read_bytes());(WORK/'authorized_keys').chmod(0o600)
    config=('Port 22222\nListenAddress '+IP+'\nHostKey '+str(WORK/'host')+'\nPidFile '+str(WORK/'sshd.pid')+
        '\nAuthorizedKeysFile '+str(WORK/'authorized_keys')+'\nPasswordAuthentication no\nKbdInteractiveAuthentication no\n'
        'PermitRootLogin prohibit-password\nUsePAM no\nStrictModes yes\n')
    (WORK/'sshd_config').write_text(config);Path('/run/sshd').mkdir(exist_ok=True)
    child=subprocess.Popen(['/usr/sbin/sshd','-D','-e','-f',str(WORK/'sshd_config')],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    public=(WORK/'host.pub').read_text().split()
    (WORK/'known_hosts').write_text('['+IP+']:22222 '+public[0]+' '+public[1]+'\n')
    prefix=['ssh','-p','22222','-i',str(WORK/'client'),'-o','UserKnownHostsFile='+str(WORK/'known_hosts'),
            '-o','StrictHostKeyChecking=yes','-o','BatchMode=yes','-o','PasswordAuthentication=no',
            '-o','KbdInteractiveAuthentication=no','-o','ControlMaster=no','-o','ConnectTimeout=5','root@'+IP]
    for _ in range(50):
        try:run(prefix+['true']);return child,prefix
        except subprocess.CalledProcessError:time.sleep(.1)
    raise ValueError('Fixture key-only SSH did not start')


def sample():
    """Observe every IPv4 address and DHCP evidence on the fixture NIC."""
    began=time.monotonic()
    addresses=json.loads(run(['ip','-j','-4','address','show','dev','eno1']))
    addresses=[a for link in addresses for a in link['addr_info'] if a.get('family')=='inet']
    routes=json.loads(run(['ip','-j','-4','route','show','default','dev','eno1']))
    link=json.loads(run(['networkctl','status','eno1','--json=short','--no-pager']))
    if link['Name']!='eno1':raise ValueError('Wrong networkd interface')
    parser=configparser.ConfigParser(strict=False)
    files=[link['NetworkFile'],*link.get('NetworkFileDropins',[])]
    if parser.read(files)!=files:raise ValueError('Cannot inspect active generated network configuration')
    configured=parser.get('Network','DHCP',fallback='no').lower() not in ('no','false','off','0')
    clients=[]
    for process in Path('/proc').glob('[0-9]*'):
        try:
            name=(process/'comm').read_text().strip()
            if name in ('dhclient','dhcpcd','udhcpc','pump'):clients.append(name)
        except FileNotFoundError:pass # process exited while enumerating
    dhcp=(configured or bool(clients) or 'DHCPv4Client' in link or 'DHCPv6Client' in link or
          Path('/run/systemd/netif/leases',str(link['Index'])).exists() or
          any(a.get('dynamic',False) or 'dynamic' in a.get('flags',[]) for a in addresses))
    return {'at':datetime.now(timezone.utc).isoformat(),'monotonic':began,'completed':time.monotonic(),
            'addresses':[a['local'] for a in addresses],'gateways':[r.get('gateway') for r in routes],
            'dhcpActive':dhcp,'dhcpConfigured':configured,'standaloneDhcpClients':clients}


def evaluate_samples(samples):
    """Conservative gap bound: last known good to first known good, inclusive."""
    if not samples:raise ValueError('No network samples')
    gaps=[];previous=None;start=None;max_interval=0
    for row in samples:
        if 'error' in row:raise ValueError('Network sampling failed')
        if any(address!=IP for address in row['addresses']):raise ValueError('Alternate IPv4 address observed')
        if row['dhcpActive']:raise ValueError('DHCP activity observed')
        if row['gateways'] not in ([],['192.168.1.1']):raise ValueError('Unexpected default route observed')
        if previous:
            # Include command runtime/observation uncertainty in the upper bound.
            interval=row['completed']-previous['monotonic'];max_interval=max(max_interval,interval)
            if interval>1:raise ValueError('Sampling coverage gap exceeds one second')
        good=row['addresses']==[IP] and row['gateways']==['192.168.1.1']
        if not good and start is None:
            if previous is None:raise ValueError('Initial network sample is not healthy')
            start=previous['monotonic']
        if start is not None:
            duration=row['completed']-start
            if duration>5:raise ValueError('Address/default-route gap exceeds five seconds')
            if good:
                gaps.append({'upperBoundSeconds':round(duration,6),'endedAt':row['at']});start=None
        previous=row
    if start is not None:raise ValueError('Network gap did not recover')
    return {'maxGapSecondsUpperBound':max((g['upperBoundSeconds'] for g in gaps),default=0),
            'maxObservationIntervalSeconds':round(max_interval,6),'gaps':gaps,
            'noAlternateIPv4':True,'noDhcpOnEno1':True,'sampleCount':len(samples)}


def prove(report):
    guard();report.mkdir(parents=True,exist_ok=True)
    spec=importlib.util.spec_from_file_location('net',ROOT/'deploy/common/host-network.py')
    net=importlib.util.module_from_spec(spec);spec.loader.exec_module(net)
    sys.path.insert(0,str(ROOT/'tools'));import platform_host as host
    from unittest.mock import patch
    captured=[]
    with patch.object(host,'request',side_effect=lambda ssh,action,**data:captured.append(data) or {'status':'passed'}):host.network(None,'check')
    data=host.expected()|captured[0]|{'dhcpReservationConfirmed':False}
    legacy=data['config'].replace('      accept-ra: false\n      link-local: []\n','').encode()
    if hashlib.sha256(legacy).hexdigest()!=net.LEGACY_SHA256:raise ValueError('Legacy fixture digest differs')
    saved={};server=sshd=None;monitor_stop=threading.Event();samples=[];units=[];cases=[]
    nic_created=False
    protection=Path('/etc/netplan/06-ci-protect.yaml')
    def monitor():
        while not monitor_stop.is_set():
            try:
                samples.append(sample())
            except Exception as error:samples.append({'error':type(error).__name__})
            monitor_stop.wait(.1)
    try:
        WORK.mkdir(mode=0o700)
        for directory in ('/etc/netplan','/etc/cloud/cloud.cfg.d'):
            Path(directory).mkdir(parents=True,exist_ok=True)
        # Preserve the runner's genuine primary NIC YAML and networking.
        dhcp=Path(net.DHCP)
        if dhcp.exists():
            extra=Path('/etc/netplan/05-ci-primary.yaml')
            if extra.exists():raise ValueError('Primary fixture backup collision')
            saved[net.DHCP]=(dhcp.read_bytes(),dhcp.stat().st_mode & 0o777)
            dhcp.rename(extra)
        default=json.loads(run(['ip','-j','-4','route','show','default']))
        if len(default)!=1 or 'gateway' not in default[0]:raise ValueError('Unsupported CI primary route')
        route=default[0]
        if protection.exists():raise ValueError('Primary route protection collision')
        # Declare protection in netplan too: networkd can garbage-collect a
        # policy rule added with ip alone when it reloads the primary NIC.
        import yaml
        protect={'network':{'version':2,'ethernets':{route['dev']:{
            'routes':[{'to':'default','via':route['gateway'],'table':int(TABLE),'on-link':True}],
            'routing-policy':[{'from':'0.0.0.0/0','table':int(TABLE),'priority':int(TABLE)}]}}}}
        protection.write_text(yaml.safe_dump(protect));protection.chmod(0o600)
        run(['ip','link','add','eno1','address',data['mac'],'type','dummy']);nic_created=True
        run(['ip','link','set','eno1','up'])
        net.write(net.STATIC,legacy);net.write(net.CLOUD,b'network: {config: disabled}\n')
        run(['netplan','generate']);run(['netplan','apply'])
        server=fixture_api();sshd,ssh=fixture_ssh()
        assert net.matches(net.effective(data),data)
        adopted=net.check(data);assert adopted['integrity']['status']=='WARN'
        samples.append(sample());monitor_thread=threading.Thread(target=monitor,daemon=True);monitor_thread.start()
        # Fresh connections execute the production module; only unrelated Dell
        # hardware/bootstrap identity checks are outside this network fixture.
        code=('import importlib.util,json,sys; s=importlib.util.spec_from_file_location("n",'+repr(str(ROOT/'deploy/common/host-network.py'))+
              '); n=importlib.util.module_from_spec(s);s.loader.exec_module(n); d=json.loads(sys.argv[1]); '
              'r=n.start(d,open('+repr(str(ROOT/'deploy/common/host-network.py'))+').read()) if sys.argv[2]=="start" else n.confirm(d); print(json.dumps(r))')
        def remote(action,values):
            return json.loads(run(ssh+[shlex.join(['/usr/bin/python3','-c',code,json.dumps(values),action])]))
        def transaction(mode,accept):
            API.ready=accept
            response=remote('start',data|{'mode':mode});unit=response['unit'];units.append(unit)
            confirmed=False;refused=False;began=time.monotonic()
            while time.monotonic()-began<175:
                state=net.poll({'unit':unit})
                if state['status']=='awaiting-confirmation' and not (confirmed or refused):
                    run(ssh+['true']) # new TCP/key authentication before confirmation
                    try:remote('confirm',data|{'unit':unit});confirmed=True
                    except subprocess.CalledProcessError:
                        if accept:raise
                        refused=True
                if state['status'] in ('failed','passed'):break
                time.sleep(.5)
            else:raise ValueError('Real netplan transaction deadline exceeded')
            API.ready=True
            assert state['status']==('passed' if accept else 'failed'),state
            assert confirmed if accept else refused
            run(ssh+['true'])
            assert run(ssh+[shlex.join(['kubectl','--kubeconfig','/etc/kubernetes/admin.conf',
                '--server=https://'+IP+':6443','--insecure-skip-tls-verify=false',
                '--request-timeout=5s','get','--raw=/readyz'])])=='ok'
            assert net.matches(net.effective(data),data),net.effective(data)
            cases.append({'mode':mode,'confirmation':'accepted' if accept else 'refused by HTTPS readiness',
                          'status':state['status'],'unit':unit,'elapsedSeconds':round(time.monotonic()-began,2),
                          'address':IP,'gateway':data['gateway'],'profile':net.owned()['profile'],
                          'freshSshPostCheck':'passed','trustedTlsReadyzPostCheck':'passed','nodeInternalIP':IP})
        transaction('apply',True)
        assert net.path(net.STATIC).read_bytes()==data['config'].encode()
        transaction('rollback',True)
        assert net.path(net.STATIC).read_bytes()==legacy
        transaction('apply',False)
        assert net.path(net.STATIC).read_bytes()==legacy
        assert not net.path(net.DHCP).exists()
        assert net.check(data)['integrity']['status']=='WARN'
        monitor_stop.set();monitor_thread.join(timeout=15)
        if monitor_thread.is_alive():raise ValueError('Sampler did not stop')
        samples.append(sample());bounds=evaluate_samples(samples)
        result={'status':'passed','at':datetime.now(timezone.utc).isoformat(),'commit':run(['git','-C',str(ROOT),'rev-parse','HEAD']),
                'os':Path('/etc/os-release').read_text(),'vm':run(['systemd-detect-virt']),
                'versions':run(['dpkg-query','-W','netplan.io','systemd','openssh-server']),
                'adoption':adopted,'cases':cases,'samples':samples,'bounds':bounds,
                'scope':'Real VM dummy NIC/networkd/netplan/SSH/TLS; synthetic Node API; no Dell or AMT'}
        (report/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result|{'samples':len(samples)}),flush=True)
    except Exception:
        diagnostics={}
        for name,args in {
            'addresses':['ip','-j','-4','address'], 'routes':['ip','-j','-4','route','show','table','all'],
            'rules':['ip','-j','rule'], 'dns':['resolvectl','dns','eno1'],
            'api':['kubectl','--kubeconfig','/etc/kubernetes/admin.conf','--request-timeout=5s','get','--raw=/api/v1/nodes'],
        }.items():
            found=subprocess.run(args,capture_output=True,text=True,timeout=10,check=False)
            diagnostics[name]={'exit':found.returncode,'stdout':found.stdout,'stderr':found.stderr}
        (report/'failure.json').write_text(json.dumps({'diagnostics':diagnostics,'cases':cases,'samples':samples},indent=2)+'\n')
        print(json.dumps(diagnostics),flush=True)
        raise
    finally:
        monitor_stop.set()
        for unit in units:
            (report/(unit+'.log')).write_text(run(['journalctl','-u',unit,'--no-pager','-o','cat']))
            subprocess.run(['systemctl','stop',unit],check=False,capture_output=True)
        if sshd:sshd.terminate();sshd.wait(timeout=10)
        if server:server.shutdown();server.server_close()
        for name in (net.STATIC,net.CLOUD):Path(name).unlink(missing_ok=True)
        if saved:
            raw,mode=saved[net.DHCP];Path(net.DHCP).write_bytes(raw);Path(net.DHCP).chmod(mode)
            Path('/etc/netplan/05-ci-primary.yaml').unlink()
        if nic_created:run(['ip','link','delete','eno1'])
        protection.unlink(missing_ok=True)
        subprocess.run(['ip','rule','del','priority',TABLE,'lookup',TABLE],capture_output=True,check=False)
        subprocess.run(['ip','route','del','table',TABLE,'default'],capture_output=True,check=False)
        subprocess.run(['netplan','apply'],capture_output=True,check=False,timeout=60)
        if WORK.exists():shutil.rmtree(WORK) # constant, owned disposable tmpfs only


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--report',type=Path,required=True);args=parser.parse_args()
    prove(args.report.resolve())
