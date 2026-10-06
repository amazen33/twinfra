#!/usr/bin/env python3
"""Generate the disabled Module 5b reference. --check detects manifest drift."""
import argparse
import copy
import json
from pathlib import Path
import sys
import yaml

ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / 'module-5b'
NS = 'hpc-compute'
QUEUE = 'spinifex-hpc-burst'
TARGET = {'vcloud.io/offload-target': 'spinifex-hpc'}
IMAGE = 'registry.vcloud.example.com/vcloud/agent-bridge:1.0.0'
WORKER = 'registry.vcloud.example.com/vcloud/hpc-reference-worker:1.0.0'
SECURITY = dict(runAsNonRoot=True, runAsUser=65532, runAsGroup=65532, allowPrivilegeEscalation=False,
                readOnlyRootFilesystem=True, capabilities={'drop': ['ALL']}, seccompProfile={'type': 'RuntimeDefault'})


def resource(kind, name, spec=None, api='v1', namespace=NS, **extra):
    obj = {'apiVersion': api, 'kind': kind, 'metadata': {'name': name,
           'labels': {'app.kubernetes.io/part-of': 'vcloud', **TARGET}}}
    if namespace: obj['metadata']['namespace'] = namespace
    if spec is not None: obj['spec'] = spec
    obj.update(extra)
    return obj


def feature_env(profile):
    return [{'name': name, 'value': value} for name, value in {
        'SPINIFEX_OFFLOAD_ENABLED': 'false', 'SPINIFEX_ENDPOINT_URL': profile['endpoint_url'],
        'SPINIFEX_GPU_PROFILE': profile['default_profile'], 'SPINIFEX_MAX_BURST_NODES': '4'}.items()]


def workloads(profile):
    config = resource('ConfigMap', 'vcloud-hpc-reference', data={'reference-profile.json': json.dumps(profile, indent=2) + '\n'})
    items = [config, resource('PersistentVolumeClaim', 'vcloud-hpc-state',
                             {'accessModes': ['ReadWriteOnce'], 'storageClassName': 'vcloud-hpc-csi',
                              'resources': {'requests': {'storage': '1Gi'}}})]
    for name, mode in [('vcloud-deepseek-agent', 'agent'), ('vcloud-spinifex-bridge', 'capacity')]:
        items.append(resource('ServiceAccount', name, automountServiceAccountToken=False,
                              imagePullSecrets=[{'name': 'vcloud-registry-pull'}]))
        labels = {'app.kubernetes.io/name': name, 'app.kubernetes.io/part-of': 'vcloud', **TARGET}
        volumes = [{'name': 'config', 'configMap': {'name': 'vcloud-hpc-reference'}},
                   {'name': 'tls', 'secret': {'secretName': name + '-mtls', 'defaultMode': 288}},
                   {'name': 'trust', 'configMap': {'name': 'vcloud-hpc-public-trust'}},
                   {'name': 'tmp', 'emptyDir': {'medium': 'Memory', 'sizeLimit': '64Mi'}}]
        mounts = [{'name': 'config', 'mountPath': '/etc/vcloud', 'readOnly': True},
                  {'name': 'tls', 'mountPath': '/var/run/vcloud/tls', 'readOnly': True},
                  {'name': 'trust', 'mountPath': '/var/run/vcloud/trust', 'readOnly': True},
                  {'name': 'tmp', 'mountPath': '/tmp'}]
        if mode == 'capacity':
            volumes += [{'name': 'state', 'persistentVolumeClaim': {'claimName': 'vcloud-hpc-state'}},
                        {'name': 'provider', 'csi': {'driver': 'secrets-store.csi.k8s.io', 'readOnly': True,
                                                   'volumeAttributes': {'secretProviderClass': 'spinifex-aws-credentials'}}},
                        {'name': 'prometheus', 'secret': {'secretName': 'vcloud-hpc-prometheus-mtls', 'defaultMode': 288}},
                        {'name': 'kubernetes', 'projected': {'defaultMode': 288, 'sources': [
                            {'serviceAccountToken': {'path': 'token', 'expirationSeconds': 600, 'audience': 'https://kubernetes.default.svc.cluster.local'}},
                            {'configMap': {'name': 'kube-root-ca.crt', 'items': [{'key': 'ca.crt', 'path': 'ca.crt'}]}}]}}]
            mounts += [{'name': 'state', 'mountPath': '/var/lib/vcloud'},
                       {'name': 'provider', 'mountPath': '/var/run/vcloud/spinifex', 'readOnly': True},
                       {'name': 'prometheus', 'mountPath': '/var/run/vcloud/prometheus', 'readOnly': True},
                       {'name': 'kubernetes', 'mountPath': '/var/run/vcloud/kubernetes', 'readOnly': True}]
        pod = {'serviceAccountName': name, 'automountServiceAccountToken': False,
               'securityContext': {'runAsNonRoot': True, 'runAsUser': 65532, 'runAsGroup': 65532,
                                   'fsGroup': 65532, 'seccompProfile': {'type': 'RuntimeDefault'}},
               'containers': [{'name': mode, 'image': IMAGE, 'imagePullPolicy': 'IfNotPresent', 'args': ['--mode', mode],
                   'env': feature_env(profile), 'ports': [{'name': 'api-mtls', 'containerPort': 8443}, {'name': 'health-metrics', 'containerPort': 9091}],
                   'securityContext': copy.deepcopy(SECURITY), 'resources': {'requests': {'cpu': '100m', 'memory': '128Mi'},
                                                                           'limits': {'cpu': '1', 'memory': '512Mi'}},
                   'volumeMounts': mounts, 'readinessProbe': {'httpGet': {'path': '/healthz', 'port': 9091}},
                   'livenessProbe': {'httpGet': {'path': '/healthz', 'port': 9091}}}], 'volumes': volumes}
        items.append(resource('Deployment', name, {'replicas': 0, 'strategy': {'type': 'Recreate'},
                    'selector': {'matchLabels': {'app.kubernetes.io/name': name}},
                    'template': {'metadata': {'labels': labels}, 'spec': pod}}, api='apps/v1'))
        items.append(resource('Service', name, {'selector': {'app.kubernetes.io/name': name},
            'ports': [{'name': 'api-mtls', 'port': 8443, 'targetPort': 8443}, {'name': 'health-metrics', 'port': 9091, 'targetPort': 9091}]}))
    return items


def queues(profile, worker=False):
    api = 'kueue.x-k8s.io/v1beta2'
    items = []
    for flavor, key in [('spinifex-h100-8x', profile['default_profile']), ('spinifex-a100-4x', 'spinifex.gpu.a100.80gb.4x')]:
        items.append(resource('ResourceFlavor', flavor, {'nodeLabels': {**TARGET, 'vcloud.io/gpu-profile': key, 'vcloud.io/gpu-role': 'batch'},
            'nodeTaints': [{'key': 'vcloud.io/gpu-role', 'value': 'batch', 'effect': 'NoSchedule'}],
            'topologyName': 'spinifex-gpu-topology'} if worker else {}, api=api, namespace=None))
    flavors = [{'name': name, 'resources': [{'name': resource_name, 'nominalQuota': 0, 'borrowingLimit': 0, 'lendingLimit': 0}
                     for resource_name in ['cpu', 'memory', 'nvidia.com/gpu']]} for name in ['spinifex-h100-8x', 'spinifex-a100-4x']]
    spec = {'namespaceSelector': {'matchLabels': {**TARGET, 'kubernetes.io/metadata.name': NS}},
            'queueingStrategy': 'StrictFIFO', 'stopPolicy': 'HoldAndDrain',
            'resourceGroups': [{'coveredResources': ['cpu', 'memory', 'nvidia.com/gpu'], 'flavors': flavors}]}
    if not worker:
        spec['admissionChecksStrategy'] = {'admissionChecks': [{'name': 'spinifex-multikueue'}]}
    items += [resource('ClusterQueue', QUEUE, spec, api=api, namespace=None),
              resource('LocalQueue', QUEUE, {'clusterQueue': QUEUE, 'stopPolicy': 'HoldAndDrain'}, api=api)]
    if worker:
        items += [resource('Topology', 'spinifex-gpu-topology', {'levels': [{'nodeLabel': 'vcloud.io/fabric-domain'},
                    {'nodeLabel': 'kubernetes.io/hostname'}]}, api=api, namespace=None)]
    else:
        items += [resource('AdmissionCheck', 'spinifex-multikueue',
                    {'controllerName': 'kueue.x-k8s.io/multikueue', 'parameters': {'apiGroup': 'kueue.x-k8s.io',
                     'kind': 'MultiKueueConfig', 'name': 'spinifex-workers'}}, api=api, namespace=None),
                  resource('MultiKueueConfig', 'spinifex-workers', {'clusters': ['spinifex-worker-01'], 'quotaManagement': 'Manual'}, api=api, namespace=None),
                  resource('MultiKueueCluster', 'spinifex-worker-01',
                           {'clusterSource': {'kubeConfig': {'locationType': 'Secret', 'location': 'spinifex-worker-01-kubeconfig'}}},
                           api=api, namespace=None)]
    return items


def integration(profile):
    items = [resource('SecretProviderClass', 'spinifex-aws-credentials', {'provider': 'openbao', 'parameters': {
        'roleName': 'vcloud-spinifex', 'baoAuthMountPath': 'kubernetes', 'audience': 'openbao',
        'objects': yaml.safe_dump([{'objectName': 'aws-credentials.json', 'secretPath': 'kv/data/vcloud/spinifex',
                                  'secretKey': 'credentials', 'filePermission': 288}], sort_keys=False)}},
        api='secrets-store.csi.x-k8s.io/v1'),
        resource('Role', 'vcloud-spinifex-observer', api='rbac.authorization.k8s.io/v1', rules=[{
            'apiGroups': ['kueue.x-k8s.io'], 'resources': ['workloads'], 'verbs': ['get', 'list']}]),
        resource('RoleBinding', 'vcloud-spinifex-observer', api='rbac.authorization.k8s.io/v1',
            subjects=[{'kind': 'ServiceAccount', 'name': 'vcloud-spinifex-bridge', 'namespace': NS}],
            roleRef={'apiGroup': 'rbac.authorization.k8s.io', 'kind': 'Role', 'name': 'vcloud-spinifex-observer'}),
        resource('ServiceAccount', 'vcloud-hpc-worker', automountServiceAccountToken=False, imagePullSecrets=[{'name': 'vcloud-registry-pull'}]),
        resource('ServiceAccount', 'vcloud-hpc-trigger', automountServiceAccountToken=False, imagePullSecrets=[{'name': 'vcloud-registry-pull'}])]
    return items


def worker_pod():
    return {'serviceAccountName': 'vcloud-hpc-worker', 'automountServiceAccountToken': False, 'runtimeClassName': 'nvidia',
        'nodeSelector': {**TARGET, 'vcloud.io/gpu-profile': 'spinifex.gpu.h100.80gb.8x', 'vcloud.io/gpu-role': 'batch'},
        'tolerations': [{'key': 'vcloud.io/gpu-role', 'operator': 'Equal', 'value': 'batch', 'effect': 'NoSchedule'}],
        'securityContext': {'runAsNonRoot': True, 'runAsUser': 65532, 'runAsGroup': 65532, 'fsGroup': 65532},
        'restartPolicy': 'Never', 'containers': [{'name': 'simulation', 'image': WORKER, 'imagePullPolicy': 'IfNotPresent',
            'command': ['python', '/opt/vcloud/gpu-check.py'], 'securityContext': copy.deepcopy(SECURITY),
            'resources': {'requests': {'cpu': '32', 'memory': '128Gi', 'nvidia.com/gpu': 8},
                          'limits': {'cpu': '32', 'memory': '128Gi', 'nvidia.com/gpu': 8}},
            'volumeMounts': [{'name': 'tmp', 'mountPath': '/tmp'}, {'name': 'shm', 'mountPath': '/dev/shm'}],
            'env': [{'name': 'NCCL_IB_DISABLE', 'value': '1'}, {'name': 'NCCL_SOCKET_IFNAME', 'value': 'eth0'}]}],
        'volumes': [{'name': 'tmp', 'emptyDir': {'medium': 'Memory', 'sizeLimit': '64Mi'}},
                    {'name': 'shm', 'emptyDir': {'medium': 'Memory', 'sizeLimit': '16Gi'}}]}


def examples(profile):
    template = {'metadata': {'labels': {'app.kubernetes.io/name': 'vcloud-hpc-worker', **TARGET}}, 'spec': worker_pod()}
    job = resource('Job', 'vcloud-eight-gpu-reference', {'suspend': True, 'managedBy': 'kueue.x-k8s.io/multikueue',
        'completions': 1, 'parallelism': 1, 'backoffLimit': 0, 'activeDeadlineSeconds': 600, 'template': copy.deepcopy(template)}, api='batch/v1')
    job['metadata']['labels']['kueue.x-k8s.io/queue-name'] = QUEUE
    jobset = resource('JobSet', 'vcloud-two-node-reference', {'suspend': True, 'managedBy': 'kueue.x-k8s.io/multikueue',
        'failurePolicy': {'maxRestarts': 0}, 'replicatedJobs': [{'name': 'workers', 'replicas': 2,
            'template': {'spec': {'parallelism': 1, 'completions': 1, 'backoffLimit': 0, 'template': copy.deepcopy(template)}}}]},
        api='jobset.x-k8s.io/v1alpha2')
    jobset['metadata']['labels']['kueue.x-k8s.io/queue-name'] = QUEUE
    jobset['spec']['replicatedJobs'][0]['template']['spec']['template']['metadata']['annotations'] = {'kueue.x-k8s.io/podset-required-topology': 'vcloud.io/fabric-domain'}
    # A reference vLLM Knative service is intentionally outside the Argo source.
    # Creating a revision may load a GPU even with min-scale=0; accept it separately.
    ksvc = resource('Service', 'vcloud-vllm', {'template': {'metadata': {'labels': {'app.kubernetes.io/name': 'vcloud-vllm', **TARGET},
        'annotations': {'autoscaling.knative.dev/min-scale': '0', 'autoscaling.knative.dev/max-scale': '1',
                        'autoscaling.knative.dev/target': '1'}}, 'spec': {
        'serviceAccountName': 'vcloud-vllm', 'automountServiceAccountToken': False, 'runtimeClassName': 'nvidia',
        'nodeSelector': {'vcloud.io/gpu-role': 'inference', 'vcloud.io/gpu-profile': profile['default_profile']},
        'tolerations': [{'key': 'vcloud.io/gpu-role', 'operator': 'Equal', 'value': 'inference', 'effect': 'NoSchedule'}],
        'securityContext': {'runAsNonRoot': True, 'runAsUser': 65532, 'runAsGroup': 65532, 'fsGroup': 65532},
        'containerConcurrency': 1, 'timeoutSeconds': 180, 'responseStartTimeoutSeconds': 120,
        'containers': [{'name': 'vllm', 'image': 'registry.vcloud.example.com/vllm/vllm-openai:v0.31.0', 'imagePullPolicy': 'IfNotPresent',
            'command': ['vllm', 'serve'], 'args': [profile['model_path'], '--served-model-name', profile['vllm_model'],
                '--host', '0.0.0.0', '--port', '8080', '--tensor-parallel-size', '1', '--max-model-len', '4096',
                '--gpu-memory-utilization', '0.85', '--reasoning-parser', 'deepseek_r1', '--no-enable-log-requests', '--no-enable-log-outputs'],
            'ports': [{'containerPort': 8080}], 'securityContext': copy.deepcopy(SECURITY),
            'env': [{'name': 'HF_HUB_OFFLINE', 'value': '1'}, {'name': 'TRANSFORMERS_OFFLINE', 'value': '1'},
                    {'name': 'HOME', 'value': '/tmp'}, {'name': 'XDG_CACHE_HOME', 'value': '/tmp/cache'}],
            'resources': {'requests': {'cpu': '8', 'memory': '80Gi', 'nvidia.com/gpu': 1},
                          'limits': {'cpu': '16', 'memory': '96Gi', 'nvidia.com/gpu': 1}},
            'volumeMounts': [{'name': 'models', 'mountPath': '/models', 'readOnly': True}, {'name': 'tmp', 'mountPath': '/tmp'},
                            {'name': 'shm', 'mountPath': '/dev/shm'}],
            'readinessProbe': {'httpGet': {'path': '/health', 'port': 8080}}}],
        'volumes': [{'name': 'models', 'persistentVolumeClaim': {'claimName': 'vcloud-deepseek-models', 'readOnly': True}},
                    {'name': 'tmp', 'emptyDir': {'medium': 'Memory', 'sizeLimit': '2Gi'}},
                    {'name': 'shm', 'emptyDir': {'medium': 'Memory', 'sizeLimit': '8Gi'}}]}}}, api='serving.knative.dev/v1')
    ksvc['metadata']['labels']['networking.knative.dev/visibility'] = 'cluster-local'
    return job, jobset, [resource('ServiceAccount', 'vcloud-vllm', automountServiceAccountToken=False,
                                 imagePullSecrets=[{'name': 'vcloud-registry-pull'}]), ksvc]


def pipeline(profile):
    task = resource('Task', 'vcloud-hpc-capacity-check', {'params': [{'name': 'capacity-request', 'type': 'string', 'default': '{}'}],
        'steps': [{'name': 'signal', 'image': IMAGE, 'imagePullPolicy': 'IfNotPresent', 'command': ['python', '/opt/vcloud/trigger.py'],
                   'env': feature_env(profile) + [{'name': 'CAPACITY_REQUEST_JSON', 'value': '$(params.capacity-request)'}],
                   'securityContext': copy.deepcopy(SECURITY), 'computeResources': {'requests': {'cpu': '50m', 'memory': '128Mi'},
                        'limits': {'cpu': '500m', 'memory': '256Mi'}},
                   'volumeMounts': [{'name': 'trigger', 'mountPath': '/var/run/vcloud/trigger', 'readOnly': True}, {'name': 'tmp', 'mountPath': '/tmp'}]}],
        'volumes': [{'name': 'trigger', 'secret': {'secretName': 'vcloud-hpc-tekton-mtls', 'defaultMode': 288}},
                    {'name': 'tmp', 'emptyDir': {'medium': 'Memory', 'sizeLimit': '16Mi'}}]}, api='tekton.dev/v1')
    flow = resource('Pipeline', 'vcloud-hpc-offload', {'params': [{'name': 'capacity-request', 'type': 'string', 'default': '{}'}],
        'tasks': [{'name': 'capacity-check', 'taskRef': {'name': 'vcloud-hpc-capacity-check'},
                   'params': [{'name': 'capacity-request', 'value': '$(params.capacity-request)'}]}]}, api='tekton.dev/v1')
    run = resource('PipelineRun', 'vcloud-hpc-offload-reference', {'status': 'PipelineRunPending', 'pipelineRef': {'name': 'vcloud-hpc-offload'},
        'taskRunTemplate': {'serviceAccountName': 'vcloud-hpc-trigger', 'podTemplate': {'automountServiceAccountToken': False,
            'securityContext': {'runAsNonRoot': True, 'runAsUser': 65532, 'runAsGroup': 65532, 'fsGroup': 65532,
                                'seccompProfile': {'type': 'RuntimeDefault'}}}},
        'params': [{'name': 'capacity-request', 'value': '{}'}], 'timeouts': {'pipeline': '2m0s'}}, api='tekton.dev/v1')
    return [task, flow], run


def gateway():
    upstream = resource('ApisixUpstream', 'vcloud-deepseek-agent', {'scheme': 'https',
        'upstreamHost': 'vcloud-deepseek-agent.hpc-compute.svc.cluster.local',
        'timeout': {'connect': '5s', 'send': '15s', 'read': '150s'},
        'tlsSecret': {'name': 'vcloud-agent-upstream-mtls', 'namespace': NS}},
        api='apisix.apache.org/v2')
    route = resource('ApisixRoute', 'vcloud-agent', {'ingressClassName': 'apisix', 'http': [{
        'name': 'agent', 'match': {'hosts': ['api.vcloud.example.com'], 'paths': ['/v1/agent/runs'], 'methods': ['POST'],
            'exprs': [{'subject': {'scope': 'Variable', 'name': 'scheme'}, 'op': 'Equal', 'value': 'https'}]},
        'plugin_config_name': 'vcloud-agent-oidc', 'backends': [{'serviceName': 'vcloud-deepseek-agent', 'servicePort': 8443}],
        'plugins': [{'name': 'limit-req', 'enable': True, 'config': {'rate': 1, 'burst': 4, 'rejected_code': 429, 'key': 'remote_addr'}},
                    {'name': 'client-control', 'enable': True, 'config': {'max_body_size': 65536}}]}]},
        api='apisix.apache.org/v2')
    # Backend, upstream and plugin belong to the route namespace. The controller
    # can watch multiple namespaces; no unsupported cross-namespace backend field.
    plugin = copy.deepcopy(yaml.safe_load((ROOT / 'module-4b/manifests/oidc-plugin.yaml').read_text()))
    plugin['metadata']['name'] = 'vcloud-agent-oidc'; plugin['metadata']['namespace'] = NS
    tls = resource('ApisixTls', 'vcloud-agent-gateway', {'hosts': ['api.vcloud.example.com'],
        'secret': {'name': 'vcloud-agent-gateway-tls', 'namespace': NS}}, api='apisix.apache.org/v2')
    return [plugin, upstream, route, tls]


def network():
    def policy(name, endpoint, ingress=None, egress=None):
        spec = {'endpointSelector': {'matchLabels': endpoint}}
        if ingress is not None: spec['ingress'] = ingress
        if egress is not None: spec['egress'] = egress
        return resource('CiliumNetworkPolicy', name, spec, api='cilium.io/v2')
    def peer(name, namespace=NS):
        return {'matchLabels': {'k8s:io.kubernetes.pod.namespace': namespace, 'k8s:app.kubernetes.io/name': name}}
    def knative(name):
        return {'matchLabels': {'k8s:io.kubernetes.pod.namespace': 'platform-services', 'k8s:app': name}}
    def ports(*numbers): return [{'ports': [{'port': str(n), 'protocol': 'TCP'} for n in numbers]}]
    items = [policy('vcloud-hpc-reference-default-deny', TARGET, ingress=[], egress=[]),
        policy('vcloud-hpc-reference-dns', TARGET, egress=[{'toEndpoints': [{'matchLabels': {'k8s:io.kubernetes.pod.namespace': 'kube-system', 'k8s:k8s-app': 'kube-dns'}}],
            'toPorts': [{'ports': [{'port': '53', 'protocol': 'UDP'}, {'port': '53', 'protocol': 'TCP'}],
                        'rules': {'dns': [{'matchPattern': '*.svc.cluster.local'}, {'matchName': 'ec2.spinifex.pcloud.example.com'}]}}]}]),
        policy('vcloud-agent-in', {'app.kubernetes.io/name': 'vcloud-deepseek-agent'}, ingress=[{'fromEndpoints': [peer('apisix', 'platform-services')], 'toPorts': ports(8443)}]),
        policy('vcloud-capacity-in', {'app.kubernetes.io/name': 'vcloud-spinifex-bridge'}, ingress=[
            {'fromEndpoints': [{'matchLabels': {'k8s:io.kubernetes.pod.namespace': NS, 'k8s:tekton.dev/task': 'vcloud-hpc-capacity-check'}},
                               peer('alertmanager', 'platform-services')], 'toPorts': ports(8443)}]),
        policy('vcloud-capacity-out', {'app.kubernetes.io/name': 'vcloud-spinifex-bridge'}, egress=[
            {'toEntities': ['kube-apiserver'], 'toPorts': ports(443, 6443)},
            {'toEndpoints': [peer('prometheus', 'platform-services')], 'toPorts': ports(9090)},
            {'toEndpoints': [peer('spinifex-aws-gateway')], 'toPorts': ports(3000)},
            {'toFQDNs': [{'matchName': 'ec2.spinifex.pcloud.example.com'}], 'toPorts': ports(443)}]),
        policy('vcloud-agent-inference', {'app.kubernetes.io/name': 'vcloud-deepseek-agent'}, egress=[
            {'toEndpoints': [knative('3scale-kourier-gateway')], 'toPorts': ports(8443)},
            {'toEndpoints': [{'matchLabels': {'k8s:io.kubernetes.pod.namespace': NS, 'k8s:serving.knative.dev/service': 'vcloud-vllm'}},
                             knative('activator')], 'toPorts': ports(8112)}]),
        policy('vcloud-hpc-probes-metrics', TARGET, ingress=[{'fromEntities': ['host', 'remote-node'], 'toPorts': ports(9091)},
            {'fromEndpoints': [peer('prometheus', 'platform-services')], 'toPorts': ports(9091)}]),
        policy('vcloud-hpc-trigger-out', {'tekton.dev/task': 'vcloud-hpc-capacity-check'}, egress=[{'toEndpoints': [peer('vcloud-spinifex-bridge')], 'toPorts': ports(8443)}])]
    # Reciprocal policies are namespace-scoped; no global egress exception.
    for sender, dest, port in [('apisix', 'vcloud-deepseek-agent', 8443), ('alertmanager', 'vcloud-spinifex-bridge', 8443),
                               ('prometheus', 'vcloud-spinifex-bridge', 9091), ('prometheus', 'vcloud-deepseek-agent', 9091)]:
        p = policy('vcloud-hpc-' + sender + '-' + dest, {'app.kubernetes.io/name': sender}, egress=[{'toEndpoints': [peer(dest)], 'toPorts': ports(port)}])
        p['metadata']['namespace'] = 'platform-services'; items.append(p)
    p = policy('vcloud-hpc-prometheus-in', {'app.kubernetes.io/name': 'prometheus'}, ingress=[{'fromEndpoints': [peer('vcloud-spinifex-bridge')], 'toPorts': ports(9090)}])
    p['metadata']['namespace'] = 'platform-services'; items.append(p)
    p = policy('vcloud-hpc-knative-in-out', {}, ingress=[{'fromEndpoints': [peer('vcloud-deepseek-agent')], 'toPorts': ports(8443, 8112)}],
               egress=[{'toEndpoints': [{'matchLabels': {'k8s:io.kubernetes.pod.namespace': NS, 'k8s:serving.knative.dev/service': 'vcloud-vllm'}}], 'toPorts': ports(8112, 9090, 8022)}])
    p['metadata']['namespace'] = 'platform-services'
    p['spec']['endpointSelector'] = {'matchExpressions': [{'key': 'k8s:app', 'operator': 'In', 'values': ['3scale-kourier-gateway', 'activator', 'autoscaler']}]}
    items.append(p)
    items.append(policy('vcloud-vllm-knative', {'serving.knative.dev/service': 'vcloud-vllm'}, ingress=[
        {'fromEndpoints': [knative('3scale-kourier-gateway'), knative('activator')], 'toPorts': ports(8112)},
        {'fromEndpoints': [knative('autoscaler')], 'toPorts': ports(9090, 8022)},
        {'fromEntities': ['host'], 'toPorts': ports(8080, 8022)}], egress=[{'toEndpoints': [knative('autoscaler')], 'toPorts': ports(8080)}]))
    return items


def argocd():
    kinds = [('apps', 'Deployment'), ('', 'Service'), ('', 'ConfigMap'), ('', 'PersistentVolumeClaim'), ('', 'ServiceAccount'),
             ('rbac.authorization.k8s.io', 'Role'), ('rbac.authorization.k8s.io', 'RoleBinding'), ('cilium.io', 'CiliumNetworkPolicy'),
             ('tekton.dev', 'Task'), ('tekton.dev', 'Pipeline'), ('monitoring.coreos.com', 'PrometheusRule'), ('monitoring.coreos.com', 'ServiceMonitor'),
             ('secrets-store.csi.x-k8s.io', 'SecretProviderClass'), ('kueue.x-k8s.io', 'LocalQueue'),
             ('apisix.apache.org', 'ApisixRoute'), ('apisix.apache.org', 'ApisixUpstream'),
             ('apisix.apache.org', 'ApisixPluginConfig'), ('apisix.apache.org', 'ApisixTls')]
    project = resource('AppProject', 'vcloud-hpc', {'sourceRepos': ['https://github.com/amazen33/vCloud.git'],
        'destinations': [{'server': 'https://kubernetes.default.svc', 'namespace': n} for n in [NS, 'platform-services']],
        'clusterResourceWhitelist': [{'group': 'kueue.x-k8s.io', 'kind': k} for k in ['ClusterQueue', 'ResourceFlavor', 'AdmissionCheck', 'MultiKueueConfig', 'MultiKueueCluster']],
        'namespaceResourceWhitelist': [{'group': group, 'kind': kind} for group, kind in kinds]}, api='argoproj.io/v1alpha1', namespace='platform-services')
    app = resource('Application', 'vcloud-hpc-reference', {'project': 'vcloud-hpc',
        'source': {'repoURL': 'https://github.com/amazen33/vCloud.git', 'targetRevision': 'main', 'path': 'module-5b/manifests', 'directory': {'recurse': False}},
        'destination': {'server': 'https://kubernetes.default.svc', 'namespace': NS},
        'syncPolicy': {'automated': {'enabled': False, 'prune': False, 'selfHeal': False, 'allowEmpty': False},
                       'syncOptions': ['CreateNamespace=false']}}, api='argoproj.io/v1alpha1', namespace='platform-services')
    return [project, app]


def monitoring():
    rule = {'groups': [{'name': 'vcloud.hpc.pressure', 'interval': '30s', 'rules': [
        {'record': 'vcloud:hpc_cpu_saturation_ratio', 'expr': '1 - avg by(cluster) (rate(node_cpu_seconds_total{mode="idle",cluster="vCloud-prod-01"}[5m]))'},
        {'record': 'vcloud:hpc_gpu_saturation_ratio', 'expr': 'max by(cluster) (DCGM_FI_DEV_GPU_UTIL{cluster="vCloud-prod-01"}) / 100'},
        {'record': 'vcloud:hpc_memory_limit_ratio', 'expr': 'sum by(cluster) (container_memory_working_set_bytes{namespace="hpc-compute",cluster="vCloud-prod-01",container!="",container!="POD"}) / sum by(cluster) (kube_pod_container_resource_limits{namespace="hpc-compute",cluster="vCloud-prod-01",resource="memory",unit="byte"})'},
        {'alert': 'VCloudHPCBurstCandidate', 'expr': '(vcloud:hpc_cpu_saturation_ratio > 0.85 or vcloud:hpc_gpu_saturation_ratio > 0.85 or vcloud:hpc_memory_limit_ratio >= 0.85) and on(cluster) (sum by(cluster) (kueue_pending_workloads{cluster="vCloud-prod-01",cluster_queue="spinifex-hpc-burst"}) > 0)',
         'for': '5m', 'labels': {'severity': 'info', 'queue': QUEUE}, 'annotations': {'summary': 'Reserved HPC demand may need capacity; bridge refetches quota and fresh metrics before any action'}},
        {'alert': 'VCloudHPCReferenceUnexpectedlyEnabled', 'expr': 'vcloud_spinifex_offload_enabled == 1', 'for': '1m',
         'labels': {'severity': 'critical'}, 'annotations': {'summary': 'Disabled reference offload flag was enabled; inspect all independent acceptance gates'}},
        {'alert': 'VCloudHPCReconciliationNeedsReview', 'expr': 'vcloud_spinifex_reconciliation_uncertain > 0 or vcloud_spinifex_reconciliation_expired > 0 or increase(vcloud_spinifex_reconciliation_failures[10m]) > 0',
         'for': '1m', 'labels': {'severity': 'warning'}, 'annotations': {'summary': 'Capacity outcome or cleanup requires operator reconciliation; quota stays charged'}}]}]}
    items = [resource('PrometheusRule', 'vcloud-hpc', rule, api='monitoring.coreos.com/v1', namespace='platform-services')]
    for component in ['vcloud-deepseek-agent', 'vcloud-spinifex-bridge']:
        items.append(resource('ServiceMonitor', component, {'selector': {'matchLabels': {'app.kubernetes.io/name': component}},
            'namespaceSelector': {'matchNames': [NS]}, 'endpoints': [{'port': 'health-metrics', 'path': '/metrics', 'interval': '30s', 'honorLabels': False}]},
            api='monitoring.coreos.com/v1', namespace='platform-services'))
    return items, rule


def files():
    profile = json.loads((MODULE / 'reference-profile.json').read_text())
    job, jobset, vllm = examples(profile); tasks, run = pipeline(profile); monitors, rules = monitoring()
    docs = {'manifests/workloads.yaml': workloads(profile), 'manifests/queues.yaml': queues(profile),
            'manifests/integration.yaml': integration(profile), 'manifests/gateway.yaml': gateway(), 'manifests/network.yaml': network(),
            'manifests/pipeline.yaml': tasks, 'manifests/observability.yaml': monitors, 'argocd/application.yaml': argocd(),
            'worker/queues.yaml': queues(profile, worker=True), 'examples/job.yaml': [job], 'examples/jobset.yaml': [jobset],
            'examples/vllm.knative.yaml': vllm, 'examples/pipelinerun.yaml': [run]}
    # ServiceMonitors select labels on Services, not deployment metadata.
    for obj in docs['manifests/workloads.yaml']:
        if obj['kind'] == 'Service': obj['metadata']['labels']['app.kubernetes.io/name'] = obj['metadata']['name']
    result = {path: '# Generated by tools/render_module5b.py; disabled reference, not an installer.\n' + yaml.safe_dump_all(objects, sort_keys=False)
              for path, objects in docs.items()}
    result['observability/rules.yaml'] = yaml.safe_dump(rules, sort_keys=False)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument('--check', action='store_true'); args = parser.parse_args()
    drift = []
    for relative, content in files().items():
        path = MODULE / relative
        if args.check:
            if not path.exists() or path.read_text() != content: drift.append(relative)
        else:
            path.parent.mkdir(parents=True, exist_ok=True); path.write_text(content, encoding='utf-8', newline='\n')
    if drift: sys.exit('Module 5b generation drift: ' + ', '.join(drift))
    print('Module 5b manifests ' + ('match generator' if args.check else 'generated'))
