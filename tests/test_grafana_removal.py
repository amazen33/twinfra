"""WO-07a offline negative fixtures and exact preserved-data/removal receipts."""
import gzip
import hashlib
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


def original(path):return subprocess.check_output(['git','-C',str(ROOT),'show',BASE+':'+path])


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
        # The committed receipt pins the imported objects; CI never needs the
        # unmerged PR #39 branch to survive owner closure/deletion.
        receipt=json.loads((ROOT/'docs/acceptance/grafana-removal-2026-10-15.json').read_text())
        self.assertEqual(receipt['portedSource']['commit'],'48d3a0a05477a88ebb3115fca9f19fcebde2f974')
        expected=receipt['dashboards']
        path=ROOT/'deploy/observability/dashboards'
        self.assertEqual({p.stem for p in path.glob('*.json')},set(expected))
        for name,evidence in expected.items():
            obj=json.loads((path/(name+'.json')).read_text())
            digest=hashlib.sha256(json.dumps(obj,sort_keys=True,separators=(',',':')).encode()).hexdigest()
            self.assertEqual(digest,evidence['canonicalJSONSHA256'])
            self.assertEqual(obj['kind'],'Dashboard');self.assertNotIn('apiVersion',obj)
            self.assertEqual(len(obj['spec']['panels']),4 if name=='twinfra-delivery' else 3)
        self.assertFalse((ROOT/'deploy/observability/perses').exists())

    def test_grafana_removed_from_register_and_wsl_lock(self):
        # The mandatory supply-chain register test separately verifies all
        # remaining terms, including the two exact approved P2 replacements.
        path='security/licence-register.json';before=json.loads(original(path))
        removed=[c for c in before['components'] if c['name']=='docker.io/grafana/grafana']
        self.assertEqual(len(removed),1);self.assertEqual(removed[0]['class'],'pending-removal')
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

    def test_no_perses_pins_or_policy_identity_and_baseline_changes(self):
        for path in ('deploy/common/images.lock.json','deploy/common/bootstrap-images.lock.json'):
            lock=json.loads((ROOT/path).read_text())
            self.assertEqual(set(lock['images']),set(json.loads(original(path))['images']))
            self.assertNotIn('perses',json.dumps(lock['images']).lower())
        for path in ('tools/ci/pr-baselines.json','security/licence-policy.json','security/node-exceptions.json','vcloud-ssot.yaml'):
            self.assertEqual((ROOT/path).read_bytes().replace(b'\r\n',b'\n'),original(path),path)


if __name__=='__main__':unittest.main()
