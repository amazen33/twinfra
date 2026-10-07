#!/usr/bin/env python3
"""Publish bounded namespaced GitOps workloads; controllers/CRDs stay bootstrap-owned."""
import argparse
from pathlib import Path
import yaml
from wsl_platform import NS,resource
from wsl_endpoints import ROOT,APP_NS,render,check,validate


def definitions(revision='main'):
    result=[]
    for ns in (NS,APP_NS):
        role=resource('Role','vcloud-wsl-endpoints-writer',namespace=ns,api='rbac.authorization.k8s.io/v1')
        role['rules']=[{'apiGroups':[group],'resources':resources,'verbs':['get','list','watch','create','update','patch','delete']} for group,resources in
          [('', ['configmaps','services','serviceaccounts']),('apps',['deployments']),
           ('postgresql.cnpg.io',['databases']),('monitoring.coreos.com',['prometheuses','servicemonitors']),
           ('serving.knative.dev',['services']),('apisix.apache.org',['apisixroutes','gatewayproxies'])]]
        # Prometheus discovery Roles are bootstrap-owned. No new permissions to
        # Secrets, CRDs, Nodes, PVs, ClusterRoles or RoleBindings are granted.
        binding=resource('RoleBinding','vcloud-wsl-endpoints-writer',namespace=ns,api='rbac.authorization.k8s.io/v1')
        binding.update(roleRef={'apiGroup':'rbac.authorization.k8s.io','kind':'Role','name':role['metadata']['name']},
            subjects=[{'kind':'ServiceAccount','name':'argocd-application-controller','namespace':NS}])
        result += [role,binding]
    project=resource('AppProject','vcloud-wsl-endpoints',{'sourceRepos':['https://github.com/amazen33/vCloud.git'],
          'destinations':[{'server':'https://kubernetes.default.svc','namespace':ns} for ns in (NS,APP_NS)],
          'clusterResourceWhitelist':[], 'namespaceResourceWhitelist':[{'group':g,'kind':k} for g,k in
            [('', 'ConfigMap'),('','Service'),('','ServiceAccount'),('apps','Deployment'),('postgresql.cnpg.io','Database'),
             ('monitoring.coreos.com','Prometheus'),('monitoring.coreos.com','ServiceMonitor'),
             ('serving.knative.dev','Service'),('apisix.apache.org','ApisixRoute'),('apisix.apache.org','GatewayProxy')]]},NS,'argoproj.io/v1alpha1')
    app=resource('Application','vcloud-wsl-endpoints',{'project':'vcloud-wsl-endpoints',
        'destination':{'server':'https://kubernetes.default.svc','namespace':NS},
        'source':{'repoURL':'https://github.com/amazen33/vCloud.git','targetRevision':revision,'path':'lab/wsl/endpoints/gitops'},
        'syncPolicy':{'automated':{'enabled':True,'prune':False,'selfHeal':True,'allowEmpty':False},
                     'syncOptions':['CreateNamespace=false','ServerSideApply=true']}},NS,'argoproj.io/v1alpha1')
    return result+[project,app]


def publish(build,revision,check_only=False,kubeconform=None,schemas=None):
    render(build)
    target=ROOT/'lab/wsl/endpoints/gitops';target.mkdir(exist_ok=True)
    objects=[]
    for name in ('identity.yaml','application.yaml','observability.yaml'):
        objects += [o for o in yaml.safe_load_all((build/name).read_text()) if o['kind'] not in ('Role','RoleBinding')]
    # IP-dependent node health policies remain node-bootstrap-owned, avoiding
    # committing a dynamic /32 as a portable cluster-wide GitOps assumption.
    outputs={target/'workloads.yaml':yaml.safe_dump_all(objects,sort_keys=False),
             ROOT/'lab/wsl/endpoints/argocd.yaml':yaml.safe_dump_all(definitions(revision),sort_keys=False)}
    check(objects);check(definitions(revision))
    if check_only:
        for path,content in outputs.items():
            if not path.is_file() or path.read_text()!=content:raise ValueError('GitOps source drift: '+str(path))
        validate(build,kubeconform,schemas,list(outputs))
        print('PASS: GitOps source matches renderer and passes strict schemas')
        return
    for path,content in outputs.items():path.write_text(content)
    print('PASS: namespaced GitOps source rendered; publish before activation')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--build',type=Path,default=ROOT/'.build/wsl-endpoints')
    parser.add_argument('--revision',default='main')
    parser.add_argument('--check',action='store_true');parser.add_argument('--kubeconform');parser.add_argument('--schemas',type=Path)
    args=parser.parse_args();publish(args.build,args.revision,args.check,args.kubeconform,args.schemas)
