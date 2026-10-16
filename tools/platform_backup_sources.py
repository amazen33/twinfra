#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Render only WO-09 source-derived pins and TLS schemas; never downloads."""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import yaml

ROOT=Path(__file__).resolve().parents[1]
COMMON=ROOT/'deploy/common'


def write(path,value):path.write_text(json.dumps(value,indent=2)+'\n',encoding='utf-8',newline='\n')


def image_entries():
    backup=json.loads((COMMON/'backup-artifacts.lock.json').read_text())
    entries=dict(backup['images'])
    etcd=json.loads((COMMON/'bootstrap-images.lock.json').read_text())['images']['etcd']
    entries['etcd-backup']={'source':etcd['source'],'canonical':etcd['canonical']+'@'+etcd['digest'],
                                  'digest':etcd['digest'],'release':etcd['release']}
    return entries


def update_images():
    path=COMMON/'images.lock.json';value=json.loads(path.read_text())
    value['images'].update(image_entries())
    write(path,value)


def upstream_project():
    entry=json.loads((COMMON/'backup-artifacts.lock.json').read_text())['plugin']
    compressed=(COMMON/'vendor/barman-cloud.yaml.gz').read_bytes()
    if hashlib.sha256(compressed).hexdigest()!=entry['gzipSHA256']:raise ValueError('Barman vendor gzip differs')
    raw=gzip.decompress(compressed)
    if hashlib.sha256(raw).hexdigest()!=entry['sha256']:raise ValueError('Barman upstream source differs')
    objects=[v for v in yaml.safe_load_all(raw) if v and v['kind']!='Secret']
    return {'project':'cnpg-barman-cloud','version':entry['version'],'source':entry['url'],
        'sources':[{'path':'deploy/common/vendor/barman-cloud.yaml.gz','format':'gzip','sha256':entry['gzipSHA256']}],
        'names':[{'kind':v['kind'],'name':v['metadata']['name']} for v in objects]}


def schemas():
    lock=json.loads((COMMON/'backup-schemas.lock.json').read_text())
    result={}
    for filename,entry in lock.items():
        raw=gzip.decompress((COMMON/'vendor'/entry['vendor']).read_bytes())
        if hashlib.sha256(raw).hexdigest()!=entry['sha256']:raise ValueError('TLS schema source differs')
        crd=yaml.safe_load(raw)
        schema=next(v['schema']['openAPIV3Schema'] for v in crd['spec']['versions'] if v['name']=='v1')
        result[COMMON/'backup/schemas'/filename]=json.dumps(schema,indent=2)+'\n'
    return result


def main():
    parser=argparse.ArgumentParser();parser.add_argument('command',choices=['render','check']);args=parser.parse_args()
    if args.command=='render':
        update_images()
        path=ROOT/'deploy/upstream-names.json';registry=json.loads(path.read_text())
        registry['projects']=[v for v in registry['projects'] if v['project']!='cnpg-barman-cloud']+[upstream_project()]
        write(path,registry)
    registry=json.loads((ROOT/'deploy/upstream-names.json').read_text())
    if [v for v in registry['projects'] if v['project']=='cnpg-barman-cloud']!=[upstream_project()]:
        raise ValueError('Barman upstream-name registration differs')
    current=json.loads((COMMON/'images.lock.json').read_text())['images']
    if any(current.get(k)!=v for k,v in image_entries().items()):raise ValueError('Backup source-derived image pin drift')
    for path,text in schemas().items():
        if args.command=='check':
            if not path.is_file() or path.read_text()!=text:raise ValueError('Backup TLS schema drift')
        else:path.parent.mkdir(parents=True,exist_ok=True);path.write_text(text,encoding='utf-8',newline='\n')
    print('PASS: backup source-derived metadata '+args.command)


if __name__=='__main__':main()
