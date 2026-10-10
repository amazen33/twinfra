#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Offline render/schema/PSS checks for every rebuilt environment. No provisioning."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import yaml

from platform_resources import ROOT
from platform_dev import database
from manifest_contract import audit_objects, podspec
from check_upstream_names import renders, source_objects, validate
from platform_sources import check_argocd_api


def run(command):
    result=subprocess.run([v.as_posix() if isinstance(v,Path) else str(v) for v in command],capture_output=True,text=True,encoding='utf-8')
    if result.returncode:raise ValueError(result.stdout+result.stderr)
    return result.stdout


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for cli in ('helm','kustomize','kubeconform','conftest','bash'):
        parser.add_argument('--'+cli,default=cli)
    parser.add_argument('--schemas',type=Path,required=True)
    parser.add_argument('--build',type=Path,default=ROOT/'.build/dev-validation')
    args=parser.parse_args();args.build.mkdir(parents=True,exist_ok=True)
    check_argocd_api(ROOT)
    registry=json.loads((ROOT/'deploy/upstream-names.json').read_text())
    sources={p['project']:source_objects(ROOT,p,args.helm) for p in registry['projects']}
    objects=renders(ROOT,args.kustomize)
    validate(objects,registry,sources)
    output=args.build/'dev.yaml';output.write_text(yaml.safe_dump_all(objects,sort_keys=False),encoding='utf-8')
    print(run([args.conftest,'test','--namespace','twinfra_platform','--policy',ROOT/'tests/ci/policy/platform-restricted.rego',output]))
    # Explicit dev PV vetting; the frozen node approval is never edited for storage.
    pv=next(o for o in database() if o['kind']=='PersistentVolume')
    fields=('local','nodeAffinity','accessModes','volumeMode','storageClassName')
    policy={'registry':'registry.twinfra.example.com','localPVs':{pv['metadata']['name']:{k:pv['spec'][k] for k in fields}}}
    checked=[o for o in objects if podspec(o) or o['kind']=='PersistentVolume']
    report=audit_objects(checked,policy)
    if report['violations']:raise ValueError(str(report['violations']))
    env=dict(os.environ,PLATFORM_PROFILE='dev-cairo-1',NODE_IP='10.50.0.10',POD_CIDR='10.110.0.0/16',
             CLUSTER_DNS_NAME='twinfra-dev-cairo-1',IMAGE_REGISTRY='registry.twinfra.example.com')
    command=['source "$1"; render_cilium_values','source "$1"; render_exception_policy']
    rendered=[]
    for code in command:
        rendered.append(subprocess.check_output([args.bash,'-c',code,'_',(ROOT/'00-setup-ubuntu-host.sh').as_posix()],env=env,text=True,encoding='utf-8'))
    values=args.build/'cilium-values.yaml';values.write_text(rendered[0],encoding='utf-8')
    node_policy=json.loads(rendered[1])
    raw=run([args.helm,'template','cilium',ROOT/'module-2/vendor/cilium-1.20.2.tgz','--namespace','kube-system','-f',values])
    upstream=args.build/'cilium-upstream.yaml';upstream.write_text(raw,encoding='utf-8')
    kdir=args.build/'cilium-labels';kdir.mkdir(exist_ok=True)
    (kdir/'upstream.yaml').write_text(raw,encoding='utf-8')
    (kdir/'kustomization.yaml').write_text(yaml.safe_dump({'apiVersion':'kustomize.config.k8s.io/v1beta1','kind':'Kustomization','resources':['upstream.yaml'],'labels':[{'pairs':{'twinfra.io/environment':'dev','twinfra.io/region':'cairo-1','twinfra.io/component':'cilium'},'includeSelectors':False,'includeTemplates':True}]}),encoding='utf-8')
    raw=run([args.kustomize,'build',kdir])
    nodes=[o for o in yaml.safe_load_all(raw) if o];validate(nodes,registry,sources)
    result=audit_objects(nodes,node_policy)
    if result['violations']:raise ValueError(str(result['violations']))
    nodefile=args.build/'cilium.yaml';nodefile.write_text(raw,encoding='utf-8')
    for name,entry in json.loads((ROOT/'deploy/common/schema.lock.json').read_text()).items():
        if hashlib.sha256((ROOT/'deploy/common/schemas'/name).read_bytes()).hexdigest()!=entry['sha256']:raise ValueError('Schema differs: '+name)
    templates=[ROOT/'deploy/common/schemas/{{.ResourceKind}}.json',args.schemas/'{{.ResourceKind}}.json',ROOT/'module-2/schemas/{{.Group}}/{{.ResourceKind}}_{{.ResourceAPIVersion}}.json',
               ROOT/'module-2/schemas/{{.ResourceKind}}_{{.ResourceAPIVersion}}.json',args.build/'schemas/{{.ResourceKind}}_{{.ResourceAPIVersion}}.json']
    # Extract exact schemas for CNPG Database/other CRDs from the pinned upstream input.
    schema_dir=args.build/'schemas';schema_dir.mkdir(exist_ok=True)
    for obj in objects:
        if obj['kind']!='CustomResourceDefinition':continue
        kind=obj['spec']['names']['kind'].lower()
        for version in obj['spec']['versions']:
            schema=version.get('schema',{}).get('openAPIV3Schema')
            if schema:(schema_dir/(kind+'_'+version['name']+'.json')).write_text(json.dumps(schema),encoding='utf-8')
    # kubeconform treats a Windows drive prefix as a URI scheme. Relative POSIX
    # paths keep the exact locked schemas usable on both Windows and Linux.
    flags=[part for template in templates for part in
           ('-schema-location',Path(os.path.relpath(template)).as_posix() if os.name=='nt' else template.as_posix())]
    print(run([args.kubeconform,'-strict','-summary','-kubernetes-version','1.36.5',*flags,output,nodefile]))
    (args.build/'summary.json').write_text(json.dumps({'status':'passed','scope':'static only; live acceptance Pending','resources':len(objects),'ciliumResources':len(nodes),'nodePolicySourceSHA256':node_policy['sourcePolicySHA256']},indent=2)+'\n',encoding='utf-8')


if __name__=='__main__':main()
