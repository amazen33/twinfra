#!/usr/bin/env python3
"""Generate public OpenBao API payloads and restricted CSI integration examples offline."""
from pathlib import Path
import argparse
import json
import yaml

ROOT=Path(__file__).resolve().parents[1]
SEC={'runAsNonRoot':True,'runAsUser':65532,'runAsGroup':65532,
     'allowPrivilegeEscalation':False,'readOnlyRootFilesystem':True,
     'capabilities':{'drop':['ALL']},'seccompProfile':{'type':'RuntimeDefault'}}


def files():
    payloads={
        'database-mount':{'type':'database','description':'vCloud dynamic PostgreSQL credentials',
                          'config':{'default_lease_ttl':'15m','max_lease_ttl':'1h'}},
        'kv-mount':{'type':'kv','description':'vCloud static API keys','options':{'version':'2'}},
        'kv-config':{'cas_required':True,'max_versions':5},
        'kubernetes-mount':{'type':'kubernetes'},
        'kubernetes-config':{'kubernetes_host':'https://kubernetes.default.svc:443',
                             'disable_local_ca_jwt':False},
        'database-connection':{'plugin_name':'postgresql-database-plugin',
            'allowed_roles':['vcloud-app-readonly','vcloud-validation'],
            'connection_url':'postgresql://{{username}}:{{password}}@vcloud-postgres-rw.platform-services.svc.cluster.local:5432/vcloud?sslmode=verify-full&sslrootcert=/openbao/trust/postgres/ca.crt',
            'username':'openbao_manager','password_authentication':'scram-sha-256',
            'username_template':'{{ printf "vcloud_dyn_%s" (random 20) }}',
            'verify_connection':True},
    }
    for name,ttl,max_ttl in [('vcloud-app-readonly','15m','1h'),('vcloud-validation','2m','5m')]:
        payloads['database-role-'+name]={
            'db_name':'vcloud-postgres','default_ttl':ttl,'max_ttl':max_ttl,
            'credential_type':'password',
            'creation_statements':["SELECT vcloud_secret_lifecycle.create_login('{{name}}','{{password}}','{{expiration}}'::timestamptz);"],
            'renew_statements':["SELECT vcloud_secret_lifecycle.renew_login('{{name}}','{{expiration}}'::timestamptz);"],
            'revocation_statements':["SELECT vcloud_secret_lifecycle.revoke_login('{{name}}');"],
            'rollback_statements':["SELECT vcloud_secret_lifecycle.revoke_login('{{name}}');"],
            # Username templates are connection-level in the PostgreSQL plugin.
            # Both roles use the same managed prefix; ACL isolation is by lease path.
        }
    for name,account,policy,ttl in [('vcloud-csi-client','vcloud-secrets-client','vcloud-secrets-workload','10m'),
                                    ('vcloud-validation','vcloud-secret-validator','vcloud-secrets-validation','10m')]:
        payloads['kubernetes-role-'+name]={
            'bound_service_account_names':[account],'bound_service_account_namespaces':['workload-apps'],
            'audience':'openbao','token_policies':[policy],'token_ttl':ttl,'token_max_ttl':'1h',
            'token_no_default_policy':True,'token_type':'service','token_num_uses':0}
    out={f'module-4a/openbao/{name}.json':json.dumps(value,indent=2)+'\n' for name,value in payloads.items()}

    def meta(name,ns='workload-apps'):return {'name':name,'namespace':ns,'labels':{'app.kubernetes.io/part-of':'vcloud','vcloud.io/module':'4a'}}
    def obj(api,kind,name,ns='workload-apps',**kw):return {'apiVersion':api,'kind':kind,'metadata':meta(name,ns),**kw}
    accounts=[obj('v1','ServiceAccount',name,automountServiceAccountToken=False,
                  imagePullSecrets=[{'name':'vcloud-registry-pull'}]) for name in ['vcloud-secrets-client','vcloud-secret-validator']]
    reviewer=[{'apiVersion':'rbac.authorization.k8s.io/v1','kind':'ClusterRole','metadata':{'name':'vcloud-openbao-token-reviewer'},
              'rules':[{'apiGroups':['authentication.k8s.io'],'resources':['tokenreviews'],'verbs':['create']}]},
              {'apiVersion':'rbac.authorization.k8s.io/v1','kind':'ClusterRoleBinding','metadata':{'name':'vcloud-openbao-token-reviewer'},
               'roleRef':{'apiGroup':'rbac.authorization.k8s.io','kind':'ClusterRole','name':'vcloud-openbao-token-reviewer'},
               'subjects':[{'kind':'ServiceAccount','name':'openbao','namespace':'platform-services'}]}]
    spc=obj('secrets-store.csi.x-k8s.io/v1','SecretProviderClass','vcloud-openbao',spec={
        'provider':'openbao','parameters':{'roleName':'vcloud-csi-client','baoAuthMountPath':'kubernetes',
            'audience':'openbao',
            # Address/CA are configured at provider Agent integration so its lease
            # cache and renewals are retained; do not bypass it with baoAddress.
            'objects':yaml.safe_dump([
                {'objectName':'database.json','secretPath':'database/creds/vcloud-app-readonly','filePermission':288},
                {'objectName':'api-key','secretPath':'kv/data/vcloud/api','secretKey':'api_key','filePermission':288},
            ],sort_keys=False)}})
    deployment=obj('apps/v1','Deployment','vcloud-secrets-consumer',spec={
        'replicas':1,'selector':{'matchLabels':{'app':'vcloud-secrets-consumer'}},
        'template':{'metadata':{'labels':{'app':'vcloud-secrets-consumer'}},'spec':{
            'serviceAccountName':'vcloud-secrets-client','automountServiceAccountToken':False,
            'securityContext':{'runAsNonRoot':True,'runAsUser':65532,'runAsGroup':65532,'fsGroup':65532,
                               'seccompProfile':{'type':'RuntimeDefault'}},
            'containers':[{'name':'consumer','image':'registry.vcloud.example.com/vcloud/openbao-verifier:1.0.0',
                'imagePullPolicy':'IfNotPresent','command':['sleep','infinity'],
                'securityContext':SEC,'resources':{'requests':{'cpu':'25m','memory':'64Mi'},'limits':{'cpu':'100m','memory':'128Mi'}},
                'readinessProbe':{'exec':{'command':['python3','/opt/vcloud/check-csi.py']},'periodSeconds':10},
                'volumeMounts':[{'name':'scratch','mountPath':'/tmp'}]}],
            'volumes':[{'name':'scratch','emptyDir':{'medium':'Memory','sizeLimit':'16Mi'}}]}}})
    patch=[{'op':'test','path':'/spec/template/spec/serviceAccountName','value':'vcloud-secrets-client'},
           {'op':'add','path':'/spec/template/spec/volumes/-','value':{'name':'secrets','csi':{
               'driver':'secrets-store.csi.k8s.io','readOnly':True,'volumeAttributes':{'secretProviderClass':'vcloud-openbao'}}}},
           {'op':'add','path':'/spec/template/spec/containers/0/volumeMounts/-','value':{'name':'secrets','mountPath':'/run/vcloud-secrets','readOnly':True}}]
    import copy
    full=copy.deepcopy(deployment)
    full['spec']['template']['spec']['volumes'].append(patch[1]['value'])
    full['spec']['template']['spec']['containers'][0]['volumeMounts'].append(patch[2]['value'])
    pods=[obj('cilium.io/v2','CiliumNetworkPolicy','vcloud-secrets-consumer',spec={
        'endpointSelector':{'matchLabels':{'app':'vcloud-secrets-consumer'}},
        'egress':[{'toEndpoints':[{'matchLabels':{'k8s:io.kubernetes.pod.namespace':'kube-system','k8s:k8s-app':'kube-dns'}}],
                   'toPorts':[{'ports':[{'port':'53','protocol':'UDP'},{'port':'53','protocol':'TCP'}]}]},
                  {'toEndpoints':[{'matchLabels':{'k8s:io.kubernetes.pod.namespace':'platform-services','vcloud.io/component':'postgres'}}],
                   'toPorts':[{'ports':[{'port':'5432','protocol':'TCP'}]}]}]}),
          obj('cilium.io/v2','CiliumNetworkPolicy','vcloud-openbao-db',ns='platform-services',spec={
              'endpointSelector':{'matchLabels':{'vcloud.io/component':'postgres'}},
              'ingress':[{'fromEndpoints':[{'matchLabels':{'k8s:io.kubernetes.pod.namespace':'workload-apps','app':'vcloud-secrets-consumer'}},
                                          {'matchLabels':{'k8s:io.kubernetes.pod.namespace':'platform-services','app.kubernetes.io/name':'openbao'}}],
                          'toPorts':[{'ports':[{'port':'5432','protocol':'TCP'}]}]}]})]
    manifests={'serviceaccounts':accounts,'reviewer-rbac':reviewer,'secretproviderclass':[spc],'consumer':[full],'network':pods}
    validator=obj('v1','Pod','vcloud-secret-validator',spec={
        'serviceAccountName':'vcloud-secret-validator','automountServiceAccountToken':False,
        'restartPolicy':'Never','activeDeadlineSeconds':1800,
        'securityContext':{'runAsNonRoot':True,'runAsUser':65532,'runAsGroup':65532,'fsGroup':65532,'seccompProfile':{'type':'RuntimeDefault'}},
        'containers':[{'name':'validator','image':'registry.vcloud.example.com/vcloud/openbao-verifier:1.0.0','imagePullPolicy':'IfNotPresent',
            'command':['sleep','1800'],'securityContext':SEC,
            'resources':{'requests':{'cpu':'25m','memory':'64Mi'},'limits':{'cpu':'100m','memory':'128Mi'}},
            'volumeMounts':[{'name':'identity','mountPath':'/run/openbao-identity','readOnly':True},
                            {'name':'trust','mountPath':'/run/trust','readOnly':True},
                            {'name':'scratch','mountPath':'/tmp'}]}],
        'volumes':[{'name':'identity','projected':{'defaultMode':288,'sources':[{'serviceAccountToken':{'audience':'openbao','expirationSeconds':600,'path':'jwt'}}]}},
                   {'name':'trust','configMap':{'name':'vcloud-secrets-trust','defaultMode':292}},
                   {'name':'scratch','emptyDir':{'medium':'Memory','sizeLimit':'16Mi'}}]})
    validator['metadata']['labels']['vcloud.io/secret-test']='true'
    out['module-4a/examples/validator-pod.yaml']=yaml.safe_dump(validator,sort_keys=False)
    dns={'toEndpoints':[{'matchLabels':{'k8s:io.kubernetes.pod.namespace':'kube-system','k8s:k8s-app':'kube-dns'}}],
         'toPorts':[{'ports':[{'port':'53','protocol':'UDP'},{'port':'53','protocol':'TCP'}]}]}
    def port(*values):return [{'ports':[{'port':str(v),'protocol':'TCP'} for v in values]}]
    bao_selector={'k8s:io.kubernetes.pod.namespace':'platform-services','app.kubernetes.io/name':'openbao','component':'server'}
    provider_selector={'k8s:io.kubernetes.pod.namespace':'kube-system','app.kubernetes.io/name':'openbao-csi-provider'}
    validator_selector={'k8s:io.kubernetes.pod.namespace':'workload-apps','vcloud.io/secret-test':'true'}
    postgres_selector={'k8s:io.kubernetes.pod.namespace':'platform-services','vcloud.io/component':'postgres'}
    pods[1]['spec']['ingress'][0]['fromEndpoints'].append({'matchLabels':validator_selector})
    pods.extend([
        obj('cilium.io/v2','CiliumNetworkPolicy','vcloud-secret-validator',spec={'endpointSelector':{'matchLabels':{'vcloud.io/secret-test':'true'}},
            'egress':[dns,{'toEndpoints':[{'matchLabels':bao_selector}],'toPorts':port(8200)},
                      {'toEndpoints':[{'matchLabels':postgres_selector}],'toPorts':port(5432)}]}),
        obj('cilium.io/v2','CiliumNetworkPolicy','vcloud-openbao-server',ns='platform-services',spec={
            'endpointSelector':{'matchLabels':{'app.kubernetes.io/name':'openbao','component':'server'}},
            'ingress':[{'fromEndpoints':[{'matchLabels':provider_selector},{'matchLabels':validator_selector}],'toPorts':port(8200)},
                       {'fromEndpoints':[{'matchLabels':bao_selector}],'toPorts':port(8200,8201)},
                       {'fromEntities':['host','remote-node'],'toPorts':port(8200)}],
            'egress':[dns,{'toEntities':['kube-apiserver'],'toPorts':port(443,6443)},
                      {'toEndpoints':[{'matchLabels':postgres_selector}],'toPorts':port(5432)},
                      {'toEndpoints':[{'matchLabels':bao_selector}],'toPorts':port(8200,8201)}]}),
        obj('cilium.io/v2','CiliumNetworkPolicy','vcloud-openbao-provider',ns='kube-system',spec={
            'endpointSelector':{'matchLabels':{'app.kubernetes.io/name':'openbao-csi-provider'}},
            'ingress':[{'fromEntities':['host','remote-node'],'toPorts':port(8080)}],
            'egress':[dns,{'toEntities':['kube-apiserver'],'toPorts':port(443,6443)},
                      {'toEndpoints':[{'matchLabels':bao_selector}],'toPorts':port(8200)}]}),
    ])
    for name,items in manifests.items():
        out[f'module-4a/manifests/{name}.yaml']='# Generated by tools/render_module4a.py; contains no secret values.\n'+yaml.safe_dump_all(items,sort_keys=False)
    out['module-4a/examples/consumer-base.yaml']=yaml.safe_dump(deployment,sort_keys=False)
    out['module-4a/patches/consumer-csi.jsonpatch.yaml']=yaml.safe_dump(patch,sort_keys=False)
    out['module-4a/patches/static-secret-sync.jsonpatch.yaml']=yaml.safe_dump([{'op':'add','path':'/spec/secretObjects','value':[
        {'secretName':'vcloud-api-key-cache','type':'Opaque','data':[{'objectName':'api-key','key':'api-key'}]}]}],sort_keys=False)
    out['module-4a/patches/csi-fsgroup.mergepatch.yaml']=yaml.safe_dump({'spec':{
        'fsGroupPolicy':'File','requiresRepublish':True,
        'tokenRequests':[{'audience':'openbao','expirationSeconds':600}]}},sort_keys=False)
    out['module-4a/patches/cnpg-hba.mergepatch.yaml']=yaml.safe_dump({'spec':{'postgresql':{'pg_hba':[
        'hostnossl all all all reject',
        'hostssl vcloud +vcloud_db_readonly all scram-sha-256',
        'hostssl all +vcloud_db_readonly all reject',
        'hostssl vcloud openbao_manager all scram-sha-256',
        'hostssl all openbao_manager all reject',
        'hostssl all all all scram-sha-256']}}},sort_keys=False)
    return out


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--check',action='store_true');args=parser.parse_args()
    for relative,text in files().items():
        path=ROOT/relative
        if args.check:
            if not path.exists() or path.read_bytes()!=text.encode():raise SystemExit('Module 4a generated drift: '+relative)
        else:
            path.parent.mkdir(parents=True,exist_ok=True);path.write_text(text,encoding='utf-8',newline='\n')
    print('Module 4a public payloads and CSI manifests '+('checked' if args.check else 'generated'))


if __name__=='__main__':main()
