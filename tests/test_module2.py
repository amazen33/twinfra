"""Executable checks for offline manifests, policy regressions and resource scaling."""
import copy
from datetime import datetime, timezone
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import module2 as m

loader = importlib.util.spec_from_file_location('cnpg_scaler', ROOT / 'module-2/chart/files/scaler.py')
scaler = importlib.util.module_from_spec(loader)
loader.loader.exec_module(scaler)


class RenderedContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.args = SimpleNamespace(build=Path(cls.temp.name), helm=os.environ.get('HELM','helm'),
                                   kubeconform=os.environ.get('KUBECONFORM','kubeconform'))
        cls.values = m.values(ROOT / 'module-2/site-values.example.yaml')
        m.render(cls.args, cls.values)
        cls.objects = list(m.flatten(o for file in ('cilium.yaml','foundation.yaml','apisix-dependency.yaml')
                                     for o in yaml.safe_load_all((cls.args.build / file).read_text())))

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def change(self, kind, name, mutate, error):
        objects = copy.deepcopy(self.objects)
        obj = next(o for o in objects if o['kind'] == kind and o['metadata']['name'] == name)
        mutate(obj)
        with self.assertRaisesRegex(ValueError, error):
            m.audit(objects, self.values)

    def test_complete_render_passes_node_and_application_contracts(self):
        report = m.audit(self.objects, self.values)
        self.assertEqual(report['violations'], [])
        self.assertEqual(len(report['acceptedExceptions']), 3)

    def test_unknown_cnpg_field_is_rejected_by_offline_schema(self):
        obj = copy.deepcopy(next(o for o in self.objects if o['kind'] == 'Cluster'))
        obj['spec']['madeUpAutoscaling'] = True
        path = self.args.build / 'bad.yaml'; m.dump(path, obj)
        result = subprocess.run([self.args.kubeconform, '-strict', '-schema-location',
            str(ROOT / 'module-2/schemas/{{.Group}}/{{.ResourceKind}}_{{.ResourceAPIVersion}}.json'), str(path)], capture_output=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(b'madeUpAutoscaling', result.stdout)

    def test_actual_helm_post_renderer_accepts_reviewed_profile(self):
        result = subprocess.run([self.args.helm,'template','cilium',str(ROOT / 'module-2/vendor/cilium-1.20.2.tgz'),
            '--namespace','kube-system','--kube-version','1.36.5','--values',str(self.args.build / 'cilium-values.yaml'),
            '--post-renderer',sys.executable,'--post-renderer-args',str(ROOT / 'tools/helm_node_guard.py'),
            '--post-renderer-args=--kubeconform','--post-renderer-args',self.args.kubeconform],capture_output=True)
        self.assertEqual(result.returncode,0,result.stderr.decode())
        self.assertIn(b'kind: DaemonSet',result.stdout)

    def test_actual_helm_post_renderer_rejects_image_drift(self):
        result = subprocess.run([self.args.helm,'template','cilium',str(ROOT / 'module-2/vendor/cilium-1.20.2.tgz'),
            '--namespace','kube-system','--kube-version','1.36.5','--values',str(self.args.build / 'cilium-values.yaml'),
            '--set','image.tag=v1.20.1','--set','image.useDigest=false',
            '--post-renderer',sys.executable,'--post-renderer-args',str(ROOT / 'tools/helm_node_guard.py'),
            '--post-renderer-args=--kubeconform','--post-renderer-args',self.args.kubeconform],capture_output=True)
        self.assertNotEqual(result.returncode,0)
        self.assertIn(b'drift from approved',result.stderr)

    def test_missing_schema_fails_instead_of_skipping(self):
        path = self.args.build / 'unknown.yaml'
        m.dump(path, {'apiVersion':'unknown.example/v1','kind':'Unreviewed','metadata':{'name':'x'}})
        result = subprocess.run([self.args.kubeconform,'-strict','-schema-location',
            str(ROOT / 'module-2/schemas/{{.Group}}/{{.ResourceKind}}_{{.ResourceAPIVersion}}.json'), str(path)], capture_output=True)
        self.assertNotEqual(result.returncode, 0)

    def test_cilium_node_mount_drift_is_rejected(self):
        self.change('DaemonSet','cilium',lambda o: o['spec']['template']['spec']['volumes'][0].update(hostPath={'path':'/','type':'Directory'}),'drift from approved')

    def test_function_root_is_rejected(self):
        self.change('Service','secure-function',lambda o: o['spec']['template']['spec']['securityContext'].update(runAsUser=0),'root execution')

    def test_function_host_path_is_rejected(self):
        self.change('Service','secure-function',lambda o: o['spec']['template']['spec']['volumes'].append({'name':'escape','hostPath':{'path':'/'}}),'forbidden hostPath')

    def test_privileged_application_is_rejected(self):
        self.change('Service','secure-function',lambda o: o['spec']['template']['spec']['containers'][0]['securityContext'].update(privileged=True),'privileged containers')

    def test_function_privilege_escalation_is_rejected(self):
        self.change('Service','secure-function',lambda o: o['spec']['template']['spec']['containers'][0]['securityContext'].update(allowPrivilegeEscalation=True),'Restricted application')

    def test_latest_image_is_rejected(self):
        self.change('Service','secure-function',lambda o: o['spec']['template']['spec']['containers'][0].update(image='registry.vcloud.example.com/function:latest'),'not pinned')

    def test_unvetted_local_pv_is_rejected(self):
        self.change('PersistentVolume','vcloud-function-data',lambda o: o['spec']['local'].update(path='/etc'),'exact storage plan')

    def test_local_pv_node_drift_is_rejected(self):
        self.change('PersistentVolume','vcloud-function-data',lambda o: o['spec']['nodeAffinity']['required']['nodeSelectorTerms'][0]['matchExpressions'][0].update(values=['another-node']),'retention/node/claim')

    def test_absent_deny_all_is_rejected(self):
        objects = [o for o in self.objects if not (o['kind'] == 'CiliumNetworkPolicy' and o['metadata']['name'] == 'baseline-deny-all' and o['metadata']['namespace'] == 'workload-apps')]
        with self.assertRaisesRegex(ValueError, 'deny-all'):
            m.audit(objects, self.values)

    def test_dns_cannot_expand_to_entire_namespace(self):
        self.change('CiliumNetworkPolicy','allow-internal-dns',lambda o: o['spec']['egress'][0]['toEndpoints'][0]['matchLabels'].pop('k8s:k8s-app'),'limited to kube-dns')

    def test_hpc_peer_group_cannot_be_removed(self):
        self.change('CiliumNetworkPolicy','hpc-bounded-ssh-mpi',lambda o: o['spec']['ingress'][0]['fromEndpoints'][0]['matchLabels'].pop('k8s:vcloud.io/hpc-job-group'),'ports/peers')

    def test_vpa_cannot_evict_database(self):
        self.change('VerticalPodAutoscaler','postgres-resources',lambda o: o['spec']['updatePolicy'].update(updateMode='Auto'),'must not resize')

    def test_gateway_idp_tls_cannot_be_disabled(self):
        self.change('ApisixRoute','secure-function',lambda o: o['spec']['http'][0]['plugins'][1]['config'].update(ssl_verify=False),'verify bearer tokens')

    def test_gateway_audience_is_required(self):
        self.change('ApisixRoute','secure-function',lambda o: o['spec']['http'][0]['plugins'][1]['config']['claim_validator']['audience'].update(required=False),'required audience')

    def test_gateway_upstream_ca_verification_cannot_be_disabled(self):
        obj = next(o for o in self.objects if o['kind'] == 'ConfigMap' and o['metadata']['name'] == 'apisix')
        config = yaml.safe_load(obj['data']['config.yaml'])
        config['nginx_config']['http_configuration_snippet'] += '\nproxy_ssl_verify off;'
        with self.assertRaisesRegex(ValueError,'upstream TLS'):
            m.apisix_runtime_contract(config)

    def test_gateway_admin_tls_cannot_be_disabled(self):
        obj = next(o for o in self.objects if o['kind'] == 'ConfigMap' and o['metadata']['name'] == 'apisix')
        config = yaml.safe_load(obj['data']['config.yaml'])
        config['deployment']['admin']['https_admin'] = False
        with self.assertRaisesRegex(ValueError,'authenticated TLS'):
            m.apisix_runtime_contract(config)

    def test_argo_floating_revision_is_rejected(self):
        self.change('Application','vcloud-root',lambda o: o['spec']['source'].update(targetRevision='main'),'Argo source pin')

    def test_argo_pruning_stateful_intent_is_rejected(self):
        self.change('Application','vcloud-database',lambda o: o['spec']['syncPolicy']['automated'].update(prune=True),'stateful pruning')

    def test_chart_null_init_array_normalizes_without_changing_node_policy(self):
        obj = next(o for o in self.objects if o['kind'] == 'Deployment' and o['metadata']['name'] == 'apisix')
        self.assertEqual(m.normalize_pods([obj])[0]['spec']['template']['spec']['initContainers'], [])
        self.assertEqual(m.sha(ROOT / 'security/node-exceptions.json'), 'd9799b19ff5fb101cde1870840f29b6d54d6e6cff2c22b389a62d9adfe7cd253')


class Scaling(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026,10,6,10,tzinfo=timezone.utc).timestamp()
        self.policy = m.values(ROOT / 'module-2/site-values.example.yaml')['database']['autoscaler']
        self.cluster = {'metadata':{'name':'vcloud-postgres','resourceVersion':'123','annotations':{'kept':'yes'}},
            'spec':{'instances':1,'resources':{'requests':{'cpu':'1','memory':'2Gi'},'limits':{'cpu':'1','memory':'2Gi'}}},
            'status':{'readyInstances':1,'instances':1,'phase':'Cluster in healthy state','currentPrimary':'db-1','targetPrimary':'db-1'}}
        self.vpa = {'metadata':{'managedFields':[{'subresource':'status','time':'2026-10-06T10:00:00Z'}]},
            'spec':{'targetRef':{'apiVersion':'postgresql.cnpg.io/v1','kind':'Cluster','name':'vcloud-postgres'},'updatePolicy':{'updateMode':'Off'}},
            'status':{'conditions':[{'type':'RecommendationProvided','status':'True'}],
                      'recommendation':{'containerRecommendations':[{'containerName':'postgres','target':{'cpu':'1800m','memory':'3Gi'}}]}}}

    def evaluate(self):
        return scaler.plan(self.cluster,self.vpa,self.policy,self.now)

    def test_bounded_growth_updates_cluster_only(self):
        patch, reason = self.evaluate()
        self.assertEqual([p['path'] for p in patch], ['/metadata/resourceVersion','/spec/resources','/spec/resources','/metadata/annotations'])
        self.assertEqual(patch[2]['value'], {'requests':{'cpu':'1800m','memory':'3072Mi'},'limits':{'cpu':'1800m','memory':'3072Mi'}})
        self.assertEqual(patch[3]['value']['kept'], 'yes')

    def test_large_recommendation_clamps_to_maximum(self):
        self.vpa['status']['recommendation']['containerRecommendations'][0]['target'] = {'cpu':'20','memory':'80Gi'}
        patch, _ = self.evaluate()
        self.assertEqual(patch[2]['value']['requests'], {'cpu':'2000m','memory':'4096Mi'})

    def test_low_recommendation_never_shrinks(self):
        self.vpa['status']['recommendation']['containerRecommendations'][0]['target'] = {'cpu':'100m','memory':'100Mi'}
        self.assertIsNone(self.evaluate()[0])

    def test_hysteresis_prevents_churn(self):
        self.vpa['status']['recommendation']['containerRecommendations'][0]['target'] = {'cpu':'1200m','memory':'2200Mi'}
        self.assertIsNone(self.evaluate()[0])

    def test_failover_blocks_resize(self):
        self.cluster['status']['targetPrimary'] = 'db-2'
        self.assertIn('healthy/stable', self.evaluate()[1])

    def test_pending_instance_blocks_resize(self):
        self.cluster['status']['readyInstances'] = 0
        self.assertIsNone(self.evaluate()[0])

    def test_maintenance_blocks_resize(self):
        self.cluster['spec']['nodeMaintenanceWindow'] = {'inProgress':True}
        self.assertIsNone(self.evaluate()[0])

    def test_cooldown_blocks_resize(self):
        self.cluster['metadata']['annotations']['vcloud.io/resources-last-scaled'] = '2026-10-06T09:30:00Z'
        self.assertEqual(self.evaluate()[1], 'cooldown')

    def test_stale_recommendation_blocks_resize(self):
        self.vpa['metadata']['managedFields'][0]['time'] = '2026-10-06T09:00:00Z'
        self.assertIn('stale', self.evaluate()[1])

    def test_future_recommendation_blocks_resize(self):
        self.vpa['metadata']['managedFields'][0]['time'] = '2026-10-06T11:00:00Z'
        self.assertIn('stale', self.evaluate()[1])

    def test_missing_freshness_evidence_blocks_resize(self):
        self.vpa['metadata']['managedFields'] = []
        self.assertIsNone(self.evaluate()[0])

    def test_missing_optimistic_version_blocks_resize(self):
        self.cluster['metadata'].pop('resourceVersion')
        self.assertIsNone(self.evaluate()[0])

    def test_unequal_limits_and_requests_block_resize(self):
        self.cluster['spec']['resources']['limits']['memory'] = '4Gi'
        self.assertIsNone(self.evaluate()[0])

    def test_wrong_vpa_target_blocks_resize(self):
        self.vpa['spec']['targetRef']['name'] = 'other'
        self.assertIsNone(self.evaluate()[0])

    def test_vpa_mode_drift_blocks_resize(self):
        self.vpa['spec']['updatePolicy']['updateMode'] = 'Auto'
        self.assertIsNone(self.evaluate()[0])

    def test_sidecar_recommendations_are_not_database_recommendations(self):
        self.vpa['status']['recommendation']['containerRecommendations'][0]['containerName'] = 'sidecar'
        self.assertIsNone(self.evaluate()[0])

    def test_out_of_bounds_current_request_blocks_resize(self):
        self.cluster['spec']['resources'] = {'requests':{'cpu':'4','memory':'8Gi'},'limits':{'cpu':'4','memory':'8Gi'}}
        self.assertIsNone(self.evaluate()[0])

    def test_negative_resource_is_rejected(self):
        with self.assertRaises(ValueError):
            scaler.quantity('-10Gi')

    def test_api_redirect_cannot_forward_service_account_token(self):
        with self.assertRaisesRegex(ValueError, 'redirects'):
            scaler.NoRedirect().redirect_request(None,None,302,'',{},'https://outside.example')


class ExecutionGates(unittest.TestCase):
    def setUp(self):
        self.values = m.values(ROOT / 'module-2/site-values.example.yaml')

    def test_reference_site_is_not_deployable(self):
        with self.assertRaisesRegex(ValueError, 'Reference site'):
            m.check_values(self.values, live=True)

    def test_identity_cannot_use_another_repository(self):
        self.values['git']['upstream'] = 'https://github.com/amazen33/twinfra-other.git'
        with self.assertRaisesRegex(ValueError, 'identity'):
            m.check_values(self.values)

    def test_default_route_is_not_an_admin_cidr(self):
        self.values['site']['adminCIDR'] = '0.0.0.0/0'
        with self.assertRaisesRegex(ValueError,'Default-route'):
            m.check_values(self.values)

    def test_maximum_database_reservation_requires_node_headroom(self):
        node = {'metadata':{'name':'vcloud-node-01','labels':{'kubernetes.io/hostname':'vcloud-node-01'}},'status':{'conditions':[{'type':'Ready','status':'True'}],'allocatable':{'cpu':'2','memory':'4Gi'}}}
        with self.assertRaisesRegex(ValueError,'Insufficient node capacity'):
            m.compute_capacity([node],[],self.values)

    def test_existing_pod_reservations_are_counted(self):
        node = {'metadata':{'name':'vcloud-node-01','labels':{'kubernetes.io/hostname':'vcloud-node-01'}},'status':{'conditions':[{'type':'Ready','status':'True'}],'allocatable':{'cpu':'8','memory':'16Gi'}}}
        pod = {'metadata':{'namespace':'workload-apps'},'spec':{'nodeName':'vcloud-node-01','containers':[{'resources':{'requests':{'cpu':'6','memory':'1Gi'}}}]}}
        with self.assertRaisesRegex(ValueError,'Insufficient node capacity'):
            m.compute_capacity([node],[pod],self.values)

    def test_secondary_sriov_exception_is_not_assumed(self):
        self.values['hpc']['secondaryNetworksApproved'] = True
        with self.assertRaisesRegex(ValueError,'SR-IOV'):
            m.check_values(self.values)

    def test_memory_shrink_cannot_be_enabled(self):
        self.values['database']['autoscaler']['allowDecrease'] = True
        with self.assertRaisesRegex(ValueError,'reduction'):
            m.check_values(self.values)

    def test_diff_preserves_kubectl_difference_exit_code(self):
        with patch.object(sys,'argv',['module2','--site',str(ROOT / 'module-2/site-values.example.yaml'),'diff']), patch.object(m,'validate'), patch.object(m,'live_preflight'), patch.object(m,'preserve_database_resources',side_effect=lambda a,v:v), patch.object(m,'run',return_value=SimpleNamespace(returncode=1,stdout='difference')):
            self.assertEqual(m.main(),1)

    def test_server_admission_precedes_any_apply_mutation(self):
        commands = []
        def run(command, **kwargs):
            commands.append([str(x) for x in command]); return SimpleNamespace(returncode=0, stdout='')
        with patch.object(sys,'argv',['module2','--site',str(ROOT / 'module-2/site-values.example.yaml'),'apply']), patch.object(m,'validate'), patch.object(m,'live_preflight'), patch.object(m,'preserve_database_resources',side_effect=lambda a,v:v), patch.object(m,'run',side_effect=run):
            self.assertEqual(m.main(),0)
        self.assertIn('--dry-run=server',commands[0])
        self.assertEqual(commands[1][1:3], ['upgrade','--install'])
        self.assertNotIn('--force-conflicts', sum(commands,[]))

    def test_bootstrap_reapply_preserves_live_resource_growth(self):
        obj = {'metadata':{'resourceVersion':'124','annotations':{'vcloud.io/resources-last-scaled':'2026-10-06T10:00:00Z'}},
               'spec':{'resources':{'requests':{'cpu':'1800m','memory':'3Gi'},'limits':{'cpu':'1800m','memory':'3Gi'}}}}
        args = SimpleNamespace(kubectl='kubectl')
        with patch.object(m,'run',return_value=SimpleNamespace(stdout=json.dumps(obj))):
            actual = m.preserve_database_resources(args,self.values)
        self.assertEqual(actual['database']['cpu'],'1800m')
        self.assertEqual(actual['database']['memory'],'3Gi')
        self.assertEqual(args.database_version,'124')
        self.assertEqual(self.values['database']['cpu'],'1')

    def test_bootstrap_reapply_rejects_unreviewed_live_resource_sizes(self):
        obj = {'metadata':{'resourceVersion':'124'},'spec':{'resources':{'requests':{'cpu':'20','memory':'3Gi'},'limits':{'cpu':'20','memory':'3Gi'}}}}
        with patch.object(m,'run',return_value=SimpleNamespace(stdout=json.dumps(obj))), self.assertRaisesRegex(ValueError,'outside this scaler policy'):
            m.preserve_database_resources(SimpleNamespace(kubectl='kubectl'),self.values)


if __name__ == '__main__':
    unittest.main()
