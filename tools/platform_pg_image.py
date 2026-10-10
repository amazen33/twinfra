#!/usr/bin/env python3
"""Reproduce the module-2 pgvector COPY stages as deterministic OCI file layers.

No build daemon or privileged build Pod is used. Verified base layers and the
extension bytes are retained, and the resulting image runs as PostgreSQL UID 26.
"""
import argparse
import copy
import io
import json
from pathlib import Path
import tarfile
from platform_oci import digest, encoded

REGISTRY='registry.twinfra.example.com/'
BASE='ghcr.io/cloudnative-pg/postgresql@sha256:37ade18dbdddba430858c72725aceeec66f33fa5333e82ea1df4942f6c1c83a3'
EXTENSION='ghcr.io/cloudnative-pg/pgvector@sha256:79fc129f885e2143bf6eb656a6b181ea449d1ef1a58c40fe5860986ed99bafcb'
IMAGE=REGISTRY+'twinfra/twinfra-postgresql-pgvector:18.6.0-pgvector0.8.2'


class Export:
    def __init__(self,path):
        self.archive=tarfile.open(path)
        index=json.load(self.archive.extractfile('index.json'))
        self.root_digest=index['manifests'][0]['digest']
        descriptor=index['manifests'][0]
        manifest=json.loads(self.blob(descriptor))
        while 'manifests' in manifest:
            descriptor=next(d for d in manifest['manifests'] if d.get('platform',{}).get('os')=='linux' and d.get('platform',{}).get('architecture')=='amd64')
            manifest=json.loads(self.blob(descriptor))
        self.manifest,self.descriptor=manifest,descriptor
    def blob(self,d):
        content=self.archive.extractfile('blobs/sha256/'+d['digest'].split(':')[1]).read()
        if digest(content)!=d['digest']:raise ValueError('Source image hash differs')
        return content
    def extension_files(self):
        result={}
        for layer in self.manifest['layers']:
            with tarfile.open(fileobj=io.BytesIO(self.blob(layer)),mode='r:*') as archive:
                for member in archive:
                    name=member.name.lstrip('./')
                    for prefix,target in [('lib/','usr/lib/postgresql/18/lib/'),('share/extension/','usr/share/postgresql/18/extension/')]:
                        if name.startswith(prefix) and member.isfile():
                            suffix=name[len(prefix):]
                            if '..' in Path(suffix).parts:raise ValueError('Invalid extension path')
                            result[target+suffix]=archive.extractfile(member).read()
        if not any(name.endswith('/vector.so') for name in result) or not any(name.endswith('/vector.control') for name in result):
            raise ValueError('Expected pgvector library/control files absent')
        return result


def build(base,extension,output):
    files=extension.extension_files();layer_io=io.BytesIO()
    with tarfile.open(fileobj=layer_io,mode='w',format=tarfile.USTAR_FORMAT) as archive:
        for name,content in sorted(files.items()):
            member=tarfile.TarInfo(name);member.size=len(content);member.mode=0o644;member.uid=member.gid=26
            archive.addfile(member,io.BytesIO(content))
    layer=layer_io.getvalue()
    config=json.loads(base.blob(base.manifest['config']));config['config']['User']='26:26'
    config['rootfs']['diff_ids'].append(digest(layer))
    config.setdefault('history',[]).append({'created':'1970-01-01T00:00:00Z','created_by':'vcloud verified pgvector file copy'})
    config_raw=encoded(config)
    manifest=copy.deepcopy(base.manifest);manifest.pop('annotations',None)
    manifest['mediaType']='application/vnd.oci.image.manifest.v1+json'
    manifest['config']={'mediaType':'application/vnd.oci.image.config.v1+json','digest':digest(config_raw),'size':len(config_raw)}
    manifest['layers'].append({'mediaType':'application/vnd.oci.image.layer.v1.tar','digest':digest(layer),'size':len(layer)})
    raw=encoded(manifest)
    index=encoded({'schemaVersion':2,'manifests':[{'mediaType':manifest['mediaType'],'digest':digest(raw),'size':len(raw),
        'platform':{'os':'linux','architecture':'amd64'},'annotations':{'org.opencontainers.image.ref.name':IMAGE}}]})
    data={'oci-layout':encoded({'imageLayoutVersion':'1.0.0'}),'index.json':index}
    for item in [config_raw,layer,raw]:data['blobs/sha256/'+digest(item).split(':')[1]]=item
    for descriptor in base.manifest['layers']:
        data['blobs/sha256/'+descriptor['digest'].split(':')[1]]=base.blob(descriptor)
    with tarfile.open(output,'w',format=tarfile.USTAR_FORMAT) as archive:
        for name,content in sorted(data.items()):
            member=tarfile.TarInfo(name);member.size=len(content);member.mode=0o644;archive.addfile(member,io.BytesIO(content))
    return {'image':IMAGE,'manifestDigest':digest(raw),'baseManifest':base.descriptor['digest'],
            'extensionManifest':extension.descriptor['digest'],'copiedFiles':sorted(files),'user':'26:26'}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base',type=Path,required=True)
    parser.add_argument('--extension',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--receipt',type=Path,default=Path('deploy/common/postgresql-image.lock.json'))
    parser.add_argument('--download-inputs',action='store_true',help='Owner-only public digest-verified download; never imports/starts containers')
    parser.add_argument('--check',action='store_true',help='Compare the generated receipt without replacing it')
    args=parser.parse_args()
    if args.download_inputs:
        from platform_oci import export_ghcr
        for reference,path in ((BASE,args.base),(EXTENSION,args.extension)):
            if not path.is_file():export_ghcr(reference,path)
    base,extension=Export(args.base),Export(args.extension)
    if base.root_digest!=BASE.split('@')[1] or extension.root_digest!=EXTENSION.split('@')[1]:
        raise ValueError('Input OCI export differs from the approved image pin')
    args.output.parent.mkdir(parents=True,exist_ok=True)
    receipt=build(base,extension,args.output)
    if args.check:
        if json.loads(args.receipt.read_text())!=receipt:raise ValueError('PG image receipt differs')
    else:args.receipt.write_text(json.dumps(receipt,indent=2)+'\n',encoding='utf-8',newline='\n')
    print('PASS: verified pgvector OCI image '+receipt['manifestDigest']+'; no runtime import')
