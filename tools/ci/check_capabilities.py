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
README = 'README.md'
ACCEPTANCE = 'docs/acceptance'
INDEX = 'docs/adr/' + README
COUNT = r'<!-- adr-count:start -->.*?<!-- adr-count:end -->'
LINKS = re.compile(r'\[([^\]\n]+)\]\(([^)\n]+)\)')


def unfenced(text):
    """Exclude Markdown examples without a multi-line backtracking regex."""
    output, fence = [], None
    for line in text.splitlines(keepends=True):
        stripped = line.strip()
        if fence is not None:
            if stripped.startswith(fence) and set(stripped) == {fence[0]}:
                fence = None
            continue
        opening = re.match(r'(`{3,}|~{3,})', stripped)
        if opening:
            fence = opening[0]
        else:
            output.append(line)
    return ''.join(output)


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


def section_blocks(text, heading):
    blocks, active = [], None
    for line in text.splitlines():
        if line.startswith('## '):
            active = [] if line.strip() == heading else None
            if active is not None:
                blocks.append(active)
        elif active is not None:
            active.append(line)
    return blocks


def signoff_error(text):
    blocks = section_blocks(text, '## Tester sign-off')
    if len(blocks) != 1:
        return 'tester sign-off is not Accepted'
    results = [line.removeprefix('Result:').strip() for line in blocks[0] if line.startswith('Result:')]
    if results != ['Accepted']:
        return 'tester sign-off is not Accepted'
    if not any(line.startswith('Tester:') and '@amazen33' in line for line in blocks[0]):
        return 'missing named tester'
    return None


def matching_environment(text, status):
    identities = [line.lower() for line in text.splitlines()
                  if line.lstrip('-* ').lower().startswith(('environment', 'scope'))]
    name = r'\bproduction\b' if status == 'Production-accepted' else r'\btwinfra-dev-cairo-1\b'
    return any(re.search(name, line) for line in identities)


def receipt_error(path, label, status):
    if not path.is_file() or path.suffix != '.md' or path.name == README:
        return 'missing receipt'
    text = unfenced(path.read_text(encoding='utf-8'))
    # Inspect identity/scope, not retained WSL source discussions in a dev receipt.
    if historical_receipt(path, text) or re.search(r'Historical', label, re.I):
        return 'Historical (retired environment) receipt'
    error = signoff_error(text)
    if error:
        return error
    if not matching_environment(text, status):
        return 'receipt lacks matching live environment'
    return None


def receipt_errors(root, source, claim, status):
    errors = []
    for label, target in LINKS.findall(claim):
        if target.startswith(('http:', 'https:', '#')):
            continue
        path = (source.parent / unquote(target.split('#')[0]).strip('<>')).resolve()
        if not path.is_relative_to((root / ACCEPTANCE).resolve()):
            continue
        error = receipt_error(path, label, status)
        if error is None:
            return []
        errors.append(error + ': ' + target)
    return errors or ['missing Accepted receipt under docs/acceptance/']


def historical_label_errors(root, index, row):
    errors = []
    for label, target in LINKS.findall(' '.join(row.values())):
        path = (index.parent / target.split('#')[0]).resolve()
        if (root / ACCEPTANCE) not in path.parents or not path.is_file():
            continue
        if historical_receipt(path, path.read_text(encoding='utf-8')) and label != 'Historical (retired environment)':
            errors.append('unlabelled retired WSL evidence: ' + row['ADR'])
    return errors


def index_errors(root, index, adrs):
    errors = []
    names = [re.search(r'\((\d{4}-[^)]+\.md)\)', row['ADR']) for row in adrs]
    actual = {p.name for p in index.parent.glob('[0-9]*.md')}
    if (not all(names) or len(names) != len(actual) or
            {match[1] for match in names if match} != actual):
        errors.append('ADR index rows must cover every decision exactly once')
    for row in adrs:
        if plain(row.get('Status', '')) not in STATUSES:
            errors.append('invalid current ADR status: ' + row['ADR'])
        errors.extend(historical_label_errors(root, index, row))
    return errors


def count_text(count):
    return f'<!-- adr-count:start -->{count} records<!-- adr-count:end -->'


def count_errors(root, count, write):
    path = root / README
    text = path.read_text(encoding='utf-8')
    if len(re.findall(COUNT, text, re.S)) != 1:
        return ['README requires exactly one generated ADR count marker']
    expected = count_text(count)
    if write:
        path.write_text(re.sub(COUNT, expected, text, flags=re.S), encoding='utf-8', newline='\n')
    elif re.search(COUNT, text, re.S)[0] != expected:
        return ['README ADR count drift; run check_capabilities.py --write']
    return []


def live_claims(source, index):
    text = unfenced(source.read_text(encoding='utf-8'))
    for row in table_rows(text):
        for key, value in row.items():
            status = strong_status(value)
            if plain(key).lower().startswith('status') and status:
                yield status, ' | '.join(row.values())
    # Original ADR headers are historical snapshots. Newly asserted live headers
    # still need evidence, as well as their authoritative current index rows.
    if source.parent == index.parent and source.name != README:
        header = re.search(r'^\*\*Status:\*\* +([^\n]+)', text, re.M)
        if header and strong_status(header[1]):
            yield strong_status(header[1]), text


def check_claims(root, index):
    files = [root / README, *sorted((root / 'docs').rglob('*.md'))]
    errors, claims = [], 0
    for source in files:
        if (root / ACCEPTANCE) in source.parents:
            continue  # observations are not product claims
        for status, claim in live_claims(source, index):
            claims += 1
            errors.extend(f'{source.relative_to(root)} [{status}]: {error}'
                          for error in receipt_errors(root, source, claim, status))
    return claims, errors


def check(root, *, write=False):
    root = Path(root).resolve()
    present = [(root / name).is_file() for name in BUNDLE]
    if not any(present):
        return {'status': 'not_present_in_revision', 'findings': []}
    if not all(present):
        return {'status': 'failed', 'findings': ['incomplete WO-37 evidence bundle']}
    index = root / INDEX
    adrs = [row for row in table_rows(index.read_text(encoding='utf-8')) if 'ADR' in row]
    errors = index_errors(root, index, adrs) + count_errors(root, len(adrs), write)
    claims, findings = check_claims(root, index)
    errors.extend(findings)
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
