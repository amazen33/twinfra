"""Bound the R12 delta before projecting frozen pre-R12 historical receipts."""
import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
BASE = '0d950075a8bf43358d9fd406b80b67d657f804e1'
sys.path.insert(0, str(ROOT/'tools/ci'))


def old(path):
    return subprocess.check_output(['git', '-C', str(ROOT), 'show', BASE+':'+path])


def approved_content(root=ROOT):
    """WO-40 10g: approval survives squash merges through committed hashes."""
    record=json.loads((root/'security/security-wave-2026-10-approval.json').read_bytes())
    content=[]
    for path,key in (('security/proposals/r12-vulnerability-exceptions.json','proposalSHA256'),
                     ('security/licence-carry-log.json','carryLogSHA256')):
        raw=(root/path).read_bytes()
        if hashlib.sha256(raw).hexdigest()!=record[key]:
            raise AssertionError('Approved R12 content hash differs: '+path)
        content.append(json.loads(raw))
    proposal,log=content
    rows=proposal['exceptions'];events=log['events']
    groups={severity:[e for e in rows if e['severity']==severity]
            for severity in ('High','Critical','Medium')}
    if sum(map(len,groups.values()))!=len(rows):
        raise AssertionError('Unexpected R12 severity')
    def expiry(severity):
        values={e['expires'] for e in groups[severity]}
        if len(values)!=1:raise AssertionError('R12 expiry scope differs: '+severity)
        return values.pop()
    scope={'vulnerabilityRows':len(rows),'High':len(groups['High']),'HighExpires':expiry('High'),
           'Critical':len(groups['Critical']),'CriticalExpires':expiry('Critical'),
           'kevRows':len(groups['Medium']),'kevExpires':expiry('Medium'),'carries':len(events),
           'dueDatesUnchanged':all(e['record']['enterpriseGrade']['due']==e['originalDue'] for e in events)}
    if scope!=record['approvedScope'] or scope['dueDatesUnchanged'] is not True:
        raise AssertionError('Approved R12 scope differs')
    return record,proposal,log


def current_exceptions(root=ROOT):
    """Preserve R12/O-11 anchors and require O-12 for the three appended risks."""
    from r12_exceptions import amendment_11a_batch, amendment_11c_batch
    original,proposal,_=approved_content(root)
    record=json.loads((root/'security/wo40-amendment-11a-approval.json').read_bytes())
    raw=(root/'security/proposals/wo40-amendment-11a-kev.json').read_bytes()
    if (hashlib.sha256(raw).hexdigest()!=record['proposalSHA256']
            or record['r12ProposalSHA256']!=original['proposalSHA256']):
        raise AssertionError('Amendment 11a approved content hash differs')
    expected=amendment_11a_batch(proposal,json.loads(raw),record)
    amendment_paths=(root/'security/wo40-amendment-11c-approval.json',
                     root/'security/proposals/wo40-amendment-11c.json')
    anchor=record
    if any(path.exists() for path in amendment_paths):
        if not all(path.is_file() for path in amendment_paths):
            raise AssertionError('Incomplete Amendment 11c approval bundle')
        amended=json.loads(amendment_paths[0].read_bytes())
        proposed=amendment_paths[1].read_bytes()
        if hashlib.sha256(proposed).hexdigest()!=amended['proposalSHA256']:
            raise AssertionError('Amendment 11c approved content hash differs')
        expected=amendment_11c_batch(expected,json.loads(proposed),amended,record)
        anchor=amended
    active=(root/'security/vulnerability-exceptions.json').read_bytes()
    key='approvedRegistrySHA256' if anchor['approvedBy'] else 'proposedRegistrySHA256'
    if hashlib.sha256(active).hexdigest()!=anchor[key] or json.loads(active)!=expected:
        raise AssertionError('Active registry differs from Amendment 11a/11c content/approval')
    return record,expected


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
    current_exceptions()
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
