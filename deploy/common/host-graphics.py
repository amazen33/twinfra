#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Owned display-driver configuration and count-only kernel health. No IO at import."""
from collections import deque
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import time

ROOT = Path('/')
FILE = '/etc/modprobe.d/twinfra-display-drivers.conf'
BODY = 'blacklist nouveau\noptions nouveau modeset=0\nblacklist nvidiafb\n'
STATE = '/var/lib/twinfra/host-graphics'
OWNER = 'WO-31 display drivers v1'
SHA = hashlib.sha256(BODY.encode()).hexdigest()
PATTERNS = {
    'warningTraces': r'\bWARNING:', 'bugTraces': r'\bBUG(?: at|:)|\bOops:',
    'machineCheck': r'machine check (?:exception|events logged)|\[Hardware Error\]|mce:.*(?:error|uncorrected|bank\s*\d)',
    'hungTask': r'\btask .*blocked for more than \d+ seconds',
    'oom': r'out of memory:|oom-kill:|invoked oom-killer|killed process \d+ .*total-vm:',
    'ioErrors': r'I/O error|blk_update_request:.*error|EXT4-fs error|XFS.*(?:corruption|error)',
}


def path(name):
    return ROOT / name.lstrip('/')


def secure(p):
    for item in (p, *p.parents):
        if item == ROOT.parent:
            break
        if item.is_symlink():
            raise ValueError('Linked graphics path refused')
        if item.exists() and (item.stat().st_uid != 0 or item.stat().st_mode & 0o022):
            raise ValueError('Unowned/insecure graphics path')


def write(name, raw, mode=0o600):
    p = path(name)
    secure(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=p.parent, delete=False) as stream:
        stream.write(raw)
        candidate = stream.name
    os.chmod(candidate, mode)
    os.replace(candidate, p)


def run(args):
    result = subprocess.run(args, capture_output=True, text=True, timeout=900)
    if result.returncode:
        raise ValueError('Graphics verification command failed: ' + args[0])
    return result.stdout


def kernel():
    value = run(['uname', '-r']).strip()
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._+-]{0,127}', value):
        raise ValueError('Invalid running kernel')
    return value


def loaded():
    return {name: path('/sys/module/' + name).exists() for name in ('nouveau', 'nvidiafb')}


def ownership():
    p, receipt = path(FILE), path(STATE + '/ownership.json')
    secure(p)
    secure(receipt)
    data = json.loads(receipt.read_text()) if receipt.exists() else None
    if data is not None:
        if data != {'owner': OWNER, 'sha256': SHA, 'backup': None}:
            raise ValueError('Invalid graphics ownership or backup')
        if p.exists() and (not p.is_file() or p.read_bytes() != BODY.encode()):
            raise ValueError('Owned graphics file differs; no adoption')
    elif p.exists():
        raise ValueError('Unowned graphics file; no adoption')
    return data


def initramfs_contains(version):
    initrd = '/boot/initrd.img-' + version
    secure(path(initrd))
    names = run(['lsinitramfs', initrd]).splitlines()
    return any(name.removeprefix('./') == FILE.lstrip('/') for name in names)


def rebuild(version, present):
    run(['update-initramfs', '-u', '-k', version])
    if initramfs_contains(version) != present:
        raise ValueError('Initramfs graphics file presence differs')
    if present:
        with tempfile.TemporaryDirectory(prefix='twinfra-initramfs-') as temp:
            run(['unmkinitramfs', '/boot/initrd.img-' + version, temp])
            files = list(Path(temp).rglob(FILE.lstrip('/')))
            if not files or any(p.is_symlink() or p.read_bytes() != BODY.encode() for p in files):
                raise ValueError('Initramfs graphics file content differs')


@contextmanager
def lock():
    import fcntl
    directory = path(STATE)
    secure(directory)
    directory.mkdir(parents=True, exist_ok=True)
    os.chmod(directory, 0o700)
    file = directory / 'lock'
    secure(file)
    with file.open('a') as stream:
        try:
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ValueError('Graphics action already active') from None
        try:
            yield
        finally:
            fcntl.flock(stream, fcntl.LOCK_UN)


def check():
    data = ownership()
    version = kernel()
    present = path(FILE).exists()
    included = initramfs_contains(version)
    modules = loaded()
    return {'status': 'passed' if data and present and included and not any(modules.values()) else 'failed',
            'loaded': modules, 'blacklistCurrent': bool(data and present), 'initramfsContainsFile': included,
            'runningKernel': version, 'kernelHealth': kernel_health()}


def change(mode):
    if mode not in ('apply', 'rollback'):
        raise ValueError('Unknown graphics mutation')
    ownership()  # Refuse foreign files before any lock/backup write.
    version = kernel()
    for name in ('update-initramfs', 'lsinitramfs', 'unmkinitramfs'):
        if not shutil.which(name):
            raise ValueError('Required Ubuntu initramfs tool unavailable')
    with lock():
        data = ownership()
        if mode == 'rollback' and data is None:
            raise ValueError('No owned graphics backup to restore')
        if data is None:
            # The only permitted initial state is absence. This permanent backup
            # is also the ownership receipt, kept across apply retries/rollback.
            data = {'owner': OWNER, 'sha256': SHA, 'backup': None}
            write(STATE + '/ownership.json', (json.dumps(data) + '\n').encode())
        if mode == 'apply':
            write(FILE, BODY.encode(), 0o644)
        elif path(FILE).exists():
            path(FILE).unlink()
        rebuild(version, mode == 'apply')
    return {'status': 'reboot-required', 'runningKernel': version,
            'message': 'Owned display configuration and initramfs verified; owner must plan reboot. No reboot executed.'}


def kernel_status(counts, maximum):
    if any(counts[k] for k in ('machineCheck', 'hungTask', 'oom')) or maximum > 100:
        return 'BLOCK'
    return 'WARN' if any(counts.values()) else 'PASS'


def count_kernel(entries, now_us):
    counts = dict.fromkeys(PATTERNS, 0)
    window, maximum, last_hour, previous = deque(), 0, 0, -1
    for row in entries:
        message = row.get('MESSAGE', '')
        if not isinstance(message, str):
            continue
        timestamp = int(row['__MONOTONIC_TIMESTAMP'])
        if timestamp < previous:
            raise ValueError('Kernel journal timestamps out of order')
        previous = timestamp
        for key, pattern in PATTERNS.items():
            counts[key] += int(bool(re.search(pattern, message, re.I)))
        if re.search(PATTERNS['warningTraces'], message, re.I):
            while window and window[0] < timestamp - 3_600_000_000:
                window.popleft()
            window.append(timestamp)
            maximum = max(maximum, len(window))
            last_hour += int(timestamp >= now_us - 3_600_000_000)
    return {'status': kernel_status(counts, maximum),
            'detail': {'counts': counts, 'maxWarningTracesPerHour': maximum, 'lastHourWarningTraces': last_hour}}


def kernel_health():
    try:
        probe = subprocess.run(['journalctl', '-k', '-b', '-n', '1', '--no-pager', '--quiet', '-o', 'json'],
                               capture_output=True, text=True, timeout=30)
        if probe.returncode or not probe.stdout.strip():
            raise ValueError('Current-boot kernel journal unavailable')
        int(json.loads(probe.stdout)['__MONOTONIC_TIMESTAMP'])
        # Filter trace starts/events in journald, not millions of stack lines.
        result = subprocess.run(['journalctl', '-k', '-b', '--no-pager', '--quiet', '-o', 'json',
            '--output-fields=MESSAGE,__MONOTONIC_TIMESTAMP', '--case-sensitive=no',
            '--grep=' + '|'.join(PATTERNS.values())], capture_output=True, text=True, timeout=120)
        if result.returncode not in (0, 1) or getattr(result, 'stderr', '').strip():
            raise ValueError('Kernel journal unavailable')
        value = count_kernel((json.loads(line) for line in result.stdout.splitlines() if line.strip()),
                             int(time.monotonic() * 1_000_000))
        value['detail']['coverage'] = 'retained kernel journal since boot; rotated history may be missing'
        return value
    except (ValueError, OSError, KeyError, TypeError, subprocess.SubprocessError):
        return {'status': 'BLOCK', 'detail': {'available': False}}


def health_checks():
    value = kernel_health()
    checks = [{'name': 'Kernel health', **value}]
    try:
        owned = bool(ownership() and path(FILE).exists())
        pending = owned and loaded()['nouveau']
        checks.append({'name': 'Display driver reboot', 'status': 'WARN' if pending else 'PASS',
                       'detail': {'nouveauLoadedWithBlacklist': pending}})
    except (ValueError, OSError, TypeError):
        checks.append({'name': 'Display driver ownership', 'status': 'BLOCK', 'detail': {'owned': False}})
    return checks


def bootstrap():
    config = path('/etc/twinfra-host.env').read_text()
    if not re.search(r'(?m)^PLATFORM_PROFILE=dev-cairo-[12]$', config) or not re.search(r'(?m)^DISABLE_NOUVEAU=true$', config):
        raise ValueError('Graphics bootstrap requires explicit dev profile and DISABLE_NOUVEAU=true')
    return change('apply')


if __name__ == '__main__':
    try:
        if os.geteuid() != 0 or sys.argv[1:] != ['--bootstrap']:
            raise ValueError('Root dev bootstrap only')
        report = bootstrap()
    except (ValueError, OSError, KeyError, subprocess.SubprocessError):
        report = {'status': 'failed', 'message': 'Graphics bootstrap failed; inspect owned state locally'}
    print(json.dumps(report))
    sys.exit(20 if report['status'] == 'reboot-required' else 1)
