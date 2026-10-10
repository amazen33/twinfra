#!/usr/bin/env python3
"""Frozen CPU-only WSL identity, gateway, Knative and observability profile."""
import argparse
import copy
import gzip
import hashlib
import ipaddress
import json
from functools import lru_cache
from pathlib import Path
import subprocess
import yaml
from wsl_platform import ROOT,NS,DB,PYTHON,resource,cnp,ports,peers,audit,vendor as platform_vendor
from wsl_lab import security
from manifest_contract import podspec

HERE=ROOT/'lab/wsl/endpoints'
APP_NS='workload-apps'

class KubernetesLoader(yaml.SafeLoader):pass
KubernetesLoader.add_constructor('tag:yaml.org,2002:value',KubernetesLoader.construct_scalar)


def image(key):return json.loads((HERE/'artifacts.lock.json').read_text())['images'][key]['canonical']


def vendor(name):
    lock=json.loads((HERE/'artifacts.lock.json').read_text())['files'][name]
    compressed=(HERE/'vendor'/(name+'.gz')).read_bytes()
    if hashlib.sha256(compressed).hexdigest()!=lock['gzipSHA256']:raise ValueError('Vendor digest differs')
    raw=gzip.decompress(compressed)
    if hashlib.sha256(raw).hexdigest()!=lock['sourceSHA256']:raise ValueError('Vendor source digest differs')
    return [o for o in yaml.load_all(raw,Loader=KubernetesLoader) if o]


def relocate(value,ns):
    if isinstance(value,dict):
        for k,v in list(value.items()):
            if k=='namespace' and v in ('knative-serving','kourier-system','default'):value[k]=ns
            elif isinstance(v,str):value[k]=v.replace('.knative-serving','.'+ns).replace('.kourier-system','.'+ns)
            else:relocate(v,ns)
    elif isinstance(value,list):
        for v in value:relocate(v,ns)


@lru_cache(maxsize=1)
def controllers():
    result=[]
    for filename in ('serving-core.yaml','kourier.yaml','prometheus-operator.yaml'):
        ns=NS if filename=='prometheus-operator.yaml' else APP_NS
        for obj in vendor(filename):
            if obj['kind'] in ('Namespace','HorizontalPodAutoscaler'):continue
            relocate(obj,ns)
            spec=podspec(obj)
            if spec:
                name=obj['metadata']['name']
                component='prometheus-operator' if ns==NS else 'knative'
                obj['spec']['template']['metadata'].setdefault('labels',{})['vcloud.io/component']=component
                spec['securityContext']={'runAsNonRoot':True,'runAsUser':65532,'runAsGroup':65532,
                                         'fsGroup':65532,'seccompProfile':{'type':'RuntimeDefault'}}
                spec.setdefault('volumes',[]).append({'name':'vcloud-tmp','emptyDir':{'medium':'Memory','sizeLimit':'32Mi'}})
                for c in spec.get('containers',[])+spec.get('initContainers',[]):
                    if ns==NS:key=c['name']
                    elif filename=='kourier.yaml' and c['name']=='controller':key='knative-kourier-control'
                    else:key='knative-'+c['name']
                    c['image']=image(key);c['imagePullPolicy']='IfNotPresent';c['securityContext']=security()
                    c['resources']={'requests':{'cpu':'50m','memory':'64Mi'},'limits':{'cpu':'500m','memory':'256Mi'}}
                    mounts=c.setdefault('volumeMounts',[])
                    if not any(m['mountPath']=='/tmp' for m in mounts):mounts.append({'name':'vcloud-tmp','mountPath':'/tmp'})
                    for e in c.get('env',[]):
                        if e.get('value') in ('knative-serving','kourier-system'):e['value']=ns
                    if key=='prometheus-operator':
                        c['args']=[a for a in c.get('args',[]) if not a.startswith('--prometheus-config-reloader=')]
                        c['args'].append('--prometheus-config-reloader='+image('prometheus-config-reloader'))
                if obj['kind']=='Deployment':obj['spec']['replicas']=1
            if obj['kind']=='Service' and obj['metadata']['name']=='kourier':obj['spec']['type']='ClusterIP'
            # Knative's webhook controller owns discovery-generated rules and
            # CA bundles. Leave those fields to it on first and repeated apply.
            if obj['kind'] in ('MutatingWebhookConfiguration','ValidatingWebhookConfiguration'):
                for webhook in obj.get('webhooks',[]):
                    webhook.pop('rules',None);webhook.get('clientConfig',{}).pop('caBundle',None)
            if obj['kind']=='ConfigMap':
                name=obj['metadata']['name'];data=obj.setdefault('data',{})
                if name=='config-deployment':data['queue-sidecar-image']=image('knative-queue-proxy');data['registries-skipping-tag-resolving']='registry.vcloud.example.com'
                if name=='config-domain':obj['data']={'vcloud.example.com':''}
                if name=='config-network':data['ingress-class']='kourier.ingress.networking.knative.dev'
                if name=='config-features':data['kubernetes.podspec-securitycontext']='enabled'
                if name=='config-observability':
                    data.update({'metrics-protocol':'prometheus','metrics-endpoint':'0.0.0.0:9090',
                                 'request-metrics-protocol':'prometheus','request-metrics-endpoint':'0.0.0.0:9091',
                                 'runtime-profiling':'disabled'})
                if name=='kourier-bootstrap':
                    for key,value in data.items():data[key]=value.replace('address: ::','address: 0.0.0.0').replace('address: "::"','address: "0.0.0.0"').replace('ipv4_compat: true','ipv4_compat: false')
            result.append(obj)
    observations=next(o['data'] for o in result if o['kind']=='ConfigMap' and o['metadata']['name']=='config-observability')
    for obj in result:
        if obj['kind']=='Deployment' and obj['metadata']['namespace']==APP_NS and obj['metadata']['name']!='3scale-kourier-gateway':
            obj['spec']['template']['metadata'].setdefault('annotations',{})['vcloud.io/observability-hash']=hashlib.sha256(json.dumps(observations,sort_keys=True).encode()).hexdigest()
    return result


def config(name,data,ns=NS):
    obj=resource('ConfigMap',name,namespace=ns);obj['data']=data;return obj


def service(name,port,target=None,ns=NS,labels=None):
    labels=labels or {'app.kubernetes.io/name':name}
    return resource('Service',name,{'selector':labels,'ports':[{'name':'http','port':port,'targetPort':target or port}]},ns,labels=labels)


def deployment(name,container,volumes=None,init=None,ns=NS,uid=65532):
    labels={'app.kubernetes.io/name':name}
    container['imagePullPolicy']='IfNotPresent';container['securityContext']=security()|{'runAsUser':uid,'runAsGroup':uid}
    container.setdefault('resources',{'requests':{'cpu':'50m','memory':'128Mi'},'limits':{'cpu':'500m','memory':'512Mi'}})
    spec={'automountServiceAccountToken':False,'securityContext':{'runAsNonRoot':True,'runAsUser':uid,'runAsGroup':uid,'fsGroup':uid,
          'seccompProfile':{'type':'RuntimeDefault'}},'containers':[container],'volumes':volumes or []}
    if init:spec['initContainers']=init
    return resource('Deployment',name,{'replicas':1,'selector':{'matchLabels':labels},'template':{'metadata':{'labels':labels},'spec':spec}},ns,'apps/v1')


def identity():
    result=[config('vcloud-runtime-config',{'runtime-config.py':(HERE/'runtime-config.py').read_text()}),
            config('vcloud-keycloak-realm',{'vcloud-realm.json':(ROOT/'module-4b/keycloak/vcloud-realm.json').read_text()})]
    for name in ('openbao','keycloak'):
        volumes=[{'name':'auth','secret':{'secretName':'vcloud-wsl-'+name+'-db','defaultMode':0o440}},
                 {'name':'tls','secret':{'secretName':'vcloud-wsl-'+name+'-tls','defaultMode':0o440}},
                 {'name':'pg-ca','secret':{'secretName':DB+'-ca','items':[{'key':'ca.crt','path':'ca.crt'}],'defaultMode':0o440}},
                 {'name':'code','configMap':{'name':'vcloud-runtime-config'}},
                 {'name':'runtime','emptyDir':{'medium':'Memory','sizeLimit':'8Mi'}},
                 {'name':'tmp','emptyDir':{'medium':'Memory','sizeLimit':'32Mi'}}]
        mounts=[{'name':v['name'],'mountPath':'/'+v['name'],'readOnly':v['name'] not in ('runtime','tmp')} for v in volumes]
        init=[{'name':'config','image':PYTHON,'imagePullPolicy':'IfNotPresent','command':['python','/code/runtime-config.py',name],
               'securityContext':security(),'resources':{'requests':{'cpu':'25m','memory':'32Mi'},'limits':{'cpu':'100m','memory':'64Mi'}},'volumeMounts':mounts}]
        c={'name':name,'image':image(name),'volumeMounts':mounts}
        if name=='openbao':
            c['command']=['bao','server','-config=/runtime/openbao.hcl']
            c['ports']=[{'name':'https','containerPort':8200}]
            # Transport availability does not assert unseal/initialization.
            c['startupProbe']={'httpGet':{'path':'/v1/sys/init','port':8200,'scheme':'HTTPS'},'failureThreshold':60,'periodSeconds':5}
            c['livenessProbe']={'httpGet':{'path':'/v1/sys/init','port':8200,'scheme':'HTTPS'},'periodSeconds':15}
            c['readinessProbe']={'httpGet':{'path':'/v1/sys/init','port':8200,'scheme':'HTTPS'}}
            result.append(service(name,8200))
        else:
            volumes.extend([{'name':'data','emptyDir':{'medium':'Memory','sizeLimit':'128Mi'}},
                            {'name':'realm','configMap':{'name':'vcloud-keycloak-realm'}},
                            {'name':'quarkus','emptyDir':{'medium':'Memory','sizeLimit':'256Mi'}}])
            init.insert(0,{'name':'prepare-quarkus','image':image('keycloak'),'imagePullPolicy':'IfNotPresent',
                           'command':['sh','-ec','cp -R /opt/keycloak/lib/quarkus/. /built/'],
                           'securityContext':security(),'resources':{'requests':{'cpu':'25m','memory':'32Mi'},'limits':{'cpu':'100m','memory':'64Mi'}},
                           'volumeMounts':[{'name':'quarkus','mountPath':'/built'}]})
            c['volumeMounts'] += [{'name':'data','mountPath':'/opt/keycloak/data'},
                                 {'name':'realm','mountPath':'/opt/keycloak/data/import','readOnly':True},
                                 {'name':'quarkus','mountPath':'/opt/keycloak/lib/quarkus'}]
            c['command']=['/opt/keycloak/bin/kc.sh'];c['args']=['--config-file=/runtime/keycloak.conf','start','--import-realm']
            c['resources']={'requests':{'cpu':'100m','memory':'512Mi'},'limits':{'cpu':'1','memory':'1Gi'}}
            c['startupProbe']={'httpGet':{'path':'/health/started','port':9000,'scheme':'HTTPS'},'failureThreshold':90,'periodSeconds':5}
            c['readinessProbe']={'httpGet':{'path':'/health/ready','port':9000,'scheme':'HTTPS'}}
            result.append(service(name,443,8443))
        dep=deployment(name,c,volumes,init);dep['spec']['strategy']={'type':'Recreate'}
        dep['spec']['template']['metadata'].setdefault('annotations',{})['vcloud.io/runtime-config-hash']=hashlib.sha256((HERE/'runtime-config.py').read_bytes()).hexdigest()
        result.append(dep)
        result.append(resource('Database','vcloud-wsl-'+name,{'cluster':{'name':DB},'name':name,'owner':name,
                              'ensure':'present','databaseReclaimPolicy':'retain'},NS,'postgresql.cnpg.io/v1'))
    return result


def application():
    apisix={'apisix':{'node_listen':9080,'enable_admin':False,'enable_ipv6':False},
            'nginx_config':{'worker_processes':1,'error_log':'/dev/stderr','error_log_level':'warn',
                            'http':{'access_log':'/dev/stdout','client_body_temp_path':'/tmp/client-body',
                                    'proxy_temp_path':'/tmp/proxy','fastcgi_temp_path':'/tmp/fastcgi','uwsgi_temp_path':'/tmp/uwsgi','scgi_temp_path':'/tmp/scgi'}},
            'deployment':{'role':'data_plane','role_data_plane':{'config_provider':'yaml'}},
            'plugin_attr':{'prometheus':{'export_addr':{'ip':'0.0.0.0','port':9091}}}}
    routes={'routes':[{'id':'demo-cpu','uri':'/*','host':'demo-cpu-app.workload-apps.example.com',
                       'plugins':{'prometheus':{},'proxy-rewrite':{'host':'demo-cpu-app.workload-apps.vcloud.example.com'}},
                       'upstream':{'type':'roundrobin','nodes':{'kourier-internal.workload-apps.svc.cluster.local:80':1}}},
                      {'id':'legacy-smoke','uri':'/','plugins':{'prometheus':{}},
                       'upstream':{'type':'roundrobin','nodes':{'vcloud-lab-server.platform-services.svc.cluster.local:8080':1}}}]}
    ingress_available=(ROOT/'deploy/common/apisix-ingress.lock.json').exists()
    if ingress_available:
        # The official controller supplies full in-memory route snapshots.
        # The public file-driven route list remains a rollback reference only.
        apisix['apisix']['enable_admin']=True
        apisix['deployment']={'role':'traditional','role_traditional':{'config_provider':'yaml'},
            'admin':{'admin_key_required':True,'enable_admin_cors':False,'enable_admin_ui':False,
                'allow_admin':['10.42.0.0/16'],'admin_listen':{'ip':'0.0.0.0','port':9180},
                'https_admin':True,'admin_key':[{'name':'controller','key':'__VCLOUD_ADMIN_KEY__','role':'admin'}],
                'admin_api_mtls':{'admin_ssl_cert':'/admin/tls.crt','admin_ssl_cert_key':'/admin/tls.key'}}}
    route_text=yaml.safe_dump(routes,sort_keys=False)+'#END\n'
    result=[config('vcloud-apisix',{'config.yaml':yaml.safe_dump(apisix,sort_keys=False),'apisix.yaml':route_text}),
            deployment('apisix',{'name':'apisix','image':image('apisix'),
              'command':['sh','-ec','cp /config/* /usr/local/apisix/conf/; apisix init; exec /usr/local/openresty/bin/openresty -p /usr/local/apisix -c conf/nginx.conf -g "daemon off;"'],
              'volumeMounts':[{'name':'config','mountPath':'/config','readOnly':True},
                              {'name':'conf','mountPath':'/usr/local/apisix/conf'}, {'name':'logs','mountPath':'/usr/local/apisix/logs'},
                              {'name':'tmp','mountPath':'/tmp'}],
              'readinessProbe':{'tcpSocket':{'port':9080}},'livenessProbe':{'tcpSocket':{'port':9080}}},
              [{'name':'config','configMap':{'name':'vcloud-apisix'}},{'name':'conf','emptyDir':{'medium':'Memory','sizeLimit':'32Mi'}},
               {'name':'logs','emptyDir':{'medium':'Memory','sizeLimit':'32Mi'}},{'name':'tmp','emptyDir':{'medium':'Memory','sizeLimit':'32Mi'}}],
              [{'name':'prepare-conf','image':image('apisix'),'imagePullPolicy':'IfNotPresent',
                'command':['sh','-ec','cp -R /usr/local/apisix/conf/. /built/'],'securityContext':security(),
                'resources':{'requests':{'cpu':'25m','memory':'32Mi'},'limits':{'cpu':'100m','memory':'64Mi'}},
                'volumeMounts':[{'name':'conf','mountPath':'/built'}]}]),
            service('apisix',9080),service('apisix-metrics',9091,labels={'app.kubernetes.io/name':'apisix'}),
            config('demo-cpu-app',{'demo.py':(HERE/'demo.py').read_text()},APP_NS)]
    demo=resource('Service','demo-cpu-app',{'template':{'metadata':{'labels':{'vcloud.io/component':'demo'},
                        'annotations':{'autoscaling.knative.dev/min-scale':'0','autoscaling.knative.dev/max-scale':'1'}},
         'spec':{'automountServiceAccountToken':False,'containerConcurrency':10,
                 'securityContext':{'runAsNonRoot':True,'runAsUser':65532,'runAsGroup':65532,'seccompProfile':{'type':'RuntimeDefault'}},
                 'containers':[{'name':'demo','image':PYTHON,'imagePullPolicy':'IfNotPresent','command':['python','/app/demo.py'],
                                'securityContext':security(),'ports':[{'containerPort':8080}],
                                'resources':{'requests':{'cpu':'25m','memory':'32Mi'},'limits':{'cpu':'200m','memory':'64Mi'}},
                                'volumeMounts':[{'name':'code','mountPath':'/app','readOnly':True}]}],
                 'volumes':[{'name':'code','configMap':{'name':'demo-cpu-app'}}]}}},APP_NS,'serving.knative.dev/v1')
    # Explicit admission defaults keep this custom resource stable in Argo's
    # desired/live comparison; no broad ignoreDifferences rule is required.
    demo['spec']['traffic']=[{'latestRevision':True,'percent':100}]
    template=demo['spec']['template']['spec']
    template.update(enableServiceLinks=False,timeoutSeconds=300)
    template['containers'][0]['ports'][0]['protocol']='TCP'
    template['containers'][0]['readinessProbe']={'tcpSocket':{'port':0},'successThreshold':1}
    next(o for o in result if o['kind']=='Service' and o['metadata']['name']=='apisix-metrics')['spec']['ports'][0]['name']='metrics'
    apisix_dep=next(o for o in result if o['kind']=='Deployment')
    spec=apisix_dep['spec']['template']['spec']
    # OpenResty's default temporary paths are relative to its immutable prefix.
    # Mount only these scratch directories; retain the read-only root filesystem.
    for path in ('client_body_temp','proxy_temp','fastcgi_temp','uwsgi_temp','scgi_temp'):
        volume='scratch-'+path.replace('_','-')
        spec['volumes'].append({'name':volume,'emptyDir':{'medium':'Memory','sizeLimit':'8Mi'}})
        spec['containers'][0]['volumeMounts'].append({'name':volume,'mountPath':'/usr/local/apisix/'+path})
    if ingress_available:
        from platform_ingress import routes as ingress_routes,ADMIN_SECRET
        c=spec['containers'][0]
        c['command']=['sh','-ec','apisix init; exec /usr/local/openresty/bin/openresty -p /usr/local/apisix -c conf/nginx.conf -g "daemon off;"']
        # OIDC outbound TLS trusts only the mounted public Keycloak certificate.
        # Existing private APISIX admin TLS and credentials remain unchanged.
        apisix['nginx_config']['http']['access_log_format']='$remote_addr [$time_local] $request_method $uri $status $body_bytes_sent'
        apisix['apisix'].setdefault('ssl',{})['ssl_trusted_certificate']='/oidc-trust/tls.crt'
        next(o for o in result if o['kind']=='ConfigMap' and o['metadata']['name']=='vcloud-apisix')['data']['config.yaml']=yaml.safe_dump(apisix)
        spec['volumes'] += [{'name':'oidc-trust','secret':{'secretName':'vcloud-wsl-keycloak-tls','items':[{'key':'tls.crt','path':'tls.crt'}],'defaultMode':0o440}},
                           {'name':'admin','secret':{'secretName':ADMIN_SECRET,'defaultMode':0o440}},
                           {'name':'setup','configMap':{'name':'vcloud-apisix-setup'}}]
        c['volumeMounts'].append({'name':'admin','mountPath':'/admin','readOnly':True})
        c['volumeMounts'].append({'name':'oidc-trust','mountPath':'/oidc-trust','readOnly':True})
        mounts=[{'name':'config','mountPath':'/config','readOnly':True},
                {'name':'conf','mountPath':'/conf'},{'name':'admin','mountPath':'/admin','readOnly':True},
                {'name':'setup','mountPath':'/code','readOnly':True}]
        spec['initContainers'].append({'name':'config','image':PYTHON,'imagePullPolicy':'IfNotPresent',
            'command':['python','/code/configure-apisix.py'],'securityContext':security(),
            'resources':{'requests':{'cpu':'25m','memory':'32Mi'},'limits':{'cpu':'100m','memory':'64Mi'}},'volumeMounts':mounts})
        admin=service('apisix-admin',9180,labels={'app.kubernetes.io/name':'apisix'})
        result += [config('vcloud-apisix-setup',{'configure-apisix.py':(ROOT/'deploy/common/configure-apisix.py').read_text()}),
                   admin,*ingress_routes()]
        gateway=next(o for o in result if o['kind']=='Deployment' and o['metadata']['name']=='apisix')
        gateway['spec']['template']['metadata'].setdefault('annotations',{})['vcloud.io/gateway-config-hash']=hashlib.sha256(yaml.safe_dump(apisix).encode()).hexdigest()
    return result+[demo]


def observability():
    result=[]
    operator_sa=resource('ServiceAccount','vcloud-prometheus',namespace=NS);result.append(operator_sa)
    role=resource('Role','vcloud-prometheus',namespace=NS,api='rbac.authorization.k8s.io/v1')
    role['rules']=[{'apiGroups':[''],'resources':['services','endpoints','pods'],'verbs':['get','list','watch']},
                   {'apiGroups':['discovery.k8s.io'],'resources':['endpointslices'],'verbs':['get','list','watch']}]
    for ns in (NS,APP_NS):
        local=copy.deepcopy(role);local['metadata']['namespace']=ns;result.append(local)
        binding=resource('RoleBinding','vcloud-prometheus',namespace=ns,api='rbac.authorization.k8s.io/v1')
        binding.update(roleRef={'apiGroup':'rbac.authorization.k8s.io','kind':'Role','name':'vcloud-prometheus'},
                       subjects=[{'kind':'ServiceAccount','name':'vcloud-prometheus','namespace':NS}]);result.append(binding)
    result.append(resource('Prometheus','vcloud',{'replicas':1,'image':image('prometheus'),'version':'v3.15.0',
        'serviceAccountName':'vcloud-prometheus','serviceDiscoveryRole':'EndpointSlice','serviceMonitorSelector':{'matchLabels':{'vcloud.io/monitor':'true'}},
        'serviceMonitorNamespaceSelector':{'matchLabels':{'kubernetes.io/metadata.name':NS}},
        'podMonitorSelector':{'matchLabels':{'vcloud.io/monitor':'true'}},'retention':'2h',
        'resources':{'requests':{'cpu':'100m','memory':'256Mi'},'limits':{'cpu':'1','memory':'768Mi'}},
        'securityContext':{'runAsNonRoot':True,'runAsUser':65532,'runAsGroup':65532,'fsGroup':65532,'seccompProfile':{'type':'RuntimeDefault'}},
        'containers':[{'name':'prometheus','imagePullPolicy':'IfNotPresent','securityContext':security()},
                      {'name':'config-reloader','imagePullPolicy':'IfNotPresent','securityContext':security()}],
        'initContainers':[{'name':'init-config-reloader','imagePullPolicy':'IfNotPresent','securityContext':security()}]},NS,'monitoring.coreos.com/v1'))
    result.append(service('prometheus',9090,labels={'prometheus':'vcloud'}))
    for name,labels,ns,port,path in [('apisix',{'app.kubernetes.io/name':'apisix'},NS,'metrics','/apisix/prometheus/metrics'),
                                  ('cnpg',{'app.kubernetes.io/name':'cloudnative-pg'},NS,'metrics','/metrics'),
                                  ('knative',{'app':'controller'},APP_NS,'metrics','/metrics')]:
        result.append(resource('ServiceMonitor',name,{'selector':{'matchLabels':labels},'namespaceSelector':{'matchNames':[ns]},
                      'endpoints':[{'port':port,'path':path,'interval':'15s'}]},NS,'monitoring.coreos.com/v1',labels={'vcloud.io/monitor':'true'}))
    # Explicit metric services avoid scraping unrelated controllers/webhooks.
    result += [service('cnpg-operator-metrics',8080,labels={'app.kubernetes.io/name':'cloudnative-pg'}),
               service('knative-controller-metrics',9090,ns=APP_NS,labels={'app':'controller'})]
    result[-2]['spec']['ports'][0]['name']='metrics';result[-1]['spec']['ports'][0]['name']='metrics'
    otel={'receivers':{'otlp':{'protocols':{'grpc':{'endpoint':'0.0.0.0:4317'},'http':{'endpoint':'0.0.0.0:4318'}}}},
          'processors':{'memory_limiter':{'check_interval':'1s','limit_mib':160,'spike_limit_mib':32},'batch':{}},
          'exporters':{'debug':{'verbosity':'detailed'},'prometheus':{'endpoint':'0.0.0.0:9464'}},
          'extensions':{'health_check':{'endpoint':'0.0.0.0:13133'}},
          'service':{'extensions':['health_check'],'pipelines':{
            'traces':{'receivers':['otlp'],'processors':['memory_limiter','batch'],'exporters':['debug']},
            'metrics':{'receivers':['otlp'],'processors':['memory_limiter','batch'],'exporters':['prometheus']}}}}
    result += [config('vcloud-otel',{'config.yaml':yaml.safe_dump(otel,sort_keys=False)}),
               deployment('otel-collector',{'name':'collector','image':image('otel-collector'),'args':['--config=/conf/config.yaml'],
                           'volumeMounts':[{'name':'config','mountPath':'/conf','readOnly':True}],
                           'readinessProbe':{'httpGet':{'path':'/','port':13133}},'livenessProbe':{'httpGet':{'path':'/','port':13133}}},
                          [{'name':'config','configMap':{'name':'vcloud-otel'}}])]
    otel_service=service('otel-collector',4318);otel_service['spec']['ports'].append({'name':'grpc','port':4317,'targetPort':4317});result.append(otel_service)
    datasources={'apiVersion':1,'datasources':[{'name':'vCloud Prometheus','type':'prometheus','access':'proxy',
        'url':'http://prometheus.platform-services.svc.cluster.local:9090','isDefault':True,'editable':False}]}
    result += [config('vcloud-grafana',{'datasources.yaml':yaml.safe_dump(datasources,sort_keys=False)}),
               deployment('grafana',{'name':'grafana','image':image('grafana'),
                 'env':[{'name':'GF_SECURITY_ADMIN_USER__FILE','value':'/auth/admin-user'},
                        {'name':'GF_SECURITY_ADMIN_PASSWORD__FILE','value':'/auth/admin-password'},
                        {'name':'GF_AUTH_ANONYMOUS_ENABLED','value':'false'}, {'name':'GF_ANALYTICS_REPORTING_ENABLED','value':'false'},
                        {'name':'GF_ANALYTICS_CHECK_FOR_UPDATES','value':'false'}, {'name':'GF_PLUGINS_PREINSTALL_DISABLED','value':'true'}],
                 'volumeMounts':[{'name':'auth','mountPath':'/auth','readOnly':True},
                                 {'name':'datasources','mountPath':'/etc/grafana/provisioning/datasources','readOnly':True},
                                 {'name':'data','mountPath':'/var/lib/grafana'},{'name':'tmp','mountPath':'/tmp'}],
                 'readinessProbe':{'httpGet':{'path':'/api/health','port':3000}}},
                 [{'name':'auth','secret':{'secretName':'vcloud-wsl-grafana-admin','defaultMode':0o440}},
                  {'name':'datasources','configMap':{'name':'vcloud-grafana'}},
                  {'name':'data','emptyDir':{'medium':'Memory','sizeLimit':'128Mi'}},{'name':'tmp','emptyDir':{'medium':'Memory','sizeLimit':'32Mi'}}]),
               service('grafana',3000)]
    return result


def network(router='10.42.0.188'):
    ipaddress.ip_address(router)
    api={'toEntities':['kube-apiserver'],'toPorts':ports(443,16443)}
    endpoint=lambda name,ns=NS:{'k8s:io.kubernetes.pod.namespace':ns,'k8s:app.kubernetes.io/name':name}
    prom={'k8s:io.kubernetes.pod.namespace':NS,'k8s:prometheus':'vcloud'}
    knative={'k8s:io.kubernetes.pod.namespace':APP_NS,'k8s:vcloud.io/component':'knative'}
    demo={'k8s:io.kubernetes.pod.namespace':APP_NS,'k8s:vcloud.io/component':'demo'}
    pg={'k8s:io.kubernetes.pod.namespace':NS,'k8s:cnpg.io/cluster':DB}
    # WSL classifies router health traffic as world, and CIDR alone is ineffective
    # in the measured datapath. Only health/metrics ports have this lab exception.
    health=lambda *p:[{'fromEntities':['host','remote-node','health','world'],'toPorts':ports(*p)},
                       {'fromCIDR':[router+'/32'],'toPorts':ports(*p)}]
    result=[cnp('vcloud-wsl-db-node-probe',{'k8s:cnpg.io/cluster':DB},[
                {'fromCIDR':[router+'/32'],'toPorts':ports(8000)}, {'fromEntities':['world'],'toPorts':ports(8000)}]),
            cnp('vcloud-wsl-identity-db',{'k8s:cnpg.io/cluster':DB},[{'fromEndpoints':[endpoint('openbao'),endpoint('keycloak')],'toPorts':ports(5432)},
                  {'fromEndpoints':[prom],'toPorts':ports(9187)}])]
    result.append(cnp('vcloud-wsl-cnpg-metrics',endpoint('cloudnative-pg'),[{'fromEndpoints':[prom],'toPorts':ports(8080)}]))
    result.append(cnp('vcloud-wsl-smoke-gateway',{'k8s:vcloud.io/lab-role':'server'},[{'fromEndpoints':[endpoint('apisix')],'toPorts':ports(8080)}]))
    for name,hp in [('openbao',8200),('keycloak',9000)]:
        ingress=health(hp)
        if name=='keycloak':ingress += health(8443)
        result.append(cnp('vcloud-wsl-'+name,endpoint(name),ingress,[{'toEndpoints':[pg],'toPorts':ports(5432)}]))
    result += [cnp('vcloud-wsl-apisix',endpoint('apisix'),health(9080)+[{'fromEndpoints':[prom],'toPorts':ports(9091)}],
                    [{'toEndpoints':[knative],'toPorts':ports(8080,8081)},
                     {'toEndpoints':[{'k8s:io.kubernetes.pod.namespace':NS,'k8s:vcloud.io/lab-role':'server'}],'toPorts':ports(8080)}]),
               cnp('vcloud-wsl-otel',endpoint('otel-collector'),health(13133)+[{'fromEndpoints':[demo],'toPorts':ports(4317,4318)}],[]),
               cnp('vcloud-wsl-grafana',endpoint('grafana'),health(3000),[{'toEndpoints':[prom],'toPorts':ports(9090)}]),
               cnp('vcloud-wsl-prometheus',prom,health(9090),[api,
                    {'toEndpoints':[endpoint('apisix')],'toPorts':ports(9091)},
                    {'toEndpoints':[endpoint('cloudnative-pg')],'toPorts':ports(8080)},
                    {'toEndpoints':[knative],'toPorts':ports(9090)}, {'toEndpoints':[pg],'toPorts':ports(9187)}]),
               cnp('vcloud-wsl-prom-operator',{'k8s:vcloud.io/component':'prometheus-operator'},health(8080),[api])]
    cp=cnp('vcloud-wsl-knative',knative,health(8080,8081,8443,9090,8008,8181,8012,18000,9000)+[
        {'fromEntities':['kube-apiserver'],'toPorts':ports(8443)},
        {'fromEndpoints':[knative,endpoint('apisix'),prom,demo],'toPorts':ports(8080,8081,8090,8443,9090,8008,8012,8013,8022,18000,19000)}],
        [api,{'toEndpoints':[knative,demo],'toPorts':ports(8080,8081,8090,8443,8008,8012,8013,8022,18000,19000)}])
    cp['metadata']['namespace']=APP_NS;result.append(cp)
    cp=cnp('vcloud-wsl-demo',demo,health(8012)+[{'fromEndpoints':[knative],'toPorts':ports(8080,8012,8022)}],
        [{'toEndpoints':[endpoint('otel-collector')],'toPorts':ports(4318)}]);cp['metadata']['namespace']=APP_NS;result.append(cp)
    for obj in result:
        for direction in ('ingress','egress'):
            for rule in obj['spec'].get(direction,[]):
                for key in ('fromEndpoints','toEndpoints'):
                    if key in rule:rule[key]=[v if 'matchLabels' in v else {'matchLabels':v} for v in rule[key]]
    return result


def groups(router='10.42.0.188'):
    control=controllers()
    extra_network=[]
    if (ROOT/'deploy/common/apisix-ingress.lock.json').exists():
        from platform_ingress import crds,controller,network as ingress_network
        control=control+crds()+controller()
        extra_network=ingress_network(router)
    return {'crds.yaml':[o for o in control if o['kind']=='CustomResourceDefinition'],
            'controllers.yaml':[o for o in control if o['kind']!='CustomResourceDefinition'],
            'network.yaml':network(router)+extra_network,'identity.yaml':identity(),
            'observability.yaml':observability(),'application.yaml':application()}


def check(objects):
    # All node exceptions remain frozen; there are no new host mounts/namespaces.
    adapted=copy.deepcopy(objects)
    served={(o['spec']['group']+'/'+v['name'],o['spec']['names']['kind']) for o in controllers()
            if o['kind']=='CustomResourceDefinition' for v in o['spec']['versions'] if v['served'] and not v.get('deprecated',False)}
    if (ROOT/'deploy/common/apisix-ingress.lock.json').exists():
        from platform_ingress import crds
        served |= {(o['spec']['group']+'/'+v['name'],o['spec']['names']['kind']) for o in crds()
                   for v in o['spec']['versions'] if v['served'] and not v.get('deprecated',False)}
    for obj in adapted:
        if obj['apiVersion']=='monitoring.coreos.com/v1' and obj['kind']=='ServiceMonitor':continue
        if obj['apiVersion']=='monitoring.coreos.com/v1' and obj['kind']=='Prometheus':
            spec=obj['spec']
            if spec.get('image')!=image('prometheus'):raise ValueError('Prometheus image differs from lock')
            if any('nvidia.com/' in key for key in spec.get('resources',{}).get('limits',{})):raise ValueError('GPU forbidden')
            # Audit the partial Pod overrides as the operator will fill them;
            # schema validation still uses the original Prometheus CR.
            for c in spec.get('containers',[])+spec.get('initContainers',[]):
                if c['name'] not in ('prometheus','config-reloader','init-config-reloader'):
                    raise ValueError('Unapproved Prometheus sidecar')
                expected=image('prometheus' if c['name']=='prometheus' else 'prometheus-config-reloader')
                if c.get('image',expected)!=expected:raise ValueError('Prometheus sidecar image differs from lock')
                c['image']=expected
            obj['kind']='Pod';obj['apiVersion']='v1'
        spec=podspec(obj)
        if spec:
            for c in spec.get('containers',[])+spec.get('initContainers',[]):
                if c.get('securityContext',{}).get('allowPrivilegeEscalation') is not False:
                    raise ValueError('Privilege escalation must be disabled')
                if c.get('imagePullPolicy')!='IfNotPresent':raise ValueError('Image cache policy missing')
                if c.get('image') and '@sha256:' not in c['image']:raise ValueError('Immutable image required')
                if any('nvidia.com/' in key for key in c.get('resources',{}).get('limits',{})):raise ValueError('GPU forbidden')
        if obj['kind']=='CustomResourceDefinition':continue
        # Knative's internal Certificate API has an alpha suffix but remains
        # served and non-deprecated in the frozen bundle. Schema validation still
        # uses its real version; only the generic suffix heuristic is adapted.
        if (obj['apiVersion'],obj['kind']) in served and obj['apiVersion'].endswith('v1alpha1'):
            obj['apiVersion']=obj['apiVersion'].rsplit('/',1)[0]+'/v1'
        audit([obj])


def render(build,router='10.42.0.188'):
    build.mkdir(parents=True,exist_ok=True);schemas=build/'schemas';schemas.mkdir(exist_ok=True)
    lock=json.loads((HERE/'artifacts.lock.json').read_text())
    images={v['canonical'] for v in lock['images'].values()}|{PYTHON}
    if (ROOT/'deploy/common/apisix-ingress.lock.json').exists():
        from platform_ingress import lock as ingress_lock
        images|={v['canonical'] for v in ingress_lock()['images'].values()}
    (build/'images.txt').write_text('\n'.join(sorted(images))+'\n')
    for filename,objects in groups(router).items():
        objects=copy.deepcopy(objects)
        configs={(o['metadata'].get('namespace'),o['metadata']['name']):o.get('data',{}) for o in objects if o['kind']=='ConfigMap'}
        for obj in objects:
            spec=podspec(obj)
            if not spec:continue
            data=[configs[(obj['metadata'].get('namespace'),v['configMap']['name'])] for v in spec.get('volumes',[])
                  if 'configMap' in v and (obj['metadata'].get('namespace'),v['configMap']['name']) in configs]
            if data:obj['spec']['template']['metadata'].setdefault('annotations',{})['vcloud.io/config-hash']=hashlib.sha256(json.dumps(data,sort_keys=True).encode()).hexdigest()
        check(objects)
        (build/filename).write_text(yaml.safe_dump_all(objects,sort_keys=False))
        for obj in objects:
            if obj['kind']!='CustomResourceDefinition':continue
            s=obj['spec']
            for version in s['versions']:
                if version['served']:
                    (schemas/(s['names']['kind'].lower()+'_'+s['group']+'_'+version['name']+'.json')).write_text(json.dumps(version['schema']['openAPIV3Schema']))
    for obj in platform_vendor('cnpg.yaml'):
        if obj['kind']=='CustomResourceDefinition' and obj['spec']['names']['kind']=='Database':
            s=obj['spec']
            for v in s['versions']:
                if v['served']:(schemas/('database_'+s['group']+'_'+v['name']+'.json')).write_text(json.dumps(v['schema']['openAPIV3Schema']))
    print('PASS: CPU-only endpoint manifests rendered and policy audited')


def validate(build,kubeconform=None,schemas=None,files=None):
    files=[str(path) for path in (files or [build/name for name in groups()])]
    schema_paths=[str(build/'schemas/{{.ResourceKind}}_{{.Group}}_{{.ResourceAPIVersion}}.json'),
                  str(ROOT/'lab/wsl/schemas/{{.ResourceKind}}.json'),
                  str(Path(schemas or ROOT/'.build/ci-linux-assets/schemas')/'{{.ResourceKind}}.json'),
                  str(ROOT/'module-4a/schemas/{{.ResourceKind}}_{{.ResourceAPIVersion}}.json'),
                  str(ROOT/'module-2/schemas/{{.ResourceKind}}_{{.ResourceAPIVersion}}.json'),
                  str(ROOT/'module-2/schemas/{{.Group}}/{{.ResourceKind}}_{{.ResourceAPIVersion}}.json'),
                  str(Path(schemas or ROOT/'.build/ci-linux-assets/schemas')/'{{.ResourceKind}}_{{.ResourceAPIVersion}}.json')]
    command=[str(kubeconform or ROOT/'.build/ci-linux-assets/bin/kubeconform'),'-strict','-summary']
    for path in schema_paths:command+=['-schema-location',path]
    subprocess.run(command+files,check=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('action',choices=['render','validate'])
    parser.add_argument('--build',type=Path,default=ROOT/'.build/wsl-endpoints');parser.add_argument('--router',default='10.42.0.188')
    parser.add_argument('--kubeconform');parser.add_argument('--schemas',type=Path)
    args=parser.parse_args()
    render(args.build,args.router) if args.action=='render' else validate(args.build,args.kubeconform,args.schemas)
