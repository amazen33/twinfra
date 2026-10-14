#!/usr/bin/env python3
"""WO-34 Python base licence refresh; preserve the original evidence deadline."""
import copy
import json
from pathlib import Path
import sys
import urllib.request

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools/ci'))
from licence_inventory import enumerate_inputs


def main():
    observed,_=enumerate_inputs(ROOT)
    register_path=ROOT/'security/licence-register.json'
    register=json.loads(register_path.read_text())
    baseline_path=ROOT/'security/licence-baseline.json'
    baseline=json.loads(baseline_path.read_text())
    key='oci-image|docker.io/library/python|'+json.loads((ROOT/'console/image.lock.json').read_text())['base'].split('@')[1]
    if key not in observed:raise ValueError('Generated Python pin is not inventoried')
    entries={entry['id']:entry for entry in register['components']}
    if key not in entries:
        before=next(e for e in register['components'] if e['ecosystem']=='oci-image' and e['name']=='docker.io/library/python' and 'console/Dockerfile' in e['locations'])
        source='https://raw.githubusercontent.com/python/cpython/v3.14.8/LICENSE'
        with urllib.request.urlopen(source,timeout=60) as response:licence=response.read()
        if b'PYTHON SOFTWARE FOUNDATION LICENSE' not in licence:raise ValueError('Python licence source could not be verified')
        entry=copy.deepcopy(before)
        entry.update(id=key,version=key.split('|')[-1],locations=observed[key]['locations'],integrities=[key.split('|')[-1]],
                     licenceSource=source,verifiedOn='2026-10-14',recordedOn='2026-10-14')
        register['components'].append(entry)
        # The known distribution-image evidence gap retains its owner and original
        # deadline; this is not a claim that the new SBOM has been legally reviewed.
        gap=copy.deepcopy(next(f for f in baseline['findings'] if f['id']=='image-sbom:'+before['id']))
        gap.update(id='image-sbom:'+key,component=key)
        baseline['findings'].append(gap)
    for entry in register['components']:
        if entry['id'] in observed and entry['name']=='docker.io/library/python':entry['locations']=observed[entry['id']]['locations']
    register['components'].sort(key=lambda e:e['id'])
    register_path.write_text(json.dumps(register,indent=2)+'\n',encoding='utf-8',newline='\n')
    baseline_path.write_text(json.dumps(baseline,indent=2)+'\n',encoding='utf-8',newline='\n')
    print('PASS: Python licence verified; inherited image-SBOM deadline unchanged')


if __name__=='__main__':main()
