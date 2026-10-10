#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""WO-06 candidate source guard; historical revision checks remain independent."""
import argparse
from pathlib import Path
import subprocess

REMOVED = 'local' + 'stack'
CI_RUNNER = 'tools/ci/run_checks.py'
# Only the original historical bundle and its dispatch may name the removed component.
HISTORICAL_LINES = {
    "'lab/wsl/"+REMOVED+"': ['lab/wsl/"+REMOVED+"/artifacts.lock.json','lab/wsl/"+REMOVED+"/deployment.yaml',",
    "'lab/wsl/"+REMOVED+"/service.yaml','lab/wsl/"+REMOVED+"/apisix-route.yaml',",
    "'lab/wsl/"+REMOVED+"/configure-apisix.py','lab/wsl/"+REMOVED+"/access.sh',",
    "'lab/wsl/"+REMOVED+"/deploy.sh',",
    "'lab/wsl/"+REMOVED+"/verify.sh','lab/wsl/"+REMOVED+"/test-api.py',",
    "'tools/wsl_"+REMOVED+".py','tests/test_wsl_"+REMOVED+".py'],",
    "present = (source / name).exists() if name == 'lab/wsl/"+REMOVED+"' else (",
    "if report['modules']['lab/wsl/"+REMOVED+"'] == 'present':",
    "run('wsl-"+REMOVED+"-tests',[python,'-m','unittest','discover','-s','tests','-p','test_wsl_"+REMOVED+".py','-v'],unit=True)",
}
SUFFIXES = {'.py', '.tsx', '.ts', '.json', '.yaml', '.yml', '.sh', '.ps1', '.toml', '.txt'}


def violations(root, paths):
    problems = []
    for name in paths:
        file = root / name
        if not file.is_file() or not name.startswith(('console/', 'deploy/', 'lab/', 'module-', 'tools/', 'tests/', '.github/')):
            continue
        if REMOVED in name.lower():
            problems.append(name + ': removed component path')
        if file.suffix not in SUFFIXES:
            continue
        for number, line in enumerate(file.read_text(encoding='utf-8').splitlines(), 1):
            if REMOVED in line.lower() and not (name == CI_RUNNER and line.strip() in HISTORICAL_LINES):
                problems.append(f'{name}:{number}: removed component reference')
    return problems


def check(root):
    paths = subprocess.run(['git', '-C', str(root), 'ls-files', '--cached', '--others', '--exclude-standard'],
                           capture_output=True, text=True, check=True).stdout.splitlines()
    problems = violations(root, paths)
    if problems:
        raise ValueError('\n'.join(problems))
    print('PASS: only MiniStack remains in candidate code, locks and manifests')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    try:
        check(parser.parse_args().root.resolve())
    except (ValueError, OSError, subprocess.CalledProcessError) as error:
        raise SystemExit(str(error)) from None
