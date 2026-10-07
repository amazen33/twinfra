"""Mutation tests for the lab exception and production/Argo routing boundary."""
import copy
from pathlib import Path
import sys
import tempfile
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import check_host_routing as guard
import wsl_lab


class HostRoutingTests(unittest.TestCase):
    def write(self, root, name, data):
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(yaml.safe_dump(data), encoding='utf-8')
        return path

    def fixture(self, root):
        self.write(root, guard.BASE, {'bpf': {'hostLegacyRouting': False}})
        self.write(root, guard.LAB, guard.LAB_VALUES)

    def app(self, helm):
        return {'apiVersion': 'argoproj.io/v1alpha1', 'kind': 'Application',
                'spec': {'destination': {'name': 'vcloud-prod-01'},
                         'source': {'chart': 'cilium', 'helm': helm}}}

    def reject(self, data, name='deploy/production/cilium.yaml'):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.fixture(root)
            self.write(root, name, data)
            with self.assertRaises(ValueError):
                guard.check_repository(root)

    def test_current_source_passes(self):
        self.assertGreater(guard.check_repository(ROOT), 50)

    def test_production_and_staging_reject_legacy(self):
        for name in ('deploy/production/cilium.yaml', 'deploy/staging/values.yaml', 'module-2/values/new.yaml'):
            with self.subTest(name=name):
                self.reject({'bpf': {'hostLegacyRouting': True}}, name)

    def test_second_lab_values_file_is_not_an_exception(self):
        self.reject(guard.LAB_VALUES, 'lab/wsl/values/other.yaml')

    def test_flat_alias_is_rejected_even_false(self):
        for value in (True, False):
            self.reject({'enableHostLegacyRouting': value})

    def test_helm_strings_and_null_fail_closed(self):
        for value in ('false', 'true', None, 0, 1, 'off'):
            with self.subTest(value=value):
                self.reject({'bpf': {'hostLegacyRouting': value}})

    def test_argo_values_object(self):
        self.reject(self.app({'valuesObject': {'bpf': {'hostLegacyRouting': True}}}))

    def test_argo_inline_values(self):
        self.reject(self.app({'values': 'bpf:\n  hostLegacyRouting: true\n'}))

    def test_argo_dotted_inline_key(self):
        self.reject(self.app({'values': 'bpf.hostLegacyRouting: true\n'}))

    def test_argo_helm_parameter_and_aliases(self):
        for name in guard.OPTION_KEYS:
            self.reject(self.app({'parameters': [{'name': name, 'value': 'true'}]}))

    def test_argo_force_string_false_is_unsafe(self):
        self.reject(self.app({'parameters': [{'name': 'bpf.hostLegacyRouting', 'value': 'false', 'forceString': True}]}))

    def test_safe_argo_false_and_defaults(self):
        for helm in ({}, {'valuesObject': {'bpf': {'hostLegacyRouting': False}}},
                     {'parameters': [{'name': 'bpf.hostLegacyRouting', 'value': 'false'}]}):
            with tempfile.TemporaryDirectory() as temp:
                root = Path(temp); self.fixture(root)
                self.write(root, 'deploy/staging/app.yaml', self.app(helm))
                self.assertEqual(guard.check_repository(root), 3)

    def test_argo_multi_source(self):
        app = self.app({})
        app['spec']['sources'] = [app['spec'].pop('source'),
                                 {'chart': 'cilium', 'helm': {'values': 'bpf:\n  hostLegacyRouting: true'}}]
        self.reject(app)

    def test_argo_lab_file_reference_forbidden_even_with_false_parameter(self):
        for ref in ('../../lab/wsl/values/cilium-routing.yaml', '$values/lab/wsl/values/cilium-routing.yaml'):
            self.reject(self.app({'valueFiles': [ref], 'parameters': [{'name': 'bpf.hostLegacyRouting', 'value': 'false'}]}))

    def test_application_set_template(self):
        self.reject({'kind': 'ApplicationSet', 'spec': {'template': self.app({'values': 'bpf:\n  hostLegacyRouting: true'})}})

    def test_daemon_configmap_and_node_config(self):
        self.reject({'kind': 'ConfigMap', 'metadata': {'name': 'cilium-config'},
                     'data': {'enable-host-legacy-routing': 'true'}})
        self.reject({'kind': 'CiliumNodeConfig', 'spec': {'defaults': {'enable-host-legacy-routing': 'true'}}})

    def test_daemon_arguments(self):
        self.reject({'extraArgs': ['--enable-host-legacy-routing=true']})

    def test_bare_boolean_daemon_flag_cannot_evade_guard(self):
        for args in (['--enable-host-legacy-routing'], ['--enable-host-legacy-routing', 'true']):
            self.reject({'extraArgs': args})
        guard.inspect({'extraArgs': ['--enable-host-legacy-routing=false']})

    def test_daemon_environment_override_cannot_evade_guard(self):
        self.reject({'extraEnv': [{'name': 'CILIUM_ENABLE_HOST_LEGACY_ROUTING', 'value': 'true'}]})
        self.reject({'CILIUM_ENABLE_HOST_LEGACY_ROUTING': 'true'})
        guard.inspect({'extraEnv': [{'name': 'CILIUM_ENABLE_HOST_LEGACY_ROUTING', 'value': 'false'}]})

    def test_kustomize_json_patch(self):
        self.reject([{'op': 'replace', 'path': '/data/enable-host-legacy-routing', 'value': 'true'}])

    def test_duplicate_key_ambiguity_rejected(self):
        with self.assertRaises(ValueError):
            guard.documents('bpf:\n  hostLegacyRouting: true\n  hostLegacyRouting: false\n')

    def test_cyclic_alias_rejected(self):
        with self.assertRaises(ValueError):
            guard.inspect(yaml.safe_load('cycle: &loop\n  recurse: *loop\n'))

    def test_templated_routing_option_fails_closed(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); self.fixture(root)
            path = root / 'deploy/chart/templates/config.yaml'
            path.parent.mkdir(parents=True)
            path.write_text('enable-host-legacy-routing: {{ .Values.override }}')
            with self.assertRaises(ValueError):
                guard.check_repository(root)

    def test_base_must_explicitly_disable_legacy(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); self.fixture(root)
            self.write(root, guard.BASE, {'bpf': {}})
            with self.assertRaises(ValueError):
                guard.check_repository(root)

    def test_lab_cannot_disable_remaining_datapath_controls(self):
        for field in ('kubeProxyReplacement', 'routingMode', 'bpf', 'socketLB', 'cluster'):
            with tempfile.TemporaryDirectory() as temp:
                root = Path(temp); self.fixture(root)
                data = copy.deepcopy(guard.LAB_VALUES); del data[field]
                self.write(root, guard.LAB, data)
                with self.assertRaises(ValueError):
                    guard.check_repository(root)

    def test_renderer_preserves_base_mount_security(self):
        with tempfile.TemporaryDirectory() as temp:
            values = wsl_lab.render(Path(temp), '192.0.2.10', 'eth1')['cilium-values.yaml']
        self.assertEqual(values['bpf']['autoMount'], {'enabled': False})
        self.assertTrue(values['socketLB']['enabled'])
        self.assertTrue(values['hostFirewall']['enabled'])
        self.assertEqual(values['cluster']['name'], 'vcloud-wsl-local')

    def test_render_assertion_rejects_missing_or_duplicate_configmaps(self):
        for objects in ([], [{'kind': 'ConfigMap', 'metadata': {'name': 'cilium-config'}}] * 2):
            with self.assertRaises(ValueError):
                guard.assert_config(objects, True)

    def test_render_assertion_requires_retained_ebpf_and_socket_controls(self):
        data = {'enable-host-legacy-routing': 'true', 'enable-bpf-masquerade': 'true',
                'kube-proxy-replacement': 'true', 'routing-mode': 'native', 'bpf-lb-sock': 'true'}
        obj = {'kind': 'ConfigMap', 'metadata': {'name': 'cilium-config'}, 'data': data}
        guard.assert_config([obj], True, socket_lb=True)
        for field in data:
            wrong = copy.deepcopy(obj); wrong['data'][field] = 'false'
            with self.assertRaises(ValueError):
                guard.assert_config([wrong], True, socket_lb=True)


if __name__ == '__main__':
    unittest.main(verbosity=2)
