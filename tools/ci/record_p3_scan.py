#!/usr/bin/env python3
"""Generate P3 scan receipt and exact, evidence-backed exception closures."""
import argparse
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[2]


def record(comparison, run_url):
    if not re.fullmatch(r'https://github\.com/amazen33/twinfra/actions/runs/[0-9]+', run_url):
        raise ValueError('Verified Twinfra CI run URL required')
    rows = {v['name']: v for v in comparison['images']}
    app = json.loads((ROOT / 'deploy/common/images.lock.json').read_text())
    boot = json.loads((ROOT / 'deploy/common/bootstrap-images.lock.json').read_text())
    for name, pin in (('ministack-after', app['images']['ministack']['digest']),
                      ('pause-after', boot['images']['pause']['digest'])):
        row = rows[name]
        if not row['reference'].endswith('@' + pin) or row['coverage'] != 'complete-oci-archive-linux-amd64':
            raise ValueError('Complete scan must match the promoted lock')
        if row['counts']['CriticalWithFix'] or row['counts']['HighWithFix']:
            raise ValueError('P3 candidate still has fixable Critical/High findings')
    path = ROOT / 'security/vulnerability-exceptions.json'
    ledger = json.loads(path.read_text())
    removed, kept = [], []
    for entry in ledger['exceptions']:
        before = next((row for name, row in rows.items()
                       if name.endswith('-before') and row['reference'] == entry['target']), None)
        if before is None:
            kept.append(entry)
            continue
        if not any(v['package'] == entry['package'] and v['version'] == entry['version']
                   and entry['vulnerability'] in v['aliases'] for v in before['findings']):
            raise ValueError('Exception lacks exact before-scan evidence')
        after = rows[before['name'].replace('-before', '-after')]
        if any(v['package'] == entry['package'] and entry['vulnerability'] in v['aliases'] for v in after['findings']):
            raise ValueError('Exception remains affected')
        removed.append(entry)
    ledger['exceptions'] = kept
    path.write_text(json.dumps(ledger, indent=2) + '\n', encoding='utf-8', newline='\n')
    receipt = dict(date=comparison['date'], scope='Static complete P3 image comparison; no live changes',
                   result='Passed', liveAcceptance='Pending', testerSignOff='Pending', runURL=run_url,
                   database=comparison['database'], images=[{k: v for k, v in row.items() if k != 'findings'}
                   for row in comparison['images']], closedExceptions=removed, remainingExceptions=len(kept))
    (ROOT / 'docs/acceptance/wo34-p3-2026-10-14.json').write_text(json.dumps(receipt, indent=2) + '\n',
                                                              encoding='utf-8', newline='\n')
    return receipt


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--comparison', required=True, type=Path)
    parser.add_argument('--run-url', required=True)
    args = parser.parse_args()
    record(json.loads(args.comparison.read_text()), args.run_url)
