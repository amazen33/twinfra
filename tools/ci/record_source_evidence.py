#!/usr/bin/env python3
"""Generate the WO-34 source-mode/net-improvement receipt from public CI data."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[2]


def record(inputs, comparison, run_url):
    if not re.fullmatch(r'https://github\.com/amazen33/twinfra/actions/runs/[0-9]+', run_url):
        raise ValueError('Verified Twinfra CI run URL required')
    locked = json.loads((ROOT / 'tools/ci/toolchain.lock.json').read_text())['sourceAnalysis']
    result = dict(date='2026-10-14', scope='Static tagged-source analysis and complete image comparisons',
                  liveAcceptance='Pending', testerSignOff='Pending', runURL=run_url,
                  applicationBinaryBuilt=False, applicationCodeExecuted=False, projects=[])
    for project in locked['projects']:
        files = list((inputs / project['name']).rglob('summary.json'))
        if len(files) != 1:
            raise ValueError('Exactly one source summary per project required')
        value = json.loads(files[0].read_text())
        if (value['project'], value['tag'], value['image'], value['sourceSHA256']) != (
                project['name'], project['tag'], project['candidateReference'], project['sourceSHA256']):
            raise ValueError('Source evidence differs from locked tag/image/archive')
        if value['applicationBinaryBuilt'] or value['applicationCodeExecuted']:
            raise ValueError('Application execution/build is prohibited')
        if len(value['analyses']) != len(project['analyses']):
            raise ValueError('Incomplete selected-binary source coverage')
        analyses = []
        for row, expected in zip(value['analyses'], project['analyses']):
            for key in ('binaryPath', 'goVersion', 'moduleDirectory', 'patterns'):
                if row[key] != expected[key]:
                    raise ValueError('Source configuration differs: ' + key)
            if row['GOTOOLCHAIN'] != expected['goVersion']:
                raise ValueError('GOTOOLCHAIN differs from binary metadata')
            modules = Counter((f['module'], f['version']) for f in row['findings'] if f['reachable'])
            samples = []
            for module, version in sorted(modules):
                choices = [f for f in row['findings'] if f['reachable'] and f['module'] == module and f['version'] == version]
                network = [f for f in choices if f['callStack'][0].get('function') in ('ReadFrame', 'ReadFrameHeader')]
                selected = min(network or choices, key=lambda f: len(f['callStack']))
                samples.append(selected)
            analyses.append(dict(binaryPath=row['binaryPath'], goVersion=row['goVersion'],
                                 binarySHA256=expected['binarySHA256'], SDK=locked['sdks'][row['goVersion']],
                                 classification=row['classification'], target='GO-2026-6612',
                                 sourceFindingCount=len(row['findings']), representativeCallStacks=samples,
                                 databaseLastModified=row['databaseLastModified']))
        result['projects'].append(dict(project=value['project'], tag=value['tag'], image=value['image'],
                                        sourceSHA256=value['sourceSHA256'],
                                        summarySHA256=hashlib.sha256(files[0].read_bytes()).hexdigest(), analyses=analyses,
                                        promotion='Stopped: reachable source finding requires owner decision'
                                        if any(a['representativeCallStacks'] for a in analyses) else 'Pending remaining gates'))
    result['comparison'] = {k: v for k, v in comparison.items() if k != 'images'}
    result['comparison']['images'] = [{k: v for k, v in row.items() if k != 'findings'} for row in comparison['images']]
    ledger = json.loads((ROOT / 'security/vulnerability-exceptions.json').read_text())['exceptions']
    risk = [v for v in ledger if v['severity'] == 'Critical' and v['expires'] == '2026-11-12']
    result['deadlineWatch'] = dict(reportBy='2026-11-05', expires='2026-11-12',
                                  currentlyOpenCritical=len(risk), exceptionIdentities=[{k: v[k] for k in
                                  ('target', 'package', 'version', 'vulnerability')} for v in risk],
                                  extensionApproved=False, note='No validated not-reachable/vendor clearance recorded by this work; owner notified early.')
    receipt = ROOT / 'docs/acceptance/wo34-source-2026-10-14.json'
    receipt.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8', newline='\n')
    lines = ['# WO-34 source reachability and P2 net improvement', '',
             'Static evidence from [CI run](' + run_url + '). No application binary was built or executed; live/tester acceptance remains Pending.', '',
             '**Promotion stopped for Argo CD, CoreDNS and etcd: source mode reports reachable GO-2026-6612.** Amendment 2 requires an owner decision; no risk acceptance, exception transfer, lock change or expiry extension is made.', '',
             '| Image | Critical with fix | Critical without fix | High with fix | High without fix |',
             '| --- | ---: | ---: | ---: | ---: |']
    for row in result['comparison']['images']:
        count = row['counts']
        lines.append('| ' + row['name'] + ' | ' + ' | '.join(str(count[k]) for k in
            ('CriticalWithFix', 'CriticalWithoutFix', 'HighWithFix', 'HighWithoutFix')) + ' |')
    lines.extend(['', 'All three candidates are net improvements with no new Critical/High identities in the same database. Argo CD 3.5.5 remains age-ineligible before **2026-10-26**. Net improvement does not override the reachable-source stop.', '',
                  '## Call-stack evidence', '',
                  'Argo CD 3.5.5 still carries GO-2026-6612 in **golang.org/x/net v0.59.0** (fixed v0.60.0), not its updated Go 1.26.9 stdlib. CoreDNS and etcd retain affected x/net and stdlib. Selected source configurations match the published binary toolchains; bundled Argo auxiliary binaries remain separately affected binary findings.', ''])
    for project in result['projects']:
        for row in project['analyses']:
            lines.extend(['### ' + project['project'] + ': ' + row['binaryPath'], '',
                          '`GOTOOLCHAIN=' + row['goVersion'] + '`, ' + str(row['sourceFindingCount']) + ' source findings for GO-2026-6612. Classification: **' + row['classification'] + '**.', ''])
            for sample in row['representativeCallStacks']:
                lines.append('Module `' + sample['module'] + ' ' + sample['version'] + '`; representative caller-to-vulnerable-function path:')
                lines.extend(['', '```text'])
                for frame in reversed(sample['callStack']):
                    position = frame.get('position') or {}
                    location = position.get('filename', '') + (':' + str(position['line']) if position.get('line') else '')
                    symbol = frame.get('package', '') + '.' + (frame.get('receiver') or '') + '.' + frame.get('function', '')
                    lines.append(symbol + (' (' + location + ')' if location else ''))
                lines.extend(['```', ''])
    lines.extend(['The receipt preserves positions, pins, SDK checksums and public artifact hashes. Full traces are in the CI artifacts. Govulncheck conservatively analyzes interfaces/function pointers and cannot establish actual exposure or universal runtime exploitability; these are source call paths, not a live exploit test.', '',
                  '## Owner decision and deadline watch', '',
                  'The owner chooses documented time-boxed risk acceptance with existing tunnel-only/owner-repository controls, or waits for a fixed eligible patch. No self-built application binaries, minor upgrades or expedite.', '',
                  '**' + str(len(risk)) + ' current Critical exceptions expire 2026-11-12.** They have no not-reachable clearance established here; this is the early notice required **by 2026-11-05**. Source-reachable candidates cannot be promoted using a not-reachable exception. No expiry is extended.', '',
                  'Receipt: [source/P2 evidence](acceptance/wo34-source-2026-10-14.json).'])
    (ROOT / 'docs/image-patch-refresh-source.md').write_text('\n'.join(lines) + '\n', encoding='utf-8', newline='\n')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--inputs', type=Path, required=True)
    parser.add_argument('--comparison', type=Path, required=True)
    parser.add_argument('--run-url', required=True)
    args = parser.parse_args()
    record(args.inputs, json.loads(args.comparison.read_text()), args.run_url)
