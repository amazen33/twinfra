#!/usr/bin/env python3
"""Generate contract-derived identity and foundation objects; --check detects drift."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shlex
import yaml

ROOT = Path(__file__).resolve().parents[1]


def replace_block(text, name, body):
    pattern = rf"(?m)^(?P<indent> *)# BEGIN GENERATED {name}\n.*?^ *(?:# END GENERATED {name})"
    def replacement(match):
        indent = match['indent']
        return '\n'.join(indent + line if line else '' for line in
                         [f'# BEGIN GENERATED {name}', *body.splitlines(), f'# END GENERATED {name}'])
    result, count = re.subn(pattern, replacement, text, flags=re.DOTALL)
    if count != 1:
        raise ValueError(f'Missing/duplicate generated block: {name}')
    return result


def outputs():
    s = yaml.safe_load((ROOT / 'vcloud-ssot.yaml').read_text())
    c = s['cluster']
    # Keep shell/YAML substitutions safe; this generator accepts identifiers only.
    identity = dict(SSOT_VERSION=s['version'], CLUSTER_NAME=c['name'],
                    CLUSTER_DNS_NAME=c['dnsName'], BASE_DOMAIN=c['baseDomain'],
                    GITOPS_REPOSITORY=c['gitOpsRepository'], IMAGE_REGISTRY=s['registry'])
    assert all(re.fullmatch(r'[A-Za-z0-9./-]+', str(v)) for v in identity.values())
    assert c['dnsName'] == c['name'].lower()
    resources = []
    for ns in c['namespaces']:
        assert re.fullmatch(r'[a-z][a-z0-9-]+', ns)
        resources += [
            dict(apiVersion='v1', kind='Namespace', metadata=dict(name=ns, labels={
                'vcloud.io/managed': 'true',
                'pod-security.kubernetes.io/enforce': 'restricted',
                'pod-security.kubernetes.io/enforce-version': 'v1.30',
                'pod-security.kubernetes.io/audit': 'restricted',
                'pod-security.kubernetes.io/audit-version': 'v1.30',
                'pod-security.kubernetes.io/warn': 'restricted',
                'pod-security.kubernetes.io/warn-version': 'v1.30'}, annotations={
                'vcloud.io/cluster': c['name'], 'vcloud.io/base-domain': c['baseDomain'],
                'vcloud.io/gitops-repository': c['gitOpsRepository']})),
            dict(apiVersion='networking.k8s.io/v1', kind='NetworkPolicy',
                 metadata=dict(name='default-deny-all', namespace=ns),
                 spec=dict(podSelector={}, policyTypes=['Ingress', 'Egress'], ingress=[], egress=[]))]
    foundation = '# Generated from vcloud-ssot.yaml by tools/render_ssot.py.\n' + yaml.safe_dump_all(resources, sort_keys=False)
    script = (ROOT / '00-setup-ubuntu-host.sh').read_text()
    defaults = '\n'.join(f': "${{{k}:={v}}}"' for k, v in identity.items())
    script = replace_block(script, 'SSOT DEFAULTS', defaults)
    expected = identity | dict(REGISTRY_MIRROR='https://' + s['registry'], MIRROR_REQUIRED='true')
    conditions = ' &&\n       '.join(f'${k} == {shlex.quote(str(v))}' for k, v in expected.items())
    profiles = [f'production) [[ {conditions} && $IMAGE_STAGING == false ]] ;;']
    dev = s.get('environments', {}).get('dev')
    if dev:
        expected_dev = expected | dict(CLUSTER_NAME=dev['context'], CLUSTER_DNS_NAME=dev['context'],
            BASE_DOMAIN=dev['baseDomain'], IMAGE_REGISTRY=dev['registry'], REGISTRY_MIRROR='https://'+dev['registry'])
        for row in s['addressPlan']:
            if row['environment'] != 'dev': continue
            expected_row = expected_dev | dict(CLUSTER_NAME='twinfra-dev-'+row['region'], CLUSTER_DNS_NAME='twinfra-dev-'+row['region'])
            check = ' && '.join(f'${k} == {shlex.quote(str(v))}' for k,v in expected_row.items())
            profiles.append(f'dev-{row["region"]}) [[ {check} && ( $IMAGE_STAGING == false || $IMAGE_STAGING == true ) ]] ;;')
    script = replace_block(script, 'SSOT VALIDATION', 'validate_ssot_identity() {\n    case $PLATFORM_PROFILE in\n    '+
        '\n    '.join(profiles)+"\n    *) return 2 ;;\n    esac || bad_config 'Identity/registry drift from vcloud-ssot.yaml; change the contract and regenerate first'\n}")
    foundation_body = "render_foundation() {\n    if [[ $PLATFORM_PROFILE == dev-* ]]; then\n        cat <<'EOF'\n"
    dev_resources = yaml.safe_load_all(foundation)
    dev_objects = []
    for obj in dev_resources:
        if not obj: continue
        ns_map=dict(zip(c['namespaces'],dev['namespaces'].values())) if dev else {}
        if obj['kind']=='Namespace':obj['metadata']['name']=ns_map.get(obj['metadata']['name'],obj['metadata']['name'])
        elif 'namespace' in obj['metadata']:obj['metadata']['namespace']=ns_map.get(obj['metadata']['namespace'],obj['metadata']['namespace'])
        obj['metadata']['labels'] = {k.replace('vcloud.io/', 'twinfra.io/'):v for k,v in obj['metadata'].get('labels',{}).items()}
        obj['metadata'].pop('annotations', None)
        if obj['kind'] == 'NetworkPolicy': obj['metadata']['name'] = 'twinfra-default-deny'
        dev_objects.append(obj)
    foundation_body += yaml.safe_dump_all(dev_objects,sort_keys=False)+"EOF\n    else\n    cat <<'EOF'\n"+foundation+'EOF\n    fi\n}'
    script = replace_block(script, 'FOUNDATION', foundation_body)
    decision = s['security']['nodeHostMountException']
    policy_text = (ROOT / decision['policyFile']).read_text()
    if hashlib.sha256(policy_text.encode()).hexdigest() != decision['policySHA256']:
        raise ValueError('Node exception policy differs from the approved SSoT hash')
    policy = json.loads(policy_text)
    checker = (ROOT / 'tools/manifest_contract.py').read_text()
    profile_policy=json.loads(policy_text)
    if dev:
        dev_policy=json.loads(json.dumps(profile_policy).replace(s['registry'],dev['registry']))
        dev_policy['sourcePolicySHA256']=decision['policySHA256']
        dev_policy['profile']='WO-21 dev mirror relocation only; same images, mounts and security'
        dev_text=json.dumps(dev_policy,indent=2)+'\n'
    else:dev_text=policy_text
    script = replace_block(script, 'EXCEPTION POLICY', "render_exception_policy() {\n    if [[ $PLATFORM_PROFILE == dev-* ]]; then\n        cat <<'VCLOUD_DEV_POLICY_JSON'\n" + dev_text + "VCLOUD_DEV_POLICY_JSON\n    else\n    cat <<'VCLOUD_POLICY_JSON'\n" + policy_text + 'VCLOUD_POLICY_JSON\n    fi\n}')
    script = replace_block(script, 'POLICY CHECKER', "render_policy_checker() {\n    cat <<'VCLOUD_POLICY_PYTHON'\n" + checker + 'VCLOUD_POLICY_PYTHON\n}')
    versions = policy['versions']
    if decision['status'] == 'approved' and policy['status'] == 'approved':
        gate = '''check_policy_gate() {
    [[ $BOOTSTRAP_K8S == true ]] || return 0
    # Approved by the user on 2026-10-05; no environment flag broadens the scope.
    [[ $KUBERNETES_VERSION == %s && $CILIUM_VERSION == %s && $NVIDIA_DEVICE_PLUGIN_VERSION == %s ]] || {
        log 'Node exception is pinned to the approved Kubernetes/Cilium/NVIDIA versions; unreviewed drift rejected.' >&2
        return 42
    }
}''' % (versions['kubernetes'], versions['cilium'], versions['nvidiaDevicePlugin'])
    else:
        gate = "check_policy_gate() { [[ $BOOTSTRAP_K8S == false ]] || return 42; }"
    script = replace_block(script, 'POLICY GATE', gate)
    env = (ROOT / 'host.env.example').read_text()
    env = replace_block(env, 'SSOT IDENTITY', '\n'.join(f'{k}={v}' for k, v in identity.items()))
    return {ROOT / '00-setup-ubuntu-host.sh': script,
            ROOT / 'host.env.example': env,
            ROOT / 'manifests/foundation.yaml': foundation}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    stale = []
    for path, content in outputs().items():
        if args.check:
            if not path.exists() or path.read_text() != content:
                stale.append(str(path))
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding='utf-8', newline='\n')
    if stale:
        print('SSoT outputs are stale: ' + ', '.join(stale))
        return 1
    print('SSoT outputs checked' if args.check else 'SSoT outputs generated')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
