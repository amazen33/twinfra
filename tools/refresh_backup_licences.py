#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""WO-09 deterministic licence records; unresolved admission stays visibly pending.

Does not manufacture a vulnerability approval, SBOM baseline or enterprise pass.
Exact legacy records are retained; only boto3's requested requalification changes.
"""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent/'ci'))
from licence_inventory import enumerate_inputs
from check_licences import observed_integrities
from licence_ladder import CRITERIA

ROOT=Path(__file__).resolve().parents[1]
DATE='2026-10-16'
NOTICE='security/licences/backups/NOTICE.md'
PLUGIN='https://github.com/cloudnative-pg/plugin-barman-cloud'


def grade(project, pending=()):
    urls={
        'plugin':[PLUGIN+'/releases/tag/v0.15.1','https://www.cncf.io/projects/cloudnativepg/',
                  PLUGIN+'/releases',PLUGIN+'/security/policy',PLUGIN+'/releases/tag/v0.15.1',
                  'https://cloudnative-pg.io/plugin-barman-cloud/docs/intro/'],
        'barman':['https://pgbarman.org/','https://pgbarman.org/support/',
                  'https://github.com/EnterpriseDB/barman/releases','https://github.com/EnterpriseDB/barman/security/policy',
                  PLUGIN+'/releases/tag/v0.15.1','https://docs.pgbarman.org/release/2.19/'],
        'psycopg2':['https://www.psycopg.org/docs/','https://www.psycopg.org/',
                  'https://www.psycopg.org/docs/news.html','https://github.com/psycopg/psycopg2/security/policy',
                  PLUGIN+'/releases/tag/v0.15.1','https://www.psycopg.org/'],
        'openssl':['https://openssl-library.org/source/','https://openssl-foundation.org/',
                   'https://openssl-library.org/policies/releasestrat/','https://openssl-library.org/policies/general/security-policy/',
                   'https://github.com/amazen33/twinfra/pull/55','https://openssl-library.org/'],
        'boto3':['https://boto3.amazonaws.com/v1/documentation/api/latest/index.html','https://aws.amazon.com/sdk-for-python/',
                 'https://github.com/boto/boto3/releases','https://github.com/boto/boto3/security/policy',
                 'https://github.com/amazen33/twinfra/pull/58','https://aws.amazon.com/sdk-for-python/'],
        'cert-manager':['https://cert-manager.io/docs/','https://www.cncf.io/projects/cert-manager/',
                        'https://cert-manager.io/docs/releases/','https://cert-manager.io/docs/contributing/security/',
                        'https://github.com/cert-manager/cert-manager/releases/tag/v1.20.4',
                        'https://cert-manager.io/docs/contributing/ambassadors/']}
    result={'status':'pending' if pending else 'verified','criteria':{}}
    for criterion,url in zip(CRITERIA,urls[project]):
        result['criteria'][criterion]={'result':'pending' if criterion in pending else 'pass','evidence':url,'date':DATE}
    if project=='psycopg2':
        result['criteria']['governance']['notes']='Bundled dependency; support/governance qualification not inferred from Barman approval.'
    if project=='openssl':
        result['criteria']['supplyChain']['notes']='Inherited admitted Python base; verified CLI 3.5.7, Debian 3.5.7-1~deb13u3 and binary/library hashes. CMS CI fixture required separately.'
    return result


def climbing():
    return {'reviewedOn':DATE,'reevaluateOn':'2027-04-16','reviewAtMinorUpgrade':True,'rejectedCandidates':[
        {'name':'pgBackRest CNPG plugins (Dalibo / Opera)','tier':2,'failedCriterion':'maturity: experimental v0.0.x; WO-09 Amendment 2',
         'evidence':'https://github.com/dalibo/cnpg-plugin-pgbackrest'},
        {'name':'WAL-G','tier':2,'failedCriterion':'integration: no CNPG plugin; WO-09 Amendment 2',
         'evidence':'https://github.com/wal-g/wal-g'}]}


def render():
    register_path=ROOT/'security/licence-register.json';register=json.loads(register_path.read_text())
    policy_path=ROOT/'security/licence-policy.json';policy=json.loads(policy_path.read_text())
    entries={v['id']:v for v in register['components']};components,_=enumerate_inputs(ROOT)
    managed={'barman','psycopg2','openssl/openssl','cloudnative-pg/plugin-barman-cloud/manifest.yaml',
             'ghcr.io/cloudnative-pg/plugin-barman-cloud','ghcr.io/cloudnative-pg/plugin-barman-cloud-sidecar',
             'cert-manager/cert-manager/deploy/crds/cert-manager.io_certificates.yaml',
             'cert-manager/cert-manager/deploy/crds/cert-manager.io_issuers.yaml'}
    for key,value in components.items():
        if value['ecosystem']=='pip' and value['name'] in ('attrs','jsonschema','pyrsistent'):
            # Same versions, stronger CI wheel evidence. A changed integrity
            # record cannot inherit the frozen legacy approval under ADR-0054.
            entry=deepcopy(entries[key]);entry['integrities']=observed_integrities(value);entry['locations']=value['locations']
            entry['enterpriseGrade']={'status':'pending','criteria':{k:{'result':'pending',
                'evidence':entry['licenceSource'],'date':DATE,
                'notes':'Existing CI library/version; newly hash-pinned wheel requires full qualification. No runtime upgrade or approval inferred.'} for k in CRITERIA}}
            entries[key]=entry;continue
        if key in entries and value['name'] not in managed and not (value['ecosystem']=='pip' and value['name']=='boto3'):continue
        eco,name,version=value['ecosystem'],value['name'],value['version']
        if name=='boto3':
            entry=deepcopy(entries[key]);entry['enterpriseGrade']=grade('boto3');entry['locations']=value['locations'];entries[key]=entry
            continue
        if name=='barman':project,spdx,tier='barman','GPL-3.0-only',4;licence='https://github.com/EnterpriseDB/barman/blob/release/3.20.1/LICENSE'
        elif name=='psycopg2':project,spdx,tier='psycopg2','LGPL-3.0-or-later',3;licence='https://github.com/psycopg/psycopg2/blob/2_9_13/LICENSE'
        elif name=='openssl/openssl':project,spdx,tier='openssl','Apache-2.0',2;licence='https://raw.githubusercontent.com/openssl/openssl/openssl-3.5.7/LICENSE.txt'
        elif name.startswith('cert-manager/cert-manager/'):
            project,spdx,tier='cert-manager','Apache-2.0',2;licence='https://github.com/cert-manager/cert-manager/blob/0b9448974868c5669d4f3e7499f5afd393889e22/LICENSE'
        elif 'plugin-barman-cloud' in name:
            project,spdx,tier='plugin','Apache-2.0',2;licence=PLUGIN+'/blob/v0.15.1/LICENSE'
            if name.endswith('sidecar'):project,spdx,tier='barman','Apache-2.0 AND GPL-3.0-only AND LGPL-3.0-or-later',4
        else:raise ValueError('Unreviewed WO-09 component: '+key)
        pending=['supplyChain','securityProcess'] if project in ('plugin','barman','psycopg2') else []
        if project=='psycopg2':pending+=['governance','activitySupport','securityProcess','adoption']
        entry=dict(id=key,ecosystem=eco,name=name,version=version,spdx=spdx,
                   **{'class':'exception' if tier>=3 else 'allowed'},tier=tier,licenceSource=licence,
                   verifiedOn=DATE,recordedOn=DATE,locations=value['locations'],integrities=observed_integrities(value),
                   enterpriseGrade=grade(project,pending))
        if project=='cert-manager':
            entry.pop('tier');entry.pop('enterpriseGrade')
            entry['notes']='CRD schema-only validation input, never installed. WO-08 owns cert-manager runtime admission.'
        if eco=='oci-image':entry['notes']='Upstream project/package licences verified; complete image SBOM licence review and ADR-0049 admission still required. No baseline or vulnerability approval granted.'
        if tier>=3:
            entry.update(adr='0054',approvedBy='amazen33',expires='2027-04-16',unmodified=True,separateUnit=True,
                         notice=NOTICE,climbing=climbing())
            policy['exceptions'][name]={'spdx':spdx,'adr':'0054'}
        entries[key]=entry
    register['components']=sorted(entries.values(),key=lambda v:v['id'])
    register_path.write_text(json.dumps(register,indent=2)+'\n',encoding='utf-8',newline='\n')
    policy_path.write_text(json.dumps(policy,indent=2)+'\n',encoding='utf-8',newline='\n')
    notice_root=ROOT/'security/licences/backups'
    lock={p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(notice_root.iterdir()) if p.is_file()}
    (ROOT/'security/licences/backup-notices.lock.json').write_text(json.dumps(lock,indent=2)+'\n',encoding='utf-8',newline='\n')
    print('Rendered WO-09 records; pending criteria and missing image evidence remain blocking')


if __name__=='__main__':render()
