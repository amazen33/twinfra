"""WO-34 read-only, digest-verified public registry data export. MIT."""
import io
import json
from pathlib import Path
import re
import tarfile
import urllib.error
import urllib.parse
import urllib.request
from platform_oci import digest, encoded, export_dockerhub


def export_public(reference, destination):
    """Read a digest-pinned public registry graph; never import or execute it."""
    if reference.startswith('docker.io/'):
        return export_dockerhub(reference, destination)
    match=re.fullmatch(r'(quay\.io|registry\.k8s\.io|ghcr\.io)/([a-z0-9._/-]+)@(sha256:[a-f0-9]{64})',reference)
    if not match:raise ValueError('Unsupported public registry or unpinned reference')
    host,repo,pin=match.groups();token=None;blobs={}
    accept='application/vnd.oci.image.index.v1+json,application/vnd.docker.distribution.manifest.list.v2+json,application/vnd.oci.image.manifest.v1+json,application/vnd.docker.distribution.manifest.v2+json'
    def get(kind,expected,size=None):
        nonlocal token
        url='https://'+host+'/v2/'+repo+'/'+kind+'/'+expected
        headers={'Accept':accept}
        if token:headers['Authorization']='Bearer '+token
        try:
            with urllib.request.urlopen(urllib.request.Request(url,headers=headers),timeout=120) as response:raw=response.read()
        except urllib.error.HTTPError as error:
            if error.code!=401 or token:raise
            attrs=dict(re.findall(r'(\w+)="([^"]+)"',error.headers.get('WWW-Authenticate','')))
            realm=attrs['realm']
            if not realm.startswith('https://') or urllib.parse.urlsplit(realm).hostname!=host:
                raise ValueError('Unexpected public registry auth realm')
            query=urllib.parse.urlencode({'service':attrs.get('service',host),'scope':'repository:'+repo+':pull'})
            with urllib.request.urlopen(realm+'?'+query,timeout=60) as response:value=json.load(response)
            token=value.get('token') or value['access_token']
            return get(kind,expected,size)
        if digest(raw)!=expected or size is not None and len(raw)!=size:raise ValueError('Public registry checksum/size mismatch')
        blobs['blobs/sha256/'+expected.split(':')[1]]=raw;return raw
    raw=get('manifests',pin);value=json.loads(raw)
    root={'digest':pin,'size':len(raw),'mediaType':value['mediaType']};seen={pin}
    while 'manifests' in value:
        choices=[d for d in value['manifests'] if d.get('platform',{}).get('os')=='linux' and d.get('platform',{}).get('architecture')=='amd64']
        if len(choices)!=1 or choices[0]['digest'] in seen:raise ValueError('Unique acyclic amd64 manifest required')
        child=choices[0];seen.add(child['digest']);value=json.loads(get('manifests',child['digest'],child['size']))
    config=json.loads(get('blobs',value['config']['digest'],value['config']['size']))
    if (config.get('os'),config.get('architecture'))!=('linux','amd64'):raise ValueError('Linux amd64 registry input required')
    for layer in value['layers']:get('blobs',layer['digest'],layer['size'])
    blobs.update({'oci-layout':encoded({'imageLayoutVersion':'1.0.0'}),'index.json':encoded({'schemaVersion':2,'manifests':[root]})})
    destination=Path(destination);destination.parent.mkdir(parents=True,exist_ok=True)
    partial=destination.with_name(destination.name+'.part')
    try:
        with tarfile.open(partial,'w') as archive:
            for name,raw in sorted(blobs.items()):
                item=tarfile.TarInfo(name);item.size=len(raw);item.mode=0o644;item.mtime=0
                archive.addfile(item,io.BytesIO(raw))
        partial.replace(destination)
    finally:partial.unlink(missing_ok=True)

