#!/usr/bin/env python3
"""Render Module 5a references. GPU/ingestion examples are not installed."""
import argparse
import copy
import json
from pathlib import Path
import sys
import yaml

ROOT=Path(__file__).resolve().parents[1];MODULE=ROOT/'module-5a'
SECURITY={'runAsNonRoot':True,'runAsUser':65532,'runAsGroup':65532,
    'allowPrivilegeEscalation':False,'readOnlyRootFilesystem':True,
    'capabilities':{'drop':['ALL']},'seccompProfile':{'type':'RuntimeDefault'}}


def resource(kind,name,spec=None,namespace='workload-apps',api='v1',**fields):
    obj={'apiVersion':api,'kind':kind,'metadata':{'name':name,'namespace':namespace,
         'labels':{'app.kubernetes.io/part-of':'vcloud','vcloud.io/module':'5a'}}}
    if spec is not None:obj['spec']=spec
    obj.update(fields);return obj


def vllm():
    sa=resource('ServiceAccount','vcloud-vllm',namespace='hpc-compute',automountServiceAccountToken=False,
                imagePullSecrets=[{'name':'vcloud-registry-pull'}])
    pod={'serviceAccountName':'vcloud-vllm','automountServiceAccountToken':False,'runtimeClassName':'nvidia',
        'nodeSelector':{'vcloud.io/gpu-role':'inference','vcloud.io/gpu-profile':'spinifex.gpu.h100.80gb.8x'},
        'tolerations':[{'key':'vcloud.io/gpu-role','operator':'Equal','value':'inference','effect':'NoSchedule'}],
        'securityContext':{'runAsNonRoot':True,'runAsUser':65532,'runAsGroup':65532,'fsGroup':65532},
        'containerConcurrency':1,'timeoutSeconds':180,'responseStartTimeoutSeconds':150,
        'containers':[{'name':'vllm','image':'registry.vcloud.example.com/vllm/vllm-openai:v0.31.0','imagePullPolicy':'IfNotPresent',
            'command':['vllm','serve'],'args':['/models/deepseek-r1-distill-qwen-32b','--served-model-name','deepseek-r1-distill-qwen-32b',
                '--host','0.0.0.0','--port','8080','--tensor-parallel-size','1','--max-model-len','4096',
                '--gpu-memory-utilization','0.85','--reasoning-parser','deepseek_r1','--no-enable-log-requests','--no-enable-log-outputs'],
            'ports':[{'containerPort':8080}],'securityContext':copy.deepcopy(SECURITY),
            'resources':{'requests':{'cpu':'8','memory':'80Gi','nvidia.com/gpu':1},
                         'limits':{'cpu':'16','memory':'96Gi','nvidia.com/gpu':1}},
            'env':[{'name':k,'value':v} for k,v in {'HF_HUB_OFFLINE':'1','TRANSFORMERS_OFFLINE':'1','HOME':'/tmp',
                'XDG_CACHE_HOME':'/tmp/cache','VLLM_NO_USAGE_STATS':'1','DO_NOT_TRACK':'1'}.items()],
            'volumeMounts':[{'name':'models','mountPath':'/models','readOnly':True},{'name':'tmp','mountPath':'/tmp'},{'name':'shm','mountPath':'/dev/shm'}],
            'readinessProbe':{'httpGet':{'path':'/health','port':8080},'periodSeconds':10,'timeoutSeconds':5},
            'startupProbe':{'httpGet':{'path':'/health','port':8080},'periodSeconds':10,'timeoutSeconds':5,'failureThreshold':120}}],
        'volumes':[{'name':'models','persistentVolumeClaim':{'claimName':'vcloud-deepseek-models','readOnly':True}},
                   {'name':'tmp','emptyDir':{'medium':'Memory','sizeLimit':'2Gi'}},
                   {'name':'shm','emptyDir':{'medium':'Memory','sizeLimit':'8Gi'}}]}
    svc=resource('Service','vcloud-vllm',{'template':{'metadata':{'labels':{'app.kubernetes.io/name':'vcloud-vllm'},
        'annotations':{'autoscaling.knative.dev/min-scale':'0','autoscaling.knative.dev/max-scale':'1',
            'autoscaling.knative.dev/initial-scale':'0','autoscaling.knative.dev/target':'1'}},'spec':pod}},
        namespace='hpc-compute',api='serving.knative.dev/v1')
    svc['metadata']['labels']['networking.knative.dev/visibility']='cluster-local'
    return [sa,svc]


def integration():
    result=[]
    for name,path in [('vcloud-rag','vcloud-rag-query'),('vcloud-rag-indexer','vcloud-rag-ingest')]:
        result.append(resource('ServiceAccount',name,automountServiceAccountToken=False,imagePullSecrets=[{'name':'vcloud-registry-pull'}]))
        result.append(resource('SecretProviderClass',name,{'provider':'openbao','parameters':{
            'roleName':name,'baoAuthMountPath':'kubernetes','audience':'openbao',
            'objects':yaml.safe_dump([{'objectName':'database.json','secretPath':'database/creds/'+path,'filePermission':288}],sort_keys=False)}},
            api='secrets-store.csi.x-k8s.io/v1'))
    result.append(resource('ConfigMap','vcloud-rag-config',data={'rag.yaml':(MODULE/'config/rag.yaml').read_text(encoding='utf-8')}))
    return result


def jobs():
    result=[]
    for action,sa in [('query','vcloud-rag'),('ingest','vcloud-rag-indexer')]:
        # Activation also requires changing the accepted configuration. Neither
        # removing suspend nor applying examples can bypass enabled:false.
        args=['--config','/etc/vcloud/rag.yaml',action]
        args+=['--question','What does vCloud provide?'] if action=='query' else ['--documents','/input/documents.json']
        mounts=[{'name':'config','mountPath':'/etc/vcloud','readOnly':True},{'name':'database','mountPath':'/run/vcloud-secrets','readOnly':True},
            {'name':'trust','mountPath':'/var/run/vcloud/trust','readOnly':True},{'name':'models','mountPath':'/models','readOnly':True},
            {'name':'tmp','mountPath':'/tmp'}]
        volumes=[{'name':'config','configMap':{'name':'vcloud-rag-config'}},
            {'name':'database','csi':{'driver':'secrets-store.csi.k8s.io','readOnly':True,'volumeAttributes':{'secretProviderClass':sa}}},
            {'name':'trust','configMap':{'name':'vcloud-rag-public-trust'}},
            {'name':'models','persistentVolumeClaim':{'claimName':'vcloud-rag-embeddings','readOnly':True}},
            {'name':'tmp','emptyDir':{'medium':'Memory','sizeLimit':'64Mi'}}]
        if action=='ingest':
            mounts.append({'name':'input','mountPath':'/input','readOnly':True})
            volumes.append({'name':'input','configMap':{'name':'vcloud-rag-ingest-input'}})
        pod={'serviceAccountName':sa,'automountServiceAccountToken':False,'restartPolicy':'Never',
            'securityContext':{'runAsNonRoot':True,'runAsUser':65532,'runAsGroup':65532,'fsGroup':65532},
            'containers':[{'name':'rag','image':'registry.vcloud.example.com/vcloud/rag:1.0.0','imagePullPolicy':'IfNotPresent',
                'command':['python','/opt/vcloud/pipeline.py'],'args':args,'securityContext':copy.deepcopy(SECURITY),
                'resources':{'requests':{'cpu':'500m','memory':'1Gi'},'limits':{'cpu':'2','memory':'2Gi'}},
                'env':[{'name':k,'value':v} for k,v in {'HF_HUB_OFFLINE':'1','TRANSFORMERS_OFFLINE':'1','LANGSMITH_TRACING':'false',
                    'LANGCHAIN_TRACING_V2':'false','PYTHONDONTWRITEBYTECODE':'1','HOME':'/tmp','HF_HOME':'/tmp/hf','OMP_NUM_THREADS':'2'}.items()],
                'volumeMounts':mounts}],'volumes':volumes}
        result.append(resource('Job','vcloud-rag-'+action,{'suspend':True,'backoffLimit':0,'activeDeadlineSeconds':300,
            'template':{'metadata':{'labels':{'vcloud.io/component':'rag-'+action}},'spec':pod}},api='batch/v1'))
    return result


def network():
    def endpoint(ns,labels):return {'matchLabels':{'k8s:io.kubernetes.pod.namespace':ns}|labels}
    def ports(*values):return [{'ports':[{'port':str(p),'protocol':'TCP'} for p in values]}]
    def cnp(name,ns,selector,ingress=None,egress=None):
        spec={'endpointSelector':{'matchLabels':selector}}
        if ingress is not None:spec['ingress']=ingress
        if egress is not None:spec['egress']=egress
        return resource('CiliumNetworkPolicy',name,spec,ns,'cilium.io/v2')
    readers=[endpoint('workload-apps',{'k8s:vcloud.io/component':'rag-query'}),endpoint('workload-apps',{'k8s:vcloud.io/component':'rag-ingest'})]
    knative=[endpoint('platform-services',{'k8s:app':'activator'}),endpoint('platform-services',{'k8s:app':'3scale-kourier-gateway'})]
    dns={'toEndpoints':[endpoint('kube-system',{'k8s:k8s-app':'kube-dns'})],
         'toPorts':[{'ports':[{'port':'53','protocol':'UDP'},{'port':'53','protocol':'TCP'}]}]}
    pg={'toEndpoints':[endpoint('platform-services',{'k8s:cnpg.io/cluster':'vcloud-postgres'})],'toPorts':ports(5432)}
    result=[]
    for action in ['query','ingest']:
        egress=[dns,pg]
        if action=='query':egress.append({'toEndpoints':[knative[1]],'toPorts':ports(8443)})
        result.append(cnp('vcloud-rag-'+action,'workload-apps',{'vcloud.io/component':'rag-'+action},[],egress))
    result.append(cnp('vcloud-rag-db','platform-services',{'cnpg.io/cluster':'vcloud-postgres'},[{'fromEndpoints':readers,'toPorts':ports(5432)}]))
    result.append(cnp('vcloud-rag-knative-entry','platform-services',{'app':'3scale-kourier-gateway'},
        [{'fromEndpoints':[readers[0]],'toPorts':ports(8443)}],
        [{'toEndpoints':[endpoint('hpc-compute',{'k8s:serving.knative.dev/service':'vcloud-vllm'})],'toPorts':ports(8112)}]))
    # Module 2 allows these controllers to reach its CPU function only. Add
    # explicit HPC egress so scale-from-zero does not depend on Module 5b.
    for app,allowed in [('activator',(8112,)),('autoscaler',(9090,8022))]:
        result.append(cnp('vcloud-rag-'+app,'platform-services',{'app':app},egress=[
            {'toEndpoints':[endpoint('hpc-compute',{'k8s:serving.knative.dev/service':'vcloud-vllm'})],'toPorts':ports(*allowed)}]))
    result.append(cnp('vcloud-5a-vllm','hpc-compute',{'serving.knative.dev/service':'vcloud-vllm'},[
        {'fromEndpoints':knative,'toPorts':ports(8112)},
        {'fromEndpoints':[endpoint('platform-services',{'k8s:app':'autoscaler'})],'toPorts':ports(9090,8022)},
        {'fromEntities':['host'],'toPorts':ports(8080,8022)}],
        [{'toEndpoints':[endpoint('platform-services',{'k8s:app':'autoscaler'})],'toPorts':ports(8080)}]))
    return result


def secret_files():
    result={}
    base=json.loads((ROOT/'module-4a/openbao/database-role-vcloud-app-readonly.json').read_text())
    for identity,role,writer in [('vcloud-rag','vcloud-rag-query',False),('vcloud-rag-indexer','vcloud-rag-ingest',True)]:
        data=copy.deepcopy(base)
        if writer:data['creation_statements']=["SELECT vcloud_secret_lifecycle.create_rag_writer('{{name}}','{{password}}','{{expiration}}'::timestamptz);"]
        result['openbao/database-role-'+role+'.json']=json.dumps(data,indent=2)+'\n'
        result['openbao/kubernetes-role-'+identity+'.json']=json.dumps({'bound_service_account_names':[identity],
            'bound_service_account_namespaces':['workload-apps'],'audience':'openbao','token_policies':[identity],
            'token_ttl':'10m','token_max_ttl':'1h','token_no_default_policy':True,'token_type':'service','token_num_uses':0},indent=2)+'\n'
        result['openbao/'+identity+'.hcl']='path "database/creds/'+role+'" { capabilities = ["read"] }\n'
    return result


def files():
    encoded=lambda objects:'# Generated by tools/render_module5a.py; activation is a separate gate.\n'+yaml.safe_dump_all(objects,sort_keys=False)
    result={'examples/vllm.knative.yaml':encoded(vllm()),'examples/rag-jobs.yaml':encoded(jobs()),
        'manifests/integration.yaml':encoded(integration()),'manifests/network.yaml':encoded(network())}
    result.update(secret_files());return result


def main(check=False):
    drift=[]
    for relative,content in files().items():
        path=MODULE/relative
        if check:
            if not path.exists() or path.read_text(encoding='utf-8')!=content:drift.append(relative)
        else:path.parent.mkdir(parents=True,exist_ok=True);path.write_text(content,encoding='utf-8',newline='\n')
    if drift:raise ValueError('Module 5a render drift: '+', '.join(drift))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--check',action='store_true')
    main(parser.parse_args().check)
