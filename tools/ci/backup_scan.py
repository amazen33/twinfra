#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Scan the complete WO-09 built image with existing pinned read-only controls."""
import argparse
from datetime import date
import json
from pathlib import Path
import supply_chain as sc


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--tools',type=Path,required=True);parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args();args.out.mkdir(parents=True,exist_ok=True)
    root=Path(__file__).resolve().parents[2];entry=sc.read(root/'deploy/common/images.lock.json')['images']['backup']
    item={'target':sc.immutable(entry),'digest':entry['digest'],'source':'oci-archive:'+str(root/'.build/dev-images/backups.oci.tar'),
          'introduced':True,'origins':['deploy/common/images.lock.json:backup'],'previousInputs':[]}
    plan={'images':[item],'lockfiles':['deploy/common/backup/requirements.txt'],'coverage':[{'entry':'backup','mode':'built-archive'}]}
    tools=sc.verify_tools(args.tools,root)
    result=sc.scan(plan,tools,root/'.build/backup-sbom-cache',args.out,root)
    raw=sc.fetch('https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json')
    report=sc.evaluate(result,sc.read(root/'security/vulnerability-exceptions.json'),json.loads(raw),on=date.today(),root=root)
    sc.report_files(report,args.out)
    return int(report['status']!='passed')


if __name__=='__main__':raise SystemExit(main())
