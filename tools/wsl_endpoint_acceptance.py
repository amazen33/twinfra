#!/usr/bin/env python3
"""Live lab gates. HTTP shells and running Pods alone cannot count as a pass."""
from datetime import datetime,timezone
import json
from http.client import RemoteDisconnected
from pathlib import Path
import subprocess
import time
import urllib.request
from wsl_db_test import sql
from wsl_endpoints import ROOT,NS

K=['/usr/local/bin/k3s','kubectl','--kubeconfig=/etc/vcloud-wsl/kubeconfig.yaml','--context=vcloud-wsl-local','--request-timeout=30s']


def get(*args):return json.loads(subprocess.check_output(K+list(args)+['-o','json']))


def http(url,headers=None):
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
    for attempt in range(6):
        try:
            with opener.open(urllib.request.Request(url,headers=headers or {}),timeout=45) as response:
                return response.status,response.read()
        except (RemoteDisconnected,ConnectionResetError):
            # A kubectl port-forward holds the old Pod until its first request
            # after rollout. The owned unit restarts in 3s; never mask HTTP errors.
            if attempt==5:raise
            time.sleep(1)


def main():
    report={'timestampUTC':datetime.now(timezone.utc).isoformat(),'scope':'CPU-only local WSL; no production promotion','checks':[]}
    def passed(name,detail):report['checks'].append({'name':name,'status':'passed','detail':detail});print('PASS: '+name+' '+str(detail),flush=True)
    try:
        app=get('get','application','vcloud-wsl-platform','-n',NS)
        assert app['status']['sync']['status']=='Synced' and app['status']['health']['status']=='Healthy'
        assert not app['status'].get('conditions')
        passed('GitOps',{'revision':app['status']['sync']['revision'],'sync':'Synced','health':'Healthy'})
        assert sql("SELECT extversion FROM pg_extension WHERE extname='vector';")=='0.8.2'
        assert sql('SELECT ssl FROM pg_stat_ssl WHERE pid=pg_backend_pid();')=='t'
        assert sql("SELECT count(*) FROM local_acceptance WHERE marker='local-storage-survives';")=='1'
        passed('Database','pgvector 0.8.2, TLS and retained marker verified')
        code,body=http('http://127.0.0.1:18080/',{'Host':'demo-cpu-app.workload-apps.example.com'})
        assert code==200 and body==b'vcloud-knative-cpu-ok\n'
        passed('Ingress',{'http':code,'path':'APISIX -> Kourier -> Knative demo-cpu-app'})
        for attempt in range(30):
            code,body=http('http://127.0.0.1:9090/api/v1/targets');targets=json.loads(body)
            active=targets['data']['activeTargets']
            required={name:[t for t in active if ('/'+name+'/') in t['scrapePool']] for name in ('apisix','cnpg','knative')}
            if all(v and all(t['health']=='up' for t in v) for v in required.values()):break
            time.sleep(2)
        else:raise ValueError('APISIX/CNPG/Knative metrics targets are not all present and up')
        passed('Prometheus targets',{name:len(v) for name,v in required.items()})
        for attempt in range(15):
            logs=subprocess.check_output(K+['logs','deployment/otel-collector','-n',NS,'--since=5m'],text=True,stderr=subprocess.DEVNULL)
            if 'vcloud-demo-request' in logs and 'demo-cpu-app' in logs:break
            time.sleep(2)
        else:raise ValueError('Collector did not export the real demo trace')
        passed('OpenTelemetry','real demo span received and exported via debug; no durable trace backend claimed')
        code,body=http('http://127.0.0.1:3000/api/health');assert code==200 and json.loads(body)['database']=='ok'
        passed('Grafana','HTTP 200, application database ok')
        # Verify Keycloak TLS using its public certificate; never skip verification.
        public=subprocess.check_output(K+['get','secret','vcloud-wsl-keycloak-tls','-n',NS,'-o','jsonpath={.data.tls\\.crt}'])
        import base64,ssl
        context=ssl.create_default_context(cadata=base64.b64decode(public).decode())
        opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),urllib.request.HTTPSHandler(context=context))
        with opener.open('https://localhost:18443/realms/vcloud/.well-known/openid-configuration',timeout=15) as response:oidc=json.load(response)
        assert oidc['issuer']=='https://localhost:18443/realms/vcloud'
        passed('Keycloak','OIDC discovery and verified TLS')
        pods=get('get','pods','-A')['items']
        application_namespaces={NS,'workload-apps','hpc-compute'}
        for pod in pods:
            if pod['metadata']['namespace'] not in application_namespaces:continue
            spec=pod['spec']
            assert not any(spec.get(k,False) for k in ('hostNetwork','hostPID','hostIPC'))
            assert not any('hostPath' in v for v in spec.get('volumes',[]))
            for c in spec.get('containers',[])+spec.get('initContainers',[]):
                parent=spec.get('securityContext',{});sc=parent|c.get('securityContext',{})
                assert sc.get('runAsNonRoot') is True and sc.get('runAsUser')!=0
                assert sc.get('allowPrivilegeEscalation') is False and 'ALL' in sc.get('capabilities',{}).get('drop',[])
                assert not sc.get('capabilities',{}).get('add') and sc.get('seccompProfile')=={'type':'RuntimeDefault'}
                assert not sc.get('privileged',False)
                assert not any('nvidia.com/' in r for scope in ('requests','limits') for r in c.get('resources',{}).get(scope,{}))
                assert not any(e.get('name')=='SPINIFEX_OFFLOAD_ENABLED' and e.get('value','').lower()=='true' for e in c.get('env',[]))
                assert not any(token in c['image'].lower() for token in ('/vllm','/spinifex','deepseek'))
        passed('Restricted PodSecurity','all live non-system vCloud Pods checked, including generated CNPG/Knative/Prometheus containers')
        passed('GPU/Spinifex','no AI/HPC containers, GPU allocations or enabled offloading flags')
        code,body=http('http://127.0.0.1:8200/v1/sys/init');status=json.loads(body)
        report['openbao']={'initialized':status['initialized'],'initialization':'operator PGP gate; unseal never automated'}
        if not status['initialized']:
            result=subprocess.run(['bash',str(ROOT/'lab/wsl/openbao-init.sh'),'--check-only'],capture_output=True,text=True)
            assert result.returncode in (0,3)
            if result.returncode==3:assert 'Initialization gated: Missing required PGP public key files.' in result.stdout
            found=subprocess.check_output(K+['get','secret','openbao-init-encrypted','-n',NS,'--ignore-not-found','-o','name'])
            assert not found.strip()
            passed('OpenBao initialization gate',('GET false; missing operator keys -> exit 3' if result.returncode==3 else
                'GET false; valid public-key/custody preflight only')+'; no POST or init-output Secret')
        else:
            result=subprocess.run(['bash',str(ROOT/'lab/wsl/openbao-init.sh'),'--check-only'],capture_output=True,text=True)
            assert result.returncode==0
            passed('OpenBao initialization gate','GET true; initialization skipped; unseal acceptance remains separate')
        report['status']='passed';report['failures']=0
    except Exception as error:
        # Assertions and known public outcomes only; no SQL/API credential bytes.
        report['status']='failed';report['failures']=1;report['failureType']=type(error).__name__
        print('FAIL: acceptance stopped at '+str(len(report['checks']))+' passed gates; '+type(error).__name__,flush=True)
    output=ROOT/'.build/wsl-endpoints/acceptance.json';output.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))
    return 0 if report['status']=='passed' else 1


if __name__=='__main__':raise SystemExit(main())
