#!/usr/bin/env python3
"""Generate the approved dev overlay and NoCloud seed from the shared Module -1. MIT."""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import re
import subprocess
import yaml
from platform_resources import ROOT,resource,security
from platform_sources import vendor
from manifest_contract import podspec

NS='twinfra-platform-services'
COMMON=ROOT/'deploy/common'
TARGET=ROOT/'deploy/environments/dev/cairo-1'
UPSTREAM_FIXED={'CustomResourceDefinition'}

def image(key): return json.loads((COMMON/'images.lock.json').read_text())['images'][key]['canonical']

def refresh_console_image(check=False):
    path=COMMON/'images.lock.json';data=json.loads(path.read_text())
    digest=json.loads((ROOT/'console/image.lock.json').read_text())['canonical'].split('@')[1]
    entry=data['images']['console']
    expected=dict(entry,source='docker.io/twinfra/twinfra-console@'+digest,
                  canonical='registry.twinfra.example.com/docker.io/twinfra/twinfra-console@'+digest,digest=digest)
    if check:
        if entry!=expected:raise ValueError('Dev console image lock differs from build receipt')
    else:
        data['images']['console']=expected
        path.write_text(json.dumps(data,indent=2)+'\n',encoding='utf-8')
def labels(component):return {'twinfra.io/environment':'dev','twinfra.io/region':'cairo-1','twinfra.io/component':component,'app.kubernetes.io/part-of':'twinfra'}
def obj(kind,name,spec=None,api='v1',ns=NS):
    value=resource(kind,name,spec,ns,api,labels(name.removeprefix('twinfra-')))
    return value
def config(name,data):
    value=obj('ConfigMap',name);value['data']=data;return value
def service(name,port,target=None):
    return obj('Service',name,{'selector':{'app.kubernetes.io/name':name},'ports':[{'name':'http','port':port,'targetPort':target or port}]})
def deployment(name,container,volumes=(),init=(),uid=65532):
    l=labels(name.removeprefix('twinfra-'))|{'app.kubernetes.io/name':name}
    for c in [container,*init]:
        c['securityContext']=security()|{'runAsUser':uid,'runAsGroup':uid};c['imagePullPolicy']='IfNotPresent'
        c.setdefault('resources',{'requests':{'cpu':'50m','memory':'128Mi'},'limits':{'cpu':'1','memory':'512Mi'}})
    return obj('Deployment',name,{'replicas':1,'strategy':{'type':'Recreate'},'selector':{'matchLabels':{'app.kubernetes.io/name':name}},
        'template':{'metadata':{'labels':l},'spec':{'automountServiceAccountToken':False,
        'securityContext':{'runAsNonRoot':True,'runAsUser':uid,'runAsGroup':uid,'fsGroup':uid,'seccompProfile':{'type':'RuntimeDefault'}},
        'containers':[container],'initContainers':list(init),'volumes':list(volumes),
        'topologySpreadConstraints':[{'maxSkew':1,'topologyKey':'topology.kubernetes.io/zone','whenUnsatisfiable':'ScheduleAnyway','labelSelector':{'matchLabels':{'app.kubernetes.io/name':name}}}]}}},'apps/v1')

def rename(value,mapping):
    if isinstance(value,dict):return {k:rename(v,mapping) for k,v in value.items()}
    if isinstance(value,list):return [rename(v,mapping) for v in value]
    if isinstance(value,str):
        for old,new in sorted(mapping.items(),key=lambda p:len(p[0]),reverse=True):
            value=re.sub(r'(?<![\w-])'+re.escape(old)+r'(?![\w-])',lambda _:new,value)
    return value

def controllers():
    raw=vendor(COMMON/'vendor',COMMON/'artifacts.lock.json','argocd-core.yaml')+vendor(COMMON/'vendor',COMMON/'artifacts.lock.json','cnpg.yaml')
    api=COMMON/'argocd-api.yaml';expected=json.loads((COMMON/'artifacts.lock.json').read_text())['argocd-api.yaml']['sha256']
    if hashlib.sha256(api.read_bytes()).hexdigest()!=expected:raise ValueError('Argo API source differs')
    raw+=list(yaml.safe_load_all(api.read_text()))
    raw=[o for o in raw if o and o['kind'] not in ('Namespace','NetworkPolicy') and 'applicationset-controller' not in o['metadata']['name']]
    names={o['metadata']['name'] for o in raw if o['kind'] not in UPSTREAM_FIXED}
    mapping={'argocd':NS,'cnpg-system':NS}
    result=[]
    cluster_kinds={'CustomResourceDefinition','ClusterRole','ClusterRoleBinding','MutatingWebhookConfiguration','ValidatingWebhookConfiguration'}
    for source in raw:
        o=copy.deepcopy(source);m=o['metadata']
        for binding in o.get('subjects',[]):
            if binding.get('namespace') in mapping:binding['namespace']=NS
        for webhook in o.get('webhooks',[]):
            if 'service' in webhook.get('clientConfig',{}):webhook['clientConfig']['service']['namespace']=NS
        if o['kind'] not in cluster_kinds:m['namespace']=NS
        spec=podspec(o)
        if spec:
            uid=10001 if 'cnpg' in m['name'] else 999
            o['spec']['replicas']=1
            spec['securityContext']={'runAsNonRoot':True,'runAsUser':uid,'runAsGroup':uid,'fsGroup':uid,'seccompProfile':{'type':'RuntimeDefault'}}
            spec.pop('imagePullSecrets',None)
            # ADR-0047 environment labels are added by Kustomize, selectors stay upstream.
            for c in spec.get('containers',[])+spec.get('initContainers',[]):
                c['image']=image('cnpg' if 'cnpg' in m['name'] else 'argocd')
                c['imagePullPolicy']='IfNotPresent';c['securityContext']=security()|{'runAsUser':uid,'runAsGroup':uid}
                c['resources']={'requests':{'cpu':'100m','memory':'128Mi'},'limits':{'cpu':'1','memory':'512Mi'}}
            if m['name']=='argocd-redis':
                spec.pop('initContainers',None);spec['automountServiceAccountToken']=False
                c=spec['containers'][0];c.pop('env',None);c.pop('args',None);c['image']=image('valkey')
                c['command']=['sh','-ec',"umask 077; printf 'requirepass %s\\n' \"$(cat /auth/auth)\" > /tmp/valkey.conf; exec valkey-server /tmp/valkey.conf --save '' --appendonly no"]
                c['volumeMounts']=[{'name':'auth','mountPath':'/auth','readOnly':True},{'name':'tmp','mountPath':'/tmp'}]
                spec['volumes']=[{'name':'auth','secret':{'secretName':'twinfra-argocd-cache','defaultMode':0o440}},{'name':'tmp','emptyDir':{'medium':'Memory','sizeLimit':'16Mi'}}]
            for c in spec.get('containers',[])+spec.get('initContainers',[]):
                for env in c.get('env',[]):
                    ref=env.get('valueFrom',{}).get('secretKeyRef',{})
                    if ref.get('name')=='argocd-redis':ref['name']='twinfra-argocd-cache'
            if 'cnpg' in m['name']:spec['containers'][0].setdefault('env',[]).append({'name':'WATCH_NAMESPACE','value':NS})
        if o['kind']=='ConfigMap' and m['name']=='argocd-cmd-params-cm':
            o['data']={'controller.repo.server':'argocd-repo-server:8081','server.repo.server':'argocd-repo-server:8081',
                'controller.status.processors':'2','controller.operation.processors':'1','reposerver.parallelism.limit':'2',
                'redis.server':'argocd-redis:6379','server.insecure':'false'}
        result.append(o)
    return result

def database():
    lock=json.loads((COMMON/'images.lock.json').read_text())['images']['postgres']
    pg=obj('Cluster','twinfra-postgres',{'instances':1,'imageName':lock['canonical'],'imagePullPolicy':'IfNotPresent','postgresUID':26,'postgresGID':26,
        'inheritedMetadata':{'labels':labels('postgres')},
        'enableSuperuserAccess':False,'seccompProfile':{'type':'RuntimeDefault'},
        'managed':{'roles':[{'name':n,'ensure':'present','login':True,'superuser':False,'createdb':False,'createrole':False,'passwordSecret':{'name':'twinfra-'+n+'-db'}} for n in ('keycloak','openbao')]},
        'bootstrap':{'initdb':{'database':'twinfra','owner':'twinfra_app','postInitApplicationSQL':['CREATE EXTENSION IF NOT EXISTS vector;']}},
        'postgresql':{'parameters':{'shared_buffers':'256MB','max_connections':'100','huge_pages':'off'},'pg_hba':['hostnossl all all all reject','hostssl all all all scram-sha-256']},
        'resources':{'requests':{'cpu':'500m','memory':'1Gi'},'limits':{'cpu':'1','memory':'2Gi'}},
        'storage':{'storageClass':'twinfra-local','size':'20Gi','resizeInUseVolumes':False},
        'affinity':{'enablePodAntiAffinity':True,'podAntiAffinityType':'preferred','topologyKey':'topology.kubernetes.io/zone'}},'postgresql.cnpg.io/v1')
    sc=obj('StorageClass','twinfra-local',ns=None,api='storage.k8s.io/v1');sc.update(provisioner='kubernetes.io/no-provisioner',volumeBindingMode='WaitForFirstConsumer',reclaimPolicy='Retain')
    pv=obj('PersistentVolume','twinfra-postgres-1',{'capacity':{'storage':'20Gi'},'volumeMode':'Filesystem','accessModes':['ReadWriteOnce'],
        'persistentVolumeReclaimPolicy':'Retain','storageClassName':'twinfra-local','claimRef':{'namespace':NS,'name':'twinfra-postgres-1'},
        'local':{'path':'/var/lib/twinfra/local-pv/postgres-1'},'nodeAffinity':{'required':{'nodeSelectorTerms':[{'matchExpressions':[{'key':'kubernetes.io/hostname','operator':'In','values':['twinfra-node']}]}]}}},ns=None)
    pv['metadata']['annotations']={'twinfra.io/vetted':'true','twinfra.io/vetting-document':'docs/dev-environment.md','argocd.argoproj.io/sync-options':'Prune=false,Delete=false'}
    return [sc,pv,pg]+[obj('Database','twinfra-'+n,{'cluster':{'name':'twinfra-postgres'},'name':n,'owner':n,'ensure':'present','databaseReclaimPolicy':'retain'},'postgresql.cnpg.io/v1') for n in ('keycloak','openbao')]

def endpoints():
    result=[config('twinfra-runtime-config',{'runtime-config.py':(COMMON/'runtime-config.py').read_text()}),
        config('twinfra-keycloak-realm',{'twinfra-realm.json':(COMMON/'keycloak-realm.json').read_text()})]
    for name in ('openbao','keycloak'):
        full='twinfra-'+name
        volumes=[{'name':'auth','secret':{'secretName':full+'-db','defaultMode':0o440}},
            {'name':'tls','secret':{'secretName':full+'-tls','defaultMode':0o440}},
            {'name':'pg-ca','secret':{'secretName':'twinfra-postgres-ca','defaultMode':0o440}},
            {'name':'code','configMap':{'name':'twinfra-runtime-config'}},
            {'name':'runtime','emptyDir':{'medium':'Memory','sizeLimit':'8Mi'}},{'name':'tmp','emptyDir':{'medium':'Memory','sizeLimit':'32Mi'}}]
        mounts=[{'name':v['name'],'mountPath':'/'+v['name'],'readOnly':v['name'] not in ('runtime','tmp')} for v in volumes]
        init=[{'name':'config','image':image('python'),'command':['python','/code/runtime-config.py',name],'volumeMounts':mounts}]
        c={'name':name,'image':image(name),'volumeMounts':mounts}
        if name=='openbao':
            c.update(command=['bao','server','-config=/runtime/openbao.hcl'],readinessProbe={'httpGet':{'path':'/v1/sys/init','port':8200,'scheme':'HTTPS'}})
            result.append(service(full,8200))
        else:
            volumes.append({'name':'admin','secret':{'secretName':'twinfra-keycloak-admin','defaultMode':0o440}})
            init[-1]['volumeMounts'].extend([{'name':'admin','mountPath':'/admin','readOnly':True},{'name':'realm','mountPath':'/realm-source','readOnly':True},{'name':'import','mountPath':'/import'},{'name':'oidc','mountPath':'/oidc','readOnly':True}])
            volumes += [{'name':'import','emptyDir':{'medium':'Memory','sizeLimit':'8Mi'}},{'name':'oidc','secret':{'secretName':'twinfra-console-oidc','defaultMode':0o440}},{'name':'realm','configMap':{'name':'twinfra-keycloak-realm'}},{'name':'data','emptyDir':{'medium':'Memory','sizeLimit':'128Mi'}},{'name':'quarkus','emptyDir':{'medium':'Memory','sizeLimit':'256Mi'}}]
            init.insert(0,{'name':'prepare','image':image('keycloak'),'command':['sh','-ec','cp -R /opt/keycloak/lib/quarkus/. /built/'],'volumeMounts':[{'name':'quarkus','mountPath':'/built'}]})
            c['volumeMounts']=mounts+[{'name':'import','mountPath':'/opt/keycloak/data/import','readOnly':True},{'name':'data','mountPath':'/opt/keycloak/data'},{'name':'quarkus','mountPath':'/opt/keycloak/lib/quarkus'}]
            c.update(command=['/opt/keycloak/bin/kc.sh'],args=['--config-file=/runtime/keycloak.conf','start','--import-realm'],
                resources={'requests':{'cpu':'250m','memory':'768Mi'},'limits':{'cpu':'2','memory':'2Gi'}},
                startupProbe={'httpGet':{'path':'/health/started','port':9000,'scheme':'HTTPS'},'failureThreshold':90,'periodSeconds':5},
                readinessProbe={'httpGet':{'path':'/health/ready','port':9000,'scheme':'HTTPS'}})
            result.append(service(full,443,8443))
        result.append(deployment(full,c,volumes,init))
    mini={'name':'ministack','image':image('ministack'),'ports':[{'containerPort':4566}],
        'env':[{'name':'HOME','value':'/tmp'},{'name':'MINISTACK_PERSIST','value':'0'},{'name':'PYTHONDONTWRITEBYTECODE','value':'1'}],
        'readinessProbe':{'tcpSocket':{'port':4566}},'volumeMounts':[{'name':'tmp','mountPath':'/tmp'},{'name':'home','mountPath':'/home'}]}
    result += [deployment('twinfra-ministack',mini,[{'name':'tmp','emptyDir':{'medium':'Memory','sizeLimit':'64Mi'}},{'name':'home','emptyDir':{'medium':'Memory','sizeLimit':'64Mi'}}]),service('twinfra-ministack',4566)]
    return result

def portal():
    p=yaml.safe_load((ROOT/'vcloud-ssot.yaml').read_text())['environments']['dev']
    issuer='https://auth.dev.cairo-1.twinfra.example.com:18443/realms/twinfra'
    env={'OIDC_ISSUER':issuer,'OIDC_CLIENT':'twinfra-console','OIDC_JWKS_URL':'https://twinfra-keycloak.twinfra-platform-services.svc.cluster.local/realms/twinfra/protocol/openid-connect/certs',
        'KEYCLOAK_ADMIN_URL':'https://auth.dev.cairo-1.twinfra.example.com:18443/admin/twinfra/console/',
        'PLATFORM_NAMESPACE':NS,'PLATFORM_ENVIRONMENT':'dev','PLATFORM_REGION':p['region'],'PLATFORM_BACKENDS':'ministack','PLATFORM_DEFAULT_BACKEND':'ministack',
        'PLATFORM_SERVICE_ACCOUNT_PATH':'/var/run/secrets/twinfra','MINISTACK_ENDPOINT':'http://twinfra-ministack.twinfra-platform-services.svc.cluster.local:4566'}
    sa=obj('ServiceAccount','twinfra-console');sa['automountServiceAccountToken']=False
    role=obj('Role','twinfra-console-reader',api='rbac.authorization.k8s.io/v1');role['rules']=[{'apiGroups':[g],'resources':r,'verbs':['get','list']} for g,r in [('', ['pods']),('apps',['deployments']),('argoproj.io',['applications'])]]
    binding=obj('RoleBinding','twinfra-console-reader',api='rbac.authorization.k8s.io/v1');binding.update(roleRef={'apiGroup':'rbac.authorization.k8s.io','kind':'Role','name':role['metadata']['name']},subjects=[{'kind':'ServiceAccount','name':'twinfra-console','namespace':NS}])
    c={'name':'console','image':image('console'),'env':[{'name':k,'value':v} for k,v in env.items()],
        'volumeMounts':[{'name':'identity','mountPath':'/var/run/secrets/twinfra','readOnly':True},{'name':'oidc-trust','mountPath':'/oidc-trust','readOnly':True}],
        'readinessProbe':{'httpGet':{'path':'/healthz','port':3000}}}
    volumes=[{'name':'identity','projected':{'defaultMode':0o440,'sources':[{'serviceAccountToken':{'path':'token','expirationSeconds':3600}},{'configMap':{'name':'kube-root-ca.crt','items':[{'key':'ca.crt','path':'ca.crt'}]}}]}},
        {'name':'oidc-trust','secret':{'secretName':'twinfra-keycloak-tls','items':[{'key':'ca.crt','path':'tls.crt'}],'defaultMode':0o440}}]
    d=deployment('twinfra-console',c,volumes);d['spec']['template']['spec']['serviceAccountName']='twinfra-console'
    return [sa,role,binding,d,service('twinfra-console',3000)]

def gateway():
    # Standalone APISIX consumes a complete declarative snapshot; no admin API/controller/etcd needed.
    cm=config('twinfra-gateway',{'config.yaml':yaml.safe_dump({'apisix':{'node_listen':[],'enable_admin':False,'enable_ipv6':False,'ssl':{'enable':True,'listen':[{'port':9443}],
        'ssl_cert':'/tls/tls.crt','ssl_cert_key':'/tls/tls.key','ssl_trusted_certificate':'/oidc-trust/tls.crt'}},
        'nginx_config':{'worker_processes':1,'error_log':'/dev/stderr','http':{'access_log':'/dev/stdout','access_log_format':'$remote_addr $request_method $uri $status'}},
        'deployment':{'role':'data_plane','role_data_plane':{'config_provider':'yaml'}}}),
        'apisix.template.json':(COMMON/'apisix-routes.json').read_text(),'configure.py':(COMMON/'gateway-config.py').read_text()})
    volumes=[{'name':'source','configMap':{'name':'twinfra-gateway'}},{'name':'conf','emptyDir':{'medium':'Memory','sizeLimit':'32Mi'}},
        {'name':'auth','secret':{'secretName':'twinfra-console-oidc','defaultMode':0o440}},
        {'name':'tls','secret':{'secretName':'twinfra-gateway-tls','defaultMode':0o440}},
        {'name':'oidc-trust','secret':{'secretName':'twinfra-keycloak-tls','items':[{'key':'ca.crt','path':'tls.crt'}],'defaultMode':0o440}},
        {'name':'tmp','emptyDir':{'medium':'Memory','sizeLimit':'32Mi'}},{'name':'logs','emptyDir':{'medium':'Memory','sizeLimit':'16Mi'}}]
    init=[{'name':'prepare','image':image('apisix'),'command':['sh','-ec','cp -R /usr/local/apisix/conf/. /conf/'],'volumeMounts':[{'name':'conf','mountPath':'/conf'}]},
        {'name':'config','image':image('python'),'command':['python','/source/configure.py'],'volumeMounts':[{'name':'source','mountPath':'/source','readOnly':True},{'name':'auth','mountPath':'/auth','readOnly':True},{'name':'tls','mountPath':'/tls','readOnly':True},{'name':'conf','mountPath':'/conf'}]}]
    c={'name':'gateway','image':image('apisix'),'command':['sh','-ec','apisix init; exec /usr/local/openresty/bin/openresty -p /usr/local/apisix -c conf/nginx.conf -g "daemon off;"'],
        'volumeMounts':[{'name':'conf','mountPath':'/usr/local/apisix/conf'},{'name':'tls','mountPath':'/tls','readOnly':True},{'name':'oidc-trust','mountPath':'/oidc-trust','readOnly':True},{'name':'tmp','mountPath':'/tmp'},{'name':'logs','mountPath':'/usr/local/apisix/logs'}],
        'readinessProbe':{'tcpSocket':{'port':9443}}}
    # Scratch paths required by OpenResty stay isolated from the immutable root.
    for path in ('client_body_temp','proxy_temp','fastcgi_temp','uwsgi_temp','scgi_temp'):
        name=path.replace('_','-');volumes.append({'name':name,'emptyDir':{'medium':'Memory','sizeLimit':'8Mi'}});c['volumeMounts'].append({'name':name,'mountPath':'/usr/local/apisix/'+path})
    return [cm,deployment('twinfra-gateway',c,volumes,init),service('twinfra-gateway',9443)]

def network():
    def ports(*p):return [{'ports':[{'port':str(n),'protocol':'TCP'} for n in p]}]
    def peer(name):return {'matchLabels':{'k8s:io.kubernetes.pod.namespace':NS,'k8s:app.kubernetes.io/name':name}}
    policies=[obj('NetworkPolicy','twinfra-default-deny',{'podSelector':{},'policyTypes':['Ingress','Egress'],'ingress':[],'egress':[]},'networking.k8s.io/v1')]
    dns={'toEndpoints':[{'matchLabels':{'k8s:io.kubernetes.pod.namespace':'kube-system','k8s:k8s-app':'kube-dns'}}],'toPorts':[{'ports':[{'port':'53','protocol':'ANY'}],'rules':{'dns':[{'matchPattern':'*'}]}}]}
    api={'toEntities':['kube-apiserver'],'toPorts':ports(443,6443)}
    edges=[('twinfra-console','twinfra-ministack',4566),('twinfra-console','twinfra-keycloak',8443),('twinfra-gateway','twinfra-console',3000),('twinfra-gateway','twinfra-keycloak',8443),
        ('twinfra-keycloak','twinfra-postgres',5432),('twinfra-openbao','twinfra-postgres',5432),
        ('argocd-application-controller','argocd-repo-server',8081),('argocd-server','argocd-repo-server',8081),
        ('argocd-application-controller','argocd-redis',6379),('argocd-repo-server','argocd-redis',6379),('argocd-server','argocd-redis',6379)]
    # CNPG/Argo use upstream recommended selectors; database pods use operator-generated identity.
    selectors={o['metadata']['name']:o['spec']['template']['metadata']['labels'] for o in controllers() if podspec(o)}
    def select(name):
        if name=='twinfra-postgres':return {'matchLabels':{'k8s:io.kubernetes.pod.namespace':NS,'k8s:cnpg.io/cluster':name}}
        keys=selectors.get(name)
        if keys:return {'matchLabels':{'k8s:io.kubernetes.pod.namespace':NS,**{'k8s:'+k:v for k,v in keys.items() if k in ('app.kubernetes.io/name','app')}}}
        return peer(name)
    cnpg=next(o['metadata']['name'] for o in controllers() if o['kind']=='Deployment' and 'cnpg' in o['metadata']['name'])
    edges += [(cnpg,'twinfra-postgres',8000),(cnpg,'twinfra-postgres',5432)]
    for name in sorted({v for a,b,_ in edges for v in (a,b)}):
        ingress=[{'fromEndpoints':[select(a)],'toPorts':ports(p)} for a,b,p in edges if b==name]
        probe_ports={'argocd-repo-server':8084,'argocd-application-controller':8082,'argocd-server':8080,'twinfra-console':3000,'twinfra-keycloak':9000,'twinfra-openbao':8200,'twinfra-ministack':4566,'twinfra-gateway':9443,'twinfra-postgres':8000,cnpg:9443}
        if name in probe_ports:ingress.append({'fromEntities':['host','remote-node','health'],'toPorts':ports(probe_ports[name])})
        if name=='twinfra-keycloak':ingress.append({'fromEntities':['host','remote-node'],'toPorts':ports(8443)})
        if name==cnpg:ingress.append({'fromEntities':['kube-apiserver'],'toPorts':ports(9443)})
        egress=[dns]+[{'toEndpoints':[select(b)],'toPorts':ports(p)} for a,b,p in edges if a==name]
        if name in (cnpg,'twinfra-postgres','twinfra-console','argocd-server','argocd-application-controller'):egress.append(api)
        if name=='argocd-repo-server':egress.append({'toFQDNs':[{'matchName':'github.com'}],'toPorts':ports(443)})
        policies.append(obj('CiliumNetworkPolicy','twinfra-'+name.removeprefix('twinfra-')+'-network',{'endpointSelector':select(name),'ingress':ingress,'egress':egress},'cilium.io/v2'))
    return policies

def applications():
    project=obj('AppProject','twinfra-dev',{'sourceRepos':['https://github.com/amazen33/twinfra.git'],'destinations':[{'server':'https://kubernetes.default.svc','namespace':NS}],
        'clusterResourceWhitelist':[{'group':'*','kind':'*'}],'namespaceResourceWhitelist':[{'group':'*','kind':'*'}]},'argoproj.io/v1alpha1')
    def app(name,path,wave):
        a=obj('Application',name,{'project':'twinfra-dev','destination':{'server':'https://kubernetes.default.svc','namespace':NS},
            'source':{'repoURL':'https://github.com/amazen33/twinfra.git','targetRevision':'main','path':path},
            'syncPolicy':{'automated':{'enabled':True,'prune':False,'selfHeal':True,'allowEmpty':False},'syncOptions':['ServerSideApply=true','CreateNamespace=false']}},'argoproj.io/v1alpha1')
        a['metadata']['annotations']={'argocd.argoproj.io/sync-wave':str(wave)};return a
    return [project,app('twinfra-root','deploy/environments/dev/cairo-1/apps',0)], [app('twinfra-platform','deploy/environments/dev/cairo-1/platform',0),app('twinfra-services','deploy/environments/dev/cairo-1/services',10)]

def seed(row):
    from render_cloud_init import rendered
    data=yaml.safe_load(rendered());env=next(v for v in data['write_files'] if v['path']=='/etc/vcloud-host.env')
    values={'PLATFORM_PROFILE':'dev-'+row['region'],'CLUSTER_NAME':'twinfra-dev-'+row['region'],'CLUSTER_DNS_NAME':'twinfra-dev-'+row['region'],
        'BASE_DOMAIN':'twinfra.example.com','IMAGE_REGISTRY':'registry.twinfra.example.com','REGISTRY_MIRROR':'https://registry.twinfra.example.com',
        'POD_CIDR':row['podCidr'],'SERVICE_CIDR':row['serviceCidr'],'NODE_IP':row['ipAddress'],'NODE_NAME':'twinfra-node',
        'CONTROL_PLANE_ENDPOINT':'api.dev.'+row['region']+'.twinfra.example.com:6443','BOOTSTRAP_K8S':'true','INSTALL_HPC':'false','ENABLE_GPU':'false','GPU_SMOKE_TEST':'false','RUN_SMOKE_TESTS':'false','IMAGE_STAGING':'true'}
    raw=env['content']
    for key,value in values.items():
        pattern=r'(?m)^'+key+r'=.*$';line=key+'='+value
        raw=re.sub(pattern,line,raw) if re.search(pattern,raw) else raw+line+'\n'
    env['content']=raw;env['path']='/etc/twinfra-host.env'
    data['write_files'] += [{'path':'/etc/twinfra/bootstrap-images.lock.json','permissions':'0644','content':(COMMON/'bootstrap-images.lock.json').read_text()},
        {'path':'/usr/local/lib/twinfra/stage-images.py','permissions':'0644','content':(COMMON/'stage-images.py').read_text()}]
    for file in data['write_files']:
        if file['path']=='/etc/systemd/system/vcloud-host-bootstrap.service':
            file['content']=file['content'].replace('[Service]\n','[Service]\nEnvironment=VCLOUD_CONFIG_FILE=/etc/twinfra-host.env\n')
    for command in data.get('runcmd',[]):
        if isinstance(command,list):
            for i,arg in enumerate(command):
                if isinstance(arg,str) and '00-setup-ubuntu-host.sh --apply' in arg:
                    command[i]='VCLOUD_CONFIG_FILE=/etc/twinfra-host.env '+arg
    data['users']=[{'name':'twinfra-operator','sudo':['ALL=(ALL) NOPASSWD:ALL'],'shell':'/bin/bash','lock_passwd':True,'ssh_authorized_keys':['@@SSH_PUBLIC_KEY@@']}]
    data['ssh_pwauth']=False;data['hostname']='twinfra-dev-'+row['region'];data['manage_etc_hosts']=True
    data['write_files'] += [{'path':'/etc/hosts','append':True,'permissions':'0644','content':row['ipAddress']+' api.dev.'+row['region']+'.twinfra.example.com\n'},
        {'path':'/etc/systemd/system/twinfra-node-zone.service','permissions':'0644','content':'[Unit]\nAfter=kubelet.service\n[Service]\nType=oneshot\nExecStart=/usr/bin/kubectl --kubeconfig=/etc/kubernetes/admin.conf label node twinfra-node topology.kubernetes.io/zone='+row['region']+'a twinfra.io/environment=dev twinfra.io/region='+row['region']+' --overwrite\n[Install]\nWantedBy=multi-user.target\n'}]
    profile_script="#!/usr/bin/env bash\nset -Eeuo pipefail\nexport KUBECONFIG=/etc/kubernetes/admin.conf\nkubectl label node twinfra-node topology.kubernetes.io/zone="+row['region']+"a twinfra.io/environment=dev twinfra.io/region="+row['region']+" --overwrite\n"
    data['write_files'].append({'path':'/usr/local/sbin/twinfra-node-profile.sh','permissions':'0755','content':profile_script})
    zone=next(f for f in data['write_files'] if f['path']=='/etc/systemd/system/twinfra-node-zone.service')
    zone['content']='[Unit]\nAfter=kubelet.service\nStartLimitIntervalSec=0\n[Service]\nType=oneshot\nExecStart=/usr/local/sbin/twinfra-node-profile.sh\nRestart=on-failure\nRestartSec=30\n[Install]\nWantedBy=multi-user.target\n'
    data['runcmd'] += [['systemctl','enable','--now','twinfra-node-zone.service']]
    network={'version':2,'ethernets':{'eth0':{'match':{'name':'e*'},'set-name':'eth0','dhcp4':False,'addresses':[row['ipAddress']+'/24'],
        'routes':[{'to':'default','via':'10.50.0.1'}],'nameservers':{'addresses':['1.1.1.1','9.9.9.9']}}}}
    return {'user-data':'#cloud-config\n'+yaml.safe_dump(data,sort_keys=False),'meta-data':yaml.safe_dump({'instance-id':'twinfra-dev-'+row['region'],'local-hostname':'twinfra-dev-'+row['region']}),
        'network-config':yaml.safe_dump(network,sort_keys=False)}

def outputs():
    ssot=yaml.safe_load((ROOT/'vcloud-ssot.yaml').read_text());root,children=applications()
    namespace=obj('Namespace',NS,ns=None);namespace['metadata']['labels'].update({'pod-security.kubernetes.io/enforce':'restricted','pod-security.kubernetes.io/enforce-version':'v1.30','pod-security.kubernetes.io/audit':'restricted','pod-security.kubernetes.io/warn':'restricted'})
    result={TARGET/'root.yaml':yaml.safe_dump_all(root,sort_keys=False),TARGET/'apps/applications.yaml':yaml.safe_dump_all(children,sort_keys=False),
        TARGET/'platform/workloads.yaml':yaml.safe_dump_all([namespace]+controllers()+database()+network(),sort_keys=False),
        TARGET/'services/workloads.yaml':yaml.safe_dump_all(endpoints()+portal()+gateway(),sort_keys=False)}
    for folder,component in [('platform','platform'),('services','services')]:
        result[TARGET/folder/'kustomization.yaml']=yaml.safe_dump({'apiVersion':'kustomize.config.k8s.io/v1beta1','kind':'Kustomization','resources':['workloads.yaml'],'labels':[{'pairs':{k:v for k,v in labels(component).items() if k.startswith('twinfra.io/')},'includeSelectors':False,'includeTemplates':True}]},sort_keys=False)
    for row in ssot['addressPlan']:
        if row['environment']=='dev':
            for name,text in seed(row).items():result[ROOT/'deploy/environments/dev'/row['region']/'seed'/name]=text
    return result

def main():
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=['render','check','stage-images'])
    parser.add_argument('--context');parser.add_argument('--ssh');parser.add_argument('--check',action='store_true');parser.add_argument('--archive-dir',type=Path)
    args=parser.parse_args()
    if args.action=='stage-images':
        from platform_image_staging import stage_applications
        if not args.context or not args.ssh:parser.error('stage-images requires --context and --ssh')
        report=stage_applications(args.context,args.ssh,args.check,args.archive_dir)
        for problem in report['problems']:print(problem['name']+': '+problem['reason']+' ('+problem['image']+')')
        print('PASS: all application images verified' if not report['problems'] else 'FAIL: application image cache incomplete')
        return int(bool(report['problems']))
    refresh_console_image(check=args.action=='check')
    for path,raw in outputs().items():
        if args.action=='check':
            if not path.exists() or path.read_text()!=raw:raise ValueError('Dev render drift: '+str(path))
        else:path.parent.mkdir(parents=True,exist_ok=True);path.write_text(raw,encoding='utf-8',newline='\n')
    print('PASS: dev profile '+args.action+'; no live actions')
if __name__=='__main__':raise SystemExit(main())
