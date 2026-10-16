"""Owner-only deterministic dev image assembly; no runtime, SSH or repository writes. MIT."""
from contextlib import ExitStack
import json
from pathlib import Path
import tempfile

from platform_resources import ROOT
import build_console_image as console
import platform_pg_image as pg
from platform_oci import export_ghcr
from platform_image_staging import validate_archive


def build_images(download_inputs=False, refresh_console=False):
    directory=ROOT/'.build/dev-images';inputs=directory/'inputs'
    base=ROOT/'.build/console/python-base.oci.tar';wheels=ROOT/'.build/console/wheels'
    postgres=inputs/'postgres-base.oci.tar';extension=inputs/'pgvector.oci.tar'
    images=json.loads((ROOT/'deploy/common/images.lock.json').read_text())['images']
    if download_inputs:
        console.download_inputs(base,wheels)
        for reference,path in ((pg.BASE,postgres),(pg.EXTENSION,extension)):
            if not path.is_file():export_ghcr(reference,path)
    for path in (base,postgres,extension):
        if not path.is_file():raise ValueError('Missing build input: '+str(path)+'; owner may use --download-inputs')
    # Builders never run npm. Existing output and every input are checked before
    # publishing either archive; temporary work is confined to the ignored tree.
    directory.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='build-',dir=directory) as tmp,ExitStack() as stack:
        work=Path(tmp);console_path=work/'console.oci.tar';postgres_path=work/'postgresql-pgvector.tar'
        if 'backup' in images:
            from platform_backup_image import download_inputs as backup_inputs, build as backup_build
            backup_wheels=ROOT/'.build/wo09/wheels'
            if download_inputs:backup_inputs(base,backup_wheels)
            receipt=backup_build(base,backup_wheels,work/'backups.oci.tar')
            if receipt!=json.loads((ROOT/'deploy/common/backup-image.lock.json').read_text()):
                raise ValueError('Backup receipt differs; image locks were not changed')
            validate_archive(work/'backups.oci.tar',images['backup']['digest'])
        built_console=console.build(base,console_path,wheels)
        console_receipt=(console.verify_patch_refresh(built_console) if refresh_console
                         else console.verify_receipt(built_console))
        exports=[]
        for path,pin in ((postgres,pg.BASE),(extension,pg.EXTENSION)):
            item=pg.Export(path);stack.callback(item.archive.close)
            if item.root_digest!=pin.split('@')[1]:raise ValueError('PostgreSQL input differs from the approved pin')
            exports.append(item)
        postgres_receipt=pg.build(*exports,postgres_path)
        expected=json.loads((ROOT/'deploy/common/postgresql-image.lock.json').read_text())
        if postgres_receipt!=expected:raise ValueError('PostgreSQL receipt differs; locks were not updated')
        if refresh_console:
            # Build/verify both archives before changing either receipt or lock.
            images['console'].update(source='docker.io/twinfra/twinfra-console@'+console_receipt['digest'],
                canonical=console_receipt['canonical'],digest=console_receipt['digest'])
            images['python'].update(source=console.BASE.removeprefix('registry.twinfra.example.com/'),
                canonical=console.BASE,digest=console.BASE.split('@')[1])
        for name,path,actual in (('console',console_path,console_receipt['digest']),
                                  ('postgres',postgres_path,postgres_receipt['manifestDigest'])):
            if actual!=images[name]['digest']:raise ValueError(name+' built digest differs from image lock')
            validate_archive(path,images[name]['digest'])
        # Close all input archives before replacement/TemporaryDirectory cleanup on Windows.
        stack.close()
        if refresh_console:
            (ROOT/'console/image.lock.json').write_text(json.dumps(console_receipt,indent=2)+'\n',encoding='utf-8',newline='\n')
            lock=ROOT/'deploy/common/images.lock.json'
            value=json.loads(lock.read_text());value['images']=images
            lock.write_text(json.dumps(value,indent=2)+'\n',encoding='utf-8',newline='\n')
        console_path.replace(directory/'console.oci.tar')
        postgres_path.replace(directory/'postgresql-pgvector.tar')
        if 'backup' in images:(work/'backups.oci.tar').replace(directory/'backups.oci.tar')
    return {'status':'passed','archives':{'console':str(directory/'console.oci.tar'),
            'postgres':str(directory/'postgresql-pgvector.tar'),
            **({'backup':str(directory/'backups.oci.tar')} if 'backup' in images else {})},
            'digests':{name:images[name]['digest'] for name in ('console','postgres','backup') if name in images},
            'repositoryWrites':refresh_console,'runtimeImport':False}
