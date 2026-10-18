"""WO-34 comparisons stay out of the general gate and unrelated PR paths."""
import fnmatch
import json
from pathlib import Path
import sys
import unittest
import tempfile
from unittest.mock import patch

import yaml

CI = Path(__file__).resolve().parents[1]
ROOT = CI.parents[1]
sys.path.insert(0, str(CI))
import supply_chain as sc


class WorkflowScope(unittest.TestCase):
    def setUp(self):
        self.required = yaml.safe_load((ROOT / '.github/workflows/pr-tests.yaml').read_text())
        self.wo34 = yaml.safe_load((ROOT / '.github/workflows/wo34-tool-build.yaml').read_text())

    def test_general_gate_has_no_console_rebuild_rescan_or_comparison_artifacts(self):
        raw = json.dumps(self.required)
        self.assertNotIn('compare_console_images.py', raw)
        self.assertNotIn('.build/wo34-console', raw)
        self.assertNotIn('compare_p3_images.py', raw)
        self.assertNotIn('.build/wo34-p3', raw)
        triggers = self.required.get('on', self.required.get(True))
        for event in ('pull_request', 'push'):
            self.assertEqual(triggers[event]['branches'], ['main', 'release/**'])
        self.assertNotIn('inventory --full', raw)
        self.assertIn('supply_chain.py inventory', raw)
        self.assertIn('supply_chain.py evaluate', raw)
        self.assertIn('scan-pr', self.required['jobs']['required']['needs'])

    def test_comparison_is_read_only_and_keeps_complete_artifacts(self):
        self.assertEqual(self.wo34['permissions'], {'contents': 'read'})
        job = self.wo34['jobs']['console-comparison']
        steps = job['steps']
        compare = next(s for s in steps if s.get('name') == 'Reproduce and fully compare the WO-34 console images')
        self.assertIn('compare_console_images.py', compare['run'])
        self.assertIn('--base b55c0ea3a7805e80c218dcc13a5bfbea7e259a24', compare['run'])
        upload = next(s for s in steps if s.get('name') == 'Upload complete console comparison and CycloneDX SBOMs')
        for path in ('comparison.json', 'scan/*.json', 'scan/sboms/', 'cache/*.error.log'):
            self.assertIn('.build/wo34-console/' + path, upload['with']['path'])
        self.assertNotIn('secrets.', json.dumps(job))
        self.assertNotIn('pull_request_target', (ROOT / '.github/workflows/wo34-tool-build.yaml').read_text())

    def test_p3_comparison_keeps_scanners_and_complete_artifacts(self):
        job = self.wo34['jobs']['p3-comparison']
        commands = '\n'.join(step.get('run', '') for step in job['steps'])
        self.assertIn('stage_govulncheck.py --destination .build/p3-go-tools', commands)
        self.assertIn('compare_p3_images.py --tools .build/scan-tools/bin --scanner .build/p3-go-tools/govulncheck', commands)
        upload = next(s for s in job['steps'] if s.get('name') == 'Upload complete P3 comparison and CycloneDX SBOMs')
        for path in ('comparison.json', 'scan/*.json', 'scan/sboms/', '**/*.json.gz', '**/summary.json'):
            self.assertIn('.build/wo34-p3/' + path, upload['with']['path'])
        self.assertNotIn('secrets.', json.dumps(job))

    def test_filter_matches_console_builder_wo34_tools_and_excludes_unrelated_paths(self):
        triggers = self.wo34.get('on', self.wo34.get(True))
        paths = triggers['pull_request']['paths']
        matches = lambda path: any(fnmatch.fnmatchcase(path, pattern) for pattern in paths)
        for path in ('console/server.py', 'console/src/App.tsx', 'console/image.lock.json',
                     'tools/build_console_image.py', 'tools/ci/compare_console_images.py',
                     'tools/ci/compare_p3_images.py', 'tools/ci/record_p3_scan.py',
                     'tools/refresh_p3_pins.py', 'deploy/common/bootstrap-images.lock.json',
                     'deploy/common/images.lock.json', 'tools/ci/triage_go_source.py', '.github/workflows/wo34-tool-build.yaml'):
            self.assertTrue(matches(path), path)
        for path in ('README.md', 'docs/work-orders/WO-07-perses-replaces-grafana.md',
                     'CHANGELOG.md', 'deploy/environments/dev/cairo-1/services/workloads.yaml'):
            self.assertFalse(matches(path), path)

    def test_unrelated_docs_change_selects_no_images_or_locks(self):
        def git(_root, command, spec):
            self.assertEqual(command, 'show')
            return (ROOT / spec.split(':', 1)[1]).read_text()
        with patch.object(sc, 'tracked', return_value=[]), \
             patch.object(sc, 'changed', return_value=['README.md', 'docs/service-access.md']), \
             patch.object(sc, 'git', side_effect=git):
            plan = sc.inventory(ROOT, base='a' * 40)
        self.assertFalse(plan['full'])
        self.assertEqual(plan['images'], [])
        self.assertEqual(plan['lockfiles'], [])

    def test_p3_superseded_pin_is_historical_and_unknown_pins_still_fail(self):
        from compare_p3_images import promotion,ROWS
        from security_wave_2026_10 import CASES
        before={'reference':ROWS[0][1]}
        after={'reference':ROWS[1][1],'counts':{'CriticalWithFix':1,'HighWithFix':1}}
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/'security').mkdir()
            path=root/'security/security-wave-2026-10-images.json'
            ref=CASES['ministack1533'][2]
            data={'images':{'ministack':{'before':before['reference'],'after':ref,
                'comparison':{'subset':True,'strictImprovement':True,'introduced':[]}}}}
            path.write_text(json.dumps(data),encoding='utf-8')
            value,failed=promotion('ministack',ref.split('@')[1],before,after,root)
            self.assertFalse(failed);self.assertFalse(value['promoted'])
            self.assertTrue(value['historicalOnly']);self.assertEqual(value['supersededBy'],ref)
            with self.assertRaisesRegex(ValueError,'Unexpected P3'):
                promotion('ministack','sha256:'+'a'*64,before,after,root)
            data['images']['ministack']['comparison']['introduced']=[['bad','CVE-new']]
            path.write_text(json.dumps(data),encoding='utf-8')
            with self.assertRaisesRegex(ValueError,'Unexpected P3'):
                promotion('ministack',ref.split('@')[1],before,after,root)
            selected,failed=promotion('ministack',after['reference'].split('@')[1],before,after,root)
            self.assertTrue(selected['promoted']);self.assertTrue(failed)


if __name__ == '__main__':
    unittest.main()
