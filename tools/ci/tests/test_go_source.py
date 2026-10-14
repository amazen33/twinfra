"""Offline source triage contracts: no application build or network."""
import io
import json
from pathlib import Path
import sys
import tarfile
import tempfile
import unittest

sys.path[:0] = [str(Path(__file__).resolve().parents[1]), str(Path(__file__).resolve().parents[2])]
import triage_go_source as source
import compare_go_candidates as compare


class SourceMode(unittest.TestCase):
    def test_inline_build_info_uses_binary_version_and_strips_sentinels(self):
        def string(raw):
            self.assertLess(len(raw), 128)
            return bytes([len(raw)]) + raw
        header = b'\xff Go buildinf:' + bytes([8, 2]) + b'\x00' * 16
        raw = header + string(b'go1.26.9') + string(b'x' * 16 + b'dep\tx/net\tv0.59.0\n' + b'y' * 16)
        self.assertEqual(source.build_info(raw), ('go1.26.9', 'dep\tx/net\tv0.59.0\n'))
        with self.assertRaises(ValueError):
            source.build_info(raw[:-20])
        with self.assertRaises(ValueError):
            source.build_info(b'no build info')

    def test_trace_is_retained_and_module_only_is_not_reachable(self):
        config = {'config': {'scan_mode': 'source'}}
        trace = [dict(module='golang.org/x/net', version='v0.59.0', package='golang.org/x/net/http2', function='ReadFrame'),
                 dict(package='application', function='main', position={'filename': 'main.go', 'line': 10})]
        raw = json.dumps(config) + json.dumps({'finding': {'osv': source.TARGET, 'trace': trace}})
        self.assertEqual(source.findings(raw)[1][0]['callStack'], trace)
        self.assertTrue(source.findings(raw)[1][0]['reachable'])
        raw = json.dumps(config) + json.dumps({'finding': {'osv': source.TARGET, 'trace': [dict(module='stdlib')]}})
        self.assertFalse(source.findings(raw)[1][0]['reachable'])

    def test_missing_config_wrong_mode_and_missing_trace_are_errors(self):
        for raw in ('', '{', json.dumps({'config': {'scan_mode': 'binary'}}),
                    json.dumps({'finding': {'osv': source.TARGET}})):
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                source.findings(raw)

    def test_source_archive_escape_is_refused(self):
        data = io.BytesIO()
        with tarfile.open(fileobj=data, mode='w') as archive:
            item = tarfile.TarInfo('../outside'); item.size = 1
            archive.addfile(item, io.BytesIO(b'x'))
        with tempfile.TemporaryDirectory() as directory, self.assertRaises(ValueError):
            source.extract_source(data.getvalue(), Path(directory))

    def test_source_mode_never_builds_or_executes_an_application(self):
        text = Path(source.__file__).read_text()
        self.assertNotIn("'build'", text)
        self.assertNotIn("'install'", text)
        self.assertIn("'-mode=source'", text)
        self.assertIn('GOTOOLCHAIN=version', text)
        self.assertIn("GOFLAGS='-mod=readonly'", text)
        self.assertIn("GOSUMDB='sum.golang.org'", text)

    def test_net_improvement_refuses_new_or_worsened_high_and_critical(self):
        before = [dict(package='x/net', vulnerability='GO-one', severity='Critical'),
                  dict(package='openssl', vulnerability='CVE-two', severity='High')]
        self.assertTrue(compare.improvement(before, before[:1])['netImprovement'])
        self.assertFalse(compare.improvement(before, before)['netImprovement'])
        after = before[:1] + [dict(package='new', vulnerability='CVE-new', severity='High')]
        self.assertFalse(compare.improvement(before, after)['noNewCriticalHigh'])
        worse = [before[1] | {'severity': 'Critical'}]
        self.assertFalse(compare.improvement(before, worse)['netImprovement'])


if __name__ == '__main__':
    unittest.main()
