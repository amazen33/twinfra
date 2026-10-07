#!/usr/bin/env python3
"""Connected staging of locked endpoint images into the owned CRI cache.

First --freeze resolves explicit release tags to digests. Subsequent invocations
pull only those digests, require exact equality, and create private registry
aliases without enabling public fallback in containerd.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import re
import subprocess

ROOT=Path(__file__).resolve().parents[1]
LOCK=ROOT/'lab/wsl/endpoints/artifacts.lock.json'


def stage(freeze=False):
    if not Path('/var/lib/vcloud-wsl/owner.json').is_file():raise ValueError('Owned WSL lab required for CRI staging')
    lock=json.loads(LOCK.read_text())
    if not freeze and not lock.get('images'):raise ValueError('Missing immutable image lock')
    def one(item):
        key,source=item
        if 'latest' in source:raise ValueError('Floating image forbidden')
        pinned=source if freeze else lock['images'][key]['source']
        subprocess.run(['ctr','-n','k8s.io','images','pull','--local','--platform','linux/amd64',pinned],
                       check=True,stdout=subprocess.DEVNULL)
        output=subprocess.check_output(['ctr','-n','k8s.io','images','ls',f'name=={pinned}'],text=True)
        digest=output.splitlines()[1].split()[2]
        if not re.fullmatch(r'sha256:[a-f0-9]{64}',digest):raise ValueError('Invalid OCI digest')
        if '@' in pinned and pinned.rsplit('@',1)[1]!=digest:raise ValueError('Digest mismatch')
        repo=source.split('@')[0]
        if ':' in repo.rsplit('/',1)[-1]:repo=repo.rsplit(':',1)[0]
        source_digest=repo+'@'+digest
        canonical='registry.vcloud.example.com/'+source_digest
        subprocess.run(['ctr','-n','k8s.io','images','tag','--force',pinned,canonical],check=True,stdout=subprocess.DEVNULL)
        print('Staged '+key+' '+digest,flush=True)
        return key,{'source':source_digest,'canonical':canonical,'digest':digest}
    with ThreadPoolExecutor(max_workers=2) as pool:images=dict(pool.map(one,lock['imageSources'].items()))
    if freeze:
        lock['images']=images
        LOCK.write_text(json.dumps(lock,indent=2)+'\n')
    elif images!=lock['images']:raise ValueError('Staged images differ from lock')
    print('PASS: '+str(len(images))+' immutable images cached')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--freeze',action='store_true')
    stage(parser.parse_args().freeze)
