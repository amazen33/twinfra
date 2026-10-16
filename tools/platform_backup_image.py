#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Deterministic backup image: admitted Python/OpenSSL plus verified SDK wheels.

Never runs installers, image code, a daemon or SSH. --refresh is the sole writer
of this image's receipt and lock entry. Downloaded inputs stay in .build.
"""
import argparse
import copy
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import stat
import tarfile
import urllib.request
import zipfile

from platform_oci import digest, encoded, export_dockerhub
from platform_pg_image import Export

ROOT=Path(__file__).resolve().parents[1]
COMMON=ROOT/'deploy/common'
TAG='registry.twinfra.example.com/docker.io/twinfra/twinfra-backup:1.0.0'
FILES=('deploy/common/backup/upload.py',)


def wheels_payload(directory, lock):
    files={}
    for item in lock['wheels']:
        path=directory/item['filename'];raw=path.read_bytes()
        if hashlib.sha256(raw).hexdigest()!=item['sha256']:raise ValueError('Backup wheel checksum differs')
        if not path.name.endswith(('-py3-none-any.whl','-py2.py3-none-any.whl')):
            raise ValueError('Only the admitted pure-Python SDK wheels are allowed')
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            for member in archive.infolist():
                if member.is_dir():continue
                name=PurePosixPath(member.filename)
                if (name.is_absolute() or '..' in name.parts or '\\' in member.filename or
                        stat.S_ISLNK(member.external_attr>>16) or name.suffix=='.pth'):
                    raise ValueError('Unsafe backup wheel member')
                # Preserve optional wheel scripts as inert bytes outside the
                # import/PATH roots; no installer or entry-point code executes.
                target=('app/wheel-data/' if name.parts[0].endswith('.data') else 'app/vendor/')+str(name)
                if target in files:raise ValueError('Duplicate backup dependency member')
                files[target]=archive.read(member)
    return files


def build(base_path, wheel_dir, output):
    images=json.loads((COMMON/'images.lock.json').read_text())['images']
    lock=json.loads((COMMON/'backup-artifacts.lock.json').read_text())
    base=Export(base_path)
    try:
        if base.root_digest!=images['python']['digest']:raise ValueError('Unadmitted backup Python base')
        files=wheels_payload(wheel_dir,lock)
        for path in FILES:files['app/'+Path(path).name]=(ROOT/path).read_bytes()
        files['app/requirements.txt']=(COMMON/'backup/requirements.txt').read_bytes()
        layer=io.BytesIO()
        with tarfile.open(fileobj=layer,mode='w',format=tarfile.PAX_FORMAT) as archive:
            for name,raw in sorted(files.items()):
                item=tarfile.TarInfo(name);item.size=len(raw);item.mode=0o444;item.uid=item.gid=65532;item.mtime=0
                archive.addfile(item,io.BytesIO(raw))
        raw_layer=layer.getvalue();config=json.loads(base.blob(base.manifest['config']))
        config['rootfs']['diff_ids'].append(digest(raw_layer));config['created']='2026-10-16T00:00:00Z'
        config.setdefault('history',[]).append({'created':config['created'],'created_by':'twinfra-backup verified SDK and CMS uploader'})
        config['config'].update(User='65532:65532',WorkingDir='/app',Entrypoint=['python','/app/upload.py'],Cmd=[])
        config['config']['Env']=[v for v in config['config'].get('Env',[]) if not v.startswith('PYTHONPATH=')]+['PYTHONPATH=/app/vendor','PYTHONDONTWRITEBYTECODE=1']
        config['config'].setdefault('Labels',{}).update({'org.opencontainers.image.title':'twinfra-backup','org.opencontainers.image.licenses':'MIT'})
        config_raw=encoded(config);manifest=copy.deepcopy(base.manifest);manifest.pop('annotations',None)
        manifest['mediaType']='application/vnd.oci.image.manifest.v1+json'
        manifest['config']={'mediaType':'application/vnd.oci.image.config.v1+json','digest':digest(config_raw),'size':len(config_raw)}
        manifest['layers'].append({'mediaType':'application/vnd.oci.image.layer.v1.tar','digest':digest(raw_layer),'size':len(raw_layer)})
        raw=encoded(manifest);sha=digest(raw)
        files={'oci-layout':encoded({'imageLayoutVersion':'1.0.0'}),'index.json':encoded({'schemaVersion':2,'manifests':[
            {'mediaType':manifest['mediaType'],'digest':sha,'size':len(raw),'platform':{'os':'linux','architecture':'amd64'},
             'annotations':{'org.opencontainers.image.ref.name':TAG}}]})}
        for value in (raw,raw_layer,config_raw):files['blobs/sha256/'+digest(value).split(':')[1]]=value
        for desc in base.manifest['layers']:files['blobs/sha256/'+desc['digest'].split(':')[1]]=base.blob(desc)
        output.parent.mkdir(parents=True,exist_ok=True)
        with tarfile.open(output,'w',format=tarfile.USTAR_FORMAT) as archive:
            for name,value in sorted(files.items()):
                item=tarfile.TarInfo(name);item.size=len(value);item.mode=0o644;archive.addfile(item,io.BytesIO(value))
        return {'digest':sha,'canonical':TAG.split(':1.0.0')[0]+'@'+sha,'base':images['python']['canonical'],
                'filesSHA256':{p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in FILES+('deploy/common/backup/requirements.txt',)},
                'wheels':{v['filename']:v['sha256'] for v in lock['wheels']},'openssl':lock['embeddedTools'][0]}
    finally:base.archive.close()


def download_inputs(base, directory):
    lock=json.loads((COMMON/'backup-artifacts.lock.json').read_text())
    image=json.loads((COMMON/'images.lock.json').read_text())['images']['python']
    if not base.is_file():export_dockerhub(image['source'],base)
    directory.mkdir(parents=True,exist_ok=True)
    for item in lock['wheels']:
        path=directory/item['filename']
        if path.is_file() and hashlib.sha256(path.read_bytes()).hexdigest()==item['sha256']:continue
        if not item['url'].startswith('https://files.pythonhosted.org/'):raise ValueError('Unapproved wheel origin')
        with urllib.request.urlopen(item['url'],timeout=120) as response:raw=response.read()
        if hashlib.sha256(raw).hexdigest()!=item['sha256']:raise ValueError('Downloaded backup wheel differs')
        path.write_bytes(raw)


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--download-inputs',action='store_true')
    parser.add_argument('--refresh',action='store_true');args=parser.parse_args()
    base=ROOT/'.build/console/python-base.oci.tar';wheels=ROOT/'.build/wo09/wheels';output=ROOT/'.build/dev-images/backups.oci.tar'
    if args.download_inputs:download_inputs(base,wheels)
    receipt=build(base,wheels,output);path=COMMON/'backup-image.lock.json'
    if args.refresh:
        path.write_text(json.dumps(receipt,indent=2)+'\n',encoding='utf-8',newline='\n')
        lock_path=COMMON/'images.lock.json';lock=json.loads(lock_path.read_text())
        lock['images']['backup']={'source':receipt['canonical'].removeprefix('registry.twinfra.example.com/'),
                                'canonical':receipt['canonical'],'digest':receipt['digest'],'buildReceipt':'deploy/common/backup-image.lock.json'}
        lock_path.write_text(json.dumps(lock,indent=2)+'\n',encoding='utf-8',newline='\n')
    elif not path.is_file() or receipt!=json.loads(path.read_text()):raise ValueError('Backup receipt differs; use the reviewed generator --refresh')
    print('PASS: deterministic backup image '+receipt['digest']+'; no runtime import')


if __name__=='__main__':main()
