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
from platform_host import execute as host_execute, expected as host_expected

CONTEXT = 'twinfra-dev-cairo-1'
NS = 'twinfra-platform-services'
APPS = ('twinfra-root', 'twinfra-platform', 'twinfra-services')
ARGO = ('argocd-application-controller', 'argocd-repo-server', 'argocd-server')
CONSOLE_HOST = 'console.dev.cairo-1.twinfra.example.com'
LIMIT = 65536
NAME_LABEL = 'app.kubernetes.io/name'
APPLICATION_RESOURCE = 'applications.argoproj.io'
STATUS_FIELDS = ('containerStatuses', 'initContainerStatuses', 'ephemeralContainerStatuses')

# Tokens travel only on exec stdin, never argv/env. Only status codes return.
TOKEN_PROBE = '''import base64,http.client,json,os,sys,time
token=json.load(sys.stdin)['roleless']
def b64(value):return base64.urlsafe_b64encode(json.dumps(value).encode()).decode().rstrip('=')
head=token.split('.')[0]
kid=json.loads(base64.urlsafe_b64decode(head+'='*(-len(head)%4))).get('kid','unsigned-probe')
claims={'iss':os.environ['OIDC_ISSUER'],'aud':os.environ['OIDC_CLIENT'],'azp':os.environ['OIDC_CLIENT'],
 'sub':'wo40-unsigned-probe','iat':int(time.time())-30,'nbf':int(time.time())-30,'exp':int(time.time())+300,
 'resource_access':{os.environ['OIDC_CLIENT']:{'roles':['console.admin']}}}
unsigned=b64({'alg':'none','kid':kid})+'.'+b64(claims)+'.dW5zaWduZWQ'
cases=[[],[('X-Access-Token',unsigned)],
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
        status = 'passed'
        if days <= 7:
            status = 'failed'
        elif days <= 21:
            status = 'warning'
        result.append({k: entry[k] for k in ('target', 'package', 'version', 'vulnerability', 'expires')} |
                      {'daysLeft': days, 'status': status})
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
    context = ssl.create_default_context(cafile=str(ca))
    context.verify_mode = ssl.CERT_REQUIRED
    context.check_hostname = True
    connection = http.client.HTTPSConnection(CONSOLE_HOST, 18444, timeout=10, context=context)
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
            p['metadata'].get('labels', {}).get(NAME_LABEL) == name and
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
            for field in STATUS_FIELDS
            for c in p.get('status', {}).get(field, [])} for p in pods}


def container_statuses(pod):
    return [status for field in STATUS_FIELDS for status in pod.get('status', {}).get(field, [])]


def pod_state_problems(pod, since, allowed_new):
    errors = []
    label = pod['metadata'].get('namespace', '') + '/' + pod['metadata']['name']
    if pod.get('status', {}).get('phase') != 'Running' or pod['metadata'].get('deletionTimestamp'):
        errors.append(label + ': not Running')
    created = pod['metadata'].get('creationTimestamp')
    if created and stamp(created) >= since and pod['metadata']['uid'] != allowed_new:
        errors.append(label + ': created/replaced since acceptance start')
    for status in container_statuses(pod):
        ended = status.get('lastState', {}).get('terminated', {}).get('finishedAt')
        if ended and stamp(ended) >= since:
            errors.append(label + ': restarted since acceptance start')
    return errors


def pod_problems(pods, since, before=None, replaced=None, allowed_new=None):
    errors = []
    if not pods:
        return ['No pods returned']
    for pod in pods:
        errors.extend(pod_state_problems(pod, since, allowed_new))
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


def container_images(pods):
    fields = (('containers', 'containerStatuses'), ('initContainers', 'initContainerStatuses'),
              ('ephemeralContainers', 'ephemeralContainerStatuses'))
    for pod in pods:
        for field, status_field in fields:
            statuses = {s['name']: s for s in pod.get('status', {}).get(status_field, [])}
            for container in pod.get('spec', {}).get(field, []):
                yield pod, container, statuses.get(container['name'], {})


def runtime_matches(actual, digest, cri_ids, ref):
    reported = runtime_reference(actual)
    if reported.rsplit('@', 1)[-1] in (digest, cri_ids.get(ref)):
        return True
    return bool(cri_ids.get(ref) and cri_ids.get(reported) == cri_ids[ref])


def image_problems(pods, lock, cri_ids):
    allowed = {cri_reference(e['canonical']): e['digest'] for e in lock['images'].values()}
    errors, observed = [], []
    for pod, container, status in container_images(pods):
        ref = cri_reference(container['image'])
        digest, actual = allowed.get(ref), status.get('imageID', '')
        label = pod['metadata']['name'] + '/' + container['name']
        if not digest or not actual:
            errors.append(label + ': unverified image')
            continue
        try:
            reported = runtime_reference(actual)
            if ref in cri_ids and cri_ids[ref] is None:
                errors.append(label + ': canonical CRI identity unavailable or differs from lock')
            elif reported.rsplit('@', 1)[-1] != digest and reported in cri_ids and cri_ids[reported] is None:
                errors.append(label + ': runtime CRI identity lookup failed')
            elif not runtime_matches(actual, digest, cri_ids, ref):
                errors.append(label + ': runtime image digest/CRI ID mismatch')
        except ValueError:
            errors.append(label + ': malformed runtime image ID')
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


def replica_version(client, pods, label, name, container, command):
    values = []
    for pod in pods:
        if (pod['metadata'].get('labels', {}).get(label) != name or not ready(pod) or
                pod['metadata'].get('deletionTimestamp')):
            continue
        try:
            # System components are outside NS; no credentials on argv.
            raw = client.call('-n', pod['metadata']['namespace'], 'exec', pod['metadata']['name'], '-c', container, '--', *command)
            version = re.search(r'\bv?(\d+\.\d+(?:\.\d+)?(?:-(?:alpha|beta|rc)\.?\d+)?)\b', raw)
            if not version or len(raw) > 4096:
                raise ValueError('Invalid version response')
            values.append(version[1])  # Only the version, never command output.
        except (ValueError, OSError, KeyError, TypeError, AttributeError, subprocess.SubprocessError):
            values.append(None)  # Still query every other Ready replica.
    return values[0] if values and None not in values and len(set(values)) == 1 else None


def versions(client, pods, node):
    problems = []
    result = {'kubernetes': node['status']['nodeInfo']['kubeletVersion'],
              'containerd': node['status']['nodeInfo']['containerRuntimeVersion']}
    commands = {'cilium': ('k8s-app', 'cilium', 'cilium-agent', ['cilium-dbg', 'version']),
                'etcd': ('component', 'etcd', 'etcd', ['etcd', '--version']),
                'coredns': ('k8s-app', 'kube-dns', 'coredns', ['/coredns', '-version']),
                'argocd': (NAME_LABEL, 'argocd-server', 'argocd-server', ['argocd', 'version', '--client', '--short']),
                'cnpg': (NAME_LABEL, 'cloudnative-pg', 'manager', ['/manager', 'version']),
                'postgresql': ('cnpg.io/cluster', 'twinfra-postgres', 'postgres', ['postgres', '--version']),
                'keycloak': (NAME_LABEL, 'twinfra-keycloak', 'keycloak', ['/opt/keycloak/bin/kc.sh', '--version']),
                'openbao': (NAME_LABEL, 'twinfra-openbao', 'openbao', ['bao', 'version']),
                'valkey': (NAME_LABEL, 'argocd-redis', 'redis', ['valkey-server', '--version'])}
    for key, (label, name, container, command) in commands.items():
        version = replica_version(client, pods, label, name, container, command)
        if version is None:
            problems.append(key + ': Ready-pod versions unavailable or unequal')
        else:
            result[key] = version
    console = one_pod(pods, 'twinfra-console')
    result['console'] = {'image': console['spec']['containers'][0]['image'],
                         'versioning': 'Content-addressed image; no embedded release-version claim'}
    return result, problems


def cri_identity(transport, ref, digest=None):
    try:
        info = json.loads(transport.run(['sudo', '-n', 'crictl', 'inspecti', ref]))['status']
        if digest and not any(d.endswith('@' + digest) for d in info.get('repoDigests', [])):
            return None
        identity = info['id']
        if not isinstance(identity, str) or not re.fullmatch(r'sha256:[a-f0-9]{64}', identity):
            return None
        return identity
    except (ValueError, OSError, KeyError, TypeError, AttributeError, subprocess.SubprocessError):
        # A failed lookup is evidence of an unverified image, never a reason to
        # abort or serialize command/exception output into the receipt.
        return None


def cri_identities(transport, lock, pods):
    identities = {}
    allowed = {}
    for entry in lock['images'].values():
        ref = cri_reference(entry['canonical'])
        allowed[ref] = entry['digest']
        identities[ref] = cri_identity(transport, ref, entry['digest'])
    for _, container, status in container_images(pods):
        canonical = cri_reference(container['image'])
        digest = allowed.get(canonical)
        if not digest:
            continue  # image_problems reports unlocked container references.
        try:
            ref = runtime_reference(status.get('imageID', ''))
        except ValueError:
            continue  # image_problems reports missing/malformed runtime IDs.
        if ref.rsplit('@', 1)[-1] == digest:
            continue  # A matching manifest digest needs no temporary-name lookup.
        if ref not in identities and ref not in identities.values():
            identities[ref] = cri_identity(transport, ref)
    return identities


def cache_ok(state):
    return state['noAuthRejected'] and state['authenticatedPong'] and all(state['argoClientsConnected'].values())


def normalized_lock(lock):
    """Same tag-to-digest input normalization as stage_applications --check."""
    for entry in lock['images'].values():
        source, digest = entry['source'], entry['digest']
        if '@' in source and source.rsplit('@', 1)[1] != digest:
            raise ValueError('Upstream source differs from the locked digest')
        entry['source'] = cri_reference(source if '@' in source else source + '@' + digest)
    return lock


def completion_status(checks):
    statuses = {c['status'] for c in checks.values()}
    if 'failed' in statuses:
        return 'failed'
    if 'pending' in statuses:
        return 'incomplete'
    return 'passed'


class AcceptanceRun:
    def __init__(self, args, client, transport, host, health, now, sleeper):
        self.args, self.client, self.transport = args, client, transport
        self.host, self.health, self.now, self.sleeper = host, health, now, sleeper
        self.start = now()
        self.replaced = None
        self.report = {'workOrder': 'WO-40a', 'environment': CONTEXT, 'startedAt': self.start.isoformat(),
                       'expectedRevision': args.expected_revision, 'status': 'failed',
                       'testerSignOff': 'Pending', 'checks': {}}

    def check(self, name, ok, details=None):
        self.report['checks'][name] = {'status': 'passed' if ok else 'failed'}
        if details is not None:
            self.report['checks'][name]['details'] = details

    def initialize(self):
        entries = json.loads((ROOT / 'security/vulnerability-exceptions.json').read_text())['exceptions']
        self.report['exceptionCalendar'] = calendar(entries, self.start.date())
        self.check('exceptionCalendar', all(e['status'] != 'failed' for e in self.report['exceptionCalendar']))
        args = self.args
        if args.context != CONTEXT or not re.fullmatch(r'[a-f0-9]{40}', args.expected_revision or ''):
            raise ValueError('Explicit dev context and immutable expected commit required')
        if not 1 <= args.timeout <= 900:
            raise ValueError('Timeout must be between 1 and 900 seconds')
        self.since = stamp(args.since) if args.since else self.start
        if self.since > self.start:
            raise ValueError('Acceptance start cannot be in the future')
        self.report['since'] = self.since.isoformat()
        self.cookie = private_input(args.session_file)
        self.token = private_input(args.roleless_token_file)
        if not re.fullmatch(r'[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+', self.token):
            raise ValueError('Owner roleless access-token input must be a compact signed JWT')
        self.client = self.client or Client(args.context)
        self.transport = self.transport or SSH(args.ssh, args.context)

    def applications(self):
        return self.client.get(APPLICATION_RESOURCE, '-n', NS)['items']

    def cluster(self):
        nodes = self.client.get('nodes')['items']
        if len(nodes) != 1 or nodes[0]['metadata']['name'] != CONTEXT:
            raise ValueError('Acceptance targets exactly the approved single node')
        self.node = nodes[0]
        labels = self.node['metadata'].get('labels', {})
        expected_ip = host_expected()['ip']
        correct_ip = any(a['type'] == 'InternalIP' and a['address'] == expected_ip
                         for a in self.node['status'].get('addresses', []))
        correct_labels = all(labels.get(k) == v for k, v in {
            'topology.kubernetes.io/zone': 'cairo-1a', 'twinfra.io/environment': 'dev',
            'twinfra.io/region': 'cairo-1'}.items())
        self.check('node', ready(self.node) and correct_ip and correct_labels)
        self.pods = self.client.get('pods', '--all-namespaces')['items']
        self.before = snapshot(self.pods)
        self.report['podSnapshots'] = {'initial': self.before}
        problems = pod_problems(self.pods, self.since)
        self.check('podsInitial', not problems, problems)
        problems = application_problems(self.applications(), self.args.expected_revision)
        self.check('gitops', not problems, problems)

    def inspect_images(self, pods, name):
        problems, observed = image_problems(pods, self.lock, self.cri_ids)
        self.check(name, not problems, {'problems': problems, 'images': observed})

    def host_and_images(self):
        for action in ('host-check', 'host-network'):
            transport = ReadOnlyNetwork(self.transport) if action == 'host-network' else self.transport
            value = self.host(action, transport, check=True)
            self.check(action, value.get('status') == 'passed')
        self.lock = {'images': {}}
        for name in ('images.lock.json', 'bootstrap-images.lock.json'):
            lock = normalized_lock(json.loads((ROOT / 'deploy/common' / name).read_text(encoding='utf-8')))
            self.check('staging:' + name, self.transport.agent(lock, check=True).get('status') == 'passed')
            self.lock['images'].update({name + ':' + key: value for key, value in lock['images'].items()})
        self.cri_ids = cri_identities(self.transport, self.lock, self.pods)
        self.inspect_images(self.pods, 'deployedImages')

    def console_and_cache(self):
        self.check('consoleHTTPS', self.health(self.args.ca_file, self.cookie))
        console = one_pod(self.pods, 'twinfra-console')
        statuses = json.loads(self.client.exec(console, 'console', 'python', '-c', TOKEN_PROBE,
                                  payload=json.dumps({'roleless': self.token}).encode()))
        self.check('tokenNegatives', statuses == [401, 401, 401, 403], {'missing': statuses[0],
              'unsigned': statuses[1], 'duplicate': statuses[2], 'roleless': statuses[3]})
        cache = valkey(self.client, self.pods)
        self.check('valkey', cache_ok(cache), cache)
        self.report['versions'] = {}
        try:
            self.report['versions'], problems = versions(self.client, self.pods, self.node)
        except (ValueError, OSError, KeyError, IndexError, TypeError, AttributeError,
                subprocess.SubprocessError, http.client.HTTPException):
            problems = ['Version report unavailable']  # Never serialize exception/output.
        self.check('versions', not problems, problems)

    def reconnected(self, current, restarted):
        new = one_pod(current, 'argocd-redis')
        apps = self.applications()
        state = valkey(self.client, current)
        return (new['metadata']['uid'] != self.replaced and ready(new) and
                all(ready(one_pod(current, n)) for n in ARGO) and
                not application_problems(apps, self.args.expected_revision, restarted) and cache_ok(state))

    def poll_reconnect(self, restarted):
        self.client.deadline = time.monotonic() + self.args.timeout
        try:
            for _ in range(max(1, self.args.timeout // 5)):
                if time.monotonic() >= self.client.deadline:
                    break
                self.sleeper(min(5, max(0, self.client.deadline - time.monotonic())))
                current = self.client.get('pods', '--all-namespaces')['items']
                try:
                    if self.reconnected(current, restarted):
                        return True
                except ValueError:
                    pass
            return False
        finally:
            self.client.deadline = None

    def cache_restart(self):
        if not self.args.with_restart:
            self.report['checks']['valkeyRestart'] = {'status': 'pending',
                'details': 'Owner must run --with-restart to prove reconnect'}
            return
        # Informational version failures do not block the explicitly requested
        # restart test; health/security/image failures still refuse mutation.
        if any(c['status'] == 'failed' for name, c in self.report['checks'].items() if name != 'versions'):
            raise ValueError('Cache restart refused because pre-restart acceptance failed')
        cache = one_pod(self.pods, 'argocd-redis')
        self.replaced = cache['metadata']['uid']
        restarted = self.now()
        # Sole mutation, explicitly requested by the owner; never a rollout/config patch.
        self.client.call('-n', NS, 'delete', 'pod', cache['metadata']['name'], '--wait=false')
        self.check('valkeyRestart', self.poll_reconnect(restarted))

    def finish(self):
        pods = self.client.get('pods', '--all-namespaces')['items']
        allowed_new = one_pod(pods, 'argocd-redis')['metadata']['uid'] if self.replaced else None
        problems = pod_problems(pods, self.since, self.before, self.replaced, allowed_new)
        self.report['podSnapshots']['final'] = snapshot(pods)
        self.check('podsFinal', not problems, problems)
        self.inspect_images(pods, 'deployedImagesFinal')
        problems = application_problems(self.applications(), self.args.expected_revision)
        self.check('gitopsFinal', not problems, problems)
        self.report['status'] = completion_status(self.report['checks'])

    def run(self):
        try:
            self.initialize()
            self.cluster()
            self.host_and_images()
            self.console_and_cache()
            self.cache_restart()
            self.finish()
        except (ValueError, OSError, KeyError, IndexError, TypeError, AttributeError,
                subprocess.SubprocessError, http.client.HTTPException):
            # Never serialize exceptions, response bodies, tokens, cookies or subprocess output.
            self.report['error'] = 'Acceptance could not complete; verify prerequisites and sanitized check results.'
        self.report['finishedAt'] = self.now().isoformat()
        self.report['warnings'] = sum(e['status'] == 'warning' for e in self.report.get('exceptionCalendar', []))
        return self.report


def accept(args, *, client=None, transport=None, host=host_execute, health=console_health,
           now=utc, sleeper=time.sleep):
    return AcceptanceRun(args, client, transport, host, health, now, sleeper).run()


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
