"""WO-34 P3 bounded offline pin/render contracts; no runtime or network."""
import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import yaml

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
import platform_dev as dev
sys.path.insert(0,str(ROOT/'tools/ci'))
import record_p3_scan as receipt
BASE='48299120a8afd716ccdb22185053aa7c883fa573'
MINI='sha256:451a0cc80a4f464e1c2d2f77fbb40ac37d01902d58ca3630ac5eaea9c92f12da'
PAUSE='registry.twinfra.example.com/registry.k8s.io/pause:3.10.2'


def old(path):return subprocess.check_output(['git','-C',str(ROOT),'show',BASE+':'+path])


class PatchPins(unittest.TestCase):
    def test_production_wsl_policy_and_historical_baselines_are_byte_identical(self):
        for name in ('00-setup-ubuntu-host.sh','host.env.example','user-data.yaml','user-data-remote.yaml','user-data.yaml.gz',
                     'vcloud-ssot.yaml','security/licence-policy.json','tools/ci/pr-baselines.json',
                     'lab/wsl/console/artifacts.lock.json','lab/wsl/console/workloads.yaml'):
            self.assertEqual((ROOT/name).read_bytes().replace(b'\r\n',b'\n') if not name.endswith('.gz') else (ROOT/name).read_bytes(),old(name),name)

    def test_blocked_ministack_pin_is_unchanged_and_no_app_pin_changes(self):
        name='deploy/common/images.lock.json';before=json.loads(old(name));current=json.loads((ROOT/name).read_text())
        self.assertEqual(current,before)

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

    def test_services_render_is_unchanged_when_ministack_is_stopped(self):
        path='deploy/environments/dev/cairo-1/services/workloads.yaml'
        before=list(yaml.safe_load_all(old(path)));current=list(yaml.safe_load_all((ROOT/path).read_text()))
        self.assertEqual(current,before)

    def test_receipt_retains_blocked_mini_exception_and_rejects_promoted_critical(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            for name in ('deploy/common','security','docs/acceptance'):(root/name).mkdir(parents=True)
            mini_before='sha256:'+'a'*64;mini_after='sha256:'+'b'*64;pause='sha256:'+'c'*64
            app=root/'deploy/common/images.lock.json'
            app.write_text(json.dumps({'images':{'ministack':{'digest':mini_before}}}))
            (root/'deploy/common/bootstrap-images.lock.json').write_text(json.dumps({'images':{'pause':{'digest':pause}}}))
            original={'target':'docker.io/ministackorg/ministack@'+mini_before,'package':'python','version':'3.13.15','vulnerability':'CVE-one'}
            (root/'security/vulnerability-exceptions.json').write_text(json.dumps({'exceptions':[original]}))
            rows=[]
            for name,pin in [('ministack-before',mini_before),('ministack-after',mini_after),('pause-before','sha256:'+'d'*64),('pause-after',pause)]:
                rows.append(dict(name=name,reference=('docker.io/ministackorg/ministack' if name.startswith('ministack') else 'registry.k8s.io/pause')+'@'+pin,
                    coverage='complete-oci-archive-linux-amd64',counts={'CriticalWithFix':1 if name.startswith('ministack') else 0,'HighWithFix':0},findings=[]))
            with patch.object(receipt,'ROOT',root):
                value=receipt.record(dict(images=rows,date='2026-10-14',database={}),
                    'https://github.com/amazen33/twinfra/actions/runs/123')
                self.assertEqual(value['promotedImages'],['pause-after']);self.assertEqual(value['closedExceptions'],[])
                self.assertEqual(json.loads((root/'security/vulnerability-exceptions.json').read_text())['exceptions'],[original])
                app.write_text(json.dumps({'images':{'ministack':{'digest':mini_after}}}))
                with self.assertRaisesRegex(ValueError,'fixable Critical'):
                    receipt.record(dict(images=rows,date='2026-10-14',database={}),
                        'https://github.com/amazen33/twinfra/actions/runs/123')


if __name__=='__main__':unittest.main()
