"""WO-31 image-build fixtures only: public fake HTTP, no runtime or host access."""
from contextlib import ExitStack, contextmanager, redirect_stdout
import copy
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
import threading
import unittest
from unittest.mock import patch
import urllib.parse
import urllib.request
import zipfile

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
import platform_oci as oci
import platform_build_images as builds
import build_console_image as console
import platform_pg_image as pg
import platform_dev as dev
import vcloud_console as retained

BASELINE='3b6ec829105ebc1511b067d53c24d0766b701fb6'


def graph(layer=None,indexed=False):
    config=oci.encoded({'os':'linux','architecture':'amd64','config':{'Env':['FIXTURE=yes']},
                        'rootfs':{'type':'layers','diff_ids':[]},'history':[]})
    def desc(raw,kind):return dict(digest=oci.digest(raw),size=len(raw),mediaType=kind)
    cfg=desc(config,'application/vnd.oci.image.config.v1+json');blobs={cfg['digest']:config}
    layers=[]
    if layer is not None:
        d=desc(layer,'application/vnd.oci.image.layer.v1.tar');layers.append(d);blobs[d['digest']]=layer
    raw=oci.encoded(dict(schemaVersion=2,mediaType='application/vnd.oci.image.manifest.v1+json',config=cfg,layers=layers))
    manifest=desc(raw,'application/vnd.oci.image.manifest.v1+json');blobs[manifest['digest']]=raw
    root=manifest
    if indexed:
        child=manifest|{'platform':{'os':'linux','architecture':'amd64'}}
        raw=oci.encoded(dict(schemaVersion=2,mediaType='application/vnd.oci.image.index.v1+json',manifests=[child]))
        root=desc(raw,'application/vnd.oci.image.index.v1+json');blobs[root['digest']]=raw
    return root,blobs


def write_graph(path,root,blobs):
    path.parent.mkdir(parents=True,exist_ok=True)
    values={'oci-layout':oci.encoded({'imageLayoutVersion':'1.0.0'}),
            'index.json':oci.encoded({'schemaVersion':2,'manifests':[root]})}
    values.update({'blobs/sha256/'+sha.split(':')[1]:raw for sha,raw in blobs.items()})
    with tarfile.open(path,'w') as archive:
        for name,raw in sorted(values.items()):
            item=tarfile.TarInfo(name);item.size=len(raw);archive.addfile(item,io.BytesIO(raw))


@contextmanager
def registry(blobs,corrupt=None):
    calls=[]
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def do_GET(self):
            calls.append(self.path)
            if self.path.startswith('/token?'):raw=b'{"token":"public-fixture"}'
            else:
                if self.headers.get('Authorization')!='Bearer public-fixture':self.send_error(401);return
                sha=self.path.rsplit('/',1)[-1];raw=blobs[sha]
                if sha==corrupt:raw+=b'tamper'
            self.send_response(200);self.end_headers();self.wfile.write(raw)
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    opener=urllib.request.urlopen
    def local(request,**kwargs):
        url=request.full_url if isinstance(request,urllib.request.Request) else request
        self_url=urllib.parse.urlsplit(url)
        if self_url.scheme!='https' or self_url.hostname not in ('auth.docker.io','registry-1.docker.io'):
            raise AssertionError('Unexpected registry endpoint')
        target='http://127.0.0.1:'+str(server.server_port)+self_url.path+('?' + self_url.query if self_url.query else '')
        headers=dict(request.header_items()) if isinstance(request,urllib.request.Request) else {}
        return opener(urllib.request.Request(target,headers=headers),**kwargs)
    try:
        with patch.object(oci.urllib.request,'urlopen',side_effect=local):yield calls
    finally:server.shutdown();server.server_close();thread.join()


class ImageBuildTests(unittest.TestCase):
    def test_dockerhub_exports_pinned_amd64_graph_via_anonymous_http(self):
        root,blobs=graph(layer=b'fixture layer',indexed=True)
        with tempfile.TemporaryDirectory() as tmp,registry(blobs) as calls:
            target=Path(tmp)/'base.tar'
            oci.export_dockerhub('docker.io/library/python:1.2.3@'+root['digest'],target)
            with tarfile.open(target) as archive:
                index=json.load(archive.extractfile('index.json'))
                self.assertEqual(index['manifests'][0],root)
                for sha,raw in blobs.items():
                    self.assertEqual(archive.extractfile('blobs/sha256/'+sha.split(':')[1]).read(),raw)
            self.assertIn('repository%3Alibrary%2Fpython%3Apull',calls[0])
            self.assertTrue(any(root['digest'] in call for call in calls))

    def test_dockerhub_refuses_digest_mismatch_without_replacing_cache(self):
        root,blobs=graph(layer=b'fixture layer',indexed=True)
        for sha in blobs:
            with self.subTest(sha=sha),tempfile.TemporaryDirectory() as tmp,registry(blobs,corrupt=sha):
                target=Path(tmp)/'base.tar';target.write_bytes(b'existing cache')
                with self.assertRaisesRegex(ValueError,'checksum'):oci.export_dockerhub('docker.io/library/python@'+root['digest'],target)
                self.assertEqual(target.read_bytes(),b'existing cache')
                self.assertFalse(target.with_name('base.tar.part').exists())

    def test_unpinned_or_foreign_registry_never_opens_http(self):
        with patch.object(oci.urllib.request,'urlopen',side_effect=AssertionError('Network called')):
            for ref in ('docker.io/library/python:1.2.3','quay.io/library/python@sha256:'+'a'*64,
                        'docker.io/../python@sha256:'+'a'*64):
                with self.assertRaises(ValueError):oci.export_dockerhub(ref,Path('unused.tar'))

    @contextmanager
    def fixture(self):
        with tempfile.TemporaryDirectory() as tmp,ExitStack() as patches:
            root=Path(tmp);wheels=root/'.build/console/wheels';wheels.mkdir(parents=True)
            for path in ('console/server.py','console/aws_views.py','tools/build_console_image.py','tools/platform_oci.py'):
                file=root/path;file.parent.mkdir(parents=True,exist_ok=True);file.write_bytes(b'# fixture\n')
            dist=root/'console/dist';(dist/'assets').mkdir(parents=True)
            (dist/'index.html').write_text('<script src="/console/assets/app.js"></script>')
            (dist/'assets/app.js').write_bytes(b'fixture frontend')
            wheel=wheels/'sample-1.0-py3-none-any.whl'
            with zipfile.ZipFile(wheel,'w') as archive:archive.writestr('sample.py',b'# fixture');archive.writestr('sample-1.0.dist-info/LICENSE',b'MIT fixture')
            (root/'console/requirements.txt').write_text('sample==1.0 --hash=sha256:'+hashlib.sha256(wheel.read_bytes()).hexdigest()+'\n')
            inputs=root/'.build/dev-images/inputs'
            base_root,blobs=graph();base=root/'.build/console/python-base.oci.tar';write_graph(base,base_root,blobs)
            write_graph(inputs/'postgres-base.oci.tar',base_root,blobs)
            layer=io.BytesIO()
            with tarfile.open(fileobj=layer,mode='w') as archive:
                for name,raw in [('lib/vector.so',b'fixture library'),('share/extension/vector.control',b'fixture control')]:
                    item=tarfile.TarInfo(name);item.size=len(raw);archive.addfile(item,io.BytesIO(raw))
            ext_root,ext_blobs=graph(layer.getvalue());write_graph(inputs/'pgvector.oci.tar',ext_root,ext_blobs)
            for module in (console,builds,retained):patches.enter_context(patch.object(module,'ROOT',root))
            patches.enter_context(patch.object(console,'BASE',console.BASE.split('@')[0]+'@'+base_root['digest']))
            patches.enter_context(patch.object(pg,'BASE','ghcr.io/example/base@'+base_root['digest']))
            patches.enter_context(patch.object(pg,'EXTENSION','ghcr.io/example/extension@'+ext_root['digest']))
            receipt=console.build(base,root/'initial-console.tar',wheels)
            common=root/'deploy/common';common.mkdir(parents=True)
            with ExitStack() as exports:
                b=pg.Export(inputs/'postgres-base.oci.tar');exports.callback(b.archive.close)
                e=pg.Export(inputs/'pgvector.oci.tar');exports.callback(e.archive.close)
                pg_receipt=pg.build(b,e,root/'initial-postgres.tar')
            images={'console':{'canonical':receipt['canonical'],'digest':receipt['digest']},
                    'python':{'canonical':receipt['base']},'postgres':{'digest':pg_receipt['manifestDigest']}}
            (root/'console/image.lock.json').write_text(json.dumps(receipt))
            (common/'images.lock.json').write_text(json.dumps({'images':images}))
            (common/'postgresql-image.lock.json').write_text(json.dumps(pg_receipt))
            yield root,wheels,base

    def test_console_fixture_reproduces_identical_archive_and_retains_image_config(self):
        with self.fixture() as (root,wheels,base):
            a=root/'a.tar';b=root/'b.tar'
            first=console.build(base,a,wheels);second=console.build(base,b,wheels)
            self.assertEqual(first,second);self.assertEqual(a.read_bytes(),b.read_bytes())
            with tarfile.open(a) as archive:
                desc=json.load(archive.extractfile('index.json'))['manifests'][0]
                manifest=json.load(archive.extractfile('blobs/sha256/'+desc['digest'].split(':')[1]))
                config=json.load(archive.extractfile('blobs/sha256/'+manifest['config']['digest'].split(':')[1]))
                self.assertEqual(config['config']['Labels']['org.opencontainers.image.title'],'twinfra-console')
                self.assertEqual(config['history'][-1]['created_by'],'twinfra-console deterministic application layer')
                self.assertEqual(config['config']['User'],'65532:65532')

    def test_wheel_hash_and_built_frontend_asset_drift_refused(self):
        with self.fixture() as (root,wheels,base):
            next(wheels.glob('*.whl')).write_bytes(b'corrupted wheel')
            with self.assertRaisesRegex(ValueError,'hash differs'):console.build(base,root/'bad.tar',wheels)
        with self.fixture() as (root,wheels,base):
            (root/'console/dist/assets/app.js').unlink()
            with self.assertRaisesRegex(ValueError,'frontend asset'):console.build(base,root/'bad.tar',wheels)

    def test_build_images_default_is_offline_and_leaves_repository_bytes_unchanged(self):
        with self.fixture() as (root,wheels,base):
            before={p.relative_to(root).as_posix():p.read_bytes() for p in root.rglob('*') if p.is_file() and '.build' not in p.parts}
            with patch.object(oci.urllib.request,'urlopen',side_effect=AssertionError('Network called')),\
                 patch.object(console.subprocess,'run',side_effect=AssertionError('Program called')),\
                 patch.object(dev,'refresh_console_image',side_effect=AssertionError('Receipt rewrite called')),\
                 patch.object(dev,'outputs',side_effect=AssertionError('Render called')),\
                 patch.object(sys,'argv',['platform_dev.py','build-images']),redirect_stdout(io.StringIO()) as output:
                self.assertEqual(dev.main(),0)
                report=json.loads(output.getvalue())
            self.assertEqual(report['status'],'passed');self.assertFalse(report['repositoryWrites'])
            self.assertTrue((root/'.build/dev-images/console.oci.tar').is_file())
            self.assertTrue((root/'.build/dev-images/postgresql-pgvector.tar').is_file())
            after={p.relative_to(root).as_posix():p.read_bytes() for p in root.rglob('*') if p.is_file() and '.build' not in p.parts}
            self.assertEqual(before,after)

    def test_build_images_lock_mismatch_refuses_without_repository_or_archive_publish(self):
        with self.fixture() as (root,wheels,base):
            lock=root/'deploy/common/images.lock.json';value=json.loads(lock.read_text());value['images']['console']['digest']='sha256:'+'a'*64;lock.write_text(json.dumps(value))
            before=lock.read_bytes()
            with self.assertRaisesRegex(ValueError,'did not reproduce'):builds.build_images()
            self.assertEqual(lock.read_bytes(),before)
            self.assertFalse((root/'.build/dev-images/console.oci.tar').exists())
        with self.fixture() as (root,wheels,base):
            lock=root/'deploy/common/images.lock.json';value=json.loads(lock.read_text());value['images']['postgres']['digest']='sha256:'+'a'*64;lock.write_text(json.dumps(value))
            with self.assertRaisesRegex(ValueError,'digest differs'):builds.build_images()
            self.assertFalse((root/'.build/dev-images/console.oci.tar').exists())

    def test_receipt_refresh_refuses_console_source_and_digest_changes(self):
        with self.fixture() as (root,wheels,base):
            before=(root/'console/image.lock.json').read_bytes()
            receipt=console.build(base,root/'a.tar',wheels)
            receipt['digest']='sha256:'+'b'*64
            with self.assertRaisesRegex(ValueError,'did not reproduce'):console.verify_receipt(receipt,refresh=True)
            receipt=console.build(base,root/'a.tar',wheels);receipt['filesSHA256']['console/server.py']='a'*64
            with self.assertRaisesRegex(ValueError,'source hashes'):console.verify_receipt(receipt,refresh=True)
            self.assertEqual((root/'console/image.lock.json').read_bytes(),before)

    def test_download_is_explicit_hash_locked_linux_wheels_and_never_installs(self):
        with self.fixture() as (root,wheels,base),patch.object(oci,'export_dockerhub') as exported,\
             patch.object(console.subprocess,'run') as launched:
            console.download_inputs(base,wheels)
            self.assertTrue(exported.call_args.args[0].startswith('docker.io/'))
            command=launched.call_args.args[0]
            self.assertEqual(command[:4],[sys.executable,'-m','pip','download'])
            self.assertIn('--require-hashes',command);self.assertIn('--only-binary=:all:',command)
            self.assertIn('manylinux_2_28_x86_64',command);self.assertIn('cp314',command)
            self.assertNotIn('install',command);self.assertNotIn('npm',command)

    def test_no_retired_runtime_import_path_remains(self):
        code=(ROOT/'tools/build_console_image.py').read_text()
        for forbidden in ('vcloud-wsl','microsoft','--import',"['ctr'"):
            self.assertNotIn(forbidden,code)

    def test_retained_renderer_accepts_twinfra_metadata_and_rejects_drift(self):
        with self.fixture() as (root,wheels,base):
            lock=root/'console/image.lock.json';original=json.loads(lock.read_text())
            self.assertEqual(retained.image(),'registry.vcloud.example.com/vcloud/vcloud-console@'+original['digest'])
            bad=copy.deepcopy(original);bad['digest']='sha256:'+'f'*64;lock.write_text(json.dumps(bad))
            with self.assertRaisesRegex(ValueError,'digest differs'):retained.image()
            lock.write_text(json.dumps(original));(root/'console/server.py').write_bytes(b'changed source')
            with self.assertRaisesRegex(ValueError,'source drift'):retained.image()

    def test_production_wsl_and_pin_bytes_unchanged_against_main(self):
        for name in ('00-setup-ubuntu-host.sh','user-data.yaml','user-data-remote.yaml','user-data.yaml.gz',
                     'deploy/common/postgresql-image.lock.json',
                     'tools/ci/pr-baselines.json','security/licence-policy.json'):
            old=subprocess.check_output(['git','-C',str(ROOT),'show',BASELINE+':'+name])
            raw=(ROOT/name).read_bytes()
            self.assertEqual(raw if name.endswith('.gz') else raw.replace(b'\r\n',b'\n'),old,name)
        old_lock=json.loads(subprocess.check_output(['git','-C',str(ROOT),'show',BASELINE+':deploy/common/images.lock.json']))
        current_lock=json.loads((ROOT/'deploy/common/images.lock.json').read_text())
        for key in ('console','python'):
            for field in ('source','canonical','digest'):
                old_lock['images'][key][field]=current_lock['images'][key][field]
        self.assertEqual(current_lock,old_lock,'Only the WO-34 console/Python pins may change')
        old_console=json.loads(subprocess.check_output(['git','-C',str(ROOT),'show',BASELINE+':console/image.lock.json']))
        current_console=json.loads((ROOT/'console/image.lock.json').read_text())
        for name,raw in retained.outputs().items():
            old=subprocess.check_output(['git','-C',str(ROOT),'show',BASELINE+':deploy/console/'+name])
            self.assertEqual(raw.replace(current_console['digest'],old_console['digest']).encode(),old,name)
            actual=(ROOT/'deploy/console'/name).read_bytes().replace(b'\r\n',b'\n')
            self.assertEqual(actual,raw.encode(),name)

    def test_receipt_refresh_changes_only_allowed_metadata_and_tooling(self):
        old=json.loads(subprocess.check_output(['git','-C',str(ROOT),'show',BASELINE+':console/image.lock.json']))
        current=json.loads((ROOT/'console/image.lock.json').read_text())
        self.assertNotEqual(old['digest'],current['digest'])
        self.assertEqual(current['base'],console.BASE)
        for name,sha in old['filesSHA256'].items():
            if name not in ('tools/build_console_image.py','tools/platform_oci.py','console/Dockerfile'):
                self.assertEqual(current['filesSHA256'][name],sha,name)
        self.assertEqual(current['canonical'],json.loads((ROOT/'deploy/common/images.lock.json').read_text())['images']['console']['canonical'])

    def test_console_refresh_refuses_minor_jump_and_application_source_drift(self):
        with self.fixture() as (root,wheels,base):
            receipt=console.build(base,root/'a.tar',wheels)
            self.assertEqual(console.verify_patch_refresh(receipt),receipt)
            changed=copy.deepcopy(receipt);changed['base']=changed['base'].replace('3.14.8','3.15.0')
            with self.assertRaisesRegex(ValueError,'same Python minor'):console.verify_patch_refresh(changed)
            changed=copy.deepcopy(receipt);changed['filesSHA256']['console/server.py']='a'*64
            with self.assertRaisesRegex(ValueError,'application sources'):console.verify_patch_refresh(changed)

    def test_source_bound_frontend_archive_matches_preserved_candidate(self):
        lock=json.loads((ROOT/'console/frontend.lock.json').read_text())
        self.assertEqual(hashlib.sha256((ROOT/'console/frontend.tar.gz').read_bytes()).hexdigest(),lock['archiveSHA256'])
        for name,sha in lock['sourcesSHA256'].items():
            self.assertEqual(hashlib.sha256((ROOT/name).read_bytes()).hexdigest(),sha,name)
        with patch.object(console,'ROOT',ROOT),patch.object(console.tarfile,'open',side_effect=AssertionError('Archive opened')):
            with patch.object(console.hashlib,'sha256') as sha:
                sha.return_value.hexdigest.return_value='invalid'
                with self.assertRaisesRegex(ValueError,'checksum'):console.stage_frontend()

    def test_pinned_compression_layer_is_verified_against_fresh_payload(self):
        lock=json.loads((ROOT/'console/application-layer.lock.json').read_text())
        raw=(ROOT/'console/application-layer.tar.gz').read_bytes()
        import gzip
        self.assertEqual(hashlib.sha256(raw).hexdigest(),lock['archiveSHA256'])
        self.assertEqual(hashlib.sha256(gzip.decompress(raw)).hexdigest(),lock['uncompressedSHA256'])
        with self.fixture() as (root,wheels,base):
            (root/'console/application-layer.lock.json').write_text(json.dumps(lock))
            (root/'console/application-layer.tar.gz').write_bytes(raw)
            with self.assertRaisesRegex(ValueError,'freshly assembled payload'):
                console.build(base,root/'refused.tar',wheels)

    def test_explicit_refresh_updates_only_receipt_and_two_image_pins(self):
        with self.fixture() as (root,wheels,base):
            before=json.loads((root/'deploy/common/images.lock.json').read_text())
            pg_before=(root/'deploy/common/postgresql-image.lock.json').read_bytes()
            result=builds.build_images(refresh_console=True)
            self.assertTrue(result['repositoryWrites']);self.assertFalse(result['runtimeImport'])
            after=json.loads((root/'deploy/common/images.lock.json').read_text())
            self.assertEqual(before['images']['postgres'],after['images']['postgres'])
            self.assertEqual(pg_before,(root/'deploy/common/postgresql-image.lock.json').read_bytes())
            self.assertEqual(after['images']['console']['digest'],result['digests']['console'])
            builds.build_images()  # The ordinary offline path reproduces the newly generated receipt.


if __name__=='__main__':unittest.main()
