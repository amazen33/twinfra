"""Fail-closed init behavior: no real OpenBao writes or operator private keys."""
import base64
import contextlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import openbao_pgp_init as init

# Structurally valid PKESK + integrity-protected encrypted packet fixtures;
# never production keys, passwords or root tokens.
CIPHER=base64.b64encode(bytes([0xc1,3,3,1,2,0xd2,3,1,5,6])).decode()


class InitTests(unittest.TestCase):
    def test_real_armored_public_key_normalization_and_encrypted_packets(self):
        # A disposable CI recipient lives exclusively in Linux tmpfs, never the
        # standard operator key paths. Kill only its own scoped GnuPG agent.
        with tempfile.TemporaryDirectory(dir='/dev/shm') as directory:
            home=Path(directory);key=home/'public.asc'
            command=['gpg','--batch','--no-tty','--homedir',str(home),'--pinentry-mode','loopback','--passphrase','']
            try:
                subprocess.run(command+['--quick-generate-key','vCloud CI fixture <fixture.invalid>','rsa2048','encr','1d'],check=True,capture_output=True)
                key.write_bytes(subprocess.check_output(command+['--armor','--export'],stderr=subprocess.DEVNULL))
                fingerprint,binary=init.public_key(key,home)
                self.assertTrue(base64.b64decode(binary));self.assertEqual(len(fingerprint),40)
                cipher=subprocess.run(command+['--trust-model','always','--encrypt','--recipient',fingerprint],
                    input=b'synthetic CI fragment',capture_output=True,check=True).stdout
                tags=init.packet_tags(base64.b64encode(cipher).decode())
                self.assertEqual(tags[0],1)
                # GnuPG selects integrity-protected (18) or AEAD (20) packets
                # by version/preferences. Both must remain encrypted streams.
                self.assertTrue(set(tags)&{18,20})
                key.write_bytes(subprocess.check_output(command+['--armor','--export-secret-keys'],stderr=subprocess.DEVNULL))
                with self.assertRaises(ValueError):init.public_key(key,home)
            finally:
                subprocess.run(['gpgconf','--homedir',str(home),'--kill','gpg-agent'],capture_output=True,check=False)

    def test_initialized_skips_keys_and_post_and_secret(self):
        api=unittest.mock.Mock(return_value={'initialized':True});run=unittest.mock.Mock()
        self.assertEqual(init.initialize(keys=[],api=api,run=run),0)
        api.assert_called_once_with('GET');run.assert_not_called()

    def test_missing_keys_exact_error_and_no_writes(self):
        api=unittest.mock.Mock(return_value={'initialized':False});run=unittest.mock.Mock()
        with contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(init.initialize(keys=[Path('/does-not-exist')]*4,api=api,run=run),3)
        self.assertEqual(output.getvalue().strip(),'ERROR: Initialization gated: Missing required PGP public key files.')
        api.assert_called_once_with('GET');run.assert_not_called()

    def test_unknown_status_does_not_initialize(self):
        api=unittest.mock.Mock(return_value={'initialized':'false'})
        with self.assertRaises(ValueError):init.initialize(api=api)
        api.assert_called_once_with('GET')

    def test_ciphertext_rejects_plaintext_and_malformed_packets(self):
        for value in ('hvs.plaintext-token',base64.b64encode(b'plaintext').decode(),base64.b64encode(bytes([0xc1,255])).decode()):
            with self.subTest(value=value),self.assertRaises((ValueError,IndexError)):init.packet_tags(value)
        self.assertEqual(init.packet_tags(CIPHER),[1,18])

    def test_duplicate_operator_keys_abort_before_post(self):
        with tempfile.TemporaryDirectory() as directory:
            keys=[Path(directory)/str(i) for i in range(4)]
            for p in keys:p.write_text('PUBLIC-TEST-FIXTURE')
            api=unittest.mock.Mock(return_value={'initialized':False})
            with patch.object(init,'public_key',return_value=('same-fingerprint','binary-b64')):
                with self.assertRaises(ValueError):init.initialize(keys=keys,api=api)
            api.assert_called_once_with('GET')

    def test_validated_payload_and_ciphertext_only_secret(self):
        with tempfile.TemporaryDirectory() as directory:
            keys=[Path(directory)/str(i) for i in range(4)]
            for p in keys:p.write_text('PUBLIC-TEST-FIXTURE')
            api=unittest.mock.Mock(side_effect=[{'initialized':False},
                {'keys_base64':[CIPHER]*3,'root_token':CIPHER,'secret_shares':3,'secret_threshold':2}])
            captured=[]
            def run(command,**kwargs):
                captured.append((command,kwargs))
                return subprocess.CompletedProcess(command,0,b'yes\n' if 'can-i' in command else b'',b'')
            with patch.object(init,'public_key',side_effect=[(str(i),f'key{i}') for i in range(4)]):
                self.assertEqual(init.initialize(keys=keys,api=api,run=run),0)
            self.assertEqual(api.call_args_list[1].args,('POST',{'secret_shares':3,'secret_threshold':2,
                'pgp_keys':['key0','key1','key2'],'root_token_pgp_key':'key3'}))
            secret=json.loads(captured[-1][1]['input'])
            payload=json.loads(base64.b64decode(secret['data']['init.json']))
            self.assertEqual(secret['metadata']['name'],'openbao-init-encrypted');self.assertTrue(secret['immutable'])
            self.assertEqual(payload['keys_base64'],[CIPHER]*3)
            self.assertNotIn('keys',payload)

    def test_existing_secret_refuses_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            keys=[Path(directory)/str(i) for i in range(4)]
            for p in keys:p.write_text('PUBLIC-TEST-FIXTURE')
            api=unittest.mock.Mock(return_value={'initialized':False})
            def run(command,**kwargs):
                return subprocess.CompletedProcess(command,0,b'yes\n' if 'can-i' in command else b'secret/openbao-init-encrypted',b'')
            with patch.object(init,'public_key',side_effect=[(str(i),f'key{i}') for i in range(4)]):
                with self.assertRaises(ValueError):init.initialize(keys=keys,api=api,run=run)
            api.assert_called_once_with('GET')

    def test_standard_paths_and_loopback_endpoint(self):
        self.assertEqual([str(k) for k in init.KEYS],['/etc/openbao/keys/'+n for n in ['operator1.asc','operator2.asc','operator3.asc','root-secops.asc']])
        self.assertEqual(init.URL,'http://127.0.0.1:8200/v1/sys/init')

    def test_encryption_gate_failure_never_posts(self):
        with tempfile.TemporaryDirectory() as directory:
            keys=[Path(directory)/str(i) for i in range(4)]
            for p in keys:p.write_text('PUBLIC-TEST-FIXTURE')
            api=unittest.mock.Mock(return_value={'initialized':False})
            run=unittest.mock.Mock(return_value=subprocess.CompletedProcess([],1,b'',b''))
            with patch.object(init,'public_key',side_effect=[(str(i),f'key{i}') for i in range(4)]):
                with self.assertRaises(ValueError):init.initialize(keys=keys,api=api,run=run)
            api.assert_called_once_with('GET')

    def test_uncertain_secret_create_verifies_custody_without_second_post(self):
        with tempfile.TemporaryDirectory() as directory:
            keys=[Path(directory)/str(i) for i in range(4)]
            for p in keys:p.write_text('PUBLIC-TEST-FIXTURE')
            api=unittest.mock.Mock(side_effect=[{'initialized':False},
                {'keys_base64':[CIPHER]*3,'root_token':CIPHER,'secret_shares':3,'secret_threshold':2}])
            stored=None;created=0
            def run(command,**kwargs):
                nonlocal stored,created
                if 'create' in command and '-f' in command:
                    stored=json.loads(kwargs['input']);created+=1
                    return subprocess.CompletedProcess(command,1,b'',b'')
                if command[-1]=='json':return subprocess.CompletedProcess(command,0,json.dumps(stored).encode(),b'')
                return subprocess.CompletedProcess(command,0,b'yes\n' if 'can-i' in command else b'',b'')
            with patch.object(init,'public_key',side_effect=[(str(i),f'key{i}') for i in range(4)]):
                self.assertEqual(init.initialize(keys=keys,api=api,run=run),0)
            self.assertEqual(created,1);self.assertEqual(api.call_count,2)

    def test_valid_key_check_only_never_initializes_or_creates_secret(self):
        with tempfile.TemporaryDirectory() as directory:
            keys=[Path(directory)/str(i) for i in range(4)]
            for p in keys:p.write_text('PUBLIC-TEST-FIXTURE')
            api=unittest.mock.Mock(return_value={'initialized':False})
            def run(command,**kwargs):
                self.assertNotIn('-f',command)
                return subprocess.CompletedProcess(command,0,b'yes\n' if 'can-i' in command else b'',b'')
            with patch.object(init,'public_key',side_effect=[(str(i),f'key{i}') for i in range(4)]):
                self.assertEqual(init.initialize(keys=keys,api=api,run=run,check_only=True),0)
            api.assert_called_once_with('GET')


if __name__=='__main__':unittest.main()
