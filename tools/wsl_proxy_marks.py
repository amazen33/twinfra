#!/usr/bin/env python3
"""Preserve Cilium proxy marks in the owned mirrored WSL lab's output chain.

WSL's WSLOUTPUT overwrites skb marks with 1. Returning early for Cilium's
two proxy mark classes preserves L7 DNS replies and endpoint identities.
This changes mark handling only; it does not add firewall ACCEPT rules.
Root/CAP_NET_ADMIN is required for the host netlink mutation. No Pod is created.
"""
import argparse
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys

PROFILE_SHA256 = 'f75dbd4c1597faa6689716bbfe40ddbd512e2c20147647cab59c09eaec8e9eea'
MASK = 0xE00
MARKS = {'vcloud:cilium-proxy-return-mark': 0xA00,
         'vcloud:cilium-proxy-upstream-mark': 0x800}


def integer(value):
    if isinstance(value, bool):
        raise ValueError('Boolean is not a packet mark or rule handle')
    return int(value, 0) if isinstance(value, str) else int(value)


def expected_match(mark):
    return {'match': {'op': '==', 'left': {'&': [{'meta': {'key': 'mark'}}, MASK]}, 'right': mark}}


def plan(state, remove=False):
    """Return an atomic nft command batch; refuse unfamiliar chain/rule shapes."""
    objects = state['nftables']
    chains = [o['chain'] for o in objects if 'chain' in o]
    if len(chains) != 1 or any(chains[0].get(k) != v for k, v in
                             {'family': 'ip', 'table': 'filter', 'name': 'WSLOUTPUT',
                              'type': 'filter', 'hook': 'output', 'policy': 'accept'}.items()):
        raise ValueError('Expected mirrored WSL IPv4 output chain was not found')
    rules = [o['rule'] for o in objects if 'rule' in o]
    owned = {tag: [] for tag in MARKS}
    overwrite = []
    for index, rule in enumerate(rules):
        if any(rule.get(k) != v for k, v in {'family': 'ip', 'table': 'filter', 'chain': 'WSLOUTPUT'}.items()):
            raise ValueError('Unexpected rule scope')
        statements = [e for e in rule['expr'] if set(e) != {'counter'}]
        if {'mangle': {'key': {'meta': {'key': 'mark'}}, 'value': 1}} in statements:
            overwrite.append(index)
        tag = rule.get('comment')
        if tag not in MARKS:
            continue
        if statements != [expected_match(MARKS[tag]), {'return': None}]:
            raise ValueError('Owned rule has an unexpected predicate or verdict: ' + tag)
        handle = integer(rule['handle'])
        if handle <= 0:
            raise ValueError('Invalid owned nft rule handle')
        owned[tag].append((index, handle))
    if not remove and len(overwrite) != 1:
        raise ValueError('Expected one WSL mark=1 overwrite rule; inspect changed WSL behavior')
    commands = []
    for tag, mark in MARKS.items():
        entries = owned[tag]
        if not remove and len(entries) == 1 and entries[0][0] < overwrite[0]:
            continue
        for _, handle in entries:
            commands.append(f'delete rule ip filter WSLOUTPUT handle {handle}')
        if not remove:
            commands.append(f'insert rule ip filter WSLOUTPUT meta mark & 0x{MASK:08x} == 0x{mark:08x} '
                            f'counter return comment "{tag}"')
    return commands


def check_host():
    if os.geteuid() != 0 or 'microsoft' not in platform.release().lower():
        raise ValueError('Run as root on the owned WSL lab only')
    path = Path('/var/lib/vcloud-wsl/owner.json')
    if path.is_symlink():
        raise ValueError('Unexpected ownership marker symlink')
    owner = json.loads(path.read_text())
    if owner.get('profileSHA256') != PROFILE_SHA256:
        raise ValueError('Owned WSL profile differs; refusing an automatic migration')
    if subprocess.check_output(['wslinfo', '--networking-mode'], text=True).strip() != 'mirrored':
        raise ValueError('This compatibility fix requires mirrored networking')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument('--plan', action='store_true', help='Print validated commands without applying (default)')
    modes.add_argument('--apply', action='store_true', help='Reconcile the two tagged mark-preservation rules')
    modes.add_argument('--remove', action='store_true', help='Remove only the two tagged, verified rules')
    args = parser.parse_args()
    try:
        check_host()
        nft = shutil.which('nft')
        if not nft:
            raise ValueError('Missing dependency: nft; install the Ubuntu nftables package')
        state = json.loads(subprocess.check_output([nft, '--json', '--handle', 'list', 'chain',
                                                   'ip', 'filter', 'WSLOUTPUT'], text=True))
        commands = plan(state, args.remove)
        if not commands:
            print('WSL Cilium proxy marks: already reconciled')
            return 0
        batch = '\n'.join(commands) + '\n'
        subprocess.run([nft, '--check', '--file', '-'], input=batch, text=True, check=True)
        if args.apply or args.remove:
            subprocess.run([nft, '--file', '-'], input=batch, text=True, check=True)
            print('WSL Cilium proxy marks: ' + ('removed' if args.remove else 'reconciled'))
        else:
            print(batch, end='')
        return 0
    except (ValueError, OSError, KeyError, subprocess.CalledProcessError) as error:
        print('WSL Cilium proxy marks: ' + str(error), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
