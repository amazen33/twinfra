#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""WO-07: pinned Perses resources, Git-provisioned dashboards and read-only SSO."""
import argparse
import copy
from datetime import date
import gzip
import hashlib
import json
from pathlib import Path
import yaml

from platform_resources import ROOT, resource, security

HERE = ROOT / 'deploy/observability/perses'
PREFIX = '/console/metrics'
PROJECT = 'twinfra'

DELIVERY = [
    ('Pipeline runs', 'sum by (status) (increase(tekton_pipelines_controller_pipelinerun_duration_seconds_count{namespace="workload-apps",pipeline="vcloud-ci"}[1h]))'),
    ('Pipeline duration p95', 'histogram_quantile(0.95, sum by (le) (rate(tekton_pipelines_controller_pipelinerun_duration_seconds_bucket{namespace="workload-apps",pipeline="vcloud-ci"}[15m])))'),
    ('Argo CD sync and health', 'argocd_app_info{name="vcloud-delivery"}'),
    ('Delivery alerts', 'ALERTS{alertname=~"VCloud.*",alertstate="firing"}'),
]
HEALTH = [('Scrape targets', 'up'), ('PostgreSQL instances', 'cnpg_collector_up'),
          ('Platform alerts', 'ALERTS{alertstate="firing"}')]


def lock():
    data = json.loads((HERE / 'artifacts.lock.json').read_text())
    for item in data['images'].values():
        if (date.today() - date.fromisoformat(item['publishedOn'])).days < 14:
            raise ValueError('Perses release has not aged 14 days')
        if item['canonical'] != 'registry.twinfra.example.com/' + item['source'] or not item['source'].endswith('@' + item['digest']):
            raise ValueError('Perses canonical digest differs')
    return data


def crds():
    result = []
    for name, item in lock()['files'].items():
        raw = (HERE / 'vendor' / (name + '.gz')).read_bytes()
        if hashlib.sha256(raw).hexdigest() != item['gzipSHA256']:
            raise ValueError('Perses CRD archive differs')
        raw = gzip.decompress(raw)
        if hashlib.sha256(raw).hexdigest() != item['sourceSHA256']:
            raise ValueError('Perses CRD source differs')
        result += [o for o in yaml.safe_load_all(raw) if o]
    return result


def verify_sbom(bundle, expected_digest):
    def sha(raw):return 'sha256:'+hashlib.sha256(raw.encode()).hexdigest()
    if sha(bundle['index'])!=expected_digest:raise ValueError('SBOM index digest differs')
    index=json.loads(bundle['index'])
    if set(bundle['platforms'])!={'amd64','arm64'}:raise ValueError('SBOM platform missing')
    for arch,evidence in bundle['platforms'].items():
        platform=next(x for x in index['manifests'] if x['platform']['architecture']==arch)
        attestation=next(x for x in index['manifests'] if x.get('annotations',{}).get('vnd.docker.reference.digest')==platform['digest'])
        if sha(evidence['attestation'])!=attestation['digest']:raise ValueError('SBOM attestation digest differs')
        statement_layer=next(x for x in json.loads(evidence['attestation'])['layers'] if
            x.get('annotations',{}).get('in-toto.io/predicate-type')=='https://spdx.dev/Document')
        if sha(evidence['statement'])!=statement_layer['digest']:raise ValueError('SBOM statement digest differs')
        statement=json.loads(evidence['statement'])
        if not any(x['digest'].get('sha256')==platform['digest'].split(':')[1] for x in statement['subject']):
            raise ValueError('SBOM subject differs')
        if statement['predicateType']!='https://spdx.dev/Document' or not statement['predicate'].get('packages'):
            raise ValueError('Missing SPDX package inventory')


def sboms():
    for item in lock()['images'].values():
        evidence=item['imageSBOM'];raw=(ROOT/evidence['path']).read_bytes()
        if hashlib.sha256(raw).hexdigest()!=evidence['sha256']:raise ValueError('SBOM evidence archive differs')
        verify_sbom(json.loads(gzip.decompress(raw)),item['digest'])


def dashboard(name, title, queries):
    panels, items = {}, []
    for index, (label, query) in enumerate(queries):
        key = 'panel' + str(index + 1)
        panels[key] = {'kind': 'Panel', 'spec': {'display': {'name': label},
            'plugin': {'kind': 'TimeSeriesChart', 'spec': {}},
            'queries': [{'kind': 'TimeSeriesQuery', 'spec': {'plugin': {
                'kind': 'PrometheusTimeSeriesQuery', 'spec': {'query': query,
                    'datasource': {'kind': 'Datasource', 'name': 'prometheus'}}}}}]}}
        items.append({'x': index % 2 * 12, 'y': index // 2 * 8, 'width': 12, 'height': 8,
                      'content': {'$ref': '#/spec/panels/' + key}})
    return {'kind': 'Dashboard', 'metadata': {'name': name, 'project': PROJECT},
            'spec': {'display': {'name': title}, 'duration': '1h', 'refreshInterval': '30s',
                     'panels': panels, 'layouts': [{'kind': 'Grid', 'spec': {'items': items}}]}}


def provisioned(prometheus_url):
    return [{'kind': 'Project', 'metadata': {'name': PROJECT}, 'spec': {'display': {'name': 'Twinfra'}}},
        {'kind': 'Datasource', 'metadata': {'name': 'prometheus', 'project': PROJECT}, 'spec': {
            'display': {'name': 'Twinfra Prometheus'}, 'default': True,
            'plugin': {'kind': 'PrometheusDatasource', 'spec': {
                'proxy': {'kind': 'HTTPProxy', 'spec': {'url': prometheus_url}}}}}},
        dashboard('twinfra-delivery', 'Twinfra delivery', DELIVERY),
        dashboard('twinfra-health', 'Twinfra environment health', HEALTH)]


def objects(namespace, gateway='twinfra-gateway', prometheus='twinfra-prometheus', legacy=False):
    """Operator manages the Perses instance; provisioned files need no API writer."""
    def obj(kind, name, spec=None, api='v1', ns=namespace):
        return resource(kind, name, spec, ns, api, {'app.kubernetes.io/part-of': 'twinfra',
            'twinfra.io/environment': 'dev', 'twinfra.io/region': 'cairo-1',
            'twinfra.io/component': 'perses'})
    def peer(name):
        return {'matchLabels': {'k8s:io.kubernetes.pod.namespace': namespace, 'k8s:app.kubernetes.io/name': name}}
    def ports(*values):
        return [{'ports': [{'port': str(value), 'protocol': 'TCP'} for value in values]}]
    def image(name):
        value = lock()['images'][name]['canonical']
        return value.replace('registry.twinfra.example.com/', 'registry.vcloud.example.com/') if legacy else value

    sa = obj('ServiceAccount', 'twinfra-perses-operator'); sa['automountServiceAccountToken'] = True
    server_sa = obj('ServiceAccount', 'twinfra-perses'); server_sa['automountServiceAccountToken'] = False
    # v0.5.0 uses cluster-wide informers (no namespace flag). Read-only informer
    # access is explicit; mutation permissions are confined to this namespace.
    reader = obj('ClusterRole', 'twinfra-perses-reader', api='rbac.authorization.k8s.io/v1', ns=None)
    reader['rules'] = [
        {'apiGroups': ['perses.dev'], 'resources': ['perses', 'persesdashboards', 'persesdatasources', 'persesglobaldatasources'], 'verbs': ['get', 'list', 'watch']},
        {'apiGroups': ['apps'], 'resources': ['deployments', 'statefulsets'], 'verbs': ['get', 'list', 'watch']},
        {'apiGroups': [''], 'resources': ['configmaps', 'services', 'secrets', 'pods', 'namespaces'], 'verbs': ['get', 'list', 'watch']}]
    writer = obj('Role', 'twinfra-perses-operator', api='rbac.authorization.k8s.io/v1')
    writer['rules'] = [
        {'apiGroups': ['apps'], 'resources': ['deployments', 'statefulsets'], 'verbs': ['get', 'list', 'watch', 'create', 'update', 'patch', 'delete']},
        {'apiGroups': [''], 'resources': ['configmaps', 'services', 'events'], 'verbs': ['get', 'list', 'watch', 'create', 'update', 'patch', 'delete']},
        {'apiGroups': ['perses.dev'], 'resources': ['perses/status', 'perses/finalizers', 'persesdashboards/status', 'persesdashboards/finalizers',
            'persesdatasources/status', 'persesdatasources/finalizers', 'persesglobaldatasources/status', 'persesglobaldatasources/finalizers'], 'verbs': ['get', 'update', 'patch']}]
    writer['rules'].append({'apiGroups':['perses.dev'],'resources':['perses','persesdashboards','persesdatasources','persesglobaldatasources'],
                            'verbs':['get','update','patch']})
    bindings = []
    for role, kind in [(reader, 'ClusterRoleBinding'), (writer, 'RoleBinding')]:
        b = obj(kind, role['metadata']['name'], api='rbac.authorization.k8s.io/v1', ns=None if kind == 'ClusterRoleBinding' else namespace)
        b.update(roleRef={'apiGroup': 'rbac.authorization.k8s.io', 'kind': role['kind'], 'name': role['metadata']['name']},
            subjects=[{'kind': 'ServiceAccount', 'name': sa['metadata']['name'], 'namespace': namespace}]); bindings.append(b)
    operator = obj('Deployment', 'twinfra-perses-operator', {'replicas': 1,
        'selector': {'matchLabels': {'app.kubernetes.io/name': 'twinfra-perses-operator'}},
        'template': {'metadata': {'labels': {'app.kubernetes.io/name': 'twinfra-perses-operator'}}, 'spec': {
            'serviceAccountName': sa['metadata']['name'], 'automountServiceAccountToken': True,
            'securityContext': {'runAsNonRoot': True, 'runAsUser': 65532, 'runAsGroup': 65532, 'seccompProfile': {'type': 'RuntimeDefault'}},
            'containers': [{'name': 'operator', 'image': image('operator'), 'imagePullPolicy': 'IfNotPresent',
                'args': ['--perses-default-base-image=' + image('perses'), '--metrics-bind-address=0', '--health-probe-bind-address=:8081'],
                'env': [{'name': 'ENABLE_WEBHOOKS', 'value': 'false'}], 'securityContext': security(),
                'resources': {'requests': {'cpu': '50m', 'memory': '64Mi'}, 'limits': {'cpu': '500m', 'memory': '256Mi'}},
                'readinessProbe': {'httpGet': {'path': '/readyz', 'port': 8081}},
                'livenessProbe': {'httpGet': {'path': '/healthz', 'port': 8081}}}]}}}, 'apps/v1')
    cm = obj('ConfigMap', 'twinfra-perses-resources')
    cm['data'] = {str(i) + '-' + item['kind'].lower() + '.json': json.dumps(item, indent=2) + '\n'
                  for i, item in enumerate(provisioned('http://' + prometheus + '.' + namespace + '.svc.cluster.local:9090'))}
    cm['metadata']['annotations'] = {'argocd.argoproj.io/sync-wave': '5'}
    # APISIX authenticates every browser/API route using the console role schema.
    # No direct access/port-forward is published. Backend API writes are disabled;
    # immutable dashboards/datasource are injected from mounted Git ConfigMaps.
    instance = obj('Perses', 'twinfra-perses', {'replicas': 1, 'image': image('perses'),
        'metadata': {'labels': {'app.kubernetes.io/name': 'twinfra-perses'},
                     'annotations': {'twinfra.io/provisioning-hash': hashlib.sha256(json.dumps(cm['data'], sort_keys=True).encode()).hexdigest()}},
        'serviceAccountName': 'twinfra-perses', 'containerPort': 8080,
        'storage': {'emptyDir': {'sizeLimit': '256Mi'}},
        'podSecurityContext': {'runAsNonRoot': True, 'runAsUser': 65532, 'runAsGroup': 65532, 'fsGroup': 65532, 'seccompProfile': {'type': 'RuntimeDefault'}},
        'resources': {'requests': {'cpu': '50m', 'memory': '128Mi'}, 'limits': {'cpu': '500m', 'memory': '512Mi'}},
        'config': {'api_prefix': PREFIX, 'database': {'file': {'folder': '/perses', 'extension': 'json'}},
            'security': {'enable_auth': False, 'readonly': True, 'cookie':{'secure':True},'encryption_key_file': '/identity/encryption-key'},
            'provisioning': {'folders': ['/resources']}, 'ephemeral_dashboard': {'enable': False,'cleanup_interval':'1h'}},
        'volumes': [{'name': 'resources', 'configMap': {'name': cm['metadata']['name']}},
                    {'name': 'identity', 'secret': {'secretName': 'twinfra-perses-key', 'defaultMode': 0o440}}],
        'volumeMounts': [{'name': 'resources', 'mountPath': '/resources', 'readOnly': True},
                         {'name': 'identity', 'mountPath': '/identity', 'readOnly': True}],
        'livenessProbe': {'httpGet': {'path': PREFIX + '/api/v1/health', 'port': 8080}},
        'readinessProbe': {'httpGet': {'path': PREFIX + '/api/v1/health', 'port': 8080}}}, 'perses.dev/v1alpha2')
    instance['metadata']['annotations'] = {'argocd.argoproj.io/sync-wave': '10'}
    dns = {'toEndpoints': [{'matchLabels': {'k8s:io.kubernetes.pod.namespace': 'kube-system', 'k8s:k8s-app': 'kube-dns'}}],
           'toPorts': [{'ports': [{'port': '53', 'protocol': 'ANY'}], 'rules': {'dns': [{'matchPattern': '*'}]}}]}
    prom_peer = {'matchLabels': {'k8s:io.kubernetes.pod.namespace': namespace, 'k8s:prometheus': 'vcloud'}} if legacy else peer(prometheus)
    policies = [obj('NetworkPolicy', 'twinfra-perses-deny', {'podSelector': {'matchExpressions': [
        {'key': 'app.kubernetes.io/name', 'operator': 'In', 'values': ['twinfra-perses', 'twinfra-perses-operator']}]},
        'policyTypes': ['Ingress', 'Egress'], 'ingress': [], 'egress': []}, 'networking.k8s.io/v1'),
        obj('CiliumNetworkPolicy', 'twinfra-perses-network', {'endpointSelector': peer('twinfra-perses'),
            'ingress': [{'fromEndpoints': [peer(gateway)], 'toPorts': ports(8080)},
                {'fromEntities': ['host', 'remote-node', 'health'], 'toPorts': [{'ports': [{'port': '8080', 'protocol': 'TCP'}],
                    'rules': {'http': [{'method': 'GET', 'path': PREFIX + '/api/v1/health'}]}}]}],
            'egress': [dns, {'toEndpoints': [prom_peer], 'toPorts': ports(9090)}]}, 'cilium.io/v2'),
        obj('CiliumNetworkPolicy', 'twinfra-perses-operator-network', {'endpointSelector': peer('twinfra-perses-operator'),
            'ingress': [{'fromEntities': ['host', 'remote-node', 'health'], 'toPorts': ports(8081)}],
            'egress': [dns, {'toEntities': ['kube-apiserver'], 'toPorts': ports(443, 6443, 16443)}]}, 'cilium.io/v2'),
        obj('CiliumNetworkPolicy', 'twinfra-perses-gateway-network', {'endpointSelector': peer(gateway),
            'egress': [{'toEndpoints': [peer('twinfra-perses')], 'toPorts': ports(8080)}]}, 'cilium.io/v2'),
        obj('CiliumNetworkPolicy', 'twinfra-perses-prometheus-network', {'endpointSelector': prom_peer,
            'ingress': [{'fromEndpoints': [peer('twinfra-perses')], 'toPorts': ports(9090)}]}, 'cilium.io/v2')]
    output = [sa, server_sa, reader, writer, *bindings, operator, cm, instance, *policies]
    for value in output:
        if value['kind'] != 'Perses': value['metadata'].setdefault('annotations', {})['argocd.argoproj.io/sync-wave'] = '5'
    return output


def gateway_route(template, namespace):
    """Reuse the existing trusted OIDC role schema/session, not caller headers."""
    result = copy.deepcopy(template)
    result.update(id=70, name='twinfra-perses', priority=200, uris=[PREFIX, PREFIX + '/*'])
    result['upstream'] = {'type': 'roundrobin', 'nodes': {'twinfra-perses.' + namespace + '.svc.cluster.local:8080': 1}}
    # Keep backend prefix: Perses embeds api_prefix in its own asset/API URLs.
    result['plugins']['proxy-rewrite']['headers']['remove'] = ['Authorization', 'Cookie', 'X-ID-Token', 'X-Access-Token', 'X-Userinfo', 'X-Refresh-Token', 'X-Raw-ID-Token']
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    for filename, raw in {'dashboards.json': json.dumps(provisioned('http://twinfra-prometheus.twinfra-platform-services.svc.cluster.local:9090'), indent=2) + '\n'}.items():
        path = HERE / filename
        if args.check:
            if not path.is_file() or path.read_text() != raw: raise ValueError('Perses dashboard render drift')
        else: path.write_text(raw, encoding='utf-8', newline='\n')
    crds(); sboms(); print('PASS: pinned Perses CRDs, upstream SPDX attestations and dashboard generation')


if __name__ == '__main__': main()
