#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""WO-40a owner-run acceptance. Import and unit tests never contact the dev host."""
from datetime import date, datetime, timezone
import http.client
import ipaddress
import json
import ast
import os
from pathlib import Path
import re
import socket
import ssl
import subprocess
import time

from platform_resources import ROOT
from platform_image_staging import SSH, cri_reference
from platform_host import execute as host_execute

CONTEXT = 'twinfra-dev-cairo-1'
NS = 'twinfra-platform-services'
APPS = ('twinfra-root', 'twinfra-platform', 'twinfra-services')
ARGO = ('argocd-application-controller', 'argocd-repo-server', 'argocd-server')
CONSOLE_HOST = 'console.dev.cairo-1.twinfra.example.com'
LIMIT = 65536

# Tokens travel only on exec stdin, never argv/env. Only status codes return.
TOKEN_PROBE = '''import http.client,json,sys
token=json.load(sys.stdin)['roleless']
cases=[[],[('X-Access-Token','eyJhbGciOiJub25lIn0.eyJyb2xlcyI6WyJjb25zb2xlLmFkbWluIl19.')],
 [('X-Access-Token','first'),('X-Access-Token','second')],[('X-Access-Token',token)]]
statuses=[]
for headers in cases:
 c=http.client.HTTPConnection('127.0.0.1',3000,timeout=10)
 try:
  c.putrequest('GET','/console/api/identity')
  for k,v in headers:c.putheader(k,v)
  c.endheaders();r=c.getresponse();statuses.append(r.status);r.read(65537)
 finally:c.close()
print(json.dumps(statuses))
'''
VALKEY_AUTH = 'exec valkey-cli -e --askpass --no-auth-warning --raw "$@" < /auth/auth'


class ReadOnlyNetwork:
    """Scope the existing host-network check without changing its owner-run behavior."""
    def __init__(self, transport):
        self.transport = transport

    def run(self, command, payload=None):
        if command[:4] != ['sudo', '-n', 'python3', '-'] or json.loads(command[4]).get('action') != 'network-check':
            raise ValueError('Read-only network transport refuses other operations')
        first, rest = payload.decode().split('\n', 1)
        assignment = ast.parse(first).body[0]
        if not isinstance(assignment, ast.Assign) or [n.id for n in assignment.targets] != ['NETWORK_SOURCE']:
            raise ValueError('Unexpected network-check source envelope')
        source = ast.literal_eval(assignment.value)
        # Refuse before entering adoption's lock/write path, including if ownership
        # disappears between checks. No host script or owned file is replaced.
        source += '\ndef adoptable(*args):\n    raise ValueError("Read-only acceptance refuses network adoption")\n'
        return self.transport.run(command, payload=('NETWORK_SOURCE=' + repr(source) + '\n' + rest).encode())


def utc():
    return datetime.now(timezone.utc)


def stamp(value):
    parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if parsed.tzinfo is None:
        raise ValueError('UTC/offset timestamp required')
    return parsed.astimezone(timezone.utc)


def calendar(entries, on):
    """Inclusive boundaries: <=7 days fails, <=21 warns; never omit expired entries."""
    result = []
    for entry in entries:
        days = (date.fromisoformat(entry['expires']) - on).days
        result.append({k: entry[k] for k in ('target', 'package', 'version', 'vulnerability', 'expires')} |
                      {'daysLeft': days, 'status': 'failed' if days <= 7 else 'warning' if days <= 21 else 'passed'})
    return sorted(result, key=lambda row: (row['daysLeft'], row['target'], row['vulnerability'], row['package']))


def private_input(path):
    """Owner supplies session/access tokens outside any Git checkout, never passwords."""
    path = Path(path).absolute()
    if any(p.is_symlink() or (hasattr(p, 'is_junction') and p.is_junction()) for p in (path, *path.parents)):
        raise ValueError('Linked private input refused')
    path = path.resolve()
    if path.is_relative_to(ROOT) or any((p / '.git').exists() for p in path.parents):
        raise ValueError('Private inputs must be outside Git')
    if not path.is_file() or path.stat().st_size > LIMIT:
        raise ValueError('Missing or oversized private input')
    if os.name != 'nt' and (path.stat().st_mode & 0o077 or path.stat().st_uid != os.geteuid()):
        raise ValueError('Private input must be owner-only (0600)')
    text = path.read_text(encoding='utf-8').strip()
    if not text or '\r' in text or '\n' in text:
        raise ValueError('Private input must be one nonempty line')
    return text


def console_health(ca, cookie):
    if not re.fullmatch(r'twinfra_portal=[^;\s]+', cookie):
        raise ValueError('Supply only the twinfra_portal cookie')
    addresses = socket.getaddrinfo(CONSOLE_HOST, 18444, type=socket.SOCK_STREAM)
    if not addresses or any(not ipaddress.ip_address(a[4][0]).is_loopback for a in addresses):
        raise ValueError('Console tunnel must resolve exclusively to laptop loopback')
    connection = http.client.HTTPSConnection(CONSOLE_HOST, 18444, timeout=10,
                                            context=ssl.create_default_context(cafile=str(ca)))
    try:
        # Identity is the existing authenticated BFF health/read path through APISIX.
        # No new route, browser login, redirect or TLS bypass is introduced.
        connection.request('GET', '/console/api/identity', headers={'Cookie': cookie})
        response = connection.getresponse()
        raw = response.read(LIMIT + 1)
        return response.status == 200 and len(raw) <= LIMIT and json.loads(raw).get('environment') == 'dev'
    finally:
        connection.close()


class Client:
    def __init__(self, context, runner=subprocess.run):
        if context != CONTEXT:
            raise ValueError('Explicit twinfra-dev-cairo-1 context required')
        self.context, self.runner = context, runner

    def call(self, *args, payload=None):
        remaining = getattr(self, 'deadline', None)
        timeout = min(45, remaining - time.monotonic()) if remaining is not None else 45
        if timeout <= 0:
            raise ValueError('Kubernetes acceptance deadline elapsed')
        result = self.runner(['kubectl', '--context', self.context, '--request-timeout=30s', *args],
                             input=payload, capture_output=True, timeout=timeout)
        if result.returncode:
            # stderr/stdout can include upstream credentials. Never reflect them.
            raise ValueError('Kubernetes acceptance operation failed')
        return result.stdout.decode('utf-8')

    def get(self, kind, *args):
        return json.loads(self.call('get', kind, *args, '-o', 'json'))

    def exec(self, pod, container, *command, payload=None):
        return self.call('-n', NS, 'exec', '-i', pod['metadata']['name'], '-c', container, '--',
                         *command, payload=payload)


def pods_by_name(pods, name):
    return [p for p in pods if p['metadata'].get('namespace') == NS and
            p['metadata'].get('labels', {}).get('app.kubernetes.io/name') == name and
            not p['metadata'].get('deletionTimestamp')]


def one_pod(pods, name):
    values = pods_by_name(pods, name)
    if len(values) != 1 or values[0].get('status', {}).get('phase') != 'Running':
        raise ValueError('Expected one Running workload: ' + name)
    return values[0]


def ready(pod):
    return any(c['type'] == 'Ready' and c['status'] == 'True' for c in pod.get('status', {}).get('conditions', []))


def snapshot(pods):
    return {p['metadata']['uid']: {c['name']: c.get('restartCount', 0)
            for field in ('containerStatuses', 'initContainerStatuses', 'ephemeralContainerStatuses')
            for c in p.get('status', {}).get(field, [])} for p in pods}


def pod_problems(pods, since, before=None, replaced=None, allowed_new=None):
    errors = []
    if not pods:
        return ['No pods returned']
    for pod in pods:
        label = pod['metadata'].get('namespace', '') + '/' + pod['metadata']['name']
        if pod.get('status', {}).get('phase') != 'Running' or pod['metadata'].get('deletionTimestamp'):
            errors.append(label + ': not Running')
        created = pod['metadata'].get('creationTimestamp')
        if created and stamp(created) >= since and pod['metadata']['uid'] != allowed_new:
            errors.append(label + ': created/replaced since acceptance start')
        for field in ('containerStatuses', 'initContainerStatuses', 'ephemeralContainerStatuses'):
            for status in pod.get('status', {}).get(field, []):
                ended = status.get('lastState', {}).get('terminated', {}).get('finishedAt')
                if ended and stamp(ended) >= since:
                    errors.append(label + ': restarted since acceptance start')
    if before is not None:
        after = snapshot(pods)
        if {k: v for k, v in before.items() if k != replaced} != {
                k: v for k, v in after.items() if not replaced or k in before}:
            errors.append('Pod UID/restart counters changed during acceptance')
        if replaced and len(set(after) - set(before)) != 1:
            errors.append('Expected exactly one owner-authorized cache replacement')
    return errors


def application_problems(apps, revision, after=None):
    errors = []
    for name in APPS:
        matches = [a for a in apps if a['metadata']['name'] == name]
        if len(matches) != 1:
            errors.append(name + ': missing/ambiguous')
            continue
        status = matches[0].get('status', {})
        if (status.get('sync', {}).get('status'), status.get('health', {}).get('status'),
                status.get('sync', {}).get('revision')) != ('Synced', 'Healthy', revision):
            errors.append(name + ': not Synced/Healthy at expected commit')
        if after and (not status.get('reconciledAt') or stamp(status['reconciledAt']) <= after):
            errors.append(name + ': no fresh reconciliation after cache restart')
    return errors


def runtime_reference(value):
    ref = value.removeprefix('containerd://').removeprefix('docker-pullable://')
    if not re.fullmatch(r'(?:[a-zA-Z0-9][a-zA-Z0-9._:/-]*@)?sha256:[a-f0-9]{64}', ref):
        raise ValueError('Invalid containerd runtime image reference')
    return ref


def image_problems(pods, lock, cri_ids):
    allowed = {cri_reference(e['canonical']): e['digest'] for e in lock['images'].values()}
    errors, observed = [], []
    for pod in pods:
        for field in ('containers', 'initContainers', 'ephemeralContainers'):
            statuses = {s['name']: s for s in pod.get('status', {}).get(field.replace('Containers', 'ContainerStatuses')
                        if field != 'containers' else 'containerStatuses', [])}
            for container in pod.get('spec', {}).get(field, []):
                ref = cri_reference(container['image'])
                # Tag-only kubeadm/containerd names are admitted only as exact bootstrap canonicals.
                digest = allowed.get(ref)
                status = statuses.get(container['name'], {})
                actual = status.get('imageID', '')
                if not digest or not actual:
                    errors.append(pod['metadata']['name'] + '/' + container['name'] + ': unverified image')
                else:
                    # CRI imageID can be the config ID. Bind it to inspecti's ID for this
                    # exact staged manifest, rather than accepting any sha256-shaped value.
                    try:
                        reported = runtime_reference(actual)
                    except ValueError:
                        errors.append(pod['metadata']['name'] + ': malformed runtime image ID')
                    else:
                        if (reported.rsplit('@', 1)[-1] not in (digest, cri_ids.get(ref)) and
                                (not cri_ids.get(ref) or cri_ids.get(reported) != cri_ids[ref])):
                            errors.append(pod['metadata']['name'] + ': runtime image digest/CRI ID mismatch')
                    observed.append({'pod': pod['metadata']['name'], 'container': container['name'],
                                     'reference': ref, 'manifestDigest': digest, 'runtimeImageID': actual})
    return errors, observed


def valkey(client, pods):
    cache = one_pod(pods, 'argocd-redis')
    container = cache['spec']['containers'][0]['name']
    noauth = client.exec(cache, container, 'valkey-cli', '--raw', 'PING').strip()
    pong = client.exec(cache, container, 'sh', '-ec', VALKEY_AUTH, '--', 'PING').strip().splitlines()
    clients = client.exec(cache, container, 'sh', '-ec', VALKEY_AUTH, '--', 'CLIENT', 'LIST')
    addresses = set(re.findall(r'(?:^|\s)addr=([^\s]+)', clients))
    connected = {name: any(addr.rsplit(':', 1)[0] == one_pod(pods, name)['status']['podIP']
                           for addr in addresses) for name in ARGO}
    return {'noAuthRejected': noauth.startswith('NOAUTH'), 'authenticatedPong': bool(pong and pong[-1] == 'PONG'),
            'argoClientsConnected': connected}


def versions(client, pods, node):
    result = {'kubernetes': node['status']['nodeInfo']['kubeletVersion'],
              'containerd': node['status']['nodeInfo']['containerRuntimeVersion']}
    commands = {'cilium': ('k8s-app', 'cilium', 'cilium-agent', ['cilium-dbg', 'version']),
                'etcd': ('component', 'etcd', 'etcd', ['etcd', '--version']),
                'coredns': ('k8s-app', 'kube-dns', 'coredns', ['/coredns', '-version']),
                'argocd': ('app.kubernetes.io/name', 'argocd-server', 'argocd-server', ['argocd', 'version', '--client', '--short']),
                'cnpg': ('app.kubernetes.io/name', 'cloudnative-pg', 'manager', ['/manager', 'version']),
                'postgresql': ('cnpg.io/cluster', 'twinfra-postgres', 'postgres', ['postgres', '--version']),
                'keycloak': ('app.kubernetes.io/name', 'twinfra-keycloak', 'keycloak', ['/opt/keycloak/bin/kc.sh', '--version']),
                'openbao': ('app.kubernetes.io/name', 'twinfra-openbao', 'openbao', ['bao', 'version']),
                'valkey': ('app.kubernetes.io/name', 'argocd-redis', 'redis', ['valkey-server', '--version'])}
    for key, (label, name, container, command) in commands.items():
        matches = [p for p in pods if p['metadata'].get('labels', {}).get(label) == name]
        if len(matches) != 1:
            raise ValueError('Version workload missing/ambiguous: ' + key)
        pod = matches[0]
        # System components are outside NS; no credentials on argv.
        raw = client.call('-n', pod['metadata']['namespace'], 'exec', pod['metadata']['name'], '-c', container, '--', *command)
        if not raw.strip() or len(raw) > 4096:
            raise ValueError('Invalid version response: ' + key)
        result[key] = raw.strip()
    console = one_pod(pods, 'twinfra-console')
    result['console'] = {'image': console['spec']['containers'][0]['image'],
                         'versioning': 'Content-addressed image; no embedded release-version claim'}
    return result


def accept(args, *, client=None, transport=None, host=host_execute, health=console_health,
           now=utc, sleeper=time.sleep):
    start = now()
    report = {'workOrder': 'WO-40a', 'environment': CONTEXT, 'startedAt': start.isoformat(),
              'expectedRevision': args.expected_revision, 'status': 'failed', 'testerSignOff': 'Pending', 'checks': {}}

    def check(name, ok, details=None):
        report['checks'][name] = {'status': 'passed' if ok else 'failed'}
        if details is not None:
            report['checks'][name]['details'] = details

    try:
        entries = json.loads((ROOT / 'security/vulnerability-exceptions.json').read_text())['exceptions']
        report['exceptionCalendar'] = calendar(entries, start.date())
        check('exceptionCalendar', all(e['status'] != 'failed' for e in report['exceptionCalendar']))
        if args.context != CONTEXT or not re.fullmatch(r'[a-f0-9]{40}', args.expected_revision or ''):
            raise ValueError('Explicit dev context and immutable expected commit required')
        if not 1 <= args.timeout <= 900:
            raise ValueError('Timeout must be between 1 and 900 seconds')
        since = stamp(args.since) if args.since else start
        if since > start:
            raise ValueError('Acceptance start cannot be in the future')
        report['since'] = since.isoformat()
        cookie, token = private_input(args.session_file), private_input(args.roleless_token_file)
        if not re.fullmatch(r'[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+', token):
            raise ValueError('Owner roleless access-token input must be a compact signed JWT')
        client, transport = client or Client(args.context), transport or SSH(args.ssh, args.context)
        nodes = client.get('nodes')['items']
        if len(nodes) != 1 or nodes[0]['metadata']['name'] != CONTEXT:
            raise ValueError('Acceptance targets exactly the approved single node')
        node = nodes[0]
        labels = node['metadata'].get('labels', {})
        check('node', ready(node) and any(a['type'] == 'InternalIP' and a['address'] == '192.168.1.3'
              for a in node['status'].get('addresses', [])) and all(labels.get(k) == v for k, v in {
            'topology.kubernetes.io/zone': 'cairo-1a', 'twinfra.io/environment': 'dev', 'twinfra.io/region': 'cairo-1'}.items()))
        pods = client.get('pods', '--all-namespaces')['items']
        before = snapshot(pods)
        problems = pod_problems(pods, since)
        check('podsInitial', not problems, problems)
        apps = client.get('applications.argoproj.io', '-n', NS)['items']
        problems = application_problems(apps, args.expected_revision)
        check('gitops', not problems, problems)
        for action in ('host-check', 'host-network'):
            value = host(action, ReadOnlyNetwork(transport) if action == 'host-network' else transport, check=True)
            check(action, value.get('status') == 'passed')
        merged = {'images': {}}
        for name in ('images.lock.json', 'bootstrap-images.lock.json'):
            lock = json.loads((ROOT / 'deploy/common' / name).read_text(encoding='utf-8'))
            check('staging:' + name, transport.agent(lock, check=True).get('status') == 'passed')
            merged['images'].update({name + ':' + key: value for key, value in lock['images'].items()})
        cri_ids = {}
        for entry in merged['images'].values():
            ref = cri_reference(entry['canonical'])
            info = json.loads(transport.run(['sudo', '-n', 'crictl', 'inspecti', ref]))['status']
            if not any(d.endswith('@' + entry['digest']) for d in info.get('repoDigests', [])):
                raise ValueError('CRI manifest identity differs from lock')
            cri_ids[ref] = info['id']
        for pod in pods:
            for field in ('containerStatuses', 'initContainerStatuses', 'ephemeralContainerStatuses'):
                for status in pod.get('status', {}).get(field, []):
                    ref = runtime_reference(status.get('imageID', ''))
                    if ref not in cri_ids and ref not in cri_ids.values():
                        # Some runtimes expose an index's platform-manifest reference.
                        # Resolve it via CRI and compare its config ID to the admitted parent.
                        cri_ids[ref] = json.loads(transport.run(['sudo', '-n', 'crictl', 'inspecti', ref]))['status']['id']
        problems, observed = image_problems(pods, merged, cri_ids)
        check('deployedImages', not problems, {'problems': problems, 'images': observed})
        check('consoleHTTPS', health(args.ca_file, cookie))
        console = one_pod(pods, 'twinfra-console')
        statuses = json.loads(client.exec(console, 'console', 'python', '-c', TOKEN_PROBE,
                                          payload=json.dumps({'roleless': token}).encode()))
        check('tokenNegatives', statuses == [401, 401, 401, 403], {'missing': statuses[0],
              'unsigned': statuses[1], 'duplicate': statuses[2], 'roleless': statuses[3]})
        cache = valkey(client, pods)
        check('valkey', cache['noAuthRejected'] and cache['authenticatedPong'] and all(cache['argoClientsConnected'].values()), cache)
        report['versions'] = versions(client, pods, node)
        replaced = None
        if args.with_restart:
            if any(c['status'] == 'failed' for c in report['checks'].values()):
                raise ValueError('Cache restart refused because pre-restart acceptance failed')
            cache_pod = one_pod(pods, 'argocd-redis')
            replaced = cache_pod['metadata']['uid']
            restarted = now()
            # Sole mutation, explicitly requested by the owner; never a rollout/config patch.
            client.call('-n', NS, 'delete', 'pod', cache_pod['metadata']['name'], '--wait=false')
            reconnect = False
            client.deadline = time.monotonic() + args.timeout
            for _ in range(max(1, args.timeout // 5)):
                if time.monotonic() >= client.deadline:
                    break
                sleeper(min(5, max(0, client.deadline - time.monotonic())))
                current = client.get('pods', '--all-namespaces')['items']
                try:
                    new = one_pod(current, 'argocd-redis')
                    current_apps = client.get('applications.argoproj.io', '-n', NS)['items']
                    state = valkey(client, current)
                    reconnect = (new['metadata']['uid'] != replaced and ready(new) and
                                 all(ready(one_pod(current, n)) for n in ARGO) and
                                 not application_problems(current_apps, args.expected_revision, restarted) and
                                 state['noAuthRejected'] and state['authenticatedPong'] and all(state['argoClientsConnected'].values()))
                    if reconnect:
                        break
                except ValueError:
                    pass
            client.deadline = None
            check('valkeyRestart', reconnect)
        else:
            report['checks']['valkeyRestart'] = {'status': 'pending', 'details': 'Owner must run --with-restart to prove reconnect'}
        final_pods = client.get('pods', '--all-namespaces')['items']
        allowed_new = one_pod(final_pods, 'argocd-redis')['metadata']['uid'] if replaced else None
        problems = pod_problems(final_pods, since, before, replaced, allowed_new)
        check('podsFinal', not problems, problems)
        problems, observed = image_problems(final_pods, merged, cri_ids)
        check('deployedImagesFinal', not problems, {'problems': problems, 'images': observed})
        final_apps = client.get('applications.argoproj.io', '-n', NS)['items']
        problems = application_problems(final_apps, args.expected_revision)
        check('gitopsFinal', not problems, problems)
        statuses = {c['status'] for c in report['checks'].values()}
        report['status'] = 'failed' if 'failed' in statuses else 'incomplete' if 'pending' in statuses else 'passed'
    except (ValueError, OSError, KeyError, IndexError, TypeError, AttributeError, subprocess.SubprocessError, http.client.HTTPException):
        # Never serialize exceptions, response bodies, tokens, cookies or subprocess output.
        report['error'] = 'Acceptance could not complete; verify prerequisites and sanitized check results.'
    report['finishedAt'] = now().isoformat()
    report['warnings'] = sum(e['status'] == 'warning' for e in report.get('exceptionCalendar', []))
    return report


def fragment_path(path):
    path = Path(path).absolute()
    if not path.resolve().is_relative_to(ROOT / '.build') or path.exists():
        raise ValueError('Receipt fragments must stay under .build; never overwrite signed receipts')
    return path


def write_fragment(path, report):
    path = fragment_path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x', encoding='utf-8') as stream:
        json.dump(report, stream, indent=2)
        stream.write('\n')
