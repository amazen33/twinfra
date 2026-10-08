#!/usr/bin/env python3
"""Fail-closed offline IAM/reference validation. Does not validate real JWTs or apply IAM."""
import argparse,copy,gzip,hashlib,json,re,subprocess,sys
from pathlib import Path
import yaml
ROOT=Path(__file__).resolve().parents[1];MODULE=ROOT/'module-4b'
sys.path.insert(0,str(ROOT/'tools'))
from build_module2_schemas import compact
from render_module4b import ISSUER,PREFIX,base_route,files

def bundle():
    lock=json.loads((MODULE/'artifacts.lock.json').read_text())
    for p,digest in lock['filesSHA256'].items():
        if not (ROOT/p).resolve().is_relative_to(MODULE.resolve()) or hashlib.sha256((ROOT/p).read_bytes()).hexdigest()!=digest:
            raise ValueError('Locked IAM source/schema drift: '+p)
    for source in lock['sources']:
        if hashlib.sha256(gzip.decompress((ROOT/source['file']).read_bytes())).hexdigest()!=source['sourceSHA256']:
            raise ValueError('Upstream source reconstruction drift')
    crd=yaml.safe_load(gzip.decompress((MODULE/'vendor/apisixpluginconfig-crd.yaml.gz').read_bytes()))
    v=next(v for v in crd['spec']['versions'] if v['name']=='v2')
    if not v['served'] or v.get('deprecated'):raise ValueError('Unsupported IAM CRD API')
    s=compact(v['schema']['openAPIV3Schema']);s['$schema']='http://json-schema.org/draft-07/schema#'
    s['properties']['metadata']=json.loads((ROOT/'module-2/schemas/namespace_v1.json').read_text())['properties']['metadata']
    s['properties']['apiVersion']={'type':'string','enum':['apisix.apache.org/v2']};s['properties']['kind']={'type':'string','enum':['ApisixPluginConfig']}
    s['required']=list(dict.fromkeys(s.get('required',[])+['apiVersion','kind','metadata']))
    if (MODULE/'schemas/apisix.apache.org/apisixpluginconfig_v2.json').read_bytes()!=(json.dumps(s,separators=(',',':'))+'\n').encode():
        raise ValueError('IAM schema reproduction drift')
    lua=gzip.decompress((MODULE/'vendor/openid-connect.lua.gz').read_bytes()).decode()
    if 'client_secret_optional = (conf.public_key or conf.use_jwks)' not in lua or 'required_scopes_present' not in lua:
        raise ValueError('Selected APISIX release lacks required secret-free JWT/scope behavior')
    return lock

def realm_contract(r):
    if r['realm']!='vcloud' or r['sslRequired']!='all' or r['registrationAllowed'] or r.get('users') or r['defaultSignatureAlgorithm']!='RS256':
        raise ValueError('Realm identity/TLS/user provisioning drift')
    if r['accessTokenLifespan']>300 or not r['bruteForceProtected'] or not r['revokeRefreshToken'] or r['refreshTokenMaxReuse']!=0:
        raise ValueError('Realm lifetime/abuse/refresh hardening drift')
    if r.get('adminEventsDetailsEnabled'):raise ValueError('Sensitive admin event detail logging prohibited')
    fields=lambda name:set(re.findall(r'protected [^;\n]+ (\w+);',gzip.decompress((MODULE/f'vendor/{name}.java.gz').read_bytes()).decode()))
    if set(r)-fields('RealmRepresentation'):raise ValueError('Unrecognized pinned realm representation field')
    clients={c['clientId']:c for c in r['clients']}
    if set(clients)!={'vcloud-function','vcloud-api-cli','vcloud-kubernetes'}:raise ValueError('Unexpected IAM client')
    for c in clients.values():
        if set(c)-fields('ClientRepresentation'):raise ValueError('Unrecognized pinned client representation field')
        if not c['publicClient'] or c['implicitFlowEnabled'] or c['directAccessGrantsEnabled'] or c['serviceAccountsEnabled'] or c['fullScopeAllowed'] or 'secret' in c:
            raise ValueError('Unsafe client grant/role/credential configuration')
        if c['attributes'].get('pkce.code.challenge.method')!='S256':raise ValueError('PKCE S256 required')
        if c['webOrigins'] or any('*' in u for u in c['redirectUris']):raise ValueError('Redirect/origin expansion')
    if not clients['vcloud-function']['bearerOnly'] or clients['vcloud-function']['standardFlowEnabled'] or clients['vcloud-function']['redirectUris']:
        raise ValueError('Resource client must not grant tokens or redirect browsers')
    if clients['vcloud-kubernetes']['defaultClientScopes']!=['kubernetes-groups'] or clients['vcloud-api-cli']['defaultClientScopes']!=['function.read']:
        raise ValueError('API and Kubernetes token scopes must stay separate')
    scopes={s['name']:s for s in r['clientScopes']}
    group=scopes['kubernetes-groups']['protocolMappers'][0]
    if group['protocolMapper']!='oidc-group-membership-mapper' or group['config']!={'claim.name':'groups','full.path':'true','id.token.claim':'true','access.token.claim':'false','userinfo.token.claim':'false'}:
        raise ValueError('Kubernetes ID-token group mapper drift')
    audience=scopes['function.read']['protocolMappers'][0]
    if audience['protocolMapper']!='oidc-audience-mapper' or audience['config']!={'included.client.audience':'vcloud-function','access.token.claim':'true','id.token.claim':'false'}:
        raise ValueError('API access-token audience mapper drift')
    if r['scopeMappings']!=[{'clientScope':'function.read','roles':['vcloud-function-reader']}]:raise ValueError('API scope role gate drift')
    otp=r['requiredActions'][0]
    if otp['alias']!='CONFIGURE_TOTP' or not otp['enabled'] or not otp['defaultAction']:raise ValueError('New-user OTP enrollment required')
    password=[a for a in r['requiredActions'] if a['alias']=='UPDATE_PASSWORD']
    if len(password)!=1 or not password[0]['enabled'] or password[0]['providerId']!='UPDATE_PASSWORD' or password[0]['defaultAction']:
        raise ValueError('Enabled built-in temporary password change required')

def plugin_contract(item):
    if item['kind']!='ApisixPluginConfig' or item['apiVersion']!='apisix.apache.org/v2' or item['metadata']['namespace']!='platform-services':
        raise ValueError('Wrong OIDC resource API/namespace')
    plugins=item['spec']['plugins']
    if len(plugins)!=1 or plugins[0]['name']!='openid-connect' or plugins[0]['enable'] is not True:raise ValueError('OIDC must be enabled')
    c=plugins[0]['config']
    if any(c.get(k) is not True for k in ['bearer_only','use_jwks','ssl_verify','set_access_token_header','access_token_in_authorization_header']):
        raise ValueError('Gateway authentication/TLS bypass')
    if any(c.get(k) is not False for k in ['accept_none_alg','accept_unsupported_alg','set_id_token_header','set_userinfo_header','set_refresh_token_header']):
        raise ValueError('Unsigned token or unsafe identity forwarding')
    if 'client_secret' in c or plugins[0].get('secretRef') or c['unauth_action']!='deny':raise ValueError('JWT mode must deny unauthenticated requests and require no client secret')
    if c['client_id']!='vcloud-function' or c['discovery']!=ISSUER+'/.well-known/openid-configuration' or c['token_signing_alg_values_expected']!='RS256':
        raise ValueError('Gateway issuer/client/signing algorithm drift')
    if c['claim_validator']!={'issuer':{'valid_issuers':[ISSUER]},'audience':{'required':True,'match_with_client_id':True}} or c['required_scopes']!=['function.read']:
        raise ValueError('Gateway issuer/audience/scope bypass')

def rbac_contract(items):
    roles={o['metadata']['name']:o for o in items if o['kind']=='ClusterRole'}
    if set(roles)!={'vcloud-cluster-observer','vcloud-workload-reader'}:raise ValueError('Unexpected IAM role')
    for role in roles.values():
        for rule in role['rules']:
            if set(rule['verbs'])-{'get','list','watch'} or any('*' in v for v in rule['resources']+rule['apiGroups']) or set(rule['resources'])&{'secrets','pods/exec','pods/log','serviceaccounts/token'}:
                raise ValueError('Human IAM role can mutate, escalate or access credentials')
    bindings=[o for o in items if o['kind'].endswith('Binding')]
    expected={('ClusterRoleBinding',''):(PREFIX+'/vcloud/cluster-observers','vcloud-cluster-observer'),
        ('RoleBinding','workload-apps'):(PREFIX+'/vcloud/workload-readers','vcloud-workload-reader'),
        ('RoleBinding','hpc-compute'):(PREFIX+'/vcloud/hpc-readers','vcloud-workload-reader')}
    if len(bindings)!=3:raise ValueError('Unexpected IAM bindings')
    for b in bindings:
        identity=(b['kind'],b['metadata'].get('namespace',''))
        if identity not in expected or len(b['subjects'])!=1:raise ValueError('IAM binding scope expansion')
        group,ref=expected[identity]
        if b['subjects'][0]!={'kind':'Group','apiGroup':'rbac.authorization.k8s.io','name':group} or b['roleRef']!={'apiGroup':'rbac.authorization.k8s.io','kind':'ClusterRole','name':ref}:
            raise ValueError('IAM group prefix/path or role binding drift')
        if b['kind']=='ClusterRoleBinding' and roles[ref]['rules']!=[{'apiGroups':[''],'resources':['nodes','namespaces'],'verbs':['get','list','watch']}]:
            raise ValueError('Cluster-wide IAM privilege expansion')

def identity_contract(items):
    route=next(o for o in items if o['kind']=='ApisixRoute')['spec']['http'][0]
    if route['match']['hosts']!=['auth.vcloud.example.com'] or route['match']['paths']!=['/realms/vcloud/*','/resources/*'] or route['match']['methods']!=['GET','POST']:
        raise ValueError('Public identity route exposes unreviewed realm/admin paths')
    if route.get('plugin_config_name') or any(p['name']=='openid-connect' for p in route['plugins']):raise ValueError('Public login/discovery must not require a bearer token')
    if route['match']['exprs']!=[{'subject':{'scope':'Variable','name':'scheme'},'op':'Equal','value':'https'}]:raise ValueError('Identity ingress requires HTTPS')
    headers=route['plugins'][0]['config']['headers']
    if headers!={'set':{'X-Forwarded-Host':'auth.vcloud.example.com','X-Forwarded-Proto':'https','X-Forwarded-Port':'443','X-Forwarded-For':'$remote_addr'},'remove':['Forwarded']}:
        raise ValueError('Identity proxy header spoofing boundary drift')
    upstream=next(o for o in items if o['kind']=='ApisixUpstream')['spec']
    if upstream['scheme']!='https' or upstream['upstreamHost']!='auth.vcloud.example.com':raise ValueError('Identity upstream requires canonical TLS name')

def apply_patch(base,operations):
    result=copy.deepcopy(base)
    for op in operations:
        parts=op['path'].strip('/').split('/');parent=result
        for k in parts[:-1]:parent=parent[int(k)] if isinstance(parent,list) else parent[k]
        key=int(parts[-1]) if isinstance(parent,list) else parts[-1]
        if op['op']=='test':
            if parent[key]!=op['value']:raise ValueError('Gateway patch target drift')
        elif op['op'] in ('add','replace'):parent[key]=copy.deepcopy(op['value'])
        else:raise ValueError('Unsupported gateway patch')
    return result

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--kubeconform',default='kubeconform');args=parser.parse_args()
    lock=bundle();subprocess.run([sys.executable,str(ROOT/'tools/render_module4b.py'),'--check'],check=True)
    realm_contract(json.loads((MODULE/'keycloak/vcloud-realm.json').read_text()))
    plugin_contract(yaml.safe_load((MODULE/'manifests/oidc-plugin.yaml').read_text()))
    rbac_contract(list(yaml.safe_load_all((MODULE/'manifests/rbac.yaml').read_text())))
    identity_contract(list(yaml.safe_load_all((MODULE/'manifests/identity-gateway.yaml').read_text())))
    operations=yaml.safe_load((MODULE/'patches/gateway-route.jsonpatch.yaml').read_text())
    if apply_patch(base_route(),operations)!=yaml.safe_load((MODULE/'examples/secure-function.yaml').read_text()):raise ValueError('Gateway patch composition drift')
    paths=sorted((MODULE/'manifests').glob('*.yaml'))+[MODULE/'examples/secure-function.yaml']
    cmd=[args.kubeconform,'-strict','-summary','-kubernetes-version','1.36.5']
    for directory in [MODULE/'schemas',ROOT/'module-2/schemas']:
        for pattern in ['{{.Group}}/{{.ResourceKind}}_{{.ResourceAPIVersion}}.json','{{.ResourceKind}}_{{.ResourceAPIVersion}}.json']:
            cmd+=['-schema-location',str(directory/pattern)]
    output=subprocess.check_output(cmd+[str(p) for p in paths],text=True);print(output.strip())
    report={'status':'passed','module':'4b','versions':lock['versions'],'scope':'Offline IAM reference/schema validation; live Keycloak/APISIX/API-server not executed',
      'schemaValidation':output.strip(),'schemaReproducibility':1,'gatewayPatchComposition':'passed','liveAcceptance':'not executed'}
    build=ROOT/'.build/module-4b';build.mkdir(parents=True,exist_ok=True)
    (build/'validation.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8',newline='\n')
    print('IAM realm/client, secret-free OIDC and least-privilege group contracts passed')
if __name__=='__main__':main()
