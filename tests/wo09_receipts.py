"""Bounded WO-09 additions; retain all prior delivery receipt comparisons."""
import copy
import json
from pathlib import Path
import re
import subprocess
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools/ci'))
from licence_ladder import fingerprint, runtime
BASE='09d56f3'


def old(name):return subprocess.check_output(['git','-C',str(ROOT),'show',BASE+':'+name])


def images():
    name='deploy/common/images.lock.json';original=json.loads(old(name));expected=copy.deepcopy(original)
    artifacts=json.loads((ROOT/'deploy/common/backup-artifacts.lock.json').read_text())
    receipt=json.loads((ROOT/'deploy/common/backup-image.lock.json').read_text())
    expected['images'].update(artifacts['images'])
    etcd=json.loads((ROOT/'deploy/common/bootstrap-images.lock.json').read_text())['images']['etcd']
    expected['images']['etcd-backup']={'source':etcd['source'],'canonical':etcd['canonical']+'@'+etcd['digest'],'digest':etcd['digest'],'release':etcd['release']}
    expected['images']['backup']={'source':receipt['canonical'].removeprefix('registry.twinfra.example.com/'),
        'canonical':receipt['canonical'],'digest':receipt['digest'],'buildReceipt':'deploy/common/backup-image.lock.json'}
    if not receipt['canonical'].startswith('registry.twinfra.example.com/docker.io/twinfra/twinfra-backup@sha256:'):
        raise AssertionError('Unknown backup image repository')
    if json.loads((ROOT/name).read_text())!=expected:raise AssertionError('Image lock differs outside the four WO-09 additions')
    return old(name)


def policy():
    name='security/licence-policy.json';original=json.loads(old(name));current=json.loads((ROOT/name).read_text())
    ladder=current.pop('ladder')
    tiers={'1':[x for x in original['permitted'] if x!='Apache-2.0'],'2':['Apache-2.0'],
           '3':['MPL-2.0','LGPL-*','EPL-2.0'],'4':['GPL-*']}
    legacy={}
    for entry in json.loads(old('security/licence-register.json'))['components']:
        if not runtime(entry):continue
        spdx=entry['spdx']
        tier=4 if re.search(r'(?<!L)GPL-',spdx) else 3 if any(x in spdx for x in ('MPL-','LGPL-','EPL-')) else 2 if 'Apache-2.0' in spdx else 1
        legacy[entry['id']]={'sha256':fingerprint(entry),'tier':tier,'due':'2027-01-14' if tier>=3 else '2027-04-16'}
    expected={'effectiveOn':'2026-10-16','decision':'docs/adr/0054-licence-ladder-and-enterprise-grade-gate.md',
        'tiers':tiers,'never':['AGPL-*','SSPL-*','BUSL-*','Elastic-*','Commons-Clause*','LicenseRef-*','account-gated','proprietary','source-available'],'legacy':legacy}
    if ladder!=expected:raise AssertionError('ADR-0054 baseline identities, deadlines or ladder changed')
    if current.pop('decision')!='0054':raise AssertionError('Wrong licence decision')
    current['decision']=original['decision']
    for component,spdx in [('barman','GPL-3.0-only'),('psycopg2','LGPL-3.0-or-later'),
        ('ghcr.io/cloudnative-pg/plugin-barman-cloud-sidecar','Apache-2.0 AND GPL-3.0-only AND LGPL-3.0-or-later')]:
        if current['exceptions'].pop(component)!={'spdx':spdx,'adr':'0054'}:raise AssertionError('Unapproved backup licence exception')
    if current!=original:raise AssertionError('Existing licence policy changed beyond ADR-0054 additions')
    return old(name)


def register():
    name='security/licence-register.json';before=json.loads(old(name));current=json.loads((ROOT/name).read_text())
    original={e['id']:e for e in before['components']};entries={e['id']:e for e in current['components']}
    permitted={('pip','barman'),('pip','psycopg2'),('tool','openssl/openssl'),
        ('manifest','cloudnative-pg/plugin-barman-cloud/manifest.yaml'),
        ('oci-image','ghcr.io/cloudnative-pg/plugin-barman-cloud'),('oci-image','ghcr.io/cloudnative-pg/plugin-barman-cloud-sidecar'),
        ('manifest','cert-manager/cert-manager/deploy/crds/cert-manager.io_certificates.yaml'),
        ('manifest','cert-manager/cert-manager/deploy/crds/cert-manager.io_issuers.yaml')}
    added=[v for k,v in entries.items() if k not in original]
    if len(added)!=8 or {(v['ecosystem'],v['name']) for v in added}!=permitted:
        raise AssertionError('Unknown WO-09 licence additions')
    legacy=json.loads((ROOT/'security/licence-policy.json').read_text())['ladder']['legacy']
    for key,value in original.items():
        actual=copy.deepcopy(entries[key])
        if runtime(value):
            if actual.pop('tier')!=legacy[key]['tier']:raise AssertionError('Legacy tier changed')
            grade=actual.pop('enterpriseGrade')
            if value['name']=='boto3':
                from licence_ladder import validate
                validate(entries[key],json.loads((ROOT/'security/licence-policy.json').read_text()),['Apache-2.0'],__import__('datetime').date(2026,10,16))
                actual['locations']=value['locations']
            elif value['ecosystem']=='pip' and value['name'] in ('attrs','jsonschema','pyrsistent'):
                from licence_inventory import enumerate_inputs
                from check_licences import observed_integrities
                component=enumerate_inputs(ROOT)[0][key]
                if actual['integrities']!=observed_integrities(component) or grade['status']!='pending':
                    raise AssertionError('CI wheel evidence/qualification changed')
                actual['integrities']=value['integrities'];actual['locations']=value['locations']
            elif grade!={'status':'legacy-pending','due':legacy[key]['due']}:raise AssertionError('Legacy deadline changed')
        if actual!=value:raise AssertionError('Legacy approval, version, digest or expiry changed: '+key)
    return old(name)
