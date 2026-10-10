"""Verify and read a vendored manifest without executing it. MIT."""
import gzip
import hashlib
import json
import yaml
from pathlib import Path


def argocd_api(root):
    """Derive the API server supplement from the preserved pinned full install."""
    original=root/'deploy/kustomize/base/argocd/install.yaml'
    objects=[o for o in yaml.safe_load_all(original.read_text(encoding='utf-8')) if o]
    return yaml.safe_dump_all([o for o in objects if
        o['metadata']['name'] in ('argocd-server','argocd-server-metrics') and
        o['kind'] in ('ServiceAccount','Role','ClusterRole','RoleBinding',
                     'ClusterRoleBinding','Service','Deployment')],sort_keys=False)


def check_argocd_api(root):
    expected=argocd_api(root)
    if (root/'deploy/common/argocd-api.yaml').read_text(encoding='utf-8')!=expected:
        raise ValueError('Argo CD API supplement differs; run tools/platform_sources.py render')

def vendor(directory, lock_path, name):
    lock=json.loads(lock_path.read_text())[name]
    compressed=(directory/(name+'.gz')).read_bytes()
    if hashlib.sha256(compressed).hexdigest()!=lock['gzipSHA256']: raise ValueError('Vendor gzip differs')
    raw=gzip.decompress(compressed)
    if hashlib.sha256(raw).hexdigest()!=lock['sourceSHA256']: raise ValueError('Upstream manifest differs')
    return [o for o in yaml.safe_load_all(raw) if o]


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command',choices=['render','check'])
    args=parser.parse_args();root=Path(__file__).resolve().parents[1]
    if args.command=='render':
        target=root/'deploy/common/argocd-api.yaml'
        target.write_text(argocd_api(root),encoding='utf-8',newline='\n')
        lock=root/'deploy/common/artifacts.lock.json'
        data=json.loads(lock.read_text())
        data['argocd-api.yaml']['sha256']=hashlib.sha256(target.read_bytes()).hexdigest()
        lock.write_text(json.dumps(data,indent=2)+'\n',encoding='utf-8')
    check_argocd_api(root)
    print('PASS: pinned Argo CD API supplement derivation')
