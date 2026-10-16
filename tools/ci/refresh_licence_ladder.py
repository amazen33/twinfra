"""Reproduce the one-time, owner-approved WO-09a metadata migration. MIT."""
import argparse
import json
from pathlib import Path
import re
import subprocess
from licence_ladder import fingerprint, runtime

ROOT = Path(__file__).resolve().parents[2]
BASE = '09d56f3'


def outputs():
    def original(path):
        return json.loads(subprocess.check_output(['git','-C',str(ROOT),'show',BASE+':'+path]))
    policy=original('security/licence-policy.json')
    register=original('security/licence-register.json')
    tiers={'1':[x for x in policy['permitted'] if x!='Apache-2.0'], '2':['Apache-2.0'],
           '3':['MPL-2.0','LGPL-*','EPL-2.0'], '4':['GPL-*']}
    legacy={}
    for entry in register['components']:
        if not runtime(entry):continue
        spdx=entry['spdx']
        tier=4 if re.search(r'(?<!L)GPL-',spdx) else 3 if any(v in spdx for v in ('MPL-','LGPL-','EPL-')) else 2 if 'Apache-2.0' in spdx else 1
        deadline='2027-01-14' if tier>=3 else '2027-04-16'
        legacy[entry['id']]={'sha256':fingerprint(entry), 'tier':tier, 'due':deadline}
        entry.update(tier=tier, enterpriseGrade={'status':'legacy-pending','due':deadline})
    policy['decision']='0054'
    policy['ladder']={'effectiveOn':'2026-10-16', 'decision':'docs/adr/0054-licence-ladder-and-enterprise-grade-gate.md',
        'tiers':tiers,'never':['AGPL-*','SSPL-*','BUSL-*','Elastic-*','Commons-Clause*','LicenseRef-*','account-gated','proprietary','source-available'],'legacy':legacy}
    return {'security/licence-policy.json':policy, 'security/licence-register.json':register}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check',action='store_true')
    args=parser.parse_args()
    for path,value in outputs().items():
        target=ROOT/path
        actual=json.loads(target.read_text(encoding='utf-8'))
        if actual!=value:
            if args.check:raise ValueError('Licence ladder migration drift: '+path)
            # This generator is deliberately one-time: do not discard later
            # version changes, new approvals, or completed qualifications.
            before=json.loads(subprocess.check_output(['git','-C',str(ROOT),'show',BASE+':'+path]))
            if actual!=before:raise ValueError('Refusing to replace later licence work: '+path)
        if not args.check:target.write_text(json.dumps(value,indent=2)+'\n',encoding='utf-8',newline='\n')
    print('PASS: exact WO-09a tier/backfill metadata; pre-existing approvals unchanged')


if __name__=='__main__':main()
