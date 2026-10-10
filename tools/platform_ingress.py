#!/usr/bin/env python3
"""Shared restricted console resources and pinned APISIX ingress prerequisites."""
from functools import lru_cache
import hashlib
import json
from pathlib import Path
import re
import tarfile
import yaml
from wsl_platform import ROOT, NS, resource, cnp, ports
from wsl_lab import security

LOCK_PATH = ROOT / 'deploy/common/apisix-ingress.lock.json'
CONTROL = 'vcloud-apisix-ingress'
ADMIN_SECRET = 'vcloud-wsl-apisix-admin'
CLASS = 'vcloud-local'
CHART = ROOT / 'module-2/vendor/apisix-2.18.0.tgz'


def lock():
    data = json.loads(LOCK_PATH.read_text())
    expected = json.loads((ROOT / 'module-2/artifacts.lock.json').read_text())['filesSHA256']['module-2/vendor/apisix-2.18.0.tgz']
    if hashlib.sha256(CHART.read_bytes()).hexdigest() != expected:
        raise ValueError('APISIX chart digest differs')
    for key, item in data['images'].items():
        if not re.fullmatch(r'sha256:[a-f0-9]{64}', item['digest']):
            raise ValueError('Invalid pinned image digest')
        if not item['source'].endswith('@' + item['digest']) or item['canonical'] != 'registry.vcloud.example.com/' + item['source']:
            raise ValueError('Canonical image differs from source digest')
    return data


def image(key):
    return lock()['images'][key]['canonical']


def config(name, data):
    obj = resource('ConfigMap', name, namespace=NS)
    obj['data'] = data
    return obj


def service(name, port, target=None):
    return resource('Service', name, {'selector': {'app.kubernetes.io/name': name},
        'ports': [{'name': 'http', 'port': port, 'targetPort': target or port}]}, NS)


def deploy(name, containers, volumes):
    labels = {'app.kubernetes.io/name': name}
    for container in containers:
        container['imagePullPolicy'] = 'IfNotPresent'
        container['securityContext'] = security() | {'runAsUser': 65532, 'runAsGroup': 65532}
    return resource('Deployment', name, {'replicas': 1, 'selector': {'matchLabels': labels},
        'template': {'metadata': {'labels': labels}, 'spec': {
            'automountServiceAccountToken': False,
            'securityContext': {'runAsNonRoot': True, 'runAsUser': 65532, 'runAsGroup': 65532,
                'fsGroup': 65532, 'seccompProfile': {'type': 'RuntimeDefault'}},
            'containers': containers, 'volumes': volumes}}}, NS, 'apps/v1')


def route(name, backend, port, host=None, uri='/*', priority=10, plugins=None):
    match = {'paths': [uri]}
    if host:
        match['hosts'] = [host]
    rule = {'name': name, 'priority': priority, 'match': match,
            'backends': [{'serviceName': backend, 'servicePort': port, 'resolveGranularity': 'service'}],
            'plugins': [{'name': 'prometheus', 'enable': True}] + (plugins or [])}
    return resource('ApisixRoute', name, {'ingressClassName': CLASS, 'http': [rule]}, NS, 'apisix.apache.org/v2')


def routes():
    gateway = resource('GatewayProxy', 'vcloud-apisix', {'provider': {'type': 'ControlPlane',
        'controlPlane': {'mode': 'apisix-standalone',
            'endpoints': ['https://apisix-admin.platform-services.svc.cluster.local:9180'],
            'tlsVerify': True, 'auth': {'type': 'AdminKey', 'adminKey': {'valueFrom': {
                'secretKeyRef': {'name': ADMIN_SECRET, 'key': 'admin-key'}}}}}}}, NS, 'apisix.apache.org/v1alpha1')
    # An ExternalName has no ClusterIP/endpoints in controller 2.2.0. Keep this
    # route beside the actual Kourier Service; IngressClass refers to the private
    # platform GatewayProxy explicitly by namespace.
    demo = route('demo-cpu-app', 'kourier-internal', 80, 'demo-cpu-app.workload-apps.example.com',
                 plugins=[{'name': 'proxy-rewrite', 'enable': True,
                           'config': {'host': 'demo-cpu-app.workload-apps.vcloud.example.com'}}])
    demo['metadata']['namespace']='workload-apps'
    return [gateway,
        demo,
        route('legacy-smoke', 'vcloud-lab-server', 8080, uri='/', priority=1)]


@lru_cache(maxsize=1)
def crds():
    with tarfile.open(CHART) as archive:
        raw = archive.extractfile('apisix/charts/apisix-ingress-controller/crds/apisixic-crds.yaml').read()
    return [obj for obj in yaml.safe_load_all(raw) if obj]


def controller():
    cfg = {'log_level': 'info', 'controller_name': 'apisix.apache.org/apisix-ingress-controller',
        'leader_election_id': CONTROL, 'leader_election': {'disable': False, 'leaseDuration': '15s',
            'renewDeadline': '10s', 'retryPeriod': '2s'},
        'metrics_addr': ':8080', 'secure_metrics': False, 'probe_addr': ':8081',
        'disable_gateway_api': True, 'exec_adc_timeout': '30s',
        'provider': {'type': 'apisix-standalone', 'sync_period': '5s', 'init_sync_delay': '5s'}}
    mount = [{'name': 'socket', 'mountPath': '/sockets'}, {'name': 'tmp', 'mountPath': '/tmp'},
             {'name': 'trust', 'mountPath': '/trust', 'readOnly': True}]
    manager = {'name': 'manager', 'image': image('controller'),
        'env': [{'name': 'POD_NAMESPACE', 'valueFrom': {'fieldRef': {'fieldPath': 'metadata.namespace'}}},
                {'name': 'POD_NAME', 'valueFrom': {'fieldRef': {'fieldPath': 'metadata.name'}}},
                {'name': 'ADC_SERVER_URL', 'value': 'unix:/sockets/adc.sock'}],
        'volumeMounts': mount + [{'name': 'config', 'mountPath': '/app/conf/config.yaml', 'subPath': 'config.yaml'}],
        'resources': {'requests': {'cpu': '50m', 'memory': '64Mi'}, 'limits': {'cpu': '500m', 'memory': '256Mi'}},
        'livenessProbe': {'httpGet': {'path': '/healthz', 'port': 8081}, 'initialDelaySeconds': 20},
        'readinessProbe': {'httpGet': {'path': '/readyz', 'port': 8081}}}
    adc = {'name': 'adc-server', 'image': image('adc'),
        'args': ['server', '--listen', 'unix:/sockets/adc.sock', '--listen-status', '3001'],
        'env': [{'name': 'ADC_RUNNING_MODE', 'value': 'ingress'},
                {'name': 'ADC_EXPERIMENTAL_FEATURE_FLAGS', 'value': 'remote-state-file,parallel-backend-request'},
                {'name': 'ADC_INGRESS_LOG_LEVEL', 'value': 'warn'},
                {'name': 'NODE_EXTRA_CA_CERTS', 'value': '/trust/ca.crt'}],
        'volumeMounts': mount,
        'resources': {'requests': {'cpu': '50m', 'memory': '128Mi'}, 'limits': {'cpu': '500m', 'memory': '512Mi'}},
        'livenessProbe': {'httpGet': {'path': '/healthz/ready', 'port': 3001}, 'initialDelaySeconds': 20},
        'readinessProbe': {'httpGet': {'path': '/healthz/ready', 'port': 3001}}}
    dep = deploy(CONTROL, [manager, adc], [{'name': 'socket', 'emptyDir': {'medium': 'Memory', 'sizeLimit': '16Mi'}},
        {'name': 'tmp', 'emptyDir': {'medium': 'Memory', 'sizeLimit': '64Mi'}},
        {'name': 'config', 'configMap': {'name': CONTROL}},
        {'name': 'trust', 'secret': {'secretName': ADMIN_SECRET, 'items': [{'key': 'ca.crt', 'path': 'ca.crt'}], 'defaultMode': 0o440}}])
    pod = dep['spec']['template']['spec']
    pod['automountServiceAccountToken'] = True
    pod['serviceAccountName'] = CONTROL
    for container in pod['containers']:
        container['securityContext']['readOnlyRootFilesystem'] = False
    # Official 2.2.0 informers are cluster-wide. Secrets are read-only, required
    # for GatewayProxy admin-key and TLS references; production least-privilege
    # Secret-cache scoping remains an explicit open gate, never hidden here.
    rules = [dict(apiGroups=[''], resources=['configmaps', 'namespaces', 'pods', 'secrets', 'services', 'endpoints'], verbs=['get', 'list', 'watch']),
        dict(apiGroups=['apisix.apache.org'], resources=[o['spec']['names']['plural'] for o in crds()], verbs=['get', 'list', 'watch']),
        dict(apiGroups=['apisix.apache.org'], resources=[o['spec']['names']['plural'] + '/status' for o in crds() if o['spec']['names']['kind'] != 'GatewayProxy'], verbs=['get', 'update', 'patch']),
        dict(apiGroups=['discovery.k8s.io'], resources=['endpointslices'], verbs=['get', 'list', 'watch']),
        dict(apiGroups=['networking.k8s.io'], resources=['ingresses', 'ingressclasses'], verbs=['get', 'list', 'watch']),
        dict(apiGroups=['networking.k8s.io'], resources=['ingresses/status'], verbs=['get', 'update', 'patch'])]
    cluster_role = resource('ClusterRole', CONTROL, api='rbac.authorization.k8s.io/v1'); cluster_role['rules'] = rules
    binding = resource('ClusterRoleBinding', CONTROL, api='rbac.authorization.k8s.io/v1')
    binding.update(roleRef={'apiGroup': 'rbac.authorization.k8s.io', 'kind': 'ClusterRole', 'name': CONTROL},
                   subjects=[{'kind': 'ServiceAccount', 'name': CONTROL, 'namespace': NS}])
    role = resource('Role', CONTROL, namespace=NS, api='rbac.authorization.k8s.io/v1')
    role['rules'] = [dict(apiGroups=['coordination.k8s.io'], resources=['leases'], verbs=['get', 'list', 'watch', 'create', 'update', 'patch']),
                     dict(apiGroups=[''], resources=['events'], verbs=['create', 'patch'])]
    role_binding = resource('RoleBinding', CONTROL, namespace=NS, api='rbac.authorization.k8s.io/v1')
    role_binding.update(roleRef={'apiGroup': 'rbac.authorization.k8s.io', 'kind': 'Role', 'name': CONTROL}, subjects=binding['subjects'])
    ingress = resource('IngressClass', CLASS, {'controller': cfg['controller_name'], 'parameters': {
        'apiGroup': 'apisix.apache.org', 'kind': 'GatewayProxy', 'name': 'vcloud-apisix', 'scope': 'Namespace', 'namespace': NS}}, api='networking.k8s.io/v1')
    return [config(CONTROL, {'config.yaml': yaml.safe_dump(cfg)}), resource('ServiceAccount', CONTROL, namespace=NS),
            cluster_role, binding, role, role_binding, ingress, dep]


def network(router):
    endpoint = lambda name: {'matchLabels': {'k8s:io.kubernetes.pod.namespace': NS, 'k8s:app.kubernetes.io/name': name}}
    policies = [cnp('vcloud-wsl-apisix-aws', {'k8s:app.kubernetes.io/name': 'apisix'},
            [{'fromEndpoints': [endpoint(CONTROL)], 'toPorts': ports(9180)}],
            [{'toEndpoints': [endpoint('ministack')], 'toPorts': ports(4566)}]),
        cnp('vcloud-wsl-apisix-ingress', {'k8s:app.kubernetes.io/name': CONTROL},
            [{'fromEntities': ['host', 'remote-node', 'health', 'world'], 'toPorts': ports(8081, 3001)},
             {'fromCIDR': [router + '/32'], 'toPorts': ports(8081, 3001)}],
            [{'toEntities': ['kube-apiserver'], 'toPorts': ports(443, 16443)},
             {'toEndpoints': [endpoint('apisix')], 'toPorts': ports(9180)}])]
    return policies
