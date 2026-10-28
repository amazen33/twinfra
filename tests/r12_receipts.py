"""Bound the R12 delta before projecting frozen pre-R12 historical receipts."""
import copy
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
BASE = '0d950075a8bf43358d9fd406b80b67d657f804e1'
sys.path.insert(0, str(ROOT/'tools/ci'))


def old(path):
    return subprocess.check_output(['git', '-C', str(ROOT), 'show', BASE+':'+path])


def assert_images(current=None):
    from security_wave_2026_10 import CASES
    original=json.loads(old('deploy/common/images.lock.json'))
    actual=current if current is not None else json.loads((ROOT/'deploy/common/images.lock.json').read_text(encoding='utf-8'))
    expected=copy.deepcopy(original)
    allowed={'source','release','digest','canonical','releaseSource','releasePublishedAt','verifiedOn','licenceSHA256'}
    for component,case in [('argocd','argocd355'),('ministack','ministack1533'),('keycloak','keycloak2681')]:
        _,release,ref=CASES[case];entry=actual['images'][component]
        if entry['source']!=ref or entry['digest']!=ref.split('@')[1] or entry['canonical']!='registry.twinfra.example.com/'+ref:
            raise AssertionError('R12 candidate digest differs from the approved comparison')
        if not entry['release'].endswith(':'+('v' if component=='argocd' else '')+release):
            raise AssertionError('R12 release differs')
        fields=allowed|({'publishedAt','publicationSource','digestSource','expedite'} if component=='ministack' else set())
        if not set(entry)-set(original['images'][component])<=fields:
            raise AssertionError('R12 added an unrelated pin property')
        for field in fields:
            if field in entry:expected['images'][component][field]=entry[field]
    if actual!=expected:raise AssertionError('R12 changed an unrelated image or pin property')
    return original,actual


def receipt(path):
    """Verify exact image substitutions, then expose the frozen original receipt."""
    original,current=assert_images()
    raw=old(path);expected=raw.decode()
    actual=(ROOT/path).read_text(encoding='utf-8')
    if path=='deploy/common/images.lock.json':
        return raw
    if path=='lab/wsl/console/artifacts.lock.json':
        value=json.loads(raw);entry=copy.deepcopy(current['images']['ministack'])
        entry['canonical']='registry.vcloud.example.com/'+entry['source']
        value['images']['ministack']=entry
        if json.loads(actual)!=value:raise AssertionError('R12 changed unrelated retained WSL pins')
        return raw
    if path.startswith('lab/wsl/'):
        prior=json.loads(old('lab/wsl/console/artifacts.lock.json'))['images']['ministack']['canonical']
        replacement='registry.vcloud.example.com/'+current['images']['ministack']['source']
        expected=expected.replace(prior,replacement)
    else:
        for name in ('argocd','ministack','keycloak'):
            expected=expected.replace(original['images'][name]['canonical'],current['images'][name]['canonical'])
    if actual!=expected:raise AssertionError('R12 render differs beyond the three exact image substitutions: '+path)
    return raw


def assert_current():
    from licence_carry import check
    def old(path):
        return json.loads(subprocess.check_output(['git', '-C', str(ROOT), 'show', BASE+':'+path]))
    def read(path):
        return json.loads((ROOT/path).read_text(encoding='utf-8'))
    policy = read('security/licence-policy.json')
    check(ROOT, policy)
    expected = old('security/licence-policy.json')
    events = read('security/licence-carry-log.json')['events']
    if len(events) != 3:
        raise AssertionError('R12 must contain exactly three bounded security carries')
    records = {e['id']: e for e in read('security/licence-register.json')['components']}
    original = {e['id']: e for e in old('security/licence-register.json')['components']}
    removed, added = set(), set()
    for event in events:
        removed.add(event['from']);added.add(event['to'])
        if records[event['to']] != event['record']:
            raise AssertionError('R12 carry record differs from its append-only log')
        prior = expected['ladder']['legacy'].pop(event['from'])
        actual = policy['ladder']['legacy'][event['to']]
        if actual['due'] != prior['due'] or actual['tier'] != prior['tier']:
            raise AssertionError('R12 cannot move a legacy deadline or tier')
        expected['ladder']['legacy'][event['to']] = copy.deepcopy(actual)
    expected['ladder']['carryLog'] = 'security/licence-carry-log.json'
    if policy != expected:
        raise AssertionError('R12 changed permissions or an unrelated legacy approval')
    images = read('security/security-wave-2026-10-images.json')['images']
    if set(images) != {'argocd', 'keycloak', 'ministack'}:
        raise AssertionError('R12 promoted an unapproved image')
    for component in ('argocd', 'keycloak'):
        row = images[component]
        before = 'oci-image|' + row['before'].replace('@', '|')
        after = 'oci-image|' + row['after'].replace('@', '|')
        # Production and retained reference sources still use the old pin.
        # Their exact approvals remain byte-for-byte unchanged.
        added.add(after)
        for field in ('name', 'ecosystem', 'spdx', 'class', 'tier'):
            if original[before][field] != records[after][field]:
                raise AssertionError('R12 changed component classification')
    if records.keys() != (original.keys() - removed) | added:
        raise AssertionError('R12 added or removed an unrelated licence entry')
    for key in original.keys() - removed:
        if records[key] != original[key]:
            raise AssertionError('R12 changed an unrelated approval: ' + key)
    return BASE
