#!/usr/bin/env python3
"""Generate WO-34 Go tool pins/licences from SumDB-verified inputs; no scanner execution."""
import argparse,hashlib,json,re,sys,urllib.request
from pathlib import Path
root=Path(__file__).resolve().parents[2];work=root/'.build/wo-34';cache=work/'gopath/pkg/mod/cache/download'
sys.path.insert(0,str(root/'tools/ci'))
from licence_inventory import enumerate_inputs,source_identity
def read(p):return json.loads((root/p).read_text(encoding='utf-8'))
def write(p,v):(root/p).write_text(json.dumps(v,indent=2)+'\n',encoding='utf-8',newline='\n')
data=read('tools/ci/toolchain.lock.json');sdk=json.loads((work/'go-sdk-release.json').read_text())
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--record-binary',type=Path,help='Verified public CI build receipt; sibling binary SHA256 must match')
args=parser.parse_args()
inputs=[]
for path in sorted(cache.rglob('*')):
    if not path.is_file() or path.suffix not in ('.zip','.mod','.info'):continue
    name=path.relative_to(cache).as_posix()
    if name.startswith('golang.org/x/vuln/@v/') and not path.name.startswith('v1.1.4.'):
        continue
    inputs.append({'url':'https://proxy.golang.org/'+name,'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'goBuildInput':True})
data['builds']={'govulncheck':{'module':'golang.org/x/vuln/cmd/govulncheck','version':'v1.1.4','goVersion':sdk['version'],'binarySHA256':None,
    'sdks':{x['os']+'-'+x['arch']:{'url':'https://go.dev/dl/'+x['filename'],'sha256':x['sha256'],'goBuildInput':True} for x in sdk['files']},'inputs':inputs}}
if args.record_binary:
    receipt=json.loads(args.record_binary.read_text())
    assert receipt['version']=='v1.1.4' and receipt['goVersion']==sdk['version'] and receipt['sourceInputs']==len(inputs)
    assert receipt['scannerExecuted'] is False
    binary=args.record_binary.parent/'govulncheck'
    assert hashlib.sha256(binary.read_bytes()).hexdigest()==receipt['binarySHA256']
    data['builds']['govulncheck']['binarySHA256']=receipt['binarySHA256']
write('tools/ci/toolchain.lock.json',data)
observed,_=enumerate_inputs(root)
register=read('security/licence-register.json')
register['components']=[e for e in register['components'] if e['id']!='tool|golang.org/x/vuln|v1.9.0']
old={e['id'] for e in register['components']}
for key,c in observed.items():
    if key in old:continue
    if c['ecosystem']!='tool':continue
    assert c['ecosystem']=='tool' and c['locations']==['tools/ci/toolchain.lock.json'],c
    repo=next(o['repo'] for o in c['observations'] if o.get('repo'))
    version=c['version'];ref=version
    if re.search(r'0\.\d+\.\d+-\d{14}-[a-f0-9]{12}$',version):ref=version.rsplit('-',1)[1]
    url='https://raw.githubusercontent.com/'+repo+'/'+ref+'/LICENSE'
    with urllib.request.urlopen(url,timeout=60) as response:raw=response.read()
    spdx='Apache-2.0' if b'Apache License' in raw and b'Version 2.0' in raw else 'BSD-3-Clause' if b'Redistribution and use in source and binary forms' in raw and (b'Neither the name' in raw or b'Neither the names' in raw) else None
    assert spdx,(repo,version,url)
    (work/(repo.replace('/','-')+'-'+version+'-LICENSE.txt')).write_bytes(raw)
    hashes=sorted({'sha256:'+o['sha256'] for o in c['observations'] if o.get('sha256')})
    register['components'].append({'id':key,'ecosystem':'tool','name':c['name'],'version':version,'locations':c['locations'],'spdx':spdx,'class':'build-tool','licenceSource':url,'verifiedOn':'2026-10-14','recordedOn':'2026-10-14','integrities':hashes,'unmodified':True,'notes':'WO-34: pinned source/SDK inputs for CI-only govulncheck; never copied into a runtime image.'})
    print(key,spdx,flush=True)
register['components'].sort(key=lambda e:e['id']);write('security/licence-register.json',register)
baseline=read('security/licence-baseline.json')
for row in baseline['findings']:
    if row['id']=='schema-source:tools/ci/toolchain.lock.json':row['fingerprint']=hashlib.sha256((root/'tools/ci/toolchain.lock.json').read_bytes()).hexdigest()
write('security/licence-baseline.json',baseline)


