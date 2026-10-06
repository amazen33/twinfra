"""Bounded agent planning and durable, feature-gated Spinifex capacity requests.

Model output never becomes a command, image, URL, cloud credential or arbitrary
Kubernetes manifest. MultiKueue remains the execution owner. This module only
plans workloads and, after explicit site enablement, requests EC2 capacity.
"""
import hashlib
import json
import math
from pathlib import Path
import re
import sqlite3
import threading
import time
import uuid
from urllib.parse import urlsplit

CLUSTER = 'vCloud-prod-01'
REGION = 'vcloud-hpc-1'
QUEUE = 'spinifex-hpc-burst'
EXTERNAL = 'https://ec2.spinifex.pcloud.example.com'
INTERNAL = 'https://spinifex-controller.hpc-compute.svc.cluster.local:3000'
PROFILE = 'spinifex.gpu.h100.80gb.8x'


class Rejected(ValueError):
    pass


def json_object(raw):
    def unique(pairs):
        result = {}
        for name, value in pairs:
            if name in result:
                raise Rejected('Duplicate JSON key')
            result[name] = value
        return result
    value = json.loads(raw, object_pairs_hook=unique, parse_constant=lambda _: (_ for _ in ()).throw(Rejected('Non-finite JSON')))
    if not isinstance(value, dict):
        raise Rejected('JSON object required')
    return value


def enabled_config(config):
    if config['offload_enabled'] is not True:
        return False
    if config['site_accepted'] is not True or config['storage_and_fabric_accepted'] is not True:
        raise Rejected('Site/storage/fabric acceptance required')
    endpoint = urlsplit(config['endpoint_url'])
    if config['endpoint_url'] not in (EXTERNAL, INTERNAL) or endpoint.scheme != 'https' or endpoint.username or endpoint.password:
        raise Rejected('Verified HTTPS at an exact approved Spinifex endpoint required')
    if config['region'] != REGION or config['cluster'] != CLUSTER or config['queue'] != QUEUE:
        raise Rejected('Platform/provider identity mismatch')
    if type(config['max_burst_nodes']) is not int or not 1 <= config['max_burst_nodes'] <= 4:
        raise Rejected('Burst limit must be between one and four nodes')
    launch = config['launch']
    for key, pattern in [('image_id', r'ami-[a-z0-9-]+'), ('subnet_id', r'subnet-[a-z0-9-]+')]:
        if not isinstance(launch[key], str) or not re.fullmatch(pattern, launch[key]):
            raise Rejected('Accepted private worker image/subnet required')
    if not launch['security_group_ids'] or any(not re.fullmatch(r'sg-[a-z0-9-]+', value) for value in launch['security_group_ids']):
        raise Rejected('Accepted security groups required')
    if config['worker_kubernetes_version'] != '1.36.5':
        raise Rejected('Worker Kubernetes version parity required')
    for name, minimum, maximum in [('saturation_window_seconds', 300, 3600), ('metrics_max_age_seconds', 1, 60),
            ('minimum_pending_seconds', 120, 3600), ('cooldown_seconds', 600, 86400), ('lease_seconds', 60, 3600)]:
        if type(config[name]) is not int or not minimum <= config[name] <= maximum:
            raise Rejected('Timing safety bounds required')
    if any(config[name] != 0.85 for name in ('cpu_threshold', 'gpu_threshold', 'memory_threshold')):
        raise Rejected('Accepted 85-percent thresholds required')
    if not Path(config['ca_file']).is_file():
        raise Rejected('Provider CA file required')
    return True


def request_contract(request, config):
    if set(request) != {'request_id', 'workload_name', 'workload_uid', 'profile', 'nodes', 'queue'}:
        raise Rejected('Unexpected or missing capacity request fields')
    try:
        if str(uuid.UUID(request['request_id'])) != request['request_id'] or str(uuid.UUID(request['workload_uid'])) != request['workload_uid']:
            raise ValueError()
    except (ValueError, TypeError, AttributeError):
        raise Rejected('Canonical request/workload UUIDs required') from None
    if not isinstance(request['workload_name'], str) or not re.fullmatch(r'[a-z0-9][a-z0-9-]{0,62}', request['workload_name']):
        raise Rejected('Invalid Workload name')
    if request['queue'] != QUEUE or request['profile'] != config['default_profile']:
        raise Rejected('Only the explicitly selected queue/profile is permitted')
    profile = config['profiles'].get(request['profile'])
    if not profile or profile['mapping_accepted'] is not True or profile['instance_type'] != 'p5.48xlarge' or profile['gpu_count'] != 8:
        raise Rejected('Verified whole-node H100 mapping required; no implicit fallback')
    if type(request['nodes']) is not int or not 1 <= request['nodes'] <= config['max_burst_nodes']:
        raise Rejected('Invalid whole-node request count')
    return request


def pressure(config, samples, now):
    if set(samples) != {'cpu', 'gpu', 'memory'}:
        raise Rejected('All three trusted metric samples required')
    values = {}
    for name, sample in samples.items():
        if sample['cluster'] != CLUSTER or sample['window_seconds'] < config['saturation_window_seconds']:
            raise Rejected('Metric identity/window mismatch')
        value, age = sample['value'], now - sample['timestamp']
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not 0 <= value <= 1:
            raise Rejected('Invalid metric ratio')
        if not 0 <= age <= config['metrics_max_age_seconds']:
            raise Rejected('Stale or future metric')
        values[name] = value
    # > 85% for CPU/GPU, >= 85% of defined memory limits for memory pressure.
    return (values['cpu'] > config['cpu_threshold'] or values['gpu'] > config['gpu_threshold'] or
            values['memory'] >= config['memory_threshold'])


def demand(request, workload, now, config):
    meta, spec = workload['metadata'], workload['spec']
    if meta['uid'] != request['workload_uid'] or meta['name'] != request['workload_name'] or meta['namespace'] != 'hpc-compute':
        raise Rejected('Workload identity mismatch')
    if spec['queueName'] != QUEUE or meta.get('labels', {}).get('vcloud.io/offload-target') != 'spinifex-hpc':
        raise Rejected('Workload is outside the offload queue/selector')
    conditions = {condition['type']: condition['status'] for condition in workload.get('status', {}).get('conditions', [])}
    if conditions.get('QuotaReserved') != 'True' or conditions.get('Admitted') == 'True' or conditions.get('Finished') == 'True':
        raise Rejected('Only reserved, unadmitted, unfinished Workloads can request capacity')
    from datetime import datetime
    created = datetime.fromisoformat(meta['creationTimestamp'].replace('Z', '+00:00')).timestamp()
    if now - created < config['minimum_pending_seconds']:
        raise Rejected('Pending demand hold-down has not elapsed')
    sets = spec['podSets']
    if sum(podset['count'] for podset in sets) != request['nodes']:
        raise Rejected('Whole-job node demand mismatch')
    for podset in sets:
        containers = podset['template']['spec']['containers']
        if sum(int(c.get('resources', {}).get('requests', {}).get('nvidia.com/gpu', 0)) for c in containers) != 8:
            raise Rejected('Each selected Pod must request the accepted whole eight-GPU node')


class Ledger:
    """Single-writer CSI-backed ledger; reservations count even after uncertain I/O."""
    def __init__(self, path):
        self.db = sqlite3.connect(path, check_same_thread=False, isolation_level=None)
        self.lock = threading.RLock()
        self.db.execute('PRAGMA journal_mode=WAL')
        self.db.execute('PRAGMA synchronous=FULL')
        self.db.execute('CREATE TABLE IF NOT EXISTS leases (workload TEXT PRIMARY KEY, name TEXT NOT NULL, fingerprint TEXT NOT NULL, token TEXT NOT NULL UNIQUE, nodes INTEGER NOT NULL, created REAL NOT NULL, expires REAL NOT NULL, state TEXT NOT NULL, instances TEXT NOT NULL)')

    def close(self):
        self.db.close()

    def reserve(self, request, config, now):
        canonical = {'request': {k: v for k, v in request.items() if k != 'request_id'},
                     'launch': config['launch'], 'endpoint': config['endpoint_url'], 'region': config['region']}
        fingerprint = hashlib.sha256(json.dumps(canonical, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
        token = hashlib.sha256((CLUSTER + ':' + request['workload_uid'] + ':' + fingerprint).encode()).hexdigest()
        with self.lock:
            self.db.execute('BEGIN IMMEDIATE')
            try:
                row = self.db.execute('SELECT fingerprint,token,state,instances FROM leases WHERE workload=?', (request['workload_uid'],)).fetchone()
                if row:
                    if row[0] != fingerprint:
                        raise Rejected('Workload replay changed its capacity parameters')
                    if row[2] == 'released':
                        raise Rejected('Released Workload cannot be relaunched')
                    result = dict(token=row[1], state=row[2], instances=json.loads(row[3]))
                else:
                    # Never drop quota on timeout/expiry alone: only verified cleanup
                    # can release it. This bounds resources across restarts and retries.
                    active = self.db.execute("SELECT COALESCE(SUM(nodes),0) FROM leases WHERE state != 'released'").fetchone()[0]
                    last = self.db.execute('SELECT MAX(created) FROM leases').fetchone()[0]
                    if active + request['nodes'] > config['max_burst_nodes']:
                        raise Rejected('Global burst node budget exceeded')
                    if last is not None and now - last < config['cooldown_seconds']:
                        raise Rejected('Burst cooldown has not elapsed')
                    self.db.execute('INSERT INTO leases VALUES (?,?,?,?,?,?,?,?,?)', (request['workload_uid'], request['workload_name'], fingerprint, token, request['nodes'], now, now + config['lease_seconds'], 'reserved', '[]'))
                    result = dict(token=token, state='reserved', instances=[])
                self.db.execute('COMMIT')
                return result
            except Exception:
                self.db.execute('ROLLBACK')
                raise

    def update(self, workload, state, instances):
        with self.lock:
            self.db.execute('UPDATE leases SET state=?,instances=? WHERE workload=?', (state, json.dumps(instances), workload))

    def active(self):
        with self.lock:
            return [dict(uid=row[0], name=row[1], nodes=row[2], expires=row[3], state=row[4], instances=json.loads(row[5]))
                    for row in self.db.execute("SELECT workload,name,nodes,expires,state,instances FROM leases WHERE state != 'released'")]


def aws_client(service_name, config, now):
    # Load mounted, rotating credentials only on the explicitly enabled path.
    # An explicit Session prevents ambient environment/IMDS/profile credentials.
    import boto3
    from botocore.config import Config
    if service_name not in ('ec2', 'eks', 'sts'):
        raise Rejected('Unapproved provider API service')
    credential = json_object(Path(config['credentials_file']).read_text())
    if set(credential) != {'access_key_id', 'secret_access_key', 'session_token', 'expires_at'}:
        raise Rejected('Short-lived AWS credential file shape mismatch')
    if not all(isinstance(credential[k], str) and credential[k] for k in ('access_key_id', 'secret_access_key', 'session_token')):
        raise Rejected('Incomplete provider credentials')
    if type(credential['expires_at']) not in (int, float) or not math.isfinite(credential['expires_at']) or not now + 60 <= credential['expires_at'] <= now + 3600:
        raise Rejected('Expired or excessive credential lifetime')
    session = boto3.Session(aws_access_key_id=credential['access_key_id'], aws_secret_access_key=credential['secret_access_key'],
                           aws_session_token=credential['session_token'], region_name=config['region'])
    return session.client(service_name, endpoint_url=config['endpoint_url'], verify=config['ca_file'],
                          config=Config(signature_version='v4', connect_timeout=5, read_timeout=15,
                                        retries={'total_max_attempts': 2, 'mode': 'standard'}, proxies={}))


def ec2_client(config, now):
    return aws_client('ec2', config, now)


class CapacityEngine:
    def __init__(self, config, ledger_factory, observe_workload, observe_metrics, client_factory=ec2_client, clock=time.time):
        self.config, self.ledger_factory = config, ledger_factory
        self.observe_workload, self.observe_metrics = observe_workload, observe_metrics
        self.client_factory, self.clock = client_factory, clock
        self.operation_lock = threading.Lock()
        self.ledger = None

    def handle(self, request):
        # Deliberately before schema parsing, credential reads, metrics/API calls
        # and ledger creation: a disabled profile has zero provider side effects.
        if not enabled_config(self.config):
            return dict(status='disabled', offload_enabled=False)
        request_contract(request, self.config)
        with self.operation_lock:
            now = self.clock()
            demand(request, self.observe_workload(request), now, self.config)
            if not pressure(self.config, self.observe_metrics(), now):
                return dict(status='held', reason='no sustained saturation or memory pressure')
            if self.ledger is None:
                self.ledger = self.ledger_factory()
            reservation = self.ledger.reserve(request, self.config, now)
            if reservation['state'] == 'provisioned':
                return dict(status='provisioned', instances=reservation['instances'])
            launch = self.config['launch']
            params = dict(ImageId=launch['image_id'], InstanceType='p5.48xlarge',
                          MinCount=request['nodes'], MaxCount=request['nodes'], ClientToken=reservation['token'],
                          SubnetId=launch['subnet_id'], SecurityGroupIds=launch['security_group_ids'],
                          TagSpecifications=[dict(ResourceType='instance', Tags=[
                              dict(Key='vcloud:cluster', Value=CLUSTER), dict(Key='vcloud:workload-uid', Value=request['workload_uid']),
                              dict(Key='vcloud:managed-by', Value='capacity-bridge')])])
            self.ledger.update(request['workload_uid'], 'uncertain', [])
            try:
                response = self.client_factory(self.config, now).run_instances(**params)
                instances = [item['InstanceId'] for item in response['Instances']]
                if len(instances) != request['nodes'] or len(set(instances)) != len(instances) or any(not re.fullmatch(r'i-[a-z0-9]+', identity) for identity in instances):
                    raise Rejected('Provider returned unexpected instance count/identity')
                self.ledger.update(request['workload_uid'], 'provisioned', instances)
                return dict(status='provisioned', instances=instances)
            except Exception:
                # Keep reservation charged; retry uses the same persisted ClientToken.
                # Return a generic error, without provider/credential exception text.
                raise Rejected('Provider outcome uncertain; retain reservation and reconcile') from None

    def reconcile(self):
        if not enabled_config(self.config):
            return []
        if self.ledger is None:
            self.ledger = self.ledger_factory()
        results = []
        with self.operation_lock:
            client = self.client_factory(self.config, self.clock())
            for lease in self.ledger.active():
                try:
                    observed = self.observe_workload({'workload_name': lease['name'], 'workload_uid': lease['uid']})
                    if observed['metadata']['uid'] != lease['uid'] or observed['metadata']['name'] != lease['name'] or observed['metadata']['namespace'] != 'hpc-compute' or observed['spec']['queueName'] != QUEUE:
                        raise Rejected('Workload UID changed; operator reconciliation required')
                    conditions = observed.get('status', {}).get('conditions', [])
                    if not any(c['type'] == 'Finished' and c['status'] == 'True' for c in conditions):
                        results.append(dict(uid=lease['uid'], state='held', expired=lease['expires'] <= self.clock())); continue
                    query = {'InstanceIds': lease['instances']} if lease['instances'] else {'Filters': [
                        {'Name': 'tag:vcloud:workload-uid', 'Values': [lease['uid']]},
                        {'Name': 'tag:vcloud:cluster', 'Values': [CLUSTER]}]}
                    response = client.describe_instances(**query)
                    instances = [item for reservation in response['Reservations'] for item in reservation['Instances']]
                    if len(instances) != lease['nodes']:
                        raise Rejected('Uncertain instance inventory; retain quota')
                    for item in instances:
                        tags = {tag['Key']: tag['Value'] for tag in item.get('Tags', [])}
                        if (tags.get('vcloud:workload-uid'), tags.get('vcloud:cluster'), tags.get('vcloud:managed-by')) != (lease['uid'], CLUSTER, 'capacity-bridge'):
                            raise Rejected('Instance ownership mismatch')
                        if item['InstanceType'] != 'p5.48xlarge':
                            raise Rejected('Instance profile mismatch')
                    identities = [item['InstanceId'] for item in instances]
                    if len(set(identities)) != len(identities) or (lease['instances'] and set(identities) != set(lease['instances'])):
                        raise Rejected('Provider inventory identities changed')
                    if all(item['State']['Name'] == 'terminated' for item in instances):
                        self.ledger.update(lease['uid'], 'released', identities)
                        results.append(dict(uid=lease['uid'], state='released'))
                    else:
                        client.terminate_instances(InstanceIds=identities)
                        self.ledger.update(lease['uid'], 'terminating', identities)
                        results.append(dict(uid=lease['uid'], state='terminating'))
                except Exception:
                    results.append(dict(uid=lease['uid'], state='uncertain'))
        return results


def agent_plan(value, config):
    if not isinstance(value, dict) or set(value) != {'action', 'answer', 'batch'}:
        raise Rejected('Invalid model plan')
    if value['action'] == 'answer':
        if not isinstance(value['answer'], str) or len(value['answer']) > 16000 or value['batch'] is not None:
            raise Rejected('Invalid answer')
        return value
    if value['action'] != 'enqueue_simulation' or value['answer'] is not None or not isinstance(value['batch'], dict):
        raise Rejected('Unknown model action')
    batch = value['batch']
    if set(batch) != {'profile', 'nodes', 'dataset'} or batch['profile'] != config['default_profile']:
        raise Rejected('Model cannot select another profile or arbitrary fields')
    if type(batch['nodes']) is not int or not 1 <= batch['nodes'] <= config['max_burst_nodes'] or batch['dataset'] not in ('synthetic',):
        raise Rejected('Model cannot choose unapproved capacity/data')
    return value


class Agent:
    def __init__(self, config, model):
        self.config, self.model = config, model

    def run(self, request):
        if set(request) != {'prompt', 'steps'} or not isinstance(request['prompt'], str) or not 1 <= len(request['prompt']) <= self.config['agent_max_prompt_chars']:
            raise Rejected('Invalid agent request')
        if type(request['steps']) is not int or not 1 <= request['steps'] <= self.config['agent_max_steps']:
            raise Rejected('Agent step budget exceeded')
        plan = agent_plan(self.model(request['prompt']), self.config)
        if plan['action'] == 'enqueue_simulation':
            # Only return a proposal. Submission uses the operator-owned suspended
            # Job/JobSet template, independently of the model's generated output.
            return dict(status='proposed', execution_enabled=False, proposal=plan['batch'], queue=QUEUE)
        return dict(status='answered', answer=plan['answer'])
