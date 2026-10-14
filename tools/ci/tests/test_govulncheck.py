"""Offline Go tool bootstrap fixtures; no compiler, download or scanner executes."""
import hashlib
import io
import json
from pathlib import Path
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import stage_govulncheck as stage
import licence_inventory as inventory
import registry_export


class GovulncheckBuild(unittest.TestCase):
    def sdk(self, name='go/bin/go', content=b'fixture'):
        buffer = io.BytesIO()
        with tarfile.open(fileobj=buffer, mode='w') as archive:
            for path, raw in ((name, content), ('go/VERSION', b'go1.27.1\n')):
                item = tarfile.TarInfo(path); item.size = len(raw); item.mode = 0o755
                archive.addfile(item, io.BytesIO(raw))
        return buffer.getvalue()

    def test_checksum_and_archive_escape_refuse(self):
        with self.assertRaisesRegex(ValueError, 'checksum'):
            stage.verified(b'data', 'a' * 64)
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError, 'archive path'):
                stage.extract_sdk(self.sdk('../escape'), Path(directory), False)
            self.assertFalse((Path(directory).parent / 'escape').exists())

    def test_symlink_refused(self):
        buffer = io.BytesIO()
        with tarfile.open(fileobj=buffer, mode='w') as archive:
            item = tarfile.TarInfo('go/bin/go'); item.type = tarfile.SYMTYPE; item.linkname = '/bin/sh'
            archive.addfile(item)
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError, 'regular files'):
                stage.extract_sdk(buffer.getvalue(), Path(directory), False)

    def test_discovery_does_not_execute_scanner_and_validation_requires_pin(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); (root / 'tools/ci').mkdir(parents=True)
            sdk = self.sdk(); binary = b'fixture compiled ELF'
            value = {'module': 'golang.org/x/vuln/cmd/govulncheck', 'version': 'v1.1.4',
                     'goVersion': 'go1.27.1', 'binarySHA256': None, 'inputs': [],
                     'sdks': {'linux-amd64': {'url': 'https://go.dev/dl/fixture',
                                              'sha256': hashlib.sha256(sdk).hexdigest()}}}
            lock = root / 'tools/ci/toolchain.lock.json'
            lock.write_text(json.dumps({'builds': {'govulncheck': value}}))
            def compile_only(command, **kwargs):
                self.assertEqual(command[1], 'install')
                self.assertEqual(command[-1], 'golang.org/x/vuln/cmd/govulncheck@v1.1.4')
                env = kwargs['env']; self.assertEqual(env['GOTOOLCHAIN'], 'local')
                self.assertEqual(env['GOSUMDB'], 'off'); self.assertTrue(env['GOPROXY'].startswith('file:'))
                target = Path(env['GOPATH']) / 'bin/govulncheck'
                target.parent.mkdir(parents=True); target.write_bytes(binary)
            with patch.object(stage.platform, 'system', return_value='Linux'), \
                 patch.object(stage.platform, 'machine', return_value='x86_64'), \
                 patch.object(stage, 'download', return_value=sdk), \
                 patch.object(stage.subprocess, 'run', side_effect=compile_only) as run:
                with self.assertRaisesRegex(ValueError, 'before analysis'):
                    stage.stage(root / 'output', False, root)
                self.assertEqual(run.call_count, 0)
                result = stage.stage(root / 'output', True, root)
                self.assertFalse(result['scannerExecuted']); self.assertTrue(result['discoveryOnly'])
                self.assertEqual(result['binarySHA256'], hashlib.sha256(binary).hexdigest())
                self.assertEqual(run.call_count, 1)

    def test_go_source_identities_are_explicit(self):
        self.assertEqual(inventory.source_identity('https://proxy.golang.org/golang.org/x/vuln/@v/v1.1.4.zip'),
                         ('golang.org/x/vuln', 'v1.1.4', 'golang/vuln'))
        self.assertEqual(inventory.source_identity('https://go.dev/dl/go1.27.1.linux-amd64.tar.gz'),
                         ('golang/go', 'go1.27.1', 'golang/go'))

    def test_registry_authority_and_path_are_validated_before_network(self):
        digest='sha256:'+'a'*64
        with patch.object(registry_export.urllib.request,'urlopen',side_effect=AssertionError('Network called')):
            for value in ('https://evil.example/docker.io/library/python@'+digest,
                          'docker.io.evil.example/library/python@'+digest,
                          'x/docker.io/library/python@'+digest,
                          'quay.io/a/../b@'+digest,'quay.io/a//b@'+digest,
                          'quay.io/argoproj/argocd:latest'):
                with self.subTest(reference=value),self.assertRaises(ValueError):
                    registry_export.export_public(value,Path('unused'))


if __name__ == '__main__':
    unittest.main()
