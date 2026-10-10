#!/usr/bin/env python3
"""Generate Module 3 copy-ready resources. --check rejects drift; no network or cluster calls."""
import argparse
import json
from pathlib import Path
import yaml

ROOT=Path(__file__).resolve().parents[1]
IMAGE='registry.vcloud.example.com/vcloud/ci-tooling:1.0.0'
SEC={'runAsNonRoot':True,'runAsUser':65532,'runAsGroup':65532,'allowPrivilegeEscalation':False,
     'readOnlyRootFilesystem':True,'capabilities':{'drop':['ALL']},'seccompProfile':{'type':'RuntimeDefault'}}
POD={'runAsNonRoot':True,'runAsUser':65532,'runAsGroup':65532,'fsGroup':65532,'seccompProfile':{'type':'RuntimeDefault'}}


def obj(api,kind,name,spec=None,namespace='workload-apps',**extra):
    result={'apiVersion':api,'kind':kind,'metadata':{'name':name,'labels':{'app.kubernetes.io/part-of':'vcloud'}}}
    if namespace: result['metadata']['namespace']=namespace
    if spec is not None: result['spec']=spec
    result.update(extra)
    return result


def task(name,action,results=None,credentials=None):
    environment=[{'name':'VCLOUD_WORKSPACE','value':'$(workspaces.source.path)'},
                 {'name':'VCLOUD_REVISION','value':'$(params.revision)'},
                 {'name':'HOME','value':'/tmp'},{'name':'PYTHONDONTWRITEBYTECODE','value':'1'}]
    params=[{'name':'revision','type':'string','description':'Exact protected-main Git commit; validated before use'}]
    if action=='build': environment += [{'name':'VCLOUD_DIGEST_RESULT','value':'$(results.IMAGE_DIGEST.path)'},
                                       {'name':'DOCKER_CONFIG','value':'/var/run/vcloud/registry'}]
    if action=='publish':
        environment += [{'name':'VCLOUD_DIGEST','value':'$(params.digest)'},
                        {'name':'VCLOUD_COMMIT_RESULT','value':'$(results.GITOPS_COMMIT.path)'}]
        params += [{'name':'digest','type':'string'}]
    volumes=[{'name':'tmp','emptyDir':{'sizeLimit':'256Mi'}}]
    mounts=[{'name':'tmp','mountPath':'/tmp'}]
    for secret,directory,items in credentials or []:
        volumes.append({'name':secret,'secret':{'secretName':secret,'defaultMode':288,'items':items}})
        mounts.append({'name':secret,'mountPath':directory,'readOnly':True})
    spec={'params':params,'workspaces':[{'name':'source'}],
          'stepTemplate':{'securityContext':SEC,'computeResources':{
              'requests':{'cpu':'250m','memory':'256Mi'},'limits':{'cpu':'2','memory':'1Gi'}}},
          'steps':[{'name':action,'image':IMAGE,'imagePullPolicy':'IfNotPresent',
                    'command':['python3'],'args':['/opt/vcloud-ci/runner.py',action],
                    'env':environment,'volumeMounts':mounts}], 'volumes':volumes}
    if results: spec['results']=[{'name':n,'type':'string'} for n in results]
    return obj('tekton.dev/v1','Task',name,spec)


def pod_template():
    return {'automountServiceAccountToken':False,'securityContext':POD,
            'imagePullSecrets':[{'name':'vcloud-registry-pull'}],
            'enableServiceLinks':False}


def run_spec(commit,pending=False):
    spec={'pipelineRef':{'name':'vcloud-ci'},'params':[{'name':'revision','value':commit}],
          'taskRunTemplate':{'serviceAccountName':'vcloud-ci','podTemplate':pod_template()},
          'taskRunSpecs':[{'pipelineTaskName':'publish','serviceAccountName':'vcloud-ci-publisher'}],
          'timeouts':{'pipeline':'1h0m0s','tasks':'55m0s','finally':'5m0s'},
          'workspaces':[{'name':'source','volumeClaimTemplate':{'spec':{
              'accessModes':['ReadWriteOnce'],'storageClassName':'vcloud-ci-csi',
              'resources':{'requests':{'storage':'5Gi'}}}}}]}
    if pending: spec['status']='PipelineRunPending'
    return spec


def policy(name,selector,ingress=None,egress=None,namespace='workload-apps'):
    spec={'endpointSelector':{'matchLabels':selector}}
    if ingress is not None: spec['ingress']=ingress
    if egress is not None: spec['egress']=egress
    return obj('cilium.io/v2','CiliumNetworkPolicy',name,spec,namespace)


def endpoint(labels): return {'matchLabels':labels}
def ns_labels(namespace,**labels): return {'k8s:io.kubernetes.pod.namespace':namespace,**labels}
def ports(*numbers): return [{'port':str(n),'protocol':'TCP'} for n in numbers]
def fqdn(name,port=443): return {'toFQDNs':[{'matchName':name}],'toPorts':[{'ports':ports(port)}]}


def resources():
    tasks=[task('vcloud-clone','clone'),task('vcloud-test','test'),
      task('vcloud-build','build',['IMAGE_DIGEST'],[
          ('vcloud-buildkit-mtls','/var/run/vcloud/buildkit',[{'key':k,'path':k} for k in ['ca.crt','tls.crt','tls.key']]),
          ('vcloud-registry-push','/var/run/vcloud/registry',[{'key':'.dockerconfigjson','path':'config.json'}])]),
      task('vcloud-publish','publish',['GITOPS_COMMIT'],[
          ('vcloud-git-write','/var/run/vcloud/git',[{'key':'token','path':'token'}])])]
    pipeline=obj('tekton.dev/v1','Pipeline','vcloud-ci',{
       'description':'Authenticated main push -> test -> mTLS remote OCI build -> digest-only GitOps promotion',
       'params':[{'name':'revision','type':'string'}],'workspaces':[{'name':'source'}],
       'tasks':[{'name':name,'taskRef':{'name':'vcloud-'+name},
                 **({'runAfter':[previous]} if previous else {}),
                 'params':[{'name':'revision','value':'$(params.revision)'},
                           *([{'name':'digest','value':'$(tasks.build.results.IMAGE_DIGEST)'}] if name=='publish' else [])],
                 'workspaces':[{'name':'source','workspace':'source'}]}
                for name,previous in [('clone',None),('test','clone'),('build','test'),('publish','build')]],
       'results':[{'name':'IMAGE_DIGEST','value':'$(tasks.build.results.IMAGE_DIGEST)'},
                  {'name':'GITOPS_COMMIT','value':'$(tasks.publish.results.GITOPS_COMMIT)'}]})
    sample=obj('tekton.dev/v1','PipelineRun','vcloud-ci-manual-example',
               run_spec('1bc96d335bcb82482e33d4656102123e714c8fe9',pending=True))
    sample['metadata']['annotations']={'vcloud.io/example':'Pending; replace revision with a commit containing Module 3, then remove spec.status'}
    rbac=[obj('v1','ServiceAccount',name,automountServiceAccountToken=False,
              imagePullSecrets=[{'name':'vcloud-registry-pull'}]) for name in ['vcloud-ci','vcloud-ci-publisher']]
    listener_sa=obj('v1','ServiceAccount','vcloud-trigger',automountServiceAccountToken=True,
                    imagePullSecrets=[{'name':'vcloud-registry-pull'}])
    listener_sa['metadata']['annotations']={'vcloud.io/token-justification':'EventListener creates scoped PipelineRuns and resolves trigger definitions; no deployment authority'}
    rbac += [listener_sa,
        obj('rbac.authorization.k8s.io/v1','Role','vcloud-trigger',rules=[
          {'apiGroups':['triggers.tekton.dev'],'resources':['eventlisteners','triggerbindings','triggertemplates'],'verbs':['get','list','watch']},
          {'apiGroups':['tekton.dev'],'resources':['pipelineruns'],'verbs':['create']},
          {'apiGroups':[''],'resources':['secrets'],'resourceNames':['vcloud-webhook-hmac'],'verbs':['get']},
          {'apiGroups':[''],'resources':['events'],'verbs':['create','patch']}]),
        obj('rbac.authorization.k8s.io/v1','RoleBinding','vcloud-trigger',
            roleRef={'apiGroup':'rbac.authorization.k8s.io','kind':'Role','name':'vcloud-trigger'},
            subjects=[{'kind':'ServiceAccount','name':'vcloud-trigger','namespace':'workload-apps'}]),
        obj('rbac.authorization.k8s.io/v1','ClusterRole','vcloud-trigger-interceptors',namespace=None,
            rules=[{'apiGroups':['triggers.tekton.dev'],'resources':['clusterinterceptors'],'verbs':['get','list','watch']}]),
        obj('rbac.authorization.k8s.io/v1','ClusterRoleBinding','vcloud-trigger-interceptors',namespace=None,
            roleRef={'apiGroup':'rbac.authorization.k8s.io','kind':'ClusterRole','name':'vcloud-trigger-interceptors'},
            subjects=[{'kind':'ServiceAccount','name':'vcloud-trigger','namespace':'workload-apps'}])]
    filters="body.repository.full_name == 'amazen33/twinfra' && body.ref == 'refs/heads/main' && body.deleted == false && body.forced == false && body.after.matches('^[0-9a-f]{40}$') && body.after != '0000000000000000000000000000000000000000'"
    trigger_run=obj('tekton.dev/v1','PipelineRun','vcloud-ci-$(tt.params.revision)',run_spec('$(tt.params.revision)'))
    trigger_run['metadata']['labels']['app.kubernetes.io/name']='vcloud-ci'
    trigger=[obj('triggers.tekton.dev/v1beta1','TriggerBinding','vcloud-main-push',
                 {'params':[{'name':'revision','value':'$(body.after)'}]}),
        obj('triggers.tekton.dev/v1beta1','TriggerTemplate','vcloud-main-push',
            {'params':[{'name':'revision'}],'resourcetemplates':[trigger_run]}),
        obj('triggers.tekton.dev/v1beta1','EventListener','vcloud-push',{
            'serviceAccountName':'vcloud-trigger','resources':{'kubernetesResource':{
                'serviceType':'ClusterIP','servicePort':8080,'spec':{'template':{'spec':{
                    'securityContext':POD,'containers':[{'securityContext':SEC,'resources':{
                        'requests':{'cpu':'100m','memory':'128Mi'},'limits':{'cpu':'500m','memory':'256Mi'}}}]}}}}},
            'triggers':[{'name':'trusted-main','interceptors':[
                {'ref':{'name':'github','kind':'ClusterInterceptor'},'params':[
                    {'name':'secretRef','value':{'secretName':'vcloud-webhook-hmac','secretKey':'secretToken'}},
                    {'name':'eventTypes','value':['push']}]},
                {'ref':{'name':'cel','kind':'ClusterInterceptor'},'params':[{'name':'filter','value':filters}]}],
                'bindings':[{'ref':'vcloud-main-push'}],'template':{'ref':'vcloud-main-push'}}]}),
        obj('apisix.apache.org/v2','ApisixRoute','vcloud-github-webhook',{'ingressClassName':'apisix',
            'http':[{'name':'github-push','match':{'hosts':['ci.vcloud.example.com'],'paths':['/hooks/github']},
                     'backends':[{'serviceName':'el-vcloud-push','servicePort':8080}],
                     'plugins':[{'name':'limit-req','enable':True,'config':{'rate':5,'burst':10,'key':'remote_addr','rejected_code':429}}]}]}),
        obj('apisix.apache.org/v2','ApisixTls','vcloud-ci-webhook',{
            'hosts':['ci.vcloud.example.com'],'secret':{'name':'vcloud-ci-webhook-tls','namespace':'workload-apps'}})]
    dns={'toEndpoints':[endpoint(ns_labels('kube-system',**{'k8s:k8s-app':'kube-dns'}))],
         'toPorts':[{'ports':[{'port':'53','protocol':'UDP'},{'port':'53','protocol':'TCP'}],
                     'rules':{'dns':[{'matchName':n} for n in ['github.com','registry.vcloud.example.com','buildkit.vcloud.example.com']]+[{'matchPattern':'*.svc.cluster.local'}]}}]}
    api={'toEntities':['kube-apiserver'],'toPorts':[{'ports':ports(443,6443)}]}
    networks=[policy('vcloud-ci-dns',{},egress=[dns]),
       *[policy('vcloud-ci-'+name,{'tekton.dev/task':'vcloud-'+name},egress=rules)
         for name,rules in [('clone',[fqdn('github.com')]),('test',[]),
                            ('build',[fqdn('github.com'),fqdn('buildkit.vcloud.example.com',1234),fqdn('registry.vcloud.example.com')]),
                            ('publish',[fqdn('github.com')])]],
       policy('vcloud-ci-eventlistener',{'eventlistener':'vcloud-push'},
              ingress=[{'fromEndpoints':[endpoint(ns_labels('platform-services',**{'app.kubernetes.io/name':'apisix'}))],
                        'toPorts':[{'ports':ports(8080)}]}],
              egress=[api,{'toEndpoints':[endpoint(ns_labels('tekton-pipelines',**{'app.kubernetes.io/name':'tekton-triggers-core-interceptors'}))],
                           'toPorts':[{'ports':ports(8443)}]}]),
       policy('vcloud-ci-gateway',{'app.kubernetes.io/name':'apisix'},namespace='platform-services',egress=[{
              'toEndpoints':[endpoint(ns_labels('workload-apps',eventlistener='vcloud-push'))],'toPorts':[{'ports':ports(8080)}]}]),
       policy('vcloud-ci-gitops-read',{'app.kubernetes.io/name':'argocd-repo-server'},namespace='platform-services',egress=[dns,fqdn('github.com')]),
       policy('vcloud-tekton-deny',{},ingress=[],egress=[],namespace='tekton-pipelines'),
       policy('vcloud-tekton-controller',{},namespace='tekton-pipelines',egress=[dns,api,
           {'toEndpoints':[endpoint(ns_labels('tekton-pipelines'))],'toPorts':[{'ports':ports(8080,8082,8443,443)}]}],
           ingress=[{'fromEntities':['kube-apiserver'],'toPorts':[{'ports':ports(8443,443)}]},
                    {'fromEndpoints':[endpoint(ns_labels('workload-apps',eventlistener='vcloud-push'))],'toPorts':[{'ports':ports(8443)}]},
                    {'fromEntities':['host'],'toPorts':[{'ports':ports(8080,9090,8443)}]},
                    {'fromEndpoints':[endpoint(ns_labels('platform-services',**{'app.kubernetes.io/name':'prometheus'}))],'toPorts':[{'ports':ports(9090)}]}]),
       policy('vcloud-ci-prometheus',{'app.kubernetes.io/name':'prometheus'},namespace='platform-services',egress=[
           {'toEndpoints':[endpoint(ns_labels('tekton-pipelines'))],'toPorts':[{'ports':ports(9090)}]},
           {'toEndpoints':[endpoint(ns_labels('platform-services',**{'app.kubernetes.io/name':'argocd-application-controller'}))],'toPorts':[{'ports':ports(8082)}]}]),
       policy('vcloud-ci-argocd-metrics',{'app.kubernetes.io/name':'argocd-application-controller'},namespace='platform-services',
           ingress=[{'fromEndpoints':[endpoint(ns_labels('platform-services',**{'app.kubernetes.io/name':'prometheus'}))],'toPorts':[{'ports':ports(8082)}]}])]
    namespace=obj('v1','Namespace','tekton-pipelines',namespace=None)
    namespace['metadata']['labels'].update({'pod-security.kubernetes.io/enforce':'restricted','pod-security.kubernetes.io/enforce-version':'v1.36'})
    monitors=[obj('monitoring.coreos.com/v1','ServiceMonitor','vcloud-tekton',{
        'selector':{'matchLabels':{'app.kubernetes.io/name':'controller','app.kubernetes.io/part-of':'tekton-pipelines','app.kubernetes.io/component':'controller'}},
        'namespaceSelector':{'matchNames':['tekton-pipelines']},
        'endpoints':[{'port':'http-metrics','interval':'30s','path':'/metrics','honorLabels':False}]},namespace='platform-services'),
      obj('monitoring.coreos.com/v1','ServiceMonitor','vcloud-argocd',{
        'selector':{'matchLabels':{'app.kubernetes.io/name':'argocd-metrics'}},
        'namespaceSelector':{'matchNames':['platform-services']},
        'endpoints':[{'port':'metrics','interval':'30s','path':'/metrics','honorLabels':False}]},namespace='platform-services')]
    rules=[{'alert':'VCloudPipelineFailed','expr':'sum(increase(tekton_pipelines_controller_pipelinerun_duration_seconds_count{namespace="workload-apps",pipeline="vcloud-ci",status=~"[Ff]ailed|failure"}[15m])) > 0','for':'1m','labels':{'severity':'warning'},'annotations':{'summary':'A vCloud delivery pipeline failed','description':'Inspect the failed PipelineRun before retrying; Argo CD has not received a new digest.'}},
           {'alert':'VCloudArgoOutOfSync','expr':'argocd_app_info{name="vcloud-delivery",sync_status!="Synced"} == 1','for':'15m','labels':{'severity':'warning'},'annotations':{'summary':'vCloud workload remains out of sync'}},
           {'alert':'VCloudArgoUnhealthy','expr':'argocd_app_info{name="vcloud-delivery",health_status=~"Degraded|Missing|Unknown"} == 1','for':'10m','labels':{'severity':'critical'},'annotations':{'summary':'vCloud workload health needs attention'}},
           {'alert':'VCloudTektonMetricsMissing','expr':'absent(up{job="tekton-pipelines-controller"}) or max(up{job="tekton-pipelines-controller"}) == 0','for':'10m','labels':{'severity':'warning'},'annotations':{'summary':'Tekton metrics target is missing or unavailable'}}]
    monitor_rule=obj('monitoring.coreos.com/v1','PrometheusRule','vcloud-delivery',{'groups':[{'name':'vcloud.delivery','rules':rules}]},namespace='platform-services')
    expressions=[('Pipeline runs','sum by (status) (increase(tekton_pipelines_controller_pipelinerun_duration_seconds_count{namespace="workload-apps",pipeline="vcloud-ci"}[1h]))'),
                 ('Pipeline duration p95','histogram_quantile(0.95, sum by (le) (rate(tekton_pipelines_controller_pipelinerun_duration_seconds_bucket{namespace="workload-apps",pipeline="vcloud-ci"}[15m])))'),
                 ('Argo CD sync and health','argocd_app_info{name="vcloud-delivery"}'),('Delivery alerts','ALERTS{alertname=~"VCloud.*",alertstate="firing"}')]
    dashboard={'uid':'vcloud-delivery','title':'vCloud delivery','schemaVersion':41,'version':1,'refresh':'30s',
        'templating':{'list':[{'name':'datasource','type':'datasource','query':'prometheus','current':{}}]},
        'panels':[{'id':i,'title':title,'type':'timeseries','gridPos':{'x':(i-1)%2*12,'y':(i-1)//2*8,'w':12,'h':8},
                   'datasource':{'type':'prometheus','uid':'${datasource}'},'targets':[{'refId':'A','expr':expr,'legendFormat':'{{status}} {{sync_status}} {{health_status}}'}]} for i,(title,expr) in enumerate(expressions,1)]}
    grafana=obj('v1','ConfigMap','vcloud-delivery-dashboard',namespace='platform-services',data={'vcloud-delivery.json':json.dumps(dashboard,indent=2)})
    grafana['metadata']['labels']['grafana_dashboard']='1'
    appproject=obj('argoproj.io/v1alpha1','AppProject','vcloud-delivery',namespace='platform-services',spec={
      'sourceRepos':['https://github.com/amazen33/twinfra.git'],'destinations':[{'server':'https://kubernetes.default.svc','namespace':'workload-apps'}],
      'clusterResourceWhitelist':[],'namespaceResourceWhitelist':[{'group':'serving.knative.dev','kind':'Service'},{'group':'','kind':'ServiceAccount'},{'group':'cilium.io','kind':'CiliumNetworkPolicy'}]})
    application=obj('argoproj.io/v1alpha1','Application','vcloud-delivery',namespace='platform-services',spec={
      'project':'vcloud-delivery','source':{'repoURL':'https://github.com/amazen33/twinfra.git','targetRevision':'gitops/prod','path':'module-3/gitops','directory':{'recurse':False}},
      'destination':{'server':'https://kubernetes.default.svc','namespace':'workload-apps'},
      'syncPolicy':{'automated':{'enabled':True,'prune':False,'selfHeal':True,'allowEmpty':False},'syncOptions':['CreateNamespace=false'],'retry':{'limit':3,'backoff':{'duration':'10s','factor':2,'maxDuration':'3m'}}}})
    infra_project=obj('argoproj.io/v1alpha1','AppProject','vcloud-ci',namespace='platform-services',spec={
      'sourceRepos':['https://github.com/amazen33/twinfra.git'],
      'destinations':[{'server':'https://kubernetes.default.svc','namespace':n} for n in ['platform-services','workload-apps','tekton-pipelines']],
      'clusterResourceWhitelist':[{'group':'','kind':'Namespace'},{'group':'rbac.authorization.k8s.io','kind':'ClusterRole'},{'group':'rbac.authorization.k8s.io','kind':'ClusterRoleBinding'}],
      'namespaceResourceWhitelist':[{'group':g,'kind':k} for g,k in [('', 'ServiceAccount'),('', 'ConfigMap'),
         ('rbac.authorization.k8s.io','Role'),('rbac.authorization.k8s.io','RoleBinding'),('tekton.dev','Task'),('tekton.dev','Pipeline'),
         ('triggers.tekton.dev','EventListener'),('triggers.tekton.dev','TriggerBinding'),('triggers.tekton.dev','TriggerTemplate'),
         ('cilium.io','CiliumNetworkPolicy'),('apisix.apache.org','ApisixRoute'),('apisix.apache.org','ApisixTls'),
         ('monitoring.coreos.com','ServiceMonitor'),('monitoring.coreos.com','PrometheusRule')]]})
    infra_app=obj('argoproj.io/v1alpha1','Application','vcloud-ci',namespace='platform-services',spec={
      'project':'vcloud-ci','source':{'repoURL':'https://github.com/amazen33/twinfra.git','targetRevision':'main','path':'module-3/manifests','directory':{'recurse':False}},
      'destination':{'server':'https://kubernetes.default.svc','namespace':'workload-apps'},
      'syncPolicy':{'automated':{'enabled':True,'prune':False,'selfHeal':True,'allowEmpty':False},'syncOptions':['CreateNamespace=false']}})
    workload=obj('serving.knative.dev/v1','Service','vcloud-api',{
       'template':{'metadata':{'labels':{'app.kubernetes.io/name':'vcloud-api'},'annotations':{
          'autoscaling.knative.dev/min-scale':'0','autoscaling.knative.dev/max-scale':'4'}},
       'spec':{'serviceAccountName':'vcloud-api','automountServiceAccountToken':False,'containerConcurrency':20,'timeoutSeconds':60,
         'containers':[{'name':'api','image':'registry.vcloud.example.com/vcloud/api:0.1.0','imagePullPolicy':'IfNotPresent',
           'ports':[{'containerPort':8080}],'securityContext':SEC,'resources':{'requests':{'cpu':'100m','memory':'128Mi'},'limits':{'cpu':'1','memory':'256Mi'}},
           'readinessProbe':{'httpGet':{'path':'/healthz','port':8080}},'livenessProbe':{'httpGet':{'path':'/healthz','port':8080}}}]}}})
    workload['metadata']['annotations']={'vcloud.io/source-revision':'bootstrap'}
    workload_sa=obj('v1','ServiceAccount','vcloud-api',automountServiceAccountToken=False,imagePullSecrets=[{'name':'vcloud-registry-pull'}])
    workload_net=policy('vcloud-api',{'app.kubernetes.io/name':'vcloud-api'},ingress=[{
        'fromEndpoints':[endpoint(ns_labels('platform-services',**{'app':'3scale-kourier-gateway'})),endpoint(ns_labels('platform-services',app='activator'))],
        'toPorts':[{'ports':ports(8112)}]},
        {'fromEndpoints':[endpoint(ns_labels('platform-services',app='autoscaler'))],'toPorts':[{'ports':ports(9090,8022)}]},
        {'fromEntities':['host'],'toPorts':[{'ports':ports(8022,8080)}]}],egress=[{
            'toEndpoints':[endpoint(ns_labels('platform-services',app='autoscaler'))],'toPorts':[{'ports':ports(8080)}]}])
    networks.append(obj('cilium.io/v2','CiliumNetworkPolicy','vcloud-api-knative-peers',namespace='platform-services',spec={
        'endpointSelector':{'matchExpressions':[{'key':'k8s:app','operator':'In','values':['activator','autoscaler','3scale-kourier-gateway']}]},
        'egress':[{'toEndpoints':[endpoint(ns_labels('workload-apps',**{'app.kubernetes.io/name':'vcloud-api'}))],
                   'toPorts':[{'ports':ports(8112,9090,8022)}]}]}))
    controller_config={'metrics-protocol':'prometheus','tracing-protocol':'none','metrics.pipelinerun.level':'pipeline',
                       'metrics.pipelinerun.duration-type':'histogram','metrics.taskrun.level':'task','metrics.taskrun.duration-type':'histogram'}
    flags={'disable-creds-init':'true','set-security-context':'true','set-security-context-read-only-root-filesystem':'true'}
    return {'module-3/manifests/tasks.yaml':tasks,'module-3/manifests/pipeline.yaml':[pipeline],
      'module-3/examples/pipelinerun.yaml':[sample],'module-3/manifests/rbac.yaml':rbac,
      'module-3/manifests/triggers.yaml':trigger,'module-3/manifests/network.yaml':networks,
      'module-3/manifests/tekton-namespace.yaml':[namespace],
      'module-3/manifests/observability.yaml':[*monitors,monitor_rule,grafana],
      'module-3/argocd/application.yaml':[appproject,application,infra_project,infra_app],
      'module-3/gitops/workload.yaml':workload,'module-3/gitops/serviceaccount.yaml':[workload_sa],
      'module-3/gitops/network.yaml':[workload_net],
      'module-3/controller-config/observability.patch.json':{'data':controller_config},
      'module-3/controller-config/feature-flags.patch.json':{'data':flags},
      'module-3/observability/rules.yaml':{'groups':monitor_rule['spec']['groups']}}


def main():
    parser=argparse.ArgumentParser(description=__doc__); parser.add_argument('--check',action='store_true'); args=parser.parse_args()
    for relative,data in resources().items():
        if relative.endswith('.json') or relative.endswith('workload.yaml'):
            content=json.dumps(data,indent=2)+'\n'
        elif isinstance(data,dict):
            content='# Generated Prometheus configuration; not a Kubernetes API object.\n'+yaml.safe_dump(data,sort_keys=False)
        else:
            content='# Generated by tools/render_module3.py; review and stage prerequisites before apply.\n'+yaml.safe_dump_all(data,sort_keys=False)
        path=ROOT/relative
        if args.check:
            if not path.exists() or path.read_text(encoding='utf-8')!=content: raise ValueError('Generated Module 3 drift: '+relative)
        else:
            path.parent.mkdir(parents=True,exist_ok=True); path.write_text(content,encoding='utf-8',newline='\n')
    print('Module 3 resources '+('checked' if args.check else 'generated'))


if __name__=='__main__': main()
