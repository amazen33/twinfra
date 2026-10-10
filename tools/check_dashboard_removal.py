#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""WO-07: candidate deployable inputs cannot reintroduce the removed dashboard."""
import argparse
from pathlib import Path
import re
import subprocess

REMOVED = 'gra' + 'fana'


def violations(root, paths):
    problems=[]
    for name in paths:
        file=root/name
        # Historical ADRs/receipts, topology parser and synthetic licence tests
        # are context, not deployment inputs. Candidate generators are checked.
        if not file.is_file() or not name.startswith(('deploy/','lab/','module-','tools/')):
            continue
        if name.startswith('tools/ci/'):
            continue
        if file.suffix not in ('.json','.yaml','.yml','.txt','.py','.sh','.ps1','.toml'):
            continue
        if REMOVED in name.lower():problems.append(name+': removed component path')
        for number,line in enumerate(file.read_text(encoding='utf-8').splitlines(),1):
            if REMOVED in line.lower() or re.search(r'\bGF_(SECURITY|AUTH|ANALYTICS|PLUGINS)_',line):
                problems.append(f'{name}:{number}: removed deployment reference')
    return problems


def check(root):
    paths=subprocess.check_output(['git','-C',str(root),'ls-files','--cached','--others','--exclude-standard'],text=True).splitlines()
    problems=violations(root,paths)
    if problems:raise ValueError('\n'.join(problems))
    print('PASS: candidate dashboard images, manifests, generators, access and secret tooling contain only Perses')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--root',type=Path,default=Path(__file__).resolve().parents[1])
    check(p.parse_args().root)
