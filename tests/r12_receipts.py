"""Bound the R12 delta before projecting frozen pre-R12 historical receipts."""
import copy
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
BASE = '0d950075a8bf43358d9fd406b80b67d657f804e1'
sys.path.insert(0, str(ROOT/'tools/ci'))


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
