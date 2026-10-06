#!/usr/bin/env python3
"""Static SSoT checks complementary to kubeconform. Inventory mode never grants approval."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
from manifest_contract import audit_objects, podspec

ROOT = Path(__file__).resolve().parents[1]


def load_policy():
    ssot = yaml.safe_load((ROOT / 'vcloud-ssot.yaml').read_text())
    decision = ssot['security']['nodeHostMountException']
    path = ROOT / decision['policyFile']
    content = path.read_bytes()
    if hashlib.sha256(content).hexdigest() != decision['policySHA256']:
        raise ValueError('Node exception policy differs from the approved SSoT hash')
    policy = json.loads(content)
    if decision['status'] != 'approved':
        policy['status'] = 'unapproved'
    return policy


def audit(paths, mode='workloads'):
    objects = []
    for path in paths:
        objects.extend(yaml.safe_load_all(path.read_text(encoding='utf-8-sig')))
    return audit_objects(objects, load_policy(), mode)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('paths', type=Path, nargs='+')
    parser.add_argument('--mode', choices=['workloads', 'control-plane'], default='workloads')
    parser.add_argument('--inventory', type=Path, help='Write JSON and return success to collect evidence; does not approve findings')
    args = parser.parse_args()
    result = audit(args.paths, args.mode)
    if args.inventory:
        args.inventory.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8', newline='\n')
    print(f'SSoT contract: {result["status"]}; {len(result["violations"])} findings')
    for finding in result['violations']:
        print(finding)
    return 0 if args.inventory or not result['violations'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
