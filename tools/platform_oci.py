"""Read-only public registry export for checksum-pinned offline image assembly. MIT."""
import hashlib
import io
import json
from pathlib import Path
import tarfile
import urllib.request

def encoded(value): return json.dumps(value,sort_keys=True,separators=(',',':')).encode()
def digest(raw): return 'sha256:'+hashlib.sha256(raw).hexdigest()

def export_ghcr(reference, destination):
    if not reference.startswith('ghcr.io/') or '@sha256:' not in reference:
        raise ValueError('Only immutable public GHCR inputs are accepted')
    repo,sha=reference.removeprefix('ghcr.io/').split('@')
    token=json.load(urllib.request.urlopen('https://ghcr.io/token?service=ghcr.io&scope=repository:'+repo+':pull'))['token']
    blobs={}
    def get(kind, expected):
        request=urllib.request.Request('https://ghcr.io/v2/'+repo+'/'+kind+'/'+expected,
            headers={'Authorization':'Bearer '+token,'Accept':'application/vnd.oci.image.index.v1+json, application/vnd.docker.distribution.manifest.list.v2+json, application/vnd.oci.image.manifest.v1+json, application/vnd.docker.distribution.manifest.v2+json'})
        raw=urllib.request.urlopen(request,timeout=120).read()
        if digest(raw)!=expected: raise ValueError('OCI checksum mismatch')
        blobs['blobs/sha256/'+expected.split(':')[1]]=raw
        return raw
    raw=get('manifests',sha);value=json.loads(raw)
    root={'digest':sha,'size':len(raw),'mediaType':value['mediaType']}
    while 'manifests' in value:
        choices=[d for d in value['manifests'] if d.get('platform',{}).get('os')=='linux' and d.get('platform',{}).get('architecture')=='amd64']
        if len(choices)!=1:raise ValueError('Single amd64 input required')
        value=json.loads(get('manifests',choices[0]['digest']))
    for item in [value['config'],*value['layers']]:get('blobs',item['digest'])
    blobs['oci-layout']=encoded({'imageLayoutVersion':'1.0.0'})
    blobs['index.json']=encoded({'schemaVersion':2,'manifests':[root]})
    destination=Path(destination);destination.parent.mkdir(parents=True,exist_ok=True)
    with tarfile.open(destination,'w') as archive:
        for name,raw in sorted(blobs.items()):
            entry=tarfile.TarInfo(name);entry.size=len(raw);entry.mode=0o644;archive.addfile(entry,io.BytesIO(raw))
