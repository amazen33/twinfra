#!/usr/bin/env python3
"""Generate public IAM references; never create users, credentials or live resources."""
import argparse,copy,json
from pathlib import Path
import yaml

ROOT=Path(__file__).resolve().parents[1]
ISSUER='https://auth.vcloud.example.com/realms/vcloud'
PREFIX='keycloak:'

def mapper(name,kind,config):
    return {'name':name,'protocol':'openid-connect','protocolMapper':kind,'consentRequired':False,'config':config}

def realm():
    clients=[]
    for name,redirects,scopes,bearer in [
        ('vcloud-function',[],[],True),
        ('vcloud-api-cli',['http://127.0.0.1:18000/callback'],['function.read'],False),
        ('vcloud-kubernetes',['http://localhost:8000','http://localhost:18000'],['kubernetes-groups'],False)]:
        clients.append({'clientId':name,'name':name,'enabled':True,'protocol':'openid-connect',
            'publicClient':True,'bearerOnly':bearer,'standardFlowEnabled':not bearer,
            'implicitFlowEnabled':False,'directAccessGrantsEnabled':False,'serviceAccountsEnabled':False,
            'fullScopeAllowed':False,'redirectUris':redirects,'webOrigins':[],
            'defaultClientScopes':scopes,'optionalClientScopes':[],
            'attributes':{'pkce.code.challenge.method':'S256','access.token.lifespan':'300',
                          'id.token.signed.response.alg':'RS256'}})
    return {'realm':'vcloud','displayName':'vCloud','enabled':True,'sslRequired':'all',
        'registrationAllowed':False,'resetPasswordAllowed':False,'rememberMe':False,
        'loginWithEmailAllowed':False,'duplicateEmailsAllowed':False,'editUsernameAllowed':False,
        'bruteForceProtected':True,'failureFactor':5,'waitIncrementSeconds':60,'maxFailureWaitSeconds':900,
        'accessTokenLifespan':300,'accessCodeLifespan':60,'ssoSessionIdleTimeout':900,'ssoSessionMaxLifespan':28800,
        'revokeRefreshToken':True,'refreshTokenMaxReuse':0,'defaultSignatureAlgorithm':'RS256',
        'eventsEnabled':True,'eventsExpiration':604800,'adminEventsEnabled':True,'adminEventsDetailsEnabled':False,
        'roles':{'realm':[{'name':'vcloud-function-reader','description':'May request the function.read API scope'}]},
        'groups':[{'name':'vcloud','subGroups':[{'name':name,**({'realmRoles':['vcloud-function-reader']} if name=='api-users' else {})}
            for name in ['api-users','cluster-observers','workload-readers','hpc-readers']]}],
        'users':[], 'clients':clients,
        'clientScopes':[
          {'name':'function.read','protocol':'openid-connect','attributes':{'include.in.token.scope':'true'},
           'protocolMappers':[mapper('function-audience','oidc-audience-mapper',
               {'included.client.audience':'vcloud-function','access.token.claim':'true','id.token.claim':'false'})]},
          {'name':'kubernetes-groups','protocol':'openid-connect','attributes':{'include.in.token.scope':'true'},
           'protocolMappers':[mapper('kubernetes-groups','oidc-group-membership-mapper',
               {'claim.name':'groups','full.path':'true','id.token.claim':'true','access.token.claim':'false','userinfo.token.claim':'false'})]}],
        'scopeMappings':[{'clientScope':'function.read','roles':['vcloud-function-reader']}],
        'requiredActions':[{'alias':'CONFIGURE_TOTP','name':'Configure OTP','providerId':'CONFIGURE_TOTP',
                            'enabled':True,'defaultAction':True,'priority':40,'config':{}},
                           {'alias':'UPDATE_PASSWORD','name':'Update Password','providerId':'UPDATE_PASSWORD',
                            'enabled':True,'defaultAction':False,'priority':30,'config':{}}]}

def plugin():
    return {'apiVersion':'apisix.apache.org/v2','kind':'ApisixPluginConfig',
        'metadata':{'name':'vcloud-oidc','namespace':'platform-services','labels':{'app.kubernetes.io/part-of':'vcloud'}},
        'spec':{'ingressClassName':'apisix','plugins':[{'name':'openid-connect','enable':True,'config':{
            'client_id':'vcloud-function','discovery':ISSUER+'/.well-known/openid-configuration',
            'bearer_only':True,'use_jwks':True,'ssl_verify':True,'unauth_action':'deny',
            'accept_none_alg':False,'accept_unsupported_alg':False,'token_signing_alg_values_expected':'RS256',
            'required_scopes':['function.read'],'realm':'vcloud',
            'claim_validator':{'issuer':{'valid_issuers':[ISSUER]},'audience':{'required':True,'match_with_client_id':True}},
            'set_access_token_header':True,'access_token_in_authorization_header':True,
            'set_id_token_header':False,'set_userinfo_header':False,'set_refresh_token_header':False}}]}}

def rbac():
    api='rbac.authorization.k8s.io/v1'
    role=lambda name,rules:{'apiVersion':api,'kind':'ClusterRole','metadata':{'name':name},'rules':rules}
    binding=lambda kind,name,group,ref,ns=None:{'apiVersion':api,'kind':kind,
        'metadata':{'name':name,**({'namespace':ns} if ns else {})},
        'subjects':[{'kind':'Group','apiGroup':'rbac.authorization.k8s.io','name':PREFIX+'/vcloud/'+group}],
        'roleRef':{'kind':'ClusterRole','apiGroup':'rbac.authorization.k8s.io','name':ref}}
    return [role('vcloud-cluster-observer',[{'apiGroups':[''],'resources':['nodes','namespaces'],'verbs':['get','list','watch']}]),
        binding('ClusterRoleBinding','vcloud-keycloak-cluster-observers','cluster-observers','vcloud-cluster-observer'),
        role('vcloud-workload-reader',[
            {'apiGroups':[''],'resources':['pods','services','events'],'verbs':['get','list','watch']},
            {'apiGroups':['apps'],'resources':['deployments','replicasets','statefulsets'],'verbs':['get','list','watch']},
            {'apiGroups':['batch'],'resources':['jobs','cronjobs'],'verbs':['get','list','watch']}]),
        binding('RoleBinding','vcloud-keycloak-workload-readers','workload-readers','vcloud-workload-reader','workload-apps'),
        binding('RoleBinding','vcloud-keycloak-hpc-readers','hpc-readers','vcloud-workload-reader','hpc-compute')]

def base_route():
    return next(o for o in yaml.safe_load_all((ROOT/'module-2/manifests/function.yaml').read_text()) if o and o['kind']=='ApisixRoute')

def route_patch():
    route=base_route();rewrite=copy.deepcopy(route['spec']['http'][0]['plugins'][0])
    rewrite['config']['headers']={'remove':['X-ID-Token','X-Userinfo','X-Access-Token','X-Raw-ID-Token','X-Refresh-Token','X-User','X-Groups']}
    return [{'op':'test','path':'/metadata/name','value':'secure-function'},
            {'op':'test','path':'/spec/http/0/plugins/1/name','value':'openid-connect'},
            {'op':'replace','path':'/spec/http/0/plugins','value':[rewrite]},
            {'op':'add','path':'/spec/http/0/plugin_config_name','value':'vcloud-oidc'},
            {'op':'add','path':'/spec/http/0/plugin_config_namespace','value':'platform-services'}]

def compose_route():
    route=base_route();r=route['spec']['http'][0];r['plugins']=route_patch()[2]['value']
    r['plugin_config_name']='vcloud-oidc';r['plugin_config_namespace']='platform-services';return route

def oidc_args():
    return [{'name':name,'value':value} for name,value in [
        ('oidc-issuer-url',ISSUER),('oidc-client-id','vcloud-kubernetes'),('oidc-username-claim','sub'),
        ('oidc-username-prefix',PREFIX),('oidc-groups-claim','groups'),('oidc-groups-prefix',PREFIX),
        ('oidc-signing-algs','RS256'),('oidc-ca-file','/etc/kubernetes/pki/keycloak-ca.crt')]]

def identity_gateway():
    api='apisix.apache.org/v2';meta=lambda name:{'name':name,'namespace':'platform-services'}
    return [
      {'apiVersion':api,'kind':'ApisixTls','metadata':meta('vcloud-keycloak-public'),
       'spec':{'ingressClassName':'apisix','hosts':['auth.vcloud.example.com'],
               'secret':{'name':'keycloak-gateway-tls','namespace':'platform-services'}}},
      {'apiVersion':api,'kind':'ApisixUpstream','metadata':meta('keycloak'),
       'spec':{'ingressClassName':'apisix','scheme':'https','passHost':'rewrite','upstreamHost':'auth.vcloud.example.com',
               'retries':0,'timeout':{'connect':'5s','send':'60s','read':'60s'}}},
      {'apiVersion':api,'kind':'ApisixRoute','metadata':meta('vcloud-keycloak-public'),
       'spec':{'ingressClassName':'apisix','http':[{'name':'vcloud-realm',
         'match':{'hosts':['auth.vcloud.example.com'],'paths':['/realms/vcloud/*','/resources/*'],'methods':['GET','POST'],
                  'exprs':[{'subject':{'scope':'Variable','name':'scheme'},'op':'Equal','value':'https'}]},
         'backends':[{'serviceName':'keycloak','servicePort':443,'resolveGranularity':'service'}],
         'plugins':[{'name':'proxy-rewrite','enable':True,'config':{'headers':{'set':{
           'X-Forwarded-Host':'auth.vcloud.example.com','X-Forwarded-Proto':'https','X-Forwarded-Port':'443',
           'X-Forwarded-For':'$remote_addr'},
           'remove':['Forwarded']}}}]}]}}]

def files():
    def y(obj):return '# Generated public reference by tools/render_module4b.py.\n'+yaml.safe_dump(obj,sort_keys=False)
    return {'module-4b/keycloak/vcloud-realm.json':json.dumps(realm(),indent=2)+'\n',
        'module-4b/manifests/oidc-plugin.yaml':y(plugin()),
        'module-4b/manifests/rbac.yaml':'# Generated least-privilege group bindings.\n'+yaml.safe_dump_all(rbac(),sort_keys=False),
        'module-4b/manifests/identity-gateway.yaml':'# Public realm/resources only; no admin or master-realm route.\n'+yaml.safe_dump_all(identity_gateway(),sort_keys=False),
        'module-4b/patches/gateway-route.jsonpatch.yaml':y(route_patch()),
        'module-4b/examples/secure-function.yaml':y(compose_route()),
        'module-4b/kubernetes/kubeadm-oidc-args.yaml':y(oidc_args())}

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--check',action='store_true');args=parser.parse_args()
    for relative,text in files().items():
        path=ROOT/relative
        if args.check:
            if not path.exists() or path.read_bytes()!=text.encode():raise SystemExit('Module 4b reference drift: '+relative)
        else:path.parent.mkdir(parents=True,exist_ok=True);path.write_text(text,encoding='utf-8',newline='\n')
    print('Module 4b public realm, APISIX and RBAC references '+('checked' if args.check else 'generated'))
if __name__=='__main__':main()
