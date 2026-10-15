"""WO-07a offline negative fixtures and exact preserved-data/removal receipts."""
import gzip
import io
import json
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
import unittest
import yaml

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'tools'),str(ROOT/'tools/ci')]
import check_grafana_removal as guard
from run_checks import coverage

BASE='e92255278369a25f26bc694b38c33bfd2768c14d'
PORT='48d3a0a05477a88ebb3115fca9f19fcebde2f974'
DELIVERY='7c8abbfd9a0f701d29ca5d3a1e9a5288f0fc7511'


def original(path):return subprocess.check_output(['git','-C',str(ROOT),'show',BASE+':'+path])
def delivered(path):return subprocess.check_output(['git','-C',str(ROOT),'show',DELIVERY+':'+path])


class RemovalGuard(unittest.TestCase):
    def test_grafana_images_workloads_labels_and_chart_locks_fail(self):
        cases={
            'deploy/locks.json':'{"images":{"dashboard":"docker.io/grafana/grafana@sha256:'+'a'*64+'"}}',
            'lab/wsl/workload.yaml':'kind: Deployment\nmetadata: {name: grafana}\n',
            'module-3/manifests/dashboard.yaml':'kind: ConfigMap\nmetadata:\n  labels: {grafana_dashboard: "1"}\n',
            'deploy/chart-lock.json':'{"chart":"https://grafana.github.io/helm-charts/grafana-1.0.0.tgz"}',
            'tools/wsl_endpoints.py':'image("grafana")',
            'deploy/chart/templates/ui.tpl':'{{ include "grafana.fullname" . }}',
        }
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            for name,body in cases.items():
                file=root/name;file.parent.mkdir(parents=True,exist_ok=True);file.write_text(body)
                with self.subTest(name=name):self.assertTrue(guard.violations(root,[name]))

    def test_gzipped_manifest_and_actual_render_are_checked(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);file=root/'deploy/vendor/install.yaml.gz';file.parent.mkdir(parents=True)
            file.write_bytes(gzip.compress(b'kind: Deployment\nmetadata: {name: grafana}\n'))
            self.assertTrue(guard.violations(root,['deploy/vendor/install.yaml.gz']))
            (root/'actual.yaml').write_text('metadata: {labels: {grafana_dashboard: "1"}}')
            self.assertTrue(guard.violations(root,['actual.yaml'],rendered=True))

    def test_grafana_chart_and_dependency_and_values_image_fail(self):
        for name,body in [('Chart.yaml','name: grafana\nversion: 1.0.0'),
                          ('Chart.yaml','name: platform\ndependencies: [{name: grafana}]'),
                          ('values.yaml','image: {repository: docker.io/grafana/grafana}')]:
            with self.subTest(body=body),tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp);path=root/'deploy/vendor/chart.tgz';path.parent.mkdir(parents=True)
                raw=body.encode()
                with tarfile.open(path,'w:gz') as archive:
                    member=tarfile.TarInfo('chart/'+name);member.size=len(raw);archive.addfile(member,io.BytesIO(raw))
                self.assertTrue(guard.violations(root,['deploy/vendor/chart.tgz']))

    def test_historical_docs_receipts_fixtures_and_unused_upstream_dashboard_data_are_not_deployments(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);paths=['docs/adr/0010-grafana.md','docs/acceptance/history.json','tests/fixtures/grafana.yaml','tools/ci/pr-baselines.json']
            for name in paths:
                path=root/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_text('grafana_dashboard')
            self.assertEqual(guard.violations(root,paths),[])
            path=root/'deploy/vendor/cilium.tgz';path.parent.mkdir(parents=True)
            with tarfile.open(path,'w:gz') as archive:
                for name,raw in [('Chart.yaml',b'name: cilium\nversion: 1.20.2'),('files/dashboard.json',b'{"datasource":"Grafana"}')]:
                    member=tarfile.TarInfo('cilium/'+name);member.size=len(raw);archive.addfile(member,io.BytesIO(raw))
            self.assertEqual(guard.violations(root,['deploy/vendor/cilium.tgz']),[])

    def test_current_candidate_passes(self):guard.check(ROOT)

    def test_incomplete_removal_bundle_fails_and_historical_absence_is_supported(self):
        # Existing coverage requires the core baseline before testing optional bundles.
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            for name in ['00-setup-ubuntu-host.sh','user-data.yaml','tests/test_bootstrap.py','tools/render_ssot.py',
                         'tools/render_cloud_init.py','docs/module-1-topology.md','tools/module2.py','tests/test_module2.py',
                         'module-2/vendor/cilium-1.20.2.tgz']:
                path=root/name;path.parent.mkdir(parents=True,exist_ok=True);path.touch()
            self.assertEqual(coverage(root)['grafana-removal'],'not_present_in_revision')
            path=root/'tools/check_grafana_removal.py';path.touch()
            with self.assertRaisesRegex(ValueError,'Incomplete grafana-removal'):coverage(root)


class ExactChanges(unittest.TestCase):
    def test_two_plain_dashboards_are_identical_to_ported_pr39_definitions(self):
        source=json.loads(subprocess.check_output(['git','-C',str(ROOT),'show',PORT+':deploy/observability/perses/dashboards.json']))
        expected={o['metadata']['name']:o for o in source if o['kind']=='Dashboard'}
        path=ROOT/'deploy/observability/dashboards'
        self.assertEqual({p.stem for p in path.glob('*.json')},set(expected))
        for name,obj in expected.items():self.assertEqual(json.loads((path/(name+'.json')).read_text()),obj)
        self.assertEqual(len(expected['twinfra-delivery']['spec']['panels']),4)
        self.assertEqual(len(expected['twinfra-health']['spec']['panels']),3)
        self.assertFalse((ROOT/'deploy/observability/perses').exists())

    def test_removal_delivery_changed_only_grafana_in_register_and_lock(self):
        # Freeze this work order's delivery proof so an independently approved
        # image refresh does not rewrite it. Current removal remains mandatory.
        path='security/licence-register.json';before=json.loads(original(path));after=json.loads(delivered(path))
        removed=[c for c in before['components'] if c['name']=='docker.io/grafana/grafana']
        self.assertEqual(len(removed),1);self.assertEqual(removed[0]['class'],'pending-removal')
        before['components']=[c for c in before['components'] if c not in removed]
        self.assertEqual(after,before);self.assertFalse(any(c['class']=='pending-removal' for c in after['components']))
        current=json.loads((ROOT/path).read_text())
        self.assertFalse(any('grafana' in c['name'].lower() or c['class']=='pending-removal' for c in current['components']))
        path='lab/wsl/endpoints/artifacts.lock.json';before=json.loads(original(path))
        for key in ('versions','imageSources','images'):self.assertIsNotNone(before[key].pop('grafana'))
        self.assertEqual(json.loads((ROOT/path).read_text()),before)

    def test_generated_manifests_remove_only_grafana_objects(self):
        for path in ('module-3/manifests/observability.yaml','lab/wsl/endpoints/gitops/workloads.yaml'):
            before=list(yaml.safe_load_all(original(path)))
            expected=[o for o in before if o['metadata']['name'] not in ('grafana','vcloud-grafana','vcloud-delivery-dashboard')]
            self.assertLess(len(expected),len(before));self.assertEqual(list(yaml.safe_load_all((ROOT/path).read_text())),expected)

    def test_removal_delivery_did_not_change_dev_production_images_baselines_or_console(self):
        for path in ('deploy/common/images.lock.json','deploy/common/bootstrap-images.lock.json','console/image.lock.json',
                     'tools/ci/pr-baselines.json','security/licence-policy.json','user-data.yaml','user-data-remote.yaml',
                     'deploy/environments/dev/cairo-1/services/workloads.yaml','deploy/environments/dev/cairo-1/platform/workloads.yaml'):
            self.assertEqual(delivered(path),original(path),path)
        self.assertEqual((ROOT/'tools/ci/pr-baselines.json').read_bytes().replace(b'\r\n',b'\n'),original('tools/ci/pr-baselines.json'))


if __name__=='__main__':unittest.main()
