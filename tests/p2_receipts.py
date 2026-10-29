"""Freeze completed WO-31/P1/P3 receipts; current P2 changes have their own bounds."""
from pathlib import Path
import subprocess
import hashlib
import json

ROOT=Path(__file__).resolve().parents[1]
BASE='e92255278369a25f26bc694b38c33bfd2768c14d'
PATHS={'00-setup-ubuntu-host.sh','user-data.yaml','user-data-remote.yaml','user-data.yaml.gz',
       'deploy/common/bootstrap-images.lock.json','deploy/environments/dev/cairo-1/host.env',
       'deploy/environments/dev/cairo-2/seed/user-data'}


def original(path):
    return subprocess.check_output(['git','-C',str(ROOT),'show',BASE+':'+path])


def expected_source(raw):
    """Construct the complete approved source; no wildcard masks or ignored bytes."""
    text=raw.decode() if isinstance(raw,bytes) else raw
    text=text.replace('\r\n','\n')
    old='    local resolv_conf=/etc/resolv.conf endpoint=${CONTROL_PLANE_ENDPOINT:-"$NODE_IP:6443"} dev_proxy=\n'
    new=old.rstrip('\n').removesuffix('dev_proxy=')+"dev_proxy='' dev_images=''\n"+r'''    # WO-34: kubeadm's own patch overrides, confined to the dev profiles.
    if [[ -n ${KUBEADM_DNS_IMAGE_TAG:-}${KUBEADM_ETCD_IMAGE_TAG:-} ]]; then
        [[ $PLATFORM_PROFILE == dev-cairo-1 || $PLATFORM_PROFILE == dev-cairo-2 ]] || bad_config 'Image tag overrides are dev-only'
        [[ ${KUBEADM_DNS_IMAGE_TAG:-} =~ ^v1\.14\.[0-9]+$ && ${KUBEADM_ETCD_IMAGE_TAG:-} =~ ^3\.6\.[0-9]+-0$ ]] || bad_config 'Dev kubeadm tags must be exact compatible patches'
        printf -v dev_images 'dns:\n  imageTag: "%s"\netcd:\n  local:\n    imageTag: "%s"\n' "$KUBEADM_DNS_IMAGE_TAG" "$KUBEADM_ETCD_IMAGE_TAG"
    fi
'''
    if text.count(old)!=1:raise AssertionError('Original kubeadm declaration differs')
    text=text.replace(old,new,1)
    old='${dev_proxy}controlPlaneEndpoint: "$endpoint"'
    if text.count(old)!=1:raise AssertionError('Original kubeadm interpolation differs')
    text=text.replace(old,'${dev_proxy}${dev_images}controlPlaneEndpoint: "$endpoint"',1)
    start=text.index("        cat <<'VCLOUD_DEV_POLICY_JSON'\n")+len("        cat <<'VCLOUD_DEV_POLICY_JSON'\n")
    end=text.index('VCLOUD_DEV_POLICY_JSON\n',start)
    policy=json.loads(text[start:end])
    if policy['controlPlane']['Pod/kube-system/etcd']['image']!='registry.twinfra.example.com/registry.k8s.io/etcd:3.6.8-0':
        raise AssertionError('Original dev etcd approval differs')
    policy['controlPlane']['Pod/kube-system/etcd']['image']='registry.twinfra.example.com/registry.k8s.io/etcd:3.6.15-0'
    policy['profile']='WO-34 approved dev etcd patch and mirror; unchanged mounts and security'
    return text[:start]+json.dumps(policy,indent=2)+'\n'+text[end:]


def assert_current_source():
    expected=expected_source(original('00-setup-ubuntu-host.sh')).encode()
    if (ROOT/'00-setup-ubuntu-host.sh').read_bytes().replace(b'\r\n',b'\n')!=expected:
        raise AssertionError('Current source differs from the complete, exact owner-approved P2 edit')


def assert_current_seed(path):
    """Check every production seed byte against original plus exact source/hash edits."""
    old_source=original('00-setup-ubuntu-host.sh');new_source=expected_source(old_source).encode()
    old_hash=hashlib.sha256(old_source).hexdigest();new_hash=hashlib.sha256(new_source).hexdigest()
    source_path='user-data.yaml' if path.endswith('.gz') else path
    expected=original(source_path).decode()
    if source_path=='user-data.yaml':
        indent=lambda raw:'\n'.join('      '+line if line else '' for line in raw.decode().rstrip('\n').split('\n'))
        literal=indent(old_source)
        if expected.count(literal)!=1:raise AssertionError('Original embedded source differs')
        expected=expected.replace(literal,indent(new_source),1)
    if expected.count(old_hash)!=(2 if source_path.endswith('remote.yaml') else 1):raise AssertionError('Unexpected derived hash fields')
    expected=expected.replace(old_hash,new_hash).encode()
    actual=(ROOT/path).read_bytes()
    if path.endswith('.gz'):
        import gzip
        actual=gzip.decompress(actual)
    else:actual=actual.replace(b'\r\n',b'\n')
    if actual!=expected:raise AssertionError('Production seed differs beyond exact shared source/hash edits: '+path)


def receipt(path):
    if (ROOT/'security/security-wave-2026-10-images.json').is_file() and path in (
            'deploy/common/images.lock.json','lab/wsl/console/artifacts.lock.json',
            'lab/wsl/console/workloads.yaml','lab/wsl/console/gitops/workloads.yaml'):
        from r12_receipts import receipt as r12_receipt
        r12_receipt(path)
        return original(path)
    if path in ('vcloud-ssot.yaml','deploy/common/host-admin.py','tools/platform_host.py') and (ROOT/'deploy/common/host-network.py').is_file():
        from wo36_receipts import receipt as network_receipt
        return network_receipt(path)
    if path=='security/licence-policy.json':
        if (ROOT/'tools/ci/licence_ladder.py').is_file():
            from ladder_receipts import policy
            policy()  # Assert every field before projecting this historical receipt.
            before=original(path)
            return before
        # WO-07a owner review permits only removing the last pending entry.
        # Validate the entire current file before comparing historical receipts.
        before=original(path)
        old=b'  "pendingRemoval": [\n    "docker.io/grafana/grafana"\n  ],'
        if before.count(old)!=1:raise AssertionError('Original pending-removal list differs')
        expected=before.replace(old,b'  "pendingRemoval": [],',1)
        if (ROOT/path).read_bytes().replace(b'\r\n',b'\n')!=expected:
            raise AssertionError('Licence policy differs beyond the approved empty pending-removal list')
        return before
    if path in PATHS and (ROOT/'tools/ci/promote_p2.py').is_file():
        assert_current_source()
        if path.startswith('user-data'):assert_current_seed(path)
        return original(path)
    return (ROOT/path).read_bytes()
