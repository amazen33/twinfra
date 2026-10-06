#!/usr/bin/env python3
"""Stage pinned Linux CI tools; network use requires the explicit --download option."""
import argparse
import hashlib
import io
import json
from pathlib import Path
import tarfile
import urllib.request

ROOT=Path(__file__).resolve().parents[1]
BINARIES={'buildkit-v0.33.1.linux-amd64.tar.gz':('bin/buildctl','buildctl'),
          'kubeconform-linux-amd64.tar.gz':('kubeconform','kubeconform'),
          'helm-v3.22.0-linux-amd64.tar.gz':('linux-amd64/helm','helm'),
          'prometheus-3.15.0.linux-amd64.tar.gz':('prometheus-3.15.0.linux-amd64/promtool','promtool')}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--download',action='store_true');parser.add_argument('--cache',type=Path,default=ROOT/'.tools/module-3-toolchain')
    parser.add_argument('--destination',type=Path,default=ROOT/'.build/module-3-toolchain')
    args=parser.parse_args(); lock=json.loads((ROOT/'module-3/toolchain.lock.json').read_text())
    args.cache.mkdir(parents=True,exist_ok=True);(args.destination/'bin').mkdir(parents=True,exist_ok=True)
    for item in lock['artifacts']:
        cached=args.cache/item['name']
        if not cached.exists():
            if not args.download: raise ValueError('Missing offline tool archive: '+item['name'])
            data=urllib.request.urlopen(item['url'],timeout=180).read()
            if hashlib.sha256(data).hexdigest()!=item['sha256']: raise ValueError('Upstream checksum mismatch')
            cached.write_bytes(data)
        data=cached.read_bytes()
        if hashlib.sha256(data).hexdigest()!=item['sha256']: raise ValueError('Cached tool checksum mismatch: '+item['name'])
        member,name=BINARIES[item['name']]
        with tarfile.open(fileobj=io.BytesIO(data),mode='r:gz') as archive:
            entry=archive.getmember(member)
            if not entry.isfile(): raise ValueError('Tool archive member must be a regular file')
            output=args.destination/'bin'/name
            output.write_bytes(archive.extractfile(entry).read());output.chmod(0o755)
    print(str(len(lock['artifacts']))+' pinned Linux tools staged and checksum verified')


if __name__=='__main__': main()
