"""WO-34 P3 bounded offline pin/render contracts; no runtime or network."""
import copy
import json
from pathlib import Path
import subprocess
import sys
import unittest
import yaml

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
import platform_dev as dev
BASE='d15edac21bd313eb971331fd86263c16746ebbb7'
MINI='sha256:451a0cc80a4f464e1c2d2f77fbb40ac37d01902d58ca3630ac5eaea9c92f12da'
PAUSE='registry.twinfra.example.com/registry.k8s.io/pause:3.10.2'


def old(path):return subprocess.check_output(['git','-C',str(ROOT),'show',BASE+':'+path])


class PatchPins(unittest.TestCase):
    def test_production_wsl_policy_and_historical_baselines_are_byte_identical(self):
        for name in ('00-setup-ubuntu-host.sh','host.env.example','user-data.yaml','user-data-remote.yaml','user-data.yaml.gz',
                     'vcloud-ssot.yaml','security/licence-policy.json','tools/ci/pr-baselines.json',
                     'lab/wsl/console/artifacts.lock.json','lab/wsl/console/workloads.yaml'):
            self.assertEqual((ROOT/name).read_bytes().replace(b'\r\n',b'\n') if not name.endswith('.gz') else (ROOT/name).read_bytes(),old(name),name)

    def test_only_ministack_app_pin_changes_with_exact_patch_provenance(self):
        name='deploy/common/images.lock.json';before=json.loads(old(name));current=json.loads((ROOT/name).read_text())
        entry=current['images']['ministack'];self.assertEqual(entry['digest'],MINI)
        self.assertEqual(entry['release'],'docker.io/ministackorg/ministack:1.5.18')
        self.assertEqual(entry['publishedAt'],'2026-09-28T22:44:59.959202Z')
        self.assertEqual(entry['releasePublishedAt'],'2026-09-28T22:29:28Z')
        for field in ('source','canonical'):self.assertTrue(entry[field].endswith('@'+MINI))
        current['images']['ministack']=before['images']['ministack'];self.assertEqual(current,before)

    def test_pause_is_kubeadm_pin_and_old_alias_is_reference_only(self):
        name='deploy/common/bootstrap-images.lock.json';before=json.loads(old(name));current=json.loads((ROOT/name).read_text())
        self.assertEqual(current['images']['pause'],current['images']['kubeadm-pause'])
        self.assertEqual(current['images']['pause']['canonical'],PAUSE)
        reference=current.pop('referenceOnlyImages');self.assertEqual(len(reference),1)
        reference[0].pop('purpose');self.assertEqual(reference[0],before['images']['pause'])
        current['images']['pause']=before['images']['pause'];self.assertEqual(current,before)

    def test_dev_host_override_is_exact_in_both_regions(self):
        ssot=yaml.safe_load((ROOT/'vcloud-ssot.yaml').read_text())
        for row in ssot['addressPlan']:
            if row['environment']=='dev':self.assertEqual(dev.host_environment(row).count('PAUSE_IMAGE='+PAUSE+'\n'),1)
        self.assertIn('pause:3.10.1}',(ROOT/'00-setup-ubuntu-host.sh').read_text())

    def test_seed_changes_only_bootstrap_inventory_and_pause_override(self):
        path='deploy/environments/dev/cairo-2/seed/user-data'
        current=yaml.safe_load((ROOT/path).read_text());before=yaml.safe_load(old(path))
        for file in current['write_files']:
            original=next(v for v in before['write_files'] if v['path']==file['path'])
            if file['path']=='/etc/twinfra-host.env':
                self.assertEqual(file['content'].replace('PAUSE_IMAGE='+PAUSE+'\n',''),original['content'])
                file['content']=original['content']
            if file['path']=='/etc/twinfra/bootstrap-images.lock.json':
                self.assertEqual(json.loads(file['content']),json.loads((dev.COMMON/'bootstrap-images.lock.json').read_text()))
                file['content']=original['content']
        self.assertEqual(current,before)

    def test_services_render_changes_only_the_ministack_image(self):
        path='deploy/environments/dev/cairo-1/services/workloads.yaml'
        before=list(yaml.safe_load_all(old(path)));current=list(yaml.safe_load_all((ROOT/path).read_text()))
        # Large List fields are compared as data; only the selected container image is permitted.
        matched=0
        for item in current:
            if item.get('kind')=='Deployment' and item['metadata']['name']=='twinfra-ministack':
                container=item['spec']['template']['spec']['containers'][0]
                self.assertTrue(container['image'].endswith('@'+MINI))
                matched+=1
                original=next(v for v in before if v['metadata']['name']=='twinfra-ministack')
                container['image']=original['spec']['template']['spec']['containers'][0]['image']
        self.assertEqual(matched,1)
        self.assertEqual(current,before)


if __name__=='__main__':unittest.main()
