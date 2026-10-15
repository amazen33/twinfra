#!/usr/bin/env python3
"""WO-34 3a: verified dev-only pins and exact, non-renewing exception carry."""
import argparse
import copy
from datetime import datetime, timedelta, timezone
import gzip
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'tools'),str(ROOT/'tools/ci')]
from platform_pg_image import Export
from licence_inventory import enumerate_inputs

BASE='e92255278369a25f26bc694b38c33bfd2768c14d'
PINS={
    'coredns':('v1.14.7','sha256:7efd3c635b03efd68c4e8398fc45f0d993d0e9ab016f72c1cefb0fd6d01aa286','coredns/coredns'),
    'etcd':('3.6.15-0','sha256:5ed4e32061aa061f970d6500629213e8579ef17571dcf9789074966acb9afad1','etcd-io/etcd'),
}
CONTROLS=[
    'Argo CD is tunnel-only, with no NodePort, LoadBalancer or Ingress.',
    'Dell firewall drops etcd client TCP 2379 and peer TCP 2380 on the LAN interface.',
    'CoreDNS is cluster-internal; no NodePort, LoadBalancer or Ingress.',
    'The dev environment is LAN-only; no router port forwarding.',
]


def save(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,indent=2)+'\n',encoding='utf-8',newline='\n')


def pairs(comparison,component):
    rows={v['name']:v for v in comparison['images']}
    before,after=[rows[component+'-'+s] for s in ('before','after')]
    for row in (before,after):
        if row['coverage']!='complete-oci-archive-linux-amd64':raise ValueError('Complete image evidence required')
    identity=lambda v:(v['package'],v['vulnerability'])
    severe=lambda row:{identity(v) for v in row['findings'] if v['severity'] in ('Critical','High') and v['fixAvailable']}
    old,new=severe(before),severe(after)
    if not new<old:raise ValueError('Candidate must be a strict fixable Critical/High identity subset: '+component)
    if {identity(v) for v in after['findings']}-{identity(v) for v in before['findings']}:
        raise ValueError('Candidate contains a new vulnerability identity: '+component)
    return before,after


def carry_exceptions(comparison,ledger):
    value=copy.deepcopy(ledger);carried=[];closed=[]
    for component in PINS:
        before,after=pairs(comparison,component)
        existing=[v for v in value['exceptions'] if v['target']==before['reference']]
        after_by={}
        for finding in after['findings']:
            after_by.setdefault((finding['package'],finding['vulnerability']),[]).append(finding)
        kept=[v for v in value['exceptions'] if v['target']!=before['reference']]
        for entry in existing:
            exact=[f for f in before['findings'] if all(f[k]==entry[k] for k in ('package','version','vulnerability','severity'))]
            if len(exact)!=1:raise ValueError('Existing exception lacks exact before evidence')
            matches=after_by.get((entry['package'],entry['vulnerability']),[])
            if not matches:closed.append(entry);continue
            if len(matches)!=1 or matches[0]['severity']!=entry['severity']:raise ValueError('Ambiguous or changed-severity exception')
            new=dict(entry,target=after['reference'],version=matches[0]['version'])
            if 'GO-2026-6612' in matches[0]['aliases']:new['controls']=list(CONTROLS)
            # No approval/reason/creation/expiry changes; November 12 wins over a new 30 days.
            kept.append(new);carried.append(dict(component=component,before=entry,after=new))
        for finding in after['findings']:
            if finding['severity']=='Critical' and not any(all(e[k]==finding[k] for k in
                    ('target','package','version','vulnerability','severity')) for e in kept):
                raise ValueError('Remaining Critical lacks an existing exception to carry: '+finding['vulnerability'])
        value['exceptions']=kept
    return value,carried,closed


def promote(inputs,comparison,run_url):
    if not re.fullmatch(r'https://github\.com/amazen33/twinfra/actions/runs/[0-9]+',run_url):raise ValueError('Public CI evidence required')
    ledger_path=ROOT/'security/vulnerability-exceptions.json'
    original=json.loads(subprocess.check_output(['git','-C',str(ROOT),'show',BASE+':security/vulnerability-exceptions.json']))
    ledger,carried,closed=carry_exceptions(comparison,original)
    current=json.loads(ledger_path.read_text())
    if current not in (original,ledger):raise ValueError('Ledger changed outside this deterministic promotion')
    lock_path=ROOT/'deploy/common/bootstrap-images.lock.json';lock=json.loads(lock_path.read_text());metadata={}
    base_lock=json.loads(subprocess.check_output(['git','-C',str(ROOT),'show',BASE+':deploy/common/bootstrap-images.lock.json']))
    references=lock.setdefault('referenceOnlyImages',[])
    for component in PINS:
        previous=base_lock['images'][component]
        if not any(v['digest']==previous['digest'] for v in references):
            references.append(previous|{'purpose':'Unchanged production kubeadm default; excluded from dev staging.'})
    register_path=ROOT/'security/licence-register.json';register=json.loads(register_path.read_text())
    for component,(tag,pin,repo) in PINS.items():
        before,after=pairs(comparison,component)
        if not after['reference'].endswith('@'+pin):raise ValueError('Candidate comparison digest differs')
        release=json.loads((inputs/(component+'-release.json')).read_text())
        expected='v'+tag.removeprefix('v').removesuffix('-0')
        published=datetime.fromisoformat(release['published_at'].replace('Z','+00:00'))
        if release['tag_name']!=expected or release.get('prerelease') or release.get('draft') or datetime.now(timezone.utc)-published<timedelta(days=14):
            raise ValueError('Candidate is not an eligible stable patch')
        license_raw=(inputs/(component+'-LICENSE')).read_bytes()
        if b'Apache License' not in license_raw or b'Version 2.0' not in license_raw:raise ValueError('Primary source licence is not verified Apache-2.0')
        export=Export(inputs/(component+'-after.oci.tar'))
        try:
            if export.root_digest!=pin or export.descriptor['digest']!=after['verifiedAmd64Digest']:raise ValueError('OCI pin/platform differs from complete scan')
            config=json.loads(export.blob(export.manifest['config']))
            if (config['os'],config['architecture'])!=('linux','amd64'):raise ValueError('Wrong OCI platform')
            for layer in export.manifest['layers']:export.blob(layer)
            source=after['reference'];canonical='registry.twinfra.example.com/registry.k8s.io/'+component+':'+tag
            entry=lock['images'][component]
            entry.update(release=source.split('@')[0]+':'+tag,source=source,canonical=canonical,digest=pin,
                amd64Digest=export.descriptor['digest'],configDigest=export.manifest['config']['digest'],
                digestSource='https://registry.k8s.io/v2/'+('coredns/coredns' if component=='coredns' else 'etcd')+'/manifests/'+tag,
                releaseSource=release['html_url'],releasePublishedAt=release['published_at'],verifiedOn=comparison['date'])
        finally:export.archive.close()
        sbom=inputs.parent/'p2-promote-before-after/scan/sboms'/(pin.split(':')[1]+'.cdx.json')
        parsed=json.loads(sbom.read_text())
        if parsed.get('bomFormat')!='CycloneDX' or not parsed.get('components'):raise ValueError('Complete reviewed image SBOM required')
        sbom_path=ROOT/'deploy/common/vendor'/('wo34-'+component+'-'+tag+'.cdx.json.gz')
        sbom_path.write_bytes(gzip.compress(sbom.read_bytes(),mtime=0))
        licence_url='https://raw.githubusercontent.com/'+repo+'/'+expected+'/LICENSE'
        component_name=source.split('@')[0];component_id='oci-image|'+component_name+'|'+pin
        record=dict(id=component_id,ecosystem='oci-image',name=component_name,version=pin,locations=[],spdx='Apache-2.0',
            **{'class':'allowed'},licenceSource=licence_url,verifiedOn=comparison['date'],recordedOn=comparison['date'],integrities=[pin],
            notes='Unmodified upstream. Primary LICENSE SHA256 '+hashlib.sha256(license_raw).hexdigest()+'. OS/dependency terms remain in the reviewed SBOM.',
            imageSBOM=dict(path=sbom_path.relative_to(ROOT).as_posix(),sha256=hashlib.sha256(sbom_path.read_bytes()).hexdigest()))
        register['components']=[v for v in register['components'] if v['id']!=component_id]+[record]
        metadata[component]=dict(pin=entry,release=release['html_url'],publishedAt=release['published_at'],
            licenceSource=licence_url,licenceSHA256=hashlib.sha256(license_raw).hexdigest(),sbom=record['imageSBOM'])
    save(lock_path,lock)
    observed,_=enumerate_inputs(ROOT)
    related={v['reference'].split('@')[0] for v in comparison['images'] if v['name'].startswith(('coredns-','etcd-'))}
    register['components']=[v for v in register['components'] if v['name'] not in related or v['id'] in observed]
    for entry in register['components']:
        if entry['name'] in related and entry['id'] in observed:entry['locations']=observed[entry['id']]['locations']
    register['components'].sort(key=lambda v:v['id']);save(register_path,register);save(ledger_path,ledger)
    evidence=dict(date=comparison['date'],runURL=run_url,base=BASE,scope='Static dev CoreDNS/etcd promotion; no application binaries built/executed',
        liveAcceptance='Pending',testerSignOff='Pending',metadata=metadata,
        images=[{k:v for k,v in r.items() if k!='findings'} for r in comparison['images'] if r['name'].startswith(('coredns','etcd'))],
        carriedExceptions=carried,closedExceptions=closed,remainingExceptions=len(ledger['exceptions']),
        sourceEvidence='docs/acceptance/wo34-source-2026-10-14.json',controls=CONTROLS)
    save(ROOT/'docs/acceptance/wo34-p2-2026-10-15.json',evidence)
    # Use the existing source/seed generators; production's generated containers
    # and version selections stay the same, while their embedded script/hash follows source.
    for generator in ('tools/render_ssot.py','tools/render_cloud_init.py'):
        subprocess.run([sys.executable,generator],cwd=ROOT,check=True)
    subprocess.run([sys.executable,'tools/platform_dev.py','render'],cwd=ROOT,check=True)
    path=ROOT/'security/licence-baseline.json';baseline=json.loads(path.read_text())
    for entry in baseline['findings']:
        if entry['id']=='image-digest:00-setup-ubuntu-host.sh':
            entry['fingerprint']=hashlib.sha256((ROOT/'00-setup-ubuntu-host.sh').read_bytes()).hexdigest()
    save(path,baseline)
    print('PASS: '+str(len(closed))+' fixed exceptions closed; '+str(len(carried))+' carried without renewal')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--inputs',type=Path,required=True)
    p.add_argument('--comparison',type=Path,required=True);p.add_argument('--run-url',required=True);a=p.parse_args()
    promote(a.inputs,json.loads(a.comparison.read_text()),a.run_url)
