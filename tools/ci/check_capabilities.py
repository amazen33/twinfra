"""ADR-0052 evidence claims and index-derived README count; no live operations."""
import argparse
import json
from pathlib import Path
import re
from urllib.parse import unquote

STATUSES = ('Proposed', 'Accepted (design)', 'Dev-verified', 'Production-accepted',
            'Deferred (reference design)', 'Superseded')
STRONG = ('Dev-verified', 'Production-accepted', 'Real', 'Parity-tested')
BUNDLE = ('docs/capabilities.md', 'docs/adr/0052-evidence-first-foundation-1-0.md',
          'docs/work-orders/WO-37-readme-capabilities-and-adr-status.md')
COUNT = r'<!-- adr-count:start -->.*?<!-- adr-count:end -->'


def unfenced(text):
    return re.sub(r'^(`{3,}|~{3,}).*?^\1[^\n]*$', '', text, flags=re.M | re.S)


def plain(text):
    return text.strip().strip('*` ').strip()


def strong_status(text):
    value = plain(text)
    return next((status for status in STRONG
                 if re.match(re.escape(status) + r'(?=$|[\s(;,.])', value)), None)


def historical_receipt(path, text):
    identity = '\n'.join(text.splitlines()[:8])
    return bool(re.search(r'wsl', path.name, re.I) or
                re.search(r'\bWSL\d?\b|vcloud-wsl-|retired environment', identity, re.I))


def table_rows(text):
    """Yield header/cell pairs, ignoring fenced examples and separator rows."""
    headers = None
    for line in unfenced(text).splitlines():
        if not line.startswith('|'):
            headers = None
            continue
        cells = [cell.strip() for cell in line.strip().strip('|').split('|')]
        if all(re.fullmatch(r':?-+:?', cell) for cell in cells):
            continue
        if headers is None:
            headers = cells
        else:
            yield dict(zip(headers, cells))


def receipt_errors(root, source, claim, status):
    errors, valid = [], False
    for label, target in re.findall(r'\[([^\]\n]+)\]\(([^)\n]+)\)', claim):
        if target.startswith(('http:', 'https:', '#')):
            continue
        path = (source.parent / unquote(target.split('#')[0]).strip('<>')).resolve()
        if not path.is_relative_to((root / 'docs/acceptance').resolve()):
            continue
        if not path.is_file() or path.suffix != '.md' or path.name == 'README.md':
            errors.append('missing receipt: ' + target)
            continue
        text = unfenced(path.read_text(encoding='utf-8'))
        # Do not mistake retained WSL source discussions in a cairo-1 receipt
        # for its environment. Inspect its identity/scope, not arbitrary prose.
        historical = historical_receipt(path, text) or re.search(r'Historical', label, re.I)
        if historical:
            errors.append('Historical (retired environment) receipt: ' + target)
            continue
        blocks = re.findall(r'^## Tester sign-off\s*\n(.*?)(?=^## |\Z)', text, re.M | re.S)
        if len(blocks) != 1 or re.findall(r'^Result:\s*(.*?)\s*$', blocks[0], re.M) != ['Accepted']:
            errors.append('tester sign-off is not Accepted: ' + target)
            continue
        if not re.search(r'^Tester:.*@amazen33', blocks[0], re.M):
            errors.append('missing named tester: ' + target)
            continue
        if status == 'Production-accepted':
            environment = re.search(r'(?im)^.*Environment[^\n]*\bproduction\b', text)
        else:
            environment = re.search(r'(?im)^.*(?:Environment|Scope)[^\n]*\btwinfra-dev-cairo-1\b', text)
        if not environment:
            errors.append('receipt lacks matching live environment: ' + target)
            continue
        valid = True
    return [] if valid else (errors or ['missing Accepted receipt under docs/acceptance/'])


def count_text(count):
    return f'<!-- adr-count:start -->{count} records<!-- adr-count:end -->'


def check(root, *, write=False):
    root = Path(root).resolve()
    present = [(root / name).is_file() for name in BUNDLE]
    if not any(present):
        return {'status': 'not_present_in_revision', 'findings': []}
    errors = []
    if not all(present):
        return {'status': 'failed', 'findings': ['incomplete WO-37 evidence bundle']}
    index = root / 'docs/adr/README.md'
    rows = list(table_rows(index.read_text(encoding='utf-8')))
    adrs = [row for row in rows if 'ADR' in row]
    names = [re.search(r'\((\d{4}-[^)]+\.md)\)', row['ADR']) for row in adrs]
    actual = {p.name for p in index.parent.glob('[0-9]*.md')}
    if (not all(names) or len(names) != len(actual) or
            {match[1] for match in names if match} != actual):
        errors.append('ADR index rows must cover every decision exactly once')
    for row in adrs:
        if plain(row.get('Status', '')) not in STATUSES:
            errors.append('invalid current ADR status: ' + row['ADR'])
        for label, target in re.findall(r'\[([^]]+)\]\(([^)]+)\)', ' '.join(row.values())):
            path = (index.parent / target.split('#')[0]).resolve()
            if ((root / 'docs/acceptance') in path.parents and path.is_file() and
                    historical_receipt(path, path.read_text(encoding='utf-8')) and
                    label != 'Historical (retired environment)'):
                errors.append('unlabelled retired WSL evidence: ' + row['ADR'])
    readme = root / 'README.md'
    text = readme.read_text(encoding='utf-8')
    expected = count_text(len(adrs))
    if len(re.findall(COUNT, text, re.S)) != 1:
        errors.append('README requires exactly one generated ADR count marker')
    elif write:
        readme.write_text(re.sub(COUNT, expected, text, flags=re.S), encoding='utf-8', newline='\n')
    elif re.search(COUNT, text, re.S)[0] != expected:
        errors.append('README ADR count drift; run check_capabilities.py --write')
    # Headers in original ADRs are historical decision snapshots. The index
    # carries the current status; any newly asserted live status is checked too.
    files = [readme, *sorted((root / 'docs').rglob('*.md'))]
    claims = 0
    for source in files:
        if (root / 'docs/acceptance') in source.parents:
            continue  # receipts record observations, rather than product claims
        text = unfenced(source.read_text(encoding='utf-8'))
        claimed = []
        for row in table_rows(text):
            for key, value in row.items():
                status = strong_status(value)
                if plain(key).lower().startswith('status') and status:
                    claimed.append((status, ' | '.join(row.values())))
        if source.parent == index.parent and source.name != 'README.md':
            header = re.search(r'^\*\*Status:\*\*\s*([^\n]+)', text, re.M)
            if header and strong_status(header[1]):
                claimed.append((strong_status(header[1]), text))
        for status, claim in claimed:
            claims += 1
            errors.extend(f'{source.relative_to(root)} [{status}]: {error}'
                          for error in receipt_errors(root, source, claim, status))
    return {'status': 'failed' if errors else 'passed', 'adrCount': len(adrs),
            'liveClaimsChecked': claims, 'findings': errors}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument('--write', action='store_true', help='refresh README count from ADR index')
    args = parser.parse_args()
    result = check(args.root, write=args.write)
    print(json.dumps(result, indent=2))
    return int(result['status'] == 'failed')


if __name__ == '__main__':
    raise SystemExit(main())
