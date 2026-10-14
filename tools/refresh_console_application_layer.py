#!/usr/bin/env python3
"""Pin existing compressed layer bytes after verifying the approved image digest."""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
from platform_pg_image import Export


def refresh(path):
    receipt=json.loads((ROOT/'console/image.lock.json').read_text())
    source=Export(path)
    try:
        if source.root_digest!=receipt['digest']:raise ValueError('Application layer is not from the approved image')
        desc=source.manifest['layers'][-1];raw=source.blob(desc);plain=gzip.decompress(raw)
        config=json.loads(source.blob(source.manifest['config']))
        digest=hashlib.sha256(plain).hexdigest()
        if 'sha256:'+digest!=config['rootfs']['diff_ids'][-1]:raise ValueError('Application diff-id differs')
        (ROOT/'console/application-layer.tar.gz').write_bytes(raw)
        (ROOT/'console/application-layer.lock.json').write_text(json.dumps(dict(
            archiveSHA256=hashlib.sha256(raw).hexdigest(),uncompressedSHA256=digest),indent=2)+'\n',encoding='utf-8',newline='\n')
    finally:source.archive.close()


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--image',type=Path,required=True)
    refresh(p.parse_args().image)
