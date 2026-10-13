#!/usr/bin/env python3
"""ADR-0049: pinned, read-only scanning; reporting is a separate permission boundary."""
import argparse
import base64
from datetime import date, datetime, timedelta, timezone
import gzip
import hashlib
import html
import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request

from jsonschema import Draft202012Validator, FormatChecker

ROOT=Path(__file__).resolve().parents[2]
TOOLS=('syft','grype','osv-scanner')
REPOSITORY='amazen33/twinfra'
TITLE='Supply-chain scan: open findings'
WATCH_TITLE='Upstream updates available'
INITIAL_DATE=date(2026,10,13)
BOOTSTRAP_BRANCH='codex/wo-32-supply-chain-scanning'
SHA=re.compile(r'sha256:[a-f0-9]{64}')
LOCKS=('deploy/common/bootstrap-images.lock.json','deploy/common/images.lock.json')
RECEIPTS=('console/image.lock.json','deploy/common/postgresql-image.lock.json')
POLICY_INPUTS=('security/vulnerability-', 'security/licence-', 'tools/ci/', '.github/workflows/')


def today():return datetime.now(timezone.utc).date()
def sha(raw):return hashlib.sha256(raw).hexdigest()
def read(path):return json.loads(Path(path).read_text(encoding='utf-8'))
def write(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,indent=2,sort_keys=True)+'\n',encoding='utf-8',newline='\n')


def fetch(url, *, token=None, payload=None, method=None):
    if not url.startswith('https://'):raise ValueError('HTTPS required')
    headers={'User-Agent':'Twinfra-supply-chain','Accept':'application/json'}
    if token:headers['Authorization']='Bearer '+token
    request=urllib.request.Request(url,data=json.dumps(payload).encode() if payload is not None else None,
                                   headers=headers,method=method)
    with urllib.request.urlopen(request,timeout=120) as response:return response.read()


def git(root,*args):return subprocess.check_output(['git','-C',str(root),*args],text=True,encoding='utf-8').strip()
def tracked(root):return git(root,'ls-files').splitlines()
def changed(root,base):
    if not re.fullmatch(r'[a-f0-9]{40}',base):raise ValueError('Immutable base commit required')
    return git(root,'diff','--name-only',base,'HEAD').splitlines()


def is_lockfile(path):
    name=Path(path).name
    return name in ('package-lock.json','npm-shrinkwrap.json','yarn.lock','pnpm-lock.yaml',
                    'go.sum','Cargo.lock','Gemfile.lock','composer.lock','poetry.lock','Pipfile.lock',
                    'uv.lock','packages.lock.json','pubspec.lock') or (
        name.endswith('.txt') and ('requirements' in name or name.endswith('-runtime.lock.txt')))


def immutable(entry):
    digest=entry['digest']
    if not SHA.fullmatch(digest):raise ValueError('Invalid image digest')
    source=entry['source'].split('@')[0]
    # Tags are hints only. Always scan the pinned upstream digest, never the placeholder mirror.
    if ':' in source.rsplit('/',1)[-1]:source=source.rsplit(':',1)[0]
    if not re.fullmatch(r'[a-z0-9][a-z0-9._:/-]+',source):raise ValueError('Invalid image repository')
    return source+'@'+digest


def inventory(root=ROOT,base=None,full=False):
    paths=tracked(root);changes=changed(root,base) if base else paths
    full=full or not base or any(p.startswith(POLICY_INPUTS) for p in changes)
    targets={};coverage=[]
    for filename in LOCKS:
        current=read(root/filename)['images']
        old=json.loads(git(root,'show',base+':'+filename))['images'] if base else {}
        for name,entry in current.items():
            ref=immutable(entry);identifier=filename+':'+name
            introduced=name not in old or old[name]['digest']!=entry['digest'] if base else False
            selected=full or introduced or filename in changes and old.get(name)!=entry
            if name=='console' and RECEIPTS[0] in changes:selected=True
            if name=='postgres' and RECEIPTS[1] in changes:selected=True
            references=[(ref,'registry:'+ref,entry['digest'])]
            if name in ('console','postgres'):
                archive=root/'.build/dev-images'/('console.oci.tar' if name=='console' else 'postgresql-pgvector.tar')
                if archive.is_file():
                    sys.path.insert(0,str(root/'tools'))
                    from platform_image_staging import validate_archive
                    validate_archive(archive,entry['digest'])
                    references=[(ref,'oci-archive:'+archive.as_posix(),entry['digest'])]
                    mode='built-archive'
                elif name=='console':
                    receipt=read(root/RECEIPTS[0]);pinned=receipt['base']
                    pinned=pinned.removeprefix('registry.twinfra.example.com/')
                    references=[(pinned,'registry:'+pinned,pinned.split('@')[1])];mode='pinned-inputs-only'
                else:
                    # This receipt records selected manifests and copied files;
                    # upstream root pins belong to the existing builder constants.
                    code=(root/'tools/platform_pg_image.py').read_text(encoding='utf-8')
                    values=[re.search(r"^"+key+r"='([^']+)'$",code,re.MULTILINE)[1] for key in ('BASE','EXTENSION')]
                    references=[(value,'registry:'+value,value.split('@')[1]) for value in values]
                    mode='pinned-inputs-only'
            else:mode='pinned-registry'
            coverage.append(dict(entry=identifier,pinned=ref,mode=mode,selected=selected,
                                 scannedInputs=[r[0] for r in references]))
            if not selected:continue
            for target,source,digest in references:
                if not SHA.fullmatch(digest):raise ValueError('Unpinned build input')
                value=targets.setdefault(digest,dict(target=target,source=source,digest=digest,
                                                      platform='linux/amd64',origins=[],introduced=False))
                value['origins'].append(identifier);value['introduced']|=introduced
    locks=[p for p in paths if is_lockfile(p) and (full or p in changes)]
    return dict(version=1,full=full,base=base,images=list(targets.values()),coverage=coverage,lockfiles=locks)


def verify_tools(directory,root=ROOT):
    lock=read(root/'tools/ci/toolchain.lock.json')['artifacts']
    result={}
    for name in TOOLS:
        path=directory/name
        if not path.is_file() or sha(path.read_bytes())!=lock[name]['binarySHA256']:
            raise ValueError('Scanner binary checksum mismatch: '+name)
        result[name]=str(path.resolve())
    return result


def run(command,output=None,allowed=(0,),env=None):
    result=subprocess.run([str(x) for x in command],stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                          env=env,text=True,encoding='utf-8')
    if result.returncode not in allowed:
        # Commands contain no auth credentials. Scanner diagnostic text stays in the run artifact.
        if output:Path(str(output)+'.error.log').write_text(result.stderr,encoding='utf-8')
        raise ValueError('Scanner command failed: '+Path(command[0]).name+' (exit '+str(result.returncode)+')')
    if output:Path(output).write_text(result.stdout,encoding='utf-8',newline='\n')
    return result.stdout


def sboms(plan,tools,cache,out):
    cache.mkdir(parents=True,exist_ok=True);(out/'sboms').mkdir(parents=True,exist_ok=True)
    result=[]
    for item in plan['images']:
        key=item['digest'].split(':')[1];syft=cache/(key+'.syft.json');meta=cache/(key+'.meta.json')
        config=sha(Path(tools['syft']).read_bytes())
        if syft.exists():
            info=read(meta)
            if info!=dict(digest=item['digest'],platform='linux/amd64',scannerSHA256=config,sbomSHA256=sha(syft.read_bytes())):
                raise ValueError('Cached SBOM integrity/binding mismatch')
            read(syft)  # Refuse truncated/invalid cached documents.
        else:
            temp=syft.with_suffix('.part')
            run([tools['syft'],'scan',item['source'],'--platform','linux/amd64','-o','syft-json'],temp)
            read(temp);temp.replace(syft)
            write(meta,dict(digest=item['digest'],platform='linux/amd64',scannerSHA256=config,sbomSHA256=sha(syft.read_bytes())))
        copy=out/'sboms'/syft.name;copy.write_bytes(syft.read_bytes())
        run([tools['syft'],'convert',syft,'-o','cyclonedx-json'],out/'sboms'/(key+'.cdx.json'))
        result.append(item|{'sbom':str(copy),'sbomSHA256':sha(copy.read_bytes())})
    write(out/'sbom-inventory.json',result);return result


def cvss3(vector):
    values=dict(x.split(':',1) for x in vector.split('/')[1:])
    scope=values['S']=='C'
    av={'N':.85,'A':.62,'L':.55,'P':.2}[values['AV']]
    ac={'L':.77,'H':.44}[values['AC']]
    pr={'N':.85,'L':.68 if scope else .62,'H':.5 if scope else .27}[values['PR']]
    ui={'N':.85,'R':.62}[values['UI']]
    impacts={'H':.56,'L':.22,'N':0}
    iss=1-math.prod(1-impacts[values[x]] for x in 'CIA')
    impact=7.52*(iss-.029)-3.25*(iss-.02)**15 if scope else 6.42*iss
    if impact<=0:return 0
    score=min(1.08*(impact+8.22*av*ac*pr*ui) if scope else impact+8.22*av*ac*pr*ui,10)
    return math.ceil(round(score,10)*10)/10


def severity(vulnerability,group=None):
    known=vulnerability.get('database_specific',{}).get('severity','').title()
    if known in ('Critical','High','Medium','Low','Negligible'):return known
    scores=[]
    for value in vulnerability.get('severity',[]):
        raw=value.get('score','')
        if raw.startswith(('CVSS:3.0/','CVSS:3.1/')):scores.append(cvss3(raw))
        elif re.fullmatch(r'\d+(?:\.\d+)?',str(raw)):scores.append(float(raw))
    maximum=(group or {}).get('max_severity')
    if maximum is not None and re.fullmatch(r'\d+(?:\.\d+)?',str(maximum)):scores.append(float(maximum))
    if not scores:return 'Unknown'
    score=max(scores)
    return 'Critical' if score>=9 else 'High' if score>=7 else 'Medium' if score>=4 else 'Low' if score>0 else 'Negligible'


def identity(aliases):
    aliases=sorted(set(aliases))
    return next((x for x in aliases if x.startswith('CVE-')),aliases[0])


def finding(target,package,version,ids,level,fixed,scanner,introduced=False):
    if not ids or not all(isinstance(x,str) and x for x in ids):raise ValueError('Vulnerability ID missing')
    result=dict(target=target,package=package,version=version,vulnerability=identity(ids),aliases=sorted(set(ids)),
                severity=level,fixAvailable=bool(fixed),scanner=scanner,introduced=bool(introduced))
    result['key']=sha(json.dumps([target,package,version,result['vulnerability']],separators=(',',':')).encode())
    return result


def grype_findings(data,item):
    if 'matches' not in data or not isinstance(data['matches'],list):raise ValueError('Invalid Grype result')
    result=[]
    for match in data['matches']:
        vuln=match['vulnerability'];artifact=match['artifact']
        ids=[vuln['id']]+[v['id'] for v in match.get('relatedVulnerabilities',[])]
        fix=vuln.get('fix',{})
        result.append(finding(item['target'],artifact['name'],artifact['version'],ids,
                              vuln['severity'].title(),fix.get('state')=='fixed' and bool(fix.get('versions')),
                              'grype',item.get('introduced',False)))
    return result


def osv_findings(data,root,aliases=None):
    if 'results' not in data or not isinstance(data['results'],list):raise ValueError('Invalid OSV result')
    result=[];aliases=aliases or {}
    for source in data['results']:
        path=source['source']['path']
        if path in aliases:path=aliases[path]
        elif Path(path).is_absolute():path=Path(path).relative_to(root.resolve()).as_posix()
        for package in source.get('packages',[]):
            pkg=package['package'];groups=package.get('groups',[])
            for vuln in package.get('vulnerabilities',[]):
                group=next((g for g in groups if vuln['id'] in g.get('ids',[])),{})
                ids=[vuln['id'],*vuln.get('aliases',[]),*group.get('ids',[])]
                fixed=any(event.get('fixed') for affected in vuln.get('affected',[])
                          if affected.get('package',{}).get('name')==pkg['name'] and
                          affected.get('package',{}).get('ecosystem')==pkg.get('ecosystem')
                          for span in affected.get('ranges',[]) for event in span.get('events',[]))
                result.append(finding('lockfile:'+path,pkg['name'],pkg.get('version',''),ids,
                                      severity(vuln,group),fixed,'osv'))
    return result


def scan_locks(paths,root,tools,out,aliases=None):
    if not paths:return []
    command=[tools['osv-scanner'],'scan','source','--no-resolve','--no-call-analysis=go','--format=json']
    for path in paths:
        kind='requirements.txt:' if Path(path).suffix=='.txt' else ':'
        command.extend(['--lockfile',kind+str((root/path).resolve())])
    run(command,out,allowed=(0,1))
    return osv_findings(read(out),root,aliases)


def scan(plan,tools,cache,out,root=ROOT):
    out.mkdir(parents=True,exist_ok=True)
    items=sboms(plan,tools,cache,out)
    env=dict(os.environ,GRYPE_DB_CACHE_DIR=str((out/'database').resolve()),GRYPE_DB_AUTO_UPDATE='false')
    run([tools['grype'],'db','update'],out/'database-update.log',env=env)
    run([tools['grype'],'db','status','-o','json'],out/'database.json',env=env)
    findings=[]
    for item in items:
        raw=out/(item['digest'].split(':')[1]+'.grype.json')
        run([tools['grype'],'sbom:'+item['sbom'],'-o','json'],raw,env=env)
        findings.extend(grype_findings(read(raw),item))
    lock_findings=scan_locks(plan['lockfiles'],root,tools,out/'osv.json')
    if plan.get('base') and plan['lockfiles']:
        with tempfile.TemporaryDirectory(prefix='base-',dir=out) as tmp:
            baseline=Path(tmp);paths=[];aliases={}
            available=set(git(root,'ls-tree','-r','--name-only',plan['base']).splitlines())
            for path in plan['lockfiles']:
                if path not in available:continue
                dest=baseline/path;dest.parent.mkdir(parents=True,exist_ok=True)
                dest.write_text(git(root,'show',plan['base']+':'+path)+'\n',encoding='utf-8')
                paths.append(path);aliases[str(dest.resolve())]=path
            old=scan_locks(paths,baseline,tools,out/'osv-base.json',aliases)
            old_keys={v['key'] for v in old}
            for value in lock_findings:value['introduced']=value['key'] not in old_keys
    findings.extend(lock_findings)
    # Grype/OSV can emit multiple aliases for one affected artifact.
    merged={}
    for value in findings:
        if value['key'] in merged:
            merged[value['key']]['aliases']=sorted(set(merged[value['key']]['aliases']+value['aliases']))
            merged[value['key']]['fixAvailable']|=value['fixAvailable']
        else:merged[value['key']]=value
    result=dict(version=1,date=today().isoformat(),inventory=plan,findings=list(merged.values()),
                database=read(out/'database.json'))
    write(out/'findings.json',result);return result


def previous_state(repository=REPOSITORY):
    # Public issue reads require no repository secret or write permission.
    for page in range(1,11):
        values=json.loads(fetch(f'https://api.github.com/repos/{repository}/issues?state=all&per_page=100&page={page}'))
        match=next((x for x in values if x.get('title')==TITLE and 'pull_request' not in x),None)
        if match:
            if match.get('user',{}).get('login','').lower() not in ('amazen33','github-actions[bot]') or not any(
                    v.get('name')=='security' for v in match.get('labels',[])):
                raise ValueError('Untrusted reserved tracking issue; owner review required')
            body=match.get('body') or ''
            marker=re.search(r'<!-- twinfra-supply-chain-state:([A-Za-z0-9+/=]+) -->',body)
            if not marker:raise ValueError('Tracking issue is missing first-seen state; refusing to reset its clock')
            payload=gzip.decompress(base64.b64decode(marker[1],validate=True))
            if len(payload)>4*1024**2:raise ValueError('Oversized issue state')
            wire=json.loads(payload)
            identities={}
            if isinstance(wire,dict) and wire.get('format')==1:
                strings=wire['strings'];records=wire['records']
                if not isinstance(strings,list) or not all(isinstance(v,str) for v in strings):raise ValueError('Invalid state string table')
                state=dict(wire.get('legacy',{}))
                for row in records:
                    if not isinstance(row,list) or len(row)!=5 or any(type(i) is not int or i<0 or i>=len(strings) for i in row):
                        raise ValueError('Invalid issue state record')
                    fields=[strings[i] for i in row];key=sha(json.dumps(fields[:4],separators=(',',':')).encode())
                    if key in state and state[key]!=fields[4]:raise ValueError('Conflicting first-seen records')
                    state[key]=fields[4];identities[key]=fields[:4]
            else:state=wire  # Read the earlier hash/date format without resetting it.
            if not isinstance(state,dict) or any(not re.fullmatch(r'[a-f0-9]{64}',k) for k in state):
                raise ValueError('Invalid issue state')
            for value in state.values():date.fromisoformat(value)
            result=FirstSeenState(state);result.identities=identities
            return result,match['html_url']
        if len(values)<100:break
    return {},None


class FirstSeenState(dict):
    """Date lookup plus lossless identities retained for resolved findings."""
    identities=None


def bootstrap_context():
    if os.environ.get('GITHUB_EVENT_NAME')!='pull_request':return False
    event=read(os.environ['GITHUB_EVENT_PATH'])['pull_request']['head']
    return event['ref']==BOOTSTRAP_BRANCH and event['repo']['full_name']==REPOSITORY


def validate_exceptions(value,root=ROOT,on=None,bootstrap=False):
    on=on or today()
    validator=Draft202012Validator(read(root/'security/vulnerability-exceptions.schema.json'),format_checker=FormatChecker())
    errors=list(validator.iter_errors(value))
    if errors:raise ValueError('Malformed vulnerability exception: '+errors[0].message)
    seen=set()
    for entry in value['exceptions']:
        created=date.fromisoformat(entry['createdOn']);expires=date.fromisoformat(entry['expires'])
        if created>on or expires<on or not 0<=(expires-created).days<=90:
            raise ValueError('Expired/invalid exception lifetime: '+entry['vulnerability'])
        if entry['approvedBy']=='pending-owner' and not bootstrap:
            raise ValueError('Pending-owner exceptions are valid only on the owner WO-32 PR branch')
        key=tuple(entry[k] for k in ('target','package','version','vulnerability'))
        if key in seen:raise ValueError('Duplicate vulnerability exception')
        seen.add(key)
    return value['exceptions']


def evaluate(result,exceptions,kev,state=None,on=None,bootstrap=False,root=ROOT):
    on=on or today()
    fallback=min(INITIAL_DATE,on) if state is None else on
    identities=dict(getattr(state,'identities',None) or {})
    state=dict(state or {})
    entries=validate_exceptions(exceptions,root,on,bootstrap)
    kev_ids={v['cveID'] for v in kev['vulnerabilities']}
    if not isinstance(kev.get('catalogVersion'),str) or not isinstance(kev.get('vulnerabilities'),list):
        raise ValueError('Invalid KEV catalog')
    output=[]
    for raw in result['findings']:
        value=dict(raw)
        # Missing issues cannot continually reset pre-existing risk's grace clock.
        # New PR introductions are immediate; the initial pinned baseline has a fixed anchor.
        first=date.fromisoformat(state.get(value['key'],(on if value['introduced'] else fallback).isoformat()))
        if first>on:raise ValueError('Future first-seen date')
        state[value['key']]=first.isoformat();value['firstSeen']=first.isoformat()
        fields=[value[k] for k in ('target','package','version','vulnerability')]
        if value['key'] in identities and identities[value['key']]!=fields:raise ValueError('Finding identity collision')
        identities[value['key']]=fields
        value['kev']=bool(set(value['aliases']) & kev_ids)
        value['blockReason']='KEV' if value['kev'] else 'Critical with fix' if value['severity']=='Critical' and value['fixAvailable'] else (
            'High introduced by PR' if value['introduced'] else 'High with fix aged 14 days') if (
                value['severity']=='High' and value['fixAvailable'] and (value['introduced'] or (on-first).days>=14)) else ''
        allowed=next((e for e in entries if all(e[k]==value[k] for k in ('target','package','version','vulnerability'))),None)
        value['exception']=allowed;value['blocked']=bool(value['blockReason'] and not allowed)
        output.append(value)
    report=result|dict(findings=output,firstSeen=state,identityState=identities,kev=dict(catalogVersion=kev['catalogVersion'],sha256=sha(json.dumps(kev,sort_keys=True).encode())),
                       status='failed' if any(v['blocked'] for v in output) else 'passed')
    proposed=[]
    for value in output:
        if not value['blockReason'] or value['exception']:continue
        proposed.append({k:value[k] for k in ('target','package','version','vulnerability')}|dict(
            reason='Pending owner review: '+value['blockReason']+'; record risk, mitigation and removal work order.',
            approvedBy='pending-owner',createdOn=on.isoformat(),expires='2026-12-31'))
    report['proposedExceptions']=dict(version=1,exceptions=proposed)
    return report


def safe(value):
    value=html.escape(str(value),quote=False).replace('`','\\`').replace('|','\\|').replace('\n',' ').replace('\r',' ')
    # Prevent user/org notifications while keeping repository@digest copyable.
    return re.sub(r'(?<!\w)@','＠',value)


def markdown(report):
    lines=['# Supply-chain scan: '+report['status'],'',
           'Scope: pinned Linux amd64 inputs; static scanning only. No live environment changes.','',
           '| Target | Scan coverage | Findings | Blocking |', '| --- | --- | ---: | ---: |']
    for item in report['inventory']['images']:
        values=[v for v in report['findings'] if v['target']==item['target']]
        lines.append('| `'+safe(item['target'])+'` | '+safe(item['source'].split(':',1)[0])+' | '+str(len(values))+' | '+str(sum(v['blocked'] for v in values))+' |')
    lines.extend(['','Built image coverage:'])
    for item in report['inventory']['coverage']:
        if item['mode']=='pinned-inputs-only':lines.append('- `'+safe(item['entry'])+'`: pinned inputs only; the unpublished built archive was unavailable.')
    lines.extend(['','| Target | Package/version | Vulnerability | Severity | Fix | KEV | First seen | Gate |',
                  '| --- | --- | --- | --- | --- | --- | --- | --- |'])
    for value in sorted(report['findings'],key=lambda v:(v['target'],v['package'],v['vulnerability'])):
        gate='Exception until '+value['exception']['expires'] if value['exception'] else value['blockReason'] or 'Report only'
        lines.append('| '+' | '.join(safe(v) for v in (value['target'],value['package']+' '+value['version'],value['vulnerability'],
                      value['severity'],value['fixAvailable'],value['kev'],value['firstSeen'],gate))+' |')
    return '\n'.join(lines)+'\n'


def report_files(report,out):
    body=markdown(report)
    write(out/'report.json',report|{'markdown':body});(out/'report.md').write_text(body,encoding='utf-8')
    write(out/'proposed-exceptions.json',report['proposedExceptions'])
    summary=os.environ.get('GITHUB_STEP_SUMMARY')
    if summary:
        with open(summary,'a',encoding='utf-8') as stream:stream.write(body[:500000])


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=['inventory','sbom','scan','evaluate','report','watch'])
    parser.add_argument('--root',type=Path,default=ROOT);parser.add_argument('--out',type=Path,default=ROOT/'.build/supply-chain')
    parser.add_argument('--cache',type=Path,default=ROOT/'.build/supply-chain-cache')
    parser.add_argument('--tools',type=Path,default=ROOT/'.build/ci-tools/bin')
    parser.add_argument('--base');parser.add_argument('--full',action='store_true');parser.add_argument('--publish',action='store_true')
    parser.add_argument('--title',default=TITLE);parser.add_argument('--run-url')
    args=parser.parse_args();args.out.mkdir(parents=True,exist_ok=True)
    try:
        if args.action=='inventory':write(args.out/'inventory.json',inventory(args.root,args.base,args.full))
        elif args.action in ('sbom','scan'):
            tools=verify_tools(args.tools,args.root);plan=read(args.out/'inventory.json')
            if args.action=='sbom':sboms(plan,tools,args.cache,args.out)
            else:scan(plan,tools,args.cache,args.out,args.root)
        elif args.action=='evaluate':
            raw=fetch('https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json')
            (args.out/'kev.json').write_bytes(raw);print('CISA KEV SHA256: '+sha(raw))
            state,link=previous_state()
            value=evaluate(read(args.out/'findings.json'),read(args.root/'security/vulnerability-exceptions.json'),
                           json.loads(raw),state if link else None,bootstrap=bootstrap_context(),root=args.root)
            value['kev']['downloadSHA256']=sha(raw);value['trackingIssue']=link
            report_files(value,args.out)
            return int(value['status']!='passed')
        elif args.action=='report':
            value=read(args.out/('watch.json' if args.title==WATCH_TITLE else 'report.json'))
            if args.publish:
                # Only the issues:write reporting job calls this branch. No scanner is loaded or run.
                if os.environ.get('GITHUB_REF')!='refs/heads/main' or os.environ.get('GITHUB_REPOSITORY')!=REPOSITORY:
                    raise ValueError('Issue reporting requires trusted main in Twinfra')
                from supply_chain_report import publish
                print(publish(value,args.title,args.run_url,os.environ['GH_TOKEN']))
            else:report_files(value,args.out)
        else:
            from supply_chain_watch import watch
            value=watch(args.root,verify_tools(args.tools,args.root),args.out,args.cache)
            write(args.out/'watch.json',value);(args.out/'watch.md').write_text(value['markdown'],encoding='utf-8')
        return 0
    except (ValueError,OSError,KeyError) as error:
        print('Supply-chain failure: '+str(error),file=sys.stderr);return 1


if __name__=='__main__':raise SystemExit(main())
