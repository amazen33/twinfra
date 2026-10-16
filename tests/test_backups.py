"""WO-09 offline safety, freshness, namespace and restore invariants."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import zipfile
from unittest.mock import patch
import yaml

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
import platform_backups as backup
import platform_backup_actions as actions
import platform_dev as dev
import platform_backup_image as builder
import platform_backup_secret as secret_helper
from manifest_contract import audit_objects, podspec


def module(name,file):
    spec=importlib.util.spec_from_file_location(name,ROOT/file);value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value)
    return value


upload=module('backup_upload','deploy/common/backup/upload.py')
storage=module('restore_storage','deploy/common/backup/restore-storage.py')
NOW=datetime(2026,10,16,12,tzinfo=timezone.utc)


class BackupManifests(unittest.TestCase):
    def test_default_is_gated_and_existing_platform_stays_byte_identical(self):
        self.assertFalse(backup.config()['enabled'])
        for name in ('platform/workloads.yaml','services/workloads.yaml','root.yaml','apps/applications.yaml'):
            path='deploy/environments/dev/cairo-1/'+name
            before=subprocess.check_output(['git','-C',str(ROOT),'show','09d56f3:'+path])
            self.assertEqual((ROOT/path).read_bytes().replace(b'\r\n',b'\n'),before,path)

    def test_enabled_platform_has_daily_backup_retention_and_wal(self):
        site=backup.config()|{'enabled':True}
        with patch.object(backup,'config',return_value=site):
            documents=list(yaml.safe_load_all(dev.outputs()[dev.TARGET/'platform/workloads.yaml']))
            cluster=next(v for v in documents if v['kind']=='Cluster')
            self.assertEqual(cluster['spec']['postgresql']['parameters']['archive_timeout'],'300s')
            self.assertTrue(cluster['spec']['plugins'][0]['isWALArchiver'])
            store=next(v for v in documents if v['kind']=='ObjectStore')
            self.assertEqual(store['spec']['retentionPolicy'],'7d')
            self.assertEqual(store['spec']['configuration']['wal']['compression'],'gzip')
            self.assertEqual(store['spec']['configuration']['endpointURL'],site['endpointURL'])
            self.assertNotIn('ACCESS_SECRET_KEY',json.dumps(store['spec']).replace('"key": "ACCESS_SECRET_KEY"',''))
            schedule=next(v for v in documents if v['kind']=='ScheduledBackup')
            self.assertEqual(schedule['spec']['schedule'],'0 0 2 * * *')
            self.assertEqual(schedule['spec']['method'],'plugin')

    def test_only_exact_node_mounts_and_two_justified_root_init_containers(self):
        job=next(v for v in backup.node_objects() if v['kind']=='CronJob');pod=podspec(job)
        self.assertTrue(job['spec']['suspend']);self.assertEqual(job['spec']['schedule'],'0 */6 * * *')
        self.assertFalse(pod['automountServiceAccountToken'])
        self.assertEqual(pod['nodeSelector'],{'kubernetes.io/hostname':'twinfra-dev-cairo-1'})
        paths={v['name']:v['hostPath'] for v in pod['volumes'] if 'hostPath' in v}
        self.assertEqual({v['path'] for v in paths.values()},
            {'/etc/kubernetes/pki/etcd/'+v for v in ('ca.crt','healthcheck-client.crt','healthcheck-client.key')})
        roots=[]
        for c in pod['initContainers']+pod['containers']:
            self.assertEqual(c['imagePullPolicy'],'IfNotPresent');self.assertIn('@sha256:',c['image'])
            self.assertEqual(c['securityContext']['capabilities'],{'drop':['ALL']})
            self.assertFalse(c['securityContext']['allowPrivilegeEscalation'])
            host_mounts=[v for v in c['volumeMounts'] if v['name'] in paths]
            if c['name']=='snapshot':self.assertTrue(all(v['readOnly'] for v in host_mounts));self.assertEqual(len(host_mounts),3)
            else:self.assertFalse(host_mounts)
            if c['securityContext']['runAsUser']==0:roots.append(c['name'])
            if c['name']!='encrypt-upload':self.assertNotIn('api-token',[v['name'] for v in c['volumeMounts']])
        self.assertEqual(roots,['snapshot','snapshot-permissions'])
        self.assertFalse(any(pod.get(v,False) for v in ('hostNetwork','hostPID','hostIPC')))
        scratch=next(v for v in pod['volumes'] if v['name']=='snapshot')
        self.assertEqual(scratch['emptyDir'],{'medium':'Memory','sizeLimit':'512Mi'})

    def test_node_exception_rejects_mount_image_command_or_security_drift(self):
        job=next(v for v in backup.node_objects() if v['kind']=='CronJob');policy=backup.node_exception()
        self.assertEqual(audit_objects([job],policy)['violations'],[])
        for mutation in ('path','image','command','root','write'):
            value=deepcopy(job);pod=podspec(value)
            if mutation=='path':pod['volumes'][0]['hostPath']['path']='/etc/kubernetes/pki/etcd/ca.key'
            if mutation=='image':pod['initContainers'][0]['image']=dev.image('python')
            if mutation=='command':pod['initContainers'][0]['command'].append('unapproved')
            if mutation=='root':pod['containers'][0]['securityContext']['runAsUser']=0
            if mutation=='write':pod['initContainers'][0]['volumeMounts'][1]['readOnly']=False
            with self.subTest(mutation=mutation):self.assertTrue(audit_objects([value],policy)['violations'])

    def test_no_host_go_tools_or_pyrage_selected(self):
        lock=json.loads((dev.COMMON/'backup-artifacts.lock.json').read_text())
        self.assertNotIn('tools',lock)
        requirements=(dev.COMMON/'backup/requirements.txt').read_text()
        self.assertNotIn('pyrage',requirements)
        self.assertFalse(list((dev.COMMON/'backup').glob('*.service')))
        self.assertFalse(list((dev.COMMON/'backup').glob('*.timer')))

    def test_registry_pins_and_role_scope(self):
        role=next(v for v in backup.backup_objects() if v['kind']=='Role' and v['metadata']['name']=='twinfra-backup-secret-reader')
        self.assertEqual(role['rules'][0]['resourceNames'],['twinfra-backup-s3'])
        self.assertEqual(role['rules'][0]['verbs'],['get'])
        for v in backup.plugin_objects():
            if v['kind']=='Service':self.assertEqual(v['spec'].get('type','ClusterIP'),'ClusterIP')
            if v['kind']=='Deployment':self.assertEqual(v['spec']['strategy']['rollingUpdate'],{'maxUnavailable':0,'maxSurge':1})


class Freshness(unittest.TestCase):
    def test_healthy_ages_and_metrics_contract(self):
        # Public API accepts ISO timestamps, not datetime objects.
        report=actions.assess((NOW-timedelta(hours=1)).isoformat(),NOW.timestamp()-10,(NOW-timedelta(hours=1)).isoformat(),NOW)
        self.assertEqual(report['status'],'passed')
        self.assertIn('kind="wal"',actions.prometheus(report))
        self.assertFalse(report['restoreRpoRtoMeasured'])

    def test_warn_fail_missing_future_and_nonfinite(self):
        for value,status in ((NOW.timestamp()-599,'PASS'),(NOW.timestamp()-600,'WARN'),
                             (NOW.timestamp()-900,'FAIL'),(None,'FAIL'),(float('nan'),'FAIL'),(NOW.timestamp()+1,'FAIL')):
            with self.subTest(value=value):self.assertEqual(actions.freshness(value,NOW,600,900)['status'],status)

    def test_daily_base_and_six_hour_etcd_thresholds(self):
        report=actions.assess(NOW.timestamp()-87300,NOW.timestamp()-1,NOW.timestamp()-21600,NOW)
        self.assertEqual(report['backups']['base']['status'],'FAIL')
        self.assertEqual(report['backups']['etcd']['status'],'FAIL')

    def test_restore_is_separate_namespace_and_never_archives_over_source(self):
        objects=actions.restore_manifest('2026-10-15T12:00:00Z')
        cluster=next(v for v in objects if v['kind']=='Cluster')
        self.assertEqual(cluster['metadata']['namespace'],'twinfra-restore-drill')
        self.assertNotIn('plugins',cluster['spec'])
        self.assertEqual(cluster['spec']['bootstrap']['recovery']['recoveryTarget']['targetTime'],'2026-10-15T12:00:00+00:00')
        pv=next(v for v in objects if v['kind']=='PersistentVolume')
        self.assertEqual(pv['spec']['local']['path'],'/var/lib/twinfra/local-pv/restore-drill')
        store=next(v for v in objects if v['kind']=='ObjectStore');self.assertNotIn('retentionPolicy',store['spec'])


class CMS(unittest.TestCase):
    def perform_fixture(self, fail_upload=False):
        with tempfile.TemporaryDirectory() as directory:
            directory=Path(directory);plain=directory/'snapshot.db';plain.write_bytes(b'synthetic fixture')
            events=[]
            def encrypt(source,cert,dest):dest.write_bytes(b'CMS fixture');events.append('encrypt');return 'AES-256-GCM'
            def upload_file(*args):
                self.assertFalse(plain.exists());events.append('verified-upload')
                if fail_upload:raise ValueError('Round trip failed')
                return 'etcd/fixture.cms'
            with (patch.object(upload,'credentials',return_value={}),
                  patch.object(upload,'public_certificate'),patch.object(upload,'encrypt',side_effect=encrypt),
                  patch.object(upload,'s3_client'),patch.object(upload,'upload',side_effect=upload_file),
                  patch.object(upload,'retain',side_effect=lambda *_:events.append('retention')),
                  patch.object(upload,'api',side_effect=lambda *_:events.append('status')),
                  patch.object(upload,'checked',return_value=b'OpenSSL fixture')):
                if fail_upload:
                    with self.assertRaises(ValueError):upload.perform(backup.config(),directory)
                else:self.assertEqual(upload.perform(backup.config(),directory)['status'],'passed')
            return events

    def test_plaintext_removed_before_upload_and_status_after_roundtrip(self):
        self.assertEqual(self.perform_fixture(),['encrypt','verified-upload','retention','status'])

    def test_failed_upload_cannot_advance_success_or_delete_retained_backups(self):
        self.assertEqual(self.perform_fixture(True),['encrypt','verified-upload'])

    def test_gcm_success_and_specific_unsupported_fallback(self):
        for code,stderr,mode in ((0,b'','AES-256-GCM'),(1,b'unsupported cipher','AES-256-CBC')):
            with patch.object(upload.subprocess,'run',return_value=subprocess.CompletedProcess([],code,b'',stderr)):
                self.assertEqual(upload.encryption_mode(Path('public.pem')),mode)
        with patch.object(upload.subprocess,'run',return_value=subprocess.CompletedProcess([],1,b'',b'bad certificate')):
            with self.assertRaises(ValueError):upload.encryption_mode(Path('public.pem'))

    def test_private_key_is_rejected_as_recipient(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'recipient.pem';path.write_bytes(b'-----BEGIN PRIVATE KEY-----')
            with self.assertRaises(ValueError):upload.public_certificate(path)

    def test_remote_round_trip_detects_corruption(self):
        class Client:
            def get_object(self,**_):return {'Body':io.BytesIO(b'corrupt')}
        with self.assertRaisesRegex(ValueError,'checksum'):upload.verify_object(Client(),'fixture-bucket','fixture-key','0'*64)

    def test_retention_never_deletes_postgres_or_unowned_objects(self):
        deleted=[];old=NOW-timedelta(days=8);prefix=backup.config()['etcdPrefix']+'/'
        class Paginator:
            def paginate(self,**_):return [{'Contents':[{'Key':key,'LastModified':old} for key in (
                prefix+'snapshot-20261001T000000Z.db.cms',prefix+'snapshot-20261001T000000Z.db.cms.manifest.json',
                prefix+'unowned.db.cms','postgres/twinfra-postgres/important')]}]
        class Client:
            def get_paginator(self,_):return Paginator()
            def delete_object(self,**kw):deleted.append(kw['Key'])
        upload.retain(Client(),backup.config(),NOW)
        self.assertEqual(len(deleted),2);self.assertTrue(all(v.startswith(prefix+'snapshot-') for v in deleted))

    def test_errors_never_print_sdk_or_openssl_secret_text(self):
        with (patch.object(upload,'configuration',side_effect=ValueError('fixture-private-value')),
              patch('sys.stdout',new_callable=io.StringIO) as output):
            self.assertEqual(upload.main(),1);self.assertNotIn('fixture-private-value',output.getvalue())


class RestoreStorage(unittest.TestCase):
    def state(self):return {'lv':None,'receipt':None,'free':100*1024**3,'mounts':[]}

    def test_plan_preserves_pg_and_free_reserve(self):
        report=storage.validate(self.state(),'plan')
        self.assertEqual(report['device'],'/dev/ubuntu-vg/twinfra-restore-drill')
        self.assertNotEqual(report['device'],'/dev/ubuntu-vg/twinfra-postgres-1')
        state=self.state();state['free']=39*1024**3
        with self.assertRaises(ValueError):storage.validate(state,'apply')

    def test_existing_unowned_or_changed_lv_refused(self):
        state=self.state();state['lv']={'lv_uuid':'id','lv_size':str(storage.SIZE),'lv_tags':'foreign'}
        with self.assertRaises(ValueError):storage.validate(state,'apply')
        state['receipt']={'nonce':'a'*32,'lvUuid':'id'};state['lv']['lv_tags']='twinfra-restore-'+'a'*32
        storage.validate(state,'apply')
        state['lv']['lv_uuid']='different'
        with self.assertRaises(ValueError):storage.validate(state,'remove')

    def test_namespace_or_pv_presence_blocks_remove(self):
        with patch.object(storage,'command',return_value='{"metadata":{"name":"still-present"}}') as command:
            with self.assertRaises(ValueError):storage.remove(self.state())
            self.assertFalse(any(c.args[0][0]=='lvremove' for c in command.call_args_list))

    def test_foreign_mountpoint_refused(self):
        state=self.state();state['mounts']=[{'source':'/dev/foreign','target':str(storage.MOUNT)}]
        with self.assertRaisesRegex(ValueError,'Foreign filesystem'):storage.validate(state,'apply')

    def test_filesystem_uuid_change_refuses_deletion(self):
        state=self.state();state['receipt']={'filesystemUuid':'owned-fs'}
        with patch.object(storage,'command',side_effect=['','','foreign-fs']) as command:
            with self.assertRaisesRegex(ValueError,'identity changed'):storage.remove(state)
            self.assertFalse(any(c.args[0][0]=='lvremove' for c in command.call_args_list))


class InputsAndSecrets(unittest.TestCase):
    def test_wheel_hash_and_member_boundary(self):
        import hashlib
        for member,allowed in [('boto3/__init__.py',True),('../escape.py',False),('absolute.pth',False),('/absolute.py',False)]:
            with self.subTest(member=member),tempfile.TemporaryDirectory() as directory:
                directory=Path(directory);path=directory/'fixture-py3-none-any.whl'
                with zipfile.ZipFile(path,'w') as archive:archive.writestr(member,'# synthetic fixture')
                lock={'wheels':[{'filename':path.name,'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}]}
                if allowed:self.assertIn('app/vendor/'+member,builder.wheels_payload(directory,lock))
                else:
                    with self.assertRaises(ValueError):builder.wheels_payload(directory,lock)
                lock['wheels'][0]['sha256']='0'*64
                with self.assertRaises(ValueError):builder.wheels_payload(directory,lock)

    def test_restore_secret_copies_only_two_fields_by_stdin(self):
        secret={'data':{'ACCESS_KEY_ID':'cHVibGljLWZpeHR1cmU=','ACCESS_SECRET_KEY':'cHVibGljLWZpeHR1cmU=',
                        'CMS_CERTIFICATE':'cHVibGlj','unrelated':'cHVibGlj'}}
        with patch.object(secret_helper,'kubectl',side_effect=[json.dumps(secret).encode(),b'']) as cli:
            secret_helper.copy_restore()
        value=json.loads(cli.call_args_list[1].args[1])
        self.assertEqual(set(value['data']),{'ACCESS_KEY_ID','ACCESS_SECRET_KEY'})
        self.assertEqual(value['metadata']['namespace'],'twinfra-restore-drill')

    def test_historical_receipt_projection_preserves_every_old_pin_and_approval(self):
        from wo09_receipts import images,policy
        self.assertEqual(json.loads(images()),json.loads(subprocess.check_output(['git','show','09d56f3:deploy/common/images.lock.json'])))
        self.assertEqual(json.loads(policy()),json.loads(subprocess.check_output(['git','show','09d56f3:security/licence-policy.json'])))


if __name__=='__main__':unittest.main()
