#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Owner-only Secret stdin helper; no credential arguments, files, env or output."""
import argparse
import base64
import getpass
import hashlib
import json
from pathlib import Path
import subprocess

CONTEXT='twinfra-dev-cairo-1'
NAMESPACE='twinfra-platform-services'
NAME='twinfra-backup-s3'


def kubectl(args, data=None):
    result=subprocess.run(['kubectl','--context',CONTEXT,*args],input=data,capture_output=True)
    if result.returncode:raise ValueError('Kubernetes Secret operation failed; details suppressed')
    return result.stdout


def create(certificate):
    raw=certificate.read_bytes()
    if len(raw)>65536 or b'PRIVATE KEY' in raw or not raw.startswith(b'-----BEGIN CERTIFICATE-----'):
        raise ValueError('Provide only the public CMS certificate')
    access=getpass.getpass('R2 access key ID (hidden): ')
    secret=getpass.getpass('R2 secret access key (hidden): ')
    if not access or not secret:raise ValueError('Empty credentials refused')
    fields={'ACCESS_KEY_ID':access.encode(),'ACCESS_SECRET_KEY':secret.encode(),'CMS_CERTIFICATE':raw}
    value={'apiVersion':'v1','kind':'Secret','metadata':{'name':NAME,'namespace':NAMESPACE},'type':'Opaque',
           'data':{k:base64.b64encode(v).decode() for k,v in fields.items()}}
    # create, not apply: no last-applied credential annotation; no silent rotation.
    kubectl(['create','-f','-'],json.dumps(value).encode())
    print('Created '+NAME+'; public certificate SHA-256 '+hashlib.sha256(raw).hexdigest())


def copy_restore():
    value=json.loads(kubectl(['get','secret',NAME,'-n',NAMESPACE,'-o','json']))
    target={'apiVersion':'v1','kind':'Secret','metadata':{'name':NAME,'namespace':'twinfra-restore-drill'},'type':'Opaque',
            'data':{k:value['data'][k] for k in ('ACCESS_KEY_ID','ACCESS_SECRET_KEY')}}
    kubectl(['create','-f','-'],json.dumps(target).encode())
    print('Copied the two S3 fields into the isolated restore namespace via stdin')


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--context',required=True,choices=[CONTEXT])
    group=parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--certificate',type=Path);group.add_argument('--copy-to-restore',action='store_true')
    args=parser.parse_args()
    try:
        if args.copy_to_restore:copy_restore()
        else:create(args.certificate)
        return 0
    except (ValueError,OSError,KeyError):
        print('Secret operation failed; credential and transport output suppressed');return 1


if __name__=='__main__':raise SystemExit(main())
