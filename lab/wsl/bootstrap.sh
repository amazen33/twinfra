#!/usr/bin/env bash
# Explicitly authorized WSL development bootstrap; production bootstrap is unchanged.
# Root is required for the K3s/containerd host services, sysctls and BPF mounts.
# Workloads run non-root; Cilium keeps its exact previously approved node exception.
set -euo pipefail
umask 077
ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
BUILD="$ROOT/.build/wsl-lab"
CACHE="$ROOT/.tools/wsl-lab"
STATE=/var/lib/vcloud-wsl
ACTION=${1:---plan}
case "$ACTION" in --plan|--apply|--validate) ;; *) printf 'Use --plan, --apply or --validate\n' >&2; exit 2;; esac
mkdir -p "$BUILD"

# Collect public facts only. Ownership must match this exact local profile.
python3 - "$ROOT" "$BUILD/facts.json" <<'PY'
import hashlib,ipaddress,json,pathlib,socket,subprocess,sys
root=pathlib.Path(sys.argv[1]); osdata={}
for line in pathlib.Path('/etc/os-release').read_text().splitlines():
    if '=' in line:
        k,v=line.split('=',1); osdata[k]=v.strip('"')
def out(*args): return subprocess.check_output(args,text=True).strip()
marker=pathlib.Path('/var/lib/vcloud-wsl/owner.json')
profile_hash=hashlib.sha256((root/'lab/wsl/profile.json').read_bytes()).hexdigest()
owned=False
if marker.exists():
    owner=json.loads(marker.read_text())
    if owner.get('profileSHA256')!=profile_hash: raise SystemExit('Owned lab profile differs; no automatic migration')
    owned=True
mem=int(next(x.split()[1] for x in pathlib.Path('/proc/meminfo').read_text().splitlines() if x.startswith('MemTotal:')))
runtime=[]
for name in ('k3s','containerd','rke2-server','kubelet','docker'):
    if subprocess.run(['systemctl','is-active','--quiet',name]).returncode==0: runtime.append(name)
with socket.socket() as probe:
    try: probe.bind(('0.0.0.0',16443)); api_busy=False
    except OSError: api_busy=True
facts={'os':osdata['ID'],'version':osdata['VERSION_ID'],'kernel':out('uname','-r'),
 'memoryKiB':mem,'cpus':int(out('nproc')),'pid1':out('ps','-p','1','-o','comm='),
 'networking':out('wslinfo','--networking-mode'),'cgroup':out('stat','-fc','%T','/sys/fs/cgroup'),
 'btf':pathlib.Path('/sys/kernel/btf/vmlinux').exists(),
 'freeDiskKiB':int(out('df','-Pk','/var/lib').splitlines()[-1].split()[3]),
 'existingState':[p for p in ('/etc/rancher/k3s','/var/lib/rancher/k3s','/etc/kubernetes/admin.conf','/etc/containerd/config.toml') if pathlib.Path(p).exists()],
 'activeRuntimes':runtime,'owned':owned,'apiPortBusy':api_busy,
 'routes':json.loads(out('ip','-4','-j','route','show'))}
pathlib.Path(sys.argv[2]).write_text(json.dumps(facts,indent=2)+'\n')
if facts['os']!='ubuntu' or 'microsoft' not in facts['kernel'].lower() or facts['pid1']!='systemd': raise SystemExit('WSL2/systemd Ubuntu required')
if not owned and (facts['existingState'] or runtime or facts['apiPortBusy']): raise SystemExit('Existing unmanaged runtime/cluster; stopping')
if runtime and any(x not in ('k3s','containerd') for x in runtime): raise SystemExit('Unrelated runtime service active')
if mem<16*1024**2 or facts['cpus']<4: raise SystemExit('Insufficient lab resources')
if not owned:
    for route in facts['routes']:
        dst=route.get('dst','default')
        if dst!='default' and any(ipaddress.ip_network(dst).overlaps(ipaddress.ip_network(c)) for c in ('10.42.0.0/16','10.43.0.0/16')):
            raise SystemExit('Lab CIDR overlaps an existing route')
print(json.dumps({k:facts[k] for k in ('version','memoryKiB','cpus','networking','owned')},indent=2))
PY
if [[ $ACTION == --plan ]]; then
    printf '%s\n' 'Plan: K3s 1.36.5 + external systemd containerd + pinned Cilium 1.20.2.' \
        'API INPUT restricted to loopback/PodCIDR; no Flannel, kube-proxy, ingress, hostPath storage, GPU or HPC workloads.' \
        'Connected staging verifies immutable artifacts and populates canonical registry image names.' \
        'Production SSoT, GRUB, HugePages, Windows settings and NVIDIA drivers remain unchanged.'
    exit 0
fi
[[ $EUID == 0 ]] || { printf 'Run --apply/--validate with sudo\n' >&2; exit 2; }

if [[ $ACTION == --apply ]]; then
    # Checkpoint ownership before package installation so a partial package/runtime
    # start can be resumed without adopting an unrelated service on the next run.
    install -d -m 0700 "$STATE"
    python3 - "$ROOT" "$STATE/owner.json" <<'PY'
import hashlib,json,pathlib,sys
root=pathlib.Path(sys.argv[1]); target=pathlib.Path(sys.argv[2])
target.write_text(json.dumps({'profileSHA256':hashlib.sha256((root/'lab/wsl/profile.json').read_bytes()).hexdigest(),
 'scope':'user-authorized WSL local validation','rootServices':['containerd','k3s']},indent=2)+'\n')
target.chmod(0o600)
PY
    # Signed Ubuntu packages provide the host runtime and node diagnostic tools.
    # jq is mandatory for apply-and-verify.sh and other JSON-based cluster checks.
    apt-get update -qq
    DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
        containerd runc containernetworking-plugins iptables nftables iproute2 python3-yaml ca-certificates curl jq
    python3 "$ROOT/tools/wsl_lab.py" check-facts --facts "$BUILD/facts.json"
    python3 "$ROOT/tools/stage_wsl_lab.py" --cache "$CACHE"
fi
python3 "$ROOT/tools/wsl_lab.py" check-facts --facts "$BUILD/facts.json"
NODE_IP=$(ip -4 route get 1.1.1.1 | awk '{for(i=1;i<=NF;i++) if($i=="src") {print $(i+1);exit}}')
DEVICE=$(ip -4 route get 1.1.1.1 | awk '{for(i=1;i<=NF;i++) if($i=="dev") {print $(i+1);exit}}')
python3 "$ROOT/tools/wsl_lab.py" render --build "$BUILD" --node-ip "$NODE_IP" --device "$DEVICE"
python3 "$ROOT/tools/wsl_lab.py" validate --build "$BUILD" --helm "$CACHE/helm" --kubeconform "$CACHE/kubeconform"

if [[ $ACTION == --apply ]]; then
    # Ownership is checkpointed before service configuration to permit safe resume.
    install -d -m 0700 "$STATE" /etc/vcloud-wsl /etc/rancher/k3s
    python3 - "$ROOT" "$STATE/owner.json" <<'PY'
import hashlib,json,pathlib,sys
root=pathlib.Path(sys.argv[1]); target=pathlib.Path(sys.argv[2])
target.write_text(json.dumps({'profileSHA256':hashlib.sha256((root/'lab/wsl/profile.json').read_bytes()).hexdigest(),
 'scope':'user-authorized WSL local validation','rootServices':['containerd','k3s']},indent=2)+'\n')
target.chmod(0o600)
PY
    install -d -m 0755 /opt/cni/bin /etc/cni/net.d /etc/containerd/certs.d/_default
    if [[ -d /usr/lib/cni ]]; then cp /usr/lib/cni/* /opt/cni/bin/; fi
    containerd config default > "$BUILD/containerd-default.toml"
    python3 - "$ROOT" "$BUILD/containerd-default.toml" /etc/containerd/config.toml <<'PY'
import pathlib,sys
sys.path.insert(0,str(pathlib.Path(sys.argv[1])/'tools'))
from wsl_lab import containerd_config,profile
text=containerd_config(pathlib.Path(sys.argv[2]).read_text(),profile())
pathlib.Path(sys.argv[3]).write_text(text)
PY
    # Explicit per-upstream API roots preserve the canonical repository prefix.
    # An optional operator-supplied registry IP is accepted only after verified
    # HTTPS succeeds for the registry hostname; never guess a local address.
    registry_args=()
    [[ -z ${VCLOUD_REGISTRY_ADDRESS:-} ]] || registry_args+=(--registry-address "$VCLOUD_REGISTRY_ADDRESS")
    [[ -z ${VCLOUD_REGISTRY_CA_FILE:-} ]] || registry_args+=(--ca-file "$VCLOUD_REGISTRY_CA_FILE")
    python3 "$ROOT/tools/node_registry.py" configure --apply "${registry_args[@]}" > "$BUILD/registry-config.json"
    systemctl enable containerd
    systemctl restart containerd
    ctr --namespace k8s.io images import --platform linux/amd64 "$CACHE/k3s-images.tar.gz" > "$BUILD/image-import.log"
    # The verified airgap bundle contains exactly these immutable versioned names.
    while read -r source; do
        [[ -n $source ]] || continue
        ctr --namespace k8s.io images tag --force "$source" "registry.vcloud.example.com/$source" > /dev/null
    done < "$CACHE/k3s-images.txt"
    python3 "$ROOT/tools/wsl_lab_dns_image.py" --cache "$CACHE"
    # Connected staging uses upstream digest references; Pods use the canonical cache.
    while read -r target; do
        source=${target#registry.vcloud.example.com/}
        ctr --namespace k8s.io images pull --platform linux/amd64 "$source" > "$BUILD/image-pull.log" 2>&1
        ctr --namespace k8s.io images tag --force "$source" "$target" > /dev/null
        # CRI normalizes tag@digest to repository@digest. Seed both normalized
        # aliases so IfNotPresent finds the cache without resolving the mirror.
        tagged=${target%@*}
        digested=${tagged%:*}@${target#*@}
        ctr --namespace k8s.io images tag --force "$source" "$tagged" > /dev/null
        ctr --namespace k8s.io images tag --force "$source" "$digested" > /dev/null
    done < "$BUILD/cilium-images.txt"
    install -m 0755 "$CACHE/k3s" /usr/local/bin/k3s
    if ! command -v kubectl > /dev/null 2>&1; then
        cat > /usr/local/bin/kubectl <<'CLI'
#!/usr/bin/env bash
export KUBECONFIG=${KUBECONFIG:-/etc/vcloud-wsl/kubeconfig.yaml}
exec /usr/local/bin/k3s kubectl --context vcloud-wsl-local "$@"
CLI
        chmod 0755 /usr/local/bin/kubectl
    fi
    install -d -m 0755 /usr/local/libexec
    install -m 0750 "$ROOT/lab/wsl/api-firewall.sh" /usr/local/libexec/vcloud-wsl-api-firewall
    # WSL's output mark=1 rule otherwise destroys Cilium DNS proxy marks.
    # This owned-profile helper preserves only Cilium's proxy mark classes.
    install -m 0750 "$ROOT/tools/wsl_proxy_marks.py" /usr/local/libexec/vcloud-wsl-proxy-marks
    install -m 0644 "$ROOT/lab/wsl/vcloud-wsl-proxy-marks.service" /etc/systemd/system/
    install -m 0644 "$ROOT/lab/wsl/vcloud-wsl-proxy-marks.timer" /etc/systemd/system/
    install -m 0600 "$BUILD/k3s-config.yaml" /etc/rancher/k3s/config.yaml
    python3 - "$ROOT" <<'PY'
from pathlib import Path
import sys,yaml
sys.path.insert(0,str(Path(sys.argv[1])/'tools'))
from wsl_lab import repair_local_client_endpoint
for path in Path('/var/lib/rancher/k3s/server/cred').glob('*.kubeconfig'):
    if path.is_symlink(): raise SystemExit('Unexpected symlink in owned K3s credential directory')
    data=yaml.safe_load(path.read_text())
    fixed=repair_local_client_endpoint(data)
    if fixed!=data:
        path.write_text(yaml.safe_dump(fixed));path.chmod(0o600)
        print('Updated owned internal API endpoint: '+path.name)
PY
    cat > /etc/systemd/system/k3s.service <<'UNIT'
[Unit]
Description=vCloud WSL local K3s validation cluster
After=network-online.target containerd.service
Wants=network-online.target
Requires=containerd.service
[Service]
Type=notify
User=root
ExecStartPre=/usr/local/libexec/vcloud-wsl-api-firewall
ExecStart=/usr/local/bin/k3s server --config /etc/rancher/k3s/config.yaml
Restart=on-failure
RestartSec=5
KillMode=process
Delegate=yes
LimitNOFILE=1048576
TasksMax=infinity
[Install]
WantedBy=multi-user.target
UNIT
    # No Linux NVIDIA driver, Windows setting, swap shutdown or GRUB operation.
    modprobe br_netfilter || true
    systemctl daemon-reload
    systemctl enable k3s
    systemctl restart k3s
    systemctl enable --now vcloud-wsl-proxy-marks.timer
    systemctl start vcloud-wsl-proxy-marks.service
fi
for _attempt in $(seq 1 90); do
    if /usr/local/bin/k3s kubectl --server "https://$NODE_IP:16443" --kubeconfig /etc/rancher/k3s/k3s.yaml get --raw=/readyz > /dev/null 2>&1; then break; fi
    sleep 2
done
/usr/local/bin/k3s kubectl --server "https://$NODE_IP:16443" --kubeconfig /etc/rancher/k3s/k3s.yaml get --raw=/readyz
# Keep admin credentials on the Linux filesystem with 0600 permissions, outside Git.
python3 - /etc/rancher/k3s/k3s.yaml /etc/vcloud-wsl/kubeconfig.yaml "$NODE_IP" <<'PY'
import pathlib,sys,yaml
d=yaml.safe_load(pathlib.Path(sys.argv[1]).read_text())
name='vcloud-wsl-local'
for c in d['clusters']: c['name']=name;c['cluster']['server']='https://'+sys.argv[3]+':16443'
for c in d['contexts']: c['name']=name;c['context']['cluster']=name
d['current-context']=name
target=pathlib.Path(sys.argv[2]);target.write_text(yaml.safe_dump(d));target.chmod(0o600)
PY
export KUBECONFIG=/etc/vcloud-wsl/kubeconfig.yaml
kubectl() { /usr/local/bin/k3s kubectl --context vcloud-wsl-local "$@"; }
/usr/local/libexec/vcloud-wsl-api-firewall --check
if [[ $ACTION == --apply ]]; then
    # Namespace dry-run does not create the namespace for subsequent resources.
    python3 - "$ROOT" "$BUILD" <<'PY'
from pathlib import Path
import sys,yaml
sys.path.insert(0,str(Path(sys.argv[1])/'tools'))
from wsl_lab import namespace_phase
build=Path(sys.argv[2])
for source,target,helm_owned in [('cilium-rendered.yaml','cilium-namespaces.yaml',True),('foundation-dns.yaml','core-namespaces.yaml',False)]:
    objects=namespace_phase(list(yaml.safe_load_all((build/source).read_text())),helm_owned)
    (build/target).write_text(yaml.safe_dump_all(objects))
PY
    kubectl apply --server-side --dry-run=server -f "$BUILD/cilium-namespaces.yaml" > /dev/null
    kubectl apply --server-side -f "$BUILD/cilium-namespaces.yaml"
    # Rendered YAML was audited against the frozen Cilium exception before mutation.
    # Helm owns these fields. Force conflicts only in dry-run so validation can
    # inspect a fresh render without transferring ownership or writing Secrets.
    kubectl apply --server-side --dry-run=server --force-conflicts -f "$BUILD/cilium-rendered.yaml" > /dev/null
    cat > "$BUILD/helm-post-renderer.sh" <<POST
#!/usr/bin/env bash
exec python3 "$ROOT/tools/helm_node_guard.py" --kubeconform "$CACHE/kubeconform"
POST
    chmod 0755 "$BUILD/helm-post-renderer.sh"
    "$CACHE/helm" upgrade --install cilium "$ROOT/module-2/vendor/cilium-1.20.2.tgz" \
        --namespace kube-system --kube-context vcloud-wsl-local -f "$BUILD/cilium-values.yaml" \
        --post-renderer "$BUILD/helm-post-renderer.sh" --wait --timeout 10m
    kubectl apply --server-side --dry-run=server -f "$BUILD/core-namespaces.yaml" > /dev/null
    kubectl apply --server-side -f "$BUILD/core-namespaces.yaml"
    kubectl apply --server-side --dry-run=server -f "$BUILD/foundation-dns.yaml" > /dev/null
    kubectl apply --server-side -f "$BUILD/foundation-dns.yaml"
fi
kubectl rollout status daemonset/cilium -n kube-system --timeout=300s
kubectl rollout status deployment/cilium-operator -n kube-system --timeout=300s
kubectl rollout status deployment/vcloud-lab-dns -n kube-system --timeout=180s
kubectl wait --for=condition=Ready node/vcloud-wsl-local --timeout=180s
if [[ $ACTION == --apply ]]; then
    kubectl apply --server-side --dry-run=server -f "$BUILD/smoke.yaml" > /dev/null
    kubectl apply --server-side -f "$BUILD/smoke.yaml"
fi
for item in platform-services/server workload-apps/allowed hpc-compute/denied; do
    kubectl wait -n "${item%/*}" --for=condition=Ready "pod/vcloud-lab-${item#*/}" --timeout=120s
done
kubectl exec -n workload-apps vcloud-lab-allowed -- nslookup kubernetes.default.svc.cluster.local
kubectl exec -n hpc-compute vcloud-lab-denied -- nslookup vcloud-lab-server.platform-services.svc.cluster.local
kubectl exec -n workload-apps vcloud-lab-allowed -- wget -T 5 -qO- http://vcloud-lab-server.platform-services.svc.cluster.local:8080 | grep -qx vcloud-wsl-ok
if kubectl exec -n hpc-compute vcloud-lab-denied -- wget -T 3 -qO- http://vcloud-lab-server.platform-services.svc.cluster.local:8080 > "$BUILD/denied.log" 2>&1; then
    printf 'Denied client unexpectedly reached server\n' >&2; exit 1
fi
grep -qi 'timed out' "$BUILD/denied.log" || { printf 'Denied probe failed for an unexpected reason\n' >&2; exit 1; }
kubectl exec -n kube-system daemonset/cilium -- cilium-dbg status --verbose > "$BUILD/cilium-status.txt"
grep -q 'KubeProxyReplacement:.*True' "$BUILD/cilium-status.txt"
kubectl get nodes -o json > "$BUILD/nodes.json"
kubectl get pods -A -o json > "$BUILD/pods.json"
kubectl get daemonsets,deployments,replicasets -A -o json > "$BUILD/controllers.json"
python3 "$ROOT/tools/wsl_lab_acceptance.py" --build "$BUILD"
printf '%s\n' 'Local bootstrap and DNS/allow/deny smoke tests passed.' \
    'Private kubeconfig: /etc/vcloud-wsl/kubeconfig.yaml (root, mode 0600).' \
    'Use: sudo /usr/local/bin/k3s kubectl --kubeconfig /etc/vcloud-wsl/kubeconfig.yaml get nodes'
