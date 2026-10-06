#!/usr/bin/env python3
"""Reproduce CRD JSON schemas from locked gzip inputs, without network access."""
import argparse
import copy
import gzip
import hashlib
import json
from pathlib import Path
import yaml

ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / 'module-2'


def compact(schema, branch=False):
    schema = copy.deepcopy(schema)
    schema.pop('description', None)
    if schema.get('nullable') and 'type' in schema:
        types = schema['type'] if isinstance(schema['type'],list) else [schema['type']]
        schema['type'] = list(dict.fromkeys(types + ['null']))
    schema.pop('nullable', None)
    if schema.get('x-kubernetes-preserve-unknown-fields'):
        schema['additionalProperties'] = True
    elif not branch and 'properties' in schema and 'additionalProperties' not in schema:
        schema['additionalProperties'] = False
    for key,value in list(schema.items()):
        if isinstance(value,dict):
            if key in ('properties','definitions','$defs'):
                schema[key] = {k:compact(v) for k,v in value.items()}
            else:
                schema[key] = compact(value)
        elif isinstance(value,list):
            schema[key] = [compact(v, branch=key in ('anyOf','oneOf','allOf','not')) if isinstance(v,dict) else v for v in value]
    return schema


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--write',action='store_true',help='explicitly regenerate derived schemas and update their hashes')
    args = parser.parse_args()
    lockfile = MODULE / 'artifacts.lock.json'
    lock = json.loads(lockfile.read_text())
    meta = json.loads((MODULE / 'schemas/namespace_v1.json').read_text())['properties']['metadata']
    count = 0
    for source in sorted((MODULE / 'vendor').glob('*.yaml.gz')):
        if hashlib.sha256(source.read_bytes()).hexdigest() != lock['filesSHA256'][source.relative_to(ROOT).as_posix()]:
            raise ValueError('CRD source checksum mismatch: ' + str(source))
        for crd in yaml.safe_load_all(gzip.decompress(source.read_bytes())):
            if not crd or crd.get('kind') != 'CustomResourceDefinition':
                continue
            kind,group = crd['spec']['names']['kind'],crd['spec']['group']
            if kind not in {'Cluster','Service','Application','AppProject','VerticalPodAutoscaler','ApisixRoute','ApisixUpstream','ApisixTls','CiliumNetworkPolicy','CiliumClusterwideNetworkPolicy'}:
                continue
            for version in crd['spec']['versions']:
                if not version['served'] or version.get('deprecated') or version['name'] not in ('v1','v2','v1alpha1'):
                    continue
                schema = compact(version['schema']['openAPIV3Schema'])
                schema['$schema'] = 'http://json-schema.org/draft-07/schema#'
                schema['properties']['metadata'] = meta
                schema['properties']['apiVersion'] = {'type':'string','enum':[group + '/' + version['name']]}
                schema['properties']['kind'] = {'type':'string','enum':[kind]}
                schema['required'] = list(dict.fromkeys(schema.get('required',[]) + ['apiVersion','kind','metadata']))
                path = MODULE / 'schemas' / group / (kind.lower() + '_' + version['name'] + '.json')
                content = (json.dumps(schema,separators=(',',':')) + '\n').encode()
                if args.write:
                    path.parent.mkdir(parents=True,exist_ok=True)
                    path.write_bytes(content)
                    lock['filesSHA256'][path.relative_to(ROOT).as_posix()] = hashlib.sha256(content).hexdigest()
                elif path.read_bytes() != content:
                    raise ValueError('Derived schema is not reproducible: ' + str(path))
                count += 1
    if args.write:
        lockfile.write_text(json.dumps(lock,indent=2) + '\n',encoding='utf-8',newline='\n')
    print(f'{count} CRD schemas reproduced from local locked inputs')


if __name__ == '__main__':
    main()
