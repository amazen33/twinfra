"""CI/CD contracts and real local Git promotion tests. No cluster or remote repository writes."""
import copy
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import yaml

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
import module3
from check_module3_cluster import validate_storage
from render_module3 import resources


def load(name,path):
    spec=importlib.util.spec_from_file_location(name,ROOT/path)
    result=importlib.util.module_from_spec(spec);spec.loader.exec_module(result);return result


runner=load('ci_runner','module-3/runtime/runner.py')
verifier=load('ci_verifier','module-3/runtime/validate_workload.py')
COMMIT='a'*40; DIGEST='sha256:'+'b'*64


class InputAndPromotionGuards(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.path=Path(self.temp.name)/'workload.yaml'
        self.baseline=json.loads((ROOT/'module-3/gitops/workload.yaml').read_text())
        self.path.write_text(json.dumps(self.baseline))
    def tearDown(self): self.temp.cleanup()
    def candidate(self): return runner.update_manifest(self.path,COMMIT,DIGEST)
    def test_exact_source_and_digest_accepted(self):
        self.assertTrue(verifier.validate(self.candidate(),self.baseline))
    def test_shell_metacharacters_and_zero_commit_rejected(self):
        for value in ['main','0'*40,'a'*40+';echo hello','../main','a'*39]:
            with self.subTest(value=value),self.assertRaises(ValueError): runner.revision(value)
    def test_digest_cannot_select_another_registry(self):
        for value in ['latest','sha256:'+'x'*64,'evil.invalid/repo:1.0.0',DIGEST+'\n']:
            with self.subTest(value=value),self.assertRaises(ValueError): runner.digest(value)
    def test_stale_build_cannot_promote(self):
        with self.assertRaisesRegex(ValueError,'Stale'): runner.ensure_current_source('c'*40,COMMIT)
    def test_rebuild_digest_change_requires_review(self):
        self.path.write_text(json.dumps(self.candidate()))
        with self.assertRaisesRegex(ValueError,'different digest'): runner.update_manifest(self.path,COMMIT,'sha256:'+'c'*64)
    def test_application_host_mount_rejected(self):
        obj=self.candidate();obj['spec']['template']['spec']['volumes']=[{'name':'node','hostPath':{'path':'/'}}]
        with self.assertRaises(ValueError): verifier.validate(obj,self.baseline)
    def test_root_and_privilege_cannot_be_promoted(self):
        for change in [{'runAsUser':0},{'privileged':True},{'allowPrivilegeEscalation':True},{'capabilities':{'add':['SYS_ADMIN']}}]:
            obj=self.candidate();obj['spec']['template']['spec']['containers'][0]['securityContext'].update(change)
            with self.subTest(change=change),self.assertRaises(ValueError): verifier.validate(obj,self.baseline)
    def test_token_execution_and_scale_drift_rejected(self):
        for mutate in [lambda o:o['spec']['template']['spec'].update(automountServiceAccountToken=True),
                       lambda o:o['spec']['template']['spec']['containers'][0].update(command=['sh']),
                       lambda o:o['spec']['template']['metadata']['annotations'].update({'autoscaling.knative.dev/max-scale':'100'})]:
            obj=self.candidate();mutate(obj)
            with self.assertRaises(ValueError): verifier.validate(obj,self.baseline)
    def test_source_digest_attribution_rejected(self):
        obj=self.candidate();obj['metadata']['annotations']['vcloud.io/source-revision']='c'*40
        with self.assertRaises(ValueError): verifier.validate(obj,self.baseline)
    def test_credentials_never_live_in_environment(self):
        env=runner.git_env('/var/run/vcloud/git')
        self.assertNotIn('TOKEN',env);self.assertNotIn('PASSWORD',env)
        self.assertEqual(env['GIT_CONFIG_VALUE_1'],'true')
    def test_askpass_rejects_a_lookalike_host(self):
        result=subprocess.run([sys.executable,str(ROOT/'module-3/runtime/askpass.py'),"Password for 'https://x-access-token@github.com.evil.invalid': "],capture_output=True,text=True)
        self.assertNotEqual(result.returncode,0);self.assertEqual(result.stdout,'')


class ManifestGuards(unittest.TestCase):
    def setUp(self): self.items=module3.objects()
    def change(self,kind,name,mutate):
        items=copy.deepcopy(self.items);item=next(o for o in items if o['kind']==kind and o['metadata']['name']==name)
        mutate(item)
        with self.assertRaises(ValueError): module3.audit(items)
    def test_complete_contract_passes(self): self.assertEqual(module3.audit(self.items)['status'],'passed')
    def test_schemas_reproduce(self): self.assertEqual(len(module3.verify_bundle()['apis']),8)
    def test_task_cannot_mount_git_credentials_in_test(self):
        self.change('Task','vcloud-test',lambda o:o['spec']['volumes'].append({'name':'git','secret':{'secretName':'vcloud-git-write'}}))
    def test_step_cannot_become_privileged(self):
        self.change('Task','vcloud-build',lambda o:o['spec']['stepTemplate']['securityContext'].update(privileged=True))
    def test_source_cannot_be_interpolated_into_a_script(self):
        self.change('Task','vcloud-clone',lambda o:o['spec']['steps'][0].update(script='git clone $(params.revision)'))
    def test_image_latest_is_rejected(self):
        self.change('Task','vcloud-build',lambda o:o['spec']['steps'][0].update(image='registry.vcloud.example.com/vcloud/ci-tooling:latest'))
    def test_publish_requires_successful_build(self):
        self.change('Pipeline','vcloud-ci',lambda o:o['spec']['tasks'][-1].update(runAfter=['clone']))
    def test_webhook_secret_verification_cannot_be_removed(self):
        self.change('EventListener','vcloud-push',lambda o:o['spec']['triggers'][0]['interceptors'].pop(0))
    def test_non_main_push_filter_cannot_be_enabled(self):
        self.change('EventListener','vcloud-push',lambda o:o['spec']['triggers'][0]['interceptors'][1]['params'][0].update(value='true'))
    def test_listener_cannot_deploy_workloads(self):
        self.change('Role','vcloud-trigger',lambda o:o['rules'].append({'apiGroups':['apps'],'resources':['deployments'],'verbs':['patch']}))
    def test_task_run_cannot_receive_api_token(self):
        self.change('PipelineRun','vcloud-ci-manual-example',lambda o:o['spec']['taskRunTemplate']['podTemplate'].update(automountServiceAccountToken=True))
    def test_workspace_requires_explicit_csi(self):
        self.change('PipelineRun','vcloud-ci-manual-example',lambda o:o['spec']['workspaces'][0].update(emptyDir={}))
    def test_argo_cannot_prune_or_change_destination(self):
        self.change('Application','vcloud-delivery',lambda o:o['spec']['syncPolicy']['automated'].update(prune=True))
        self.change('Application','vcloud-delivery',lambda o:o['spec']['destination'].update(namespace='platform-services'))
    def test_network_cannot_expand_to_world(self):
        self.change('CiliumNetworkPolicy','vcloud-ci-build',lambda o:o['spec']['egress'].append({'toEntities':['world']}))
    def test_served_beta_trigger_api_is_explicitly_documented(self):
        versions=module3.verify_bundle()['apis']
        self.assertTrue(all(a['served'] and a['deprecated'] is False for a in versions))
    def test_interceptor_tls_and_metrics_ports_match_selected_release(self):
        expected=resources()
        monitor=expected['module-3/manifests/observability.yaml'][0]
        self.assertEqual(monitor['spec']['endpoints'][0]['port'],'http-metrics')
        policy=next(o for o in expected['module-3/manifests/network.yaml'] if o['metadata']['name']=='vcloud-ci-eventlistener')
        self.assertEqual(policy['spec']['egress'][1]['toPorts'][0]['ports'][0]['port'],'8443')
    def test_static_local_storage_cannot_provision_pipeline_workspaces(self):
        with self.assertRaises(ValueError): validate_storage({'provisioner':'kubernetes.io/no-provisioner','volumeBindingMode':'WaitForFirstConsumer'})
    def test_csi_workspace_binding_is_explicit(self):
        validate_storage({'provisioner':'rbd.csi.ceph.com','volumeBindingMode':'WaitForFirstConsumer'})
    def test_csi_immediate_binding_is_rejected(self):
        with self.assertRaises(ValueError): validate_storage({'provisioner':'rbd.csi.ceph.com','volumeBindingMode':'Immediate'})


class RealGitPromotion(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.repo=self.root/'repository';self.repo.mkdir()
        self.env=runner.git_env()
        self.git('init','--quiet','--initial-branch=main')
        self.git('config','user.name','Fixture');self.git('config','user.email','fixture@example.invalid')
        path=self.repo/runner.MANIFEST;path.parent.mkdir(parents=True)
        path.write_bytes((ROOT/runner.MANIFEST).read_bytes())
        (self.repo/'README.md').write_text('fixture\n')
        self.git('add','.');self.git('commit','--quiet','-m','Seed')
        self.commit=self.git('rev-parse','HEAD');self.git('branch',runner.BRANCH)
        self.remote=self.root/'remote.git'
        runner.run(['git','clone','--quiet','--bare',self.repo,self.remote],env=self.env)
        self.repo_patch=patch.object(runner,'REPO',str(self.remote));self.repo_patch.start()
        self.original_run=runner.run;self.commands=[]
        def real_command(command,cwd=None,env=None):
            self.commands.append([str(v) for v in command])
            if command[:2]==['python3','/opt/vcloud-ci/validate_workload.py']:
                return self.original_run([sys.executable,str(ROOT/'module-3/runtime/validate_workload.py'),command[2]])
            if command[0]=='kubeconform':
                command=[os.environ.get('KUBECONFORM','kubeconform'),'-strict','-schema-location',
                         str(ROOT/'module-2/schemas/{{.Group}}/{{.ResourceKind}}_{{.ResourceAPIVersion}}.json'),command[-1]]
            return self.original_run(command,cwd,env)
        self.run_patch=patch.object(runner,'run',side_effect=real_command);self.mock_run=self.run_patch.start()
    def tearDown(self):
        self.run_patch.stop();self.repo_patch.stop();self.temp.cleanup()
    def git(self,*args): return runner.run(['git','-C',self.repo,*args],env=self.env)
    def promote(self,name='run'):
        work=self.root/name;work.mkdir();result=work/'result'
        runner.publish(work,self.commit,DIGEST,result)
        return result.read_text()
    def test_real_commit_push_changes_only_image_and_source(self):
        commit=self.promote()
        data=json.loads(self.original_run(['git','--git-dir',self.remote,'show',runner.BRANCH+':'+runner.MANIFEST],env=self.env))
        self.assertEqual(data['spec']['template']['spec']['containers'][0]['image'],runner.image_reference(self.commit,DIGEST))
        self.assertEqual(self.original_run(['git','--git-dir',self.remote,'diff-tree','--no-commit-id','--name-only','-r',commit],env=self.env),runner.MANIFEST)
        self.assertFalse(any('--force' in command for command in self.commands))
    def test_real_replay_creates_no_extra_commit(self):
        first=self.promote('first');second=self.promote('second');self.assertEqual(first,second)
    def test_real_stale_main_rejects_before_remote_mutation(self):
        before=self.original_run(['git','--git-dir',self.remote,'rev-parse',runner.BRANCH],env=self.env)
        (self.repo/'README.md').write_text('main advanced\n');self.git('add','README.md');self.git('commit','--quiet','-m','Advance')
        self.git('push','--quiet',str(self.remote),'main')
        with self.assertRaisesRegex(ValueError,'Stale'): self.promote()
        after=self.original_run(['git','--git-dir',self.remote,'rev-parse',runner.BRANCH],env=self.env)
        self.assertEqual(before,after)
    def test_real_clone_checks_exact_commit(self):
        work=self.root/'checkout';work.mkdir();runner.clone(work,self.commit)
        self.assertEqual(self.original_run(['git','-C',work/'source','rev-parse','HEAD'],env=self.env),self.commit)
    def test_concurrent_remote_commit_is_preserved_after_retry(self):
        original_side_effect=self.mock_run.side_effect
        collided=False
        def collide(command,cwd=None,env=None):
            nonlocal collided
            if 'push' in command and '--porcelain' in command and not collided:
                collided=True
                other=self.root/'concurrent'
                self.original_run(['git','clone','--quiet','--branch',runner.BRANCH,self.remote,other],env=self.env)
                self.original_run(['git','-C',other,'config','user.name','Concurrent fixture'],env=self.env)
                self.original_run(['git','-C',other,'config','user.email','concurrent@example.invalid'],env=self.env)
                (other/'NOTES').write_text('Concurrent change survives\n')
                self.original_run(['git','-C',other,'add','NOTES'],env=self.env)
                self.original_run(['git','-C',other,'commit','--quiet','-m','Concurrent change'],env=self.env)
                self.original_run(['git','-C',other,'push','--quiet','origin',runner.BRANCH],env=self.env)
            return original_side_effect(command,cwd,env)
        self.mock_run.side_effect=collide
        self.promote()
        self.assertTrue(collided)
        self.assertEqual(self.original_run(['git','--git-dir',self.remote,'show',runner.BRANCH+':NOTES'],env=self.env),'Concurrent change survives')
    def test_build_uses_mtls_and_emits_verified_oci_digest(self):
        work=self.root/'build';work.mkdir();runner.clone(work,self.commit)
        captured=[]
        original_side_effect=self.mock_run.side_effect
        def build_command(command,cwd=None,env=None):
            if command[0]=='buildctl':
                captured.extend(command)
                (work/'build-metadata.json').write_text(json.dumps({'containerimage.digest':DIGEST}))
                return ''
            return original_side_effect(command,cwd,env)
        self.mock_run.side_effect=build_command
        output=work/'result';runner.build(work,self.commit,output)
        self.assertEqual(output.read_text(),DIGEST)
        self.assertIn('--tlskey',captured);self.assertIn('--tlscacert',captured);self.assertIn('--tlsservername',captured)
        self.assertIn('force-network-mode=none',captured)
        self.assertTrue(any('rewrite-timestamp=true' in value for value in captured))
    def test_build_never_consults_test_workspace_git_configuration(self):
        work=self.root/'dirty-test-workspace';work.mkdir();runner.clone(work,self.commit)
        (work/'source/.git/config').write_text('[core]\n    sshCommand = should-never-execute\n')
        original_side_effect=self.mock_run.side_effect
        def build_command(command,cwd=None,env=None):
            if command[0]=='buildctl':
                (work/'build-metadata.json').write_text(json.dumps({'containerimage.digest':DIGEST}))
                return ''
            return original_side_effect(command,cwd,env)
        self.commands.clear();self.mock_run.side_effect=build_command
        runner.build(work,self.commit,work/'result')
        self.assertFalse(any(str(work/'source') in command for command in self.commands))
        self.assertTrue((work/'build-context/source/README.md').is_file())
