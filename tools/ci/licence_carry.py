"""ADR-0054 Amendment 1: security fixes retain the original backfill deadline."""
from datetime import date
import hashlib
import json
import re
import subprocess
from urllib.parse import urlparse


def same_line(name, before, after):
    def version(value):
        match=re.fullmatch(r'v?(\d+)\.(\d+)\.(\d+)',value)
        if not match:raise ValueError('Carry requires explicit release versions')
        return tuple(map(int,match.groups()))
    old,new=version(before),version(after)
    if new<=old or (name!='certifi' and new[:2]!=old[:2]):
        raise ValueError('Carry cannot admit a major/minor upgrade or downgrade')


def validate_log(policy, log, originals):
    """Follow every carry from the immutable original approval, including reruns."""
    from licence_ladder import fingerprint
    states={key:dict(record=entry,originalDue=entry['enterpriseGrade']['due'])
            for key,entry in originals.items() if entry.get('enterpriseGrade',{}).get('status')=='legacy-pending'}
    events=log['events']
    if log.get('version')!=1 or not isinstance(events,list):raise ValueError('Invalid carry log')
    for event in events:
        before=states.pop(event['from'],None)
        if before is None or event['to'] in states:raise ValueError('Carry predecessor missing or duplicate')
        old,new=before['record'],event['record']
        for key in ('name','ecosystem','spdx','class','tier'):
            if old.get(key)!=new.get(key):raise ValueError('Carry cannot change component, licence, class or tier')
        for term in re.findall(r'[A-Za-z0-9][A-Za-z0-9.+:-]*',new['spdx']):
            import fnmatch
            if any(fnmatch.fnmatchcase(term,p) for p in policy['ladder']['never']):
                raise ValueError('Never licence cannot use carry-forward')
        same_line(new['name'],event['fromVersion'],event['toVersion'])
        for record,version in ((old,event['fromVersion']),(new,event['toVersion'])):
            if record['ecosystem']=='oci-image':
                if not re.search(r'/v?'+re.escape(version)+r'/',record['licenceSource']):
                    raise ValueError('Image release must match exact-version primary licence')
            elif record['version']!=version:
                raise ValueError('Carry release version differs from component identity')
        grade=new['enterpriseGrade']
        if grade!={'status':'legacy-pending','due':before['originalDue']} or event['originalDue']!=before['originalDue']:
            raise ValueError('Carry must retain the original due date')
        if event['to']!=new['id'] or not event.get('advisoriesCleared') or event.get('netImprovement') is not True:
            raise ValueError('Carry requires a security fix and net-improvement evidence')
        if not re.fullmatch(r'[a-f0-9]{64}',event.get('licenceSHA256','')):
            raise ValueError('Carry requires primary licence checksum')
        url=urlparse(new['licenceSource'])
        if url.scheme!='https' or not url.netloc or not event.get('evidence'):
            raise ValueError('Carry requires primary licence and scan evidence')
        states[new['id']]=dict(record=new,originalDue=before['originalDue'])
    affected={event['from'] for event in events}|{event['to'] for event in events}
    legacy=policy['ladder']['legacy']
    for key in affected:
        if key not in states:
            if key in legacy:raise ValueError('Carry predecessor must be removed from the legacy map')
            continue
        state=states[key];record=legacy.get(key)
        event=next(e for e in reversed(events) if e['to']==key)
        expected={'sha256':fingerprint(state['record']),'tier':state['record']['tier'],
                  'due':state['originalDue'],'carriedFrom':event['from'],
                  'advisoriesCleared':event['advisoriesCleared']}
        if not record or any(record.get(k)!=v for k,v in expected.items()):
            raise ValueError('Carry map differs from its immutable log')
    return states


def check(root, policy):
    """Offline anchor and append-only history checks; old revisions have no log."""
    ladder=policy['ladder'];filename=ladder.get('carryLog')
    if not filename:
        if any('carriedFrom' in e for e in ladder['legacy'].values()):raise ValueError('Carry log missing')
        return
    if filename!='security/licence-carry-log.json':raise ValueError('Unexpected carry log path')
    log=json.loads((root/filename).read_text(encoding='utf-8'))
    anchor=log['anchorCommit']
    if not re.fullmatch(r'[a-f0-9]{40}',anchor):raise ValueError('Immutable carry anchor required')
    def git(*args):return subprocess.check_output(['git','-C',str(root),*args],text=True,encoding='utf-8').strip()
    original=json.loads(git('show',anchor+':security/licence-register.json'))
    original_policy=json.loads(git('show',anchor+':security/licence-policy.json'))
    if hashlib.sha256(json.dumps(original_policy['ladder']['legacy'],sort_keys=True).encode()).hexdigest()!=log['anchorLegacySHA256']:
        raise ValueError('Carry original approval anchor differs')
    # Any committed previous log must be a prefix. Approval is recorded in the
    # current map; proposed carry events themselves are immutable.
    for revision in git('log','--format=%H','--',filename).splitlines():
        prior=json.loads(git('show',revision+':'+filename))
        if prior['anchorCommit']!=anchor or prior['events']!=log['events'][:len(prior['events'])]:
            raise ValueError('Carry log is append-only')
    validate_log(policy,log,{e['id']:e for e in original['components']})


def approval(legacy, today):
    if 'carriedFrom' not in legacy:return
    if legacy.get('approvedBy')!='amazen33':raise ValueError('Security carry-forward awaits owner batch approval')
    approved=date.fromisoformat(legacy.get('approvalDate',''))
    if approved>today:raise ValueError('Carry approval date is in the future')
