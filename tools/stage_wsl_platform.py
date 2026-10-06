#!/usr/bin/env python3
"""Connected, version/digest-pinned staging; workload pulls stay private-only."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = 'registry.vcloud.example.com/'


def stage(cache):
    cache.mkdir(parents=True, exist_ok=True)
    def one(source):
        subprocess.run(['ctr','-n','k8s.io','images','pull','--local','--platform','linux/amd64',source],
                       check=True, stdout=subprocess.DEVNULL)
        output=subprocess.check_output(['ctr','-n','k8s.io','images','ls',f'name=={source}'],text=True)
        digest=output.splitlines()[1].split()[2]
        target=REGISTRY+source
        subprocess.run(['ctr','-n','k8s.io','images','tag','--force',source,target],check=True,stdout=subprocess.DEVNULL)
        repo=target.split('@')[0].rsplit(':',1)[0] if ':' in target.split('@')[0].rsplit('/',1)[-1] else target.split('@')[0]
        alias=repo+'@'+digest
        if alias!=target:
            subprocess.run(['ctr','-n','k8s.io','images','tag','--force',source,alias],check=True,stdout=subprocess.DEVNULL)
        print('Staged '+target,flush=True)
        return {'source':source,'canonical':target,'digest':digest}
    sources=(ROOT/'lab/wsl/platform-images.txt').read_text().splitlines()
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(one,sources))
    (cache/'images.json').write_text(json.dumps(results,indent=2)+'\n')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--cache',type=Path,required=True)
    stage(parser.parse_args().cache)
