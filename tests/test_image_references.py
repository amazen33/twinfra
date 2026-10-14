"""WO-31 13–13b: offline image-resolution/provenance fixtures; no live operations."""
import copy
from datetime import date
import io
import json
from pathlib import Path
import re
import subprocess
import sys
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

import yaml

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
import platform_dev as dev
import platform_image_references as guard
from platform_sources import vendor

BASE='a84169a63a941f98c989d4db4739e9470e803fe4'


def pod(ref,kind='Pod',name='example',category='containers'):
    return {'kind':kind,'metadata':{'name':name},'spec':{category:[{'name':'example','image':ref}]}}


class Resolution(unittest.TestCase):
    def setUp(self):
        self.app=json.loads((dev.COMMON/'images.lock.json').read_text())
        self.boot=json.loads((dev.COMMON/'bootstrap-images.lock.json').read_text())
        self.ref=self.app['images']['cnpg']['canonical']

    def test_all_runtime_image_locations_accept_matching_repo_digest(self):
        objects=[pod(self.ref,category=c) for c in ('containers','initContainers','ephemeralContainers')]
        objects += [{'kind':'Cluster','metadata':{'name':'pg'},'spec':{'imageName':self.ref}},
            {'kind':'ImageCatalog','metadata':{'name':'catalog'},'spec':{'images':[{'major':18,'image':self.ref}]}},
            {'kind':'ClusterImageCatalog','metadata':{'name':'cluster-catalog'},'spec':{'images':[{'major':18,'image':self.ref}]}},
            {'kind':'Pooler','metadata':{'name':'pooler'},'spec':{'template':{'spec':{'containers':[{'name':'pgbouncer','image':self.ref}]}}}},
            {'kind':'Deployment','metadata':{'name':'operator'},'spec':{'template':{'spec':{'containers':[{'name':'manager','image':self.ref,
                'env':[{'name':'OPERATOR_IMAGE_NAME','value':self.ref}]}]}}}}]
        refs=list(guard.references(objects));self.assertEqual(len(refs),9)
        for r in refs:self.assertIn('image',r['path'].lower())
        guard.require(objects,self.app,'A')
        tagged=self.ref.replace('@',':1.30.1@')
        guard.require([pod(tagged)],self.app,'A')

    def test_each_reference_location_blocks_upstream_plain_tag_and_digest_drift(self):
        bad=[self.ref.split('@')[0]+':1.30.1',self.ref.replace('registry.twinfra.example.com/',''),
             self.ref.split('@')[0]+'@sha256:'+'a'*64]
        for ref in bad:
            for category in ('containers','initContainers','ephemeralContainers'):
                with self.subTest(ref=ref,category=category),self.assertRaisesRegex(ValueError,'guard failed'):
                    guard.require([pod(ref,category=category)],self.app,'A')
            for obj in ({'kind':'Cluster','metadata':{'name':'pg'},'spec':{'imageName':ref}},
                        {'kind':'ImageCatalog','metadata':{'name':'catalog'},'spec':{'images':[{'image':ref}]}},
                        {'kind':'Pooler','metadata':{'name':'pooler'},'spec':{'template':{'spec':{'containers':[{'image':ref}]}}}},
                        {'kind':'Pod','metadata':{'name':'operator'},'spec':{'containers':[{'image':self.ref,'env':[{'name':'BOOTSTRAP_IMAGE','value':ref}]}]}}):
                with self.subTest(obj=obj),self.assertRaisesRegex(ValueError,'guard failed'):guard.require([obj],self.app,'A')

    def test_image_env_value_from_and_non_string_image_fail_closed(self):
        for spec in ({'containers':[{'image':self.ref,'env':[{'name':'OPERATOR_IMAGE_NAME','valueFrom':{'secretKeyRef':{'name':'fixture'}}}]}]},
                     {'containers':[{'image':123}]}):
            with self.subTest(spec=spec),self.assertRaises(ValueError):
                guard.require([{'kind':'Pod','metadata':{'name':'bad'},'spec':spec}],self.app,'A')

    def test_schema_declarations_are_not_runtime_image_references(self):
        obj={'kind':'CustomResourceDefinition','metadata':{'name':'clusters.example'},'spec':{'versions':[{'schema':{'openAPIV3Schema':{'properties':{'image':{'type':'string'}}}}}]}}
        self.assertEqual(list(guard.references([obj])),[])

    def test_both_production_cloud_init_inputs_match_shared_bootstrap_and_report_mode(self):
        inputs=guard.cloud_inputs(ROOT)
        self.assertEqual(set(inputs),{'user-data.yaml','user-data-remote.yaml'})
        for values in inputs.values():
            self.assertEqual(values['PLATFORM_PROFILE'],'production')
            self.assertEqual(values['IMAGE_REGISTRY'],'registry.vcloud.example.com')
            self.assertEqual(values['GPU_SMOKE_TEST'],'false')

    def test_closed_allowlist_is_exactly_the_owner_approved_renderers_objects_and_tags(self):
        expected={('kubeadm','Pod',name):'registry.twinfra.example.com/registry.k8s.io/'+name+':'+tag
                  for name,tag in [('kube-apiserver','v1.36.5'),('kube-controller-manager','v1.36.5'),
                                   ('kube-scheduler','v1.36.5'),('etcd','3.6.8-0')]}
        expected.update({('kubeadm','Deployment','coredns'):'registry.twinfra.example.com/registry.k8s.io/coredns:v1.14.2',
            ('containerd','ContainerRuntimeConfiguration','containerd'):'registry.twinfra.example.com/registry.k8s.io/pause:3.10.1',
            ('kubeadm','RuntimeImage','pause'):'registry.twinfra.example.com/registry.k8s.io/pause:3.10.2'})
        self.assertEqual(guard.BOOTSTRAP_TAG_ALLOWLIST,expected)
        for (producer,kind,name),ref in expected.items():
            obj=pod(ref,kind,name)
            with self.subTest(ref=ref):
                guard.require([obj],self.boot,'B',producer)
                with self.assertRaises(ValueError):guard.require([obj],self.boot,'A',producer)
                with self.assertRaises(ValueError):guard.require([obj],self.boot,'B','helm')

    def test_tag_allowance_requires_exact_staged_canonical_and_cannot_adopt_new_tags(self):
        key=('kubeadm','Pod','kube-apiserver');ref=guard.BOOTSTRAP_TAG_ALLOWLIST[key]
        lock=copy.deepcopy(self.boot);lock['images']['apiserver']['canonical']=ref.replace(':v1.36.5',':v1.36.6')
        with self.assertRaises(ValueError):guard.require([pod(ref,'Pod','kube-apiserver')],lock,'B','kubeadm')
        # Even a new tag in the lock is not an approval to enlarge the constant.
        with self.assertRaises(ValueError):guard.require([pod(lock['images']['apiserver']['canonical'],'Pod','kube-apiserver')],lock,'B','kubeadm')
        cilium=self.boot['images']['cilium']['canonical']
        guard.require([pod(cilium,'DaemonSet','cilium')],self.boot,'B','helm')
        lock=copy.deepcopy(self.boot);lock['images']['cilium']['canonical']=cilium.split('@')[0]
        with self.assertRaises(ValueError):guard.require([pod(cilium.split('@')[0],'DaemonSet','cilium')],lock,'B','helm')

    def test_repo_normalization_preserves_registry_port_and_rejects_bad_digest(self):
        ref=self.ref.replace('registry.twinfra.example.com/','registry.twinfra.example.com:443/')
        self.assertEqual(guard.normalized(ref.replace('@',':1.30.1@')),ref)
        self.assertIsNone(guard.normalized(ref.replace('sha256:','sha256:BAD')))
        self.assertIsNone(guard.normalized(ref.replace('@',':@')))

    def test_production_findings_are_dated_report_only(self):
        objects=[pod('registry.vcloud.example.com/registry.k8s.io/kube-apiserver:v1.36.5','Pod','kube-apiserver'),
                 pod('registry.vcloud.example.com/nvcr.io/nvidia/k8s-device-plugin:v0.20.1','DaemonSet','nvidia-device-plugin')]
        findings=guard.audit(objects,self.boot,'B','kubeadm')
        with redirect_stdout(io.StringIO()) as output:
            text=guard.production_report(findings,date(2026,10,14))
        self.assertEqual(len(findings),2);self.assertIn('Production image-reference debt',text)
        self.assertIn('2026-10-14 (report-only)',output.getvalue())


class OperatorAndRenders(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.controllers=dev.controllers()

    def test_operator_setting_uses_vendor_tag_and_canonical_locked_digest(self):
        original=vendor(dev.COMMON/'vendor',dev.COMMON/'artifacts.lock.json','cnpg.yaml')
        vendor_setting=next(e['value'] for o in original if o['kind']=='Deployment' for c in o['spec']['template']['spec']['containers']
                            for e in c.get('env',[]) if e['name']=='OPERATOR_IMAGE_NAME')
        current=next(o for o in self.controllers if o['kind']=='Deployment' and 'cnpg' in o['metadata']['name'])
        ref=next(e['value'] for c in current['spec']['template']['spec']['containers'] for e in c['env'] if e['name']=='OPERATOR_IMAGE_NAME')
        lock=json.loads((dev.COMMON/'images.lock.json').read_text())['images']['cnpg']
        self.assertEqual(ref,lock['canonical'].replace('@',':'+vendor_setting.rsplit(':',1)[1]+'@'))
        self.assertIn(':1.30.1@',ref)
        from test_dev_runnable import FakeCtr
        state=FakeCtr({lock['canonical']:lock['digest']})
        self.assertTrue(json.loads(state(['crictl','inspecti',ref]))['status']['pinned'])
        self.assertEqual(list(state.state),[lock['canonical']])

    def test_all_generated_workload_image_references_resolve(self):
        lock=json.loads((dev.COMMON/'images.lock.json').read_text())
        objects=self.controllers+dev.database()+dev.endpoints()+dev.portal()+dev.gateway()
        self.assertGreater(len(list(guard.references(objects))),10)
        guard.require(objects,lock,'A')

    def test_missing_duplicate_or_drifted_operator_setting_is_refused(self):
        for value in ('ghcr.io/cloudnative-pg/cloudnative-pg:latest','ghcr.io/cloudnative-pg/cloudnative-pg:1.30.2'):
            with self.subTest(value=value),self.assertRaises(ValueError):dev.operator_image(value)
        upstream=vendor(dev.COMMON/'vendor',dev.COMMON/'artifacts.lock.json','cnpg.yaml')
        for fault in ('missing','duplicate'):
            changed=copy.deepcopy(upstream)
            manager=next(o for o in changed if o['kind']=='Deployment')['spec']['template']['spec']['containers'][0]
            entry=next(e for e in manager['env'] if e['name']=='OPERATOR_IMAGE_NAME')
            if fault=='missing':manager['env'].remove(entry)
            else:manager['env'].append(copy.deepcopy(entry))
            def vendored(directory,lock,name):return changed if name=='cnpg.yaml' else []
            with patch.object(dev,'vendor',side_effect=vendored),self.assertRaises(ValueError):dev.controllers()

    def test_current_render_diff_only_operator_env_vendor_locks_and_production_unchanged(self):
        def base(path):return subprocess.check_output(['git','-C',str(ROOT),'show',BASE+':'+path])
        for path,raw in dev.outputs().items():
            relative=path.relative_to(ROOT).as_posix();before=base(relative)
            # Preserve Amendment 13's original one-field receipt. Amendments
            # 10/11/14 independently bound today's outputs in test_platform_hygiene.
            raw=subprocess.check_output(['git','-C',str(ROOT),'show',
                '9404906da34175f9175822edf9b5be2cf10e7330:'+relative]).decode()
            if relative.endswith('/platform/workloads.yaml'):
                pattern=rb'(?m)(^        - name: OPERATOR_IMAGE_NAME\n          value: )[^\n]+'
                self.assertEqual(len(re.findall(pattern,before)),1)
                self.assertEqual(len(re.findall(pattern,raw.encode())),1)
                self.assertEqual(re.sub(pattern,rb'\1@@OPERATOR_IMAGE@@',before),re.sub(pattern,rb'\1@@OPERATOR_IMAGE@@',raw.encode()))
            else:self.assertEqual(before,raw.encode(),relative)
        for path in ('deploy/common/vendor/cnpg.yaml.gz','deploy/common/artifacts.lock.json','deploy/common/images.lock.json',
                     'deploy/common/bootstrap-images.lock.json','deploy/common/postgresql-image.lock.json','tools/ci/pr-baselines.json',
                     '00-setup-ubuntu-host.sh','host.env.example','user-data.yaml','user-data-remote.yaml','user-data.yaml.gz'):
            self.assertEqual(base(path),(ROOT/path).read_bytes(),path)

    def test_runbook_scopes_the_stuck_initdb_job_recovery(self):
        text=(ROOT/'docs/dev-environment.md').read_text()
        self.assertIn('delete job -l cnpg.io/cluster=twinfra-postgres,cnpg.io/jobRole=initdb',text)
        self.assertIn('Keep the Cluster, PVC and PV',text)
        self.assertIn('Pending',text)

    def test_ci_preview_changes_only_imports_and_the_scoped_image_reference_hook(self):
        path='tools/ci/kubeadm_dry_run.py'
        original=subprocess.check_output(['git','-C',str(ROOT),'show',BASE+':'+path]).decode()
        current=(ROOT/path).read_text()
        additions=['import sys\n',
            'import yaml\n\nsys.path.insert(0,str(Path(__file__).resolve().parents[1]))\n'
            'from platform_image_references import require as require_images, audit as audit_images, production_report\n\n',
            '            objects=[yaml.safe_load((preview/file).read_text()) for file in MANIFESTS]\n'
            "            image_lock=json.loads((source/'deploy/common/bootstrap-images.lock.json').read_text())\n"
            "            if name=='dev-cairo-1':require_images(objects,image_lock,'B','kubeadm')\n"
            '            else:\n'
            "                debt=audit_images(objects,image_lock,'B','kubeadm')\n"
            "                (directory/'production-image-reference-debt.txt').write_text(production_report(debt),encoding='utf-8')\n"]
        for block in additions:
            self.assertEqual(current.count(block),1)
            current=current.replace(block,'',1)
        self.assertEqual(current,original)


if __name__=='__main__':unittest.main()
