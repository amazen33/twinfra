"""WO-31 10/11/14 offline contracts; no host, cluster or credential access."""
import importlib.util
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest

import yaml
from p2_receipts import receipt as p2_receipt

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
import platform_dev as dev
from platform_network_boundary import audit_boundary,CILIUM_NODE_EXCEPTIONS

BASE='9404906da34175f9175822edf9b5be2cf10e7330'
NAMESPACES=('twinfra-platform-services','twinfra-workload-apps','twinfra-hpc-compute')


def deny(namespace=NAMESPACES[0]):
    return {'apiVersion':'networking.k8s.io/v1','kind':'NetworkPolicy',
        'metadata':{'name':'twinfra-default-deny','namespace':namespace},
        'spec':{'podSelector':{},'policyTypes':['Ingress','Egress'],'ingress':[],'egress':[]}}


def workload(kind='Deployment',namespace=NAMESPACES[0],name='twinfra-fixture',pod=None):
    spec=pod or {'containers':[{'name':'fixture','image':'fixture'}]}
    if kind=='Pod':body=spec
    elif kind=='CronJob':body={'jobTemplate':{'spec':{'template':{'spec':spec}}}}
    else:body={'template':{'spec':spec}}
    return {'apiVersion':'apps/v1','kind':kind,'metadata':{'name':name,'namespace':namespace},'spec':body}


class NetworkBoundary(unittest.TestCase):
    def check(self,*objects,required=()):return audit_boundary([deny(),*objects],required)

    def test_private_clusterip_and_explicit_allow_edges_pass(self):
        service=dev.service('twinfra-fixture',3000)
        self.assertEqual(self.check(service,workload())['status'],'passed')
        self.assertEqual(audit_boundary(dev.network())['status'],'passed')

    def test_nodeport_loadbalancer_and_externalips_fail(self):
        for fault in ({'type':'NodePort'},{'type':'LoadBalancer'},{'externalIPs':['192.168.1.3']},
                      {'ports':[{'port':443,'nodePort':30443}]}):
            service=dev.service('twinfra-fixture',443);service['spec'].update(fault)
            with self.subTest(fault=fault):self.assertEqual(self.check(service)['status'],'failed')
        for value in ([],None):
            service=dev.service('twinfra-fixture',443);service['spec']['externalIPs']=value
            self.assertEqual(self.check(service)['status'],'passed')

    def test_hostnetwork_in_every_pod_template_fails(self):
        for kind in ('Pod','Deployment','DaemonSet','StatefulSet','Job','CronJob','Service'):
            obj=workload(kind,pod={'hostNetwork':True,'containers':[]})
            if kind=='Service':obj['apiVersion']='serving.knative.dev/v1'
            with self.subTest(kind=kind):self.assertEqual(self.check(obj)['status'],'failed')

    def test_hostport_in_container_init_and_ephemeral_fails(self):
        for category in ('containers','initContainers','ephemeralContainers'):
            for port in (8080,0):
                obj=workload(pod={category:[{'name':'fixture','ports':[{'containerPort':8080,'hostPort':port}]}]})
                with self.subTest(category=category,port=port):self.assertEqual(self.check(obj)['status'],'failed')

    def test_node_exception_list_has_only_three_exact_cilium_objects(self):
        self.assertEqual(CILIUM_NODE_EXCEPTIONS,frozenset({('DaemonSet','kube-system','cilium'),
            ('DaemonSet','kube-system','cilium-envoy'),('Deployment','kube-system','cilium-operator')}))
        for kind,namespace,name in CILIUM_NODE_EXCEPTIONS:
            obj=workload(kind,namespace,name,{'hostNetwork':True,'containers':[{'ports':[{'hostPort':9879}]}]})
            self.assertEqual(self.check(obj)['status'],'passed')

    def test_node_exception_cannot_move_namespace_kind_or_name(self):
        for kind,namespace,name in (('DaemonSet',NAMESPACES[0],'cilium'),('Pod','kube-system','cilium'),
                ('Deployment','kube-system','foreign-operator'),('DaemonSet','kube-system','cilium-copy')):
            obj=workload(kind,namespace,name,{'hostNetwork':True,'containers':[]})
            with self.subTest(kind=kind,namespace=namespace,name=name):self.assertEqual(self.check(obj)['status'],'failed')

    def test_every_twinfra_namespace_needs_its_own_ingress_default_deny(self):
        report=self.check(required=NAMESPACES)
        self.assertEqual(report['status'],'failed')
        self.assertEqual(len(report['violations']),2)
        self.assertEqual(audit_boundary([deny(n) for n in NAMESPACES],NAMESPACES)['status'],'passed')

    def test_selector_specific_egress_only_or_allowing_policy_is_not_default_deny(self):
        for fault in ({'podSelector':{'matchLabels':{'app':'one'}}},{'policyTypes':['Egress']},
                      {'ingress':[{}]}):
            policy=deny();policy['spec'].update(fault)
            with self.subTest(fault=fault):self.assertEqual(audit_boundary([policy])['status'],'failed')

    def test_namespace_ownership_and_crd_schema_text_are_handled(self):
        named=workload(namespace='twinfra-new-namespace')
        self.assertEqual(self.check(named)['status'],'failed')
        namespace={'kind':'Namespace','metadata':{'name':'owned-namespace','labels':{'twinfra.io/managed':'true'}}}
        self.assertEqual(self.check(namespace)['status'],'failed')
        upstream={'kind':'Namespace','metadata':{'name':'cilium-secrets','labels':
            {'app.kubernetes.io/part-of':'cilium','twinfra.io/environment':'dev','twinfra.io/region':'cairo-1'}}}
        self.assertEqual(self.check(upstream)['status'],'passed')
        crd={'kind':'CustomResourceDefinition','metadata':{'name':'fixtures.example.com'},
             'spec':{'versions':[{'schema':{'openAPIV3Schema':{'properties':{'hostNetwork':{'default':True},
                 'hostPort':{'default':8080},'type':{'enum':['NodePort','LoadBalancer']}}}}}]}}
        self.assertEqual(self.check(crd)['status'],'passed')


class Hygiene(unittest.TestCase):
    def test_every_generated_dev_application_has_server_side_diff_and_apply(self):
        apps=[]
        for region in ('cairo-1','cairo-2'):
            root,children=dev.applications(region)
            regional=[obj for obj in root+children if obj['kind']=='Application']
            self.assertEqual({app['metadata']['name'] for app in regional},{'twinfra-root','twinfra-platform','twinfra-services'})
            for app in regional:
                self.assertEqual(app['metadata']['labels']['twinfra.io/region'],region)
                self.assertTrue(app['spec']['source']['path'].startswith('deploy/environments/dev/'+region+'/'))
            apps.extend(regional)
        # Inspect every currently persisted dev Application, too. Cairo-2 has
        # only a cold seed until WO-23; no broken workload path is deployed here.
        for profile in sorted((ROOT/'deploy/environments/dev').glob('*/root.yaml')):
            for path in (profile,profile.parent/'apps/applications.yaml'):
                apps.extend(o for o in yaml.safe_load_all(path.read_text()) if o and o.get('kind')=='Application')
        for app in apps:
            options=set(app['metadata']['annotations']['argocd.argoproj.io/compare-options'].split(','))
            self.assertTrue({'ServerSideDiff=true','IncludeMutationWebhook=true'} <= options)
            self.assertIn('ServerSideApply=true',app['spec']['syncPolicy']['syncOptions'])
            self.assertNotIn('ignoreDifferences',app['spec'])
        with self.assertRaises(ValueError):dev.applications('production')

    def test_actual_openbao_runtime_configuration_omits_unsupported_field(self):
        spec=importlib.util.spec_from_file_location('hygiene_runtime',dev.COMMON/'runtime-config.py')
        runtime=importlib.util.module_from_spec(spec);spec.loader.exec_module(runtime)
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'auth').mkdir();(root/'runtime').mkdir()
            (root/'auth/password').write_text('synthetic-test-only')
            runtime.configure('openbao',root)
            config=(root/'runtime/openbao.hcl').read_text()
            self.assertNotIn('disable_mlock',config)
            self.assertIn('sslmode=verify-full',config);self.assertIn('tls_cert_file',config)
        cm=next(o for o in dev.endpoints() if o['kind']=='ConfigMap' and o['metadata']['name']=='twinfra-runtime-config')
        self.assertNotIn('disable_mlock',cm['data']['runtime-config.py'])

    def test_runbook_crd_overlay_applies_use_server_side_and_force_conflicts(self):
        text=(ROOT/'docs/dev-environment.md').read_text()
        commands=[line.strip() for line in text.splitlines() if 'kubectl' in line and ' apply ' in line and ' -k ' in line]
        self.assertEqual(len(commands),2)
        for command in commands:
            self.assertIn('--server-side',command);self.assertIn('--force-conflicts',command)
        self.assertIn('no matches for kind Cluster/Database',text)
        self.assertIn('Server-Side Diff is not performed on initial creation',text)
        self.assertIn('rollout restart deployment/twinfra-openbao',text)
        self.assertIn('Updating a ConfigMap does not re-run that init container',text)

    def test_step11_primary_forwards_run_on_laptop_loopback_with_ssh_alternative(self):
        text=(ROOT/'docs/dev-environment.md').read_text().split('11. **Owner:',1)[1].split('### Runtime pin',1)[0]
        primary=text.split('Alternative:',1)[0]
        for service,ports in (('twinfra-gateway','18444:9443'),('twinfra-keycloak','18443:443'),('argocd-server','18081:443')):
            self.assertIn('kubectl --context twinfra-dev-cairo-1 -n twinfra-platform-services port-forward --address 127.0.0.1 svc/'+service+' '+ports,primary)
        self.assertNotIn('sudo kubectl',primary);self.assertNotIn('--address 0.0.0.0',text)
        self.assertIn('StrictHostKeyChecking=yes',text);self.assertIn('ExitOnForwardFailure=yes',text)

    def test_signin_passwords_flow_only_to_clipboard_and_console_role_is_explicit(self):
        text=(ROOT/'docs/dev-environment.md').read_text().split('11. **Owner:',1)[1].split('### Runtime pin',1)[0]
        snippets=re.findall(r'```powershell\n(.*?)```',text,re.S)
        secrets=[block for block in snippets if 'get secret' in block]
        self.assertEqual(len(secrets),2)
        for snippet in secrets:
            self.assertIn("-o jsonpath='{.data.password}'",snippet)
            self.assertIn('FromBase64String',snippet);self.assertIn('Set-Clipboard',snippet)
            self.assertNotRegex(snippet,r'Write-Host|Write-Output|Out-File|Tee-Object')
        self.assertIn('twinfra-keycloak-admin',text);self.assertIn('argocd-initial-admin-secret',text)
        self.assertIn('realm `twinfra`',text);self.assertIn('`twinfra-console` / `console.admin`',text)
        self.assertIn('realm import has no users',text);self.assertIn('TOTP',text)

    def test_network_runbook_states_host_only_boundary_and_future_host_policy(self):
        text=(ROOT/'docs/dev-environment.md').read_text()
        self.assertIn('## Network boundary',text)
        for value in ('kube-proxy-replacement','enable-host-firewall','routing-mode','enable-bpf-masquerade',
                      'bpf-lb-external-clusterip','CiliumClusterwideNetworkPolicy'):
            self.assertIn(value,text)
        self.assertIn('before netfilter',text)

    def test_render_diffs_are_only_dev_app_annotations_and_openbao_configuration(self):
        rendered=dev.outputs()
        if (ROOT/'deploy/common/backup-config.json').is_file():
            from wo09_receipts import prior_outputs
            rendered=prior_outputs(rendered)
        for path,raw in rendered.items():
            relative=path.relative_to(ROOT).as_posix()
            original=subprocess.check_output(['git','-C',str(ROOT),'show',BASE+':'+relative])
            # Keep the original WO-31 receipt exact; WO-34 separately bounds
            # current image pins, services images and the dev bootstrap seed.
            if relative.endswith(('services/workloads.yaml','seed/user-data','host.env')):
                raw=subprocess.check_output(['git','-C',str(ROOT),'show','b55c0ea3a7805e80c218dcc13a5bfbea7e259a24:'+relative]).decode()
            if relative.endswith(('root.yaml','apps/applications.yaml','services/workloads.yaml')):
                objects=list(yaml.safe_load_all(raw))
                for obj in objects:
                    if obj.get('kind')=='Application':
                        self.assertEqual(obj['metadata']['annotations'].pop('argocd.argoproj.io/compare-options'),'ServerSideDiff=true,IncludeMutationWebhook=true')
                    if obj.get('kind')=='ConfigMap' and obj['metadata']['name']=='twinfra-runtime-config':
                        code=obj['data']['runtime-config.py']
                        self.assertEqual(code.count('ui = true\\napi_addr'),1)
                        obj['data']['runtime-config.py']=code.replace('ui = true\\napi_addr','ui = true\\ndisable_mlock = true\\napi_addr')
                raw=yaml.safe_dump_all(objects,sort_keys=False)
            self.assertEqual(raw.encode(),original,relative)
        for path in ('00-setup-ubuntu-host.sh','host.env.example','user-data.yaml','user-data-remote.yaml','user-data.yaml.gz',
                     'deploy/common/images.lock.json','deploy/common/bootstrap-images.lock.json','tools/ci/pr-baselines.json',
                     'vcloud-ssot.yaml','deploy/common/host-admin.py','tools/platform_host.py'):
            original=subprocess.check_output(['git','-C',str(ROOT),'show',BASE+':'+path])
            current=(subprocess.check_output(['git','-C',str(ROOT),'show','b55c0ea3a7805e80c218dcc13a5bfbea7e259a24:'+path])
                     if path in ('deploy/common/images.lock.json','deploy/common/bootstrap-images.lock.json') else p2_receipt(path))
            if not path.endswith('.gz'):current=current.replace(b'\r\n',b'\n')
            self.assertEqual(current,original,path)

    def test_owner_evidence_is_attributed_and_soak_and_tester_stay_pending(self):
        text=(ROOT/'docs/acceptance/dev-environment-2026-10-13.md').read_text()
        self.assertIn('Owner-reported live evidence',text)
        for value in ('3b6ec82','11/11','92k','cairo-1a','9c33d0c','9404906','2026-10-13T14:43:38Z',
                      'Healthy/OutOfSync','console.admin','ePSA'):
            self.assertIn(value,text)
        self.assertIn('Soak verdict: Pending',text);self.assertIn('Result: Pending',text)
        self.assertNotIn('Result: Accepted',text)


if __name__=='__main__':unittest.main()
