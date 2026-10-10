#!/usr/bin/env python3
"""Scoped local trial; pause only endpoint reconciliation until tested source is published.

Existing database/storage/OpenBao resources are never applied here. Private
credential data is kept in memory by the preflight. The public state receipt
permits resuming the exact prior GitOps annotation after publication.
"""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools'))
from configure_console_identity import guard
from wsl_console_preflight import validate_secret
from wsl_keycloak_admin import k, obj, patch
from vcloud_console import image, publish, profile

STATE = ROOT / '.build/console/local-trial.json'
APP = 'vcloud-wsl-endpoints'
SKIP = 'argocd.argoproj.io/skip-reconcile'


def apply(values):
    from platform_apply import apply as platform_apply
    platform_apply(values, k, "vcloud-console-bootstrap")


def scoped(values):
    return [o for o in values if (o['kind'], o['metadata']['name']) in {
        ('ConfigMap','vcloud-runtime-config'), ('ConfigMap','vcloud-apisix'),
        ('Deployment','keycloak'), ('Deployment','apisix')}]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true'); parser.add_argument('--resume-gitops', action='store_true')
    args = parser.parse_args(); guard()
    if args.resume_gitops:
        state = json.loads(STATE.read_text())
        if state['application'] != APP: raise ValueError('Unexpected reconciliation owner')
        patch('application', APP, {'metadata': {'annotations': {SKIP: state['previous'], 'argocd.argoproj.io/refresh':'hard'}}})
        print('PASS: endpoint GitOps reconciliation restored'); return
    publish(True); profile()
    secret = obj(['get','secret','vcloud-console-oidc','-o','json']); validate_secret(secret)
    cached = subprocess.run(['/usr/local/bin/k3s','crictl','--runtime-endpoint=unix:///run/containerd/containerd.sock','inspecti',image()], capture_output=True)
    if cached.returncode: raise ValueError('Pinned portal image absent from local CRI cache')
    values = list(yaml.safe_load_all((ROOT/'lab/wsl/endpoints/gitops/workloads.yaml').read_text()))
    app = obj(['get','application',APP,'-o','json'])
    previous = app['metadata'].get('annotations',{}).get(SKIP)
    if previous == 'true' or app.get('status',{}).get('operationState',{}).get('phase') == 'Running':
        raise ValueError('Refusing an already paused or actively syncing endpoint Application')
    print('PASS: owned lab, encrypted credential references, cache and generated source')
    if not args.apply: return
    STATE.parent.mkdir(parents=True,exist_ok=True)
    STATE.write_text(json.dumps({'application': APP, 'previous': previous})+'\n')
    patch('application',APP,{'metadata':{'annotations':{SKIP:'true'}}})
    if obj(['get','application',APP,'-o','json']).get('status',{}).get('operationState',{}).get('phase')=='Running':
        raise ValueError('Application began a sync; no gateway candidate applied')
    try:
        apply(list(yaml.safe_load_all((ROOT/'deploy/console/bootstrap.yaml').read_text())))
        apply(scoped(values))
        # Existing Keycloak hostname/issuer is unchanged. Reload only its new
        # private-service backchannel option and the gateway's public CA mount.
        for name in ('keycloak','apisix'):
            k(['rollout','restart','deployment/'+name])
            k(['rollout','status','deployment/'+name,'--timeout=300s'],timeout=320)
            print('PASS: '+name+' rollout')
        # Mount-aware legacy browser views are additive; retain their inventory.
        legacy=list(yaml.safe_load_all((ROOT/'lab/wsl/console/workloads.yaml').read_text()))
        apply([o for o in legacy if o['kind']=='ConfigMap' or o['metadata']['name'] in ('storage-ui','dynamodb-admin')])
        apply(list(yaml.safe_load_all((ROOT/'deploy/console/deployment.yaml').read_text())))
        apply(list(yaml.safe_load_all((ROOT/'deploy/console/service.yaml').read_text())))
        for name in ('vcloud-console','storage-ui','dynamodb-admin'):
            k(['rollout','status','deployment/'+name,'--timeout=180s'],timeout=200)
        apply(list(yaml.safe_load_all((ROOT/'deploy/console/apisix-routes.yaml').read_text())))
        for unit in ('vcloud-wsl-apisix-access.service','vcloud-wsl-keycloak-access.service'):
            if subprocess.check_output(['systemctl','show',unit,'--property=LoadState','--value'],text=True).strip()=='loaded':
                subprocess.run(['systemctl','restart',unit],check=True)
        print('PASS: portal candidate deployed; verify OIDC before restoring reconciliation to published source')
    except Exception:
        # Restore only known public desired configuration from the current commit.
        baseline=subprocess.check_output(['git','show','HEAD:lab/wsl/endpoints/gitops/workloads.yaml'],cwd=ROOT,text=True)
        apply(scoped(list(yaml.safe_load_all(baseline))))
        patch('application',APP,{'metadata':{'annotations':{SKIP:previous}}})
        raise


if __name__=='__main__':
    try: main()
    except Exception as error:
        detail = str(error) if isinstance(error, (ValueError, RuntimeError)) else type(error).__name__
        print('FAIL: scoped deployment failed: ' + detail + '; private command output withheld',file=sys.stderr)
        raise SystemExit(1)
