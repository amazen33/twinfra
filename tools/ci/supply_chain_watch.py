"""Weekly upstream comparison: public metadata/downloads only; never edits a lock or runs candidate code."""
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import re
import tarfile
import urllib.error
import urllib.parse
import urllib.request

import supply_chain as sc
from stage_tools import verified, extract_member

# Release provenance is explicit. An absent aged release or unpublished image is
# reported as unavailable, never replaced with latest or guessed publication dates.
IMAGES={
    'registry.k8s.io/kube-apiserver':('kubernetes/kubernetes','{tag}'),
    'registry.k8s.io/kube-controller-manager':('kubernetes/kubernetes','{tag}'),
    'registry.k8s.io/kube-scheduler':('kubernetes/kubernetes','{tag}'),
    'registry.k8s.io/etcd':('kubernetes/kubernetes','kubeadm-etcd'),
    'registry.k8s.io/pause':('kubernetes/kubernetes','kubeadm-pause'),
    'registry.k8s.io/coredns/coredns':('coredns/coredns','{tag}'),
    'quay.io/cilium/cilium':('cilium/cilium','{tag}'),
    'quay.io/cilium/operator-generic':('cilium/cilium','{tag}'),
    'quay.io/cilium/cilium-envoy':('cilium/proxy','{tag}'),
    'docker.io/openbao/openbao':('openbao/openbao','{version}'),
    'quay.io/keycloak/keycloak':('keycloak/keycloak','{version}'),
    'docker.io/apache/apisix':('apache/apisix','{version}-ubuntu'),
    'docker.io/ministackorg/ministack':('ministackorg/ministack','{version}'),
    'quay.io/argoproj/argocd':('argoproj/argo-cd','{tag}'),
    'ghcr.io/cloudnative-pg/cloudnative-pg':('cloudnative-pg/cloudnative-pg','{version}'),
    'ghcr.io/cloudnative-pg/postgresql':('cloudnative-pg/postgres-containers','{version}-standard-trixie'),
    'ghcr.io/cloudnative-pg/pgvector':('cloudnative-pg/pgvector','{version}'),
}
HUB={
    'docker.io/library/busybox':r'^\d+\.\d+\.\d+$',
    'docker.io/library/python':r'^\d+\.\d+\.\d+-slim-trixie$',
    'docker.io/valkey/valkey':r'^\d+\.\d+\.\d+-alpine$',
}
TOOL_RULES={
    'kubeadm':('kubernetes/kubernetes',r'^v\d+\.\d+\.\d+$','kubernetes-kubeadm',None),
    'kubectl':('kubernetes/kubernetes',r'^v\d+\.\d+\.\d+$','kubernetes-kubectl',None),
    'helm':('helm/helm',r'^v\d+\.\d+\.\d+$','helm-linux','linux-amd64/helm'),
    'kubeconform':('yannh/kubeconform',r'^v\d+\.\d+\.\d+$',r'^kubeconform-linux-amd64\.tar\.gz$','kubeconform'),
    'promtool':('prometheus/prometheus',r'^v\d+\.\d+\.\d+$',r'^prometheus-.*\.linux-amd64\.tar\.gz$',r'prometheus-[^/]+/promtool'),
    'shellcheck':('koalaman/shellcheck',r'^v\d+\.\d+\.\d+$',r'^shellcheck-.*\.linux\.x86_64\.tar\.gz$',r'shellcheck-[^/]+/shellcheck'),
    'actionlint':('rhysd/actionlint',r'^v\d+\.\d+\.\d+$',r'^actionlint_.*_linux_amd64\.tar\.gz$','actionlint'),
    'yq':('mikefarah/yq',r'^v\d+\.\d+\.\d+$',r'^yq_linux_amd64$',None),
    'jq':('jqlang/jq',r'^jq-\d+\.\d+\.\d+$',r'^jq-linux-amd64$',None),
    'kustomize':('kubernetes-sigs/kustomize',r'^kustomize/v\d+\.\d+\.\d+$',r'^kustomize_.*_linux_amd64\.tar\.gz$','kustomize'),
    'conftest':('open-policy-agent/conftest',r'^v\d+\.\d+\.\d+$',r'^conftest_.*_Linux_x86_64\.tar\.gz$','conftest'),
    'powershell':('PowerShell/PowerShell',r'^v\d+\.\d+\.\d+$',r'^powershell-.*-linux-x64\.tar\.gz$','pwsh'),
    'syft':('anchore/syft',r'^v\d+\.\d+\.\d+$',r'^syft_.*_linux_amd64\.tar\.gz$','syft'),
    'grype':('anchore/grype',r'^v\d+\.\d+\.\d+$',r'^grype_.*_linux_amd64\.tar\.gz$','grype'),
    'osv-scanner':('google/osv-scanner',r'^v\d+\.\d+\.\d+$',r'^osv-scanner_linux_amd64$',None),
}


def newest(values,on,pattern=r'^v?\d+\.\d+\.\d+$'):
    cutoff=datetime.combine(on,datetime.min.time(),tzinfo=timezone.utc)-timedelta(days=14)
    eligible=[v for v in values if not v.get('draft') and not v.get('prerelease') and
              re.fullmatch(pattern,v['tag_name']) and
              datetime.fromisoformat(v['published_at'].replace('Z','+00:00'))<=cutoff]
    return max(eligible,key=lambda v:v['published_at']) if eligible else None


def releases(repo,memo):
    if repo not in memo:
        memo[repo]=json.loads(sc.fetch('https://api.github.com/repos/'+repo+'/releases?per_page=100'))
    return memo[repo]


def registry_digest(repository,tag):
    host,path=repository.split('/',1)
    host='registry-1.docker.io' if host=='docker.io' else host
    url='https://'+host+'/v2/'+path+'/manifests/'+urllib.parse.quote(tag,safe='')
    accept='application/vnd.oci.image.index.v1+json,application/vnd.docker.distribution.manifest.list.v2+json,application/vnd.oci.image.manifest.v1+json,application/vnd.docker.distribution.manifest.v2+json'
    headers={'Accept':accept,'User-Agent':'Twinfra-supply-chain-watch'}
    def get():
        with urllib.request.urlopen(urllib.request.Request(url,headers=headers),timeout=120) as response:
            return response.read(),response.headers.get('Docker-Content-Digest')
    try:raw,declared=get()
    except urllib.error.HTTPError as error:
        if error.code!=401:raise
        challenge=error.headers.get('WWW-Authenticate','')
        attrs=dict(re.findall(r'(\w+)="([^"]+)"',challenge))
        realm=attrs['realm'];service=attrs.get('service',host)
        if urllib.parse.urlsplit(realm).hostname not in ('auth.docker.io',host):raise ValueError('Unexpected registry auth realm')
        token=json.loads(sc.fetch(realm+'?'+urllib.parse.urlencode(dict(service=service,scope='repository:'+path+':pull'))))
        headers['Authorization']='Bearer '+(token.get('token') or token['access_token'])
        raw,declared=get()
    value=json.loads(raw)
    if 'config' not in value and 'manifests' not in value:raise ValueError('Not an OCI manifest')
    digest='sha256:'+sc.sha(raw)
    if declared and declared!=digest:raise ValueError('Registry digest mismatch')
    return digest


def image_candidate(repository,on,memo):
    if repository in HUB:
        repo=repository.removeprefix('docker.io/')
        values=json.loads(sc.fetch('https://hub.docker.com/v2/repositories/'+repo+'/tags?page_size=100'))['results']
        values=[dict(tag_name=v['name'],published_at=v['last_updated']) for v in values]
        release=newest(values,on,HUB[repository]);tag=release['tag_name'] if release else None
    elif repository in IMAGES:
        repo,template=IMAGES[repository]
        release=newest(releases(repo,memo),on)
        if not release:return None
        version=release['tag_name'].removeprefix('v');tag=template.format(tag=release['tag_name'],version=version)
        if template.startswith('kubeadm-'):
            raw=sc.fetch('https://raw.githubusercontent.com/kubernetes/kubernetes/'+release['tag_name']+'/cmd/kubeadm/app/constants/constants.go').decode()
            pattern=r'PauseVersion\s*=\s*"([^"]+)"' if template=='kubeadm-pause' else r'"([0-9]+\.[0-9]+\.[0-9]+-[0-9]+)"'
            matches=re.findall(pattern,raw)
            if not matches:raise ValueError('No release-matched kubeadm dependency version')
            tag=matches[-1] if template=='kubeadm-etcd' else matches[0]
    elif repository.startswith('docker.io/twinfra/'):
        return None  # Own unpublished builds: input coverage is explicit in the report.
    else:raise ValueError('Unmapped upstream image: '+repository)
    if not release:return None
    digest=registry_digest(repository,tag)
    return dict(target=repository+'@'+digest,source='registry:'+repository+'@'+digest,digest=digest,
                platform='linux/amd64',release=tag,publishedAt=release['published_at'],origins=[],introduced=False)


def member(path,pattern):
    if not pattern:return path.read_bytes()
    with tarfile.open(path) as archive:
        choices=[v.name for v in archive.getmembers() if v.isfile() and re.fullmatch(pattern,v.name)]
    if len(choices)!=1:raise ValueError('Unique candidate binary member required')
    return extract_member(path,choices[0])


def tool_candidate(name,root,out,on,memo):
    repo,pattern,asset_pattern,archive_member=TOOL_RULES[name]
    release=newest(releases(repo,memo),on,pattern)
    if not release:return None
    tag=release['tag_name']
    if asset_pattern.startswith('kubernetes-'):
        binary=asset_pattern.removeprefix('kubernetes-')
        url=f'https://dl.k8s.io/release/{tag}/bin/linux/amd64/{binary}'
        checksum=sc.fetch(url+'.sha256').decode().strip();raw=verified(sc.fetch(url),checksum)
    elif asset_pattern=='helm-linux':
        url=f'https://get.helm.sh/helm-{tag}-linux-amd64.tar.gz'
        checksum=sc.fetch(url+'.sha256sum').decode().split()[0];raw=verified(sc.fetch(url),checksum)
    else:
        assets=[v for v in release['assets'] if re.fullmatch(asset_pattern,v['name'])]
        if len(assets)!=1:raise ValueError('Unique Linux amd64 candidate asset required')
        asset=assets[0];url=asset['browser_download_url'];checksum=asset.get('digest','').removeprefix('sha256:')
        if not re.fullmatch(r'[a-f0-9]{64}',checksum):raise ValueError('Candidate has no official asset SHA256')
        raw=verified(sc.fetch(url),checksum)
    archive=out/(name+'-candidate.download');archive.write_bytes(raw)
    binary=member(archive,archive_member);digest='sha256:'+sc.sha(binary)
    target=out/(name+'-candidate.binary');target.write_bytes(binary)
    return dict(target='tool:'+name+'@'+digest,source='file:'+target.as_posix(),digest=digest,
                platform='linux/amd64',release=tag,publishedAt=release['published_at'],url=url,downloadSHA256=checksum,
                origins=[],introduced=False)


def watch(root,tools,out,cache):
    plan=sc.inventory(root,full=True);current=sc.scan(plan,tools,cache,out,root)
    memo={};comparisons=[];on=sc.today()
    lock=sc.read(root/'tools/ci/toolchain.lock.json')['artifacts']
    binary_names={name for name,value in lock.items() if value['output'].startswith('bin/') or value.get('runtimeArchive')}
    if binary_names-set(TOOL_RULES):raise ValueError('Unmapped CI tools: '+str(sorted(binary_names-set(TOOL_RULES))))
    candidates=[];existing=list(plan['images'])
    for name in sorted(binary_names):
        item=lock[name];raw=verified(sc.fetch(item['url']),item['sha256'])
        archive=out/(name+'-current.download');archive.write_bytes(raw)
        binary=extract_member(archive,item['member']) if item.get('member') else (member(archive,'pwsh') if item.get('runtimeArchive') else raw)
        path=out/(name+'-current.binary');path.write_bytes(binary);digest='sha256:'+sc.sha(binary)
        existing.append(dict(target='tool:'+name+'@'+digest,source='file:'+path.as_posix(),digest=digest,
                             platform='linux/amd64',origins=[],introduced=False,tool=name))
    for item in existing:
        try:
            repository=item['target'].split('@')[0]
            if ':' in repository.rsplit('/',1)[-1]:repository=repository.rsplit(':',1)[0]
            candidate=tool_candidate(item['tool'],root,out,on,memo) if 'tool' in item else image_candidate(repository,on,memo)
            reason=None if candidate else 'No verifiable aged published upstream candidate; locks unchanged.'
        except (ValueError,KeyError,OSError) as error:
            candidate=None;reason='Candidate unavailable: '+str(error)
        if candidate:candidates.append(candidate)
        comparisons.append(dict(current=item,candidate=candidate,unavailableReason=reason))
    # Candidate binaries are data inputs, never subprocess executables.
    more=sc.scan(dict(images=existing[len(plan['images']):]+candidates,lockfiles=[],coverage=[],base=None),tools,cache,out/'watch-inputs',root) if candidates or binary_names else {'findings':[]}
    all_findings=current['findings']+more['findings']
    lines=['# Upstream updates available','',
           'Newest verifiable published releases at least 14 days old; no lock writes or update PRs.','',
           '| Current pinned input | Candidate | Published | Current findings | Candidate findings | Detail |',
           '| --- | --- | --- | ---: | ---: | --- |']
    for value in comparisons:
        a=value['current'];b=value['candidate'];old=[f for f in all_findings if f['target']==a['target']]
        new=[f for f in all_findings if b and f['target']==b['target']]
        value.update(currentFindings=old,candidateFindings=new)
        lines.append('| '+' | '.join(sc.safe(x) for x in (a['target'],b['target'] if b else 'Unavailable',
                      b['publishedAt'] if b else '',len(old),len(new) if b else '',value['unavailableReason'] or b['release']))+' |')
    return dict(version=1,date=on.isoformat(),comparisons=comparisons,markdown='\n'.join(lines)+'\n',
                status='reported',lockWrites=False,updatePRs=False,inventoryCoverage=plan['coverage'])
