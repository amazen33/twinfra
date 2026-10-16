"""Offline WO-21 conformance; no host inventory, cluster, VM or credential operations."""
import copy
import importlib.util
import json
import os
from pathlib import Path
import re
import struct
import subprocess
import sys
import tempfile
import unittest
import zlib
from unittest.mock import patch

import yaml
from p2_receipts import receipt as p2_receipt

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import check_upstream_names as naming
import platform_dev as dev
from manifest_contract import podspec

spec = importlib.util.spec_from_file_location('disk', ROOT / 'deploy/hyperv/qcow2_to_vhd.py')
disk = importlib.util.module_from_spec(spec)
spec.loader.exec_module(disk)

CNPG_TAG_BASE='9c33d0c3bdae2447173df3797ec2c8666116992d'
CNPG_TAG_RECEIPT='a84169a63a941f98c989d4db4739e9470e803fe4'


class CNPGImage(unittest.TestCase):
    def test_cluster_has_receipt_tag_major18_and_locked_repo_digest(self):
        lock=json.loads((dev.COMMON/'images.lock.json').read_text())['images']['postgres']
        receipt=json.loads((dev.COMMON/'postgresql-image.lock.json').read_text())
        tag=receipt['image'].rsplit(':',1)[1]
        self.assertEqual(tag,'18.6.0-pgvector0.8.2');self.assertEqual(tag.split('.')[0],'18')
        cluster=next(o for o in dev.database() if o['kind']=='Cluster')
        self.assertEqual(cluster['spec']['imageName'],lock['canonical'].split('@')[0]+':'+tag+'@'+lock['digest'])
        self.assertEqual(cluster['spec']['imageName'].split('@')[1],receipt['manifestDigest'])

    def test_every_cnpg_cluster_in_every_deployable_profile_has_tag_and_digest(self):
        profiles=sorted((ROOT/'deploy/environments').glob('*/*/root.yaml'))
        self.assertTrue(profiles,'No deployable environment profiles')
        rendered=dev.outputs();clusters=[]
        for profile in profiles:
            for path in sorted(profile.parent.rglob('*.yaml')):
                raw=rendered.get(path,path.read_text())
                for obj in yaml.safe_load_all(raw):
                    if isinstance(obj,dict) and obj.get('kind')=='Cluster' and obj.get('apiVersion')=='postgresql.cnpg.io/v1':
                        clusters.append(obj)
                        with self.subTest(profile=profile.parent,cluster=obj['metadata']['name']):
                            self.assertEqual(obj['spec']['imageName'],dev.postgres_image())
                            self.assertRegex(obj['spec']['imageName'],r':18\.[^@]+@sha256:[a-f0-9]{64}$')
        self.assertTrue(clusters,'No CNPG Cluster found in deployable profiles')

    def test_tag_comes_from_receipt_but_repository_and_digest_come_from_lock(self):
        with tempfile.TemporaryDirectory() as tmp:
            common=Path(tmp);locked=json.loads((dev.COMMON/'images.lock.json').read_text())
            receipt=json.loads((dev.COMMON/'postgresql-image.lock.json').read_text())
            locked['images']['postgres']['canonical']='registry.twinfra.example.com:443/example/postgres@'+locked['images']['postgres']['digest']
            receipt['image']='different.example.com/receipt-only:18.7.0-pgvector0.8.3'
            for name,data in [('images.lock.json',locked),('postgresql-image.lock.json',receipt)]:
                (common/name).write_text(json.dumps(data))
            with patch.object(dev,'COMMON',common):
                self.assertEqual(dev.postgres_image(),locked['images']['postgres']['canonical'].replace('@',':18.7.0-pgvector0.8.3@'))

    def test_missing_version_tag_and_mismatched_receipt_digest_fail(self):
        with tempfile.TemporaryDirectory() as tmp:
            common=Path(tmp);(common/'images.lock.json').write_bytes((dev.COMMON/'images.lock.json').read_bytes())
            receipt=json.loads((dev.COMMON/'postgresql-image.lock.json').read_text())
            for fault in ({'image':receipt['image'].split(':')[0]}, {'image':'example:latest'}, {'manifestDigest':'sha256:'+'a'*64}):
                (common/'postgresql-image.lock.json').write_text(json.dumps(receipt|fault))
                with self.subTest(fault=fault),patch.object(dev,'COMMON',common),self.assertRaises(ValueError):
                    dev.postgres_image()

    def test_render_diff_is_only_cluster_image_name_and_all_locks_production_unchanged(self):
        def base(path):
            return subprocess.check_output(['git','-C',str(ROOT),'show',CNPG_TAG_BASE+':'+Path(path).as_posix()])
        rendered=dev.outputs()
        if (ROOT/'deploy/common/backup-config.json').is_file():
            from wo09_receipts import prior_outputs
            rendered=prior_outputs(rendered)
        for path,raw in rendered.items():
            relative=path.relative_to(ROOT).as_posix();before=base(relative)
            # Preserve Amendment 12's original one-field receipt; Amendment 13
            # independently bounds the current operator-env change.
            raw=subprocess.check_output(['git','-C',str(ROOT),'show',CNPG_TAG_RECEIPT+':'+relative]).decode()
            if relative=='deploy/environments/dev/cairo-1/platform/workloads.yaml':
                pattern=rb'(?m)^  imageName: [^\n]+$'
                self.assertEqual(len(re.findall(pattern,before)),1)
                self.assertEqual(len(re.findall(pattern,raw.encode())),1)
                self.assertEqual(re.sub(pattern,b'  imageName: @@CNPG_IMAGE@@',raw.encode()),
                                 re.sub(pattern,b'  imageName: @@CNPG_IMAGE@@',before))
            else:self.assertEqual(raw.encode(),before,relative)
        for path in ('deploy/common/images.lock.json','deploy/common/postgresql-image.lock.json',
                     'deploy/common/bootstrap-images.lock.json','tools/ci/pr-baselines.json',
                     '00-setup-ubuntu-host.sh','host.env.example','user-data.yaml','user-data-remote.yaml','user-data.yaml.gz'):
            # Preserve Amendment 12's original lock receipt; WO-34 bounds the
            # current two-pin refresh in test_build_images instead.
            actual=(subprocess.check_output(['git','-C',str(ROOT),'show',CNPG_TAG_RECEIPT+':'+path])
                    if path in ('deploy/common/images.lock.json','deploy/common/bootstrap-images.lock.json') else p2_receipt(path))
            self.assertEqual(actual,base(path),path)


class Naming(unittest.TestCase):
    def setUp(self):
        self.labels = dev.labels('argocd')
        self.upstream = {'kind':'ConfigMap','metadata':{'name':'argocd-cm','labels':self.labels}}
        self.registry = {'projects':[{'project':'argo-cd','names':[{'kind':'ConfigMap','name':'argocd-cm'}]}]}
        self.sources = {'argo-cd':[self.upstream]}

    def test_listed_upstream_name_present_passes(self):
        naming.validate([self.upstream], self.registry, self.sources)

    def test_non_twinfra_name_unlisted_fails(self):
        obj = copy.deepcopy(self.upstream); obj['metadata']['name']='foreign-cm'
        with self.assertRaisesRegex(ValueError,'Unregistered'):
            naming.validate([obj], self.registry, self.sources)

    def test_registered_name_missing_from_source_fails(self):
        with self.assertRaisesRegex(ValueError,'absent'):
            naming.validate([self.upstream], self.registry, {'argo-cd':[]})

    def test_twinfra_owned_name_with_legacy_word_fails(self):
        for word in ('lab','wsl','vcloud'):
            obj=copy.deepcopy(self.upstream);obj['metadata']['name']='twinfra-'+word+'-secret'
            with self.assertRaisesRegex(ValueError,'Forbidden'):
                naming.validate([obj], self.registry, self.sources)

    def test_application_project_not_whitelisted(self):
        for kind in ('Application','AppProject'):
            obj={'kind':kind,'metadata':{'name':'argocd','labels':self.labels}}
            registry={'projects':[{'project':'fake','names':[{'kind':kind,'name':'argocd'}]}]}
            with self.assertRaisesRegex(ValueError,'Twinfra-owned'):
                naming.validate([obj],registry,{'fake':[obj]})


class Profile(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.controllers=dev.controllers()
        cls.services=dev.endpoints()+dev.portal()+dev.gateway()

    def test_upstream_selectors_and_fixed_config_names_preserved(self):
        from platform_sources import vendor
        original=vendor(dev.COMMON/'vendor',dev.COMMON/'artifacts.lock.json','argocd-core.yaml')
        current={(o['kind'],o['metadata']['name']):o for o in self.controllers}
        for obj in original:
            key=(obj['kind'],obj['metadata']['name'])
            if key in current and 'selector' in obj.get('spec',{}):
                self.assertEqual(obj['spec']['selector'],current[key]['spec']['selector'])
        cm=current[('ConfigMap','argocd-cmd-params-cm')]
        self.assertEqual(cm['data']['redis.server'],'argocd-redis:6379')

    def test_valkey_restricted_and_no_redis_image(self):
        workloads=[o for o in self.controllers if podspec(o)]
        cache=next(o for o in workloads if o['metadata']['name']=='argocd-redis')
        self.assertIn('/valkey/valkey@sha256:',podspec(cache)['containers'][0]['image'])
        self.assertEqual(podspec(cache)['volumes'][0]['secret']['secretName'],'twinfra-argocd-cache')
        for obj in workloads+self.services:
            pod=podspec(obj)
            if not pod:continue
            self.assertTrue(pod['securityContext']['runAsNonRoot'])
            for c in pod.get('containers',[])+pod.get('initContainers',[]):
                self.assertFalse(c['securityContext']['allowPrivilegeEscalation'])
                self.assertEqual(c['securityContext']['capabilities']['drop'],['ALL'])
                self.assertEqual(c['imagePullPolicy'],'IfNotPresent')
                self.assertIn('@sha256:',c['image'])
                self.assertNotIn('/redis:',c['image'])

    def test_only_initial_components_and_no_active_gpu_hpc(self):
        text=yaml.safe_dump_all(self.services)
        for word in ('local'+'stack','grafana','knative','nvidia.com/gpu','spinifex'):
            self.assertNotIn(word,text)
        portal=next(o for o in self.services if o['kind']=='Deployment' and o['metadata']['name']=='twinfra-console')
        self.assertIn('twinfra-keycloak-tls',str(podspec(portal)['volumes']))
        self.assertIn('twinfra-console',str(podspec(portal)['containers'][0]['env']))

    def test_shared_seed_control_plane_and_region_parameters(self):
        ssot=yaml.safe_load((ROOT/'vcloud-ssot.yaml').read_text())
        for row in ssot['addressPlan']:
            if row['environment']!='dev':continue
            env=dev.host_environment(row)
            self.assertIn('CONTROL_PLANE_ENDPOINT=api.dev.'+row['region']+'.twinfra.example.com:6443',env)
            self.assertIn('POD_CIDR='+row['podCidr'],env)
            for disabled in ('ENABLE_GPU','INSTALL_HPC','GPU_SMOKE_TEST','RUN_SMOKE_TESTS'):
                self.assertIn(disabled+'=false',env)
            if row.get('delivery')!='bare-metal':
                data=yaml.safe_load(dev.seed(row)['user-data'])
                self.assertTrue(data['ssh_pwauth'] is False)
                self.assertNotIn('passwd',str(data['users'][0].keys()).replace('lock_passwd',''))

    def test_protected_main_and_kustomize_labels_without_selector_mutation(self):
        for app in dev.applications()[0]+dev.applications()[1]:
            if app['kind']=='Application':self.assertEqual(app['spec']['source']['targetRevision'],'main')
        for folder in ('platform','services'):
            k=yaml.safe_load((dev.TARGET/folder/'kustomization.yaml').read_text())
            self.assertFalse(k['labels'][0]['includeSelectors'])

    def test_seed_has_no_wsl_dependency(self):
        for code in ('tools/platform_dev.py','tools/platform_resources.py','tools/platform_sources.py','console/aws_views.py','deploy/common/runtime-config.py'):
            self.assertNotIn('from wsl_', (ROOT/code).read_text())

    def test_node_approval_derivative_changes_only_registry_and_approved_dev_etcd_patch(self):
        approved=json.loads((ROOT/'security/node-exceptions.json').read_text())
        rendered={}
        for profile in ('production','dev-cairo-1'):
            env=dict(os.environ,PLATFORM_PROFILE=profile)
            raw=subprocess.check_output([env.get('BASH_BINARY','bash'),'-c',
                'source "$1"; render_exception_policy','_',
                (ROOT/'00-setup-ubuntu-host.sh').as_posix()],env=env,text=True)
            rendered[profile]=json.loads(raw)
        self.assertEqual(rendered['production'],approved)
        derivative=rendered['dev-cairo-1']
        self.assertIn('sourcePolicySHA256',derivative)
        derivative.pop('sourcePolicySHA256');derivative.pop('profile')
        normalized=json.loads(json.dumps(derivative).replace('registry.twinfra.example.com',
                                                            'registry.vcloud.example.com'))
        expected=copy.deepcopy(approved)
        expected['controlPlane']['Pod/kube-system/etcd']['image']='registry.vcloud.example.com/registry.k8s.io/etcd:3.6.15-0'
        self.assertEqual(normalized,expected)


class DiskConversion(unittest.TestCase):
    def qcow(self):
        result=bytearray(2560)
        struct.pack_into('>IIQIIQIIQ',result,0,0x514649fb,3,0,0,9,1536,0,1,512)
        struct.pack_into('>I',result,100,104)
        struct.pack_into('>Q',result,512,1024)
        struct.pack_into('>QQQ',result,1024,1536 | (1<<63),1,2048 | (1<<62))
        result[1536:2048]=b'A'*512
        compressor=zlib.compressobj(wbits=-15);data=compressor.compress(b'B'*512)+compressor.flush()
        result[2048:2048+len(data)]=data
        return result

    def test_plain_zero_and_compressed_clusters_footer_checksum(self):
        with tempfile.TemporaryDirectory() as tmp:
            source=Path(tmp)/'in.img';target=Path(tmp)/'out.vhd';source.write_bytes(self.qcow())
            self.assertEqual(disk.convert(source,target),1536)
            raw=target.read_bytes();self.assertEqual(raw[:1536],b'A'*512+b'\0'*512+b'B'*512)
            f=bytearray(raw[-512:]);self.assertEqual(f[:8],b'conectix')
            checksum=struct.unpack_from('>I',f,64)[0];f[64:68]=b'\0'*4
            self.assertEqual(checksum,(~sum(f))&0xffffffff)
            self.assertEqual(struct.unpack_from('>I',f,60)[0],2)

    def test_unsupported_header_features_fail_closed(self):
        for offset,fmt,value in [(8,'>Q',512),(32,'>I',1),(72,'>Q',1),(72,'>Q',4),(72,'>Q',16)]:
            with tempfile.TemporaryDirectory() as tmp:
                raw=self.qcow();struct.pack_into(fmt,raw,offset,value);source=Path(tmp)/'in.img';source.write_bytes(raw)
                with self.assertRaises(ValueError):disk.convert(source,Path(tmp)/'out.vhd')

    def test_out_of_bounds_cluster_and_existing_destination_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            source=Path(tmp)/'in.img';target=Path(tmp)/'out.vhd';raw=self.qcow();struct.pack_into('>Q',raw,1024,4096);source.write_bytes(raw)
            with self.assertRaisesRegex(ValueError,'outside'):disk.convert(source,target)
            with self.assertRaises(FileExistsError):disk.convert(source,target)


class RuntimeConfiguration(unittest.TestCase):
    def test_keycloak_and_gateway_use_same_mounted_client_secret(self):
        module_spec=importlib.util.spec_from_file_location('runtime',ROOT/'deploy/common/runtime-config.py')
        runtime=importlib.util.module_from_spec(module_spec);module_spec.loader.exec_module(runtime)
        module_spec=importlib.util.spec_from_file_location('gateway',ROOT/'deploy/common/gateway-config.py')
        gateway=importlib.util.module_from_spec(module_spec);module_spec.loader.exec_module(gateway)
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            files={'auth/password':'synthetic-db-credential','admin/username':'synthetic-admin',
                   'admin/password':'synthetic-admin-credential','oidc/client_secret':'synthetic-client',
                   'oidc/session_secret':'x'*48,
                   'realm-source/twinfra-realm.json':(dev.COMMON/'keycloak-realm.json').read_text()}
            for name,value in files.items():
                p=root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(value)
            (root/'runtime').mkdir()
            runtime.configure('keycloak',root)
            realm=json.loads((root/'import/twinfra-realm.json').read_text())
            self.assertEqual(realm['clients'][0]['secret'],'synthetic-client')
            source=root/'gateway';source.mkdir();target=root/'conf';target.mkdir()
            (source/'apisix.template.json').write_text((dev.COMMON/'apisix-routes.json').read_text())
            (source/'config.yaml').write_text('apisix: {}')
            gateway.configure(source,root/'oidc',target)
            routes=json.loads((target/'apisix.yaml').read_text().split('\n#END')[0])
            for route in routes['routes']:
                self.assertEqual(route['plugins']['openid-connect']['client_secret'],realm['clients'][0]['secret'])
            text=(root/'runtime/keycloak.conf').read_text()
            self.assertIn('sslmode=verify-full',text)
            self.assertNotIn('db-password=',(dev.COMMON/'keycloak-realm.json').read_text())

    def test_gateway_missing_secret_fails_closed_without_config(self):
        module_spec=importlib.util.spec_from_file_location('gateway',ROOT/'deploy/common/gateway-config.py')
        gateway=importlib.util.module_from_spec(module_spec);module_spec.loader.exec_module(gateway)
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);source=root/'source';auth=root/'auth';target=root/'conf'
            for path in (source,auth,target):path.mkdir()
            (source/'apisix.template.json').write_text((dev.COMMON/'apisix-routes.json').read_text())
            (auth/'client_secret').write_text('');(auth/'session_secret').write_text('x'*48)
            with self.assertRaisesRegex(ValueError,'gated'):gateway.configure(source,auth,target)
            self.assertFalse((target/'apisix.yaml').exists())


class WorkerPlan(unittest.TestCase):
    def plan(self,route):
        env=dict(os.environ,CONTROL_PLANE_ENDPOINT='api.dev.cairo-1.twinfra.example.com:6443',
                 WORKER_IP='10.50.0.12',CONTROL_PLANE_IP='10.50.0.10',NODE_NAME='twinfra-worker-1')
        # Mock only the route read. Never execute --join or call kubeadm.
        code='ip() { printf "%s\\n" "$MOCK_ROUTE"; }; export -f ip; exec bash "$1" --plan'
        env['MOCK_ROUTE']=json.dumps(route)
        return subprocess.run([env.get('BASH_BINARY','bash'),'-c',code,'_',
            (ROOT/'deploy/common/join-worker.sh').as_posix()],env=env,capture_output=True,text=True)

    def test_direct_common_l2_worker_plan(self):
        result=self.plan([{'dev':'eth0','prefsrc':'10.50.0.12'}])
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertIn('no join/token read',result.stdout)

    def test_routed_worker_refused(self):
        result=self.plan([{'dev':'eth0','prefsrc':'10.50.0.12','gateway':'10.50.0.1'}])
        self.assertEqual(result.returncode,2,result.stderr)
        self.assertIn('no join attempted',result.stdout)


if __name__=='__main__':unittest.main()
