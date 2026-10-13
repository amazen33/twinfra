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


def build_images(download_inputs=False):
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
        console_receipt=console.verify_receipt(console.build(base,console_path,wheels))
        exports=[]
        for path,pin in ((postgres,pg.BASE),(extension,pg.EXTENSION)):
            item=pg.Export(path);stack.callback(item.archive.close)
            if item.root_digest!=pin.split('@')[1]:raise ValueError('PostgreSQL input differs from the approved pin')
            exports.append(item)
        postgres_receipt=pg.build(*exports,postgres_path)
        expected=json.loads((ROOT/'deploy/common/postgresql-image.lock.json').read_text())
        if postgres_receipt!=expected:raise ValueError('PostgreSQL receipt differs; locks were not updated')
        for name,path,actual in (('console',console_path,console_receipt['digest']),
                                  ('postgres',postgres_path,postgres_receipt['manifestDigest'])):
            if actual!=images[name]['digest']:raise ValueError(name+' built digest differs from image lock')
            validate_archive(path,images[name]['digest'])
        # Close all input archives before replacement/TemporaryDirectory cleanup on Windows.
        stack.close()
        console_path.replace(directory/'console.oci.tar')
        postgres_path.replace(directory/'postgresql-pgvector.tar')
    return {'status':'passed','archives':{'console':str(directory/'console.oci.tar'),
            'postgres':str(directory/'postgresql-pgvector.tar')},
            'digests':{name:images[name]['digest'] for name in ('console','postgres')},
            'repositoryWrites':False,'runtimeImport':False}
