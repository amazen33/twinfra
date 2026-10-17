"""WO-34 3a current pin, production-boundary and compensating-control tests."""
import copy
import gzip
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest
import yaml

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'tools'),str(ROOT/'tools/ci')]
import platform_dev as dev
import platform_image_references as refs
from promote_p2 import PINS,CONTROLS,BASE
from p2_receipts import expected_source, assert_current_source, assert_current_seed, receipt as p2_receipt


def old(path):return subprocess.check_output(['git','-C',str(ROOT),'show',BASE+':'+path])


class Promotion(unittest.TestCase):
    def test_bootstrap_changes_only_two_pins_and_reference_only_defaults(self):
        before=json.loads(old('deploy/common/bootstrap-images.lock.json'));current=json.loads((dev.COMMON/'bootstrap-images.lock.json').read_text())
        for name,(tag,pin,_) in PINS.items():
            item=current['images'][name]
            self.assertEqual(item['digest'],pin);self.assertTrue(item['canonical'].endswith(':'+tag))
            self.assertTrue(item['source'].endswith('@'+pin))
            original=next(v for v in current['referenceOnlyImages'] if v['digest']==before['images'][name]['digest'])
            original.pop('purpose');self.assertEqual(original,before['images'][name])
            current['images'][name]=before['images'][name]
        current['referenceOnlyImages']=[v for v in current['referenceOnlyImages'] if v['digest'] not in {before['images'][n]['digest'] for n in PINS}]
        self.assertEqual(current,before)
        self.assertEqual((dev.COMMON/'images.lock.json').read_bytes().replace(b'\r\n',b'\n'),old('deploy/common/images.lock.json'))

    def test_kubeadm_exact_dev_versions_and_production_override_refusal(self):
        bash=os.environ.get('BASH_BINARY','bash')
        for row in yaml.safe_load((ROOT/'vcloud-ssot.yaml').read_text())['addressPlan']:
            if row['environment']!='dev':continue
            values=dict(line.split('=',1) for line in dev.host_environment(row).splitlines() if line and not line.startswith('#'))
            env=dict(os.environ,**values,VCLOUD_CONFIG_FILE='/nonexistent')
            raw=subprocess.check_output([bash,'-c','source "$1"; load_config; render_kubeadm','_',str(ROOT/'00-setup-ubuntu-host.sh')],env=env,text=True)
            config=next(v for v in yaml.safe_load_all(raw) if v['kind']=='ClusterConfiguration')
            self.assertEqual(config['dns']['imageTag'],'v1.14.7');self.assertEqual(config['etcd']['local']['imageTag'],'3.6.15-0')
            self.assertEqual(refs.BOOTSTRAP_TAG_ALLOWLIST[('kubeadm','Pod','etcd')],config['imageRepository']+'/etcd:3.6.15-0')
        env=dict(os.environ,PLATFORM_PROFILE='production',KUBEADM_DNS_IMAGE_TAG='v1.14.7',KUBEADM_ETCD_IMAGE_TAG='3.6.15-0',NODE_IP='192.168.50.10',VCLOUD_CONFIG_FILE='/nonexistent')
        run=subprocess.run([bash,'-c','source "$1"; load_config; render_kubeadm','_',str(ROOT/'00-setup-ubuntu-host.sh')],env=env,capture_output=True,text=True)
        self.assertEqual(run.returncode,2);self.assertIn('dev-only',run.stdout+run.stderr)

    def test_shared_source_only_dev_override_and_etcd_contract_blocks_differ(self):
        assert_current_source()
        for path in ('host.env.example','vcloud-ssot.yaml','security/node-exceptions.json','tools/ci/pr-baselines.json','security/licence-policy.json'):
            self.assertEqual(p2_receipt(path).replace(b'\r\n',b'\n'),old(path),path)

    def test_production_seeds_only_embed_shared_dev_changes_and_hash(self):
        for path in ('user-data.yaml','user-data-remote.yaml','user-data.yaml.gz'):
            assert_current_seed(path)

    def test_go_exceptions_are_per_package_controls_and_original_expiry(self):
        receipt=json.loads((ROOT/'docs/acceptance/wo34-p2-2026-10-15.json').read_text())
        self.assertEqual(len(receipt['closedExceptions']),16);self.assertEqual(len(receipt['carriedExceptions']),6)
        go=[]
        for row in receipt['carriedExceptions']:
            a,b=row['before'],row['after']
            for key in ('vulnerability','reason','approvedBy','owner','severity','createdOn','expires'):
                self.assertEqual(a[key],b[key])
            self.assertEqual(b['expires'],'2026-11-12')
            if b['vulnerability']=='CVE-2026-78663':go.append(b);self.assertEqual(b['controls'],CONTROLS)
        self.assertEqual(len(go),4)
        for pin in (v[1] for v in PINS.values()):self.assertEqual({v['package'] for v in go if v['target'].endswith('@'+pin)},{'stdlib','golang.org/x/net'})

    def test_current_seed_changes_only_embedded_dev_source_env_and_inventory(self):
        path='deploy/environments/dev/cairo-2/seed/user-data'
        current=yaml.safe_load((ROOT/path).read_text());before=yaml.safe_load(old(path))
        if (ROOT/'deploy/common/host-graphics.py').is_file():
            from graphics_receipts import seed_before_graphics
            current=seed_before_graphics(current)
        for file in current['write_files']:
            original=next(v for v in before['write_files'] if v['path']==file['path'])
            if file['path']=='/etc/twinfra-host.env':
                for line in ('KUBEADM_DNS_IMAGE_TAG=v1.14.7\n','KUBEADM_ETCD_IMAGE_TAG=3.6.15-0\n'):
                    self.assertEqual(file['content'].count(line),1);file['content']=file['content'].replace(line,'')
            if file['path']=='/etc/twinfra/bootstrap-images.lock.json':
                self.assertEqual(json.loads(file['content']),json.loads((dev.COMMON/'bootstrap-images.lock.json').read_text()))
                file['content']=original['content']
            if file['path']=='/usr/local/sbin/00-setup-ubuntu-host.sh':
                self.assertEqual(file['content'],expected_source(original['content']));file['content']=original['content']
        self.assertEqual(current,before)

    def test_compensating_boundaries_remain_encoded(self):
        objects=[]
        for name in ('platform','services'):
            objects.extend(v for v in yaml.safe_load_all((dev.TARGET/name/'workloads.yaml').read_text()) if v)
        for obj in objects:
            if obj['kind']=='Service':
                self.assertEqual(obj['spec'].get('type','ClusterIP'),'ClusterIP');self.assertFalse(obj['spec'].get('externalIPs'))
            self.assertNotIn(obj['kind'],('Ingress','ApisixRoute'))
        self.assertNotIn('argocd',(dev.COMMON/'apisix-routes.json').read_text())
        firewall=(dev.TARGET/'host/host-firewall.nft').read_text()
        self.assertIn('tcp dport { 22, 6443 } accept',firewall);self.assertIn('iifname "eno1" drop',firewall)
        self.assertNotRegex(firewall,r'(2379|2380).*accept')
        row=next(r for r in yaml.safe_load((ROOT/'vcloud-ssot.yaml').read_text())['addressPlan'] if r['region']=='cairo-1' and r['environment']=='dev')
        self.assertEqual(row['ipAddress'],'192.168.1.3');self.assertIn('No router forwarding',(ROOT/'docs/dev-environment.md').read_text())
        self.assertEqual(firewall,old('deploy/environments/dev/cairo-1/host/host-firewall.nft').decode())


if __name__=='__main__':unittest.main()
