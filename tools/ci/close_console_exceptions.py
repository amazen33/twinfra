#!/usr/bin/env python3
"""WO-34: close replaced console-base exceptions only with complete scan evidence."""
import argparse
import json
from pathlib import Path
import re

ROOT=Path(__file__).resolve().parents[2]


def close(comparison,run_url):
    if not re.fullmatch(r'https://github\.com/amazen33/twinfra/actions/runs/[0-9]+',run_url):
        raise ValueError('Verified Twinfra CI run URL required')
    rows={v['name']:v for v in comparison['images']}
    receipt=json.loads((ROOT/'console/image.lock.json').read_text())
    for name in ('console-after','python-after'):
        if rows[name]['coverage']!='complete-oci-archive-linux-amd64' or rows[name]['counts']['CriticalWithFix']:
            raise ValueError('Complete zero fixable Critical evidence required')
    if rows['console-after']['reference']!=receipt['canonical'] or rows['python-after']['reference']!=receipt['base']:
        raise ValueError('Scan pins do not match the candidate receipt')
    old=rows['python-before']['reference'].split('@')[1]
    target='docker.io/library/python@'+old
    ledger=ROOT/'security/vulnerability-exceptions.json'
    value=json.loads(ledger.read_text());removed=[];kept=[]
    for entry in value['exceptions']:
        if entry['target']!=target:
            kept.append(entry);continue
        before=rows['python-before']['findings']
        if not any(v['package']==entry['package'] and v['version']==entry['version'] and entry['vulnerability'] in v['aliases'] for v in before):
            raise ValueError('Exception lacks exact before-scan evidence')
        if any(v['package']==entry['package'] and entry['vulnerability'] in v['aliases'] for v in rows['python-after']['findings']):
            raise ValueError('Exception is still affected after refresh')
        removed.append(entry)
    value['exceptions']=kept
    ledger.write_text(json.dumps(value,indent=2)+'\n',encoding='utf-8',newline='\n')
    evidence=dict(date=comparison['date'],scope='Static complete image comparison; no live acceptance',
                  result='Passed',liveAcceptance='Pending',testerSignOff='Pending',runURL=run_url,
                  consoleDigest=receipt['digest'],releaseEvidence=receipt['releaseEvidence'],
                  database=comparison['database'],images=[{k:v for k,v in row.items() if k!='findings'} for row in comparison['images']],
                  closedExceptions=removed,remainingExceptions=len(kept),
                  closureReason='Console replaced the affected immutable base; retained historical/reference sources are not declared patched.')
    path=ROOT/'docs/acceptance/wo34-p1-2026-10-14.json'
    path.write_text(json.dumps(evidence,indent=2)+'\n',encoding='utf-8',newline='\n')
    print('Closed '+str(len(removed))+' replaced console-base exceptions; remaining '+str(len(kept)))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--comparison',type=Path,required=True)
    p.add_argument('--run-url',required=True);args=p.parse_args()
    close(json.loads(args.comparison.read_text()),args.run_url)
