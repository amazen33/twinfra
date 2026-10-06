#!/usr/bin/env python3
"""Fail-closed offline HPC checks. Never installs controllers or enables offloading."""
import argparse
import copy
import gzip
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import tomllib
import yaml

ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / 'module-5b'
sys.path.insert(0, str(ROOT / 'tools'))
from build_module2_schemas import compact
from manifest_contract import audit_objects, podspec
from render_module5b import files, NS, QUEUE, TARGET


def bundle():
    lock = json.loads((MODULE / 'artifacts.lock.json').read_text())
    for path, digest in lock['filesSHA256'].items():
        target = (ROOT / path).resolve()
        if not target.is_relative_to(MODULE.resolve()) or hashlib.sha256(target.read_bytes()).hexdigest() != digest:
            raise ValueError('Locked HPC source/schema drift: ' + path)
    for source in lock['sources']:
        raw = (ROOT / source['file']).read_bytes()
        if source['file'].endswith('.gz'): raw = gzip.decompress(raw)
        if hashlib.sha256(raw).hexdigest() != source['sourceSHA256']:
            raise ValueError('HPC upstream source reconstruction drift')
    definition = json.loads(gzip.decompress((MODULE / 'vendor/kubernetes-apiextensions-openapi.json.gz').read_bytes()))
    schema = definition['components']['schemas']['io.k8s.apiextensions-apiserver.pkg.apis.apiextensions.v1.CustomResourceDefinition'].copy()
    schema.update(components=definition['components'], additionalProperties=False)
    schema['$schema'] = 'http://json-schema.org/draft-07/schema#'
    if (MODULE / 'schemas/customresourcedefinition_v1.json').read_bytes() != (json.dumps(schema, separators=(',', ':')) + '\n').encode():
        raise ValueError('Kubernetes CRD installer schema reproduction drift')
    reproduced = []
    for name in ('kueue', 'jobset'):
        for crd in yaml.safe_load_all(gzip.decompress((MODULE / f'vendor/{name}-crds.yaml.gz').read_bytes())):
            for version in crd['spec']['versions']:
                identity = (crd['spec']['names']['kind'], crd['spec']['group'] + '/' + version['name'])
                if not any((api['kind'], api['apiVersion']) == identity for api in lock['apis']): continue
                if not version['served'] or version.get('deprecated'): raise ValueError('Unserved/deprecated HPC API')
                schema = compact(version['schema']['openAPIV3Schema'])
                schema['$schema'] = 'http://json-schema.org/draft-07/schema#'
                schema['properties']['metadata'] = json.loads((ROOT / 'module-2/schemas/namespace_v1.json').read_text())['properties']['metadata']
                schema['properties']['apiVersion'] = {'type': 'string', 'enum': [identity[1]]}
                schema['properties']['kind'] = {'type': 'string', 'enum': [identity[0]]}
                schema['required'] = list(dict.fromkeys(schema.get('required', []) + ['apiVersion', 'kind', 'metadata']))
                path = MODULE / 'schemas' / crd['spec']['group'] / (identity[0].lower() + '_' + version['name'] + '.json')
                if path.read_bytes() != (json.dumps(schema, separators=(',', ':')) + '\n').encode():
                    raise ValueError('HPC CRD schema reproduction drift')
                reproduced.append(identity)
    if len(reproduced) != 9: raise ValueError('Incomplete HPC schema coverage')
    return lock


def reference_contract(profile):
    expected = {'cluster': 'vCloud-prod-01', 'namespace': NS, 'region': 'vcloud-hpc-1', 'queue': QUEUE,
        'offload_enabled': False, 'site_accepted': False, 'storage_and_fabric_accepted': False,
        'agent_batch_submission_enabled': False, 'selector': TARGET, 'max_burst_nodes': 4,
        'endpoint_url': 'http://spinifex-controller.hpc-compute.svc.cluster.local:3000',
        'external_endpoint_url': 'https://ec2.spinifex.pcloud.example.com', 'credentials_reference': 'spinifex-aws-credentials'}
    if any(profile.get(k) != v or type(profile.get(k)) != type(v) for k, v in expected.items()):
        raise ValueError('Disabled profile/platform identity drift')
    if profile['launch'] != {'image_id': None, 'subnet_id': None, 'security_group_ids': []}:
        raise ValueError('Reference launch must remain unaccepted')
    for key, count in [('spinifex.gpu.h100.80gb.8x', 8), ('spinifex.gpu.a100.80gb.4x', 4)]:
        p = profile['profiles'][key]
        if p['gpu_count'] != count or p['vram_gb_per_gpu'] != 80 or p['total_vram_gb'] != count * 80 or p['mapping_accepted'] is not False:
            raise ValueError('Disabled GPU profile drift')
    if profile['profiles']['spinifex.gpu.a100.80gb.4x']['instance_type'] is not None:
        raise ValueError('Unverified A100 fallback mapping')
    if profile['default_profile'] != 'spinifex.gpu.h100.80gb.8x' or profile['profiles'][profile['default_profile']]['instance_type'] != 'p5.48xlarge':
        raise ValueError('H100 reference mapping drift')
    if profile['worker_kubernetes_version'] != '1.36.5' or not re.fullmatch('[a-f0-9]{40}', profile['model_revision']):
        raise ValueError('Worker/model pin drift')


def pod_contract(items):
    """Audit real pod templates through the unchanged approved node policy."""
    wrappers = []
    for item in items:
        specs = []
        if item['kind'] == 'JobSet':
            specs = [job['template']['spec']['template']['spec'] for job in item['spec']['replicatedJobs']]
        elif item['kind'] == 'Task':
            step = copy.deepcopy(item['spec']['steps'][0])
            step['resources'] = step.pop('computeResources')
            specs = [{'containers': [step], 'volumes': item['spec']['volumes'], 'automountServiceAccountToken': False}]
        else:
            spec = podspec(item)
            if spec and spec.get('containers'): specs = [spec]
        for index, spec in enumerate(specs):
            wrappers.append({'apiVersion': 'v1', 'kind': 'Pod', 'metadata': {'name': item['metadata']['name'] + '-' + str(index),
                             'namespace': item['metadata'].get('namespace', NS)}, 'spec': spec})
            for c in spec.get('containers', []):
                sc = spec.get('securityContext', {}) | c.get('securityContext', {})
                if sc.get('allowPrivilegeEscalation') is not False or sc.get('readOnlyRootFilesystem') is not True or sc.get('capabilities', {}).get('drop') != ['ALL'] or sc.get('seccompProfile') != {'type': 'RuntimeDefault'}:
                    raise ValueError('HPC container hardening drift')
                if c.get('imagePullPolicy') != 'IfNotPresent': raise ValueError('Offline pull policy drift')
    result = audit_objects(wrappers, json.loads((ROOT / 'security/node-exceptions.json').read_text()))
    if result['violations']: raise ValueError('; '.join(result['violations']))
    return len(wrappers)


def object_contract(items):
    for item in items:
        if item['kind'] == 'Secret' and (item.get('data') or item.get('stringData')): raise ValueError('Credential material in reference')
        if item['kind'] in ('ClusterQueue', 'LocalQueue'):
            if item['metadata']['name'] != QUEUE or item['spec'].get('stopPolicy') != 'HoldAndDrain': raise ValueError('Queue pause drift')
            if item['kind'] == 'ClusterQueue':
                if item['spec']['namespaceSelector']['matchLabels'] != {**TARGET, 'kubernetes.io/metadata.name': NS}: raise ValueError('Queue scope drift')
                for group in item['spec']['resourceGroups']:
                    for flavor in group['flavors']:
                        for quota in flavor['resources']:
                            if any(quota.get(k) != 0 for k in ('nominalQuota', 'borrowingLimit', 'lendingLimit')): raise ValueError('Reference quota must be zero')
        if item['kind'] == 'Deployment' and item['metadata']['name'].startswith('vcloud-'):
            if item['spec']['replicas'] != 0: raise ValueError('Reference replicas must be zero')
            env = {v['name']: v.get('value') for v in item['spec']['template']['spec']['containers'][0]['env']}
            if env.get('SPINIFEX_OFFLOAD_ENABLED') != 'false': raise ValueError('Reference feature must remain disabled')
            if any(k.startswith('AWS_') for k in env): raise ValueError('AWS credentials/config must use explicit mounted SDK inputs')
            if item['metadata']['name'] == 'vcloud-deepseek-agent' and any('csi' in v or 'projected' in v for v in item['spec']['template']['spec']['volumes']):
                raise ValueError('Agent must have no provider/API credentials')
        if item['kind'] in ('Job', 'JobSet') and item['spec'].get('suspend') is not True: raise ValueError('Reference jobs must be suspended')
        if item['kind'] == 'PipelineRun' and item['spec'].get('status') != 'PipelineRunPending': raise ValueError('Reference PipelineRun must be pending')
        if item['kind'] == 'Application' and item['spec']['syncPolicy']['automated']['enabled'] is not False: raise ValueError('Reference GitOps automatic sync must stay off')
        if item['kind'] == 'MultiKueueConfig' and item['spec']['quotaManagement'] != 'Manual': raise ValueError('Automatic quota expansion prohibited')
        if item['kind'] == 'Task':
            env = {v['name']: v.get('value') for v in item['spec']['steps'][0]['env']}
            if env.get('SPINIFEX_OFFLOAD_ENABLED') != 'false': raise ValueError('Task feature must remain disabled')
        if item['kind'] == 'SecretProviderClass':
            spec = item['spec']; params = spec['parameters']
            if spec.get('secretObjects') or spec['provider'] != 'openbao' or params.get('baoSkipTLSVerify') or params['roleName'] != 'vcloud-spinifex' or params['audience'] != 'openbao':
                raise ValueError('OpenBao CSI identity/TLS/synchronization drift')
            if yaml.safe_load(params['objects']) != [{'objectName': 'aws-credentials.json', 'secretPath': 'kv/data/vcloud/spinifex', 'secretKey': 'credentials', 'filePermission': 288}]:
                raise ValueError('Provider credential mount scope drift')
        if item['kind'] == 'Role' and item['rules'] != [{'apiGroups': ['kueue.x-k8s.io'], 'resources': ['workloads'], 'verbs': ['get', 'list']}]:
            raise ValueError('Capacity bridge RBAC expansion')
        if item['apiVersion'] == 'serving.knative.dev/v1' and item['metadata']['labels'].get('networking.knative.dev/visibility') != 'cluster-local':
            raise ValueError('Inference must remain private')
    return pod_contract(items)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--helm', default='helm'); parser.add_argument('--kubeconform', default='kubeconform')
    args = parser.parse_args(); lock = bundle()
    subprocess.run([sys.executable, str(ROOT / 'tools/render_module5b.py'), '--check'], check=True)
    profile = json.loads((MODULE / 'reference-profile.json').read_text()); reference_contract(profile)
    paths = [MODULE / p for p in files() if p != 'observability/rules.yaml']
    items = [o for p in paths for o in yaml.safe_load_all(p.read_text()) if o]
    pod_count = object_contract(items)
    host = tomllib.loads((MODULE / 'host/spinifex-public-overlay.toml').read_text())
    if host['aws']['region'] != profile['region'] or host['nodes']['spinifex-node-01']['daemon']['gpu_passthrough'] is not False:
        raise ValueError('Native host reference gating drift')
    chart = MODULE / 'vendor/kueue-0.20.0.tgz'; values = MODULE / 'values/kueue.yaml'
    subprocess.run([args.helm, 'lint', str(chart), '-f', str(values)], check=True)
    rendered = subprocess.check_output([args.helm, 'template', 'kueue', str(chart), '-n', 'kueue-system',
        '-f', str(values), '--kube-version', '1.36.5'], text=True)
    build = ROOT / '.build/module-5b'; build.mkdir(parents=True, exist_ok=True)
    installer = build / 'kueue-rendered.yaml'; installer.write_text(rendered, encoding='utf-8', newline='\n')
    controller_pods = pod_contract([o for o in yaml.safe_load_all(rendered) if o])
    cmd = [args.kubeconform, '-strict', '-summary', '-kubernetes-version', '1.36.5']
    for directory in [MODULE / 'schemas'] + [ROOT / p / 'schemas' for p in ['module-4b', 'module-4a', 'module-3', 'module-2']]:
        for pattern in ['{{.Group}}/{{.ResourceKind}}_{{.ResourceAPIVersion}}.json', '{{.ResourceKind}}_{{.ResourceAPIVersion}}.json']:
            cmd += ['-schema-location', str(directory / pattern)]
    checked = subprocess.run(cmd + [str(p) for p in paths] + [str(installer)], text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    output = checked.stdout; print(output.strip())
    checked.check_returncode()
    report = dict(status='passed', module='5b', scope='Offline disabled reference; no live acceptance or GPU execution', versions=lock['versions'],
        schemaValidation=output.strip(), schemasReproduced=9, referenceResources=len(items), hardenedPodTemplates=pod_count + controller_pods,
        helm='lint and full template passed', featureEnabled=False, liveAcceptance='not executed')
    (build / 'validation.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8', newline='\n')
    print('Disabled HPC profile, zero quotas, pod security, CSI and ownership contracts passed')


if __name__ == '__main__': main()
