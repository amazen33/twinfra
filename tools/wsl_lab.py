#!/usr/bin/env python3
"""Render and audit the explicitly requested WSL K3s development profile.

Production SSoT and the frozen node exception are read-only inputs. Connected
staging imports pinned images under canonical registry names; workload pulls
cannot fall back to a public registry. No credentials are rendered or reported.
"""
import argparse
import copy
import ipaddress
import json
from pathlib import Path
import re
import subprocess
import sys
import tomllib
import yaml

ROOT = Path(__file__).resolve().parents[1]
API_PORT = 16443
sys.path.insert(0, str(ROOT / 'tools'))
from module2 import audit_objects, load_policy, normalize_pods, verify_bundle
from wsl_lab_dns_image import IMAGE as DNS_IMAGE


def profile():
    return json.loads((ROOT / 'lab/wsl/profile.json').read_text(encoding='utf-8'))


def check_facts(facts, p):
    if facts['os'] != 'ubuntu' or facts['version'] not in ('24.04', '26.04'):
        raise ValueError('Only the separate Ubuntu 24.04/26.04 WSL lab is supported')
    if 'microsoft' not in facts['kernel'].lower() or facts['pid1'] != 'systemd':
        raise ValueError('This lab requires WSL2 with systemd')
    if facts['networking'] != 'mirrored' or facts['cgroup'] != 'cgroup2fs' or not facts['btf']:
        raise ValueError('Mirrored networking, cgroup v2 and kernel BTF are required')
    if facts['memoryKiB'] < p['minimumMemoryGiB'] * 1024**2 or facts['cpus'] < p['minimumCPUs']:
        raise ValueError('Insufficient WSL resources')
    if facts['freeDiskKiB'] < 20 * 1024**2:
        raise ValueError('At least 20 GiB free on the Linux filesystem is required')
    if any(service not in ('k3s', 'containerd') for service in facts['activeRuntimes']):
        raise ValueError('Unrelated runtime service active')
    if '/etc/kubernetes/admin.conf' in facts['existingState']:
        raise ValueError('Unrelated kubeadm cluster exists')
    if not facts['owned'] and (facts['existingState'] or facts['activeRuntimes'] or facts['apiPortBusy']):
        raise ValueError('Refusing to adopt an existing cluster/runtime or occupied API port')
    if not facts['owned']:
        for route in facts['routes']:
            dst = route.get('dst', 'default')
            if dst != 'default' and any(ipaddress.ip_network(dst).overlaps(ipaddress.ip_network(p[k])) for k in ('podCIDR', 'serviceCIDR')):
                raise ValueError('Lab CIDR overlaps an existing route')
    return facts


def mirrored(source, p):
    if ':latest' in source or not re.search(r':[^/@]+(?:@sha256:[a-f0-9]{64})?$', source):
        raise ValueError('Pinned image required')
    return p['registry'] + '/' + source


def containerd_config(text, p):
    text = text.replace('SystemdCgroup = false', 'SystemdCgroup = true')
    text = re.sub(r"(?m)^(\s*config_path\s*=\s*)['\"][^'\"]*['\"]", r"\1'/etc/containerd/certs.d'", text)
    pause = mirrored(p['pauseImage'], p)
    text = re.sub(r"(?m)^(\s*sandbox\s*=\s*)['\"][^'\"]*['\"]", lambda m: m[1] + repr(pause), text)
    parsed = tomllib.loads(text)
    runtime = parsed['plugins']['io.containerd.cri.v1.runtime']
    images = parsed['plugins']['io.containerd.cri.v1.images']
    if not runtime['containerd']['runtimes']['runc']['options']['SystemdCgroup']:
        raise ValueError('SystemdCgroup missing')
    if images['registry']['config_path'] != '/etc/containerd/certs.d' or images['pinned_images']['sandbox'] != pause:
        raise ValueError('Private registry/sandbox config missing')
    cni = runtime['cni']
    if cni['conf_dir'] != '/etc/cni/net.d' or cni.get('bin_dirs', [cni.get('bin_dir')]) != ['/opt/cni/bin']:
        raise ValueError('Runtime CNI paths do not match the approved node scope')
    return text


def repair_local_client_endpoint(config):
    """Preserve credentials; repair only the owned failed-bootstrap loopback URL."""
    result = copy.deepcopy(config)
    for cluster in result.get('clusters', []):
        if cluster.get('cluster', {}).get('server') == 'https://127.0.0.1:6444':
            cluster['cluster']['server'] = f'https://127.0.0.1:{API_PORT + 1}'
    return result


def namespace_phase(objects, helm_owned=False):
    result = []
    for obj in objects:
        if obj and obj.get('kind') == 'Namespace':
            obj = copy.deepcopy(obj)
            if helm_owned:
                obj['metadata']['annotations'] = obj['metadata'].get('annotations') or {}
                obj['metadata']['annotations'].update({
                    'meta.helm.sh/release-name': 'cilium', 'meta.helm.sh/release-namespace': 'kube-system'})
                obj['metadata']['labels'] = obj['metadata'].get('labels') or {}
                obj['metadata']['labels']['app.kubernetes.io/managed-by'] = 'Helm'
            result.append(obj)
    return result


def k3s_config(p, node_ip):
    ipaddress.ip_address(node_ip)
    # Mirrored WSL routes node-address access reliably; localhost/wildcard
    # self-bootstrap can be intercepted by the Windows shared network stack.
    return {'node-name': p['nodeName'], 'node-ip': node_ip, 'bind-address': node_ip,
            'https-listen-port': API_PORT, 'write-kubeconfig-mode': '0600',
            'flannel-backend': 'none', 'disable-network-policy': True, 'disable-kube-proxy': True,
            'disable': ['traefik', 'servicelb', 'local-storage', 'metrics-server', 'coredns'],
            'disable-helm-controller': True, 'cluster-cidr': p['podCIDR'],
            'service-cidr': p['serviceCIDR'], 'cluster-dns': p['dnsServiceIP'],
            'container-runtime-endpoint': 'unix:///run/containerd/containerd.sock',
            'kubelet-arg': ['cgroup-driver=systemd', 'fail-swap-on=false'],
            'node-label': ['vcloud.io/environment=local-validation'],
            'kube-apiserver-arg': ['anonymous-auth=false']}


def resource(kind, name, spec=None, namespace=None, api='v1', labels=None):
    obj = {'apiVersion': api, 'kind': kind, 'metadata': {'name': name}}
    if namespace:
        obj['metadata']['namespace'] = namespace
    if labels:
        obj['metadata']['labels'] = labels
    if spec is not None:
        obj['spec'] = spec
    return obj


def security():
    return {'runAsNonRoot': True, 'runAsUser': 65532, 'runAsGroup': 65532,
            'allowPrivilegeEscalation': False, 'readOnlyRootFilesystem': True,
            'capabilities': {'drop': ['ALL']}, 'seccompProfile': {'type': 'RuntimeDefault'}}


def manifests(p):
    objects = list(yaml.safe_load_all((ROOT / 'manifests/foundation.yaml').read_text(encoding='utf-8')))
    for obj in objects:
        if obj['kind'] == 'Namespace':
            obj['metadata']['annotations']['vcloud.io/cluster'] = p['name']
            obj['metadata']['labels']['vcloud.io/environment'] = 'local-validation'
    for ns in ('platform-services', 'workload-apps', 'hpc-compute'):
        # Service port 53 forwards to unprivileged CoreDNS port 1053. Cilium
        # evaluates the backend port; no extra capability is granted to DNS.
        objects.append(resource('NetworkPolicy', 'allow-internal-dns',
            {'podSelector': {}, 'policyTypes': ['Egress'], 'egress': [{'to': [{
                'namespaceSelector': {'matchLabels': {'kubernetes.io/metadata.name': 'kube-system'}},
                'podSelector': {'matchLabels': {'k8s-app': 'kube-dns'}}}],
                'ports': [{'port': 1053, 'protocol': proto} for proto in ('TCP', 'UDP')]}]},
            ns, 'networking.k8s.io/v1'))
    sa = resource('ServiceAccount', 'vcloud-lab-dns', namespace='kube-system')
    objects.append(sa)
    role = resource('ClusterRole', 'vcloud-lab-dns', api='rbac.authorization.k8s.io/v1')
    role['rules'] = [{'apiGroups': [''], 'resources': ['endpoints', 'services', 'pods', 'namespaces'], 'verbs': ['list', 'watch']},
                     {'apiGroups': ['discovery.k8s.io'], 'resources': ['endpointslices'], 'verbs': ['list', 'watch']}]
    objects.append(role)
    binding = resource('ClusterRoleBinding', 'vcloud-lab-dns', api='rbac.authorization.k8s.io/v1')
    binding.update(roleRef={'apiGroup': 'rbac.authorization.k8s.io', 'kind': 'ClusterRole', 'name': 'vcloud-lab-dns'},
                   subjects=[{'kind': 'ServiceAccount', 'name': 'vcloud-lab-dns', 'namespace': 'kube-system'}])
    objects.append(binding)
    cm = resource('ConfigMap', 'vcloud-lab-dns', namespace='kube-system')
    # Cluster DNS only: no arbitrary external DNS forwarder bypasses deny-all.
    cm['data'] = {'Corefile': '.:1053 {\n errors\n health :8080\n ready :8181\n kubernetes cluster.local in-addr.arpa ip6.arpa {\n  pods disabled\n  fallthrough in-addr.arpa ip6.arpa\n }\n cache 30\n reload\n loop\n}\n'}
    objects.append(cm)
    dns_container = {'name': 'coredns', 'image': DNS_IMAGE, 'imagePullPolicy': 'IfNotPresent',
        'args': ['-conf', '/etc/coredns/Corefile'], 'securityContext': security(),
        'resources': {'requests': {'cpu': '100m', 'memory': '64Mi'}, 'limits': {'cpu': '500m', 'memory': '128Mi'}},
        'ports': [{'name': 'dns', 'containerPort': 1053, 'protocol': 'UDP'}, {'name': 'dns-tcp', 'containerPort': 1053, 'protocol': 'TCP'}],
        'readinessProbe': {'httpGet': {'path': '/ready', 'port': 8181}},
        'livenessProbe': {'httpGet': {'path': '/health', 'port': 8080}},
        'volumeMounts': [{'name': 'config', 'mountPath': '/etc/coredns', 'readOnly': True}]}
    objects.append(resource('Deployment', 'vcloud-lab-dns', {'replicas': 1,
        'selector': {'matchLabels': {'k8s-app': 'kube-dns'}}, 'template': {
            'metadata': {'labels': {'k8s-app': 'kube-dns', 'vcloud.io/environment': 'local-validation'}},
            'spec': {'serviceAccountName': 'vcloud-lab-dns', 'securityContext': {'seccompProfile': {'type': 'RuntimeDefault'}},
                'containers': [dns_container], 'volumes': [{'name': 'config', 'configMap': {'name': 'vcloud-lab-dns'}}]}}}, 'kube-system', 'apps/v1'))
    objects.append(resource('Service', 'kube-dns', {'clusterIP': p['dnsServiceIP'], 'selector': {'k8s-app': 'kube-dns'},
        'ports': [{'name': 'dns', 'port': 53, 'targetPort': 1053, 'protocol': 'UDP'},
                  {'name': 'dns-tcp', 'port': 53, 'targetPort': 1053, 'protocol': 'TCP'}]}, 'kube-system', labels={'k8s-app': 'kube-dns'}))
    return objects


def smoke(p):
    cm = resource('ConfigMap', 'vcloud-lab-smoke', namespace='platform-services')
    cm['data'] = {'index.html': 'vcloud-wsl-ok\n'}
    result = [cm]
    for ns, role in [('platform-services', 'server'), ('workload-apps', 'allowed'), ('hpc-compute', 'denied')]:
        container = {'name': 'smoke', 'image': mirrored(p['smokeImage'], p), 'imagePullPolicy': 'IfNotPresent',
            'securityContext': security(), 'command': ['sh', '-c', 'sleep 36000'],
            'resources': {'requests': {'cpu': '10m', 'memory': '16Mi'}, 'limits': {'cpu': '100m', 'memory': '32Mi'}}}
        spec = {'automountServiceAccountToken': False, 'containers': [container]}
        if role == 'server':
            container['command'] = ['httpd', '-f', '-p', '8080', '-h', '/www']
            container['volumeMounts'] = [{'name': 'www', 'mountPath': '/www', 'readOnly': True}]
            spec['volumes'] = [{'name': 'www', 'configMap': {'name': 'vcloud-lab-smoke'}}]
        result.append(resource('Pod', 'vcloud-lab-' + role, spec, ns, labels={'vcloud.io/lab-role': role}))
    result.append(resource('Service', 'vcloud-lab-server', {'selector': {'vcloud.io/lab-role': 'server'},
        'ports': [{'port': 8080, 'targetPort': 8080}]}, 'platform-services'))
    result.append(resource('NetworkPolicy', 'vcloud-lab-allow-client', {'podSelector': {'matchLabels': {'vcloud.io/lab-role': 'allowed'}},
        'policyTypes': ['Egress'], 'egress': [{'to': [{'namespaceSelector': {'matchLabels': {'kubernetes.io/metadata.name': 'platform-services'}},
            'podSelector': {'matchLabels': {'vcloud.io/lab-role': 'server'}}}], 'ports': [{'port': 8080, 'protocol': 'TCP'}]}]}, 'workload-apps', 'networking.k8s.io/v1'))
    result.append(resource('NetworkPolicy', 'vcloud-lab-allow-server', {'podSelector': {'matchLabels': {'vcloud.io/lab-role': 'server'}},
        'policyTypes': ['Ingress'], 'ingress': [{'from': [{'namespaceSelector': {'matchLabels': {'kubernetes.io/metadata.name': 'workload-apps'}},
            'podSelector': {'matchLabels': {'vcloud.io/lab-role': 'allowed'}}}], 'ports': [{'port': 8080, 'protocol': 'TCP'}]}]}, 'platform-services', 'networking.k8s.io/v1'))
    return result


def audit(objects):
    violations = audit_objects(normalize_pods(objects), load_policy())['violations']
    if violations:
        raise ValueError('; '.join(violations))


def render(build, node_ip, device):
    p = profile()
    build.mkdir(parents=True, exist_ok=True)
    cilium = yaml.safe_load((ROOT / 'module-2/values/cilium.yaml').read_text(encoding='utf-8'))
    cilium.update(k8sServiceHost=node_ip, k8sServicePort=API_PORT, devices=[device], cluster={'name': p['name']})
    datasets = {'k3s-config.yaml': k3s_config(p, node_ip), 'cilium-values.yaml': cilium}
    for name, data in datasets.items():
        (build / name).write_text(yaml.safe_dump(data, sort_keys=False), encoding='utf-8', newline='\n')
    for name, objects in [('foundation-dns.yaml', manifests(p)), ('smoke.yaml', smoke(p))]:
        audit(objects)
        (build / name).write_text(yaml.safe_dump_all(objects, sort_keys=False), encoding='utf-8', newline='\n')
    # Exact existing Cilium node images are the only root/capability exception.
    policy = load_policy()
    images = sorted({c['image'] for k, v in policy['agents'].items() if 'cilium' in k for c in v['containers']})
    (build / 'cilium-images.txt').write_text('\n'.join(images) + '\n', encoding='utf-8', newline='\n')
    return datasets


def validate(build, helm, kubeconform, schemas=None):
    verify_bundle()
    command = [helm, 'template', 'cilium', str(ROOT / 'module-2/vendor/cilium-1.20.2.tgz'),
               '--namespace', 'kube-system', '-f', str(build / 'cilium-values.yaml')]
    output = subprocess.check_output(command, text=True, encoding='utf-8')
    audit([obj for obj in yaml.safe_load_all(output) if obj])
    (build / 'cilium-rendered.yaml').write_text(output, encoding='utf-8', newline='\n')
    schema_args = []
    if schemas:
        schema_args += ['-schema-location', str(Path(schemas) / '{{.ResourceKind}}.json')]
    for pattern in ('{{.Group}}/{{.ResourceKind}}_{{.ResourceAPIVersion}}.json', '{{.ResourceKind}}_{{.ResourceAPIVersion}}.json'):
        schema_args += ['-schema-location', str(ROOT / 'module-2/schemas' / pattern)]
    schema_args += ['-schema-location', str(ROOT / 'module-4a/schemas/{{.ResourceKind}}_{{.ResourceAPIVersion}}.json')]
    subprocess.run([kubeconform, '-strict', '-summary', *schema_args,
                    *[str(build / f) for f in ('foundation-dns.yaml', 'smoke.yaml', 'cilium-rendered.yaml')]], check=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['render', 'validate', 'check-facts'])
    parser.add_argument('--build', type=Path, default=ROOT / '.build/wsl-lab')
    parser.add_argument('--node-ip', default='192.168.1.9')
    parser.add_argument('--device', default='eth1')
    parser.add_argument('--helm', default='helm')
    parser.add_argument('--kubeconform', default='kubeconform')
    parser.add_argument('--schemas')
    parser.add_argument('--facts', type=Path)
    args = parser.parse_args()
    try:
        if args.action == 'check-facts':
            check_facts(json.loads(args.facts.read_text(encoding='utf-8')), profile())
            print('WSL lab preflight passed')
        elif args.action == 'render':
            render(args.build, args.node_ip, args.device)
        else:
            validate(args.build, args.helm, args.kubeconform, args.schemas)
        return 0
    except (ValueError, OSError, subprocess.CalledProcessError) as error:
        print('WSL lab: ' + str(error), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
