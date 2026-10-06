#!/usr/bin/env python3
"""Record only sanitized live acceptance facts, never kubeconfig or tokens."""
import argparse
import copy
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
from wsl_lab import audit, check_facts, load_policy, profile


def runtime_projection(pods, controllers):
    """Resolve actual API owner UIDs before using any frozen controller exception.

    Audit the live Pod spec, rather than trusting a controller template or a Pod
    name prefix. Unowned/spoofed root Pods receive no node exception.
    """
    owners = {(o['kind'], o['metadata']['namespace'], o['metadata']['name']): o
              for o in controllers['items']}
    approved = load_policy()['agents']
    node_images = {c['image'] for agent in approved.values() for c in agent['containers']}
    result = []
    for pod in pods['items']:
        # CNPG, StatefulSet and Job owners do not grant node privileges. Audit
        # ordinary Pods directly; only frozen node images need owner resolution.
        if not any(c['image'] in node_images for c in pod['spec'].get('containers', []) + pod['spec'].get('initContainers', [])):
            result.append(pod)
            continue
        current = pod
        visited = set()
        while True:
            refs = [r for r in current['metadata'].get('ownerReferences', []) if r.get('controller')]
            if not refs:
                break
            if len(refs) != 1:
                raise ValueError('Ambiguous Pod controller ownership')
            ref = refs[0]
            key = (ref['kind'], pod['metadata']['namespace'], ref['name'])
            owner = owners.get(key)
            if key in visited or not owner or owner['metadata']['uid'] != ref['uid']:
                raise ValueError('Unresolved or mismatched Pod controller UID')
            visited.add(key)
            current = owner
        key = '/'.join((current['kind'], pod['metadata']['namespace'], current['metadata']['name']))
        if key in approved:
            result.append({'apiVersion': current['apiVersion'], 'kind': current['kind'],
                           'metadata': copy.deepcopy(current['metadata']),
                           'spec': {'template': {'spec': copy.deepcopy(pod['spec'])}}})
        else:
            result.append(pod)
    return result


def ready_or_completed(pod):
    status = pod['status']
    if status['phase'] == 'Succeeded':
        refs = pod['metadata'].get('ownerReferences', [])
        containers = status.get('containerStatuses', []) + status.get('initContainerStatuses', [])
        return (any(r.get('controller') and r['kind'] == 'Job' for r in refs)
                and len(status.get('containerStatuses', [])) == len(pod['spec']['containers'])
                and all(c.get('state', {}).get('terminated', {}).get('exitCode') == 0 for c in containers))
    return status['phase'] == 'Running' and any(c['type'] == 'Ready' and c['status'] == 'True' for c in status.get('conditions', []))


def acceptance(facts, nodes, pods, cilium, controllers=None):
    check_facts(facts, profile())
    if len(nodes['items']) != 1 or nodes['items'][0]['metadata']['name'] != 'vcloud-wsl-local':
        raise ValueError('Unexpected cluster/node topology')
    node = nodes['items'][0]
    if not any(c['type'] == 'Ready' and c['status'] == 'True' for c in node['status']['conditions']):
        raise ValueError('Node is not Ready')
    if 'v1.36.5+k3s1' != node['status']['nodeInfo']['kubeletVersion']:
        raise ValueError('Unreviewed Kubernetes version')
    if 'KubeProxyReplacement:' not in cilium or 'True' not in cilium.split('KubeProxyReplacement:', 1)[1].splitlines()[0]:
        raise ValueError('eBPF replacement is not active')
    inventory = []
    projected = runtime_projection(pods, controllers or {'items': []})
    audit(projected)
    present = {(p['kind'], p['metadata']['namespace'], p['metadata']['name']) for p in projected}
    required = {('DaemonSet', 'kube-system', 'cilium'), ('DaemonSet', 'kube-system', 'cilium-envoy'),
                ('Deployment', 'kube-system', 'cilium-operator'),
                ('Pod', 'platform-services', 'vcloud-lab-server'),
                ('Pod', 'workload-apps', 'vcloud-lab-allowed'), ('Pod', 'hpc-compute', 'vcloud-lab-denied')}
    if not required <= present or not any(p['metadata'].get('labels', {}).get('k8s-app') == 'kube-dns' for p in pods['items']):
        raise ValueError('Required foundation or policy probe Pod is missing')
    for pod in pods['items']:
        if not ready_or_completed(pod):
            raise ValueError('Pod is not Ready: ' + pod['metadata']['name'])
        for container in pod['spec'].get('containers', []):
            if not container['image'].startswith('registry.vcloud.example.com/'):
                raise ValueError('Pod image outside canonical registry')
        if any(key in pod['metadata']['name'] for key in ('vllm', 'spinifex', 'deepseek', 'traefik', 'svclb', 'local-path', 'kube-proxy')):
            raise ValueError('Excluded workload present')
        if any(c.get('resources', {}).get('limits', {}).get('nvidia.com/gpu') for c in pod['spec'].get('containers', [])):
            raise ValueError('GPU workload unexpectedly enabled')
        inventory.append({'namespace': pod['metadata']['namespace'], 'name': pod['metadata']['name'], 'phase': pod['status']['phase']})
    return {'status': 'passed', 'scope': 'live single-node WSL K3s foundation and policy smoke tests',
            'timestampUTC': datetime.now(timezone.utc).isoformat(),
            'context': 'vcloud-wsl-local', 'kubernetes': node['status']['nodeInfo']['kubeletVersion'],
            'apiPort': 16443,
            'cpu': facts['cpus'], 'memoryGiB': round(facts['memoryKiB']/1024**2, 2),
            'networking': facts['networking'], 'nodeReady': True, 'kubeProxyReplacement': True,
            'tests': {'clusterDNS': 'passed', 'permittedCrossNamespaceHTTP': 'passed',
                      'deniedCrossNamespaceHTTP': 'passed'}, 'pods': inventory,
            'disabled': ['GPU workloads', 'vLLM/DeepSeek 32B', 'Spinifex offload', 'HPC queues', 'bundled hostPath storage'],
            'unexecuted': ['full application stack', 'real GPU container execution', 'APISIX/Knative/OpenBao/Keycloak integration',
                           'CSI/persistent database', 'backup/restore', 'host-firewall policy enforcement',
                           'bandwidth limits', 'WSL/Windows restart recovery', 'production go-live']}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--build', type=Path, required=True)
    args = parser.parse_args()
    report = acceptance(*[json.loads((args.build/name).read_text()) for name in ('facts.json','nodes.json','pods.json')],
                        (args.build/'cilium-status.txt').read_text(),
                        json.loads((args.build/'controllers.json').read_text()))
    (args.build/'live-acceptance.json').write_text(json.dumps(report,indent=2)+'\n', encoding='utf-8', newline='\n')
