#!/usr/bin/env python3
"""WO-34: extract Go executable data and inspect it; never execute image code."""
import argparse
import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tarfile

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tools'))
from platform_oci import export_public
from platform_pg_image import Export


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--scanner',type=Path,required=True)
    parser.add_argument('--image',required=True)
    parser.add_argument('--path',required=True)
    parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args()
    pin=json.loads((ROOT/'tools/ci/toolchain.lock.json').read_text())['builds']['govulncheck']['binarySHA256']
    if not pin or hashlib.sha256(args.scanner.read_bytes()).hexdigest()!=pin:
        raise ValueError('govulncheck binary is not the reviewed pin')
    args.out.mkdir(parents=True,exist_ok=True)
    archive=args.out/'image.oci.tar';export_public(args.image,archive)
    source=Export(archive);content=None
    for layer in source.manifest['layers']:
        with tarfile.open(fileobj=io.BytesIO(source.blob(layer)),mode='r:*') as stream:
            for item in stream:
                if item.name.removeprefix('./').lstrip('/')==args.path.lstrip('/'):
                    if not item.isfile():raise ValueError('A regular executable is required')
                    content=stream.extractfile(item).read()
    source.archive.close()
    if not content or not content.startswith(b'\x7fELF'):raise ValueError('Pinned Linux executable not found')
    binary=args.out/'executable-data';binary.write_bytes(content);binary.chmod(0o400)
    result=subprocess.run([str(args.scanner.resolve()),'-mode=binary','-json',str(binary.resolve())],capture_output=True,text=True)
    (args.out/'govulncheck.jsonl').write_text(result.stdout)
    (args.out/'govulncheck.log').write_text(result.stderr)
    report={'image':args.image,'path':args.path,'binarySHA256':hashlib.sha256(content).hexdigest(),
            'scannerSHA256':pin,'exitCode':result.returncode,'imageCodeExecuted':False}
    (args.out/'summary.json').write_text(json.dumps(report,indent=2)+'\n')
    return result.returncode


if __name__=='__main__':raise SystemExit(main())
