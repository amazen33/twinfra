#!/usr/bin/env python3
"""Strict offline validation of OpenBao integration and composed Kubernetes patches."""
import argparse
import copy
import gzip
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import yaml

ROOT=Path(__file__).resolve().parents[1]
MODULE=ROOT/'module-4a'
sys.path.insert(0,str(ROOT/'tools'))
from build_module2_schemas import compact
from check_manifest_contract import load_policy
from manifest_contract import audit_objects
from render_module4a import files


def merge(base,patch):
    result=copy.deepcopy(base)
    for key,value in patch.items():
        result[key]=merge(result.get(key,{}),value) if isinstance(value,dict) else copy.deepcopy(value)
    return result


def patch(base,operations):
    result=copy.deepcopy(base)
    for operation in operations:
        parts=operation['path'].strip('/').split('/')
        parent=result
        for part in parts[:-1]:parent=parent[int(part)] if isinstance(parent,list) else parent[part]
        key=parts[-1]
        if operation['op']=='test':
            if parent[key]!=operation['value']:raise ValueError('Patch target identity drift')
        elif operation['op']=='add':
            if key=='-' and isinstance(parent,list):parent.append(copy.deepcopy(operation['value']))
            else:parent[key]=copy.deepcopy(operation['value'])
        else:raise ValueError('Unsupported integration patch operation')
    return result


def bundle():
    lock=json.loads((MODULE/'artifacts.lock.json').read_text())
    for relative,expected in lock['filesSHA256'].items():
        p=ROOT/relative
        if not p.resolve().is_relative_to(MODULE.resolve()) or hashlib.sha256(p.read_bytes()).hexdigest()!=expected:
            raise ValueError('Module 4a locked input drift: '+relative)
    crd=yaml.safe_load(gzip.decompress((MODULE/'vendor/secretproviderclass-crd.yaml.gz').read_bytes()))
    version=next(v for v in crd['spec']['versions'] if v['name']=='v1')
    if not version['served'] or version.get('deprecated'):raise ValueError('Unsupported/deprecated CSI API')
    s=compact(version['schema']['openAPIV3Schema']);s['$schema']='http://json-schema.org/draft-07/schema#'
    s['properties']['metadata']=json.loads((ROOT/'module-2/schemas/namespace_v1.json').read_text())['properties']['metadata']
    s['properties']['apiVersion']={'type':'string','enum':['secrets-store.csi.x-k8s.io/v1']}
    s['properties']['kind']={'type':'string','enum':['SecretProviderClass']}
    s['required']=list(dict.fromkeys(s.get('required',[])+['apiVersion','kind','metadata']))
    if (MODULE/'schemas/secrets-store.csi.x-k8s.io/secretproviderclass_v1.json').read_bytes()!=(json.dumps(s,separators=(',',':'))+'\n').encode():
        raise ValueError('SecretProviderClass schema reproduction drift')
    return lock


def objects():
    return [o for p in sorted((MODULE/'manifests').glob('*.yaml')) for o in yaml.safe_load_all(p.read_text()) if o]


def audit(items):
    violations=audit_objects(items,load_policy())['violations']
    if violations:raise ValueError('Original SSoT/pod contract: '+'; '.join(violations))
    for item in items:
        if item['kind']=='SecretProviderClass':
            sp=item['spec'];params=sp['parameters']
            if sp['provider']!='openbao' or sp.get('secretObjects') or params.get('baoSkipTLSVerify') not in (None,'false'):
                raise ValueError('Default CSI secret delivery/TLS drift')
            secrets=yaml.safe_load(params['objects'])
            if len(secrets)!=2 or secrets[0].get('secretKey') or secrets[0]['objectName']!='database.json':
                raise ValueError('Database credential pairing drift')
            if params['audience']!='openbao' or params['roleName']!='vcloud-csi-client':raise ValueError('CSI identity drift')
            if any(s.get('filePermission')!=288 for s in secrets):raise ValueError('Secret file mode drift')
        if item['kind']=='ClusterRole' and item['rules']!=[{'apiGroups':['authentication.k8s.io'],'resources':['tokenreviews'],'verbs':['create']}]:
            raise ValueError('OpenBao TokenReview RBAC expansion')
        if item['kind']=='Deployment':
            spec=item['spec']['template']['spec']
            if spec.get('automountServiceAccountToken') is not False or spec['serviceAccountName']!='vcloud-secrets-client':
                raise ValueError('Application identity/token drift')
            volume=next(v for v in spec['volumes'] if v['name']=='secrets')
            if volume['csi']!={'driver':'secrets-store.csi.k8s.io','readOnly':True,'volumeAttributes':{'secretProviderClass':'vcloud-openbao'}}:
                raise ValueError('CSI driver/reference/access drift')
    # Exact generated wiring supplements the permissive provider parameters schema.
    expected=[o for path,text in files().items() if path.startswith('module-4a/manifests/') for o in yaml.safe_load_all(text)]
    def key(o):return (o['kind'],o['metadata'].get('namespace',''),o['metadata']['name'])
    if sorted(items,key=key)!=sorted(expected,key=key):raise ValueError('Namespace/network/integration contract drift')


def compose():
    consumer=patch(yaml.safe_load((MODULE/'examples/consumer-base.yaml').read_text()),
                   yaml.safe_load((MODULE/'patches/consumer-csi.jsonpatch.yaml').read_text()))
    if consumer!=yaml.safe_load((MODULE/'manifests/consumer.yaml').read_text()):raise ValueError('CSI mount patch composition drift')
    cluster=next(o for o in yaml.safe_load_all((ROOT/'module-2/manifests/database.yaml').read_text()) if o and o['kind']=='Cluster')
    cluster=merge(cluster,yaml.safe_load((MODULE/'patches/cnpg-hba.mergepatch.yaml').read_text()))
    driver=merge(yaml.safe_load(gzip.decompress((MODULE/'vendor/csidriver.yaml.gz').read_bytes())),
                 yaml.safe_load((MODULE/'patches/csi-fsgroup.mergepatch.yaml').read_text()))
    synced=patch(yaml.safe_load((MODULE/'manifests/secretproviderclass.yaml').read_text()),
                 yaml.safe_load((MODULE/'patches/static-secret-sync.jsonpatch.yaml').read_text()))
    return [consumer,cluster,driver,synced]


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--kubeconform',default='kubeconform');parser.add_argument('--build',type=Path,default=ROOT/'.build/module-4a')
    args=parser.parse_args();lock=bundle()
    subprocess.run([sys.executable,str(ROOT/'tools/render_module4a.py'),'--check'],check=True)
    items=objects();audit(items);composed=compose()
    example=yaml.safe_load((MODULE/'examples/validator-pod.yaml').read_text())
    violations=audit_objects([example],load_policy())['violations']
    if violations:raise ValueError('Validator Pod contract: '+'; '.join(violations))
    args.build.mkdir(parents=True,exist_ok=True)
    compiled=args.build/'composed.yaml'
    compiled.write_text(yaml.safe_dump_all(composed,sort_keys=False),encoding='utf-8',newline='\n')
    paths=list(sorted((MODULE/'manifests').glob('*.yaml')))+[MODULE/'examples/consumer-base.yaml',MODULE/'examples/validator-pod.yaml',compiled]
    command=[args.kubeconform,'-strict','-summary','-kubernetes-version','1.36.5']
    for directory in [MODULE/'schemas',ROOT/'module-2/schemas']:
        for pattern in ['{{.Group}}/{{.ResourceKind}}_{{.ResourceAPIVersion}}.json','{{.ResourceKind}}_{{.ResourceAPIVersion}}.json']:
            command+=['-schema-location',str(directory/pattern)]
    output=subprocess.check_output(command+[str(p) for p in paths],text=True)
    print(output.strip())
    report={'status':'passed','module':'4a','scope':'Strict offline schemas and semantic contracts; live OpenBao/PostgreSQL/CSI not executed',
            'versions':lock['versions'],'primaryResources':len(items),'schemaValidation':output.strip(),
            'schemaReproducibility':1,'composedPatches':['consumer CSI mount','CNPG HBA','CSIDriver fsGroup/token audience','optional static Secret sync'],
            'nodeExceptionExpansion':False,'liveAcceptance':'not executed'}
    (args.build/'validation.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8',newline='\n')
    print('Module 4a CSI pairing, scoped identities/network and original node approval checks passed')


if __name__=='__main__':main()
