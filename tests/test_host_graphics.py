"""WO-31 Amendment 15: offline root/SSH/initramfs fixtures only."""
from contextlib import nullcontext, redirect_stdout
import copy
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch, MagicMock

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import platform_dev as dev
import platform_host as host


def load(name, file):
    spec = importlib.util.spec_from_file_location(name, ROOT / file)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


graphics = load('graphics_fixture', 'deploy/common/host-graphics.py')
agent = load('graphics_host_agent', 'deploy/common/host-admin.py')
DATA = host.expected()


class OwnedGraphics(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        for name, value in [('ROOT', self.root), ('secure', lambda p: None), ('kernel', lambda: '6.8.0-fixture'),
                            ('lock', nullcontext)]:
            mocked = patch.object(graphics, name, value); mocked.start(); self.addCleanup(mocked.stop)
        mocked = patch.object(graphics.shutil, 'which', lambda name: '/usr/sbin/' + name)
        mocked.start(); self.addCleanup(mocked.stop)
        self.calls = []
        self.included = False

    def fake_run(self, args):
        self.calls.append(args)
        if args[0] == 'update-initramfs':
            self.included = graphics.path(graphics.FILE).exists()
        if args[0] == 'lsinitramfs':
            return graphics.FILE.lstrip('/') + '\n' if self.included else ''
        if args[0] == 'unmkinitramfs':
            p = Path(args[-1]) / 'main' / graphics.FILE.lstrip('/')
            p.parent.mkdir(parents=True); p.write_bytes(graphics.BODY.encode())
        return ''

    def test_apply_backup_retry_rollback_only_named_file_and_running_kernel(self):
        self.assertEqual(graphics.FILE,'/etc/modprobe.d/twinfra-display-drivers.conf')
        self.assertEqual(graphics.BODY,'blacklist nouveau\noptions nouveau modeset=0\nblacklist nvidiafb\n')
        foreign = self.root / 'etc/modprobe.d/foreign.conf'; foreign.parent.mkdir(parents=True)
        foreign.write_text('options i915 example=1\n')
        with patch.object(graphics, 'run', self.fake_run):
            self.assertEqual(graphics.change('apply')['status'], 'reboot-required')
            receipt = graphics.path(graphics.STATE + '/ownership.json').read_bytes()
            self.assertIsNone(json.loads(receipt)['backup'])
            self.assertEqual(graphics.path(graphics.FILE).read_text(), graphics.BODY)
            self.assertEqual(graphics.change('apply')['status'], 'reboot-required')
            self.assertEqual(graphics.path(graphics.STATE + '/ownership.json').read_bytes(), receipt)
            self.assertEqual(graphics.change('rollback')['status'], 'reboot-required')
        self.assertFalse(graphics.path(graphics.FILE).exists())
        self.assertEqual(foreign.read_text(), 'options i915 example=1\n')
        self.assertTrue(all(c[0] in ('update-initramfs', 'lsinitramfs', 'unmkinitramfs') for c in self.calls))
        self.assertEqual([c for c in self.calls if c[0] == 'update-initramfs'],
                         [['update-initramfs', '-u', '-k', '6.8.0-fixture']] * 3)

    def test_foreign_file_and_owned_tampering_refused_before_any_write(self):
        p = graphics.path(graphics.FILE); p.parent.mkdir(parents=True); p.write_text('foreign\n')
        with patch.object(graphics, 'run', side_effect=AssertionError('command ran')):
            with self.assertRaisesRegex(ValueError, 'Unowned'): graphics.change('apply')
        self.assertFalse(graphics.path(graphics.STATE).exists())
        p.unlink()
        with patch.object(graphics, 'run', self.fake_run): graphics.change('apply')
        p.write_text('tampered\n')
        with self.assertRaisesRegex(ValueError, 'differs'): graphics.change('rollback')

    def test_unowned_rollback_missing_tool_and_invalid_backup_are_refused(self):
        with self.assertRaisesRegex(ValueError, 'No owned'): graphics.change('rollback')
        with patch.object(graphics.shutil, 'which', return_value=None):
            with self.assertRaisesRegex(ValueError, 'tool unavailable'): graphics.change('apply')
        graphics.write(graphics.STATE + '/ownership.json', b'{"owner":"foreign"}')
        with self.assertRaisesRegex(ValueError, 'ownership'): graphics.change('apply')

    def test_rebuild_failure_or_missing_wrong_initramfs_file_never_reports_success(self):
        for failure in ('update', 'missing', 'content'):
            def run(args):
                if args[0] == 'update-initramfs' and failure == 'update': raise ValueError('fixture')
                if args[0] == 'lsinitramfs' and failure == 'missing': return ''
                value = self.fake_run(args)
                if args[0] == 'unmkinitramfs' and failure == 'content':
                    (Path(args[-1]) / 'main' / graphics.FILE.lstrip('/')).write_text('wrong')
                return value
            with self.subTest(failure=failure), patch.object(graphics, 'run', run):
                with self.assertRaises(ValueError): graphics.change('apply')

    def test_rollback_requires_initramfs_absence_and_preserves_backup_on_failure(self):
        with patch.object(graphics,'run',self.fake_run): graphics.change('apply')
        receipt=graphics.path(graphics.STATE+'/ownership.json').read_bytes()
        with patch.object(graphics,'run',return_value=graphics.FILE.lstrip('/')+'\n'):
            with self.assertRaisesRegex(ValueError,'presence differs'):graphics.change('rollback')
        self.assertEqual(graphics.path(graphics.STATE+'/ownership.json').read_bytes(),receipt)
        with patch.object(graphics,'run',self.fake_run):
            self.assertEqual(graphics.change('rollback')['status'],'reboot-required')

    def test_check_is_read_only_reports_loaded_and_inclusion(self):
        with patch.object(graphics, 'run', self.fake_run): graphics.change('apply')
        before = {p: p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        with patch.object(graphics, 'run', self.fake_run), patch.object(graphics, 'loaded', return_value={'nouveau': True, 'nvidiafb': False}), \
             patch.object(graphics, 'kernel_health', return_value={'status':'PASS','detail':{'counts':{}}}), \
             patch.object(graphics, 'write', side_effect=AssertionError('check wrote')):
            value = graphics.check()
            self.assertTrue(value['blacklistCurrent']); self.assertTrue(value['initramfsContainsFile'])
            self.assertTrue(value['loaded']['nouveau']); self.assertEqual(value['status'], 'failed')
            checks = graphics.health_checks()
            self.assertEqual(checks[-1]['status'], 'WARN')
        self.assertEqual(before, {p: p.read_bytes() for p in self.root.rglob('*') if p.is_file()})

    def test_bootstrap_requires_flag_and_dev_profile(self):
        config = graphics.path('/etc/twinfra-host.env'); config.parent.mkdir(parents=True)
        for profile, flag, allowed in [('dev-cairo-1','true',True),('dev-cairo-2','true',True),
                                       ('production','true',False),('dev-cairo-1','false',False)]:
            config.write_text('PLATFORM_PROFILE='+profile+'\nDISABLE_NOUVEAU='+flag+'\n')
            with patch.object(graphics, 'change', return_value={'status':'reboot-required'}) as change:
                if allowed:self.assertEqual(graphics.bootstrap()['status'], 'reboot-required')
                else:
                    with self.assertRaises(ValueError):graphics.bootstrap()
                    change.assert_not_called()


class KernelHealth(unittest.TestCase):
    def rows(self, count, start=0, spacing=1):
        return [{'MESSAGE':'WARNING: CPU: 2 PID: 1 at PRIVATE-FIXTURE',
                 '__MONOTONIC_TIMESTAMP':str(start+i*spacing)} for i in range(count)]

    def test_counts_rolling_hour_not_calendar_bucket_or_stack_lines(self):
        rows = self.rows(100, start=3_599_000_000)
        self.assertEqual(graphics.count_kernel(rows, 4_000_000_000)['status'], 'WARN')
        rows += self.rows(1, start=3_601_000_000)
        self.assertEqual(graphics.count_kernel(rows, 4_000_000_000)['status'], 'BLOCK')
        self.assertEqual(graphics.count_kernel(self.rows(101, spacing=3_600_000_001), 400_000_000_000)['status'], 'WARN')
        rows += [{'MESSAGE':'drm_fb_helper_damage_work+0x...', '__MONOTONIC_TIMESTAMP':'3601000001'}]
        value = graphics.count_kernel(rows, 4_000_000_000)
        self.assertEqual(value['detail']['counts']['warningTraces'], 101)
        self.assertEqual(value['detail']['lastHourWarningTraces'], 101)
        self.assertNotIn('PRIVATE', json.dumps(value)); self.assertNotIn('drm', json.dumps(value))

    def test_blocking_events_bug_io_warning_and_benign_mce_startup(self):
        for text in ('mce: [Hardware Error]: CPU 1', 'Machine check exception',
                     'INFO: task kworker/2:0 blocked for more than 122 seconds.', 'Out of memory: Killed process 4'):
            with self.subTest(text=text):
                self.assertEqual(graphics.count_kernel([{'MESSAGE':text,'__MONOTONIC_TIMESTAMP':'1'}], 2)['status'],'BLOCK')
        value = graphics.count_kernel([{'MESSAGE':'BUG: fixture','__MONOTONIC_TIMESTAMP':'1'},
            {'MESSAGE':'Buffer I/O error on dev fixture','__MONOTONIC_TIMESTAMP':'2'}], 3)
        self.assertEqual(value['status'],'WARN'); self.assertEqual(value['detail']['counts']['bugTraces'],1)
        self.assertEqual(value['detail']['counts']['ioErrors'],1)
        self.assertEqual(graphics.count_kernel([{'MESSAGE':'mce: In-kernel MCE decoding enabled.', '__MONOTONIC_TIMESTAMP':'1'}],2)['status'],'PASS')

    def test_journal_unavailable_or_malformed_blocks_without_output(self):
        for result in (SimpleNamespace(returncode=2,stdout='PRIVATE'), SimpleNamespace(returncode=0,stdout='PRIVATE')):
            with patch.object(graphics.subprocess,'run',return_value=result):
                value=graphics.kernel_health()
                self.assertEqual(value['status'],'BLOCK'); self.assertNotIn('PRIVATE',json.dumps(value))
        result=SimpleNamespace(returncode=0,stdout=json.dumps(self.rows(1)[0]))
        with patch.object(graphics.subprocess,'run',return_value=result) as run:
            self.assertEqual(graphics.kernel_health()['status'],'WARN')
            self.assertIn('-k',run.call_args.args[0]); self.assertIn('-b',run.call_args.args[0])
        with patch.object(graphics.subprocess,'run',side_effect=[result,SimpleNamespace(returncode=1,stdout='',stderr='')]):
            self.assertEqual(graphics.kernel_health()['status'],'PASS')


class Integration(unittest.TestCase):
    def test_identity_refusal_and_kernel_block_does_not_prevent_graphics_repair(self):
        from test_bare_metal import fixture
        module=MagicMock(); module.change.return_value={'status':'reboot-required'}
        for state in (fixture(),fixture(True)|{'addresses':['192.168.1.4']}):
            with patch.object(agent,'inventory',return_value=state),patch.object(agent,'graphics_agent',return_value=module):
                with self.assertRaisesRegex(ValueError,'identity-verified'):agent.dispatch(DATA|{'action':'graphics-apply'})
        with patch.object(agent,'inventory',return_value=fixture(True)),patch.object(agent,'graphics_agent',return_value=module):
            self.assertEqual(agent.dispatch(DATA|{'action':'graphics-apply'})['status'],'reboot-required')
        state=fixture(True)|{'graphicsChecks':[{'name':'Kernel health','status':'BLOCK','detail':{'counts':{}}}]}
        self.assertEqual(agent.evaluate(state,DATA)['status'],'failed')

    def test_client_modes_exit20_and_in_memory_source(self):
        ssh=MagicMock(); ssh.run.return_value=b'{"status":"reboot-required"}'
        for flags, action in [({'check':True},'graphics-check'),({'apply':True},'graphics-apply'),({'rollback':True},'graphics-rollback')]:
            host.execute('host-graphics',ssh,**flags)
            command=ssh.run.call_args.args[0]
            self.assertEqual(json.loads(command[-1])['action'],action)
            self.assertIn(repr((ROOT/'deploy/common/host-graphics.py').read_text()).encode(),ssh.run.call_args.kwargs['payload'])
        for flags in ({},{'apply':True,'rollback':True}):
            with self.assertRaisesRegex(ValueError,'exactly one'):host.execute('host-graphics',None,**flags)
        with patch.object(host,'execute',return_value={'status':'reboot-required'}),patch.object(host,'SSH'),redirect_stdout(io.StringIO()):
            self.assertEqual(host.action('host-graphics','twinfra-dev-cairo-1','operator@192.168.1.3',apply=True),20)

    def test_bootstrap_finish_honors_flag_before_marking_complete(self):
        events=[]
        module=MagicMock()
        module.bootstrap.side_effect=lambda: events.append('graphics') or {'status':'reboot-required'}
        for flag in (False,True):
            events.clear();module.reset_mock()
            with patch.object(agent,'run',return_value=''),patch.object(agent,'read',return_value='DISABLE_NOUVEAU=true\n' if flag else ''), \
                 patch.object(agent,'write',side_effect=lambda *args:events.append('complete')),patch.object(agent,'graphics_agent',return_value=module):
                value=agent.bootstrap_complete(DATA|{'hashes':{}},{'status':'passed','message':'fixture'})
            self.assertEqual(value['status'],'reboot-required' if flag else 'passed')
            self.assertEqual(events,['graphics','complete'] if flag else ['complete'])

    def test_host_check_reports_kernel_blocks_and_blacklist_warning(self):
        from test_bare_metal import fixture
        module=SimpleNamespace(health_checks=lambda:[{'name':'Kernel health','status':'BLOCK','detail':{'counts':{'warningTraces':101}}}])
        with patch.object(agent,'inventory',return_value=fixture(True)),patch.object(agent,'graphics_agent',return_value=module), \
             patch.object(agent,'network_agent',return_value=SimpleNamespace(integrity=lambda:{'status':'PASS','detail':'fixture'})), \
             patch.object(agent,'network_warnings',return_value=[]):
            value=agent.dispatch(DATA|{'action':'check'})
        self.assertEqual(value['status'],'failed')
        self.assertEqual(next(c for c in value['checks'] if c['name']=='Kernel health')['detail']['counts']['warningTraces'],101)

    def test_dev_bootstrap_render_is_bounded_production_and_shared_script_unchanged(self):
        def old(name):return subprocess.check_output(['git','-C',str(ROOT),'show','3f62773:'+name]).decode()
        for name in ('00-setup-ubuntu-host.sh','host.env.example','user-data.yaml','user-data-remote.yaml'):
            self.assertEqual((ROOT/name).read_text(),old(name),name)
        outputs=dev.outputs()
        for name in ('deploy/environments/dev/cairo-1/host.env','deploy/environments/dev/cairo-2/seed/user-data'):
            raw=outputs[ROOT/name]
            if name.endswith('host.env'):
                self.assertEqual(raw.replace('DISABLE_NOUVEAU=true\n',''),old(name))
            else:
                staging=load('graphics_staging_guard','tools/ci/check_staging.py')
                self.assertEqual(staging.references(raw),staging.references(old(name)))
                from graphics_receipts import seed_before_graphics
                self.assertEqual(seed_before_graphics(yaml.safe_load(raw)),yaml.safe_load(old(name)))

    def test_older_receipt_projection_refuses_changed_graphics_files_or_command(self):
        from graphics_receipts import seed_before_graphics
        original=yaml.safe_load((ROOT/'deploy/environments/dev/cairo-2/seed/user-data').read_text(encoding='utf-8'))
        for target in (graphics.FILE,graphics.STATE+'/ownership.json','/usr/local/lib/twinfra/host-graphics.py'):
            data=copy.deepcopy(original)
            next(f for f in data['write_files'] if f['path']==target)['content']+='tampered'
            with self.subTest(target=target),self.assertRaises(AssertionError):seed_before_graphics(data)
        data=copy.deepcopy(original)
        data['runcmd'][-1]=['reboot']
        with self.assertRaises(AssertionError):seed_before_graphics(data)


if __name__=='__main__':unittest.main()
