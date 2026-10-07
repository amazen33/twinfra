#!/usr/bin/env python3
"""Fail-closed Module 5a source, schema and security validation; no deployment."""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import yaml
from manifest_contract import audit_objects,podspec
from module2 import verify_bundle,load_policy
from module4a import bundle as csi_bundle
from render_module5a import ROOT,MODULE,files,main as render_check


def audit(items):
    wrappers=[]
    for item in items:
        spec=podspec(item)
        if spec and spec.get('containers'):
            wrappers.append({'apiVersion':'v1','kind':'Pod','metadata':copy.deepcopy(item['metadata']),'spec':copy.deepcopy(spec)})
            if spec.get('automountServiceAccountToken') is not False:raise ValueError('RAG/inference API token forbidden')
            for container in spec['containers']:
                if container.get('imagePullPolicy')!='IfNotPresent':raise ValueError('Offline pull policy drift')
                if container['securityContext'].get('capabilities')!={'drop':['ALL']}:raise ValueError('Unexpected capability')
        if item['kind']=='SecretProviderClass':
            spec=item['spec'];params=spec['parameters']
            if spec.get('secretObjects') or params.get('baoSkipTLSVerify') or spec['provider']!='openbao':raise ValueError('CSI synchronization/TLS drift')
            if params['audience']!='openbao' or params['roleName'] not in ('vcloud-rag','vcloud-rag-indexer'):raise ValueError('CSI identity drift')
            objects=yaml.safe_load(params['objects'])
            if len(objects)!=1 or objects[0]['objectName']!='database.json' or objects[0].get('secretKey') or objects[0]['filePermission']!=288:
                raise ValueError('Credential pairing/scope drift')
        if item['kind']=='Job' and item['spec'].get('suspend') is not True:raise ValueError('Reference Job must be suspended')
        if item['apiVersion']=='serving.knative.dev/v1':
            if item['metadata']['labels'].get('networking.knative.dev/visibility')!='cluster-local':raise ValueError('Inference must be private')
            revision=item['spec']['template'];spec=revision['spec'];container=spec['containers'][0]
            if spec.get('runtimeClassName')!='nvidia':raise ValueError('NVIDIA runtime required')
            if any(container['resources'][k].get('nvidia.com/gpu')!=1 for k in ('requests','limits')):raise ValueError('GPU allocation drift')
            if revision['metadata']['annotations'].get('autoscaling.knative.dev/max-scale')!='1':raise ValueError('GPU capacity bound drift')
    # Normalize served Knative custom resources into real Pod specs for the
    # frozen hostPath/root/capability/image/security audit. It grants no exceptions.
    plain=[o for o in items if not podspec(o)]
    violations=audit_objects(wrappers+plain,load_policy())['violations']
    if violations:raise ValueError('; '.join(violations))


def main(kubeconform):
    verify_bundle();csi_bundle();render_check(True)
    # The strict Job schema is shared with Module 5b, but standalone Module 5a
    # validation must authenticate it without depending on another test gate.
    job_schema=ROOT/'module-5b/schemas/job_v1.json'
    if hashlib.sha256(job_schema.read_bytes()).hexdigest()!='edcd3b8017ad204da5cb94562dd31f038f121e9a81931204d9983edd3fa7604c':
        raise ValueError('Pinned Kubernetes Job schema differs')
    paths=[MODULE/p for p in files() if p.endswith('.yaml')]
    items=[o for path in paths for o in yaml.safe_load_all(path.read_text(encoding='utf-8')) if o]
    audit(items)
    # Merge-patch payloads are not Kubernetes objects. Validate their resulting
    # ConfigMap shapes with the same strict offline schema, without applying.
    composed=ROOT/'.build/module-5a/knative-patches.yaml'
    composed.parent.mkdir(parents=True,exist_ok=True)
    patches=[]
    for name,target in [('features','config-features'),('autoscaler','config-autoscaler'),('deployment','config-deployment')]:
        payload=yaml.safe_load((MODULE/f'patches/knative-{name}.mergepatch.yaml').read_text(encoding='utf-8'))
        patches.append({'apiVersion':'v1','kind':'ConfigMap','metadata':{'name':target,'namespace':'platform-services'},**payload})
    composed.write_text(yaml.safe_dump_all(patches,sort_keys=False),encoding='utf-8',newline='\n')
    paths.append(composed)
    schemas=[ROOT/'module-2/schemas/{{.Group}}/{{.ResourceKind}}_{{.ResourceAPIVersion}}.json',
        ROOT/'module-2/schemas/{{.ResourceKind}}_{{.ResourceAPIVersion}}.json',
        ROOT/'module-4a/schemas/{{.Group}}/{{.ResourceKind}}_{{.ResourceAPIVersion}}.json',
        ROOT/'module-5b/schemas/{{.ResourceKind}}_{{.ResourceAPIVersion}}.json']
    flags=[]
    for schema in schemas:flags+=['-schema-location',str(schema)]
    subprocess.run([kubeconform,'-strict','-summary',*flags,*map(str,paths)],check=True)
    print('Module 5a: strict offline validation passed; GPU/SQL/RAG runtime acceptance not executed')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--kubeconform',default='kubeconform')
    main(parser.parse_args().kubeconform)
