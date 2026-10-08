#!/usr/bin/env python3
"""Manual, guarded loopback recovery for the owned mirrored WSL lab.

Route Linux-originated 127.0.0.1 connections locally while preserving Windows
reply routing. No firewall ACCEPT, namespace policy or physical route changes.
Root/CAP_NET_ADMIN is explicitly required. Nothing is installed or scheduled.
"""
import argparse
import copy
import json
import re
import socket
import subprocess
import sys

from wsl_proxy_marks import check_host

TABLE = 'vcloud_wsl_loopback'
MARK = 2


def expected_table():
    scope = {'family': 'ip', 'table': TABLE, 'chain': 'output'}
    match = lambda field: {'match': {'op': '==', 'left': {'payload': {
        'protocol': 'ip', 'field': field}}, 'right': '127.0.0.1'}}
    address = [match('saddr'), match('daddr')]
    return [
        {'table': {'family': 'ip', 'name': TABLE}},
        {'chain': {'family': 'ip', 'table': TABLE, 'name': 'output',
                   'type': 'route', 'hook': 'output', 'prio': 10, 'policy': 'accept'}},
        {'rule': {**scope, 'comment': 'vcloud:local-loopback-connection', 'expr': address + [
            {'match': {'op': '==', 'left': {'ct': {'key': 'direction'}}, 'right': 'original'}},
            {'mangle': {'key': {'ct': {'key': 'mark'}},
                        'value': {'|': [{'ct': {'key': 'mark'}}, MARK]}}}]}},
        {'rule': {**scope, 'comment': 'vcloud:local-loopback-route', 'expr': address + [
            {'match': {'op': '==', 'left': {'&': [{'ct': {'key': 'mark'}}, MARK]}, 'right': MARK}},
            {'mangle': {'key': {'meta': {'key': 'mark'}},
                        'value': {'|': [{'meta': {'key': 'mark'}}, MARK]}}}]}}
    ]


def validate_table(state):
    if state is None:
        return False
    objects = copy.deepcopy(state['nftables'])
    normalized = []
    for obj in objects:
        if set(obj) == {'metainfo'}:
            continue
        if len(obj) != 1 or next(iter(obj)) not in ('table', 'chain', 'rule'):
            raise ValueError('Unrecognized object in owned loopback table')
        next(iter(obj.values())).pop('handle', None)
        normalized.append(obj)
    if normalized != expected_table():
        raise ValueError('Owned loopback table differs; inspect rather than overwrite it')
    return True


RULES = [
    {'priority': 0, 'src': 'all', 'dst': '127.0.0.1', 'fwmark': '0x2',
     'fwmask': '0x2', 'table': 'local'},
    {'priority': 0, 'src': 'all', 'dst': '127.0.0.1', 'iif': 'loopback0', 'table': 'local'}
]
SELECTORS = [
    ['to', '127.0.0.1/32', 'fwmark', '0x2/0x2'],
    ['iif', 'loopback0', 'to', '127.0.0.1/32']
]
NFT_BATCH = f'''add table ip {TABLE}
add chain ip {TABLE} output {{ type route hook output priority 10; policy accept; }}
add rule ip {TABLE} output ip saddr 127.0.0.1 ip daddr 127.0.0.1 ct direction original ct mark set ct mark | 0x2 comment "vcloud:local-loopback-connection"
add rule ip {TABLE} output ip saddr 127.0.0.1 ip daddr 127.0.0.1 ct mark & 0x2 == 0x2 meta mark set meta mark | 0x2 comment "vcloud:local-loopback-route"
'''


def plan(state, rules, remove=False):
    present = validate_table(state)
    selected = []
    for item in rules:
        if item.get('priority') != 0:
            continue
        item = dict(item)
        if item.get('protocol') == 'unspec':
            item.pop('protocol')
        # Mirrored WSL recreates these protocol-specific ingress rules on boot.
        # Preserve them verbatim; only the two exact vCloud selectors are owned.
        if (set(item) == {'priority','src','iif','ipproto','table'} and
                item['src'] == 'all' and item['table'] == 'local' and
                item['ipproto'] in ('tcp','udp') and
                re.fullmatch(r'eth[0-9]+|loopback0',item['iif'])):
            continue
        if item not in RULES or item in selected:
            raise ValueError('Foreign or duplicate priority-zero rule; refusing mutation')
        selected.append(item)
    if selected and not present:
        raise ValueError('Loopback rules exist without their owned table')
    commands = []
    for rule, selector in zip(RULES, SELECTORS):
        if (remove and rule in selected) or (not remove and rule not in selected):
            commands.append(['ip', '-4', 'rule', 'delete' if remove else 'add',
                             'priority', '0', *selector, 'lookup', 'local'])
    return ('delete table ip ' + TABLE + '\n' if remove and present
            else NFT_BATCH if not remove and not present else ''), commands


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument('--apply', action='store_true')
    modes.add_argument('--remove', action='store_true', help='Remove only the verified owned rules/table')
    args = parser.parse_args()
    try:
        check_host()
        subprocess.run(['ip', 'link', 'show', 'loopback0'], check=True, stdout=subprocess.DEVNULL)
        inventory = json.loads(subprocess.check_output(['nft', '-j', 'list', 'tables'], text=True))
        exists = any(o.get('table', {}).get('family') == 'ip' and
                     o.get('table', {}).get('name') == TABLE for o in inventory['nftables'])
        state = json.loads(subprocess.check_output(['nft', '-j', 'list', 'table', 'ip', TABLE], text=True)) if exists else None
        rules = json.loads(subprocess.check_output(['ip', '-j', '-4', 'rule', 'show'], text=True))
        batch, commands = plan(state, rules, args.remove)
        if batch:
            subprocess.run(['nft', '--check', '-f', '-'], input=batch, text=True, check=True)
        if not (args.apply or args.remove):
            print(batch, end='')
            for command in commands:
                print(' '.join(command))
            return 0
        # Add marking before route rules; remove route rules before their table.
        if batch and not args.remove:
            subprocess.run(['nft', '-f', '-'], input=batch, text=True, check=True)
        for command in commands:
            subprocess.run(command, check=True)
        if batch and args.remove:
            subprocess.run(['nft', '-f', '-'], input=batch, text=True, check=True)
        if args.apply:
            with socket.socket() as server, socket.socket() as client:
                server.bind(('127.0.0.1', 0)); server.listen(); client.settimeout(3)
                client.connect(server.getsockname())
                connection, _ = server.accept()
                with connection:
                    connection.settimeout(3); client.sendall(b'ok')
                    if connection.recv(2) != b'ok':
                        raise ValueError('Local TCP payload check failed')
                    connection.sendall(b'ok')
                    if client.recv(2) != b'ok':
                        raise ValueError('Local TCP reply check failed')
            print('PASS: Linux loopback TCP; separately verify Windows endpoints')
        else:
            print('Removed only the verified vCloud loopback recovery objects')
        return 0
    except (ValueError, OSError, KeyError, subprocess.CalledProcessError) as error:
        print('WSL loopback recovery: ' + str(error), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
