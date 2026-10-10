#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""OWNER ONLY: create missing dev credentials directly in Kubernetes, never print them.

TLS certificates/keys are supplied separately by the owner. Does not initialize
OpenBao or create users. All generated values remain in process memory/API Secret.
"""
import argparse
import base64
import json
import secrets
import subprocess


def required():
    return {'twinfra-argocd-cache':{'auth':secrets.token_urlsafe(48)},
            'twinfra-keycloak-db':{'username':'keycloak','password':secrets.token_urlsafe(48)},
            'twinfra-openbao-db':{'username':'openbao','password':secrets.token_urlsafe(48)},
            'twinfra-keycloak-admin':{'username':'twinfra-admin','password':secrets.token_urlsafe(48)},
            'twinfra-console-oidc':{'client_secret':secrets.token_urlsafe(48),'session_secret':secrets.token_urlsafe(48)},
            'twinfra-perses-key':{'encryption-key':secrets.token_hex(16)}}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--context',required=True)
    parser.add_argument('--apply',action='store_true')
    args=parser.parse_args()
    if args.context!='twinfra-dev-cairo-1':raise ValueError('Wrong dev context')
    for name,values in required().items():
        if not args.apply:print('PLAN: create missing Secret '+name);continue
        command=['kubectl','--context',args.context,'-n','twinfra-platform-services']
        status=subprocess.run(command+['get','secret',name,'--ignore-not-found','-o','name'],capture_output=True,text=True,check=True)
        if status.stdout.strip():print('Existing Secret preserved: '+name);continue
        secret_type='kubernetes.io/basic-auth' if name in ('twinfra-keycloak-db','twinfra-openbao-db') else 'Opaque'
        data={'apiVersion':'v1','kind':'Secret','metadata':{'name':name,'namespace':'twinfra-platform-services','labels':{'twinfra.io/environment':'dev','twinfra.io/region':'cairo-1','twinfra.io/component':'bootstrap'}},'type':secret_type,
              'data':{k:base64.b64encode(v.encode()).decode() for k,v in values.items()}}
        subprocess.run(command+['create','-f','-'],input=json.dumps(data),text=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,check=True)
        print('Created missing Secret: '+name)


if __name__=='__main__':main()
