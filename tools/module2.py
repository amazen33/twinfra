#!/usr/bin/env python3
"""Offline rendering/validation and fail-closed live preparation for Module 2."""
import argparse
import copy
from decimal import Decimal
from datetime import datetime, timezone
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import platform
import re
import stat
import subprocess
import sys
import time
import tomllib
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
from check_manifest_contract import load_policy
from manifest_contract import audit_objects, flatten, podspec, pod_projection

ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / 'module-2'
GROUPS = ('storage', 'network', 'database', 'function', 'children')


def merge(left, right):
    result = copy.deepcopy(left)
    for key, value in right.items():
        result[key] = merge(result[key], value) if isinstance(value, dict) and isinstance(result.get(key), dict) else copy.deepcopy(value)
    return result


def dump(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding='utf-8', newline='\n')


def run(command, accepted=(0,)):
    result = subprocess.run([str(x) for x in command], text=True, capture_output=True, encoding='utf-8')
    if result.returncode not in accepted:
        raise RuntimeError(f'{Path(str(command[0])).name} failed ({result.returncode}): {(result.stderr or result.stdout)[:4000]}')
    return result


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def values(site):
    return merge(yaml.safe_load((MODULE / 'chart/values.yaml').read_text()), yaml.safe_load(site.read_text()) or {})


def check_values(v, live=False, dependencies=True):
    ssot = yaml.safe_load((ROOT / 'vcloud-ssot.yaml').read_text())
    if (v['registry'] != ssot['registry'] or v['clusterName'] != ssot['cluster']['name'] or
            v['baseDomain'] != ssot['cluster']['baseDomain'] or
            v['git']['upstream'] != 'https://github.com/' + ssot['cluster']['gitOpsRepository'] + '.git'):
        raise ValueError('Module 2 identity must agree with SSoT v2.2')
    if not v['git']['repoURL'].endswith('/amazen33/twinfra.git') or not v['git']['repoURL'].startswith('https://'):
        raise ValueError('Git transport must be HTTPS and mirror amazen33/twinfra')
    if not re.fullmatch(r'[a-f0-9]{40}|vcloud-module-2-v\d+\.\d+\.\d+', v['git']['revision']):
        raise ValueError('Use an immutable Git commit or the documented release tag')
    if v['function']['maxScale'] != 1:
        raise ValueError('Local function profile permits one replica; multi-node storage needs a separate profile')
    if v['database']['instances'] < 1 or v['database']['instances'] > 3:
        raise ValueError('This storage profile supports 1–3 PostgreSQL instances')
    if v['database']['autoscaler']['allowDecrease']:
        raise ValueError('Automatic memory reduction is not approved by this profile')
    scaling = v['database']['autoscaler']
    if scaling['cooldownSeconds'] < 3600 or not 60 <= scaling['recommendationMaxAgeSeconds'] <= 900 or scaling['minChangeRatio'] < 1.25:
        raise ValueError('Autoscaling cooldown/freshness/hysteresis exceeds the reviewed profile')
    for current, low, high in [('cpu','minCPU','maxCPU'),('memory','minMemory','maxMemory')]:
        if not 0 < resource_quantity(scaling[low]) <= resource_quantity(v['database'][current]) <= resource_quantity(scaling[high]):
            raise ValueError('Initial CPU/memory resources must be within positive scaler bounds')
    if v['database']['instances'] > 1 and v['database']['antiAffinityType'] != 'required':
        raise ValueError('Multiple database instances require different physical nodes')
    if not 0 < v['hpc']['mpiPortMin'] <= v['hpc']['mpiPortMax'] < 65536 or v['hpc']['mpiPortMax'] - v['hpc']['mpiPortMin'] > 255:
        raise ValueError('MPI requires a bounded range of at most 256 ports')
    if v['hpc']['secondaryNetworksApproved']:
        raise ValueError('No SR-IOV secondary network/fabric exception is granted here')
    names, paths = set(), set()
    for volume in v['storage']['volumes']:
        if volume['name'] in names or (volume['node'], volume['path']) in paths:
            raise ValueError('Duplicate local storage identity/path')
        names.add(volume['name']); paths.add((volume['node'], volume['path']))
        suffix = 'function' if volume['name'] == 'function-data' else volume['name']
        if not re.fullmatch(r'function|postgres-[123]', suffix) or volume['path'] != '/var/lib/vcloud/local-pv/' + suffix:
            raise ValueError('Local storage escapes the explicit vCloud directory plan')
        expected_uid = 65532 if suffix == 'function' else 26
        if (volume['uid'], volume['gid']) != (expected_uid, expected_uid):
            raise ValueError('Incorrect local-volume ownership plan')
        namespace = 'workload-apps' if suffix == 'function' else 'platform-services'
        claim = 'function-data' if suffix == 'function' else v['database']['name'] + '-' + suffix.split('-')[1]
        mode = 'ReadOnlyMany' if suffix == 'function' else 'ReadWriteOnce'
        if (volume['namespace'], volume['claim'], volume['mode']) != (namespace, claim, mode):
            raise ValueError('Local PV namespace/claim/access mode must match its workload')
        byte_quantity(volume['size'])
        if suffix != 'function' and volume['size'] != v['database']['size']:
            raise ValueError('Database PVC size differs from its prebound Local PV')
    if names != {'function-data'} | {f'postgres-{i}' for i in range(1, v['database']['instances'] + 1)}:
        raise ValueError('Local PV plan must match function and PostgreSQL instance count')
    if len({x['node'] for x in v['storage']['volumes'] if x['name'].startswith('postgres-')}) != v['database']['instances']:
        raise ValueError('Database Local PVs must be on different nodes')
    for key in ('adminCIDR','podCIDR'):
        if ipaddress.ip_network(v['site'][key], strict=True).prefixlen == 0:
            raise ValueError('Default-route CIDRs forbidden')
    if v['function']['name'] != 'secure-function' or v['function']['routeHost'] != 'secure-function.workload-apps.svc.cluster.local' or v['knative']['namespace'] != 'platform-services':
        raise ValueError('This fixed policy profile requires the documented function/Knative identities')
    if v['apisix']['issuer'] != 'https://auth.' + v['baseDomain'] + '/realms/vcloud':
        raise ValueError('The reviewed gateway profile requires its canonical HTTPS Keycloak issuer')
    for key in ('registryCIDRs','gitCIDRs','dnsCIDRs','identityCIDRs'):
        if not v['site'][key]:
            raise ValueError('Explicit site CIDRs required: ' + key)
        for cidr in v['site'][key]:
            network = ipaddress.ip_network(cidr, strict=True)
            if network.prefixlen == 0:
                raise ValueError('Default-route CIDRs forbidden')
    for image in (v['function']['image'], v['database']['image']):
        if not image.startswith(v['registry'] + '/') or not re.search(r'@sha256:[a-f0-9]{64}$|:\d+\.\d+\.\d+[A-Za-z0-9._-]*$', image):
            raise ValueError('Every application image must be pinned in the SSoT registry')
    if live:
        if v['site']['referenceOnly']:
            raise ValueError('Reference site cannot be diffed/applied; configure a real site')
        address = ipaddress.ip_address(v['site']['apiHost'])
        if not address.is_private or any(address in ipaddress.ip_network(c) for c in ('192.0.2.0/24','198.51.100.0/24','203.0.113.0/24')):
            raise ValueError('API address must be a configured private site address')
        for cidr in [v['site']['adminCIDR'], *v['site']['registryCIDRs'], *v['site']['gitCIDRs'], *v['site']['dnsCIDRs'], *v['site']['identityCIDRs']]:
            if any(ipaddress.ip_network(cidr).overlaps(ipaddress.ip_network(c)) for c in ('192.0.2.0/24','198.51.100.0/24','203.0.113.0/24') if ipaddress.ip_network(cidr).version == 4):
                raise ValueError('Replace all documentation CIDRs before live bootstrap')
        if not v['git']['mirrorReady']:
            raise ValueError('Publish the immutable amazen33/twinfra tree to the internal Git mirror first')
        flags = [v['knative']['controllerProfileReady'], v['knative']['internalTLSReady'], v['apisix']['profileReady']]
        if dependencies and not all(flags + [v['dependencies'][x] for x in ('cnpgReady','vpaReady','argocdReady')]):
            raise ValueError('Pinned dependency, restricted-pod and verified TLS profiles are not recorded ready')
        for name, images in v['dependencies']['images'].items() if dependencies else []:
            if not images or any(not image.startswith(v['registry'] + '/') or not re.search(r'@sha256:[a-f0-9]{64}$|:v?\d+\.\d+\.\d+[A-Za-z0-9._-]*$', image) for image in images):
                raise ValueError('Record exact mirrored dependency images before apply: ' + name)
    return v


def verify_bundle():
    lock = json.loads((MODULE / 'artifacts.lock.json').read_text())
    for filename, expected in lock['filesSHA256'].items():
        path = (ROOT / filename).resolve()
        if not path.is_relative_to(MODULE.resolve()) or sha(path) != expected:
            raise ValueError('Offline artifact checksum mismatch: ' + filename)
    return lock


def render(args, v):
    verify_bundle()
    args.build.mkdir(parents=True, exist_ok=True)
    dump(args.build / 'effective-values.yaml', v)
    cilium = yaml.safe_load((MODULE / 'values/cilium.yaml').read_text())
    cilium['k8sServiceHost'] = v['site']['apiHost']
    cilium['ipv4NativeRoutingCIDR'] = v['site']['podCIDR']
    cilium['devices'] = v['site']['devices']
    dump(args.build / 'cilium-values.yaml', cilium)
    apisix = yaml.safe_load((MODULE / 'values/apisix.yaml').read_text())
    apisix['apisix']['fullCustomConfig']['config']['deployment']['admin']['allow_admin'] = [v['site']['podCIDR']]
    dump(args.build / 'apisix-values.yaml', apisix)
    commands = [
        ('cilium.yaml', [args.helm, 'template', 'cilium', MODULE / 'vendor/cilium-1.20.2.tgz', '--namespace', 'kube-system', '--kube-version', '1.36.5', '--values', args.build / 'cilium-values.yaml']),
        ('foundation.yaml', [args.helm, 'template', 'vcloud-foundation', MODULE / 'chart', '--namespace', 'platform-services', '--kube-version', '1.36.5', '--values', args.build / 'effective-values.yaml']),
        ('apisix-dependency.yaml', [args.helm, 'template', 'apisix', MODULE / 'vendor/apisix-2.18.0.tgz', '--namespace', 'platform-services', '--kube-version', '1.36.5', '--values', args.build / 'apisix-values.yaml']),
    ]
    for filename, command in commands:
        (args.build / filename).write_text(run(command).stdout, encoding='utf-8', newline='\n')
    with (args.build / 'apisix-dependency.yaml').open('a', encoding='utf-8', newline='\n') as file:
        file.write('\n---\n' + (MODULE / 'values/apisix-serviceaccount.yaml').read_text())
    for group in GROUPS:
        command = commands[1][1] + ['--set', 'renderGroup=' + group]
        (args.build / (group + '.yaml')).write_text(run(command).stdout, encoding='utf-8', newline='\n')
    # Root/ApplicationProject come from the full render, without reapplying child workloads.
    objects = list(flatten(yaml.safe_load_all((args.build / 'foundation.yaml').read_text())))
    root_objects = [obj for obj in objects if obj['kind'] == 'AppProject' or (obj['kind'] == 'Application' and obj['metadata']['name'] == 'vcloud-root')]
    (args.build / 'root.yaml').write_text(yaml.safe_dump_all(root_objects, sort_keys=False), encoding='utf-8', newline='\n')
    print('Rendered Cilium, foundation and APISIX dependency profile from local, checksummed inputs')


def audit(objects, v):
    objects = normalize_pods(objects)
    policy = load_policy()
    # Static plan approval is confined to exact Local PV definitions below. Physical
    # inspection remains a separate compulsory live gate; original node policy is unchanged.
    pvs = [obj for obj in objects if obj['kind'] == 'PersistentVolume']
    expected = {f'vcloud-{item["name"]}': item for item in v['storage']['volumes']}
    policy['localPVs'] = {}
    for pv in pvs:
        item = expected.get(pv['metadata']['name'])
        if not item or pv['spec'].get('local') != {'path': item['path']}:
            raise ValueError('Local PV not in the exact storage plan')
        affinity = {'required': {'nodeSelectorTerms': [{'matchExpressions': [{'key': 'kubernetes.io/hostname', 'operator': 'In', 'values': [item['node']]}]}]}}
        spec = pv['spec']
        if (spec.get('nodeAffinity') != affinity or spec.get('capacity') != {'storage': item['size']} or
                spec.get('claimRef') != {'namespace': item['namespace'], 'name': item['claim']} or
                spec.get('persistentVolumeReclaimPolicy') != 'Retain' or
                spec.get('accessModes') != [item['mode']] or spec.get('storageClassName') != v['storage']['className']):
            raise ValueError('Local PV drift from the exact retention/node/claim plan')
        policy['localPVs'][pv['metadata']['name']] = {key: spec.get(key) for key in ('local','nodeAffinity','accessModes','volumeMode','storageClassName')}
    # These served Argo CRDs are non-deprecated. The older generic engine's blanket
    # alpha/beta filter is not used to misclassify them; strict pinned schemas check them.
    argo = [obj for obj in objects if obj['apiVersion'] == 'argoproj.io/v1alpha1' and obj['kind'] in ('Application','AppProject')]
    result = audit_objects([obj for obj in objects if obj not in argo], policy)
    if result['violations']:
        raise ValueError('\n'.join(result['violations']))
    for obj in objects:
        spec = podspec(obj)
        if spec and not obj['metadata'].get('namespace') == 'kube-system':
            for container in pod_projection(obj)['containers']:
                security = container['securityContext']
                if security['allowPrivilegeEscalation'] or security['capabilities']['drop'] != ['ALL'] or security.get('seccompProfile') != {'type': 'RuntimeDefault'}:
                    raise ValueError('Restricted application security contract violated')
            if any('k8s.v1.cni.cncf.io/networks' in obj.get('metadata', {}).get('annotations', {}) for obj in [obj, obj.get('spec', {}).get('template', {})]):
                raise ValueError('Unreviewed secondary network annotation')
        if obj['kind'] == 'Application':
            source = obj['spec']['source']
            if source['repoURL'] != v['git']['repoURL'] or source['targetRevision'] != v['git']['revision'] or obj['spec']['syncPolicy']['automated']['prune']:
                raise ValueError('Argo source pin or stateful pruning contract violated')
        if obj['kind'] == 'Cluster':
            spec = obj['spec']
            if (spec['imageName'] != v['database']['image'] or spec['postgresUID'] != 26 or
                    spec['imagePullPolicy'] != 'IfNotPresent' or not spec['securityContext']['runAsNonRoot'] or
                    spec['storage']['storageClass'] != v['storage']['className'] or
                    spec['bootstrap']['initdb']['postInitApplicationSQL'] != ['CREATE EXTENSION IF NOT EXISTS vector;']):
                raise ValueError('CloudNativePG storage/image/extension/security contract violated')
        if obj['kind'] == 'VerticalPodAutoscaler' and obj['spec']['updatePolicy']['updateMode'] != 'Off':
            raise ValueError('VPA must not resize/evict CNPG Pods directly')
        if obj['kind'] == 'ConfigMap' and obj['metadata']['name'] == 'apisix':
            apisix_runtime_contract(yaml.safe_load(obj['data']['config.yaml']))
    network_contract(objects, v)
    return result


def normalize_pods(objects):
    # Kubernetes treats explicit null optional container arrays as absent. Keep
    # the frozen node auditor unchanged while normalizing that schema-valid form.
    objects = copy.deepcopy(objects)
    for obj in objects:
        spec = podspec(obj)
        if spec:
            for key in ('initContainers','ephemeralContainers'):
                if key in spec and spec[key] is None:
                    spec[key] = []
    return objects


def network_contract(objects, v):
    policies = {(o['metadata'].get('namespace'), o['metadata']['name']): o['spec'] for o in objects if o['kind'] == 'CiliumNetworkPolicy'}
    for namespace in ('platform-services','workload-apps','hpc-compute'):
        if policies.get((namespace,'baseline-deny-all')) != {'endpointSelector': {}, 'ingress': [], 'egress': []}:
            raise ValueError('Missing exact namespace deny-all baseline')
        dns = policies[(namespace, 'allow-internal-dns')]
        expected = {'k8s:io.kubernetes.pod.namespace': 'kube-system', 'k8s:k8s-app': 'kube-dns'}
        rule = dns['egress'][0]
        if dns['endpointSelector'] != {} or rule['toEndpoints'] != [{'matchLabels': expected}] or rule['toPorts'][0]['ports'] != [{'port': '53','protocol':'UDP'},{'port':'53','protocol':'TCP'}]:
            raise ValueError('DNS must be limited to kube-dns TCP/UDP 53')
    hpc = policies[('hpc-compute','hpc-bounded-ssh-mpi')]
    expected_labels = {'k8s:vcloud.io/hpc-ssh-mpi': 'enabled', 'k8s:vcloud.io/hpc-job-group': v['hpc']['jobGroup']}
    if hpc['endpointSelector'] != {'matchLabels': expected_labels}:
        raise ValueError('HPC traffic must be scoped to the opted-in job group')
    for direction, endpoint in [('ingress','fromEndpoints'),('egress','toEndpoints')]:
        rule = hpc[direction][0]
        if rule[endpoint] != [{'matchLabels': expected_labels | {'k8s:io.kubernetes.pod.namespace':'hpc-compute'}}] or rule['toPorts'][0]['ports'] != [{'port':'22','protocol':'TCP'},{'port':'2222','protocol':'TCP'},{'port':str(v['hpc']['mpiPortMin']),'endPort':v['hpc']['mpiPortMax'],'protocol':'TCP'}]:
            raise ValueError('HPC ports/peers drifted from the bounded MPI contract')
    gateway = policies[('platform-services','apisix-entry-and-knative')]
    if gateway['egress'][0]['toEndpoints'] != [{'matchLabels': {'k8s:io.kubernetes.pod.namespace':v['knative']['namespace'],'k8s:app':'3scale-kourier-gateway'}}]:
        raise ValueError('APISIX must route through the Knative gateway')
    for policy in policies.values():
        for direction in ('ingress','egress'):
            for rule in policy.get(direction, []):
                if rule.get('toEntities') == ['all'] or rule.get('fromEntities') == ['all'] or rule == {}:
                    raise ValueError('Unbounded policy allow rule')
                for key in ('toCIDR','fromCIDR'):
                    if any(ipaddress.ip_network(cidr).prefixlen == 0 for cidr in rule.get(key, [])):
                        raise ValueError('Unbounded network CIDR')
    route = next(o for o in objects if o['kind'] == 'ApisixRoute')['spec']['http'][0]
    plugins = {p['name']: p['config'] for p in route['plugins'] if p['enable']}
    oidc = plugins['openid-connect']
    if not oidc['bearer_only'] or not oidc['ssl_verify'] or not oidc['use_jwks'] or oidc['accept_none_alg'] or oidc['accept_unsupported_alg']:
        raise ValueError('Gateway must verify bearer tokens and IdP TLS')
    if oidc['claim_validator'] != {'issuer': {'valid_issuers':[v['apisix']['issuer']]},'audience':{'required':True,'match_with_client_id':True}} or oidc['discovery'] != v['apisix']['issuer'] + '/.well-known/openid-configuration':
        raise ValueError('Gateway must enforce the configured issuer and required audience')
    if route['backends'][0]['serviceName'] != v['knative']['kourierService'] or plugins['proxy-rewrite']['host'] != v['function']['routeHost']:
        raise ValueError('Gateway backend/Knative Host mismatch')


def apisix_runtime_contract(config):
    deployment = config.get('deployment',{})
    admin = deployment.get('admin',{})
    snippet = {line.strip() for line in config.get('nginx_config',{}).get('http_configuration_snippet','').splitlines() if line.strip()}
    if snippet != {'proxy_ssl_verify on;','proxy_ssl_verify_depth 3;','proxy_ssl_trusted_certificate /etc/vcloud-ca/ca.crt;'}:
        raise ValueError('APISIX upstream TLS verification/CA contract violated')
    if deployment.get('role') != 'traditional' or deployment.get('role_traditional',{}).get('config_provider') != 'yaml':
        raise ValueError('APISIX must use the one-writer API-driven standalone profile')
    if not admin.get('https_admin') or not admin.get('admin_key_required') or admin.get('enable_admin_ui') or admin.get('enable_admin_cors'):
        raise ValueError('APISIX administration must be private authenticated TLS')
    if admin.get('admin_key') != [{'name':'controller','key':'${{APISIX_ADMIN_KEY}}','role':'admin'}]:
        raise ValueError('APISIX admin credentials must use runtime environment interpolation')


def validate(args, v):
    render(args, v)
    validate_rendered(args, v)


def validate_rendered(args, v):
    paths = [args.build / 'cilium.yaml', args.build / 'foundation.yaml', args.build / 'apisix-dependency.yaml']
    # CRD and core schema locations are LOCAL ONLY; no default URL or ignore-missing flag.
    locations = [str(MODULE / 'schemas/{{.Group}}/{{.ResourceKind}}_{{.ResourceAPIVersion}}.json'),
                 str(MODULE / 'schemas/{{.ResourceKind}}_{{.ResourceAPIVersion}}.json')]
    command = [args.kubeconform, '-strict', '-summary', '-kubernetes-version', '1.36.5']
    for location in locations:
        command += ['-schema-location', location]
    result = run(command + paths)
    print(result.stdout.strip())
    objects = list(flatten(obj for path in paths for obj in yaml.safe_load_all(path.read_text())))
    report = audit(objects, v)
    cilium = yaml.safe_load((args.build / 'cilium-values.yaml').read_text())
    if not all((cilium['kubeProxyReplacement'], cilium['hostFirewall']['enabled'], cilium['bandwidthManager']['enabled'])):
        raise ValueError('Required Cilium features disabled')
    evidence = {'status': 'passed', 'resources': len(objects), 'schemaValidation': result.stdout.strip(),
                'acceptedNodeExceptions': report['acceptedExceptions'], 'physicalLocalPVVetting': 'required before apply',
                'liveTests': 'not run by static validation', 'renderedSHA256': {p.name: sha(p) for p in paths}}
    (args.build / 'validation.json').write_text(json.dumps(evidence, indent=2) + '\n', encoding='utf-8', newline='\n')
    print('SSoT/node scope and static Local PV plan passed; physical vetting remains compulsory')


def inspect_volume(item):
    path = Path(item['path'])
    if not path.exists() or not path.is_dir():
        raise ValueError('Prepare the local volume directory first: ' + str(path))
    for part in (path, *path.parents):
        if part.is_symlink():
            raise ValueError('Symlinks forbidden in local-volume ancestry')
    info = path.stat()
    if (info.st_uid, info.st_gid) != (item['uid'], item['gid']) or info.st_mode & stat.S_IWOTH:
        raise ValueError('Incorrect owner/group or world-writable volume: ' + str(path))
    mount = json.loads(run(['findmnt', '-J', '-T', path, '-o', 'TARGET,SOURCE,FSTYPE']).stdout)['filesystems'][0]
    if mount['fstype'] not in ('ext4','xfs') or not (mount['target'] == '/var/lib/vcloud/local-pv' or str(mount['target']).startswith('/var/lib/vcloud/local-pv/')):
        raise ValueError('Local volumes require a dedicated ext4/xfs data mount under the planned directory')
    space = os.statvfs(path)
    if space.f_bavail * space.f_frsize < 1.2 * byte_quantity(item['size']):
        raise ValueError('Insufficient volume free space including headroom')
    return {'name': item['name'], 'path': str(path), 'uid': info.st_uid, 'gid': info.st_gid,
            'device': info.st_dev, 'mount': mount, 'freeBytes': space.f_bavail * space.f_frsize}


def byte_quantity(value):
    match = re.fullmatch(r'(\d+)(Ki|Mi|Gi|Ti)', value)
    if not match:
        raise ValueError('Storage plan requires an integer binary quantity')
    return int(match[1]) * {'Ki': 2**10,'Mi': 2**20,'Gi': 2**30,'Ti': 2**40}[match[2]]


def resource_quantity(value):
    match = re.fullmatch(r'(\d+(?:\.\d+)?)(m|Ki|Mi|Gi|Ti|K|M|G|T)?', str(value))
    if not match:
        raise ValueError('Unsupported resource quantity')
    return Decimal(match[1]) * {'':1,'m':Decimal('.001'),'Ki':2**10,'Mi':2**20,'Gi':2**30,'Ti':2**40,'K':10**3,'M':10**6,'G':10**9,'T':10**12}[match[2] or '']


def preserve_database_resources(args, v):
    output = run([args.kubectl,'get','cluster.postgresql.cnpg.io',v['database']['name'],'-n','platform-services','--ignore-not-found=true','-o','json']).stdout
    if not output.strip():
        return v
    cluster = json.loads(output)
    args.database_version = cluster['metadata']['resourceVersion']
    resources = cluster['spec']['resources']
    if resources.get('requests') != resources.get('limits') or set(resources['requests']) != {'cpu','memory'}:
        raise ValueError('Existing database resources require a reviewed migration')
    policy = v['database']['autoscaler']
    for kind, low, high in [('cpu','minCPU','maxCPU'),('memory','minMemory','maxMemory')]:
        if not resource_quantity(policy[low]) <= resource_quantity(resources['requests'][kind]) <= resource_quantity(policy[high]):
            raise ValueError('Existing database resources are outside this scaler policy')
    v = copy.deepcopy(v)
    v['database']['cpu'] = resources['requests']['cpu']
    v['database']['memory'] = resources['requests']['memory']
    last = cluster['metadata'].get('annotations',{}).get('vcloud.io/resources-last-scaled')
    if last:
        v['database']['lastScaled'] = last
    return v


def stamp_database_version(args):
    if not getattr(args, 'database_version', None):
        return False
    for filename in ('database.yaml','foundation.yaml'):
        path = args.build / filename
        objects = list(flatten(yaml.safe_load_all(path.read_text())))
        for obj in objects:
            if obj['kind'] == 'Cluster':
                obj['metadata']['resourceVersion'] = args.database_version
        path.write_text(yaml.safe_dump_all(objects,sort_keys=False),encoding='utf-8',newline='\n')
    return True


def upgrade_cilium(args):
    return run([args.helm,'upgrade','--install','cilium',MODULE / 'vendor/cilium-1.20.2.tgz',
                '--namespace','kube-system','--values',args.build / 'cilium-values.yaml',
                '--post-renderer',sys.executable,'--post-renderer-args',ROOT / 'tools/helm_node_guard.py',
                '--post-renderer-args=--kubeconform','--post-renderer-args',args.kubeconform,
                '--wait','--timeout','10m'])


def host_check(args, v):
    if v['site']['referenceOnly']:
        raise ValueError('Configure a real site before inspecting its Ubuntu storage')
    if platform.system() != 'Linux':
        raise ValueError('host-check must run on the actual Ubuntu VM, not a Windows workstation')
    release = dict(line.split('=', 1) for line in Path('/etc/os-release').read_text().splitlines() if '=' in line)
    if release.get('ID', '').strip('"') != 'ubuntu' or release.get('VERSION_ID', '').strip('"') != '24.04':
        raise ValueError('SSoT requires Ubuntu 24.04')
    kernel = tuple(int(x) for x in platform.release().split('-')[0].split('.')[:2])
    if kernel < (6, 8) or not Path('/sys/fs/cgroup/cgroup.controllers').exists():
        raise ValueError('Kernel 6.8+ and cgroup v2 required')
    mount_type = run(['findmnt', '-n', '-T', '/sys/fs/bpf', '-o', 'FSTYPE']).stdout.strip()
    if mount_type != 'bpf':
        raise ValueError('BPF filesystem is not mounted at /sys/fs/bpf')
    probe = json.loads(run(['bpftool', '-j', 'feature', 'probe', 'kernel']).stdout)
    if not probe.get('syscall_config', {}).get('have_bpf_syscall') or not probe.get('program_types', {}).get('have_sched_cls_prog_type'):
        raise ValueError('eBPF syscall/TC capability not available; run the kernel probe with sudo')
    if run(['swapon', '--show', '--noheadings']).stdout.strip():
        raise ValueError('Swap must be disabled')
    for setting, threshold in [('net.ipv4.ip_forward',1), ('vm.max_map_count',262144), ('net.core.somaxconn',4096)]:
        if int(run(['sysctl','-n',setting]).stdout) < threshold:
            raise ValueError('Host sysctl below required value: ' + setting)
    config = tomllib.loads(run(['containerd', 'config', 'dump']).stdout)
    plugins = config.get('plugins', {})
    cri = plugins.get('io.containerd.grpc.v1.cri', {}).get('containerd') or plugins.get('io.containerd.cri.v1.runtime', {}).get('containerd', {})
    runtimes = cri.get('runtimes', {})
    if not runtimes.get('runc', {}).get('options', {}).get('SystemdCgroup'):
        raise ValueError('containerd runc must use systemd cgroups')
    nvidia = runtimes.get('nvidia', {}).get('options', {}).get('BinaryName', '')
    if not nvidia.endswith('nvidia-container-runtime'):
        raise ValueError('NVIDIA runtime is not configured in containerd')
    versions = run(['nvidia-smi','--query-gpu=driver_version','--format=csv,noheader']).stdout.splitlines()
    if not versions or any(int(x.split('.')[0]) < 550 for x in versions):
        raise ValueError('Accessible GPU and NVIDIA driver 550+ required')
    run(['nvidia-ctk','--version'])
    for device in v['site']['devices']:
        run(['ip','-j','link','show','dev',device])
    if platform.node() not in {x['node'] for x in v['storage']['volumes']}:
        raise ValueError('Host name is not in the exact site volume plan')
    huge = {size: int(Path(f'/sys/kernel/mm/hugepages/hugepages-{size}kB/nr_hugepages').read_text()) for size in (2048,1048576)}
    if huge[2048] < 128 or huge[1048576] < 1:
        raise ValueError('Approved 128 x 2 MiB and 1 x 1 GiB HugePage pools are not allocated')
    inspected = [inspect_volume(x) for x in v['storage']['volumes'] if x['node'] == platform.node()]
    # Check aggregate reservations when several planned PVs share a filesystem.
    totals = {}
    for item in v['storage']['volumes']:
        matching = next((x for x in inspected if x['name'] == item['name']), None)
        if matching:
            totals[matching['device']] = totals.get(matching['device'], 0) + byte_quantity(item['size'])
    for item in inspected:
        if item['freeBytes'] < 1.2 * totals[item['device']]:
            raise ValueError('Aggregate Local PV reservations exceed inspected filesystem free space')
    report = {'status': 'passed', 'time': time.time(), 'node': platform.node(), 'kernel': platform.release(),
              'siteSHA256': sha(args.site), 'gpuDrivers': versions, 'volumes': inspected, 'hugePages': huge,
              'note': 'Inspection only: no disk formatting, directory creation or host policy mutation'}
    args.build.mkdir(parents=True, exist_ok=True)
    (args.build / ('host-' + platform.node() + '.json')).write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8', newline='\n')
    print('Ubuntu/eBPF/GPU/containerd and exact local-storage inspection passed')


def live_preflight(args, v, inspect_hosts=True, dependencies=True):
    check_values(v, live=True, dependencies=dependencies)
    config = json.loads(run([args.kubectl,'config','view','--minify','-o','json']).stdout)
    cluster = config['clusters'][0]
    if cluster['name'] != v['clusterName'] or cluster['cluster']['server'].rstrip('/') != f'https://{v["site"]["apiHost"]}:6443' or cluster['cluster'].get('insecure-skip-tls-verify'):
        raise ValueError('Refusing mutation/diff against an unexpected or insecure kubeconfig target')
    version = json.loads(run([args.kubectl,'version','-o','json']).stdout)['serverVersion']['gitVersion']
    if version != 'v1.36.5':
        raise ValueError('Server differs from the pinned, node-approved Kubernetes profile')
    daemonsets = json.loads(run([args.kubectl,'get','daemonsets','-n','kube-system','-o','json']).stdout)['items']
    if any(item['metadata']['name'] == 'kube-proxy' for item in daemonsets):
        raise ValueError('Remove/disable kube-proxy through the reviewed bootstrap before full replacement')
    crds = json.loads(run([args.kubectl,'get','crds','-o','json']).stdout)['items']
    required = {'services.serving.knative.dev': 'v1','clusters.postgresql.cnpg.io':'v1',
                'apisixroutes.apisix.apache.org':'v2','apisixupstreams.apisix.apache.org':'v2','apisixtlses.apisix.apache.org':'v2',
                'applications.argoproj.io':'v1alpha1','appprojects.argoproj.io':'v1alpha1',
                'verticalpodautoscalers.autoscaling.k8s.io':'v1'}
    if not dependencies:
        required = {'ciliumnetworkpolicies.cilium.io':'v2','ciliumclusterwidenetworkpolicies.cilium.io':'v2'}
    for name, api in required.items():
        crd = next((x for x in crds if x['metadata']['name'] == name), None)
        if not crd or not any(x['name'] == api and x['served'] and not x.get('deprecated') for x in crd['spec']['versions']):
            raise ValueError('Missing/non-served/deprecated dependency CRD: ' + name)
    for namespace in ('platform-services','workload-apps','hpc-compute'):
        obj = json.loads(run([args.kubectl,'get','namespace',namespace,'-o','json']).stdout)
        if obj['metadata'].get('labels', {}).get('pod-security.kubernetes.io/enforce') != 'restricted':
            raise ValueError('Core namespace is not restricted: ' + namespace)
        baseline = json.loads(run([args.kubectl,'get','networkpolicy','default-deny-all','-n',namespace,'-o','json']).stdout)['spec']
        if baseline.get('podSelector') != {} or baseline.get('ingress',[]) or baseline.get('egress',[]) or set(baseline.get('policyTypes',[])) != {'Ingress','Egress'}:
            raise ValueError('Core namespace baseline is not deny-all: ' + namespace)
    if dependencies:
        features = json.loads(run([args.kubectl,'get','configmap','config-features','-n',v['knative']['namespace'],'-o','json']).stdout)['data']
        for key in ('kubernetes.podspec-persistent-volume-claim','kubernetes.podspec-securitycontext'):
            if features.get(key) not in ('enabled','allowed'):
                raise ValueError('Missing Knative feature: ' + key)
        network = json.loads(run([args.kubectl,'get','configmap','config-network','-n',v['knative']['namespace'],'-o','json']).stdout)['data']
        if network.get('cluster-local-domain-tls') != 'Enabled' or network.get('system-internal-tls') != 'Enabled':
            raise ValueError('Knative internal TLS acceptance profile is not configured')
        service = json.loads(run([args.kubectl,'get','service',v['knative']['kourierService'],'-n',v['knative']['namespace'],'-o','json']).stdout)['spec']
        if not any(p['port'] == 443 and p['targetPort'] in (8443,'https') for p in service['ports']):
            raise ValueError('Kourier must expose the reviewed internal HTTPS listener')
        run([args.kubectl,'get','secret',v['apisix']['upstreamTLSSecret'],'-n',v['knative']['namespace'],'-o','name'])
        verify_dependencies(args, v)
    if inspect_hosts:
        for node in {x['node'] for x in v['storage']['volumes']}:
            report = json.loads((args.build / ('host-' + node + '.json')).read_text())
            if report['status'] != 'passed' or report['siteSHA256'] != sha(args.site) or not 0 <= time.time() - report['time'] < 900:
                raise ValueError('Fresh matching host/storage report required for ' + node)
    if dependencies:
        nodes = json.loads(run([args.kubectl,'get','nodes','-o','json']).stdout)['items']
        pods = json.loads(run([args.kubectl,'get','pods','--all-namespaces','-o','json']).stdout)['items']
        compute_capacity(nodes, pods, v)
    print('Live target and required dependency contracts checked')


def compute_capacity(nodes, pods, v):
    for volume in v['storage']['volumes']:
        if not volume['name'].startswith('postgres-'):
            continue
        node = next((n for n in nodes if n['metadata']['labels'].get('kubernetes.io/hostname') == volume['node']), None)
        if not node or not any(c['type'] == 'Ready' and c['status'] == 'True' for c in node['status']['conditions']):
            raise ValueError('Database storage node is not Ready: ' + volume['node'])
        used = {'cpu':Decimal(0),'memory':Decimal(0)}
        for pod in pods:
            if pod['spec'].get('nodeName') != node['metadata']['name'] or pod.get('status',{}).get('phase') in ('Succeeded','Failed'):
                continue
            if pod['metadata']['namespace'] == 'platform-services' and pod['metadata'].get('labels',{}).get('cnpg.io/cluster') == v['database']['name']:
                continue # substitute the database's maximum resource reservation below
            # Conservatively sum init and main containers rather than understating sidecar/init overhead.
            for container in pod['spec'].get('containers',[]) + (pod['spec'].get('initContainers') or []):
                for key in used:
                    used[key] += resource_quantity(container.get('resources',{}).get('requests',{}).get(key,'0'))
            for key in used:
                used[key] += resource_quantity(pod['spec'].get('overhead',{}).get(key,'0'))
        for kind, maximum in [('cpu','maxCPU'),('memory','maxMemory')]:
            budget = resource_quantity(node['status']['allocatable'][kind]) * Decimal('.9')
            if used[kind] + resource_quantity(v['database']['autoscaler'][maximum]) > budget:
                raise ValueError('Insufficient node capacity at the database maximum with 10% headroom: ' + volume['node'] + '/' + kind)


def verify_dependencies(args, v):
    controllers = json.loads(run([args.kubectl,'get','deployments,statefulsets','-n','platform-services','-o','json']).stdout)['items']
    allowed_knative = {'controller','autoscaler','activator','webhook','net-kourier-controller','3scale-kourier-gateway'}
    for name, expected_images in v['dependencies']['images'].items():
        found = [o for o in controllers if o['spec']['template']['metadata'].get('labels',{}).get('app.kubernetes.io/name') == name]
        if name == 'knative-serving':
            found = [o for o in controllers if o['spec']['template']['metadata'].get('labels',{}).get('app') in allowed_knative]
            if {o['spec']['template']['metadata']['labels']['app'] for o in found} != allowed_knative:
                raise ValueError('Incomplete Knative/Kourier controller profile')
        if not found:
            raise ValueError('Missing dependency controller: ' + name)
        observed = set()
        for obj in found:
            if obj.get('status',{}).get('readyReplicas',0) < obj['spec'].get('replicas',1):
                raise ValueError('Dependency not ready: ' + obj['metadata']['name'])
            observed.update(c['image'] for c in obj['spec']['template']['spec']['containers'])
        if observed != set(expected_images):
            raise ValueError('Dependency image drift: ' + name)
        report = audit_objects(normalize_pods(found), load_policy())
        if report['violations']:
            raise ValueError('Dependency exceeds approved pod/node scope: ' + '; '.join(report['violations']))
    gateway = next(o for o in controllers if o['spec']['template']['metadata'].get('labels',{}).get('app.kubernetes.io/name') == 'apisix')
    volumes = gateway['spec']['template']['spec'].get('volumes',[])
    configs = [x['configMap']['name'] for x in volumes if 'configMap' in x]
    accepted = False
    for name in configs:
        data = json.loads(run([args.kubectl,'get','configmap',name,'-n','platform-services','-o','json']).stdout).get('data',{})
        if 'config.yaml' not in data:
            continue
        config = yaml.safe_load(data['config.yaml'])
        apisix_runtime_contract(config)
        accepted = True
    if not accepted:
        raise ValueError('APISIX needs the API-driven standalone / verified upstream CA configuration')
    environments = {e['name']: e for c in gateway['spec']['template']['spec']['containers'] for e in c.get('env',[])}
    if 'secretKeyRef' not in environments.get('APISIX_OIDC_CLIENT_SECRET',{}).get('valueFrom',{}):
        raise ValueError('APISIX OIDC credential must come from the reviewed secret integration')
    mount_paths = {m['mountPath'] for c in gateway['spec']['template']['spec']['containers'] for m in c.get('volumeMounts',[]) if m.get('readOnly')}
    if not {'/etc/vcloud-ca','/etc/vcloud-admin-tls','/etc/vcloud-gateway-tls'} <= mount_paths:
        raise ValueError('APISIX CA/private TLS volumes are not mounted read-only')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--site',type=Path,default=MODULE / 'site-values.yaml')
    parser.add_argument('--build',type=Path,default=ROOT / '.build/module-2')
    parser.add_argument('--helm',default='helm')
    parser.add_argument('--kubeconform',default='kubeconform')
    parser.add_argument('--kubectl',default='kubectl')
    parser.add_argument('command',choices=['render','validate','host-check','diff','apply','prepare'])
    args = parser.parse_args()
    try:
        v = check_values(values(args.site))
        if args.command == 'host-check':
            host_check(args, v)
        elif args.command == 'render':
            render(args, v)
        else:
            validate(args, v)
            if args.command in ('diff','apply','prepare'):
                live_preflight(args, v, dependencies=args.command != 'prepare')
                if args.command == 'prepare':
                    run([args.kubectl,'apply','--dry-run=server','--server-side','--field-manager=vcloud-bootstrap','-f',args.build / 'network.yaml'])
                    upgrade_cilium(args)
                    run([args.kubectl,'apply','--server-side','--field-manager=vcloud-bootstrap','-f',args.build / 'network.yaml'])
                    print('Prepared narrow network allowances; install/accept the pinned dependency profiles next')
                    return 0
                preserved = preserve_database_resources(args, v)
                if preserved != v:
                    v = preserved
                    validate(args, v) # schema/audit evidence must cover the final applied intent
                if stamp_database_version(args):
                    validate_rendered(args, v) # optimistic version checks reject concurrent scaler/operator changes
                if args.command == 'diff':
                    result = run([args.kubectl,'diff','-f',args.build / 'cilium.yaml','-f',args.build / 'foundation.yaml'], accepted=(0,1))
                    print(result.stdout)
                    return result.returncode
                # Exercise real admission/CEL/webhooks before the first mutation.
                run([args.kubectl,'apply','--dry-run=server','--server-side','--field-manager=vcloud-bootstrap','-f',args.build / 'foundation.yaml'])
                upgrade_cilium(args)
                for group in (*GROUPS, 'root'):
                    run([args.kubectl,'apply','--server-side','--field-manager=vcloud-bootstrap','-f',args.build / (group + '.yaml')])
                print('Applied verified Cilium profile and ordered foundation intent; inspect live readiness separately')
        return 0
    except (ValueError, RuntimeError, OSError, KeyError) as error:
        print('Module 2: ' + str(error), file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
