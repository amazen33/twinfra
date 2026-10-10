#!/usr/bin/env python3
"""Generate the opt-in vCloud console; bootstrap/data remain separately owned."""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import re
import subprocess
import yaml
from wsl_platform import ROOT, NS, PYTHON, resource, cnp, ports
from wsl_localstack import CLASS, NAME as LOCALSTACK, deploy, config, service
from wsl_endpoints import check, validate

HERE = ROOT / 'lab/wsl/console'


def profile():
    value = json.loads((HERE / 'profile.json').read_text(encoding='utf-8'))
    if value['name'] != 'vcloud-wsl-local' or value['host'] != 'console.vcloud.local':
        raise ValueError('Only the vCloud WSL console profile is supported')
    if value['origin'] != 'http://console.vcloud.local:18080':
        raise ValueError('Unexpected local origin')
    if {b['name'] for b in value['backends']} != {'spinifex', 'ministack', 'localstack', 'storage', 'dynamodb', 'vault'}:
        raise ValueError('Backend inventory differs')
    if any(b['enabled'] for b in value['backends'] if b['name'] in ('spinifex', 'vault')):
        raise ValueError('Spinifex/OpenBao integrations require separate site acceptance')
    return value


def image():
    item = json.loads((HERE / 'artifacts.lock.json').read_text(encoding='utf-8'))['images']['ministack']
    if not re.fullmatch('sha256:[a-f0-9]{64}', item['digest']):
        raise ValueError('Immutable digest required')
    if item['canonical'] != 'registry.vcloud.example.com/' + item['source'] or not item['source'].endswith('@' + item['digest']):
        raise ValueError('Mirror image differs')
    return item['canonical']


def workloads():
    data = {'ui.py': (ROOT / 'console/aws_views.py').read_text(encoding='utf-8'), 'profile.json': (HERE / 'profile.json').read_text(encoding='utf-8')}
    result = [config('vcloud-console-code', data)]
    health = {'exec': {'command': ['python', '-c', "import urllib.request,os; urllib.request.urlopen('http://127.0.0.1:'+os.environ['PORT']+'/healthz',timeout=2)"]}, 'timeoutSeconds': 3}
    for name, port, view in [('vcloud-console-shell', 3000, 'shell'), ('storage-ui', 9001, 'storage'), ('dynamodb-admin', 8081, 'dynamodb')]:
        container = {'name': 'ui', 'image': PYTHON, 'command': ['python', '-B', '/app/ui.py'],
            'env': [{'name': 'PORT', 'value': str(port)}, {'name': 'VCLOUD_VIEW', 'value': view}],
            'ports': [{'name': 'http', 'containerPort': port}],
            'resources': {'requests': {'cpu': '25m', 'memory': '32Mi'}, 'limits': {'cpu': '250m', 'memory': '128Mi'}},
            'volumeMounts': [{'name': 'code', 'mountPath': '/app', 'readOnly': True}],
            'readinessProbe': copy.deepcopy(health), 'livenessProbe': copy.deepcopy(health)}
        obj = deploy(name, [container], [{'name': 'code', 'configMap': {'name': 'vcloud-console-code'}}])
        obj['spec']['template']['metadata']['annotations'] = {'vcloud.io/config-hash': hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()}
        result += [obj, service(name, port)]
    mini = {'name': 'ministack', 'image': image(), 'ports': [{'name': 'http', 'containerPort': 4566}],
        'env': [{'name': 'GATEWAY_PORT', 'value': '4566'}, {'name': 'S3_PERSIST', 'value': '0'},
                {'name': 'MINISTACK_PERSIST', 'value': '0'}, {'name': 'PYTHONDONTWRITEBYTECODE', 'value': '1'},
                {'name': 'HOME', 'value': '/tmp'}, {'name': 'USE_SSL', 'value': '0'}],
        'resources': {'requests': {'cpu': '50m', 'memory': '128Mi'}, 'limits': {'cpu': '1', 'memory': '512Mi'}},
        'volumeMounts': [{'name': 'tmp', 'mountPath': '/tmp'}],
        'readinessProbe': {'exec': {'command': ['python', '-c', "import urllib.request; urllib.request.urlopen('http://127.0.0.1:4566/_ministack/health',timeout=2)"]}, 'timeoutSeconds': 3},
        'startupProbe': {'exec': {'command': ['python', '-c', "import urllib.request; urllib.request.urlopen('http://127.0.0.1:4566/_ministack/health',timeout=2)"]}, 'timeoutSeconds': 3, 'failureThreshold': 30, 'periodSeconds': 5}}
    result += [deploy('ministack', [mini], [{'name': 'tmp', 'emptyDir': {'medium': 'Memory', 'sizeLimit': '128Mi'}}]), service('ministack', 4566)]
    # A real ClusterIP alias selects the existing LocalStack Pod. ExternalName
    # has no endpoints in our pinned controller; don't duplicate the emulator.
    alias = service('localstack', 4566)
    alias['spec']['selector'] = {'app.kubernetes.io/name': LOCALSTACK}
    result.append(alias)
    check(result)
    return result


def plugins(prefix=None):
    p = profile(); oidc = p['oidc']; origin = p['origin']
    rewrite = {'headers': {'set': {'X-Forwarded-Host': 'console.vcloud.local:18080', 'X-Forwarded-Proto': 'http'}}}
    if prefix:
        rewrite['regex_uri'] = ['^/' + prefix + '(?:/(.*))?$', '/$1']
        rewrite['headers']['set']['X-Forwarded-Prefix'] = '/' + prefix
    # Runs before OIDC. proxy-rewrite runs AFTER OIDC, so clearing identity
    # headers there would discard the authenticated headers we want to preserve.
    scrub = "return function(conf, ctx) ngx.req.clear_header('X-Access-Token'); ngx.req.clear_header('X-ID-Token'); ngx.req.clear_header('X-Userinfo'); ngx.req.clear_header('X-Refresh-Token'); ngx.req.clear_header('X-Raw-ID-Token') end"
    return [
        {'name': 'serverless-pre-function', 'enable': True, 'config': {'phase': 'rewrite', 'functions': [scrub], '_meta': {'priority': 10000}}},
        {'name': 'openid-connect', 'enable': True, 'secretRef': oidc['secret'], 'config': {
            'client_id': oidc['client_id'], 'discovery': oidc['issuer'] + '/.well-known/openid-configuration',
            'bearer_only': False, 'unauth_action': 'auth', 'ssl_verify': True, 'use_pkce': True,
            'scope': 'openid', 'redirect_uri': origin + '/oidc/callback', 'logout_path': '/oidc/logout',
            'session': {'cookie_name': 'vcloud_console', 'cookie_path': '/', 'cookie_secure': False,
                        'cookie_http_only': True, 'cookie_same_site': 'Lax', 'idling_timeout': 900, 'absolute_timeout': 3600},
            'set_access_token_header': True, 'access_token_in_authorization_header': False,
            'set_id_token_header': True, 'set_userinfo_header': False, 'set_refresh_token_header': False,
            'accept_none_alg': False, 'accept_unsupported_alg': False, 'token_signing_alg_values_expected': 'RS256',
            'claim_validator': {'issuer': {'valid_issuers': [oidc['issuer']]}, 'audience': {'required': True, 'match_with_client_id': True}}}},
        {'name': 'proxy-rewrite', 'enable': True, 'config': rewrite},
        {'name': 'cors', 'enable': True, 'config': {'allow_origins': origin, 'allow_credential': True,
            'allow_methods': 'GET,POST,PUT,DELETE,HEAD,OPTIONS',
            'allow_headers': 'Authorization,Content-Type,X-Amz-Date,X-Amz-Target,X-Amz-Security-Token,X-Amz-Content-Sha256',
            'expose_headers': 'ETag', 'max_age': 300}},
        {'name': 'response-rewrite', 'enable': True, 'config': {'headers': {'set': {
            'X-Frame-Options': 'SAMEORIGIN', 'Access-Control-Allow-Origin': origin,
            'Access-Control-Allow-Credentials': 'true', 'X-Content-Type-Options': 'nosniff'}}}},
        {'name': 'prometheus', 'enable': True},
    ]


def routes(references=False):
    p = profile()
    shell = {'name': 'shell', 'service': 'vcloud-console-shell', 'namespace': NS, 'port': 3000, 'enabled': True, 'websocket': False}
    result = []
    for b in [shell] + p['backends']:
        if b['enabled'] == references:
            continue
        prefix = None if b['name'] == 'shell' else b['name']
        rule = {'name': b['name'], 'priority': 5 if prefix is None else 100,
            'match': {'hosts': [p['host']], 'paths': ['/*'] if prefix is None else ['/' + prefix, '/' + prefix + '/*']},
            'backends': [{'serviceName': b['service'], 'servicePort': b['port'], 'resolveGranularity': 'service'}],
            'websocket': b['websocket'], 'plugins': plugins(prefix)}
        obj = resource('ApisixRoute', 'vcloud-console-' + b['name'], {'ingressClassName': CLASS, 'http': [rule]}, b['namespace'], 'apisix.apache.org/v2')
        if references:
            obj['metadata']['annotations'] = {'vcloud.io/activation': 'disabled-reference-do-not-apply'}
        result.append(obj)
    return result


def network():
    endpoint = lambda name: {'matchLabels': {'k8s:io.kubernetes.pod.namespace': NS, 'k8s:app.kubernetes.io/name': name}}
    api = endpoint('apisix'); mini = endpoint('ministack'); local = endpoint(LOCALSTACK)
    result = []
    for name, port in [('vcloud-console-shell', 3000), ('storage-ui', 9001), ('dynamodb-admin', 8081), ('ministack', 4566)]:
        sources = [api] if name != 'ministack' else [api, endpoint('storage-ui'), endpoint('dynamodb-admin')]
        out = [] if name in ('vcloud-console-shell', 'ministack') else [{'toEndpoints': [mini, local], 'toPorts': ports(4566)}]
        result.append(cnp('vcloud-console-' + name, {'k8s:app.kubernetes.io/name': name}, [{'fromEndpoints': sources, 'toPorts': ports(port)}], out))
    result.append(cnp('vcloud-console-localstack-ui', {'k8s:app.kubernetes.io/name': LOCALSTACK},
        [{'fromEndpoints': [endpoint('storage-ui'), endpoint('dynamodb-admin')], 'toPorts': ports(4566)}], []))
    result.append(cnp('vcloud-console-gateway', {'k8s:app.kubernetes.io/name': 'apisix'}, [],
        [{'toEndpoints': [endpoint(name)], 'toPorts': ports(port)} for name, port in
         [('vcloud-console-shell', 3000), ('storage-ui', 9001), ('dynamodb-admin', 8081), ('ministack', 4566), ('keycloak', 8443)]]))
    return result


def definitions():
    project = resource('AppProject', 'vcloud-wsl-console', {
        'sourceRepos': ['https://github.com/amazen33/twinfra.git'],
        'destinations': [{'server': 'https://kubernetes.default.svc', 'namespace': NS}],
        'clusterResourceWhitelist': [], 'namespaceResourceWhitelist': [{'group': g, 'kind': k} for g, k in
            [('', 'ConfigMap'), ('', 'Service'), ('apps', 'Deployment'), ('apisix.apache.org', 'ApisixRoute')]]}, NS, 'argoproj.io/v1alpha1')
    app = resource('Application', 'vcloud-wsl-console', {'project': 'vcloud-wsl-console',
        'destination': {'server': 'https://kubernetes.default.svc', 'namespace': NS},
        'source': {'repoURL': 'https://github.com/amazen33/twinfra.git', 'targetRevision': 'main', 'path': 'lab/wsl/console/gitops'},
        'syncPolicy': {'automated': {'enabled': True, 'selfHeal': True, 'prune': False},
                       'syncOptions': ['CreateNamespace=false', 'ServerSideApply=true']}}, NS, 'argoproj.io/v1alpha1')
    return [project, app]


def outputs():
    return {'workloads.yaml': yaml.safe_dump_all(workloads(), sort_keys=False),
        'network.yaml': yaml.safe_dump_all(network(), sort_keys=False),
        'apisix-routes.yaml': yaml.safe_dump_all(routes(), sort_keys=False),
        'reference/apisix-routes-disabled.yaml': '# Disabled reference: never apply before service/base-path/TLS acceptance.\n' + yaml.safe_dump_all(routes(True), sort_keys=False),
        'reference/argocd.yaml': '# Activate only through apply.sh after OIDC and backend preflight.\n' + yaml.safe_dump_all(definitions(), sort_keys=False),
        'gitops/workloads.yaml': yaml.safe_dump_all(workloads() + routes(), sort_keys=False)}


def publish(check_only=False):
    for name, text in outputs().items():
        path = HERE / name
        if check_only:
            if not path.is_file() or path.read_text(encoding='utf-8') != text:
                raise ValueError('Generated source drift: ' + name)
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding='utf-8', newline='\n')
    print('PASS: vCloud console sources match renderer' if check_only else 'PASS: gated vCloud console rendered')


def stage():
    if not Path('/var/lib/vcloud-wsl/owner.json').is_file():
        raise ValueError('Owned WSL lab required')
    item = json.loads((HERE / 'artifacts.lock.json').read_text(encoding='utf-8'))['images']['ministack']
    image()
    subprocess.run(['ctr', '-n', 'k8s.io', 'images', 'pull', '--local', '--platform', 'linux/amd64', item['source']], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    listing = subprocess.check_output(['ctr', '-n', 'k8s.io', 'images', 'ls', 'name==' + item['source']], text=True)
    if listing.splitlines()[1].split()[2] != item['digest']:
        raise ValueError('Staged image differs')
    subprocess.run(['ctr', '-n', 'k8s.io', 'images', 'tag', '--force', item['source'], item['canonical']], check=True, stdout=subprocess.DEVNULL)
    print('PASS: MiniStack staged at locked digest')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true')
    parser.add_argument('--stage', action='store_true')
    parser.add_argument('--validate', action='store_true')
    parser.add_argument('--build', type=Path, default=ROOT / '.build/wsl-endpoints')
    parser.add_argument('--kubeconform')
    parser.add_argument('--schemas', type=Path)
    args = parser.parse_args()
    if args.stage:
        stage()
    elif args.validate:
        validate(args.build, args.kubeconform, args.schemas, [HERE / name for name in outputs()])
    else:
        publish(args.check)
