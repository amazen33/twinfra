#!/usr/bin/env python3
"""Render, audit and validate the scoped WSL GitOps/database deployment."""
import argparse
import copy
import gzip
import hashlib
import json
from pathlib import Path
import subprocess
import yaml
from wsl_lab import ROOT,load_policy,normalize_pods,resource,security
from manifest_contract import audit_objects,podspec
from wsl_pg_image import IMAGE as PG_IMAGE
from wsl_lab_dns_image import IMAGE as DNS_IMAGE

NS='platform-services';DB='vcloud-wsl-postgres';NODE='vcloud-wsl-local'
PG_PATH='/var/lib/vcloud-wsl/storage/postgres-1'
REG='registry.vcloud.example.com/'
SC='vcloud-wsl-local'
PYTHON=REG+'docker.io/library/python:3.14.1-slim-trixie@sha256:b823ded4377ebb5ff1af5926702df2284e53cecbc6e3549e93a19d8632a1897e'


def vendor(name):
    lock=json.loads((ROOT/'lab/wsl/platform-artifacts.lock.json').read_text())[name]
    content=(ROOT/'lab/wsl/vendor'/f'{name}.gz').read_bytes()
    if hashlib.sha256(content).hexdigest()!=lock['gzipSHA256']:raise ValueError('Vendor gzip differs')
    raw=gzip.decompress(content)
    if hashlib.sha256(raw).hexdigest()!=lock['sourceSHA256']:raise ValueError('Upstream manifest differs')
    return [o for o in yaml.safe_load_all(raw) if o]


def relocate(value):
    if isinstance(value,dict):
        for key,item in value.items():
            if key=='namespace' and item in ('argocd','cnpg-system'):value[key]=NS
            else:relocate(item)
    elif isinstance(value,list):
        for item in value:relocate(item)


def infrastructure():
    result=[]
    cluster_kinds={'CustomResourceDefinition','ClusterRole','ClusterRoleBinding','MutatingWebhookConfiguration','ValidatingWebhookConfiguration','APIService'}
    for name in ('argocd-core.yaml','cnpg.yaml','metrics-server.yaml'):
        for obj in vendor(name):
            if obj['kind']=='Namespace':continue
            if 'applicationset-controller' in obj['metadata']['name']:continue
            if obj['kind']=='NetworkPolicy':continue # Replace upstream broad allows with the scoped rules below.
            relocate(obj)
            if name=='argocd-core.yaml' and obj['kind'] not in cluster_kinds:obj['metadata']['namespace']=NS
            spec=podspec(obj)
            if spec:
                obj['spec']['replicas']=1
                uid=10001 if name=='cnpg.yaml' else 1000 if name=='metrics-server.yaml' else 999
                spec['securityContext']={'runAsNonRoot':True,'runAsUser':uid,'runAsGroup':uid,'fsGroup':uid,'seccompProfile':{'type':'RuntimeDefault'}}
                for c in spec.get('containers',[])+spec.get('initContainers',[]):
                    c['image']=REG+c['image'];c['imagePullPolicy']='IfNotPresent'
                    c['securityContext']=security()|{'runAsUser':uid,'runAsGroup':uid}
                    c['resources']={'requests':{'cpu':'100m','memory':'128Mi'},'limits':{'cpu':'1','memory':'512Mi'}}
                if obj['metadata']['name']=='argocd-repo-server':
                    spec['automountServiceAccountToken']=False
                    spec['dnsPolicy']='None';spec['dnsConfig']={'nameservers':['10.43.0.11'],'searches':[NS+'.svc.cluster.local','svc.cluster.local','cluster.local']}
                if obj['metadata']['name']=='argocd-redis':
                    spec.pop('initContainers',None);spec['automountServiceAccountToken']=False
                    c=spec['containers'][0];c.pop('env',None);c.pop('args',None)
                    c['command']=['sh','-ec',"umask 077; printf 'requirepass %s\\n' \"$(cat /auth/auth)\" > /tmp/redis.conf; exec redis-server /tmp/redis.conf --save '' --appendonly no"]
                    c['volumeMounts']=[{'name':'auth','mountPath':'/auth','readOnly':True},{'name':'tmp','mountPath':'/tmp'}]
                    spec['volumes']=[{'name':'auth','secret':{'secretName':'argocd-redis','defaultMode':0o440}}, {'name':'tmp','emptyDir':{'medium':'Memory','sizeLimit':'16Mi'}}]
                if name=='cnpg.yaml':
                    c=spec['containers'][0];c.setdefault('env',[]).append({'name':'WATCH_NAMESPACE','value':NS})
                    c['args']=[arg.replace('max-concurrent-reconciles=10','max-concurrent-reconciles=2') for arg in c['args']]
                if name=='metrics-server.yaml':
                    c=spec['containers'][0]
                    c['args'] += ['--kubelet-certificate-authority=/trust/kubelet-ca.crt','--tls-cert-file=/tls/tls.crt','--tls-private-key-file=/tls/tls.key']
                    c['volumeMounts'] += [{'name':'kubelet-trust','mountPath':'/trust','readOnly':True},{'name':'serving-tls','mountPath':'/tls','readOnly':True}]
                    spec['volumes'] += [{'name':'kubelet-trust','configMap':{'name':'vcloud-kubelet-trust'}},{'name':'serving-tls','secret':{'secretName':'vcloud-metrics-tls'}}]
            if name=='metrics-server.yaml' and obj['kind']=='APIService':
                obj['spec'].pop('insecureSkipTLSVerify');obj['spec']['caBundle']='' # Filled with actual public serving CA before apply.
            if obj['kind']=='ConfigMap' and obj['metadata']['name']=='argocd-cmd-params-cm':
                obj['data']={'controller.repo.server.strict.tls':'true','reposerver.disable.tls':'false','reposerver.parallelism.limit':'2','controller.status.processors':'2','controller.operation.processors':'1'}
            if obj['kind']=='ConfigMap' and obj['metadata']['name']=='argocd-cm':
                obj['data']={'timeout.reconciliation':'60s','timeout.reconciliation.jitter':'0s'}
            if obj['kind']=='ClusterRole' and obj['metadata']['name']=='argocd-application-controller':
                obj['rules']=[{'apiGroups':['*'],'resources':['*'],'verbs':['get','list','watch']}]
            result.append(obj)
    # Argo mutations are namespace scoped. Storage and infrastructure stay bootstrap-owned.
    role=resource('Role','vcloud-wsl-gitops-writer',namespace=NS,api='rbac.authorization.k8s.io/v1')
    role['rules']=[{'apiGroups':[group],'resources':resources,'verbs':['get','list','watch','create','update','patch']} for group,resources in
                   [('', ['configmaps','serviceaccounts']),('rbac.authorization.k8s.io',['roles','rolebindings']),
                    ('postgresql.cnpg.io',['clusters']),('batch',['cronjobs']),('cilium.io',['ciliumnetworkpolicies']),
                    ('networking.k8s.io',['networkpolicies'])]]
    binding=resource('RoleBinding','vcloud-wsl-gitops-writer',namespace=NS,api='rbac.authorization.k8s.io/v1')
    binding.update(roleRef={'apiGroup':'rbac.authorization.k8s.io','kind':'Role','name':role['metadata']['name']},
                   subjects=[{'kind':'ServiceAccount','name':'argocd-application-controller','namespace':NS}])
    result += [role,binding]
    return result


def storage():
    sc=resource('StorageClass',SC,{'unused':True},api='storage.k8s.io/v1');sc.pop('spec')
    sc.update(provisioner='kubernetes.io/no-provisioner',volumeBindingMode='WaitForFirstConsumer',reclaimPolicy='Retain',allowVolumeExpansion=False)
    pv=resource('PersistentVolume',DB+'-1',{'capacity':{'storage':'4Gi'},'volumeMode':'Filesystem','accessModes':['ReadWriteOnce'],
        'persistentVolumeReclaimPolicy':'Retain','storageClassName':SC,'claimRef':{'namespace':NS,'name':DB+'-1'},
        'local':{'path':PG_PATH},'nodeAffinity':{'required':{'nodeSelectorTerms':[{'matchExpressions':[{'key':'kubernetes.io/hostname','operator':'In','values':[NODE]}]}]}}})
    pv['metadata']['annotations']={'vcloud.io/vetted':'true','vcloud.io/vetting-document':'lab/wsl/PLATFORM.md',
                                  'argocd.argoproj.io/sync-options':'Prune=false,Delete=false'}
    return [sc,pv]


def cnp(name,selector,ingress=None,egress=None):
    spec={'endpointSelector':{'matchLabels':selector}}
    if ingress is not None:spec['ingress']=ingress
    if egress is not None:spec['egress']=egress
    return resource('CiliumNetworkPolicy',name,spec,NS,'cilium.io/v2')


def peers(labels):return [{'matchLabels':{'k8s:io.kubernetes.pod.namespace':NS}|labels}]
def ports(*numbers,protocol='TCP'):return [{'ports':[{'port':str(n),'protocol':protocol} for n in numbers]}]


def network():
    api={'toEntities':['kube-apiserver'],'toPorts':ports(443,16443)}
    operator={'k8s:app.kubernetes.io/name':'cloudnative-pg'};pg={'k8s:cnpg.io/cluster':DB}
    controller={'k8s:app.kubernetes.io/name':'argocd-application-controller'}
    repo={'k8s:app.kubernetes.io/name':'argocd-repo-server'};redis={'k8s:app.kubernetes.io/name':'argocd-redis'}
    dns={'k8s:vcloud.io/component':'git-dns'};client={'k8s:vcloud.io/component':'database-test'}
    # Probes are host traffic. The failed router /32 diagnostic is deliberately
    # absent: CIDR rules cannot repair the observed host identity mismatch.
    probe=lambda *numbers:{'fromEntities':['host'],'toPorts':ports(*numbers)}
    return [
        cnp('vcloud-wsl-operator',operator,[{'fromEntities':['host','kube-apiserver'],'toPorts':ports(9443,8081)}],
            [api,{'toEndpoints':peers(pg),'toPorts':ports(5432,8000)}]),
        cnp('vcloud-wsl-postgres',pg,[probe(8000),{'fromEndpoints':peers(operator),'toPorts':ports(5432,8000)},
            {'fromEndpoints':peers(pg),'toPorts':ports(5432,8000)}, {'fromEndpoints':peers(client),'toPorts':ports(5432)}],[api]),
        cnp('vcloud-wsl-argo-controller',controller,[probe(8082)],[api,{'toEndpoints':peers(repo),'toPorts':ports(8081)},
            {'toEndpoints':peers(redis),'toPorts':ports(6379)}]),
        cnp('vcloud-wsl-argo-redis',redis,[{'fromEndpoints':peers(controller)+peers(repo),'toPorts':ports(6379)}],[api]),
        cnp('vcloud-wsl-argo-repo',repo,[probe(8084),{'fromEndpoints':peers(controller),'toPorts':ports(8081)}],[
            {'toEndpoints':peers(redis),'toPorts':ports(6379)},
            {'toEndpoints':peers(dns),'toPorts':[{'ports':[{'port':'1053','protocol':'ANY'}],
                'rules':{'dns':[{'matchName':'github.com'},{'matchPattern':'*.svc.cluster.local'}]}}]},
            {'toFQDNs':[{'matchName':'github.com'}],'toPorts':ports(443)}]),
        cnp('vcloud-wsl-git-dns',dns,[{'fromEndpoints':peers(repo),'toPorts':ports(1053,protocol='ANY')}],[
            {'toCIDR':['10.255.255.254/32'],'toPorts':ports(53,protocol='ANY')},
            {'toEndpoints':[{'matchLabels':{'k8s:io.kubernetes.pod.namespace':'kube-system','k8s:k8s-app':'kube-dns'}}],
             'toPorts':ports(1053,protocol='ANY')}]),
        cnp('vcloud-wsl-db-scaler',{'k8s:vcloud.io/component':'database-scaler'},[],[api]),
        cnp('vcloud-wsl-db-client',client,[],[{'toEndpoints':peers(pg),'toPorts':ports(5432)}])]


def git_dns():
    cm=resource('ConfigMap','vcloud-git-dns',namespace=NS)
    cm['data']={'Corefile':'github.com:1053 {\n forward . 10.255.255.254\n cache 30\n errors\n}\ncluster.local:1053 {\n forward . 10.43.0.10\n cache 30\n errors\n}\n'}
    container={'name':'dns','image':DNS_IMAGE,'imagePullPolicy':'IfNotPresent','args':['-conf','/etc/coredns/Corefile'],
        'securityContext':security(),'resources':{'requests':{'cpu':'25m','memory':'32Mi'},'limits':{'cpu':'200m','memory':'64Mi'}},
        'volumeMounts':[{'name':'config','mountPath':'/etc/coredns','readOnly':True}]}
    deployment=resource('Deployment','vcloud-git-dns',{'replicas':1,'selector':{'matchLabels':{'vcloud.io/component':'git-dns'}},
        'template':{'metadata':{'labels':{'vcloud.io/component':'git-dns'}},'spec':{'automountServiceAccountToken':False,
        'containers':[container],'volumes':[{'name':'config','configMap':{'name':'vcloud-git-dns'}}]}}},NS,'apps/v1')
    service=resource('Service','vcloud-git-dns',{'clusterIP':'10.43.0.11','selector':{'vcloud.io/component':'git-dns'},
        'ports':[{'name':'dns','port':53,'targetPort':1053,'protocol':'UDP'},{'name':'dns-tcp','port':53,'targetPort':1053,'protocol':'TCP'}]},NS)
    return [cm,deployment,service]


def workload():
    cluster=resource('Cluster',DB,{'instances':1,'imageName':PG_IMAGE,'imagePullPolicy':'IfNotPresent','postgresUID':26,'postgresGID':26,
        'enableSuperuserAccess':False,'seccompProfile':{'type':'RuntimeDefault'},'securityContext':{'runAsNonRoot':True,'allowPrivilegeEscalation':False,'capabilities':{'drop':['ALL']}},
        'bootstrap':{'initdb':{'database':'vcloud','owner':'vcloud_app','postInitApplicationSQL':['CREATE EXTENSION IF NOT EXISTS vector;']}},
        'postgresql':{'parameters':{'shared_buffers':'128MB','max_connections':'50','huge_pages':'off'},
                      'pg_hba':['hostnossl all all all reject','hostssl all all all scram-sha-256']},
        'resources':{'requests':{'cpu':'500m','memory':'512Mi'},'limits':{'cpu':'500m','memory':'512Mi'}},
        'storage':{'storageClass':SC,'size':'4Gi','resizeInUseVolumes':False},
        'affinity':{'enablePodAntiAffinity':True,'podAntiAffinityType':'preferred','topologyKey':'kubernetes.io/hostname'}},NS,'postgresql.cnpg.io/v1')
    sa=resource('ServiceAccount','vcloud-wsl-db-scaler',namespace=NS)
    role=resource('Role','vcloud-wsl-db-scaler',namespace=NS,api='rbac.authorization.k8s.io/v1')
    role['rules']=[{'apiGroups':['postgresql.cnpg.io'],'resources':['clusters'],'resourceNames':[DB],'verbs':['get','patch']},
                   {'apiGroups':['metrics.k8s.io'],'resources':['pods'],'resourceNames':[DB+'-1'],'verbs':['get']}]
    binding=resource('RoleBinding','vcloud-wsl-db-scaler',namespace=NS,api='rbac.authorization.k8s.io/v1')
    binding.update(subjects=[{'kind':'ServiceAccount','name':sa['metadata']['name'],'namespace':NS}],
                   roleRef={'apiGroup':'rbac.authorization.k8s.io','kind':'Role','name':role['metadata']['name']})
    cm=resource('ConfigMap','vcloud-wsl-db-scaler',namespace=NS);cm['data']={'scaler.py':(ROOT/'tools/wsl_db_scaler.py').read_text()}
    cron=resource('CronJob','vcloud-wsl-db-scaler',{'schedule':'*/2 * * * *','concurrencyPolicy':'Forbid','successfulJobsHistoryLimit':1,'failedJobsHistoryLimit':1,
        'jobTemplate':{'spec':{'backoffLimit':0,'activeDeadlineSeconds':90,'template':{'metadata':{'labels':{'vcloud.io/component':'database-scaler'}},'spec':{
            'serviceAccountName':sa['metadata']['name'],'restartPolicy':'Never','containers':[{'name':'scaler','image':PYTHON,'imagePullPolicy':'IfNotPresent',
            'command':['python','/app/scaler.py'],'env':[{'name':'PYTHONDONTWRITEBYTECODE','value':'1'}],'securityContext':security(),
            'resources':{'requests':{'cpu':'25m','memory':'32Mi'},'limits':{'cpu':'100m','memory':'64Mi'}},
            'volumeMounts':[{'name':'code','mountPath':'/app','readOnly':True}]}],'volumes':[{'name':'code','configMap':{'name':cm['metadata']['name']}}]}}}}},NS,'batch/v1')
    marker=resource('ConfigMap','vcloud-wsl-gitops-marker',namespace=NS);marker['data']={'state':'managed-by-github'}
    return [cluster,sa,role,binding,cm,cron,marker]


def application():
    project=resource('AppProject','vcloud-wsl-local',{'sourceRepos':['https://github.com/amazen33/vCloud.git'],
        'destinations':[{'server':'https://kubernetes.default.svc','namespace':NS}], 'clusterResourceWhitelist':[],
        'namespaceResourceWhitelist':[{'group':group,'kind':kind} for group,kind in [('', 'ConfigMap'),('', 'ServiceAccount'),
            ('rbac.authorization.k8s.io','Role'),('rbac.authorization.k8s.io','RoleBinding'),('batch','CronJob'),
            ('postgresql.cnpg.io','Cluster'),('cilium.io','CiliumNetworkPolicy')]]},NS,'argoproj.io/v1alpha1')
    app=resource('Application','vcloud-wsl-platform',{'project':'vcloud-wsl-local','destination':{'server':'https://kubernetes.default.svc','namespace':NS},
        'source':{'repoURL':'https://github.com/amazen33/vCloud.git','targetRevision':'codex/wsl-local-bootstrap','path':'lab/wsl/gitops'},
        'syncPolicy':{'automated':{'enabled':True,'prune':False,'selfHeal':True,'allowEmpty':False},
                      'syncOptions':['CreateNamespace=false','RespectIgnoreDifferences=true']},
        'ignoreDifferences':[{'group':'postgresql.cnpg.io','kind':'Cluster','name':DB,'namespace':NS,
            'jsonPointers':['/spec/resources','/metadata/annotations/vcloud.io~1resources-last-scaled']}]},NS,'argoproj.io/v1alpha1')
    return [project,app]


def audit(objects):
    policy=copy.deepcopy(load_policy());pv=storage()[1]
    policy.setdefault('localPVs',{})[pv['metadata']['name']]={key:pv['spec'][key] for key in ('local','nodeAffinity','accessModes','volumeMode','storageClassName')}
    inspected=normalize_pods(objects)
    # Argo's served, non-deprecated CRD API has the literal v1alpha1 suffix.
    # Only its two locked/schema-validated kinds use this narrow generic check adaptation.
    for obj in inspected:
        if obj['apiVersion']=='argoproj.io/v1alpha1' and obj['kind'] in ('Application','AppProject'):obj['apiVersion']='argoproj.io/v1'
    problems=audit_objects(inspected,policy)['violations']
    if problems:raise ValueError('; '.join(problems))


def render(build,gitops=False):
    build.mkdir(parents=True,exist_ok=True)
    for name,objects in [('infrastructure.yaml',infrastructure()),('storage.yaml',storage()),('network.yaml',network()),
                         ('git-dns.yaml',git_dns()),('workload.yaml',workload()),('application.yaml',application())]:
        audit(objects);(build/name).write_text(yaml.safe_dump_all(objects,sort_keys=False),encoding='utf-8',newline='\n')
    if gitops:
        target=ROOT/'lab/wsl/gitops';target.mkdir(exist_ok=True)
        (target/'workload.yaml').write_bytes((build/'workload.yaml').read_bytes())
        (target/'network.yaml').write_text(yaml.safe_dump_all([o for o in network() if o['metadata']['name'] in ('vcloud-wsl-postgres','vcloud-wsl-db-scaler','vcloud-wsl-db-client')],sort_keys=False),encoding='utf-8',newline='\n')


def validate(build,kubeconform,schemas):
    lock=json.loads((ROOT/'lab/wsl/platform-artifacts.lock.json').read_text())
    for name,entry in lock['schemas'].items():
        if hashlib.sha256((ROOT/'lab/wsl/schemas'/name).read_bytes()).hexdigest()!=entry['sha256']:raise ValueError('Vendored Kubernetes schema differs')
    paths=[str(build/name) for name in ('infrastructure.yaml','storage.yaml','network.yaml','git-dns.yaml','workload.yaml','application.yaml')]
    schema_args=[]
    for path in [ROOT/'lab/wsl/schemas/{{.ResourceKind}}.json',Path(schemas)/'{{.ResourceKind}}.json',ROOT/'module-2/schemas/{{.Group}}/{{.ResourceKind}}_{{.ResourceAPIVersion}}.json',
                 ROOT/'module-2/schemas/{{.ResourceKind}}_{{.ResourceAPIVersion}}.json',ROOT/'module-4a/schemas/{{.ResourceKind}}_{{.ResourceAPIVersion}}.json']:
        schema_args+=['-schema-location',str(path)]
    subprocess.run([kubeconform,'-strict','-summary','-kubernetes-version','1.36.5',*schema_args,*paths],check=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('action',choices=['render','validate'])
    parser.add_argument('--build',type=Path,default=ROOT/'.build/wsl-platform');parser.add_argument('--gitops',action='store_true')
    parser.add_argument('--kubeconform',default='kubeconform');parser.add_argument('--schemas',default=str(ROOT/'.tools/ci-sources/schemas'))
    options=parser.parse_args()
    if options.action=='render':render(options.build,options.gitops)
    else:validate(options.build,options.kubeconform,options.schemas)
