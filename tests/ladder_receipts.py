"""Project only WO-09a's exact metadata additions for historical receipts."""
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
BASE = '09d56f3'
sys.path.insert(0, str(ROOT / 'tools/ci'))
from licence_ladder import fingerprint, runtime


def old(path):
    return subprocess.check_output(['git', '-C', str(ROOT), 'show', BASE+':'+path])


def current_document(path):
    """Project the separately bounded R12 patch before the older WO-09a receipt."""
    current = json.loads((ROOT/path).read_text(encoding='utf-8'))
    marker = ROOT/'security/security-wave-2026-10-images.json'
    if not marker.is_file():
        return current
    from r12_receipts import assert_current
    anchor = assert_current()
    return json.loads(subprocess.check_output(['git', '-C', str(ROOT), 'show', anchor+':'+path]))


def policy():
    path='security/licence-policy.json'
    before=json.loads(old(path));current=current_document(path)
    ladder=current.pop('ladder')
    tiers={'1':[x for x in before['permitted'] if x!='Apache-2.0'], '2':['Apache-2.0'],
           '3':['MPL-2.0','LGPL-*','EPL-2.0'], '4':['GPL-*']}
    legacy={}
    import re
    for entry in json.loads(old('security/licence-register.json'))['components']:
        if not runtime(entry):continue
        spdx=entry['spdx']
        tier=4 if re.search(r'(?<!L)GPL-',spdx) else 3 if any(v in spdx for v in ('MPL-','LGPL-','EPL-')) else 2 if 'Apache-2.0' in spdx else 1
        legacy[entry['id']]={'sha256':fingerprint(entry), 'tier':tier,
                            'due':'2027-01-14' if tier>=3 else '2027-04-16'}
    expected={'effectiveOn':'2026-10-16', 'decision':'docs/adr/0054-licence-ladder-and-enterprise-grade-gate.md',
        'tiers':tiers, 'never':['AGPL-*','SSPL-*','BUSL-*','Elastic-*','Commons-Clause*','LicenseRef-*','account-gated','proprietary','source-available'], 'legacy':legacy}
    if ladder!=expected:raise AssertionError('ADR-0054 legacy identities, tiers or dates changed')
    if current.pop('decision')!='0054':raise AssertionError('Unexpected licence decision')
    current['decision']=before['decision']
    if current!=before:raise AssertionError('Existing licence permissions changed')
    return old(path)


def register():
    path='security/licence-register.json';before=json.loads(old(path))
    current=current_document(path)
    original={e['id']:e for e in before['components']};entries={e['id']:e for e in current['components']}
    if entries.keys()!=original.keys():raise AssertionError('WO-09a cannot add/remove runtime components')
    policy()
    legacy=current_document('security/licence-policy.json')['ladder']['legacy']
    for key,entry in original.items():
        actual=dict(entries[key])
        if runtime(entry):
            record=legacy[key]
            if actual.pop('tier')!=record['tier']:raise AssertionError('Changed legacy tier')
            if actual.pop('enterpriseGrade')!={'status':'legacy-pending','due':record['due']}:
                raise AssertionError('Changed legacy deadline')
        if actual!=entry:raise AssertionError('Changed pre-existing runtime approval: '+key)
    return old(path)
