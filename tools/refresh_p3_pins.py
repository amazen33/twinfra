#!/usr/bin/env python3
"""WO-34 reviewed patch-only dev pins; production and retained WSL stay unchanged."""
import copy
from datetime import datetime,timezone,timedelta
import hashlib
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'tools'),str(ROOT/'tools/ci')]
from platform_pg_image import Export
from licence_inventory import enumerate_inputs

VERSION='1.5.18'
PIN='sha256:451a0cc80a4f464e1c2d2f77fbb40ac37d01902d58ca3630ac5eaea9c92f12da'
LICENSE_SHA='53d77ec9ad68650079486272d5bd095724c82a66303a12405edd1c59eb2b5477'


def save(path,value):path.write_text(json.dumps(value,indent=2)+'\n',encoding='utf-8',newline='\n')


def refresh():
    data=ROOT/'.build/wo-34'
    release=next(v for v in json.loads((data/'releases/ministackorg-ministack.json').read_text()) if v['tag_name']=='v'+VERSION)
    when=datetime.fromisoformat(release['published_at'].replace('Z','+00:00'))
    if datetime.now(timezone.utc)-when<timedelta(days=14):raise ValueError('MiniStack patch is not age eligible')
    published=json.loads((data/'ministack-1.5.18-hub.json').read_text())
    if published['digest']!=PIN:raise ValueError('Publisher digest differs')
    license_bytes=(data/'ministack-1.5.18-LICENSE').read_bytes()
    if hashlib.sha256(license_bytes).hexdigest()!=LICENSE_SHA:raise ValueError('Verified primary MIT licence differs')
    configs=[]
    for name in ('before','after'):
        source=Export(data/('ministack-'+name+'.oci.tar'))
        try:
            if name=='after' and source.root_digest!=PIN:raise ValueError('Candidate archive differs')
            configs.append(json.loads(source.blob(source.manifest['config']))['config'])
        finally:source.archive.close()
    for key in ('User','Entrypoint','Cmd','WorkingDir'):
        if configs[0].get(key)!=configs[1].get(key):raise ValueError('MiniStack execution contract changed: '+key)
    env=lambda c:{v for v in c.get('Env',[]) if not v.startswith('MINISTACK_VERSION=')}
    if env(configs[0])!=env(configs[1]):raise ValueError('MiniStack environment behavior changed')
    path=ROOT/'deploy/common/images.lock.json';lock=json.loads(path.read_text())
    old=copy.deepcopy(lock['images']['ministack'])
    if old.get('release') not in ('docker.io/ministackorg/ministack:1.5.17','docker.io/ministackorg/ministack:'+VERSION):
        raise ValueError('MiniStack refresh must stay on the approved 1.5 minor')
    lock['images']['ministack'].update(release='docker.io/ministackorg/ministack:'+VERSION,
        source='docker.io/ministackorg/ministack@'+PIN,canonical='registry.twinfra.example.com/docker.io/ministackorg/ministack@'+PIN,
        digest=PIN,digestSource='https://registry-1.docker.io/v2/ministackorg/ministack/manifests/'+VERSION,
        publicationSource='https://hub.docker.com/v2/repositories/ministackorg/ministack/tags/'+VERSION,
        publishedAt=published['last_updated'],releasePublishedAt=release['published_at'],
        releaseSource='https://github.com/ministackorg/ministack/releases/tag/v'+VERSION,verifiedOn='2026-10-14')
    save(path,lock)
    path=ROOT/'deploy/common/bootstrap-images.lock.json';bootstrap=json.loads(path.read_text())
    previous=bootstrap['images']['pause']
    if previous['release'].endswith(':3.10.1'):
        bootstrap['referenceOnlyImages']=[previous|{'purpose':'Unchanged production/default profile alias; excluded from dev staging.'}]
    bootstrap['images']['pause']=copy.deepcopy(bootstrap['images']['kubeadm-pause'])
    save(path,bootstrap)
    # Known distribution evidence gap keeps its original owner/deadline. This is
    # not a claim of a new legal SBOM review; the open item remains reported.
    path=ROOT/'security/licence-register.json';register=json.loads(path.read_text())
    old_key='oci-image|docker.io/ministackorg/ministack|sha256:11d7308bfc75029d55625b9525e84a2401431ed1ff2148c6311800ff5009ae9c'
    new_key='oci-image|docker.io/ministackorg/ministack|'+PIN
    existing={v['id']:v for v in register['components']}
    if new_key not in existing:
        entry=copy.deepcopy(existing[old_key]);entry.update(id=new_key,version=PIN,integrities=[PIN],
            licenceSource='https://raw.githubusercontent.com/ministackorg/ministack/v'+VERSION+'/LICENSE',
            verifiedOn='2026-10-14',recordedOn='2026-10-14')
        register['components'].append(entry)
        bp=ROOT/'security/licence-baseline.json';baseline=json.loads(bp.read_text())
        before=next(v for v in baseline['findings'] if v['id']=='image-sbom:'+old_key)
        baseline['findings'].append(copy.deepcopy(before)|{'id':'image-sbom:'+new_key,'component':new_key});save(bp,baseline)
    observed,_=enumerate_inputs(ROOT)
    for entry in register['components']:
        if entry['id'] in observed and entry['name'] in ('docker.io/ministackorg/ministack','registry.k8s.io/pause'):
            entry['locations']=observed[entry['id']]['locations']
    register['components'].sort(key=lambda v:v['id']);save(path,register)


if __name__=='__main__':refresh()
