#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""WO-31 13/13a/13b: blocking dev image resolution; report-only production debt."""
import argparse
from datetime import date
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import tomllib

import yaml

from platform_resources import ROOT

# Closed approval list, not inferred from every canonical tag in the lock.
# Adding a renderer/object/reference requires an ADR or work-order amendment.
BOOTSTRAP_TAG_ALLOWLIST={
    ('kubeadm','Pod','kube-apiserver'):'registry.twinfra.example.com/registry.k8s.io/kube-apiserver:v1.36.5',
    ('kubeadm','Pod','kube-controller-manager'):'registry.twinfra.example.com/registry.k8s.io/kube-controller-manager:v1.36.5',
    ('kubeadm','Pod','kube-scheduler'):'registry.twinfra.example.com/registry.k8s.io/kube-scheduler:v1.36.5',
    ('kubeadm','Pod','etcd'):'registry.twinfra.example.com/registry.k8s.io/etcd:3.6.8-0',
    ('kubeadm','Deployment','coredns'):'registry.twinfra.example.com/registry.k8s.io/coredns:v1.14.2',
    ('containerd','ContainerRuntimeConfiguration','containerd'):'registry.twinfra.example.com/registry.k8s.io/pause:3.10.1',
    ('kubeadm','RuntimeImage','pause'):'registry.twinfra.example.com/registry.k8s.io/pause:3.10.2',
}
IMAGE_FIELDS={'image','imageName','imageRef','sandbox_image'}


def normalized(reference):
    if not isinstance(reference,str):return None
    match=re.fullmatch(r'([a-z0-9][a-z0-9._:/-]*(?::[A-Za-z0-9_][A-Za-z0-9_.-]{0,127})?)@(sha256:[a-f0-9]{64})',reference)
    if not match:return None
    repository=match[1]
    if ':' in repository.rsplit('/',1)[-1]:
        repository,tag=repository.rsplit(':',1)
        if not re.fullmatch(r'[A-Za-z0-9_][A-Za-z0-9_.-]{0,127}',tag):return None
    return repository+'@'+match[2]


def references(objects,producer='workload'):
    """Walk Pod templates, CR instances/catalogs and IMAGE env values, not schema declarations."""
    def walk(value,path=()):
        if isinstance(value,list):
            for i,item in enumerate(value):yield from walk(item,path+(str(i),))
        elif isinstance(value,dict):
            for key,item in value.items():
                location=path+(key,)
                if key in IMAGE_FIELDS and not isinstance(item,(dict,list)):
                    yield '/'.join(location),item
                elif key=='images':
                    if isinstance(item,list):
                        for i,ref in enumerate(item):
                            if not isinstance(ref,(dict,list)):yield '/'.join(location+(str(i),)),ref
                    elif isinstance(item,dict):
                        for name,ref in item.items():
                            if not isinstance(ref,(dict,list)):yield '/'.join(location+(name,)),ref
                if key=='env' and isinstance(item,list):
                    for i,env in enumerate(item):
                        if isinstance(env,dict) and 'IMAGE' in env.get('name','').upper():
                            yield '/'.join(location+(str(i),env['name'])),env.get('value')
                yield from walk(item,location)
    for obj in objects:
        if obj.get('kind')=='List':
            yield from references(obj['items'],producer);continue
        if obj.get('kind')=='CustomResourceDefinition':continue
        metadata=obj.get('metadata',{})
        for path,ref in walk(obj.get('spec',{})):
            yield dict(producer=producer,kind=obj.get('kind'),name=metadata.get('name'),
                       namespace=metadata.get('namespace'),path=path,reference=ref)


def audit(objects,lock,scope,producer='workload'):
    entries=lock['images'].values();allowed=set();canonicals=set()
    for entry in entries:
        digest=entry['digest'];canonical=entry['canonical']
        if not re.fullmatch(r'sha256:[a-f0-9]{64}',digest):raise ValueError('Invalid image lock digest')
        ref=canonical if '@' in canonical else canonical+'@'+digest
        key=normalized(ref)
        if key is None or key.rsplit('@',1)[1]!=digest:raise ValueError('Invalid image lock canonical/digest')
        allowed.add(key);canonicals.add(canonical)
    result=[]
    for record in references(objects,producer):
        ref=record['reference'];key=normalized(ref)
        if key is not None:
            reason='' if key in allowed else 'Repository/digest does not resolve to this scope lock'
        elif (scope=='B' and ref==BOOTSTRAP_TAG_ALLOWLIST.get((producer,record['kind'],record['name'])) and
              isinstance(ref,str) and ref in canonicals):reason=''
        else:reason='Missing/invalid digest or tag-only reference outside the closed bootstrap allowance'
        if reason:result.append(record|{'reason':reason,'scope':scope})
    return result


def require(objects,lock,scope,producer='workload'):
    findings=audit(objects,lock,scope,producer)
    if findings:raise ValueError('Image-reference guard failed: '+json.dumps(findings,sort_keys=True))


def production_report(findings,on=None):
    lines=['Production image-reference debt — '+str(on or date.today())+' (report-only)']
    for row in findings:
        lines.append(f"- [{row.get('input','production')}] {row['producer']} {row['kind']}/{row['name']} {row['path']}: {row['reference']} — {row['reason']}")
    if not findings:lines.append('- No image-reference debt in these rendered objects.')
    text='\n'.join(lines)+'\n';print(text,end='');return text


def production_markdown(findings,on=None):
    lines=['## Production image-reference debt','',
           'Snapshot: '+str(on or date.today())+'. Report-only scope C; no production references changed.','',
           '| Consumers | Reference | Finding |','| --- | --- | --- |']
    sources=sorted({row['input'] for row in findings if 'input' in row})
    if sources:lines[4:4]=['Input sources: '+', '.join('`'+name+'`' for name in sources)+'.','']
    grouped={}
    for row in findings:
        key=(str(row['reference']),row['reason'])
        grouped.setdefault(key,set()).add(row['kind']+'/'+row['name'])
    for (reference,reason),consumers in sorted(grouped.items()):
        values=(', '.join(sorted(consumers)),reference,reason)
        lines.append('| '+' | '.join(v.replace('|','\\|').replace('\n',' ') for v in values)+' |')
    if not findings:lines.append('| — | — | No debt in these renders |')
    return '\n'.join(lines)+'\n'


def run(command,env=None):
    return subprocess.check_output([str(p) for p in command],env=env,text=True,encoding='utf-8')


def cloud_inputs(root):
    """Bind both production seeds to the shared script; return public env inputs."""
    script=(root/'00-setup-ubuntu-host.sh').read_bytes()
    checksum=hashlib.sha256(script).hexdigest();result={}
    for filename in ('user-data.yaml','user-data-remote.yaml'):
        config=yaml.safe_load((root/filename).read_text())
        files={f['path']:f.get('content','') for f in config['write_files']}
        if filename=='user-data.yaml':
            if files['/usr/local/sbin/00-setup-ubuntu-host.sh'].encode()!=script:
                raise ValueError('Production embedded bootstrap differs')
        elif checksum not in files['/usr/local/sbin/vcloud-fetch-host.sh']:
            raise ValueError('Production fetch bootstrap checksum differs')
        result[filename]={line.split('=',1)[0]:line.split('=',1)[1] for line in files['/etc/vcloud-host.env'].splitlines()
                          if line and not line.startswith('#') and '=' in line and line.split('=',1)[1]}
    return result


def render_profile(root,profile,bash,helm,overrides=None):
    """Render helpers only; never invoke main, kubeadm, CRI or an installer."""
    from platform_dev import host_environment
    values={}
    if profile.startswith('dev-'):
        row=next(r for r in yaml.safe_load((root/'vcloud-ssot.yaml').read_text())['addressPlan']
                 if r['environment']=='dev' and r['region']==profile.removeprefix('dev-'))
        values=dict(line.split('=',1) for line in host_environment(row).splitlines()
                    if line and not line.startswith('#') and '=' in line)
    else:values={'PLATFORM_PROFILE':'production','NODE_IP':'192.168.50.10','NODE_NAME':'ci-production'}
    if overrides:values.update(overrides)
    # Avoid inherited dev overrides when evaluating production, and inherited config paths.
    keys={line.split('=',1)[0] for line in (root/'host.env.example').read_text().splitlines()
          if line and not line.startswith('#') and '=' in line}
    env={k:v for k,v in os.environ.items() if k not in keys}
    env.update(values,VCLOUD_CONFIG_FILE='/nonexistent-image-reference-config')
    def render(command):
        return run([bash,'-c','source "$1"; load_config; '+command,'_',
                    (root/'00-setup-ubuntu-host.sh').as_posix()],env)
    kube=next(o for o in yaml.safe_load_all(render('render_kubeadm')) if o['kind']=='ClusterConfiguration')
    lock=json.loads((root/'deploy/common/bootstrap-images.lock.json').read_text())
    source=(root/lock['kubeadmSource']['path']).read_bytes()
    if hashlib.sha256(source).hexdigest()!=lock['kubeadmSource']['sha256']:raise ValueError('Kubeadm source checksum differs')
    def constant(name):return re.search(r'\b'+name+r'\s*=\s*"([^"]+)"',source.decode())[1]
    repository=kube['imageRepository']
    # The real kubeadm dry-run separately audits actual control-plane/etcd Pods in CI.
    static=[{'kind':'Pod','metadata':{'name':name},'spec':{'containers':[{'name':name,'image':repository+'/'+name+':'+kube['kubernetesVersion']}]}}
            for name in ('kube-apiserver','kube-controller-manager','kube-scheduler')]
    etcd=kube.get('etcd',{}).get('local',{});dns=kube.get('dns',{})
    static.append({'kind':'Pod','metadata':{'name':'etcd'},'spec':{'containers':[{'name':'etcd','image':etcd.get('imageRepository',repository)+'/etcd:'+etcd.get('imageTag',constant('DefaultEtcdVersion'))}]}})
    system=[{'kind':'Deployment','metadata':{'name':'coredns'},'spec':{'template':{'spec':{'containers':[{'name':'coredns','image':dns.get('imageRepository',repository)+'/coredns:'+dns.get('imageTag',constant('CoreDNSVersion'))}]}}}},
            {'kind':'RuntimeImage','metadata':{'name':'pause'},'spec':{'image':repository+'/pause:'+constant('PauseVersion')}}]
    runtimes=[]
    for version in ('1.7.28','2.2.1'):
        config=tomllib.loads(render('render_containerd '+version))
        plugins=config['plugins']
        pause=(plugins['io.containerd.grpc.v1.cri']['sandbox_image'] if version.startswith('1.') else
               plugins['io.containerd.cri.v1.images']['pinned_images']['sandbox'])
        runtimes.append({'kind':'ContainerRuntimeConfiguration','metadata':{'name':'containerd'},'spec':{'sandbox_image':pause}})
    with tempfile.TemporaryDirectory() as directory:
        file=Path(directory)/'values.yaml';file.write_text(render('render_cilium_values'),encoding='utf-8')
        raw=run([helm,'template','cilium',root/'module-2/vendor/cilium-1.20.2.tgz','--namespace','kube-system','-f',file])
    cilium=[o for o in yaml.safe_load_all(raw) if o]
    foundation=[o for o in yaml.safe_load_all(render('render_foundation')) if o]
    smoke=[]
    if profile=='production':
        if render('printf "%s" "$RUN_SMOKE_TESTS"')=='true':
            for command in ('render_smoke','render_probe_job allowed','render_probe_job denied','render_hugepage_job'):
                smoke.extend(o for o in yaml.safe_load_all(render(command)) if o)
    settings=render('printf "%s\\n%s\\n" "$IMAGE_REGISTRY" "$NVIDIA_DEVICE_PLUGIN_VERSION"').splitlines()
    return dict(kubeadm=static+system,containerd=runtimes,helm=cilium,foundation=foundation,smoke=smoke,
                registry=settings[0],nvidiaVersion=settings[1])


def check_renders(root,bash,helm,kustomize,nvidia_chart,out):
    app_lock=json.loads((root/'deploy/common/images.lock.json').read_text())
    boot_lock=json.loads((root/'deploy/common/bootstrap-images.lock.json').read_text())
    checked=[];warnings=[]
    profiles=sorted((root/'deploy/environments/dev').glob('*/platform/kustomization.yaml'))
    if not profiles:raise ValueError('No dev workload profile to validate')
    for profile in profiles:
        for component in ('platform','services'):
            directory=profile.parent.parent/component
            objects=[o for o in yaml.safe_load_all(run([kustomize,'build',directory])) if o]
            require(objects,app_lock,'A');checked.append(str(directory.relative_to(root)))
    for region in ('cairo-1','cairo-2'):
        rendered=render_profile(root,'dev-'+region,bash,helm)
        for producer in ('kubeadm','containerd','helm'):
            require(rendered[producer],boot_lock,'B',producer)
        checked.append('dev-'+region+' bootstrap/system')
    production_inputs={'production':{},**cloud_inputs(root)}
    for name,inputs in production_inputs.items():
        production=render_profile(root,'production',bash,helm,inputs)
        findings=[]
        for producer in ('kubeadm','containerd','helm'):
            findings+=audit(production[producer],boot_lock,'B',producer)
        findings+=audit(production['foundation']+production['smoke'],app_lock,'A')
        # Same upstream chart/settings as Module -1; MPS is explicitly never installed.
        raw=run([helm,'template','nvidia-device-plugin',nvidia_chart,'--namespace','kube-system',
                 '--set','runtimeClassName=nvidia','--set','gfd.enabled=false','--set','nfd.enabled=false',
                 '--set','image.repository='+production['registry']+'/nvcr.io/nvidia/k8s-device-plugin',
                 '--set','image.tag=v'+production['nvidiaVersion']])
        nvidia=[o for o in yaml.safe_load_all(raw) if o and not
                (o['kind']=='DaemonSet' and o['metadata']['name']=='nvidia-device-plugin-mps-control-daemon')]
        findings+=audit(nvidia,boot_lock,'B','helm')
        warnings.extend(row|{'input':name} for row in findings)
    for profile in sorted((root/'deploy/environments/production').glob('*/platform/kustomization.yaml')):
        for component in ('platform','services'):
            objects=[o for o in yaml.safe_load_all(run([kustomize,'build',profile.parent.parent/component])) if o]
            warnings+=audit(objects,app_lock,'A')
    warnings=[row|{'ruleScope':row['scope'],'scope':'C'} for row in warnings]
    text=production_report(warnings)
    result={'status':'passed','scope':'static only','checked':checked,'productionDebt':warnings,
            'productionInputs':list(production_inputs),
            'unusedVendorObjects':['DaemonSet/nvidia-device-plugin-mps-control-daemon']}
    out.mkdir(parents=True,exist_ok=True)
    (out/'summary.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    (out/'production-debt.txt').write_text(text,encoding='utf-8')
    (out/'production-debt.md').write_text(production_markdown(warnings),encoding='utf-8')
    print('PASS: blocking scopes A/B; production references remain report-only')
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('bash','helm','kustomize'):parser.add_argument('--'+name,default=name)
    parser.add_argument('--root',type=Path,default=ROOT)
    parser.add_argument('--nvidia-chart',type=Path,required=True)
    parser.add_argument('--out',type=Path,default=ROOT/'.build/image-references')
    args=parser.parse_args()
    check_renders(args.root,args.bash,args.helm,args.kustomize,args.nvidia_chart,args.out)
