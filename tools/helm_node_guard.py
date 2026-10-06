#!/usr/bin/env python3
"""Helm post-renderer: validate the actual Cilium mutation before Helm applies it."""
import argparse
import subprocess
import sys
import yaml
from module2 import MODULE, audit_objects, flatten, load_policy, normalize_pods, verify_bundle


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--kubeconform',default='kubeconform')
    args = parser.parse_args()
    source = sys.stdin.read()
    try:
        verify_bundle()
        objects = list(flatten(yaml.safe_load_all(source)))
        report = audit_objects(normalize_pods(objects), load_policy())
        if report['violations']:
            raise ValueError('; '.join(report['violations']))
        config = next(o for o in objects if o['kind'] == 'ConfigMap' and o['metadata']['name'] == 'cilium-config')['data']
        if any(config.get(k) != v for k,v in {'kube-proxy-replacement':'true','enable-host-firewall':'true','enable-bandwidth-manager':'true','routing-mode':'native'}.items()):
            raise ValueError('Required native/eBPF Cilium features missing in actual Helm output')
        command = [args.kubeconform,'-strict','-summary','-schema-location',str(MODULE / 'schemas/{{.Group}}/{{.ResourceKind}}_{{.ResourceAPIVersion}}.json'),'-schema-location',str(MODULE / 'schemas/{{.ResourceKind}}_{{.ResourceAPIVersion}}.json')]
        result = subprocess.run(command,input=source,text=True,capture_output=True)
        if result.returncode:
            raise ValueError(result.stdout + result.stderr)
        print(result.stdout.strip(),file=sys.stderr)
        sys.stdout.write(source)
        return 0
    except (ValueError, OSError, KeyError, StopIteration) as error:
        print('Cilium post-render guard: ' + str(error),file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
