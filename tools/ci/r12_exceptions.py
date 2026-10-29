"""Generate the R12 review batch from full scans; never grant owner approval."""
import argparse
from collections import Counter, defaultdict
from copy import deepcopy
from datetime import date, timedelta
import hashlib
import json
from pathlib import Path
import subprocess

import supply_chain as sc
import toolchain_wave as wave

ROOT = Path(__file__).resolve().parents[2]
BASE = '0d950075a8bf43358d9fd406b80b67d657f804e1'
ON = date(2026, 10, 28)
BEFORE_RUN = 'https://github.com/amazen33/twinfra/actions/runs/40659063932'
AFTER_RUN = 'https://github.com/amazen33/twinfra/actions/runs/40767198838'
KEYS = ('target', 'package', 'version', 'vulnerability')


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def save(path, value):
    path = Path(path).resolve()
    path.relative_to(ROOT.resolve())
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', encoding='utf-8', newline='\n') as stream:
        json.dump(value, stream, indent=2)
        stream.write('\n')


def identity(value):
    return tuple(value[k] for k in KEYS)


def component_identity(value):
    return value['target'].split('@')[0], value['package'], value['vulnerability']


def actionable(value):
    return value['kev'] or value['fixAvailable'] and value['severity'] in ('Critical', 'High')


def calendar(entries, merge):
    kev = [e for e in entries if e['vulnerability'] == 'CVE-2026-111497']
    if len(kev) != 1 or kev[0]['expires'] != (merge + timedelta(days=25)).isoformat():
        raise ValueError('One Argo CD KEV entry must expire on merge date + 25 days')
    # O-3 shifts the release window if merge is late; it does not grant any
    # other row a longer lifetime. Refuse a delayed window that needs approval.
    end=date(2026,11,16)+max(timedelta(),merge-date(2026,10,30))
    rows=[]
    for offset in range((end-merge).days+1):
        day=merge+timedelta(days=offset)
        closest=min((date.fromisoformat(e['expires'])-day).days for e in entries)
        if closest <= 7:
            raise ValueError('R12 acceptance calendar has an expiry within seven days')
        rows.append({'date':day.isoformat(),'nearestExpiryDays':closest,'expired':0,'withinSevenDays':0})
    return rows


def upstream_target(component, metadata):
    projects=metadata['projects']
    key={'apiserver':'kubernetes','controller':'kubernetes','scheduler':'kubernetes',
         'envoy':'cilium','operator':'cilium'}.get(component,component)
    project=projects[key]
    wanted={'kubernetes':'v1.36.6','cilium':'v1.20.4','etcd':'v3.6.16',
            'openbao':'v2.7.2','valkey':'8.1.11'}.get(key)
    release=next((v for v in project['releases'] if v['release']==wanted),None)
    if release:
        return f"WO-46 remediation candidate {release['release']}, eligible {release['eligibleAt']}; fixed package/build still requires a full rescan", release['source']
    return 'No verified fixed same-line image release or eligibility date; WO-46 must track upstream and rescan before promotion', project['source']


def package_evidence(folder, value):
    """Retain only public advisory links and image paths, never scanner output."""
    digest=value['target'].split('@sha256:')[-1]
    raw_path=folder/(digest+'.grype.json')
    if not raw_path.is_file():raise ValueError('Full raw image evidence missing')
    raw=read(raw_path);urls=set();paths=set()
    for match in raw['matches']:
        artifact=match['artifact'];vulnerability=match['vulnerability']
        if artifact['name']!=value['package'] or artifact['version']!=value['version']:
            continue
        ids={vulnerability['id'],*(v['id'] for v in match.get('relatedVulnerabilities',[]))}
        if not ids.intersection(value['aliases']):continue
        urls.update(v for v in [vulnerability.get('dataSource'),*vulnerability.get('urls',[])]
                    if isinstance(v,str) and v.startswith('https://') and '@' not in v.split('/')[2])
        paths.update(v['path'] for v in artifact.get('locations',[]) if v.get('path','').startswith('/'))
    # Go's primary advisory and upstream changes are more useful than mirrors.
    ordered=sorted(urls,key=lambda u:(not any(h in u for h in ('pkg.go.dev/vuln/','go.dev/cl/','go.dev/issue/')),u))
    if not ordered:raise ValueError('Upstream fix/advisory evidence missing for '+value['vulnerability'])
    return {'advisorySources':ordered[:6],'imagePaths':sorted(paths),
            'rawGrypeSHA256':hashlib.sha256(raw_path.read_bytes()).hexdigest()}


def make_entry(value, component, evidence, upstream, *, merge, on=ON):
    entry={k:value[k] for k in (*KEYS,'severity')}
    fixes=', '.join(value['fixVersions']) or 'not reported'
    qualified=wave.qualifies(value,wave.policy(ROOT))
    controls=['Dev-only; node/LAN APIs and laptop-loopback tunnel UIs; no public ingress.',
              'Restricted workload profile and default-deny network policies remain unchanged.',
              'Owner performs staging and live acceptance; refresh tracked by WO-46.']
    result=('Potentially reachable: scanner identifies '+value['package']+' in '+component+
            '; image paths '+', '.join(evidence['imagePaths'][:6])+'. No negative reachability claim or image execution.')
    term=30 if value['severity']=='Critical' else 60
    expiry=(on+timedelta(days=term)).isoformat()
    reason=('fixed by WO-46; package fix '+fixes+'. Dev exposure: LAN-only APIs, tunnel-only UIs. '+
            upstream[0]+'. Reachability: '+result+' Upstream: '+evidence['advisorySources'][0])
    if value['kev']:
        if component!='argocd' or value['package']!='libbrotli1' or value['vulnerability']!='CVE-2026-111497':
            raise ValueError('Unapproved remaining KEV')
        expiry=(merge+timedelta(days=25)).isoformat()
        reason=('no upstream Argo CD image contains libbrotli1 ≥ 1.2.0-3ubuntu0.1; fixed by WO-46 item 4. '
                'WO-40 Amendment 10b/O-4b: expected merge '+merge.isoformat()+' + 25 days; checkpoint 2026-11-13. '
                'Static SBOM: libcurl-gnutls.so.4.8.0 imports libbrotlidec; git HTTP helpers import libcurl. '
                'repo-server executes git; Go argocd/helm/kustomize/git-lfs do not link system brotli. '
                'Potentially reachable via Git HTTP; no exploitability or non-reachability claim. '
                'Controls verified against main 0d95007: repo-server external egress github.com:443 only; '
                'server ingress host/remote-node/health:8080 only, internal ClusterIP, no gateway route. '
                'First fixing upstream image must be promoted immediately under the KEV expedite rule; owner O-2/O-4b pending.')
        controls += ['twinfra-argocd-repo-server-network: external FQDN github.com TCP 443 only; internal DNS and Valkey.',
                     'twinfra-argocd-server-network: ingress host, remote-node, health TCP 8080 only; internal egress.',
                     'AppProject sourceRepos only https://github.com/amazen33/twinfra.git; no active remote bases or Jsonnet.']
    if len(reason)>2000:raise ValueError('Exception reason exceeds the schema; shorten explicitly')
    entry.update(owner='amazen33',workOrder='WO-46',approvedBy='',createdOn=on.isoformat(),
                 expires=expiry,reason=reason,controls=controls)
    if qualified:
        admitted=read(ROOT/'tools/ci/toolchain.lock.json')['artifacts']['grype']
        entry['toolchainWave']={'fixVersions':value['fixVersions'],'noEligibleFixedRelease':True,
            'checkedOn':on.isoformat(),'upstreamEvidence':upstream[1],
            'isolation':{'clusterOrLanOnly':True,'noExternalService':True,
                         'externalEgress':'github.com:443 only for repo-server; other components use the documented dev node/LAN or in-cluster paths'},
            'requiredScanner':{'name':'grype','version':'0.119.0','binarySHA256':admitted['binarySHA256']}}
        wave.validate_entry(entry,value,wave.policy(ROOT),on,proposal=True)
    return entry, qualified, result


def generate(before_path, after_path, merge):
    if (ROOT/'security/security-wave-2026-10-approval.json').exists():
        raise ValueError('R12 is owner-approved; preparation cannot overwrite the batch')
    before,after=read(before_path),read(after_path)
    if before['date']!='2026-10-28' or after['date']!='2026-10-28':
        raise ValueError('Refresh dates and evidence explicitly before generating another batch')
    old=subprocess.check_output(['git','-C',str(ROOT),'show',BASE+':security/vulnerability-exceptions.json'])
    old= json.loads(old)['exceptions']
    origins={item['target']:item['origins'][0].split(':')[-1] for item in after['inventory']['images']}
    metadata=read(ROOT/'security/security-wave-2026-10-upstream.json')
    proposals=[];ledger=[];unscoped=[]
    for value in sorted(after['findings'],key=identity):
        if not actionable(value):continue
        component=origins.get(value['target'])
        if not component:
            if value['blocked']:raise ValueError('Blocking finding outside R12 image scope: '+value['target'])
            unscoped.append({k:value[k] for k in (*KEYS,'severity','fixVersions','firstSeen','blocked')})
            continue
        evidence=package_evidence(after_path.parent,value)
        upstream=upstream_target(component,metadata)
        entry,qualified,reachability=make_entry(value,component,evidence,upstream,merge=merge)
        proposals.append(entry)
        predecessors=[e for e in old if component_identity(e)==component_identity(value)]
        ledger.append({k:value[k] for k in (*KEYS,'severity','fixVersions','firstSeen','blocked')}|
            {'component':component,'route':'KEV' if value['kev'] else 'toolchain-wave' if qualified else 'normal',
             'renewal':bool(predecessors),'predecessors':predecessors,'upstream':upstream[0],
             'upstreamSource':upstream[1],'reachability':reachability,'evidence':evidence,'expires':entry['expires']})
    # Do not write blank approvals to the active registry. The existing gate must
    # remain blocking until the owner reviews and authorizes this exact batch.
    proposal={'version':1,'exceptions':proposals}
    projected=deepcopy(proposal)
    for entry in projected['exceptions']:entry['approvedBy']='amazen33' # in-memory owner-approval test fixture only
    sc.validate_exceptions(projected,ROOT,ON)
    state=sc.FirstSeenState(after['firstSeen']);state.identities=after['identityState']
    kev=read(after_path.parent/'kev.json')
    prospective=sc.evaluate(after,projected,kev,state,on=ON,root=ROOT)
    if prospective['status']!='passed':raise ValueError('Proposed batch leaves current scan blockers')
    closed=[]
    for entry in old:
        matches=[v for v in after['findings'] if component_identity(v)==component_identity(entry)]
        if not matches:
            closed.append({'entry':entry,'evidence':AFTER_RUN,'result':'No matching affected package/advisory in full candidate scan'})
    old_after_identities={component_identity(v) for v in after['findings']}
    tables=[]
    targets={v['target'].split('@')[0] for v in before['findings'] if v['blocked']}|{v['target'].split('@')[0] for v in ledger}
    for target in sorted(targets):
        old_block=[v for v in before['findings'] if v['target'].split('@')[0]==target and v['blocked']]
        retained=[v for v in old_block if component_identity(v) in old_after_identities]
        new_block=[v for v in after['findings'] if v['target'].split('@')[0]==target and v['blocked']]
        table={'imageOrLockfile':target,'blockingBefore':len(old_block),'closedBlocking':len(old_block)-len(retained),
               'blockingAfterBeforeApproval':len(new_block),
               'proposedRows':sum(v['target'].split('@')[0]==target for v in proposals),
               'remainingIfApproved':0}
        tables.append(table)
    report={'date':ON.isoformat(),'expectedMergeDate':merge.isoformat(),'ownerApproval':'Pending',
        'baselineRun':BEFORE_RUN,'candidateRun':AFTER_RUN,
        'baselineSHA256':hashlib.sha256(before_path.read_bytes()).hexdigest(),
        'candidateSHA256':hashlib.sha256(after_path.read_bytes()).hexdigest(),
        'fullScan':{'beforeFindings':len(before['findings']),'afterFindings':len(after['findings']),
                    'beforeBlocking':sum(v['blocked'] for v in before['findings']),
                    'afterBlockingBeforeApproval':sum(v['blocked'] for v in after['findings'])},
        'prospectiveOwnerApprovedEvaluation':{'status':prospective['status'],'blocking':0,
                                            'limitation':'In-memory approval fixture, not an active gate pass or actual approval'},
        'counts':dict(Counter(v['route'] for v in ledger)),
        'severities':dict(Counter(v['severity'] for v in ledger)),
        'perImage':tables,'closedExceptions':closed,'ledger':ledger,'outOfScopeGraceFindings':unscoped,
        'calendar':calendar(proposals,merge)}
    save(ROOT/'security/proposals/r12-vulnerability-exceptions.json',proposal)
    save(ROOT/'security/security-wave-2026-10-review.json',report)
    # Fixed rows are closed now; all remaining rows require the owner's exact
    # replacement/renewal batch, without inheriting their earlier approval.
    closed_ids={identity(v['entry']) for v in closed}
    save(ROOT/'security/vulnerability-exceptions.json',{'version':1,'exceptions':[v for v in old if identity(v) not in closed_ids]})
    documentation(report,proposal)
    return report


def documentation(report,proposal):
    lines=['# R12: October security wave review','',
        'Static work only. Owner batch approval, staging, merge and live acceptance are Pending. No image was rebuilt or run.',
        '', 'Authority: [WO-40 Amendments 10–10c](../work-orders/WO-40-twinfra-v0-1-0-release.md), '
        '[ADR-0054 Amendment 1](../adr/amendments/0054-amendment-1-security-fix-carry-forward.md) and '
        '[WO-46](../work-orders/WO-46-post-release-image-refresh-wave.md).', '',
        '## Full scan and per-image disposition','',
        '[Baseline scan]('+BEFORE_RUN+'): 2,178 findings, 374 blocked. '
        '[Candidate full scan]('+AFTER_RUN+'): 2,004 findings, 374 blocked before owner approval. '
        'The raw blocked total is unchanged because 22 retained Criticals in the new Argo CD digest no longer match the old-digest approvals. '
        'The promotions and lockfile fixes remove 22 previously blocking records. No gate or grace period changed.', '',
        'The 420 proposed rows cover all 374 current blockers plus 46 other in-scope image findings: 59 individual Critical renewals '
        '(2026-11-27), 360 High rows (2026-12-27), one Medium KEV (2026-11-24). '
        '270 rows qualify as toolchain-wave; 149 use the normal route; the KEV uses WO-40 Amendment 10b. '
        'Exact package/version/advisory matching remains mandatory; normal Highs are grouped by image/package in the review ledger only.', '',
        '| Image or lockfile | Blocking before | Closed blocking | Raw blocking after | Proposed rows | Remaining if approved |',
        '| --- | ---: | ---: | ---: | ---: | ---: |']
    for row in report['perImage']:
        lines.append('| '+sc.safe(row['imageOrLockfile'])+' | '+' | '.join(str(row[k]) for k in
            ('blockingBefore','closedBlocking','blockingAfterBeforeApproval','proposedRows','remainingIfApproved'))+' |')
    lines += ['', 'Conditional evaluation of an in-memory owner-approved test fixture passes with zero blockers. '
        '**This is not an active gate pass or owner approval.** The active registry closes three fixed exceptions but retains '
        '59 prior Critical approvals until the owner authorizes their individual replacements. Every proposed `approvedBy` is empty.', '',
        'See the [complete High and Critical ledger](security-wave-2026-10-ledger.md), '
        '[machine-readable review](../../security/security-wave-2026-10-review.json) and '
        '[exact proposed replacement registry](../../security/proposals/r12-vulnerability-exceptions.json).', '',
        '## Candidate comparisons and immutable pins','',
        '[Data-only comparison run](https://github.com/amazen33/twinfra/actions/runs/40754061462): '
        'complete Linux amd64 OCI graphs; pinned Syft/Grype and binary-mode govulncheck; no image execution. '
        'User, entrypoint, command and working-directory contracts are unchanged. '
        'Counts below are fixable Critical/High records, not the full nightly gate totals.', '',
        '| Candidate | Before C/H | After C/H | Closed package/advisory identities | Introduced | Decision |',
        '| --- | --- | --- | ---: | ---: | --- |',
        '| Argo CD 3.5.5 | 23/152 | 22/144 | 9 | 0 | Promote; eligible 2026-10-26 |',
        '| Argo CD 3.5.6 | 23/152 | 22/143 | 10 | 0 | Do not promote; KEV remains, no expedite |',
        '| MiniStack 1.5.33 | 3/6 | 0/0 | 9 | 0 | KEV expedite; O-1 |',
        '| Keycloak 26.8.1 | 1/7 | 0/1 | 7 | 0 | Promote; O-1 |', '',
        'Keycloak carries the same Guava 33.6.0-jre / CVE-2026-102554 High as 26.8.0 (fix 33.7.2). '
        'Its CA Critical is cleared, so no CA-bundle exception is needed. The checked-in realm has no external identity providers, '
        'user federation or external SMTP; the unchanged dev network policy permits internal database/DNS only.', '']
    images=read(ROOT/'deploy/common/images.lock.json')['images']
    for name in ('argocd','ministack','keycloak'):
        lines.append('- '+name+': `'+images[name]['canonical']+'`.')
    lines += ['', 'O-1 (owner, 2026-10-28) waives cooling-off for certifi 2026.10.23 in both specified Python locks and DOMPurify 3.4.17 '
        'in the Mermaid lock. Exact hashes and primary licence evidence are generated in the security-wave dependency/carry records. '
        'No other image pin, locally built image, console source, production render or bootstrap lock changes.', '',
        '## O-5 security-fix licence carries','',
        '| Component | Old → new | Tier unchanged | Original backfill due | Advisories cleared |',
        '| --- | --- | ---: | --- | --- |',
        '| MiniStack | 1.5.17 → 1.5.33 | 1 | 2027-04-16 | CVE-2026-111497; GHSA-6q48-6c7w-9gw2 |',
        '| certifi | 2026.7.22 → 2026.10.23 | 3 | 2027-01-14 | GHSA-6q48-6c7w-9gw2 |',
        '| DOMPurify | 3.4.16 → 3.4.17 | 3 | 2027-01-14 | CVE-2026-116804 |', '',
        'The [append-only carry log](../../security/licence-carry-log.json) anchors the original approvals to main `0d95007`. '
        'The current map records `carriedFrom`, exact-version primary licence SHA-256, cleared advisories and O-5 authorization date. '
        '`approvalDate` and `approvedBy` await the PR batch decision. Second carries cannot move the original deadline. '
        'No class, tier or OR-expression logic changes. Argo CD and Keycloak have full new Apache-2.0 qualification records; '
        'their supply-chain criteria remain Pending until the vulnerability batch is approved and the gate passes.', '',
        '## Argo CD brotli KEV: O-4b decision required','',
        '**CVE-2026-111497 / libbrotli1 1.2.0-3build1: one individual row, expected merge 2026-10-30, expiry 2026-11-24.** '
        'Recompute merge + 25 days if the merge date changes. The architect checkpoint is 2026-11-13. '
        'WO-46 must promote the first fixing upstream image immediately under the KEV expedite rule.', '',
        'The complete Syft ELF metadata identifies `/usr/lib/x86_64-linux-gnu/libcurl-gnutls.so.4.8.0` as the direct '
        '`libbrotlidec.so.1` importer. Git HTTP fetch/push, imap-send and remote-http helpers import libcurl. '
        'The repo-server uses Git HTTP helpers ([pinned git execution source](https://github.com/argoproj/argo-cd/blob/v3.5.5/util/git/client.go)). '
        'The Go argocd, helm, kustomize, git-lfs and pebble ELFs do not import that system library. '
        'The amendment’s expected Helm/libcurl path is corrected by this evidence: '
        '[Helm is executed as a Go binary](https://github.com/argoproj/argo-cd/blob/v3.5.5/util/helm/cmd.go). '
        'This is potential reachability, not an exploit test or a non-reachability assertion.', '',
        'The policies are unchanged from main `0d95007`: `twinfra-argocd-repo-server-network` allows external egress '
        'only to github.com TCP 443 (plus internal DNS and Valkey); `twinfra-argocd-server-network` ingress '
        'allows host/remote-node/health TCP 8080 only. Controller and server egress is internal DNS, repo-server, Valkey and the Kubernetes API. '
        'Argo Services are ClusterIP; there is no APISIX route, host port or host-network exposure. '
        'This is static intent, not live Cilium enforcement evidence. A DNS/FQDN policy is not cryptographic proof of GitHub origin.', '',
        'AppProject `sourceRepos` is only `https://github.com/amazen33/twinfra.git`. Active dev Applications use local Git paths; '
        'there are no active OCI sources, Jsonnet sources or remote Kustomize bases. No `helmGlobals.configHome` is configured. '
        'Thus the OCI >4 MiB compatibility case is not used by this profile. Every dev Application retains '
        '`ServerSideDiff=true,IncludeMutationWebhook=true`; Server-Side Diff does not run on initial creation.', '',
        '## Calendar and newly observed grace-period risk','',
        'Every proposed expiry is beyond seven days throughout 2026-10-30–2026-11-16. '
        'The closest expiry on November 16 is November 24 (eight days). Active old approvals are not extended by this report; '
        'the owner must authorize and activate the exact proposed replacements before merge.', '',
        '| Date | Nearest expiry (days) | Expired | Within seven days |',
        '| --- | ---: | ---: | ---: |']
    lines += ['| '+r['date']+' | '+str(r['nearestExpiryDays'])+' | 0 | 0 |' for r in report['calendar']]
    lines += ['', 'Six lockfile Highs are not currently blocking and are outside R12’s image-exception scope. '
        'They must not be mistaken for approved exceptions. The dates below use the unchanged first-seen clock plus 14 days; '
        'they can block subsequent scans during the release window. The owner/architect must assign a fix or separate approval.', '',
        '| Lockfile | Package/version | Advisory | Scanner fixed versions | Blocks from |',
        '| --- | --- | --- | --- | --- |']
    for row in report['outOfScopeGraceFindings']:
        when=(date.fromisoformat(row['firstSeen'])+timedelta(days=14)).isoformat()
        lines.append('| '+' | '.join(sc.safe(v) for v in (row['target'],row['package']+' '+row['version'],row['vulnerability'],', '.join(row['fixVersions']),when))+' |')
    lines += ['', '## Owner execution order','',
        '1. Claude reviews this PR. Owner O-2 approves the exact exception batch; O-4b confirms the KEV term; '
        'O-5 approves each named carry. Implementer records those decisions without changing their due dates, reruns all gates and reports CI. '
        'No pending proposal authorizes merge.',
        '2. Before merge, use the reviewed PR branch in the existing operator checkout with its existing verified console/PostgreSQL archives. '
        'No rebuild is part of R12. Check the context and retrieve digests from the current lock:', '',
        '```powershell',
        "python -c \"import json; from pathlib import Path; d=json.loads(Path('deploy/common/images.lock.json').read_text())['images']; print('\\n'.join(k+': '+d[k]['canonical'] for k in ('argocd','ministack','keycloak')))\"", '```', '',
        'Expected: exactly the three approved candidate digests above. Any disagreement stops staging.', '',
        '```powershell',
        'python tools/platform_dev.py stage-images --context twinfra-dev-cairo-1 --ssh twinfra-operator@192.168.1.3 --archive-dir .build/dev-images',
        '```', '', 'Expected: all application images verified; no running workload changed by staging.', '',
        '```powershell',
        'python tools/platform_dev.py stage-images --context twinfra-dev-cairo-1 --ssh twinfra-operator@192.168.1.3 --check',
        '```', '',
        'Expected: PASS, canonical CRI digests and pinned labels. Only after that check succeeds, the owner adds '
        '`Staging: PASS (stage-images --check, YYYY-MM-DD)` with the actual UTC date to the PR. Never invent that attestation.', '',
        '3. Owner merges after every required check passes; Argo CD then reconciles the approved images, including its own Deployment/StatefulSet. '
        'Observe rollout and all three Applications Synced/Healthy before acceptance. Do not rerun bootstrap, init or reset.',
        '4. In the existing owner live checkout, run the owner-maintained acceptance wrapper (not a tracked repository script):', '',
        '```powershell', '.\\run-acceptance.ps1 -WithRestart', '```', '',
        'Expected: every acceptance check passes, Valkey reconnects, and a new owner receipt is created outside existing signed receipts. '
        'If the wrapper is missing, stop and recover the owner’s existing setup; do not invent credentials or bypass checks. '
        'No receipt is edited by this PR.', '',
        '5. WO-46 follows each upstream fixed-image release. The [primary release metadata](../../security/security-wave-2026-10-upstream.json) '
        'records exact publication/eligibility instants. Kubernetes 1.36.6 is eligible November 11; Cilium 1.20.4 November 6; '
        'etcd 3.6.16 November 5; OpenBao 2.7.2 and Valkey 8.1.11 November 9. These are remediation candidates: '
        'unscanned future images are not claimed fixed. No eligible same-line fix is verified for CoreDNS/CNPG/APISIX/Guava. '
        'WO-46 must verify the relevant fixed packages before promoting; a missing fix remains a tracked individual risk.', '',
        '## Validation status','',
        'CI run links and final results are reported in PR #82. The required gate remains blocked until the owner approval batch '
        'and real staging attestation exist. Static validation is separate from live acceptance. '
        'Local Windows cannot execute the Linux-only shell/systemd/CRI fixture suites faithfully; the six historical Linux legs remain required.', '']
    path=ROOT/'docs/maintenance/security-wave-2026-10.md'
    if report['ownerApproval']=='Approved':
        lines=[lines[0],'',
            '**Activated:** Ahmed Mazen approved O-2/O-4b/O-5 on 2026-10-29 (Africa/Cairo) for the exact batch at `86d4318`. '
            'The active registry contains 420 approved rows. Three carry approvals preserve the original deadlines. '
            'See the [owner decision record](../../security/security-wave-2026-10-approval.json) for immutable proposal/log hashes, '
            'the UTC recording time and the separate owner decision date. Gate approvalDate uses the actual UTC recording date; no future date or gate exception is introduced. '
            'Local re-evaluation of the full final PR scan passes with zero blockers. CI is rerun independently; staging, merge and live acceptance remain Pending.', '',
            '**The proposal review snapshot below is preserved for audit. Its references to pending batch approval describe the pre-activation state at `86d4318`, '
            'not the current active approval. Original proposed JSON remains unchanged with blank approval fields; the active '
            '[exception registry](../../security/vulnerability-exceptions.json) differs only by approvedBy.**','',*lines[1:]]
    path.write_text('\n'.join(lines),encoding='utf-8',newline='\n')
    ledger=['# R12: exact exception review ledger','',
        ('Generated from the full candidate scan. The exact batch is owner-approved (2026-10-29, PR #82 at 86d4318). '
         if report['ownerApproval']=='Approved' else 'Generated from the full candidate scan. Every approval is Pending. ')+
        'See the [review and owner runbook](security-wave-2026-10.md).', '',
        '## Every qualifying and non-qualifying High, grouped by image/package','']
    groups=defaultdict(list)
    for row in report['ledger']:
        if row['severity']=='High':groups[(row['component'],row['package'],row['version'],row['route'])].append(row)
    ledger += ['| Image | Package/version | Route | Every advisory | Scanner fixes | Remediation/eligibility evidence |',
               '| --- | --- | --- | --- | --- | --- |']
    for (component,package,version,route),rows in sorted(groups.items()):
        values=(component,package+' '+version,route,', '.join(sorted(r['vulnerability'] for r in rows)),
                ', '.join(sorted({v for r in rows for v in r['fixVersions']})),rows[0]['upstream'])
        ledger.append('| '+' | '.join(sc.safe(v) for v in values)+' |')
    ledger += ['', '## Each remaining Critical: individual renewal','',
        'Fix/advisory URLs and exact image paths are retained per row in the '
        '[machine-readable ledger](../../security/security-wave-2026-10-review.json). '
        'Reachability is conservatively potentially reachable; no unproven negative result is used to lower severity.', '',
        '| Image | Package/version | Advisory | Fix | Expiry | Primary fix/advisory reference |',
        '| --- | --- | --- | --- | --- | --- |']
    for row in report['ledger']:
        if row['severity']!='Critical':continue
        values=(row['component'],row['package']+' '+row['version'],row['vulnerability'],', '.join(row['fixVersions']),
                row['expires'],row['evidence']['advisorySources'][0])
        ledger.append('| '+' | '.join(sc.safe(v) for v in values)+' |')
    ledger += ['', '## Fixed prior exception rows','',
        '| Old target | Package/version | Advisory | Evidence |', '| --- | --- | --- | --- |']
    for row in report['closedExceptions']:
        entry=row['entry'];values=(entry['target'],entry['package']+' '+entry['version'],entry['vulnerability'],row['evidence'])
        ledger.append('| '+' | '.join(sc.safe(v) for v in values)+' |')
    (ROOT/'docs/maintenance/security-wave-2026-10-ledger.md').write_text('\n'.join(ledger)+'\n',encoding='utf-8',newline='\n')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--before',type=Path,required=True)
    parser.add_argument('--after',type=Path,required=True)
    parser.add_argument('--expected-merge',type=date.fromisoformat,default=date(2026,10,30))
    args=parser.parse_args()
    report=generate(args.before.resolve(),args.after.resolve(),args.expected_merge)
    print(json.dumps({k:report[k] for k in ('counts','severities','fullScan','ownerApproval')}))
