#!/usr/bin/env python3
"""Inspect every Go ELF in a pinned image as data; no image binary executes."""
import argparse
import gzip
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import subprocess
import sys
import tarfile

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tools'))
from registry_export import export_public
from platform_pg_image import Export


def go_files(source):
    files={};links={}
    for layer in source.manifest['layers']:
        with tarfile.open(fileobj=io.BytesIO(source.blob(layer)),mode='r:*') as stream:
            for item in stream:
                name=item.name.removeprefix('./').lstrip('/');path=PurePosixPath(name)
                if '..' in path.parts or '\\' in name:
                    raise ValueError('Unsafe image path')
                if path.name.startswith('.wh.'):
                    victim=str(path.parent/path.name.removeprefix('.wh.'))
                    prefix=str(path.parent).removeprefix('.')+'/'
                    for value in list(files):
                        if (path.name=='.wh..wh..opq' and value.startswith(prefix.lstrip('/'))) or value==victim or value.startswith(victim+'/'):
                            files.pop(value,None);links.pop(value,None)
                    continue
                files.pop(name,None);links.pop(name,None)
                if item.isfile():
                    raw=stream.extractfile(item).read()
                    if raw.startswith(b'\x7fELF') and b'\xff Go buildinf:' in raw:
                        files[name]=raw
                elif item.islnk():
                    target=item.linkname.removeprefix('./').lstrip('/')
                    if '..' in PurePosixPath(target).parts:raise ValueError('Unsafe image hardlink')
                    links[name]=target
    for name,target in links.items():
        if target in files:files[name]=files[target]
    return files


def messages(raw):
    decoder=json.JSONDecoder();position=0
    while position<len(raw):
        if raw[position].isspace():position+=1;continue
        value,position=decoder.raw_decode(raw,position)
        yield value


def classify(raw):
    vulnerabilities={};findings={}
    for message in messages(raw):
        if 'osv' in message:
            value=message['osv'];vulnerabilities[value['id']]=value.get('aliases',[])
        if 'finding' not in message:continue
        value=message['finding'];trace=value.get('trace',[])
        if not trace:raise ValueError('Go finding has no module trace')
        frame=trace[0];key=(value['osv'],frame.get('module'),frame.get('version'))
        entry=findings.setdefault(key,dict(osv=value['osv'],module=frame.get('module'),version=frame.get('version'),
                                          fixedVersion=value.get('fixed_version'),symbols=set()))
        if frame.get('function'):
            entry['symbols'].add(frame.get('package','')+'.'+frame.get('receiver','')+'.'+frame['function'])
    result=[]
    for entry in findings.values():
        entry['aliases']=vulnerabilities.get(entry['osv'],[])
        entry['symbols']=sorted(entry['symbols'])
        entry['classification']='affected-symbols-present' if entry['symbols'] else 'module-only-binary-finding'
        result.append(entry)
    return sorted(result,key=lambda x:(x['osv'],x['module'] or '',x['version'] or ''))


def triage(image,scanner,out):
    pin=json.loads((ROOT/'tools/ci/toolchain.lock.json').read_text())['builds']['govulncheck']['binarySHA256']
    if not pin or hashlib.sha256(scanner.read_bytes()).hexdigest()!=pin:
        raise ValueError('govulncheck binary is not the reviewed pin')
    out.mkdir(parents=True,exist_ok=True);archive=out/'image.oci.tar';export_public(image,archive)
    source=Export(archive)
    try:files=go_files(source)
    finally:source.archive.close()
    report=dict(image=image,scannerSHA256=pin,imageCodeExecuted=False,
                interpretation='Affected symbols are present; source mode is required for call stacks and reachability.',binaries=[])
    seen={}
    for path,raw in sorted(files.items()):
        digest=hashlib.sha256(raw).hexdigest()
        if digest not in seen:
            binary=out/(digest+'.data');binary.write_bytes(raw);binary.chmod(0o400)
            run=subprocess.run([str(scanner.resolve()),'-mode=binary','-json',str(binary.resolve())],capture_output=True,text=True)
            (out/(digest+'.govulncheck.json.gz')).write_bytes(gzip.compress(run.stdout.encode(),mtime=0))
            (out/(digest+'.log')).write_text(run.stderr)
            if run.returncode:raise ValueError('Go binary inspection failed: '+path)
            seen[digest]=classify(run.stdout)
            binary.unlink()
        report['binaries'].append(dict(path='/'+path,sha256=digest,findings=seen[digest]))
    (out/'summary.json').write_text(json.dumps(report,indent=2)+'\n')
    archive.unlink()
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--image',required=True);parser.add_argument('--scanner',required=True,type=Path)
    parser.add_argument('--out',required=True,type=Path);args=parser.parse_args()
    triage(args.image,args.scanner,args.out)
