#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Strict offline WO-09 schemas and security, including the disabled reference."""
import argparse
import gzip
import json
import os
from pathlib import Path
import subprocess
import yaml
from platform_backups import ROOT, COMMON, backup_objects, node_objects, node_exception, cluster_patch
from platform_backup_actions import restore_manifest
from platform_dev import database, controllers
from manifest_contract import audit_objects, podspec


def run(args):
    result=subprocess.run(list(map(str,args)),capture_output=True,text=True,encoding='utf-8')
    if result.returncode:raise ValueError(result.stdout+result.stderr)
    print(result.stdout,end='')


def validate(args):
    args.build.mkdir(parents=True,exist_ok=True)
    source=gzip.decompress((COMMON/'vendor/cnpg.yaml.gz').read_bytes())
    schemas=args.build/'schemas';schemas.mkdir(exist_ok=True)
    plugin=backup_objects()
    # Extract served CRDs from the exact pinned release, no schema downloading.
    for o in list(yaml.safe_load_all(source))+plugin:
        if not o or o['kind']!='CustomResourceDefinition':continue
        for v in o['spec']['versions']:
            if v.get('served'):
                path=schemas/(o['spec']['names']['kind'].lower()+'_'+v['name']+'.json')
                path.write_text(json.dumps(v['schema']['openAPIV3Schema']),encoding='utf-8')
    restore=restore_manifest('2026-10-15T00:00:00Z')
    cluster=cluster_patch(next(v for v in database() if v['kind']=='Cluster'))
    docs=plugin+[cluster]+restore
    platform=args.build/'reference.yaml';platform.write_text(yaml.safe_dump_all(docs,sort_keys=False),encoding='utf-8')
    node=args.build/'node.yaml';node.write_text(yaml.safe_dump_all(node_objects(),sort_keys=False),encoding='utf-8')
    policy=args.build/'exception.json';policy.write_text(json.dumps(node_exception()),encoding='utf-8')
    node_report=audit_objects([v for v in node_objects() if podspec(v)],node_exception())
    report=audit_objects([v for v in docs if podspec(v)],{'registry':'registry.twinfra.example.com'})
    if node_report['violations'] or report['violations']:raise ValueError(str(node_report['violations']+report['violations']))
    run([args.conftest,'test','--namespace','twinfra_platform','--policy',ROOT/'tests/ci/policy/platform-restricted.rego',platform])
    run([args.conftest,'test','--namespace','twinfra_backup','--policy',ROOT/'tests/ci/policy/backup-node.rego','--data',policy,node])
    templates=[COMMON/'schemas/{{.ResourceKind}}.json',args.schemas/'{{.ResourceKind}}.json',
               ROOT/'module-2/schemas/{{.Group}}/{{.ResourceKind}}_{{.ResourceAPIVersion}}.json',
               ROOT/'module-2/schemas/{{.ResourceKind}}_{{.ResourceAPIVersion}}.json',
               COMMON/'backup/schemas/{{.ResourceKind}}_{{.ResourceAPIVersion}}.json',schemas/'{{.ResourceKind}}_{{.ResourceAPIVersion}}.json']
    flags=[v for t in templates for v in ('-schema-location',Path(os.path.relpath(t)).as_posix() if os.name=='nt' else t.as_posix())]
    run([args.kubeconform,'-strict','-summary','-kubernetes-version','1.36.5',*flags,platform,node])
    print('PASS: WO-09 disabled references and exact node exception; no live operations')


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--schemas',type=Path,required=True)
    parser.add_argument('--kubeconform',default='kubeconform');parser.add_argument('--conftest',default='conftest')
    parser.add_argument('--build',type=Path,default=ROOT/'.build/backup-validation')
    validate(parser.parse_args())
