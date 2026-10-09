from pathlib import Path
import hashlib
import json
import re
import subprocess
from urllib.parse import unquote

import sys
root = Path(sys.argv[1]).resolve()
report_path = Path(sys.argv[2]).resolve()
mermaid_path = Path(sys.argv[3]).resolve()
canonical = (root / 'docs/adr').exists()
adr_dir = root / ('docs/adr' if canonical else 'docs/adrs')
all_adrs = sorted(adr_dir.glob('[0-9]*.md'))
adrs = [file for file in all_adrs if 2 <= int(file.name[:4]) <= 18]
expected = ['kubernetes', 'knative-serving', 'cloudnativepg', 'pgvector', 'apisix',
            'argocd', 'tekton', 'prometheus', 'grafana', 'opentelemetry', 'openbao',
            'keycloak', 'kafka', 'strimzi', 'vllm', 'langchain', 'spinifex']
assert len(adrs) == len(expected) == 17
for number, (file, slug) in enumerate(zip(adrs, expected), 2):
    assert file.name == f'{number:04d}-{slug}.md', file
    content = file.read_text(encoding='utf-8')
    assert content.startswith(f'# ADR-{number:04d}:'), file
    for field in ('Status', 'Date', 'Deciders', 'Selection', 'Scope'):
        assert f'**{field}:**' in content, (file, field)
    for section in ('Context', 'Decision', 'Options considered', 'Trade-off analysis', 'Consequences', 'Action items and acceptance'):
        assert f'## {section}\n' in content, (file, section)
    assert re.search(r'\*\*Date:\*\* \d{4}-\d{2}-\d{2}', content), file
    assert re.search(r'\*\*Status:\*\* (Proposed|Accepted|Superseded|Deprecated)', content), file
    assert 'https://' in content, file
    if canonical:
        assert '**Classification:** Constraint' in content, file

files = adrs + [adr_dir / 'README.md', root / 'docs/module-1-topology.md',
               root / 'docs/module-1-summary.md', root / 'README.md']
if canonical:
    numbers = [int(file.name[:4]) for file in all_adrs]
    assert len(numbers) >= 35 and numbers == list(range(1, len(numbers) + 1)), ('duplicate/gapped ADR numbers', numbers)
    assert not list((root / 'docs').glob('adr-*.md')), 'individual ADRs remain in docs/'
    for old_dir in ('docs/adrs', 'docs/architecture/adr'):
        remaining = list((root / old_dir).glob('*.md'))
        assert [file.name for file in remaining] == ['README.md'], (old_dir, remaining)
        assert len(remaining[0].read_text(encoding='utf-8').splitlines()) == 1, remaining[0]
    for file in all_adrs:
        content = file.read_text(encoding='utf-8')
        title_number = re.match(r'# ADR[ -](\d{4}):', content)
        assert title_number and int(title_number[1]) == int(file.name[:4]), ('ADR title/filename mismatch', file)
        assert re.search(r'\*\*Status:\*\* (Proposed|Accepted \((lab|production|owner)[,)]|Superseded)', content), file
        if '**Status:** Accepted (lab)' in content:
            assert re.search(r'\]\(\.\./acceptance/[^)]+\)', content), ('missing lab receipt', file)
    successors = {10: [34], 18: [29, 30], 25: [30], 26: [35], 27: [35]}
    for number, replacements in successors.items():
        file = next(adr_dir.glob(f'{number:04d}-*.md'))
        content = file.read_text(encoding='utf-8')
        assert all(f'ADR-{replacement:04d}' in content for replacement in replacements), file
        if number in (26, 27):
            assert 'read-only decision only' in content, file
        else:
            assert '**Status:** Superseded' in content, file
    assert 'WO-06' in next(adr_dir.glob('0025-*.md')).read_text(encoding='utf-8')
    orders = sorted((root / 'docs/work-orders').glob('WO-*.md'))
    assert [file.name[:5] for file in orders] == [f'WO-{number:02d}' for number in range(1, 12)], orders
    assert (root / 'docs/work-orders/README.md').is_file()
    assert not (root / 'docs/work-orders/CODEX-PROMPTS.md').exists()
    # Controls validate whichever selected revision CI checked out.
    # Historical revisions retain Module 1's original layout/17-record contract.
    result = subprocess.run(['git', '-C', str(root), 'ls-files', '--cached', '--others',
                             '--exclude-standard', '--', '*.md'], capture_output=True, text=True, check=True)
    files = sorted({root / name for name in result.stdout.splitlines()} | set(all_adrs))
local_links = 0
source_urls = set()
for file in files:
    content = file.read_text(encoding='utf-8')
    fences = re.findall(r'^```.*$', content, re.MULTILINE)
    assert len(fences) % 2 == 0, ('unbalanced fences', file)
    assert 'registry.pcloud.example.com' not in content
    assert 'registry.vCloud' not in content
    for target in re.findall(r'\[[^\]\n]+\]\(([^)\n]+)\)', content):
        if target.startswith(('http://', 'https://')):
            source_urls.add(target)
        elif not target.startswith('#'):
            target_path = unquote(target.split('#', 1)[0]).strip('<>')
            destination = file.parent / target_path
            assert destination.exists(), (file, target_path)
            if canonical and '#' in target and destination.suffix == '.md':
                anchor = unquote(target.split('#', 1)[1])
                headings = re.findall(r'^#+ (.+)$', destination.read_text(encoding='utf-8'), re.MULTILINE)
                anchors, counts = set(), {}
                for heading in headings:
                    heading = re.sub(r'\[([^]]+)\]\([^)]+\)', r'\1', heading)
                    slug = re.sub(r'[^\w\- ]', '', heading.lower()).replace(' ', '-')
                    count = counts.get(slug, 0)
                    counts[slug] = count + 1
                    anchors.add(slug + (f'-{count}' if count else ''))
                assert not anchor or anchor in anchors, ('missing heading anchor', file, target)
            local_links += 1
index = (adr_dir / 'README.md').read_text(encoding='utf-8')
for file in all_adrs:
    assert file.name in index
if canonical:
    assert f'**{len(all_adrs) + 1:04d}**' in index, 'incorrect next free number'
    for status in ('Proposed', 'Accepted (lab)', 'Accepted (production)', 'Superseded', 'Constraint'):
        assert status in index, status
    ssot = (root / 'vcloud-ssot.yaml').read_text(encoding='utf-8')
    assert 'adr: docs/adr/0001-node-host-mounts.md' in ssot, 'active SSoT ADR reference is stale'
for identity in ('vCloud-prod-01', 'vcloud-prod-01', 'vcloud.example.com',
                 'amazen33/vCloud', 'registry.vcloud.example.com', 'platform-services',
                 'workload-apps', 'hpc-compute'):
    assert identity in index, identity

digest = lambda file: hashlib.sha256((root / file).read_bytes()).hexdigest()
approved_policy_hash = 'd9799b19ff5fb101cde1870840f29b6d54d6e6cff2c22b389a62d9adfe7cd253'
inventory_hash = 'bbb08cd371ab6321f9620d7db4280b3515a24db0825d171c116c34d6f0946f81'
assert digest('security/node-exceptions.json') == approved_policy_hash
assert digest('docs/node-agent-inventory.json') == inventory_hash
assert approved_policy_hash in (root / 'vcloud-ssot.yaml').read_text(encoding='utf-8')
mermaid = json.loads(mermaid_path.read_text(encoding='utf-8'))
assert mermaid['status'] == 'passed'
report = {
    'module': 1, 'scope': 'architecture documentation only',
    'status': 'passed', 'adrCount': len(all_adrs), 'componentADRCount': len(adrs),
    'adrLayout': 'canonical' if canonical else 'historical', 'markdownFilesChecked': len(files),
    'localLinksChecked': local_links, 'uniquePrimarySourceURLs': len(source_urls),
    'checks': {'adrCoverageAndStructure': 'passed', 'indexCoverage': 'passed',
               'localLinks': 'passed', 'codeFenceBalance': 'passed',
               'ssotIdentity': 'passed', 'approvedNodePolicyIntegrity': 'passed'},
    'mermaid': mermaid,
    'kubeconform': {'status': 'not_applicable', 'newKubernetesManifests': 0,
                   'reason': 'Module 1 adds documentation, not deployment manifests'},
    'liveAcceptance': 'not executed',
    'implementationGates': ['component version/CRD schema matrix', 'namespace and security profiles',
                            'CSI/object storage and certificates', 'Knative internal encryption suitability',
                            'guarded PostgreSQL read-capacity adapter', 'trace backend',
                            'artifact verification', 'Spinifex admission/capacity adapter'],
    'approvedNodePolicySHA256': approved_policy_hash,
    'originalNodeInventorySHA256': inventory_hash,
    'filesSHA256': {file.relative_to(root).as_posix(): digest(file.relative_to(root)) for file in files}
}
report_path.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
print(json.dumps({key: report[key] for key in ('status', 'adrCount', 'markdownFilesChecked', 'localLinksChecked', 'uniquePrimarySourceURLs', 'mermaid')}))
