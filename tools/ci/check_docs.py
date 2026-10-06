from pathlib import Path
import hashlib
import json
import re
from urllib.parse import unquote

import sys
root = Path(sys.argv[1]).resolve()
report_path = Path(sys.argv[2]).resolve()
mermaid_path = Path(sys.argv[3]).resolve()
adrs = sorted((root / 'docs/adrs').glob('[0-9]*.md'))
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

files = adrs + [root / 'docs/adrs/README.md', root / 'docs/module-1-topology.md',
               root / 'docs/module-1-summary.md', root / 'README.md']
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
            assert (file.parent / target_path).exists(), (file, target_path)
            local_links += 1
index = (root / 'docs/adrs/README.md').read_text(encoding='utf-8')
for file in adrs:
    assert file.name in index
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
    'status': 'passed', 'adrCount': len(adrs), 'markdownFilesChecked': len(files),
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
