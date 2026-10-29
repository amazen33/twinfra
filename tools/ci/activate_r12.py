"""Activate only the owner's exact R12 batch; never renew or edit its rows."""
import argparse
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess

import supply_chain as sc
from r12_exceptions import ROOT, read, save, documentation

APPROVED_COMMIT='86d43189972f8cb8248ce518a1ccabc09187b41b'
PROPOSAL='security/proposals/r12-vulnerability-exceptions.json'
CARRY_LOG='security/licence-carry-log.json'
APPROVAL='security/security-wave-2026-10-approval.json'


def approved_batch(current, approved):
    if current!=approved:raise ValueError('R12 rows changed after the approved commit; new approval required')
    entries=deepcopy(current)
    if len(entries['exceptions'])!=420 or any(e['approvedBy']!='' for e in entries['exceptions']):
        raise ValueError('Unexpected R12 proposal or pre-existing row approvals')
    for entry in entries['exceptions']:entry['approvedBy']='amazen33'
    return entries


def require_original_or_approved(current, original, approved):
    if current!=original and current!=approved:
        raise ValueError('Current records changed outside the approved activation; refusing overwrite')


def activate(scan_path):
    decision=read(ROOT/APPROVAL)
    if decision['approvedBy']!='amazen33' or decision['approvedCommit']!=APPROVED_COMMIT or set(decision['decisions'])!={'O-2','O-4b','O-5'}:
        raise ValueError('Exact owner batch decision required')
    recorded=datetime.fromisoformat(decision['recordedAtUTC'].replace('Z','+00:00'))
    if recorded.utcoffset().total_seconds()!=0 or recorded>datetime.now(timezone.utc):
        raise ValueError('Invalid owner approval recording time')
    approved_on=recorded.date().isoformat()
    def frozen(path):return subprocess.check_output(['git','-C',str(ROOT),'show',APPROVED_COMMIT+':'+path])
    for path,key in ((PROPOSAL,'proposalSHA256'),(CARRY_LOG,'carryLogSHA256')):
        raw=frozen(path)
        if (ROOT/path).read_bytes()!=raw or hashlib.sha256(raw).hexdigest()!=decision[key]:
            raise ValueError('Approved batch/carry log bytes changed; new owner approval required')
    batch=approved_batch(read(ROOT/PROPOSAL),json.loads(frozen(PROPOSAL)))
    scan=read(scan_path)
    # A fresh scan may add risk: the approved batch cannot silently cover it.
    from r12_exceptions import identity
    keys={identity(e) for e in batch['exceptions']}
    if any(v['blocked'] and identity(v) not in keys for v in scan['findings']):
        raise ValueError('Scan has blockers outside the approved batch')
    for filename in sc.LOCKS:
        for name,entry in read(ROOT/filename)['images'].items():
            matching=[e for e in scan['inventory']['coverage'] if e['entry']==filename+':'+name]
            if len(matching)!=1 or matching[0]['pinned']!=sc.immutable(entry):
                raise ValueError('Scan coverage differs from the current locked images')
    state=sc.FirstSeenState(scan['firstSeen']);state.identities=scan['identityState']
    checked=sc.evaluate(scan,batch,read(scan_path.parent/'kev.json'),state,root=ROOT)
    if checked['status']!='passed':raise ValueError('Approved batch does not pass current scan evaluation')
    require_original_or_approved(read(ROOT/'security/vulnerability-exceptions.json'),
                                 json.loads(frozen('security/vulnerability-exceptions.json')),batch)
    original_policy=json.loads(frozen('security/licence-policy.json'))
    policy=deepcopy(original_policy)
    carried={event['to'] for event in read(ROOT/CARRY_LOG)['events']}
    if len(carried)!=3:raise ValueError('Exactly the three approved carries are required')
    for key in carried:
        policy['ladder']['legacy'][key].update(approvedBy='amazen33',approvalDate=approved_on)
    original_register=json.loads(frozen('security/licence-register.json'))
    register=deepcopy(original_register)
    images=read(ROOT/'security/security-wave-2026-10-images.json')['images']
    for name in ('argocd','keycloak'):
        key='oci-image|'+images[name]['after'].replace('@','|')
        entry=next(e for e in register['components'] if e['id']==key)
        grade=entry['enterpriseGrade']
        if any(v['result']!='pass' for k,v in grade['criteria'].items() if k!='supplyChain'):
            raise ValueError('A separate enterprise-grade criterion is not verified')
        grade['status']='verified'
        grade['criteria']['supplyChain']={'result':'pass','date':approved_on,'evidence':decision['evidence']}
    require_original_or_approved(read(ROOT/'security/licence-policy.json'),original_policy,policy)
    require_original_or_approved(read(ROOT/'security/licence-register.json'),original_register,register)
    review=read(ROOT/'security/security-wave-2026-10-review.json')
    review['ownerApproval']='Approved'
    review['approvalRecord']=APPROVAL
    review['activeLocalEvaluation']={'status':'passed','blocking':0,'scanRun':decision['scanRun'],
        'scanReportSHA256':hashlib.sha256(scan_path.read_bytes()).hexdigest(),
        'scope':'Local re-evaluation of the complete final PR scan with the owner-approved exact batch; CI rerun and live staging separate'}
    carries=read(ROOT/'security/security-wave-2026-10-carries.json')
    carries.update(ownerBatchApproval='Approved',approvedBy='amazen33',ownerDecisionDate=decision['ownerDecisionDate'],approvalRecord=APPROVAL)
    save(ROOT/'security/vulnerability-exceptions.json',batch)
    save(ROOT/'security/licence-policy.json',policy)
    save(ROOT/'security/licence-register.json',register)
    save(ROOT/'security/security-wave-2026-10-review.json',review)
    save(ROOT/'security/security-wave-2026-10-carries.json',carries)
    documentation(review,read(ROOT/PROPOSAL))
    print('Activated exact owner-approved R12 batch: 420 rows, three original-date carries; local scan re-evaluation passed. Staging remains Pending.')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--scan-report',type=Path,required=True)
    args=parser.parse_args()
    activate(args.scan_report.resolve())
