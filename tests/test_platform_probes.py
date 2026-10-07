"""Probe policy boundaries and node-origin acceptance using a controlled CLI fixture."""
import json
import os
import shutil
from pathlib import Path
import subprocess
import tempfile
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[1]
BUNDLE = ROOT / 'deploy/network/platform-probes'
EXPECTED = {'cloudnative-pg': 9443, 'argocd-repo-server': 8084, 'argocd-application-controller': 8082}
PORTS = {9443, 8084, 8082}
DEPENDENCY_EGRESS = [{'toEntities': ['kube-apiserver'],
                      'toPorts': [{'ports': [{'port': '443', 'protocol': 'TCP'}]}]}]

KUBECTL = r'''#!/usr/bin/env python3
import json, os, pathlib, sys, yaml
args=sys.argv[1:]; root=pathlib.Path(os.environ['FIXTURE_DIR'])
with (root/'calls.jsonl').open('a') as f: f.write(json.dumps(args)+'\n')
scenario=os.environ.get('SCENARIO','healthy')
if 'current-context' in args: print('fixture-context')
elif 'nodes' in args:
 nodes={'items':[{'metadata':{'name':'local-node','labels':{'vcloud.io/environment':'local-validation'}},'spec':{'podCIDRs':['10.42.0.0/24']},'status':{'addresses':[
  {'type':'InternalIP','address':'192.168.1.9'}, {'type':'ExternalIP','address':'203.0.113.9'}]}},
  {'metadata':{'name':'remote-node','labels':{'vcloud.io/environment':'local-validation'}},'spec':{'podCIDRs':['2001:db8::/64']},'status':{'addresses':[{'type':'InternalIP','address':'2001:db8::2'}]}}]}
 if scenario=='missing-cidr':
  for node in nodes['items']: node['spec']={}
 if scenario=='invalid-cidr': nodes['items'][0]['spec']['podCIDRs']=['0.0.0.0/0']
 if scenario=='production-node': nodes['items'][1]['metadata']['labels']['vcloud.io/environment']='production'
 print(json.dumps(nodes))
elif 'pods' in args:
 count=root/'count'; n=int(count.read_text())+1 if count.exists() else 1; count.write_text(str(n))
 items=[]
 for label,ip in [('cloudnative-pg','10.42.0.157'),('argocd-repo-server','10.42.0.193'),('argocd-application-controller','10.42.0.65')]:
  items.append({'metadata':{'name':label+'-fixture','uid':label,'labels':{'app.kubernetes.io/name':label}},
   'spec':{'nodeName':'remote-node' if scenario=='wrong-node' else 'local-node'},
   'status':{'phase':'Running','podIP':ip,'containerStatuses':[{'restartCount':n if scenario=='restarting' else 1}],
    'conditions':[{'type':'Ready','status':'False' if scenario=='unready' else 'True'}]}})
 if scenario=='empty': items=[]
 if scenario=='missing-ip': items[0]['status'].pop('podIP')
 if scenario=='extra-pod':
  second=json.loads(json.dumps(items[1]));second['metadata'].update(name='repo-second',uid='repo-second');second['status']['podIP']='10.42.0.198';items.append(second)
 print(json.dumps({'items':items}))
elif 'get' in args and ('deployment' in args or 'statefulset' in args):
 if scenario=='missing-rollout-target': sys.exit(1)
 kind='deployment' if 'deployment' in args else 'statefulset'
 if kind=='statefulset' and args[-1]=='json':
  print(json.dumps({'spec':{'updateStrategy':{
   'type':'OnDelete' if scenario=='on-delete-controller' else 'RollingUpdate',
   'rollingUpdate':{'partition':1 if scenario=='partitioned-controller' else 0}}}}))
 else: print(kind+'/'+args[args.index(kind)+1])
elif 'rollout' in args:
 if scenario=='restart-fails' and 'restart' in args and 'deployment' in args: sys.exit(17)
 if scenario=='statefulset-restart-fails' and 'restart' in args and 'statefulset' in args: sys.exit(18)
 if scenario=='rollout-status-fails' and 'status' in args: sys.exit(19)
 print('rollout fixture completed')
elif 'create' in args:
 docs=list(yaml.safe_load_all(pathlib.Path(args[args.index('-f')+1]).read_text()))
 if scenario=='cidr-set-response':
  for doc in docs:
   if doc['kind']=='CiliumNetworkPolicy':
    doc['spec']['egress']=[{'toEntities':['kube-apiserver'],'toPorts':[{'ports':[{'port':'443','protocol':'TCP'}]}]}]
    for rule in doc['spec']['ingress']:
     if 'fromCIDR' in rule: rule['fromCIDRSet']=[{'cidr':cidr} for cidr in rule.pop('fromCIDR')]
 if scenario=='list-response': print(json.dumps({'apiVersion':'v1','kind':'List','items':docs}))
 else:
  for doc in docs: print(json.dumps(doc))
elif 'apply' in args:
 path=pathlib.Path(args[args.index('-f')+1])
 files=sorted(path.glob('*.yaml')) if path.is_dir() else [path]
 docs=[doc for file in files for doc in yaml.safe_load_all(file.read_text())]
 if '--dry-run=server' in args:
  if scenario=='reject' and path.name=='fallback.json': sys.exit(1)
  if scenario=='policy-dry-run-fails' and path.is_dir(): sys.exit(16)
 else:
  if scenario=='policy-apply-fails' and path.is_dir(): sys.exit(15)
  with (root/'applied.jsonl').open('a') as f: f.write(json.dumps(docs)+'\n')
 print('validated' if '--dry-run=server' in args else 'configured')
elif 'events' in args: print('Warning: fixture probe failed')
else: sys.exit('Unexpected kubectl operation: '+repr(args))
'''

CURL = r'''#!/usr/bin/env python3
import json,os,pathlib,sys
with (pathlib.Path(os.environ['FIXTURE_DIR'])/'curl.jsonl').open('a') as f: f.write(json.dumps(sys.argv[1:])+'\n')
if os.environ.get('SCENARIO')=='curl-timeout': sys.exit(28)
print('503' if os.environ.get('SCENARIO')=='http-503' else '200',end='')
'''


class PolicyTests(unittest.TestCase):
    def test_cilium_ingress_is_limited_to_three_workloads_and_probe_ports(self):
        obj = yaml.safe_load((BUNDLE/'cilium-platform-probes.yaml').read_text())
        self.assertEqual(obj['apiVersion'], 'cilium.io/v2')
        self.assertEqual(obj['metadata']['namespace'], 'platform-services')
        self.assertEqual(obj['metadata']['labels']['vcloud.io/profile'], 'wsl-local')
        spec = obj['spec']; expression = spec['endpointSelector']['matchExpressions'][0]
        self.assertEqual(expression['key'], 'app.kubernetes.io/name')
        self.assertEqual(expression['operator'], 'In')
        self.assertEqual(set(expression['values']), set(EXPECTED))
        self.assertEqual(spec['ingress'][0]['fromEntities'], ['host', 'remote-node', 'health', 'world', 'cluster'])
        cidr_rule = spec['ingress'][1]
        self.assertEqual(cidr_rule.get('fromCIDR', [entry['cidr'] for entry in cidr_rule.get('fromCIDRSet', [])]),
                         ['10.42.0.0/16'])
        for rule in spec['ingress']:
            ports = rule['toPorts'][0]['ports']
            self.assertEqual({int(p['port']) for p in ports}, PORTS)
            self.assertTrue(all(p['protocol'] == 'TCP' for p in ports))

    def test_controller_dependencies_do_not_allow_general_world_egress(self):
        # Probe ingress does not grant dependency egress to all three workloads.
        # Component policies own their distinct DNS/API/Redis flows.
        self.assertNotIn('egress', yaml.safe_load((BUNDLE/'cilium-platform-probes.yaml').read_text())['spec'])
        import sys
        sys.path.insert(0, str(ROOT/'tools'))
        import wsl_platform
        policies = {obj['metadata']['name']: obj for obj in wsl_platform.network()}
        for name in ('vcloud-wsl-operator', 'vcloud-wsl-argo-controller', 'vcloud-wsl-argo-repo'):
            rules = policies[name]['spec']['egress']
            self.assertTrue(rules)
            self.assertTrue(all(not {'world', 'cluster', 'all'} & set(rule.get('toEntities', [])) for rule in rules))
            self.assertTrue(all('toCIDR' not in rule and 'toCIDRSet' not in rule for rule in rules))
            for rule in rules:
                for peer in rule.get('toEndpoints', []):
                    self.assertEqual(peer['matchLabels']['k8s:io.kubernetes.pod.namespace'], 'platform-services')
        controller = policies['vcloud-wsl-argo-controller']['spec']['egress']
        self.assertTrue(any(rule.get('toEntities') == ['kube-apiserver'] for rule in controller))
        self.assertTrue(any(port == {'port': '6379', 'protocol': 'TCP'}
                            for rule in controller for entry in rule['toPorts'] for port in entry['ports']))
        repo = policies['vcloud-wsl-argo-repo']['spec']['egress']
        self.assertEqual([peer for rule in repo for peer in rule.get('toFQDNs', [])], [{'matchName': 'github.com'}])

    def test_native_fallback_allows_sources_only_on_the_three_probe_ports(self):
        objects = list(yaml.safe_load_all((BUNDLE/'k8s-platform-probes.yaml').read_text()))
        self.assertEqual(len(objects), 1)
        for obj in objects:
            self.assertEqual(obj['apiVersion'], 'networking.k8s.io/v1')
            self.assertEqual(obj['metadata']['namespace'], 'platform-services')
            spec = obj['spec']; expression = spec['podSelector']['matchExpressions'][0]
            self.assertEqual(set(expression['values']), set(EXPECTED))
            self.assertEqual(spec['policyTypes'], ['Ingress'])
            self.assertNotIn('egress', spec)
            self.assertNotIn('from', spec['ingress'][0])
            self.assertEqual({p['port'] for p in spec['ingress'][0]['ports']}, PORTS)
            self.assertTrue(all(p['protocol'] == 'TCP' for p in spec['ingress'][0]['ports']))

    def test_wsl_bootstrap_uses_the_same_cilium_source(self):
        self.assertIn("ROOT/'deploy/network/platform-probes/cilium-platform-probes.yaml'",
                      (ROOT/'tools/wsl_platform.py').read_text())


class ScriptTests(unittest.TestCase):
    def invoke(self, scenario='healthy', arguments=(), script='apply-and-verify.sh', overrides=None):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for name, content in [('kubectl', KUBECTL), ('curl', CURL),
                ('ip', '#!/usr/bin/env python3\nprint(\'[ {"addr_info": [{"local": "192.168.1.9"}]} ]\')\n')]:
                path = root/name; path.write_text(content); path.chmod(0o755)
            env = os.environ.copy()
            env.update(FIXTURE_DIR=temp, SCENARIO=scenario, KUBE_CONTEXT='fixture-context',
                       ROLLOUT_TIMEOUT_SECONDS='180',
                       TIMEOUT_SECONDS='6' if scenario in ('healthy', 'list-response', 'extra-pod', 'cidr-set-response') else '2',
                       POLL_SECONDS='1', PATH=temp+os.pathsep+env['PATH'])
            env.pop('PROBE_NODE_NAME', None)
            env.update(overrides or {})
            bash = shutil.which(env.get('BASH_BINARY', 'bash'))
            if scenario == 'missing-jq':
                (root/'dirname').symlink_to(shutil.which('dirname'))
                env['PATH'] = temp
            result = subprocess.run([bash, str(BUNDLE/script), *arguments], cwd=ROOT,
                                    env=env, capture_output=True, text=True, timeout=15)
            logs = {}
            for name in ('calls', 'applied', 'curl'):
                file = root/(name+'.jsonl')
                logs[name] = [json.loads(line) for line in file.read_text().splitlines()] if file.exists() else []
            return result, logs

    def test_apply_injects_detected_pod_cidrs_and_checks_all_three_urls(self):
        result, logs = self.invoke()
        self.assertEqual(result.returncode, 0, result.stdout+result.stderr)
        self.assertEqual(len(logs['applied']), 2)
        cilium = logs['applied'][0][0]
        rule = cilium['spec']['ingress'][1]
        self.assertEqual(set(rule.get('fromCIDR', [c['cidr'] for c in rule.get('fromCIDRSet', [])])),
                         {'10.42.0.0/16', '10.42.0.0/24', '2001:db8::/64'})
        self.assertEqual(cilium['spec'].get('egress'),
                         yaml.safe_load((BUNDLE/'cilium-platform-probes.yaml').read_text())['spec'].get('egress'))
        policies = logs['applied'][1][0]['items']
        for policy in policies:
            self.assertNotIn('from', policy['spec']['ingress'][0])
            self.assertEqual(json.loads(policy['metadata']['annotations']['vcloud.io/detected-node-pod-cidrs']),
                             ['10.42.0.0/24', '2001:db8::/64'])
        self.assertGreaterEqual(len(logs['curl']), 6)
        for call in logs['curl']:
            self.assertEqual(call[call.index('--max-time')+1], '5')
            self.assertIn('-k', call); self.assertIn('-v', call)
            self.assertEqual(call[call.index('--noproxy')+1], '*')
        self.assertIn('https://10.42.0.157:9443/readyz', [c[-1] for c in logs['curl']])
        self.assertIn('http://10.42.0.193:8084/healthz?full=true', [c[-1] for c in logs['curl']])
        self.assertIn('http://10.42.0.65:8082/healthz', [c[-1] for c in logs['curl']])

    def test_dynamic_cidrs_also_support_from_cidr_set_without_losing_egress(self):
        result, logs = self.invoke('cidr-set-response')
        self.assertEqual(result.returncode, 0, result.stdout+result.stderr)
        cilium = logs['applied'][0][0]
        self.assertEqual({c['cidr'] for c in cilium['spec']['ingress'][1]['fromCIDRSet']},
                         {'10.42.0.0/16', '10.42.0.0/24', '2001:db8::/64'})
        self.assertEqual(cilium['spec']['egress'], DEPENDENCY_EGRESS)

    def test_plan_does_not_apply_or_curl(self):
        result, logs = self.invoke(arguments=['--plan'])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(logs['applied']); self.assertFalse(logs['curl'])
        self.assertIn('10.42.0.0/24', result.stdout)
        self.assertIn('"world"', result.stdout)

    def test_kubectl_list_and_json_stream_both_render_one_complete_list(self):
        for scenario in ('healthy', 'list-response'):
            with self.subTest(scenario=scenario):
                result, logs = self.invoke(scenario, ['--kubernetes-only', '--plan'])
                self.assertEqual(result.returncode, 0, result.stderr)
                rendered = json.loads(result.stdout[result.stdout.index('\n{')+1:])
                self.assertEqual(rendered['kind'], 'List')
                self.assertEqual(len(rendered['items']), 1)
                self.assertFalse(logs['applied'])

    def test_verify_only_does_not_apply(self):
        result, logs = self.invoke(arguments=['--verify-only'])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(logs['applied'])
        self.assertFalse(any('create' in call for call in logs['calls']))

    def test_native_only_does_not_require_cilium(self):
        result, logs = self.invoke(arguments=['--kubernetes-only'])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(len(logs['applied']), 1)
        self.assertEqual(logs['applied'][0][0]['kind'], 'List')

    def test_server_rejection_occurs_before_any_policy_write(self):
        result, logs = self.invoke('reject')
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(logs['applied'])

    def test_missing_jq_or_missing_invalid_pod_cidrs_fail_before_apply(self):
        for scenario in ('missing-jq', 'missing-cidr', 'invalid-cidr', 'production-node'):
            with self.subTest(scenario=scenario):
                result, logs = self.invoke(scenario)
                self.assertNotEqual(result.returncode, 0)
                self.assertFalse(logs['applied'])
                if scenario == 'missing-jq':
                    self.assertIn('Missing dependency: jq', result.stderr)
                    self.assertFalse(logs['calls'])

    def test_every_local_replica_is_verified(self):
        result, logs = self.invoke('extra-pod', ['--verify-only'])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('http://10.42.0.198:8084/healthz?full=true', [c[-1] for c in logs['curl']])
        self.assertGreaterEqual(len(logs['curl']), 8)

    def test_wrong_node_or_empty_pods_fail_before_any_policy_write(self):
        for scenario in ('wrong-node', 'empty'):
            with self.subTest(scenario=scenario):
                result, logs = self.invoke(scenario)
                self.assertNotEqual(result.returncode, 0)
                self.assertFalse(logs['applied']); self.assertFalse(logs['curl'])

    def test_http_503_and_timeouts_cannot_be_reported_as_healthy(self):
        for scenario in ('http-503', 'curl-timeout'):
            with self.subTest(scenario=scenario):
                result, logs = self.invoke(scenario, ['--verify-only'])
                self.assertNotEqual(result.returncode, 0)
                self.assertTrue(logs['curl'])
                self.assertNotIn('PASS:', result.stdout)

    def test_unready_missing_ip_and_restarts_cannot_pass(self):
        for scenario in ('unready', 'missing-ip', 'restarting'):
            with self.subTest(scenario=scenario):
                result, _ = self.invoke(scenario, ['--verify-only'])
                self.assertNotEqual(result.returncode, 0)
                self.assertNotIn('PASS:', result.stdout)


class RecoveryTests(unittest.TestCase):
    invoke = ScriptTests.invoke

    @staticmethod
    def rollouts(logs):
        return [call[call.index('rollout'):] for call in logs['calls'] if 'rollout' in call]

    def test_policy_apply_precedes_both_restarts_and_then_health_validation(self):
        result, logs = self.invoke(script='recover.sh')
        self.assertEqual(result.returncode, 0, result.stdout+result.stderr)
        self.assertEqual(self.rollouts(logs), [
            ['rollout', 'restart', 'deployment', 'argocd-repo-server', '-n', 'platform-services'],
            ['rollout', 'restart', 'statefulset', 'argocd-application-controller', '-n', 'platform-services'],
            ['rollout', 'status', 'deployment/argocd-repo-server', '-n', 'platform-services', '--timeout=180s'],
            ['rollout', 'status', 'statefulset/argocd-application-controller', '-n', 'platform-services', '--timeout=180s']])
        writes = [(i, call) for i, call in enumerate(logs['calls'])
                  if 'apply' in call and '--dry-run=server' not in call]
        restart_positions = [i for i, call in enumerate(logs['calls']) if 'restart' in call]
        status_positions = [i for i, call in enumerate(logs['calls']) if 'status' in call]
        self.assertEqual(len(writes), 3)  # directory, dynamic Cilium, dynamic native
        self.assertEqual(writes[0][1][-2:], ['-f', 'deploy/network/platform-probes/'])
        self.assertLess(writes[0][0], min(restart_positions))
        self.assertLess(max(restart_positions), min(status_positions))
        self.assertLess(max(status_positions), writes[1][0])
        self.assertEqual(len(logs['applied'][0]), 2)
        self.assertEqual({obj['kind'] for obj in logs['applied'][0]}, {'CiliumNetworkPolicy', 'NetworkPolicy'})
        self.assertGreaterEqual(len(logs['curl']), 6)
        self.assertIn('PASS:', result.stdout)
        for call in logs['calls']:
            self.assertEqual(call[:2], ['--context', 'fixture-context'])

    def test_plan_never_applies_restarts_watches_or_curls(self):
        result, logs = self.invoke(script='recover.sh', arguments=['--plan'])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('no changes made', result.stdout)
        self.assertFalse(logs['applied']); self.assertFalse(logs['curl'])
        self.assertFalse(self.rollouts(logs))

    def test_dependencies_locality_and_lab_profile_fail_before_mutations(self):
        for scenario in ('missing-jq', 'production-node', 'wrong-node', 'missing-cidr', 'missing-rollout-target',
                         'on-delete-controller', 'partitioned-controller'):
            with self.subTest(scenario=scenario):
                result, logs = self.invoke(scenario, script='recover.sh')
                self.assertNotEqual(result.returncode, 0)
                self.assertFalse(logs['applied']); self.assertFalse(self.rollouts(logs))
                self.assertFalse(logs['curl'])

    def test_policy_validation_or_apply_failure_prevents_any_restart(self):
        for scenario in ('policy-dry-run-fails', 'policy-apply-fails'):
            with self.subTest(scenario=scenario):
                result, logs = self.invoke(scenario, script='recover.sh')
                self.assertNotEqual(result.returncode, 0)
                self.assertIn('network-policy-apply', result.stderr)
                self.assertFalse(logs['applied']); self.assertFalse(self.rollouts(logs))
                self.assertFalse(logs['curl'])

    def test_restart_or_rollout_failure_stops_before_health_validation(self):
        for scenario, expected_count in [('restart-fails', 1), ('statefulset-restart-fails', 2),
                                         ('rollout-status-fails', 3)]:
            with self.subTest(scenario=scenario):
                result, logs = self.invoke(scenario, script='recover.sh')
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(len(self.rollouts(logs)), expected_count)
                self.assertEqual(len(logs['applied']), 1)
                self.assertFalse(logs['curl']); self.assertNotIn('PASS:', result.stdout)

    def test_http_failure_after_successful_rollouts_still_fails_recovery(self):
        result, logs = self.invoke('http-503', script='recover.sh')
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(len(self.rollouts(logs)), 4)
        self.assertTrue(logs['curl'])
        self.assertIn('live-health-validation', result.stderr)
        self.assertNotIn('PASS:', result.stdout)

    def test_bad_arguments_or_rollout_timeout_fail_before_api_access(self):
        for arguments, timeout in [(['--unknown'], '180'), (['--plan', '--plan'], '180'),
                                    ([], '0'), ([], '901'), ([], 'invalid')]:
            with self.subTest(arguments=arguments, timeout=timeout):
                result, logs = self.invoke(script='recover.sh', arguments=arguments,
                                           overrides={'ROLLOUT_TIMEOUT_SECONDS': timeout})
                self.assertNotEqual(result.returncode, 0)
                self.assertFalse(logs['calls'])

    def test_make_recovery_and_read_only_verification_targets(self):
        expected = {
            'wsl-platform-recovery-plan': 'deploy/network/platform-probes/recover.sh --plan',
            'wsl-platform-recover': 'deploy/network/platform-probes/recover.sh',
            'wsl-platform-probe-verify': 'deploy/network/platform-probes/apply-and-verify.sh --verify-only',
            'wsl-platform-probe-test': '-m unittest discover -s tests -p test_platform_probes.py -v'}
        for target, command in expected.items():
            with self.subTest(target=target):
                result = subprocess.run(['make', '--no-print-directory', '-n', target], cwd=ROOT,
                                        capture_output=True, text=True, timeout=10)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn(command, result.stdout)
                self.assertNotIn('sudo', result.stdout)


if __name__ == '__main__':
    unittest.main()
