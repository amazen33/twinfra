"""Offline WO-21 conformance; no host inventory, cluster, VM or credential operations."""
import copy
import importlib.util
import json
import os
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest
import zlib

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import check_upstream_names as naming
import platform_dev as dev
from manifest_contract import podspec

spec = importlib.util.spec_from_file_location('disk', ROOT / 'deploy/hyperv/qcow2_to_vhd.py')
disk = importlib.util.module_from_spec(spec)
spec.loader.exec_module(disk)


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
            seed=dev.seed(row);data=yaml.safe_load(seed['user-data'])
            env=next(f['content'] for f in data['write_files'] if f['path']=='/etc/twinfra-host.env')
            self.assertIn('CONTROL_PLANE_ENDPOINT=api.dev.'+row['region']+'.twinfra.example.com:6443',env)
            self.assertIn('POD_CIDR='+row['podCidr'],env)
            for disabled in ('ENABLE_GPU','INSTALL_HPC','GPU_SMOKE_TEST','RUN_SMOKE_TESTS'):
                self.assertIn(disabled+'=false',env)
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

    def test_node_approval_derivative_changes_only_registry_prefix(self):
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
        self.assertEqual(normalized,approved)


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
