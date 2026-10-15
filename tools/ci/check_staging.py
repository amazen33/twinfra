#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Lightweight WO-36 PR-body attestation gate; no image pull/build or host IO."""
import argparse
from datetime import date
import json
from pathlib import Path
import re
import subprocess
import yaml

LOCKS={'deploy/common/images.lock.json','deploy/common/bootstrap-images.lock.json'}
FIELDS={'image','imageName','imageRepository','imageTag','newName','newTag','digest','sandbox_image'}


def references(raw):
    result=[]
    def visit(item):
        if isinstance(item,dict):
            for key,value in item.items():
                if key in FIELDS:result.append((key,json.dumps(value,sort_keys=True)))
                elif key=='value' and 'IMAGE' in str(item.get('name','')).upper():result.append((item['name'],str(value)))
                else:visit(value)
        elif isinstance(item,list):
            for value in item:visit(value)
        elif isinstance(item,str):
            # Embedded seed / ConfigMap YAML, shell image args and containerd
            # sandbox references are still deployable references.
            for line in item.splitlines():
                if re.search(r'\b(?:image|imageName|imageRepository|imageTag|sandbox_image)\s*[:=]',line):result.append(('embedded',line.strip()))
    for doc in yaml.safe_load_all(raw):visit(doc)
    return sorted(result)


def required(changes):
    return [name for name,(old,new) in changes.items() if name in LOCKS or
            name.startswith('deploy/environments/dev/') and references(old)!=references(new)]


def attest(body):
    match=re.search(r'^Staging: PASS \(stage-images --check, (\d{4}-\d{2}-\d{2})\)$',body or '',re.M)
    if not match:return False
    try:date.fromisoformat(match[1]);return True
    except ValueError:return False


def git(*args):return subprocess.check_output(['git',*args])


def check(event):
    pr=event['pull_request'];base=pr['base']['sha'];head=pr['head']['sha']
    if not all(re.fullmatch(r'[a-f0-9]{40}',ref) for ref in (base,head)):raise ValueError('Invalid PR commit identity')
    names=git('diff','--name-only','-z',base,head).decode().split('\0');changes={}
    for name in names:
        if name not in LOCKS and not (name.startswith('deploy/environments/dev/') and Path(name).suffix in ('.yaml','.yml','.json') or name.startswith('deploy/environments/dev/') and Path(name).name=='user-data'):continue
        values=[]
        for ref in (base,head):
            exists=subprocess.run(['git','cat-file','-e',ref+':'+name],capture_output=True).returncode==0
            values.append(git('show',ref+':'+name).decode() if exists else '')
        changes[name]=values
    selected=required(changes);passed=not selected or attest(pr.get('body'))
    return {'status':'passed' if passed else 'failed','imageChanges':selected,
            'message':'Owner staging attestation present' if selected and passed else 'No image references changed' if passed else
            'Stage this PR branch, run stage-images --check, then add: Staging: PASS (stage-images --check, YYYY-MM-DD)'}


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--event',type=Path,required=True);args=parser.parse_args()
    try:report=check(json.loads(args.event.read_text(encoding='utf-8')))
    except (ValueError,KeyError,subprocess.CalledProcessError,yaml.YAMLError):
        report={'status':'failed','message':'Cannot validate PR image changes; inspect event/ref/schema inputs'}
    print(json.dumps(report,indent=2));return int(report['status']!='passed')


if __name__=='__main__':raise SystemExit(main())
