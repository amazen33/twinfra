#!/usr/bin/env python3
"""Fail-closed offline schema and CI/CD security validation; never deploys resources."""
import argparse
import copy
import gzip
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import yaml

ROOT=Path(__file__).resolve().parents[1]
MODULE=ROOT/'module-3'
sys.path.insert(0,str(ROOT/'tools'))
from build_module2_schemas import compact
from check_manifest_contract import load_policy
from manifest_contract import audit_objects
from render_module3 import resources, SEC


def objects():
    return [obj for folder in ['manifests','argocd','gitops','examples']
            for path in sorted((MODULE/folder).glob('*.yaml')) for obj in yaml.safe_load_all(path.read_text()) if obj]


def verify_bundle():
    lock=json.loads((MODULE/'artifacts.lock.json').read_text())
    for relative,expected in lock['filesSHA256'].items():
        path=ROOT/relative
        if not path.resolve().is_relative_to(MODULE.resolve()) or hashlib.sha256(path.read_bytes()).hexdigest()!=expected:
            raise ValueError('Module 3 locked artifact checksum mismatch: '+relative)
    meta=json.loads((ROOT/'module-2/schemas/namespace_v1.json').read_text())['properties']['metadata']
    count=0
    apis={item['kind']:item for item in lock['apis']}
    for path in (MODULE/'vendor').glob('*.yaml.gz'):
        for crd in yaml.safe_load_all(gzip.decompress(path.read_bytes())):
            kind=crd['spec']['names']['kind']
            if kind not in apis: continue
            api=apis[kind]['apiVersion']; version=next(v for v in crd['spec']['versions'] if api.endswith('/'+v['name']))
            if not version['served'] or version.get('deprecated'): raise ValueError('Unsupported/deprecated CRD version')
            s=compact(version['schema']['openAPIV3Schema']); s['$schema']='http://json-schema.org/draft-07/schema#'
            s.setdefault('properties',{})['metadata']=meta
            s['properties']['apiVersion']={'type':'string','enum':[api]};s['properties']['kind']={'type':'string','enum':[kind]}
            s['required']=list(dict.fromkeys(s.get('required',[])+['apiVersion','kind','metadata']))
            generated=(json.dumps(s,separators=(',',':'))+'\n').encode()
            target=MODULE/'schemas'/crd['spec']['group']/(kind.lower()+'_'+version['name']+'.json')
            if target.read_bytes()!=generated: raise ValueError('Schema reproduction drift: '+kind)
            count+=1
    if count!=8: raise ValueError('Incomplete Module 3 CRD schema bundle')
    return lock


def audit(items):
    load_policy() # retains the frozen node policy and approval gate without granting CI exceptions
    expected=resources()
    tasks={o['metadata']['name']:o for o in items if o['kind']=='Task'}
    if set(tasks)!={'vcloud-clone','vcloud-test','vcloud-build','vcloud-publish'}: raise ValueError('Incomplete CI tasks')
    for name,task in tasks.items():
        if task['apiVersion']!='tekton.dev/v1' or task['metadata']['namespace']!='workload-apps': raise ValueError('Task scope/API drift')
        if task['spec'].get('sidecars') or task['spec']['stepTemplate']['securityContext']!=SEC: raise ValueError('Task privilege drift')
        for step in task['spec']['steps']:
            if step.get('script') or step['command']!=['python3'] or step['image']!='registry.vcloud.example.com/vcloud/ci-tooling:1.0.0':
                raise ValueError('Trusted Task execution/image drift')
        projected={'apiVersion':'v1','kind':'Pod','metadata':task['metadata'],'spec':{
            'automountServiceAccountToken':False,'volumes':task['spec'].get('volumes',[]),
            'containers':[dict(step,securityContext=task['spec']['stepTemplate']['securityContext']|step.get('securityContext',{}))
                          for step in task['spec']['steps']]}}
        violations=audit_objects([projected],load_policy())['violations']
        if violations: raise ValueError('Task pod policy: '+'; '.join(violations))
        approved=next(o for o in expected['module-3/manifests/tasks.yaml'] if o['metadata']['name']==name)
        if task!=approved: raise ValueError('Task credentials, arguments, resources or execution contract drift')
    for item in items:
        kind=item['kind']
        if kind in {'Pipeline','PipelineRun'}:
            if item['apiVersion']!='tekton.dev/v1': raise ValueError('Deprecated pipeline API')
            key='module-3/manifests/pipeline.yaml' if kind=='Pipeline' else 'module-3/examples/pipelinerun.yaml'
            if item!=expected[key][0]: raise ValueError('Pipeline sequencing, token, workspace or result drift')
        if kind in {'EventListener','TriggerBinding','TriggerTemplate','ApisixRoute','ApisixTls'}:
            approved=next(o for o in expected['module-3/manifests/triggers.yaml'] if o['kind']==kind)
            if item!=approved: raise ValueError('Push authentication, branch filter or trigger structure drift')
        if kind in {'Role','RoleBinding','ClusterRole','ClusterRoleBinding'}:
            approved=next(o for o in expected['module-3/manifests/rbac.yaml'] if o['kind']==kind)
            if item!=approved: raise ValueError('CI RBAC authority drift')
        if kind=='Application':
            if item not in expected['module-3/argocd/application.yaml']: raise ValueError('Argo repository, destination, sync or ownership drift')
        if kind=='AppProject':
            if item not in expected['module-3/argocd/application.yaml']: raise ValueError('Argo project boundary drift')
        if kind=='Service' and item['apiVersion']=='serving.knative.dev/v1':
            projected={'apiVersion':'v1','kind':'Pod','metadata':item['metadata'],'spec':item['spec']['template']['spec']}
            problems=audit_objects([projected],load_policy())['violations']
            if problems: raise ValueError('Workload contract: '+'; '.join(problems))
        if kind=='CiliumNetworkPolicy':
            all_policies=expected['module-3/manifests/network.yaml']+expected['module-3/gitops/network.yaml']
            approved=next(o for o in all_policies if (o['metadata']['name'],o['metadata']['namespace'])==(item['metadata']['name'],item['metadata']['namespace']))
            if item!=approved: raise ValueError('CI network scope drift')
        if kind in {'ServiceMonitor','PrometheusRule'}:
            approved=next(o for o in expected['module-3/manifests/observability.yaml'] if o['kind']==kind and o['metadata']['name']==item['metadata']['name'])
            if item!=approved: raise ValueError('Observability selector, metric or alert drift')
    return {'status':'passed','resources':len(items),'nodeExceptionExpansion':False,
            'triggerSchemaLimit':'Upstream Triggers schemas preserve unknown fields; exact trigger structure is additionally audited here.',
            'liveAcceptance':'not executed'}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--kubeconform',default='kubeconform');parser.add_argument('--report',type=Path,default=ROOT/'.build/module-3/validation.json')
    args=parser.parse_args(); lock=verify_bundle()
    subprocess.run([sys.executable,str(ROOT/'tools/render_module3.py'),'--check'],check=True)
    files=[str(p) for folder in ['manifests','argocd','gitops','examples'] for p in sorted((MODULE/folder).glob('*.yaml'))]
    command=[args.kubeconform,'-strict','-summary','-kubernetes-version','1.36.5']
    for directory in [MODULE/'schemas',ROOT/'module-2/schemas']:
        for pattern in ['{{.Group}}/{{.ResourceKind}}_{{.ResourceAPIVersion}}.json','{{.ResourceKind}}_{{.ResourceAPIVersion}}.json']:
            command+=['-schema-location',str(directory/pattern)]
    result=subprocess.run(command+files,check=True,capture_output=True,text=True)
    print(result.stdout.strip())
    report=audit(objects());report['schemaValidation']=result.stdout.strip();report['schemaReproducibility']=8
    report['versions']=lock['versions'];report['renderedSHA256']={str(Path(p).relative_to(ROOT)):hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in files}
    args.report.parent.mkdir(parents=True,exist_ok=True)
    args.report.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8',newline='\n')
    print('Module 3 offline schemas, CI credentials, push filters, network and GitOps ownership passed')


if __name__=='__main__': main()
