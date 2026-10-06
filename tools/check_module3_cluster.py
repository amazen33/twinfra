#!/usr/bin/env python3
"""Read-only deployment prerequisite checks. No secret values are read or printed."""
import argparse
import json
import subprocess
import sys
import yaml
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]


def run(command):
    result=subprocess.run(command,capture_output=True,text=True)
    if result.returncode: raise ValueError('Prerequisite command failed: '+command[1])
    return result.stdout.strip()


def validate_storage(storage):
    # This profile uses per-run dynamic claims; the static Module 2 SC cannot satisfy them.
    if storage['provisioner'] not in {'rbd.csi.ceph.com','cephfs.csi.ceph.com','csi.vsphere.vmware.com',
                                     'ebs.csi.aws.com','pd.csi.storage.gke.io','disk.csi.azure.com'}:
        raise ValueError('Use a reviewed explicit CSI provisioner; the vcloud-local no-provisioner profile is insufficient')
    if storage.get('volumeBindingMode')!='WaitForFirstConsumer': raise ValueError('CSI workspace storage must use WaitForFirstConsumer')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--kubectl',default='kubectl');parser.add_argument('--context',required=True)
    args=parser.parse_args()
    if not args.context.strip(): raise ValueError('An explicit reviewed kubectl context is required')
    kubectl=[args.kubectl,'--context',args.context]
    def get(*rest): return json.loads(run([*kubectl,'get',*rest,'-o','json']))
    apis=json.loads((ROOT/'module-3/artifacts.lock.json').read_text())['apis']
    crds=get('crds')['items']
    for item in apis:
        found=next((c for c in crds if c['spec']['names']['kind']==item['kind'] and c['spec']['group']==item['apiVersion'].split('/')[0]),None)
        if not found: raise ValueError('Missing CRD: '+item['kind'])
        version=next((v for v in found['spec']['versions'] if v['name']==item['apiVersion'].split('/')[1]),None)
        if not version or not version['served'] or version.get('deprecated'): raise ValueError('Unsupported live CRD version')
    validate_storage(get('storageclass','vcloud-ci-csi'))
    for namespace in ['platform-services','workload-apps','tekton-pipelines']:
        ns=get('namespace',namespace)
        if ns['metadata'].get('labels',{}).get('pod-security.kubernetes.io/enforce')!='restricted':
            raise ValueError('Restricted Pod Security required: '+namespace)
    for name in ['vcloud-registry-pull','vcloud-webhook-hmac','vcloud-ci-webhook-tls','vcloud-buildkit-mtls','vcloud-registry-push','vcloud-git-write']:
        if not run([*kubectl,'get','secret',name,'-n','workload-apps','-o','jsonpath={.metadata.name}']):
            raise ValueError('Missing externally provisioned credential/TLS secret: '+name)
    config=get('configmap','feature-flags','-n','tekton-pipelines')['data']
    for key in ['disable-creds-init','set-security-context','set-security-context-read-only-root-filesystem']:
        if config.get(key)!='true': raise ValueError('Required Tekton flag missing: '+key)
    observed=get('configmap','config-observability','-n','tekton-pipelines')['data']
    if observed.get('metrics-protocol')!='prometheus' or observed.get('metrics.pipelinerun.duration-type')!='histogram':
        raise ValueError('Required metrics profile missing')
    service=get('service','tekton-pipelines-controller','-n','tekton-pipelines')
    if not any(p['name']=='http-metrics' and p['port']==9090 for p in service['spec']['ports']):
        raise ValueError('Controller metrics service profile drift')
    print('CRDs, restricted namespaces, explicit CSI, secret existence and Tekton configuration checked')
    print('Still prove live controller/helper images, builder mTLS, Git branch permissions, webhook HMAC, scraping and workload activation.')


if __name__=='__main__': main()
