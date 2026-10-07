"""Safety and readiness tests for an intentionally separate local WSL profile."""
import re
import copy
import io
import json
import tarfile
from pathlib import Path
import tempfile
import unittest
import yaml

ROOT = Path(__file__).resolve().parents[1]
import sys
sys.path.insert(0, str(ROOT/'tools'))
import wsl_lab as lab
import wsl_proxy_marks as proxy_marks
from wsl_lab_acceptance import acceptance, runtime_projection, ready_or_completed
from wsl_lab_dns_image import build as build_dns, binary_from_export


class WslLabTests(unittest.TestCase):
    def setUp(self):
        self.p = lab.profile()
        self.facts = {'os':'ubuntu','version':'26.04','kernel':'6.18.33.2-microsoft-standard-WSL2',
            'pid1':'systemd','networking':'mirrored','cgroup':'cgroup2fs','btf':True,
            'memoryKiB':20*1024**2,'cpus':6,'freeDiskKiB':80*1024**2,'owned':False,
            'existingState':[],'activeRuntimes':[],'apiPortBusy':False,
            'routes':[{'dst':'default'},{'dst':'192.168.1.0/24'},{'dst':'10.20.0.0/24'}]}

    def test_updated_host_passes(self):
        self.assertIs(lab.check_facts(self.facts,self.p),self.facts)

    def test_wsl_host_routing_override_leaves_production_native_bpf_values(self):
        with tempfile.TemporaryDirectory() as directory:
            values=lab.render(Path(directory),'192.0.2.10','eth1')['cilium-values.yaml']
        self.assertTrue(values['bpf']['hostLegacyRouting'])
        self.assertTrue(values['bpf']['masquerade']);self.assertTrue(values['kubeProxyReplacement'])
        self.assertEqual(values['routingMode'],'native')
        production=yaml.safe_load((ROOT/'module-2/values/cilium.yaml').read_text())
        self.assertFalse(production['bpf']['hostLegacyRouting'])

    def test_proxy_fix_profile_is_the_owned_lab(self):
        import hashlib
        self.assertEqual(proxy_marks.PROFILE_SHA256,hashlib.sha256((ROOT/'lab/wsl/profile.json').read_bytes()).hexdigest())

    def proxy_fixture(self):
        return {'nftables':[{'chain':{'family':'ip','table':'filter','name':'WSLOUTPUT',
                                     'type':'filter','hook':'output','policy':'accept'}},
             {'rule':{'family':'ip','table':'filter','chain':'WSLOUTPUT','handle':2,
                      'expr':[{'mangle':{'key':{'meta':{'key':'mark'}},'value':1}}]}}]}

    def proxy_rule(self,tag,handle):
        return {'rule':{'family':'ip','table':'filter','chain':'WSLOUTPUT','handle':handle,'comment':tag,
                        'expr':[proxy_marks.expected_match(proxy_marks.MARKS[tag]),
                                {'counter':{'packets':1,'bytes':80}},{'return':None}]}}

    def test_proxy_fix_changes_marks_without_firewall_accepts(self):
        commands=proxy_marks.plan(self.proxy_fixture())
        self.assertEqual(len(commands),2)
        self.assertTrue(all('insert rule ip filter WSLOUTPUT' in command and 'counter return' in command for command in commands))
        self.assertTrue(all(' accept' not in command and ' flush ' not in command for command in commands))

    def test_proxy_fix_is_idempotent_and_removes_only_owned_rules(self):
        fixture=self.proxy_fixture()
        for index,tag in enumerate(proxy_marks.MARKS):fixture['nftables'].insert(1,self.proxy_rule(tag,10+index))
        self.assertEqual(proxy_marks.plan(fixture),[])
        commands=proxy_marks.plan(fixture,remove=True)
        self.assertEqual(set(commands),{'delete rule ip filter WSLOUTPUT handle 10','delete rule ip filter WSLOUTPUT handle 11'})

    def test_proxy_fix_repairs_rules_recreated_after_wsl_overwrite(self):
        fixture=self.proxy_fixture()
        for index,tag in enumerate(proxy_marks.MARKS):fixture['nftables'].append(self.proxy_rule(tag,10+index))
        commands=proxy_marks.plan(fixture)
        self.assertEqual(len(commands),4)
        self.assertTrue(all('handle 2' not in command for command in commands))

    def test_proxy_fix_refuses_unknown_chain_and_tampered_owned_rule(self):
        fixture=self.proxy_fixture();fixture['nftables'][0]['chain']['policy']='drop'
        with self.assertRaises(ValueError):proxy_marks.plan(fixture)
        fixture=self.proxy_fixture();fixture['nftables'][1]['rule']['expr'][0]['mangle']['value']=99
        with self.assertRaises(ValueError):proxy_marks.plan(fixture)
        fixture=self.proxy_fixture();tag=next(iter(proxy_marks.MARKS));rule=self.proxy_rule(tag,10)
        rule['rule']['expr']=[{'accept':None}];fixture['nftables'].insert(1,rule)
        with self.assertRaises(ValueError):proxy_marks.plan(fixture,remove=True)

    def test_small_host_rejected(self):
        self.facts['memoryKiB']=4*1024**2
        with self.assertRaises(ValueError): lab.check_facts(self.facts,self.p)

    def test_too_few_cpus(self):
        self.facts['cpus']=2
        with self.assertRaises(ValueError): lab.check_facts(self.facts,self.p)

    def test_disk_headroom(self):
        self.facts['freeDiskKiB']=10*1024**2
        with self.assertRaises(ValueError): lab.check_facts(self.facts,self.p)

    def test_no_nat_fallback(self):
        self.facts['networking']='nat'
        with self.assertRaises(ValueError): lab.check_facts(self.facts,self.p)

    def test_no_physical_host_adoption(self):
        self.facts['kernel']='6.8.0-generic'
        with self.assertRaises(ValueError): lab.check_facts(self.facts,self.p)

    def test_no_unmanaged_containerd(self):
        self.facts['existingState']=['/etc/containerd/config.toml']
        with self.assertRaises(ValueError): lab.check_facts(self.facts,self.p)

    def test_no_occupied_api(self):
        self.facts['apiPortBusy']=True
        with self.assertRaises(ValueError): lab.check_facts(self.facts,self.p)

    def test_owned_resume(self):
        self.facts.update(owned=True,activeRuntimes=['k3s','containerd'],existingState=['/etc/rancher/k3s'],apiPortBusy=True)
        lab.check_facts(self.facts,self.p)

    def test_owned_does_not_allow_unrelated_runtime(self):
        self.facts.update(owned=True,activeRuntimes=['docker'])
        with self.assertRaises(ValueError): lab.check_facts(self.facts,self.p)

    def test_kubeadm_never_adopted(self):
        self.facts.update(owned=True,existingState=['/etc/kubernetes/admin.conf'])
        with self.assertRaises(ValueError): lab.check_facts(self.facts,self.p)

    def test_route_overlap_rejected(self):
        self.facts['routes'].append({'dst':'10.0.0.0/8'})
        with self.assertRaises(ValueError): lab.check_facts(self.facts,self.p)

    def test_api_requires_client_auth_and_excludes_addons(self):
        c=lab.k3s_config(self.p,'192.168.1.9')
        self.assertIn('anonymous-auth=false',c['kube-apiserver-arg'])
        self.assertEqual(c['https-listen-port'],16443)
        self.assertEqual(c['bind-address'],'192.168.1.9')
        self.assertTrue(c['disable-kube-proxy'])
        self.assertEqual(c['flannel-backend'],'none')
        self.assertIn('local-storage',c['disable'])
        self.assertTrue(c['disable-helm-controller'])

    def test_manifests_keep_app_policy(self):
        for objects in (lab.manifests(self.p),lab.smoke(self.p)):
            lab.audit(objects)
        objects=lab.manifests(self.p)
        defaults=[o for o in objects if o['kind']=='NetworkPolicy' and o['metadata']['name']=='default-deny-all']
        self.assertEqual(len(defaults),3)
        self.assertTrue(all(o['spec']['egress']==[] and o['spec']['ingress']==[] for o in defaults))

    def test_dns_backend_needs_no_root_capability(self):
        dns=next(o for o in lab.manifests(self.p) if o['kind']=='Deployment')
        c=dns['spec']['template']['spec']['containers'][0]
        self.assertEqual(c['ports'][0]['containerPort'],1053)
        self.assertTrue(c['securityContext']['runAsNonRoot'])
        self.assertEqual(c['securityContext']['capabilities'],{'drop':['ALL']})

    def test_privileged_smoke_rejected(self):
        objects=lab.smoke(self.p)
        pod=next(o for o in objects if o['kind']=='Pod')
        pod['spec']['containers'][0]['securityContext']['privileged']=True
        with self.assertRaises(ValueError): lab.audit(objects)

    def test_cilium_images_keep_frozen_scope(self):
        with tempfile.TemporaryDirectory() as directory:
            lab.render(Path(directory),'192.168.1.9','eth1')
            rendered=yaml.safe_load((Path(directory)/'cilium-values.yaml').read_text())
            self.assertEqual(rendered['cni']['binPath'],'/opt/cni/bin')
            self.assertEqual(rendered['containerRuntimeEndpoint'],'/run/containerd/containerd.sock')
            self.assertEqual(rendered['cluster']['name'],'vcloud-wsl-local')
            self.assertEqual(rendered['k8sServiceHost'],'192.168.1.9')

    def test_latest_rejected(self):
        with self.assertRaises(ValueError): lab.mirrored('docker.io/busybox:latest',self.p)

    def test_evidence_refuses_wrong_cluster(self):
        with self.assertRaises(ValueError): acceptance(self.facts,{'items':[]},{'items':[]},'')

    def live_owner_fixture(self):
        ds={'apiVersion':'apps/v1','kind':'DaemonSet',
            'metadata':{'name':'cilium','namespace':'kube-system','uid':'owned-controller'}}
        pod=copy.deepcopy(next(o for o in lab.smoke(self.p) if o['kind']=='Pod'))
        pod['spec']['containers'][0]['image']=lab.load_policy()['agents']['DaemonSet/kube-system/cilium']['containers'][0]['image']
        pod['metadata'].update(name='cilium-example',namespace='kube-system',ownerReferences=[
            {'kind':'DaemonSet','name':'cilium','uid':'owned-controller','controller':True}])
        return pod,ds

    def test_runtime_audits_actual_pod_not_controller_template(self):
        pod,ds=self.live_owner_fixture()
        pod['spec']['containers'][0]['securityContext']['privileged']=True
        projected=runtime_projection({'items':[pod]},{'items':[ds]})
        self.assertEqual(projected[0]['kind'],'DaemonSet')
        with self.assertRaises(ValueError): lab.audit(projected)

    def test_runtime_rejects_spoofed_controller_uid(self):
        pod,ds=self.live_owner_fixture()
        pod['metadata']['ownerReferences'][0]['uid']='spoofed'
        with self.assertRaises(ValueError): runtime_projection({'items':[pod]},{'items':[ds]})

    def test_runtime_unowned_cilium_name_has_no_exception(self):
        pod,_=self.live_owner_fixture()
        pod['metadata'].pop('ownerReferences')
        pod['spec']['hostNetwork']=True
        with self.assertRaises(ValueError): lab.audit(runtime_projection({'items':[pod]},{'items':[]}))

    def test_ordinary_pod_owner_grants_no_node_exception(self):
        pod=copy.deepcopy(next(o for o in lab.smoke(self.p) if o['kind']=='Pod'))
        pod['metadata']['ownerReferences']=[{'kind':'Cluster','name':'db','uid':'db-owner','controller':True}]
        projected=runtime_projection({'items':[pod]},{'items':[]})
        lab.audit(projected)
        pod['spec']['containers'][0]['securityContext']['runAsUser']=0
        with self.assertRaises(ValueError):lab.audit(runtime_projection({'items':[pod]},{'items':[]}))

    def test_only_successful_job_pods_can_be_terminal(self):
        pod=copy.deepcopy(next(o for o in lab.smoke(self.p) if o['kind']=='Pod'))
        pod['metadata']['ownerReferences']=[{'kind':'Job','name':'scale','uid':'job-owner','controller':True}]
        pod['status']={'phase':'Succeeded','containerStatuses':[{'state':{'terminated':{'exitCode':0}}}]}
        self.assertTrue(ready_or_completed(pod))
        pod['status']['containerStatuses'][0]['state']['terminated']['exitCode']=1
        self.assertFalse(ready_or_completed(pod))
        pod['status']['containerStatuses'][0]['state']['terminated']['exitCode']=0
        pod['metadata']['ownerReferences'][0]['kind']='Deployment'
        self.assertFalse(ready_or_completed(pod))

    def test_evidence_requires_all_foundation_components(self):
        node={'metadata':{'name':'vcloud-wsl-local'},'status':{'conditions':[{'type':'Ready','status':'True'}],
              'nodeInfo':{'kubeletVersion':'v1.36.5+k3s1'}}}
        pods={'items':[next(o for o in lab.smoke(self.p) if o['kind']=='Pod')]}
        with self.assertRaisesRegex(ValueError,'Required foundation'):
            acceptance(self.facts,{'items':[node]},pods,'KubeProxyReplacement: True')

    def test_bootstrap_embedded_python_compiles(self):
        blocks=re.findall(r"<<'PY'\n(.*?)\nPY",(ROOT/'lab/wsl/bootstrap.sh').read_text(),re.S)
        self.assertGreaterEqual(len(blocks),3)
        for index,block in enumerate(blocks): compile(block,f'bootstrap-heredoc-{index}','exec')

    def test_containerd_uses_systemd_and_only_private_registry(self):
        example="""version = 3
[plugins.'io.containerd.cri.v1.images'.registry]
config_path = ''
[plugins.'io.containerd.cri.v1.images'.pinned_images]
sandbox = 'registry.k8s.io/pause:3.10.1'
[plugins.'io.containerd.cri.v1.runtime'.containerd.runtimes.runc.options]
SystemdCgroup = false
[plugins.'io.containerd.cri.v1.runtime'.cni]
bin_dirs = ['/opt/cni/bin']
conf_dir = '/etc/cni/net.d'
"""
        result=lab.containerd_config(example,self.p)
        self.assertIn('SystemdCgroup = true',result)
        self.assertIn(lab.mirrored(self.p['pauseImage'],self.p),result)

    def test_retry_rewrites_only_owned_old_loopback_endpoint(self):
        config={'clusters':[{'cluster':{'server':'https://127.0.0.1:6444','certificate-authority-data':'opaque'}}],
                'users':[{'user':{'client-key-data':'opaque-key'}}]}
        repaired=lab.repair_local_client_endpoint(config)
        self.assertEqual(repaired['clusters'][0]['cluster']['server'],'https://127.0.0.1:16444')
        self.assertEqual(repaired['users'],config['users'])
        config['clusters'][0]['cluster']['server']='https://other-cluster.example.com:6444'
        self.assertEqual(lab.repair_local_client_endpoint(config),config)

    def test_namespace_phase_has_helm_ownership(self):
        source=[lab.resource('Namespace','cilium-secrets'),lab.resource('ConfigMap','other')]
        source[0]['metadata']['annotations']=None
        result=lab.namespace_phase(source,True)
        self.assertEqual(len(result),1)
        self.assertEqual(result[0]['metadata']['annotations']['meta.helm.sh/release-name'],'cilium')

    def test_dns_derivative_deterministic_nonroot_no_xattr(self):
        with tempfile.TemporaryDirectory() as directory:
            first,second=Path(directory)/'first.tar',Path(directory)/'second.tar'
            a=build_dns(b'verified-binary',first);b=build_dns(b'verified-binary',second)
            self.assertEqual(first.read_bytes(),second.read_bytes())
            self.assertEqual(a,b)
            with tarfile.open(first) as archive:
                index=json.load(archive.extractfile('index.json'))
                manifest=json.load(archive.extractfile('blobs/sha256/'+index['manifests'][0]['digest'].split(':')[1]))
                config=json.load(archive.extractfile('blobs/sha256/'+manifest['config']['digest'].split(':')[1]))
                self.assertEqual(config['config']['User'],'65532:65532')
                layer=archive.extractfile('blobs/sha256/'+manifest['layers'][0]['digest'].split(':')[1]).read()
                with tarfile.open(fileobj=io.BytesIO(layer)) as files:
                    member=files.getmember('coredns')
                    self.assertEqual(member.pax_headers,{})
                    self.assertEqual(member.uid,65532)
            binary,parent=binary_from_export(first)
            self.assertEqual(binary,b'verified-binary')
            self.assertEqual(parent,a['manifestDigest'])


if __name__=='__main__': unittest.main()
