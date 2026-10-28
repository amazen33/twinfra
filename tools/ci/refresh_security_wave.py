"""R12 deterministic candidate pins; never approve risks or touch a live host."""
import argparse
import copy
from datetime import date,datetime,timedelta,timezone
import gzip
import hashlib
import io
import json
from pathlib import Path
import re
import subprocess
import sys
import urllib.request
import zipfile

ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'tools'),str(ROOT/'tools/ci')]
from security_wave_2026_10 import CASES, compare_identities
from licence_inventory import enumerate_inputs

BASE='0d950075a8bf43358d9fd406b80b67d657f804e1'
CASES_SELECTED=('argocd355','ministack1533','keycloak2681')
DATE='2026-10-28'
CERTIFI='2026.10.23'
DOMPURIFY='3.4.17'
RUN='https://github.com/amazen33/twinfra/actions/runs/40754061462'
LICENSES={
    'argocd':('Apache-2.0','https://raw.githubusercontent.com/argoproj/argo-cd/v3.5.5/LICENSE'),
    'ministack':('MIT','https://raw.githubusercontent.com/ministackorg/ministack/v1.5.33/LICENSE'),
    'keycloak':('Apache-2.0','https://raw.githubusercontent.com/keycloak/keycloak/26.8.1/LICENSE.txt'),
}


def read(path):return json.loads(Path(path).read_text(encoding='utf-8'))
def save(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,indent=2)+'\n',encoding='utf-8',newline='\n')
def base(path):return json.loads(subprocess.check_output(['git','-C',str(ROOT),'show',BASE+':'+path]))
def fetch(url):
    if not url.startswith('https://'):raise ValueError('HTTPS evidence required')
    request=urllib.request.Request(url,headers={'User-Agent':'Twinfra-R12'})
    with urllib.request.urlopen(request,timeout=120) as response:return response.read()


def validate_comparison(report,case,previous):
    component,release,reference=CASES[case]
    if case not in CASES_SELECTED or report['component']!=component or report['release']!=release:
        raise ValueError('Only the three owner-approved candidates are permitted')
    before,after=report['images']
    old=previous['source'].split('@')[0]
    old=re.sub(r':[^/:]+$','',old)+'@'+previous['digest']
    if before['reference']!=old or after['reference']!=reference:
        raise ValueError('Comparison is not bound to the baseline/candidate digest')
    if any(row['coverage']!='complete-oci-archive-linux-amd64' for row in (before,after)):
        raise ValueError('Complete OCI evidence required')
    actual=compare_identities(before['findings'],after['findings'])
    if not actual['strictImprovement'] or not actual['subset']:
        raise ValueError('Candidate introduces risk or provides no identity improvement')
    if report['imageCodeExecuted'] is not False or not report['executionContractUnchanged']:
        raise ValueError('Data-only comparison and unchanged execution contract required')
    if component=='ministack' and any(v['kev'] or v['vulnerability']=='GHSA-6q48-6c7w-9gw2' for v in after['findings']):
        raise ValueError('MiniStack must fix both the KEV and certifi Critical')
    if component=='keycloak':
        old_guava={(v['package'],v['vulnerability']) for v in before['findings'] if v['package']=='guava'}
        if any((v['package'],v['vulnerability']) not in old_guava for v in after['findings'] if v['package']=='guava' and v['severity']=='High'):
            raise ValueError('Keycloak introduces a Guava High')
    return before,after,actual


def pins(evidence):
    """Generate only the approved dev pins and reviewed SBOMs; no application build."""
    original=base('deploy/common/images.lock.json');value=copy.deepcopy(original)
    register=read(ROOT/'security/licence-register.json')
    original_register=base('security/licence-register.json')
    summaries={}
    for case in CASES_SELECTED:
        component,release,reference=CASES[case]
        folder=evidence/('security-wave-'+case)/case
        report=read(folder/'comparison.json')
        before,after,comparison=validate_comparison(report,case,original['images'][component])
        licence,url=LICENSES[component];raw=fetch(url)
        if licence.encode() not in raw and not (b'Apache License' in raw if licence=='Apache-2.0' else b'MIT License' in raw):
            raise ValueError('Primary licence verification failed: '+component)
        digest=reference.split('@')[1];tag=('v' if component=='argocd' else '')+release
        repo={'argocd':'argoproj/argo-cd','ministack':'ministackorg/ministack','keycloak':'keycloak/keycloak'}[component]
        release_tag=('v' if component!='keycloak' else '')+release
        release_meta=json.loads(fetch('https://api.github.com/repos/'+repo+'/releases/tags/'+release_tag))
        published=datetime.fromisoformat(release_meta['published_at'].replace('Z','+00:00'))
        age=datetime.fromisoformat(DATE).replace(tzinfo=timezone.utc)+timedelta(days=1)-published
        if release_meta.get('draft') or release_meta.get('prerelease') or age.total_seconds()<0:
            raise ValueError('Stable published upstream release required')
        if age<timedelta(days=14) and not (component=='ministack' and any(v['kev'] for v in before['findings'])):
            raise ValueError('Release is not eligible for normal or KEV-expedited admission')
        entry=value['images'][component]
        entry.update(source=reference,release=reference.split('@')[0]+':'+tag,digest=digest,
                     canonical='registry.twinfra.example.com/'+reference,
                     releaseSource=release_meta['html_url'],releasePublishedAt=release_meta['published_at'],
                     verifiedOn=DATE,licenceSHA256=hashlib.sha256(raw).hexdigest())
        if component=='ministack':
            publication=json.loads(fetch('https://hub.docker.com/v2/repositories/ministackorg/ministack/tags/'+release))
            entry.update(publishedAt=publication['last_updated'],
                publicationSource='https://hub.docker.com/v2/repositories/ministackorg/ministack/tags/'+release,
                digestSource='https://registry-1.docker.io/v2/ministackorg/ministack/manifests/'+release,
                expedite={'decision':'WO-40 Amendment10a / O-1','advisory':'CVE-2026-111497','approvedOn':DATE})
        sbom=folder/'scan/sboms'/(digest.split(':')[1]+'.cdx.json')
        doc=read(sbom)
        if doc.get('bomFormat')!='CycloneDX' or not doc.get('components'):raise ValueError('Reviewed SBOM required')
        target=ROOT/'deploy/common/vendor'/('r12-'+component+'-'+release+'.cdx.json.gz')
        target.write_bytes(gzip.compress(sbom.read_bytes(),mtime=0))
        old_id='oci-image|'+before['reference'].replace('@','|')
        record=copy.deepcopy(next(e for e in original_register['components'] if e['id']==old_id))
        record.update(id='oci-image|'+reference.replace('@','|'),version=digest,integrities=[digest],
                      licenceSource=url,verifiedOn=DATE,recordedOn=DATE,
                      notes='Unmodified upstream; primary LICENSE SHA256 '+hashlib.sha256(raw).hexdigest()+'. R12 scan '+RUN,
                      imageSBOM={'path':target.relative_to(ROOT).as_posix(),'sha256':hashlib.sha256(target.read_bytes()).hexdigest()})
        # Unknown qualification is deliberately pending; the licence gate must fail.
        record['enterpriseGrade']={'status':'pending','criteria':{k:{'result':'pending','evidence':url,'date':DATE} for k in
                ('maturity','governance','activitySupport','securityProcess','supplyChain','adoption')}}
        register['components']=[e for e in register['components'] if e['id']!=record['id']]+[record]
        summaries[component]={'before':before['reference'],'after':reference,'comparison':comparison,
                              'beforeCounts':before['counts'],'afterCounts':after['counts'],'runURL':RUN}
    save(ROOT/'deploy/common/images.lock.json',value)
    # The retained offline WSL sources use the same MiniStack pin. Only render
    # files; never invoke its stage/apply helpers or start the retired distro.
    wsl=ROOT/'lab/wsl/console/artifacts.lock.json';wsl_data=read(wsl)
    wsl_data['images']['ministack']=copy.deepcopy(value['images']['ministack'])
    wsl_data['images']['ministack']['canonical']='registry.vcloud.example.com/'+value['images']['ministack']['source']
    save(wsl,wsl_data)
    subprocess.run([sys.executable,str(ROOT/'tools/wsl_console.py')],cwd=ROOT,check=True)
    subprocess.run([sys.executable,str(ROOT/'tools/platform_dev.py'),'render'],cwd=ROOT,check=True)
    observed,_=enumerate_inputs(ROOT)
    for record in register['components']:
        if record['id'].split('|')[-1] in [CASES[c][2].split('@')[1] for c in CASES_SELECTED]:
            record['locations']=observed[record['id']]['locations']
    register['components'].sort(key=lambda e:e['id']);save(ROOT/'security/licence-register.json',register)
    save(ROOT/'security/security-wave-2026-10-images.json',{'date':DATE,'base':BASE,'images':summaries,'liveAcceptance':'Pending'})


def dependencies():
    """O-1 authorises cooling-off only; qualification remains a separate gate."""
    metadata=json.loads(fetch('https://pypi.org/pypi/certifi/'+CERTIFI+'/json'))
    wheels=[v for v in metadata['urls'] if v['filename']=='certifi-'+CERTIFI+'-py3-none-any.whl']
    if len(wheels)!=1:raise ValueError('One universal certifi wheel required')
    wheel=wheels[0];raw=fetch(wheel['url']);pin=hashlib.sha256(raw).hexdigest()
    if pin!=wheel['digests']['sha256']:raise ValueError('certifi wheel checksum differs')
    for filename in ('module-5a/requirements-runtime.lock.txt','tools/ci/rag-requirements.txt'):
        path=ROOT/filename;text=path.read_text(encoding='utf-8')
        new,count=re.subn(r'^certifi==[^\n]+$', 'certifi=='+CERTIFI+' --hash=sha256:'+pin,text,flags=re.M)
        if count!=1:raise ValueError('One certifi lock entry required')
        path.write_text(new,encoding='utf-8',newline='\n')
    source=next(v for v in metadata['urls'] if v['packagetype']=='sdist')
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        names=[n for n in archive.namelist() if n.endswith('/LICENSE')]
        if len(names)!=1:raise ValueError('One certifi primary licence required')
        license_raw=archive.read(names[0])
        if b'Mozilla Public License' not in license_raw:raise ValueError('certifi licence changed')
    directory=ROOT/'security/licences/rag/certifi'
    (directory/'LICENSE').write_bytes(license_raw)
    (directory/'SOURCE.txt').write_text('certifi '+CERTIFI+'\nCorresponding unmodified source: '+source['url']+
        '\nSHA256: '+source['digests']['sha256']+'\nThe upstream source is referenced, not vendored. Preserve source availability and review obligations before distribution.\n',encoding='utf-8',newline='\n')
    notice=ROOT/'security/licences/rag/NOTICE.md';text=notice.read_text(encoding='utf-8')
    text=re.sub(r'^\| certifi \|.*$', '| certifi | '+CERTIFI+' | MPL-2.0 | [Corresponding source]('+source['url']+') |',text,flags=re.M)
    notice.write_text(text,encoding='utf-8',newline='\n')
    hashes=read(ROOT/'security/licences/rag-notices.lock.json')
    for path in hashes:hashes[path]=hashlib.sha256((ROOT/path).read_bytes().replace(b'\r\n',b'\n')).hexdigest()
    save(ROOT/'security/licences/rag-notices.lock.json',hashes)
    package=ROOT/'tools/ci/mermaid/package.json';data=read(package)
    data.setdefault('overrides',{})['dompurify']=DOMPURIFY;save(package,data)
    executable='npm.cmd' if sys.platform=='win32' else 'npm'
    subprocess.run([executable,'install','--package-lock-only','--ignore-scripts','--no-audit','--no-fund'],cwd=package.parent,check=True)
    data=read(package.with_name('package-lock.json'))
    found=[v['version'] for k,v in data['packages'].items() if k.endswith('node_modules/dompurify')]
    if found!=[DOMPURIFY]:raise ValueError('DOMPurify resolution differs')
    save(ROOT/'security/security-wave-2026-10-dependencies.json',{'date':DATE,'authority':'WO-40 Amendment10 O-1 (owner, 2026-10-28)',
          'certifi':{'version':CERTIFI,'wheelSHA256':pin,'metadata':'https://pypi.org/pypi/certifi/'+CERTIFI+'/json'},
          'dompurify':{'version':DOMPURIFY,'metadata':'https://registry.npmjs.org/dompurify/'+DOMPURIFY}})


def register():
    """Prepare O-5 carries without silently approving the owner's PR batch."""
    from licence_ladder import fingerprint
    original=base('security/licence-register.json');policy=base('security/licence-policy.json')
    current=read(ROOT/'security/licence-register.json');observed,_=enumerate_inputs(ROOT)
    events=[];carries=[]
    dependencies_receipt=read(ROOT/'security/security-wave-2026-10-dependencies.json')
    for name,version,advisories,old_release,new_release in [
        ('docker.io/ministackorg/ministack',CASES['ministack1533'][2].split('@')[1],['CVE-2026-111497','GHSA-6q48-6c7w-9gw2'],'1.5.17','1.5.33'),
        ('certifi',CERTIFI,['GHSA-6q48-6c7w-9gw2'],'2026.7.22',CERTIFI),
        ('dompurify',DOMPURIFY,['CVE-2026-116804'],'3.4.16',DOMPURIFY)]:
        old=next(e for e in original['components'] if e['name']==name)
        identity='|'.join((old['ecosystem'],name,version))
        if name.startswith('docker.io/'):
            new=copy.deepcopy(next(e for e in current['components'] if e['id']==identity))
            licence_hash=read(ROOT/'deploy/common/images.lock.json')['images']['ministack']['licenceSHA256']
        else:
            new=copy.deepcopy(old);new.update(id=identity,version=version,verifiedOn=DATE,recordedOn=DATE)
            url=('https://pypi.org/pypi/certifi/'+CERTIFI+'/json' if name=='certifi' else 'https://registry.npmjs.org/dompurify/'+DOMPURIFY)
            primary=fetch(url);doc=json.loads(primary)
            spdx=(doc['info'].get('license_expression') or doc['info']['license']) if name=='certifi' else doc['license']
            if spdx!=old['spdx']:raise ValueError('Carry licence changed: '+name)
            new.update(licenceSource=url,integrities=sorted({
                ('sha256:'+dependencies_receipt['certifi']['wheelSHA256']) if name=='certifi' else doc['dist']['integrity']}))
            licence_hash=hashlib.sha256(primary).hexdigest()
        new['enterpriseGrade']=copy.deepcopy(old['enterpriseGrade'])
        if new['spdx']!=old['spdx'] or new['tier']!=old['tier']:raise ValueError('Carry tier/licence differs')
        new['locations']=observed[identity]['locations']
        old_map=policy['ladder']['legacy'].pop(old['id'])
        new_map={'sha256':fingerprint(new),'tier':old_map['tier'],'due':old_map['due'],
                 'carriedFrom':old['id'],'advisoriesCleared':advisories,'approvalDate':'','approvedBy':'',
                 'authorisedOn':DATE,'decision':'ADR-0054 Amendment1 / O-5'}
        policy['ladder']['legacy'][identity]=new_map
        event={'from':old['id'],'to':identity,'fromVersion':old_release,'toVersion':new_release,
               'originalDue':old_map['due'],'record':new,'advisoriesCleared':advisories,
               'netImprovement':True,'licenceSHA256':licence_hash,'evidence':RUN,'proposedOn':DATE}
        events.append(event);carries.append({k:v for k,v in event.items() if k!='record'})
        current['components']=[e for e in current['components'] if e['id'] not in (old['id'],identity)]+[new]
    for component in ('argocd','keycloak'):
        name='quay.io/'+('argoproj/argocd' if component=='argocd' else 'keycloak/keycloak')
        record=next(e for e in current['components'] if e['name']==name and e['version']==CASES['argocd355' if component=='argocd' else 'keycloak2681'][2].split('@')[1])
        foundation='https://www.cncf.io/projects/'+('argo/' if component=='argocd' else 'keycloak/')
        security='https://github.com/argoproj/argo-cd/security/policy' if component=='argocd' else 'https://www.keycloak.org/security'
        release=read(ROOT/'deploy/common/images.lock.json')['images'][component]['releaseSource']
        urls=dict(maturity=release,governance=foundation,activitySupport=security,securityProcess=security,supplyChain=RUN,adoption=foundation)
        record['enterpriseGrade']={'status':'pending','criteria':{k:{'result':'pending' if k=='supplyChain' else 'pass','evidence':v,'date':DATE} for k,v in urls.items()}}
    current['components']=[e for e in current['components'] if e['id'] in observed]
    current['components'].sort(key=lambda e:e['id'])
    log={'version':1,'anchorCommit':BASE,
         'anchorLegacySHA256':hashlib.sha256(json.dumps(base('security/licence-policy.json')['ladder']['legacy'],sort_keys=True).encode()).hexdigest(),'events':events}
    policy['ladder']['carryLog']='security/licence-carry-log.json'
    save(ROOT/'security/licence-carry-log.json',log)
    save(ROOT/'security/licence-policy.json',policy);save(ROOT/'security/licence-register.json',current)
    save(ROOT/'security/security-wave-2026-10-carries.json',{'proposedOn':DATE,'carries':carries,'ownerBatchApproval':'Pending'})


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command',choices=['pins','dependencies','register'])
    parser.add_argument('--evidence',type=Path)
    args=parser.parse_args()
    if args.command=='pins':
        if not args.evidence:parser.error('--evidence is required')
        pins(args.evidence.resolve())
    elif args.command=='dependencies':dependencies()
    else:register()
