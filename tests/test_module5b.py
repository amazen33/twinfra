"""Offline HPC contracts, real SDK signing/stubs, durable ledger and local mTLS."""
import concurrent.futures
import copy
from datetime import datetime, timezone
import importlib.util
import json
import os
from pathlib import Path
import shutil
import ssl
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch
import urllib.error
import urllib.request
import uuid

import boto3
from botocore.auth import SigV4Auth
from botocore.awsrequest import AWSRequest
from botocore.credentials import Credentials
from botocore.stub import Stubber
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'module-5b/runtime'))
sys.path.insert(0, str(ROOT / 'tools'))
import engine as e
import server as s
import trigger
import module5b as m
import render_module5b as render
NOW = 1800000000


def request(nodes=1, uid=None):
    return dict(request_id=str(uuid.uuid4()), workload_name='reference-' + str(nodes),
                workload_uid=uid or str(uuid.uuid4()), profile=e.PROFILE, nodes=nodes, queue=e.QUEUE)


def workload(r, finished=False):
    return dict(metadata=dict(uid=r['workload_uid'], name=r['workload_name'], namespace='hpc-compute',
            creationTimestamp=datetime.fromtimestamp(NOW - 300, timezone.utc).isoformat(), labels=render.TARGET),
        spec=dict(queueName=e.QUEUE, podSets=[dict(count=r['nodes'], template=dict(spec=dict(containers=[dict(
            resources=dict(requests={'nvidia.com/gpu': 8}))])))]),
        status=dict(conditions=[dict(type='QuotaReserved', status='True'), dict(type='Finished', status=str(finished))]))


def samples(cpu=.9, gpu=.9, memory=.5):
    return {name: dict(cluster=e.CLUSTER, value=value, timestamp=NOW, window_seconds=300)
            for name, value in [('cpu', cpu), ('gpu', gpu), ('memory', memory)]}


class Runtime(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name)
        self.config = json.loads((ROOT / 'module-5b/reference-profile.json').read_text())
        self.config.update(offload_enabled=True, site_accepted=True, storage_and_fabric_accepted=True, endpoint_url=e.EXTERNAL,
            ca_file=str(self.path / 'ca.crt'), credentials_file=str(self.path / 'credentials.json'),
            launch={'image_id': 'ami-reference', 'subnet_id': 'subnet-reference', 'security_group_ids': ['sg-reference']})
        (self.path / 'ca.crt').write_text('test CA placeholder; Stubber performs no network')
        self.config['profiles'][e.PROFILE]['mapping_accepted'] = True
        self.credential = dict(access_key_id='test-key', secret_access_key='test-secret', session_token='test-session', expires_at=NOW + 900)
        self.write_credentials()
        self.ledger = e.Ledger(self.path / 'capacity.db'); self.addCleanup(self.ledger.close)
        self.r = request(); self.w = workload(self.r)
        self.client = e.ec2_client(self.config, NOW)
        self.factory = Mock(return_value=self.client)
        self.watcher, self.metrics = Mock(return_value=self.w), Mock(return_value=samples())
        self.engine = e.CapacityEngine(self.config, lambda: self.ledger, self.watcher, self.metrics, self.factory, lambda: NOW)

    def write_credentials(self):
        (self.path / 'credentials.json').write_text(json.dumps(self.credential))

    def params(self, r=None):
        r = r or self.r; lease = self.ledger.reserve(r, self.config, NOW)
        return dict(ImageId='ami-reference', InstanceType='p5.48xlarge', MinCount=r['nodes'], MaxCount=r['nodes'],
            ClientToken=lease['token'], SubnetId='subnet-reference', SecurityGroupIds=['sg-reference'], TagSpecifications=[dict(
                ResourceType='instance', Tags=[dict(Key='vcloud:cluster', Value=e.CLUSTER),
                    dict(Key='vcloud:workload-uid', Value=r['workload_uid']), dict(Key='vcloud:managed-by', Value='capacity-bridge')])])

    def instances(self, state='running', foreign=False):
        return dict(Reservations=[dict(Instances=[dict(InstanceId='i-reference', InstanceType='p5.48xlarge', State=dict(Name=state), Tags=[
            dict(Key='vcloud:cluster', Value='foreign' if foreign else e.CLUSTER), dict(Key='vcloud:workload-uid', Value=self.r['workload_uid']),
            dict(Key='vcloud:managed-by', Value='capacity-bridge')])])])

    def provisioned(self):
        self.ledger.reserve(self.r, self.config, NOW); self.ledger.update(self.r['workload_uid'], 'provisioned', ['i-reference'])
        self.engine.ledger = self.ledger

    def test_disabled_has_zero_io_even_for_malformed_request(self):
        self.config['offload_enabled'] = False
        self.engine.ledger_factory = Mock(side_effect=AssertionError('No ledger'))
        self.assertEqual(self.engine.handle({'malformed': True})['status'], 'disabled')
        self.assertEqual(self.engine.reconcile(), [])
        for dependency in (self.factory, self.watcher, self.metrics, self.engine.ledger_factory): dependency.assert_not_called()

    def test_disabled_trigger_never_reads_credentials_or_uses_transport(self):
        send = Mock(side_effect=AssertionError('Network forbidden'))
        self.assertEqual(trigger.dispatch({}, 'false', send)['status'], 'disabled'); send.assert_not_called()
        with self.assertRaises(ValueError): trigger.dispatch({}, 'FALSE', send)

    def test_enabled_http_is_rejected(self):
        self.config['endpoint_url'] = 'http://spinifex-controller.hpc-compute.svc.cluster.local:3000'
        with self.assertRaises(e.Rejected): self.engine.handle(self.r)
        self.factory.assert_not_called()

    def test_unaccepted_site_and_fabric_rejected(self):
        for key in ('site_accepted', 'storage_and_fabric_accepted'):
            for value in (False, 'true', 1):
                with self.subTest(key=key, value=value), self.assertRaises(e.Rejected):
                    e.enabled_config(self.config | {key: value})

    def test_provider_endpoint_redirect_identity_rejected(self):
        for value in ('https://evil.example', e.EXTERNAL + '/extra', 'https://user:pass@ec2.spinifex.pcloud.example.com'):
            with self.subTest(value=value), self.assertRaises(e.Rejected): e.enabled_config(self.config | {'endpoint_url': value})

    def test_identity_version_budget_and_timing_gates(self):
        for key, value in [('region', 'other'), ('cluster', 'other'), ('queue', 'other'), ('max_burst_nodes', 5),
                ('max_burst_nodes', True), ('worker_kubernetes_version', '1.32.0'), ('metrics_max_age_seconds', 120),
                ('cooldown_seconds', 0), ('minimum_pending_seconds', 0), ('cpu_threshold', .5), ('lease_seconds', 99999)]:
            with self.subTest(key=key, value=value), self.assertRaises(e.Rejected): e.enabled_config(self.config | {key: value})

    def test_missing_launch_and_ca_rejected(self):
        for launch in ({'image_id': None, 'subnet_id': 'subnet-ref', 'security_group_ids': ['sg-ref']},
                       {'image_id': 'ami-ref', 'subnet_id': 'subnet-ref', 'security_group_ids': []}):
            with self.assertRaises(e.Rejected): e.enabled_config(self.config | {'launch': launch})
        with self.assertRaises(e.Rejected): e.enabled_config(self.config | {'ca_file': str(self.path / 'missing')})

    def test_request_exact_fields_and_canonical_uuids(self):
        for change in ({'shell': 'id'}, {'request_id': 'not-uuid'}, {'workload_uid': '../bad'}, {'workload_name': '../bad'}, {'queue': 'foreign'}):
            with self.subTest(change=change), self.assertRaises(e.Rejected): e.request_contract(self.r | change, self.config)

    def test_node_limits_and_fallback_never_implicit(self):
        for change in ({'nodes': 5}, {'nodes': 0}, {'nodes': True}, {'profile': 'spinifex.gpu.a100.80gb.4x'}):
            with self.subTest(change=change), self.assertRaises(e.Rejected): e.request_contract(self.r | change, self.config)
        self.config['profiles'][e.PROFILE]['mapping_accepted'] = False
        with self.assertRaises(e.Rejected): e.request_contract(self.r, self.config)

    def test_threshold_semantics(self):
        self.assertFalse(e.pressure(self.config, samples(.85, .85, .84), NOW))
        for value in (samples(.851, .1, .1), samples(.1, .851, .1), samples(.1, .1, .85)):
            self.assertTrue(e.pressure(self.config, value, NOW))

    def test_invalid_missing_and_nonfinite_metrics(self):
        for ratio in (True, float('nan'), float('inf'), -1, 1.01, '0.9'):
            data = samples(); data['gpu']['value'] = ratio
            with self.subTest(ratio=ratio), self.assertRaises(e.Rejected): e.pressure(self.config, data, NOW)
        with self.assertRaises(e.Rejected): e.pressure(self.config, {'cpu': samples()['cpu']}, NOW)

    def test_stale_future_cluster_and_short_window_metrics(self):
        for change in ({'timestamp': NOW - 61}, {'timestamp': NOW + 1}, {'cluster': 'other'}, {'window_seconds': 299}):
            data = samples(); data['memory'].update(change)
            with self.subTest(change=change), self.assertRaises(e.Rejected): e.pressure(self.config, data, NOW)

    def test_demand_requires_reserved_unadmitted_unfinished(self):
        for kind, status in [('QuotaReserved', 'False'), ('Admitted', 'True'), ('Finished', 'True')]:
            value = copy.deepcopy(self.w); value['status']['conditions'] = [dict(type=kind, status=status)]
            with self.subTest(kind=kind), self.assertRaises(e.Rejected): e.demand(self.r, value, NOW, self.config)

    def test_demand_identity_label_queue_boundaries(self):
        for key, value in [('uid', str(uuid.uuid4())), ('namespace', 'other'), ('name', 'other'), ('labels', {})]:
            w = copy.deepcopy(self.w); w['metadata'][key] = value
            with self.assertRaises(e.Rejected): e.demand(self.r, w, NOW, self.config)
        w = copy.deepcopy(self.w); w['spec']['queueName'] = 'other'
        with self.assertRaises(e.Rejected): e.demand(self.r, w, NOW, self.config)

    def test_demand_pending_hold_whole_node_and_gpu_count(self):
        w = copy.deepcopy(self.w); w['metadata']['creationTimestamp'] = datetime.fromtimestamp(NOW - 119, timezone.utc).isoformat()
        with self.assertRaises(e.Rejected): e.demand(self.r, w, NOW, self.config)
        w = copy.deepcopy(self.w); w['spec']['podSets'][0]['count'] = 2
        with self.assertRaises(e.Rejected): e.demand(self.r, w, NOW, self.config)
        w = copy.deepcopy(self.w); w['spec']['podSets'][0]['template']['spec']['containers'][0]['resources']['requests']['nvidia.com/gpu'] = 4
        with self.assertRaises(e.Rejected): e.demand(self.r, w, NOW, self.config)

    def test_quiet_pressure_never_reserves_or_provisions(self):
        self.metrics.return_value = samples(.1, .1, .1)
        self.assertEqual(self.engine.handle(self.r)['status'], 'held'); self.assertEqual(self.ledger.active(), []); self.factory.assert_not_called()

    def test_real_sdk_run_instances_exact_parameters(self):
        with Stubber(self.client) as stub:
            stub.add_response('run_instances', {'Instances': [{'InstanceId': 'i-reference'}]}, self.params())
            self.assertEqual(self.engine.handle(self.r), {'status': 'provisioned', 'instances': ['i-reference']})
            stub.assert_no_pending_responses()

    def test_retry_after_uncertain_response_reuses_durable_token(self):
        expected = self.params()
        with Stubber(self.client) as stub:
            stub.add_client_error('run_instances', 'InternalError', expected_params=expected)
            stub.add_response('run_instances', {'Instances': [{'InstanceId': 'i-reference'}]}, expected)
            with self.assertRaisesRegex(e.Rejected, 'uncertain'): self.engine.handle(self.r)
            self.assertEqual(self.ledger.active()[0]['state'], 'uncertain')
            self.r['request_id'] = str(uuid.uuid4())
            self.assertEqual(self.engine.handle(self.r)['status'], 'provisioned'); stub.assert_no_pending_responses()

    def test_known_provisioned_replay_does_not_call_provider(self):
        self.provisioned(); self.assertEqual(self.engine.handle(self.r)['status'], 'provisioned'); self.factory.assert_not_called()

    def test_changed_replay_parameters_rejected(self):
        self.params()
        with self.assertRaises(e.Rejected): self.ledger.reserve(self.r | {'nodes': 2}, self.config, NOW)
        changed = copy.deepcopy(self.config); changed['launch']['image_id'] = 'ami-changed'
        with self.assertRaises(e.Rejected): self.ledger.reserve(self.r, changed, NOW)

    def test_restart_preserves_token_and_quota(self):
        token = self.params()['ClientToken']; other = e.Ledger(self.path / 'capacity.db')
        try:
            self.assertEqual(other.reserve(self.r, self.config, NOW)['token'], token)
            with self.assertRaises(e.Rejected): other.reserve(request(4), self.config, NOW + 601)
        finally: other.close()

    def test_expiry_never_frees_uncertain_capacity(self):
        self.params(); self.ledger.update(self.r['workload_uid'], 'uncertain', [])
        with self.assertRaises(e.Rejected): self.ledger.reserve(request(4), self.config, NOW + 10000)

    def test_budget_atomic_across_concurrent_writers(self):
        config = self.config | {'cooldown_seconds': 0}
        def reserve(_):
            conn = e.Ledger(self.path / 'capacity.db')
            try:
                conn.reserve(request(), config, NOW); return True
            except e.Rejected: return False
            finally: conn.close()
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            self.assertEqual(sum(pool.map(reserve, range(8))), 4)
        self.assertEqual(sum(v['nodes'] for v in self.ledger.active()), 4)

    def test_released_workload_cannot_relaunch(self):
        self.params(); self.ledger.update(self.r['workload_uid'], 'released', ['i-reference'])
        with self.assertRaises(e.Rejected): self.ledger.reserve(self.r, self.config, NOW + 999)

    def test_cooldown_survives_release(self):
        self.params(); self.ledger.update(self.r['workload_uid'], 'released', ['i-reference'])
        with self.assertRaises(e.Rejected): self.ledger.reserve(request(), self.config, NOW + 599)

    def test_cleanup_never_terminates_unfinished_even_if_expired(self):
        self.provisioned(); self.engine.clock = lambda: NOW + 10000
        client = Mock(); self.factory.return_value = client
        self.assertEqual(self.engine.reconcile()[0]['state'], 'held'); client.describe_instances.assert_not_called(); client.terminate_instances.assert_not_called()

    def test_cleanup_requires_finished_and_confirmed_termination(self):
        self.provisioned(); self.w['status']['conditions'].append(dict(type='Finished', status='True'))
        with Stubber(self.client) as stub:
            stub.add_response('describe_instances', self.instances(), {'InstanceIds': ['i-reference']})
            stub.add_response('terminate_instances', {}, {'InstanceIds': ['i-reference']})
            self.assertEqual(self.engine.reconcile()[0]['state'], 'terminating'); self.assertEqual(len(self.ledger.active()), 1)
            stub.add_response('describe_instances', self.instances('terminated'), {'InstanceIds': ['i-reference']})
            self.assertEqual(self.engine.reconcile()[0]['state'], 'released'); self.assertEqual(self.ledger.active(), []); stub.assert_no_pending_responses()

    def test_cleanup_rejects_foreign_ownership(self):
        self.provisioned(); self.w['status']['conditions'].append(dict(type='Finished', status='True'))
        with Stubber(self.client) as stub:
            stub.add_response('describe_instances', self.instances(foreign=True), {'InstanceIds': ['i-reference']})
            self.assertEqual(self.engine.reconcile()[0]['state'], 'uncertain'); self.assertEqual(len(self.ledger.active()), 1); stub.assert_no_pending_responses()

    def test_cleanup_rejects_changed_ids_and_workload_uid(self):
        self.provisioned(); self.w['status']['conditions'].append(dict(type='Finished', status='True'))
        data = self.instances(); data['Reservations'][0]['Instances'][0]['InstanceId'] = 'i-foreign'
        with Stubber(self.client) as stub:
            stub.add_response('describe_instances', data, {'InstanceIds': ['i-reference']})
            self.assertEqual(self.engine.reconcile()[0]['state'], 'uncertain')
        self.w['metadata']['uid'] = str(uuid.uuid4()); self.factory.return_value = Mock()
        self.assertEqual(self.engine.reconcile()[0]['state'], 'uncertain'); self.factory.return_value.describe_instances.assert_not_called()

    def test_sdk_uses_explicit_region_endpoint_ca_and_no_proxies(self):
        self.assertEqual(self.client.meta.region_name, 'vcloud-hpc-1'); self.assertEqual(self.client.meta.endpoint_url, e.EXTERNAL)
        self.assertEqual(self.client._endpoint.http_session._verify, self.config['ca_file'])
        self.assertEqual(self.client.meta.config.signature_version, 'v4'); self.assertEqual(self.client.meta.config.proxies, {})
        self.assertEqual(self.client._request_signer._credentials.access_key, 'test-key')

    def test_actual_sigv4_signing_scope(self):
        req = AWSRequest(method='POST', url=e.EXTERNAL, data='Action=DescribeInstances&Version=2016-11-15')
        SigV4Auth(Credentials('test-key', 'test-secret', 'test-session'), 'ec2', 'vcloud-hpc-1').add_auth(req)
        self.assertIn('/vcloud-hpc-1/ec2/aws4_request', req.headers['Authorization'])
        self.assertEqual(req.headers['X-Amz-Security-Token'], 'test-session')

    def test_standard_eks_sts_clients_use_same_explicit_profile(self):
        for name in ('eks', 'sts'):
            client = e.aws_client(name, self.config, NOW)
            self.assertEqual(client.meta.service_model.service_name, name)
            self.assertEqual(client.meta.endpoint_url, e.EXTERNAL); self.assertEqual(client.meta.region_name, e.REGION)
        with self.assertRaises(e.Rejected): e.aws_client('iam', self.config, NOW)

    def test_credential_shape_and_lease_required(self):
        for change in ({'expires_at': NOW}, {'expires_at': NOW + 3601}, {'expires_at': True}, {'expires_at': float('nan')},
                       {'access_key_id': ''}, {'extra': 'bad'}):
            (self.path / 'credentials.json').write_text(json.dumps(self.credential | change))
            with self.subTest(change=change), self.assertRaises(e.Rejected): e.ec2_client(self.config, NOW)

    def test_duplicate_and_nonfinite_json_rejected(self):
        for raw in ('{"a":1,"a":2}', '{"a":NaN}', '[]'):
            with self.assertRaises(e.Rejected): e.json_object(raw)

    def test_agent_answers_without_cloud_or_kubernetes_identity(self):
        agent = e.Agent(self.config, lambda _: {'action': 'answer', 'answer': 'reference answer', 'batch': None})
        self.assertEqual(agent.run({'prompt': 'hello', 'steps': 1})['status'], 'answered')

    def test_agent_only_returns_bounded_proposal(self):
        agent = e.Agent(self.config, lambda _: {'action': 'enqueue_simulation', 'answer': None, 'batch': {'profile': e.PROFILE, 'nodes': 2, 'dataset': 'synthetic'}})
        value = agent.run({'prompt': 'simulate', 'steps': 4})
        self.assertEqual(value['status'], 'proposed'); self.assertFalse(value['execution_enabled']); self.assertEqual(value['queue'], e.QUEUE)

    def test_model_cannot_inject_commands_images_profiles_or_data(self):
        for batch in ({'profile': e.PROFILE, 'nodes': 1, 'dataset': 'synthetic', 'command': 'id'},
                      {'profile': 'other', 'nodes': 1, 'dataset': 'synthetic'},
                      {'profile': e.PROFILE, 'nodes': 1, 'dataset': 'https://untrusted.example'},
                      {'profile': e.PROFILE, 'nodes': 5, 'dataset': 'synthetic'}):
            with self.assertRaises(e.Rejected): e.agent_plan({'action': 'enqueue_simulation', 'answer': None, 'batch': batch}, self.config)

    def test_agent_request_prompt_and_step_bounds(self):
        model = Mock(); agent = e.Agent(self.config, model)
        for req in ({'prompt': 'hello', 'steps': 5}, {'prompt': 'x' * 12001, 'steps': 1}, {'prompt': 'hello', 'steps': True}, {'prompt': 'hi', 'steps': 1, 'tool': 'shell'}):
            with self.assertRaises(e.Rejected): agent.run(req)
        model.assert_not_called()

    def test_transport_never_follows_redirect_or_accepts_http(self):
        with self.assertRaises(e.Rejected): s.NoRedirect().redirect_request(None, None, None, None, None, None)
        with self.assertRaises(e.Rejected): s.trusted_json('http://unsafe.example', 'missing')

    def test_alert_body_is_only_signal_with_exact_cluster_queue(self):
        p = {'status': 'firing', 'alerts': [{'status': 'firing', 'labels': {'alertname': 'VCloudHPCBurstCandidate', 'cluster': e.CLUSTER, 'queue': e.QUEUE}}]}
        self.assertTrue(s.alert_candidate(p)); p['alerts'][0]['labels']['cluster'] = 'other'; self.assertFalse(s.alert_candidate(p))

    def test_peer_requires_single_exact_uri_san(self):
        allowed = ['spiffe://vcloud/platform/apisix']
        self.assertTrue(s.peer_allowed({'subjectAltName': [('URI', allowed[0])]}, allowed))
        self.assertFalse(s.peer_allowed({'subjectAltName': [('DNS', 'apisix')]}, allowed))
        self.assertFalse(s.peer_allowed({'subjectAltName': [('URI', allowed[0]), ('URI', 'spiffe://foreign')]}, allowed))

    def test_environment_flags_are_public_and_exact(self):
        p = self.path / 'config.json'; p.write_text(json.dumps(self.config))
        with patch.dict(os.environ, {'SPINIFEX_OFFLOAD_ENABLED': 'false'}): self.assertFalse(s.config_from_files(p)['offload_enabled'])
        with patch.dict(os.environ, {'SPINIFEX_OFFLOAD_ENABLED': 'yes'}):
            with self.assertRaises(e.Rejected): s.config_from_files(p)


class Manifests(unittest.TestCase):
    def setUp(self):
        self.profile = json.loads((ROOT / 'module-5b/reference-profile.json').read_text())
        self.items = [o for name, text in render.files().items() if name != 'observability/rules.yaml' for o in yaml.safe_load_all(text) if o]

    def test_vendor_hashes_and_nine_crd_schemas_reproduce(self): self.assertEqual(len(m.bundle()['apis']), 9)
    def test_profile_contract(self): m.reference_contract(self.profile)
    def test_reference_rejects_enablement(self):
        with self.assertRaises(ValueError): m.reference_contract(self.profile | {'offload_enabled': True})
    def test_reference_rejects_unknown_fallback(self):
        self.profile['profiles']['spinifex.gpu.a100.80gb.4x']['instance_type'] = 'p4de.24xlarge'
        with self.assertRaises(ValueError): m.reference_contract(self.profile)
    def test_all_generated_contracts(self): self.assertGreater(m.object_contract(self.items), 4)
    def test_zero_quota_guard(self):
        cq = next(o for o in self.items if o['kind'] == 'ClusterQueue'); cq['spec']['resourceGroups'][0]['flavors'][0]['resources'][0]['nominalQuota'] = 1
        with self.assertRaisesRegex(ValueError, 'quota'): m.object_contract(self.items)
    def test_replicas_guard(self):
        next(o for o in self.items if o['kind'] == 'Deployment')['spec']['replicas'] = 1
        with self.assertRaisesRegex(ValueError, 'replicas'): m.object_contract(self.items)
    def test_private_inference_guard(self):
        next(o for o in self.items if o['apiVersion'] == 'serving.knative.dev/v1')['metadata']['labels'].pop('networking.knative.dev/visibility')
        with self.assertRaisesRegex(ValueError, 'private'): m.object_contract(self.items)
    def test_no_hostpath_or_root_exception(self):
        pod = next(o for o in self.items if o['kind'] == 'Deployment')['spec']['template']['spec']
        pod['volumes'].append({'name': 'escape', 'hostPath': {'path': '/'}})
        with self.assertRaisesRegex(ValueError, 'hostPath'): m.object_contract(self.items)
    def test_bridge_rbac_guard(self):
        next(o for o in self.items if o['kind'] == 'Role')['rules'][0]['verbs'].append('create')
        with self.assertRaisesRegex(ValueError, 'RBAC'): m.object_contract(self.items)
    def test_agent_has_no_cloud_or_api_mount(self):
        pod = next(o for o in self.items if o['kind'] == 'Deployment' and o['metadata']['name'] == 'vcloud-deepseek-agent')['spec']['template']['spec']
        pod['volumes'].append({'name': 'creds', 'csi': {'driver': 'secrets-store.csi.k8s.io'}})
        with self.assertRaisesRegex(ValueError, 'credentials'): m.object_contract(self.items)
    def test_argocd_excludes_worker_jobs_and_inference_example(self):
        app = next(o for o in self.items if o['kind'] == 'Application')
        self.assertEqual(app['spec']['source']['path'], 'module-5b/manifests'); self.assertFalse(app['spec']['syncPolicy']['automated']['enabled'])
    def test_wheel_lock_and_dockerfile_match(self):
        lock = json.loads((ROOT / 'module-5b/python-wheels.lock.json').read_text())
        actual = (ROOT / 'module-5b/requirements.txt').read_text().splitlines()
        self.assertEqual(actual, [p['name'] + '==' + p['version'] + ' --hash=sha256:' + p['sha256'] for p in lock['packages']])
        self.assertIn('--require-hashes --no-index', (ROOT / 'module-5b/images/agent-bridge.Dockerfile').read_text())
    def test_controller_manual_quota_and_opt_in_namespaces(self):
        values = yaml.safe_load((ROOT / 'module-5b/values/kueue.yaml').read_text())
        config = yaml.safe_load(values['managerConfig']['controllerManagerConfigYaml'])
        self.assertEqual(config['managedJobsNamespaceSelector']['matchLabels'], render.TARGET)
        self.assertFalse(config['manageJobsWithoutQueueName'])
        self.assertIn({'name': 'MultiKueueManagerQuotaAutomation', 'enabled': False}, values['controllerManager']['featureGates'])

    def test_task_feature_and_csi_credential_guards(self):
        task = next(o for o in self.items if o['kind'] == 'Task')
        next(v for v in task['spec']['steps'][0]['env'] if v['name'] == 'SPINIFEX_OFFLOAD_ENABLED')['value'] = 'true'
        with self.assertRaisesRegex(ValueError, 'Task feature'): m.object_contract(self.items)
        task['spec']['steps'][0]['env'][0]['value'] = 'false'
        next(o for o in self.items if o['kind'] == 'SecretProviderClass')['spec']['secretObjects'] = [{'secretName': 'leak'}]
        with self.assertRaisesRegex(ValueError, 'synchronization'): m.object_contract(self.items)


class LocalMTLS(unittest.TestCase):
    """Real TLS sockets on loopback, ephemeral test certificates, no external calls."""
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(); cls.directory = Path(cls.temp.name)
        openssl = shutil.which('openssl') or 'C:/Program Files/Git/usr/bin/openssl.exe'
        def run(*args):
            subprocess.run([openssl, *args], cwd=cls.directory, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        run('req', '-x509', '-newkey', 'rsa:2048', '-nodes', '-keyout', 'ca.key', '-out', 'ca.crt', '-days', '1', '-subj', '/CN=HPC test CA',
            '-addext', 'basicConstraints=critical,CA:TRUE', '-addext', 'keyUsage=critical,keyCertSign,cRLSign')
        for name, extension in [('server', 'subjectAltName=DNS:localhost,IP:127.0.0.1\nextendedKeyUsage=serverAuth'),
                                ('good', 'subjectAltName=URI:spiffe://vcloud/hpc/tekton-trigger\nextendedKeyUsage=clientAuth'),
                                ('bad', 'subjectAltName=URI:spiffe://foreign/client\nextendedKeyUsage=clientAuth')]:
            (cls.directory / (name + '.ext')).write_text(extension + '\nbasicConstraints=critical,CA:FALSE\nkeyUsage=critical,digitalSignature,keyEncipherment\nauthorityKeyIdentifier=keyid,issuer\nsubjectKeyIdentifier=hash')
            run('req', '-newkey', 'rsa:2048', '-nodes', '-keyout', name + '.key', '-out', name + '.csr', '-subj', '/CN=' + name)
            run('x509', '-req', '-in', name + '.csr', '-CA', 'ca.crt', '-CAkey', 'ca.key', '-CAcreateserial',
                '-out', name + '.crt', '-days', '1', '-extfile', name + '.ext')
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER); context.minimum_version = ssl.TLSVersion.TLSv1_3; context.verify_mode = ssl.CERT_REQUIRED
        context.load_cert_chain(str(cls.directory / 'server.crt'), str(cls.directory / 'server.key')); context.load_verify_locations(str(cls.directory / 'ca.crt'))
        config = json.loads((ROOT / 'module-5b/reference-profile.json').read_text())
        cls.handler = s.service(config, 'capacity'); cls.server = s.MTLSServer(('127.0.0.1', 0), cls.handler, context)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True); cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown(); cls.server.server_close(); cls.thread.join(); cls.temp.cleanup()

    def call(self, identity='good', body=b'{}', path='/hooks/capacity', content_type='application/json'):
        context = ssl.create_default_context(cafile=str(self.directory / 'ca.crt'))
        if identity: context.load_cert_chain(str(self.directory / (identity + '.crt')), str(self.directory / (identity + '.key')))
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), urllib.request.HTTPSHandler(context=context))
        req = urllib.request.Request('https://127.0.0.1:' + str(self.server.server_port) + path, data=body, headers={'Content-Type': content_type})
        with opener.open(req, timeout=3) as response: return response.status, json.load(response)

    def test_valid_identity_gets_disabled_without_provider_io(self): self.assertEqual(self.call(), (202, {'status': 'disabled', 'offload_enabled': False}))
    def test_signed_foreign_identity_is_forbidden(self):
        with self.assertRaises(urllib.error.HTTPError) as exc: self.call('bad')
        self.assertEqual(exc.exception.code, 403)
    def test_missing_certificate_fails_tls(self):
        with self.assertRaises((urllib.error.URLError, ssl.SSLError, ConnectionResetError)): self.call(None)
    def test_duplicate_json_rejected(self):
        with self.assertRaises(urllib.error.HTTPError) as exc: self.call(body=b'{"a":1,"a":2}')
        self.assertEqual(exc.exception.code, 422)
    def test_size_limit(self):
        with self.assertRaises(urllib.error.HTTPError) as exc: self.call(body=b'x' * 65537)
        self.assertEqual(exc.exception.code, 422)
    def test_wrong_content_type(self):
        with self.assertRaises(urllib.error.HTTPError) as exc: self.call(content_type='text/plain')
        self.assertEqual(exc.exception.code, 422)
    def test_unknown_endpoint(self):
        with self.assertRaises(urllib.error.HTTPError) as exc: self.call(path='/admin')
        self.assertEqual(exc.exception.code, 404)
    def test_actual_alertmanager_payload_is_inert_when_disabled(self):
        body = json.dumps({'version': '4', 'status': 'firing', 'alerts': [{'status': 'firing', 'labels': {'alertname': 'VCloudHPCBurstCandidate', 'cluster': e.CLUSTER, 'queue': e.QUEUE}}]}).encode()
        self.assertEqual(self.call(body=body, path='/hooks/alerts')[1]['status'], 'disabled')


if __name__ == '__main__': unittest.main(verbosity=2)
