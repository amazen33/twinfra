#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""WO-07a: guard candidate deployment inputs; historical snapshots stay independent."""
import argparse
import gzip
from pathlib import Path
import re
import subprocess
import yaml

ROOT=Path(__file__).resolve().parents[1]
TEXT={'.yaml','.yml','.json','.toml','.sh','.ps1','.py','.txt','.tpl','.jsonnet'}
GENERATORS={'tools/wsl_endpoints.py','tools/wsl_endpoints_gitops.py',
            'tools/wsl_runtime_secrets.py','tools/wsl_endpoint_acceptance.py','tools/render_module3.py'}
FORBIDDEN=re.compile(r'\bgrafana\b|grafana_dashboard',re.I)


def deployment_input(name):
    """No docs, ADRs, receipts, test fixtures or preserved historical CI revisions."""
    if name in GENERATORS:return True
    parts=Path(name).parts
    if not parts or not (parts[0] in ('deploy','lab','scripts','charts') or parts[0].startswith('module-')):return False
    # README files explain deferred deployment; dashboard JSON is still checked.
    file=Path(name)
    return file.suffix in TEXT or file.name.endswith(('.yaml.gz','.yml.gz','.json.gz','.tgz')) or 'dockerfile' in file.name.lower()


def violations(root,paths,rendered=False):
    problems=[]
    for name in paths:
        if not deployment_input(name) and not (rendered and Path(name).suffix in TEXT):continue
        file=root/name
        if not file.is_file():continue
        if FORBIDDEN.search(name):problems.append(name+': forbidden deployment path')
        if name.endswith('.tgz'):
            # Identify Grafana charts, chart dependencies and image pins. Cilium
            # contains unused upstream dashboard JSON, which is not a Grafana
            # chart/workload. Actual rendered labels are checked separately.
            import tarfile
            with tarfile.open(file,'r:gz') as archive:
                for member in archive.getmembers():
                    if not member.isfile():continue
                    if not member.name.endswith(('Chart.yaml','values.yaml')):continue
                    raw=archive.extractfile(member).read().decode('utf-8')
                    chart=yaml.safe_load(raw)
                    forbidden=(FORBIDDEN.search(str(chart.get('name',''))) or any(
                        FORBIDDEN.search(str(v.get('name',''))) for v in chart.get('dependencies',[]))) if member.name.endswith('Chart.yaml') else re.search(r'(?:[\w.-]+/)*grafana/grafana\b',raw,re.I)
                    if forbidden:
                        problems.append(name+': forbidden chart member '+member.name)
            continue
        raw=gzip.decompress(file.read_bytes()) if name.endswith('.gz') else file.read_bytes()
        for line,text in enumerate(raw.decode('utf-8').splitlines(),1):
            if FORBIDDEN.search(text):problems.append(f'{name}:{line}: forbidden deployment reference')
    return problems


def check(root,rendered=()):
    paths=subprocess.check_output(['git','-C',str(root),'ls-files','--cached','--others','--exclude-standard'],text=True).splitlines()
    problems=violations(root,paths)
    for directory in rendered:
        directory=Path(directory)
        if directory.is_file():problems.extend(violations(directory.parent,[directory.name],rendered=True))
        elif directory.exists():problems.extend(violations(directory,[p.relative_to(directory).as_posix() for p in directory.rglob('*') if p.is_file()],rendered=True))
    if problems:raise ValueError('\n'.join(problems))
    print('PASS: no Grafana image/chart/workload/dashboard label in candidate deployment inputs')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--root',type=Path,default=ROOT)
    parser.add_argument('--rendered',type=Path,action='append',default=[])
    args=parser.parse_args()
    try:check(args.root.resolve(),args.rendered)
    except (ValueError,OSError,subprocess.CalledProcessError) as error:raise SystemExit(str(error)) from None
