"""Bounded VPA recommendation -> CNPG Cluster resource growth; never patches Pods."""
from datetime import datetime, timezone
from decimal import Decimal, ROUND_CEILING
import json
import os
from pathlib import Path
import re
import ssl
from urllib.request import Request, build_opener, HTTPSHandler, HTTPRedirectHandler


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, response, code, message, headers, url):
        raise ValueError('API redirects are forbidden')


def quantity(value):
    match = re.fullmatch(r'(\d+(?:\.\d+)?)(m|Ki|Mi|Gi|Ti|K|M|G|T)?', str(value))
    if not match:
        raise ValueError('unsupported or negative resource quantity')
    units = {'': 1, 'm': Decimal('.001'), 'Ki': 2**10, 'Mi': 2**20,
             'Gi': 2**30, 'Ti': 2**40, 'K': 10**3, 'M': 10**6, 'G': 10**9, 'T': 10**12}
    return Decimal(match[1]) * units[match[2] or '']


def timestamp(value):
    parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if parsed.tzinfo is None:
        raise ValueError('timestamp requires a timezone')
    return parsed.timestamp()


def plan(cluster, vpa, policy, now):
    name = cluster['metadata']['name']
    target = vpa.get('spec', {}).get('targetRef', {})
    if target != {'apiVersion': 'postgresql.cnpg.io/v1', 'kind': 'Cluster', 'name': name}:
        return None, 'VPA target does not match this Cluster'
    if vpa.get('spec', {}).get('updatePolicy', {}).get('updateMode') != 'Off':
        return None, 'VPA must remain recommendation-only'
    spec, status = cluster['spec'], cluster.get('status', {})
    if (cluster['metadata'].get('deletionTimestamp') or
            spec.get('nodeMaintenanceWindow', {}).get('inProgress') or
            status.get('readyInstances') != spec['instances'] or
            status.get('instances') != spec['instances'] or
            status.get('phase') != 'Cluster in healthy state' or
            not status.get('currentPrimary') or
            status.get('currentPrimary') != status.get('targetPrimary')):
        return None, 'Cluster not fully healthy/stable'
    annotations = cluster['metadata'].get('annotations', {})
    last = annotations.get('vcloud.io/resources-last-scaled')
    if last and now - timestamp(last) < policy['cooldownSeconds']:
        return None, 'cooldown'
    if not any(c.get('type') == 'RecommendationProvided' and c.get('status') == 'True'
               for c in vpa.get('status', {}).get('conditions', [])):
        return None, 'no VPA recommendation'
    times = [timestamp(f['time']) for f in vpa.get('metadata', {}).get('managedFields', [])
             if f.get('subresource') == 'status' and f.get('time')]
    if not times or not 0 <= now - max(times) <= policy['recommendationMaxAgeSeconds']:
        return None, 'stale/unverifiable recommendation'
    recommendations = [r for r in vpa['status'].get('recommendation', {}).get('containerRecommendations', [])
                       if r.get('containerName') == 'postgres']
    if len(recommendations) != 1:
        return None, 'expected one postgres recommendation'
    current = spec['resources']
    if set(current.get('requests', {})) != {'cpu', 'memory'} or current.get('requests') != current.get('limits'):
        return None, 'resource policy requires equal CPU/memory requests and limits'
    wanted = {}
    changed = False
    for resource, low, high in [('cpu', 'minCPU', 'maxCPU'), ('memory', 'minMemory', 'maxMemory')]:
        previous = quantity(current['requests'][resource])
        minimum, maximum = quantity(policy[low]), quantity(policy[high])
        if not 0 < minimum <= previous <= maximum:
            return None, 'current resources outside policy bounds'
        target_value = quantity(recommendations[0]['target'][resource])
        next_value = min(maximum, max(minimum, target_value))
        if not policy.get('allowDecrease', False):
            next_value = max(previous, next_value)
        next_value = min(next_value, previous * 2) # bounded growth per cooldown
        if next_value < previous:
            return None, 'automatic resource reduction requires a separate maintenance policy'
        if next_value / previous < Decimal(str(policy['minChangeRatio'])):
            next_value = previous
        quantum = Decimal('.001') if resource == 'cpu' else Decimal(2**20)
        next_value = (next_value / quantum).to_integral_value(rounding=ROUND_CEILING) * quantum
        if next_value > maximum:
            return None, 'rounded recommendation exceeds maximum'
        changed |= next_value != previous
        wanted[resource] = f'{int(next_value * 1000)}m' if resource == 'cpu' else f'{int(next_value / (2**20))}Mi'
    if not changed:
        return None, 'within bounds/hysteresis'
    if not cluster['metadata'].get('resourceVersion'):
        return None, 'missing optimistic concurrency version'
    updated_annotations = dict(annotations)
    updated_annotations['vcloud.io/resources-last-scaled'] = datetime.fromtimestamp(now, timezone.utc).isoformat()
    patch = [
        {'op': 'test', 'path': '/metadata/resourceVersion', 'value': cluster['metadata']['resourceVersion']},
        {'op': 'test', 'path': '/spec/resources', 'value': current},
        {'op': 'replace', 'path': '/spec/resources', 'value': {'requests': wanted, 'limits': wanted.copy()}},
        {'op': 'add', 'path': '/metadata/annotations', 'value': updated_annotations},
    ]
    return patch, 'bounded resource growth through CNPG'


def main():
    token_dir = Path('/var/run/secrets/kubernetes.io/serviceaccount')
    token = (token_dir / 'token').read_text().strip()
    context = ssl.create_default_context(cafile=str(token_dir / 'ca.crt'))
    opener = build_opener(HTTPSHandler(context=context), NoRedirect())
    host = os.environ['KUBERNETES_SERVICE_HOST']
    if ':' in host:
        host = f'[{host}]'
    base = f'https://{host}:{os.environ.get("KUBERNETES_SERVICE_PORT_HTTPS", "443")}'
    namespace, cluster_name = os.environ['NAMESPACE'], os.environ['CLUSTER_NAME']
    for value in (namespace, cluster_name):
        if not re.fullmatch(r'[a-z0-9][a-z0-9.-]*', value):
            raise ValueError('invalid resource identifier')

    def api(path, payload=None):
        headers = {'Authorization': 'Bearer ' + token, 'Accept': 'application/json'}
        data = None
        if payload is not None:
            headers['Content-Type'] = 'application/json-patch+json'
            data = json.dumps(payload).encode()
        request = Request(base + path, data=data, headers=headers, method='PATCH' if data else 'GET')
        with opener.open(request, timeout=10) as response:
            return json.load(response)

    path = f'/apis/postgresql.cnpg.io/v1/namespaces/{namespace}/clusters/{cluster_name}'
    cluster = api(path)
    vpa = api(f'/apis/autoscaling.k8s.io/v1/namespaces/{namespace}/verticalpodautoscalers/postgres-resources')
    policy = json.loads(Path('/app/policy.json').read_text())
    patch, reason = plan(cluster, vpa, policy, datetime.now(timezone.utc).timestamp())
    if patch:
        api(path, patch) # conflict rejects this run; no blind retry or Pod eviction
    print(json.dumps({'action': 'grow' if patch else 'skip', 'reason': reason}))


if __name__ == '__main__':
    main()
