#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Disposable CI-only etcd fixture and CMS restore. Never connects to a cluster."""
import argparse
import gzip
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import time
import uuid

ROOT=Path(__file__).resolve().parents[2]


def docker_archive(source, destination):
    """Docker's classic store needs Docker-save metadata, not an OCI index.

    Only verified layer decompression/metadata conversion; image bytes and diff
    IDs are unchanged. No image code or installer executes during conversion.
    """
    sys.path.insert(0,str(ROOT/'tools'))
    from platform_pg_image import Export
    image=Export(source)
    try:
        config_raw=image.blob(image.manifest['config']);config=json.loads(config_raw)
        contents={image.manifest['config']['digest'].split(':')[1]+'.json':config_raw};layers=[]
        for descriptor,expected in zip(image.manifest['layers'],config['rootfs']['diff_ids'],strict=True):
            raw=image.blob(descriptor)
            if descriptor['mediaType'].endswith('+gzip') or descriptor['mediaType'].endswith('.gzip'):raw=gzip.decompress(raw)
            if 'sha256:'+hashlib.sha256(raw).hexdigest()!=expected:raise ValueError('Docker fixture layer diff ID differs')
            name=expected.split(':')[1]+'/layer.tar';contents[name]=raw;layers.append(name)
        contents['manifest.json']=json.dumps([{'Config':next(iter(contents)),
            'RepoTags':['registry.twinfra.example.com/docker.io/twinfra/twinfra-backup:1.0.0'],'Layers':layers}]).encode()
        with tarfile.open(destination,'w') as archive:
            for name,raw in contents.items():
                member=tarfile.TarInfo(name);member.size=len(raw);member.mode=0o444;archive.addfile(member,io.BytesIO(raw))
    finally:image.archive.close()


def run(args, **kwargs):
    result=subprocess.run(args,capture_output=True,**kwargs)
    if result.returncode:raise ValueError('CI fixture command failed: '+args[0]+' (no secret output retained)')
    return result.stdout


def verify(output):
    output.mkdir(parents=True,exist_ok=True)
    images=json.loads((ROOT/'deploy/common/images.lock.json').read_text())['images']
    admitted=json.loads((ROOT/'deploy/common/backup-artifacts.lock.json').read_text())['embeddedTools'][0]
    etcd=images['etcd-backup']['source'];python=images['python']['source']
    name='twinfra-backup-fixture-'+uuid.uuid4().hex[:12]
    common=['--network','none','--read-only','--cap-drop','ALL','--security-opt','no-new-privileges','--user','65532:65532']
    try:
        converted=output/'backup-docker.tar'
        docker_archive(ROOT/'.build/dev-images/backups.oci.tar',converted)
        run(['docker','load','--input',str(converted)])
        converted.unlink()
        sdk=json.loads(run(['docker','run','--rm',*common,'--entrypoint','python',
            'registry.twinfra.example.com/docker.io/twinfra/twinfra-backup:1.0.0','-c',
            'import boto3,botocore,json,ssl; print(json.dumps({"boto3":boto3.__version__,"botocore":botocore.__version__,"tls":ssl.OPENSSL_VERSION}))']))
        assert sdk['boto3']==sdk['botocore']=='1.43.108'
        etcd_common=common[:-2]+['--user',str(os.getuid())+':'+str(os.getgid())]
        run(['docker','run','-d','--name',name,*etcd_common,'--tmpfs','/fixture:rw,nosuid,nodev,noexec,size=128m,mode=1777',
             '--mount','type=bind,source='+str(output.resolve())+',target=/export',
             '--entrypoint','/usr/local/bin/etcd',etcd,'--data-dir=/fixture/data','--listen-client-urls=http://127.0.0.1:2379',
             '--advertise-client-urls=http://127.0.0.1:2379'])
        for attempt in range(30):
            result=subprocess.run(['docker','exec',name,'/usr/local/bin/etcdctl','endpoint','health'],capture_output=True)
            if result.returncode==0:break
            time.sleep(1)
        else:raise ValueError('Disposable etcd fixture did not become ready')
        run(['docker','exec',name,'/usr/local/bin/etcdctl','put','wo09-public-fixture','synthetic-value'])
        run(['docker','exec',name,'/usr/local/bin/etcdctl','snapshot','save','/export/snapshot.db'])
        status=json.loads(run(['docker','exec',name,'/usr/local/bin/etcdutl','snapshot','status','/export/snapshot.db','--write-out=json']))
        (output/'snapshot.db').chmod(0o644)  # Public synthetic fixture; never a real snapshot.
        source=(ROOT/'deploy/common/backup/upload.py').read_text(encoding='utf-8')
        program='source='+repr(source)+'\nexpected='+repr(admitted)+'\n'+r'''
import hashlib,json,pathlib,subprocess,tempfile
scope={'__name__':'backup_fixture'};exec(compile(source,'upload.py','exec'),scope)
def command(args):
    p=subprocess.run(args,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    if p.returncode:raise RuntimeError('CMS fixture command failed; output suppressed')
    return p.stdout
assert hashlib.sha256(pathlib.Path('/usr/bin/openssl').read_bytes()).hexdigest()==expected['sha256']
assert hashlib.sha256(pathlib.Path('/usr/lib/x86_64-linux-gnu/libcrypto.so.3').read_bytes()).hexdigest()==expected['librarySHA256']
version=command(['/usr/bin/openssl','version']).decode().strip()
assert version.startswith('OpenSSL '+expected['version']+' ')
results=[]
with tempfile.TemporaryDirectory(dir='/tmp') as d:
    d=pathlib.Path(d);plain=pathlib.Path('/fixture/snapshot.db')
    for algorithm in ('rsa:4096','ec'):
        key=d/'key.pem';cert=d/'certificate.pem';encrypted=d/'snapshot.cms';decrypted=d/'restored.db'
        args=['/usr/bin/openssl','req','-new','-x509','-newkey',algorithm,'-nodes','-days','1',
              '-subj','/CN=WO09 synthetic CI fixture','-keyout',str(key),'-out',str(cert)]
        if algorithm=='ec':args+=['-pkeyopt','ec_paramgen_curve:P-256']
        command(args)
        scope['public_certificate'](cert)
        mode=scope['encrypt'](plain,cert,encrypted)
        assert mode=='AES-256-GCM', 'Pinned OpenSSL must support authenticated CMS'
        command(['/usr/bin/openssl','cms','-decrypt','-binary','-inform','DER','-in',str(encrypted),
                 '-recip',str(cert),'-inkey',str(key),'-out',str(decrypted)])
        assert decrypted.read_bytes()==plain.read_bytes()
        damaged=bytearray(encrypted.read_bytes());damaged[-1]^=1;encrypted.write_bytes(damaged)
        p=subprocess.run(['/usr/bin/openssl','cms','-decrypt','-binary','-inform','DER','-in',str(encrypted),
                          '-recip',str(cert),'-inkey',str(key),'-out',str(decrypted)],capture_output=True)
        assert p.returncode!=0, 'CMS must reject altered ciphertext'
        results.append({'recipient':algorithm,'mode':mode,'decryptMatchesSnapshot':True,'tamperingRejected':True})
print(json.dumps({'opensslVersion':version,'results':results,'privateKeysRetained':False}))
'''
        raw=run(['docker','run','--rm','-i',*common,'--tmpfs','/tmp:rw,nosuid,nodev,noexec,size=64m,mode=1777',
                 '--mount','type=bind,source='+str(output.resolve())+',target=/fixture,readonly','--entrypoint','python',python,'-'],input=program.encode())
        result=json.loads(raw)|{'etcdImage':etcd,'pythonImage':python,'sdk':sdk,'etcdSnapshotRevision':status['revision'],'scope':'synthetic CI fixture; no live acceptance'}
        (output/'summary.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
        print(json.dumps(result,indent=2))
    finally:
        subprocess.run(['docker','rm','-f',name],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        (output/'snapshot.db').unlink(missing_ok=True)
        (output/'backup-docker.tar').unlink(missing_ok=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True)
    verify(parser.parse_args().output)
