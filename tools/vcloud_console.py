#!/usr/bin/env python3
"""Render the authenticated single-origin WSL portal and its bounded bootstrap."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import yaml
from wsl_platform import ROOT, NS, resource, cnp, ports
from wsl_localstack import deploy, config, service, CLASS
from wsl_endpoints import check, validate

HERE = ROOT / 'deploy/console'


def profile():
    p = json.loads((HERE / 'profile.json').read_text())
    if p['name'] != 'vcloud-wsl-local' or p['origin'] != 'http://localhost:18080' or p['hosts'] != ['localhost']:
        raise ValueError('Only the loopback WSL profile is supported; HTTPS needs a separate reviewed profile')
    if p['issuer'] != 'https://localhost:18443/realms/vcloud' or p['client'] != 'vcloud-console': raise ValueError('Unexpected issuer/client')
    return p


def image():
    lock = json.loads((ROOT / 'console/image.lock.json').read_text())
    if not re.fullmatch(r'sha256:[a-f0-9]{64}', lock['digest']) or lock['canonical'] != 'registry.vcloud.example.com/vcloud/vcloud-console@' + lock['digest']:
        raise ValueError('Immutable portal image required')
    for path, expected in lock['filesSHA256'].items():
        if not (ROOT / path).resolve().is_relative_to(ROOT.resolve()): raise ValueError('Invalid build input')
        if hashlib.sha256((ROOT / path).read_bytes()).hexdigest() != expected: raise ValueError('Image source drift: ' + path)
    return lock['canonical']


def workloads():
    probe = {'exec': {'command': ['python', '-c', "import urllib.request; urllib.request.urlopen('http://127.0.0.1:3000/healthz',timeout=2)"]}, 'timeoutSeconds': 3}
    c = {'name': 'console', 'image': image(), 'ports': [{'name': 'http', 'containerPort': 3000}],
        'resources': {'requests': {'cpu': '50m', 'memory': '64Mi'}, 'limits': {'cpu': '500m', 'memory': '256Mi'}},
        'volumeMounts': [{'name': 'api-identity', 'mountPath': '/var/run/secrets/vcloud', 'readOnly': True},
                        {'name': 'oidc-trust', 'mountPath': '/oidc-trust', 'readOnly': True}],
        'readinessProbe': probe, 'livenessProbe': probe}
    volume = {'name': 'api-identity', 'projected': {'defaultMode': 0o440, 'sources': [
        {'serviceAccountToken': {'path': 'token', 'expirationSeconds': 3600}},
        {'configMap': {'name': 'kube-root-ca.crt', 'items': [{'key': 'ca.crt', 'path': 'ca.crt'}]}}]}}
    trust = {'name': 'oidc-trust', 'secret': {'secretName': 'vcloud-wsl-keycloak-tls',
        'items': [{'key': 'tls.crt', 'path': 'tls.crt'}], 'defaultMode': 0o440}}
    d = deploy('vcloud-console', [c], [volume, trust])
    d['spec']['template']['spec']['serviceAccountName'] = 'vcloud-console'
    d['metadata']['labels'] = {'app.kubernetes.io/part-of': 'vcloud-console'}
    check([d])
    return [d, service('vcloud-console', 3000)]


def plugins(api=False, proxy_prefix=None):
    p = profile()
    scrub = "return function(conf, ctx) for _,name in ipairs({'X-ID-Token','X-Access-Token','X-Userinfo','X-Refresh-Token','X-Raw-ID-Token'}) do ngx.req.clear_header(name) end end"
    role_schema = {'type': 'object', 'required': ['id_token'], 'properties': {'id_token': {'type': 'object',
        'required': ['resource_access'], 'properties': {'resource_access': {'type': 'object', 'required': [p['client']],
        'properties': {p['client']: {'type': 'object', 'required': ['roles'], 'properties': {'roles': {'type': 'array',
        'contains': {'enum': p['roles']}}}}}}}}}}
    # A missing/expired browser session must not produce an opaque OAuth 500.
    # Keep this before OIDC; session-bearing callbacks retain OIDC CSRF checks.
    guard = (HERE / 'callback-guard.lua').read_text()
    result = [
        {'name': 'serverless-pre-function', 'enable': True, 'config': {'phase': 'rewrite', '_meta': {'priority': 10000}, 'functions': [scrub, guard]}},
        {'name': 'openid-connect', 'enable': True, 'secretRef': p['secret'], 'config': {
            'client_id': p['client'], 'discovery': p['discovery'], 'bearer_only': False, 'unauth_action': 'deny' if api else 'auth',
            'ssl_verify': True, 'use_pkce': True, 'scope': 'openid', 'timeout': 5,
            'redirect_uri': p['origin'] + '/console/callback', 'logout_path': '/console/logout',
            'session': {'cookie_name': 'vcloud_portal', 'cookie_path': '/console', 'cookie_secure': False,
                'cookie_http_only': True, 'cookie_same_site': 'Lax', 'idling_timeout': 900, 'absolute_timeout': 3600},
            'set_id_token_header': False, 'set_access_token_header': True, 'set_refresh_token_header': False, 'set_userinfo_header': False,
            'accept_none_alg': False, 'accept_unsupported_alg': False, 'token_signing_alg_values_expected': 'RS256',
            'claim_validator': {'issuer': {'valid_issuers': [p['issuer']]}, 'audience': {'required': True, 'match_with_client_id': True}},
            'claim_schema': role_schema}},
        {'name': 'proxy-rewrite', 'enable': True, 'config': {'headers': {'set': {'X-Forwarded-Host': 'localhost:18080', 'X-Forwarded-Proto': 'http'},
            'remove': ['Authorization', 'Cookie', 'X-ID-Token', 'X-Userinfo', 'X-Refresh-Token', 'X-Raw-ID-Token']}}},
        {'name': 'response-rewrite', 'enable': True, 'config': {'headers': {'set': {'X-Frame-Options': 'SAMEORIGIN',
            'X-Content-Type-Options': 'nosniff', 'Cache-Control': 'no-store', 'Referrer-Policy': 'no-referrer'}}}},
        {'name': 'prometheus', 'enable': True}]
    if proxy_prefix:
        result[2]['config']['regex_uri'] = ['^/console/proxy/' + proxy_prefix + '(?:/(.*))?$', '/$1']
        result[2]['config']['headers']['set']['X-Forwarded-Prefix'] = '/console/proxy/' + proxy_prefix
        # These legacy views use their own stricter CSP; preserve it verbatim.
    return result


def routes():
    p = profile(); result = []
    for name, paths, backend, port, api, prefix in [
        ('shell', ['/console', '/console/*'], 'vcloud-console', 3000, False, None),
        ('api', ['/console/api/*'], 'vcloud-console', 3000, True, None),
        ('storage-view', ['/console/proxy/storage', '/console/proxy/storage/*'], 'storage-ui', 9001, False, 'storage'),
        ('dynamodb-view', ['/console/proxy/dynamodb', '/console/proxy/dynamodb/*'], 'dynamodb-admin', 8081, False, 'dynamodb')]:
        rule = {'name': name, 'priority': 150 if name != 'shell' else 100, 'match': {'hosts': p['hosts'], 'paths': paths},
            'backends': [{'serviceName': backend, 'servicePort': port, 'resolveGranularity': 'service'}], 'websocket': False,
            'plugins': plugins(api, prefix)}
        result.append(resource('ApisixRoute', 'vcloud-portal-' + name, {'ingressClassName': CLASS, 'http': [rule]}, NS, 'apisix.apache.org/v2'))
    return result


def bootstrap():
    sa = resource('ServiceAccount', 'vcloud-console', namespace=NS)
    sa['automountServiceAccountToken'] = False
    role = resource('Role', 'vcloud-console-reader', namespace=NS, api='rbac.authorization.k8s.io/v1')
    role['rules'] = [{'apiGroups': [g], 'resources': rs, 'verbs': ['get', 'list']} for g, rs in
        [('', ['pods']), ('apps', ['deployments']), ('argoproj.io', ['applications'])]]
    binding = resource('RoleBinding', 'vcloud-console-reader', namespace=NS, api='rbac.authorization.k8s.io/v1')
    binding.update(roleRef={'apiGroup': 'rbac.authorization.k8s.io', 'kind': 'Role', 'name': role['metadata']['name']},
        subjects=[{'kind': 'ServiceAccount', 'name': 'vcloud-console', 'namespace': NS}])
    peer = lambda n: {'matchLabels': {'k8s:io.kubernetes.pod.namespace': NS, 'k8s:app.kubernetes.io/name': n}}
    emulators = [peer('ministack'), peer('localstack-aws-console')]
    result = [sa, role, binding,
        cnp('vcloud-portal', {'k8s:app.kubernetes.io/name': 'vcloud-console'},
            [{'fromEndpoints': [peer('apisix')], 'toPorts': ports(3000)}],
            [{'toEndpoints': emulators, 'toPorts': ports(4566)}, {'toEndpoints': [peer('keycloak')], 'toPorts': ports(8443)}, {'toEntities': ['kube-apiserver'],
                'toPorts': [{'ports': [{'port': str(port), 'protocol': 'TCP'} for port in (443, 16443)]}]}]),
        cnp('vcloud-portal-emulators', {'k8s:app.kubernetes.io/name': 'ministack'}, [{'fromEndpoints': [peer('vcloud-console')], 'toPorts': ports(4566)}], []),
        cnp('vcloud-portal-localstack', {'k8s:app.kubernetes.io/name': 'localstack-aws-console'}, [{'fromEndpoints': [peer('vcloud-console')], 'toPorts': ports(4566)}], []),
        cnp('vcloud-portal-gateway', {'k8s:app.kubernetes.io/name': 'apisix'}, [],
            [{'toEndpoints': [peer('vcloud-console')], 'toPorts': ports(3000)}, {'toEndpoints': [peer('keycloak')], 'toPorts': ports(8443)}]),
        cnp('vcloud-portal-keycloak', {'k8s:app.kubernetes.io/name': 'keycloak'},
            [{'fromEndpoints': [peer('apisix'), peer('vcloud-console')], 'toPorts': ports(8443)}], [])]
    # Name-resolution baseline is separately owned by the platform; no world egress.
    return result


def outputs():
    objects = workloads()
    return {'deployment.yaml': yaml.safe_dump(objects[0], sort_keys=False), 'service.yaml': yaml.safe_dump(objects[1], sort_keys=False),
        'apisix-routes.yaml': yaml.safe_dump_all(routes(), sort_keys=False), 'bootstrap.yaml': yaml.safe_dump_all(bootstrap(), sort_keys=False),
        'gitops/workloads.yaml': yaml.safe_dump_all(objects + routes(), sort_keys=False)}


def publish(check_only=False):
    for name, raw in outputs().items():
        path = HERE / name
        if check_only:
            if not path.is_file() or path.read_text() != raw: raise ValueError('Portal render drift: ' + name)
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(raw, newline='\n')
    print('PASS: unified portal render' + (' verified' if check_only else ' written'))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true'); parser.add_argument('--validate', action='store_true')
    parser.add_argument('--build', type=Path, default=ROOT / '.build/console/schema')
    parser.add_argument('--kubeconform'); parser.add_argument('--schemas', type=Path)
    args = parser.parse_args()
    if args.validate: validate(args.build, args.kubeconform, args.schemas, [HERE / n for n in outputs()])
    else: publish(args.check)
