#!/usr/bin/env bash
# Module -1: upstream Kubernetes / Cilium on a fresh Ubuntu VM or bare-metal host.
# Usage: bash 00-setup-ubuntu-host.sh --plan | sudo bash ... --apply | sudo bash ... --validate
# This script does not run when sourced: its render/validation helpers can be tested offline.
# Configuration: shell environment, then root-owned /etc/vcloud-host.env if present.
# Exit codes: 0 = requested gates passed; 1 = failed; 2 = bad configuration;
#             20 = reboot required (bootstrap has deliberately been deferred).
#             42 = SSoT hostPath prohibition blocks Kubernetes bootstrap.
# Root is required for APT, kernel/mount/sysctl/driver configuration and kubeadm PKI.
# Ordinary validation pods run as UID 10001 without capabilities or host mounts.
# No automatic reboot, kubeadm reset, firewall disable, disk formatting, or VFIO rebinding.

load_config() {
    local config_file="${VCLOUD_CONFIG_FILE:-/etc/vcloud-host.env}"
    # An env file is executable shell configuration. Never source a writable user file as root.
    if [[ -f "$config_file" ]]; then
        [[ $(stat -c '%u' "$config_file") == 0 ]] || die "Config must be root-owned: $config_file"
        [[ $(stat -c '%a' "$config_file") =~ ^(600|644)$ ]] || die "Config must have mode 0600 or 0644: $config_file"
        # shellcheck disable=SC1090
        source "$config_file"
    fi
    : "${KUBERNETES_VERSION:=v1.36.5}" "${CILIUM_VERSION:=1.20.2}"
    : "${HELM_VERSION:=v3.22.0}" "${CILIUM_CLI_VERSION:=v0.20.1}"
    : "${KUBECONFORM_VERSION:=v0.8.0}" "${TKN_VERSION:=v0.46.1}"
    : "${ARGOCD_VERSION:=v3.5.3}" "${YQ_VERSION:=v4.54.1}" "${CRICTL_VERSION:=v1.36.0}"
    : "${NVIDIA_TOOLKIT_VERSION:=1.20.1-1}" "${NVIDIA_DEVICE_PLUGIN_VERSION:=0.20.1}"
    : "${ENABLE_GPU:=auto}" "${NVIDIA_DRIVER_PACKAGE:=auto}" "${ENABLE_KVM:=false}"
    # ADR-0044 owner clarification: opt in only to the proprietary CUDA smoke image.
    : "${GPU_SMOKE_TEST:=false}"
    : "${INSTALL_HPC:=true}" "${BOOTSTRAP_K8S:=true}" "${RUN_SMOKE_TESTS:=true}"
    : "${HUGEPAGES_2M:=128}" "${HUGEPAGES_1G:=1}" "${MIN_NORMAL_RAM_MIB:=4096}"
    # BEGIN GENERATED SSOT DEFAULTS
    : "${SSOT_VERSION:=2.2}"
    : "${CLUSTER_NAME:=vCloud-prod-01}"
    : "${CLUSTER_DNS_NAME:=vcloud-prod-01}"
    : "${BASE_DOMAIN:=vcloud.example.com}"
    : "${GITOPS_REPOSITORY:=amazen33/twinfra}"
    : "${IMAGE_REGISTRY:=registry.vcloud.example.com}"
    # END GENERATED SSOT DEFAULTS
    : "${REGISTRY_MIRROR:=https://$IMAGE_REGISTRY}" "${REGISTRY_CA_FILE:=}"
    : "${MIRROR_REQUIRED:=true}" "${REGISTRY_PROBE_IMAGE:=$IMAGE_REGISTRY/docker.io/library/busybox:1.37.0}"
    # WO-29: explicit owner/NoCloud image staging is a dev-only bootstrap step.
    : "${IMAGE_STAGING:=false}"
    : "${POD_CIDR:=10.42.0.0/16}" "${SERVICE_CIDR:=10.43.0.0/16}" "${NODE_IP:=}"
    : "${PLATFORM_PROFILE:=production}" "${CONTROL_PLANE_ENDPOINT:=}"
    : "${NODE_NAME:=}" "${PAUSE_IMAGE:=$IMAGE_REGISTRY/registry.k8s.io/pause:3.10.1}"
    : "${HUGEPAGE_SMOKE_IMAGE:=$IMAGE_REGISTRY/docker.io/library/python:3.12.12-slim}"
    : "${GPU_SMOKE_IMAGE:=$IMAGE_REGISTRY/docker.io/nvidia/cuda:12.4.1-base-ubuntu22.04}"
    STATE_DIR=/var/lib/vcloud-host
    CRI_SOCKET=unix:///run/containerd/containerd.sock
    GPU_ENABLED=false
    NEEDS_REBOOT=false
    WORK_DIR=
    PHASE=preflight
    MIRROR_STATUS=not-tested
    REBOOT_ATTEMPTED=false
}

log() { printf '[vCloud] %s\n' "$*"; }
die() {
    log "ERROR: $*" >&2
    if [[ ${APPLY_ACTIVE:-false} == true ]] && command -v jq >/dev/null; then write_result failed || true; fi
    exit 1
}
bad_config() { log "CONFIG: $*" >&2; exit 2; }
version_at_least() { [[ "$(printf '%s\n%s\n' "$2" "$1" | sort -V | head -n1)" == "$2" ]]; }

validate_config() {
    local name value
    validate_ssot_identity
    for name in BOOTSTRAP_K8S INSTALL_HPC ENABLE_KVM RUN_SMOKE_TESTS GPU_SMOKE_TEST MIRROR_REQUIRED IMAGE_STAGING; do
        [[ ${!name} == true || ${!name} == false ]] || bad_config "$name must be true or false"
    done
    [[ $ENABLE_GPU =~ ^(auto|true|false)$ ]] || bad_config 'ENABLE_GPU must be auto, true or false'
    for name in HUGEPAGES_2M HUGEPAGES_1G MIN_NORMAL_RAM_MIB; do
        [[ ${!name} =~ ^(0|[1-9][0-9]{0,5})$ ]] || bad_config "$name must be a nonnegative integer <= 999999"
    done
    # Reject unsupported version combinations before any host mutation. Overrides require a
    # documented compatibility review, rather than silently selecting an untested 'latest'.
    [[ $KUBERNETES_VERSION =~ ^v1\.(33|34|35|36)\.[0-9]+$ ]] || bad_config 'Kubernetes must be v1.33..v1.36 for this Cilium profile'
    [[ $CILIUM_VERSION =~ ^1\.20\.[0-9]+$ ]] || bad_config 'This profile supports Cilium 1.20.x'
    for name in HELM_VERSION CILIUM_CLI_VERSION KUBECONFORM_VERSION TKN_VERSION ARGOCD_VERSION YQ_VERSION CRICTL_VERSION; do
        [[ ${!name} =~ ^v[0-9]+\.[0-9]+\.[0-9]+$ ]] || bad_config "$name needs an exact vX.Y.Z release"
    done
    value=${KUBERNETES_VERSION%.*}
    [[ ${CRICTL_VERSION%.*} == "$value" ]] || bad_config 'crictl must use the same Kubernetes minor version'
    [[ $NVIDIA_TOOLKIT_VERSION =~ ^[0-9]+\.[0-9]+\.[0-9]+-[0-9]+$ ]] || bad_config 'Toolkit requires an exact Debian version'
    [[ $NVIDIA_DEVICE_PLUGIN_VERSION =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] || bad_config 'Device plugin requires X.Y.Z'
    # A registry authority only: no credentials, quotes, spaces, path-prefix rewriting or HTTP.
    [[ $REGISTRY_MIRROR =~ ^https://[a-zA-Z0-9.-]+(:[0-9]+)?$ ]] || bad_config 'Mirror must be an HTTPS authority without a path or credentials'
    [[ -z $REGISTRY_CA_FILE || $REGISTRY_CA_FILE =~ ^/[a-zA-Z0-9_./-]+$ ]] || bad_config 'Registry CA requires an absolute simple path'
    [[ -z $CONTROL_PLANE_ENDPOINT || $CONTROL_PLANE_ENDPOINT =~ ^[a-zA-Z0-9.-]+:6443$ ]] || bad_config 'CONTROL_PLANE_ENDPOINT must be a DNS authority on 6443'
    [[ -z $NODE_NAME || $NODE_NAME =~ ^[a-z0-9]([a-z0-9.-]*[a-z0-9])?$ ]] || bad_config 'NODE_NAME must be a DNS label/name'
    [[ $NVIDIA_DRIVER_PACKAGE == auto || $NVIDIA_DRIVER_PACKAGE =~ ^nvidia-driver-[0-9]+(-server)?(-open)?$ ]] || bad_config 'Invalid NVIDIA driver package'
    for name in PAUSE_IMAGE GPU_SMOKE_IMAGE REGISTRY_PROBE_IMAGE HUGEPAGE_SMOKE_IMAGE; do
        [[ ${!name} =~ ^[a-zA-Z0-9][a-zA-Z0-9._/:@+-]+$ ]] || bad_config "$name contains invalid characters"
        [[ ${!name} == "$IMAGE_REGISTRY/"* ]] || bad_config "$name must use the SSoT registry"
        [[ ${!name} =~ @sha256:[a-f0-9]{64}$ || ${!name} =~ :v?[0-9]+\.[0-9]+\.[0-9]+([._+-][a-zA-Z0-9._+-]+)?$ ]] || bad_config "$name requires an exact semantic version or SHA256 digest"
    done
    # Pure stdlib check also catches CIDR overlap; host routes are checked during preflight.
    python3 - "$POD_CIDR" "$SERVICE_CIDR" "$NODE_IP" <<'PY'
import ipaddress, sys
try:
    pod, svc = [ipaddress.IPv4Network(x, strict=True) for x in sys.argv[1:3]]
    assert not pod.overlaps(svc), 'Pod and service CIDRs overlap'
    assert 16 <= pod.prefixlen <= 24, 'Pod CIDR must have a /16../24 prefix'
    if sys.argv[3]:
        node = ipaddress.IPv4Address(sys.argv[3])
        assert not node.is_loopback and not node.is_unspecified, 'Node IP must be routable'
        assert node not in pod and node not in svc, 'Node IP overlaps cluster CIDRs'
except (ValueError, AssertionError) as e:
    print(e, file=sys.stderr)
    sys.exit(2)
PY
}

# BEGIN GENERATED SSOT VALIDATION
validate_ssot_identity() {
    case $PLATFORM_PROFILE in
    production) [[ $SSOT_VERSION == 2.2 &&
       $CLUSTER_NAME == vCloud-prod-01 &&
       $CLUSTER_DNS_NAME == vcloud-prod-01 &&
       $BASE_DOMAIN == vcloud.example.com &&
       $GITOPS_REPOSITORY == amazen33/twinfra &&
       $IMAGE_REGISTRY == registry.vcloud.example.com &&
       $REGISTRY_MIRROR == https://registry.vcloud.example.com &&
       $MIRROR_REQUIRED == true && $IMAGE_STAGING == false ]] ;;
    dev-cairo-1) [[ $SSOT_VERSION == 2.2 && $CLUSTER_NAME == twinfra-dev-cairo-1 && $CLUSTER_DNS_NAME == twinfra-dev-cairo-1 && $BASE_DOMAIN == twinfra.example.com && $GITOPS_REPOSITORY == amazen33/twinfra && $IMAGE_REGISTRY == registry.twinfra.example.com && $REGISTRY_MIRROR == https://registry.twinfra.example.com && $MIRROR_REQUIRED == true && ( $IMAGE_STAGING == false || $IMAGE_STAGING == true ) ]] ;;
    dev-cairo-2) [[ $SSOT_VERSION == 2.2 && $CLUSTER_NAME == twinfra-dev-cairo-2 && $CLUSTER_DNS_NAME == twinfra-dev-cairo-2 && $BASE_DOMAIN == twinfra.example.com && $GITOPS_REPOSITORY == amazen33/twinfra && $IMAGE_REGISTRY == registry.twinfra.example.com && $REGISTRY_MIRROR == https://registry.twinfra.example.com && $MIRROR_REQUIRED == true && ( $IMAGE_STAGING == false || $IMAGE_STAGING == true ) ]] ;;
    *) return 2 ;;
    esac || bad_config 'Identity/registry drift from vcloud-ssot.yaml; change the contract and regenerate first'
}
# END GENERATED SSOT VALIDATION

# BEGIN GENERATED POLICY GATE
check_policy_gate() {
    [[ $BOOTSTRAP_K8S == true ]] || return 0
    # Approved by the user on 2026-10-05; no environment flag broadens the scope.
    [[ $KUBERNETES_VERSION == v1.36.5 && $CILIUM_VERSION == 1.20.2 && $NVIDIA_DEVICE_PLUGIN_VERSION == 0.20.1 ]] || {
        log 'Node exception is pinned to the approved Kubernetes/Cilium/NVIDIA versions; unreviewed drift rejected.' >&2
        return 42
    }
}
# END GENERATED POLICY GATE

plan() {
    cat <<EOF
Upstream Kubernetes $KUBERNETES_VERSION via kubeadm; Cilium $CILIUM_VERSION replaces kube-proxy.
SSoT $SSOT_VERSION: $CLUSTER_NAME, $BASE_DOMAIN, GitOps $GITOPS_REPOSITORY.
Ubuntu 24.04 LTS, kernel >= 6.8, cgroup v2, bpffs, overlayfs, swap disabled.
HugeTLB: $HUGEPAGES_2M x 2 MiB + $HUGEPAGES_1G x 1 GiB; ordinary RAM floor $MIN_NORMAL_RAM_MIB MiB.
System containerd CRI: $CRI_SOCKET, systemd cgroups, TLS mirror $REGISTRY_MIRROR.
GPU=$ENABLE_GPU, KVM=$ENABLE_KVM, HPC=$INSTALL_HPC, bootstrap=$BOOTSTRAP_K8S, smoke=$RUN_SMOKE_TESTS, gpu-smoke=$GPU_SMOKE_TEST.
Pods=$POD_CIDR services=$SERVICE_CIDR. A fresh single-node control plane also schedules workloads.
Cilium native routing requires underlay routes to every remote node PodCIDR; no overlay is installed.
Node exception approved: only the pinned kubeadm/Cilium/NVIDIA scope passes manifest checks.
Apply may exit 20. Reboot Ubuntu and rerun with the same /etc/vcloud-host.env.
This plan makes no changes. Consult docs/module-minus-1.md for sizing, passthrough and acceptance gates.
EOF
}

# Replace only changed content, retain one original backup, and preserve stable mtimes.
# Returns success in both cases; callers inspect FILE_CHANGED to decide on service restarts.
write_file() {
    local destination=$1 mode=${2:-0644} candidate
    candidate=$(mktemp "$WORK_DIR/file.XXXXXX")
    cat > "$candidate"
    FILE_CHANGED=false
    if [[ ! -f $destination ]] || ! cmp -s "$candidate" "$destination"; then
        mkdir -p "$(dirname "$destination")"
        if [[ -f $destination && ! -e ${destination}.vcloud-original ]]; then
            cp -a -- "$destination" "${destination}.vcloud-original"
        fi
        install -m "$mode" "$candidate" "$destination"
        FILE_CHANGED=true
    fi
    chmod "$mode" "$destination"
    rm -f -- "$candidate"
}

fetch() { curl --fail --silent --show-error --location --proto '=https' --tlsv1.2 --retry 4 --connect-timeout 15 --max-time 600 "$1" -o "$2"; }

# Exact release assets are verified against GitHub's published SHA-256 digest over TLS.
# Missing digests are a failure, never an excuse to execute unverified downloads.
gh_asset() {
    local repo=$1 tag=$2 asset=$3 output=$4 digest url metadata
    metadata="$WORK_DIR/release.json"
    fetch "https://api.github.com/repos/$repo/releases/tags/$tag" "$metadata"
    url=$(jq -er --arg name "$asset" '.assets[] | select(.name == $name) | .browser_download_url' "$metadata")
    digest=$(jq -er --arg name "$asset" '.assets[] | select(.name == $name) | .digest' "$metadata")
    [[ $digest =~ ^sha256:[a-f0-9]{64}$ ]] || die "No SHA-256 published for $repo $tag $asset"
    fetch "$url" "$output"
    printf '%s  %s\n' "${digest#sha256:}" "$output" | sha256sum -c -
}

install_cli() {
    local binary=$1 version=$2 repo=$3 asset=$4 member=${5:-} stamp archive unpack
    stamp="$STATE_DIR/cli-$binary"
    # A stamp includes the installed hash, so a replaced binary is detected on rerun.
    if [[ -x /usr/local/bin/$binary && -f $stamp ]] &&
        [[ $(head -n1 "$stamp") == "$version/$ARCH" ]] &&
        [[ $(tail -n1 "$stamp") == "$(sha256sum "/usr/local/bin/$binary" | cut -d' ' -f1)" ]]; then
        return
    fi
    archive="$WORK_DIR/$asset"
    gh_asset "$repo" "$version" "$asset" "$archive"
    if [[ -n $member ]]; then
        unpack="$WORK_DIR/unpack-$binary"
        mkdir -p "$unpack"
        tar -xzf "$archive" -C "$unpack" "$member"
        install -m 0755 "$unpack/$member" "/usr/local/bin/$binary"
    else
        install -m 0755 "$archive" "/usr/local/bin/$binary"
    fi
    printf '%s/%s\n%s\n' "$version" "$ARCH" "$(sha256sum "/usr/local/bin/$binary" | cut -d' ' -f1)" > "$stamp"
}

install_missing() {
    local package
    local -a missing=()
    for package in "$@"; do
        if [[ $(dpkg-query -W -f='${Status}' "$package" 2>/dev/null || true) != 'install ok installed' ]]; then
            missing+=("$package")
        fi
    done
    if ((${#missing[@]})); then apt-get install -y --no-install-recommends "${missing[@]}"; fi
}

preflight() {
    [[ $EUID == 0 ]] || die 'Run apply/validate as root'
    [[ $(uname -s) == Linux && -r /etc/os-release ]] || die 'A real Ubuntu host is required'
    # shellcheck disable=SC1091
    source /etc/os-release
    [[ $ID == ubuntu && $VERSION_ID == 24.04 ]] || die 'SSoT v2.2 requires Ubuntu 24.04 LTS'
    [[ -d /run/systemd/system ]] || die 'systemd must be PID 1; containers and WSL are not supported targets'
    case $(dpkg --print-architecture) in amd64) ARCH=amd64; TKN_ARCH=x86_64;; arm64) ARCH=arm64; TKN_ARCH=aarch64;; *) die 'Only amd64 and arm64 are supported';; esac
    NODE_NAME=${NODE_NAME:-$(hostname -s | tr '[:upper:]' '[:lower:]')}
    NODE_IP=${NODE_IP:-$(ip -4 route get 1.1.1.1 | awk '{for (i=1;i<=NF;i++) if ($i=="src") { print $(i+1); exit }}')}
    [[ -n $NODE_IP ]] || die 'No default IPv4 route; set NODE_IP explicitly'
    validate_config
    # Do not adopt an existing cluster or overwrite an unrelated runtime configuration.
    if [[ -e /etc/kubernetes/admin.conf && ! -e $STATE_DIR/cluster-owned ]]; then die 'Existing Kubernetes cluster is unmanaged'; fi
    if [[ -e /etc/containerd/config.toml && ! -e $STATE_DIR/containerd-owned ]] &&
        systemctl is-active --quiet containerd; then die 'An existing active containerd is unmanaged; use a fresh host'; fi
    if [[ -f $STATE_DIR/cluster-version && $(cat "$STATE_DIR/cluster-version") != "$KUBERNETES_VERSION" ]]; then
        die 'Cluster version differs. Use the kubeadm upgrade procedure rather than this bootstrap'
    fi
    if systemctl is-active --quiet k3s || systemctl is-active --quiet rke2-server; then die 'A different Kubernetes distribution is active'; fi
    # Reject overlap with existing NIC routes before creating the cluster. Ignore cluster routes
    # only after this bootstrap has initialized its own node.
    if [[ ! -e $STATE_DIR/cluster-owned ]]; then
        ip -j -4 route show | python3 -c '
import ipaddress, json, sys
nets = [ipaddress.ip_network(x) for x in sys.argv[1:]]
for route in json.load(sys.stdin):
    dst = route.get("dst", "default")
    if dst != "default" and any(ipaddress.ip_network(dst).overlaps(n) for n in nets):
        sys.exit("Existing host route overlaps the pod/service network: " + dst)
' "$POD_CIDR" "$SERVICE_CIDR"
    fi
    local mem_mib reservation_mib
    (( $(nproc) >= 2 )) || die 'At least two CPU cores are required'
    (( $(df -Pm /var/lib | awk 'NR==2 {print $4}') >= 20480 )) || die 'At least 20 GiB of free /var/lib storage is required'
    mem_mib=$(awk '/^MemTotal:/ {print int($2/1024)}' /proc/meminfo)
    reservation_mib=$((HUGEPAGES_2M * 2 + HUGEPAGES_1G * 1024))
    ((mem_mib - reservation_mib >= MIN_NORMAL_RAM_MIB)) || die "HugePages leave less than $MIN_NORMAL_RAM_MIB MiB ordinary RAM"
    if ((HUGEPAGES_1G > 0)) && [[ $ARCH == amd64 ]]; then
        grep -qw pdpe1gb /proc/cpuinfo || die 'CPU/VM hides 1 GiB pages; expose host CPU features or set HUGEPAGES_1G=0'
    fi
    if [[ $ENABLE_GPU != false ]]; then
        local device vendor class
        for device in /sys/bus/pci/devices/*; do
            [[ -r $device/vendor && -r $device/class ]] || continue
            vendor=$(cat "$device/vendor"); class=$(cat "$device/class")
            if [[ $vendor == 0x10de && ( $class == 0x03* || $class == 0x12* ) ]]; then GPU_ENABLED=true; break; fi
        done
        [[ $ENABLE_GPU != true || $GPU_ENABLED == true ]] || die 'No passed-through NVIDIA GPU detected'
    fi
    [[ -z $REGISTRY_CA_FILE || -r $REGISTRY_CA_FILE ]] || die 'Registry CA file is missing'
    log "Ubuntu $VERSION_ID/$ARCH node=$NODE_NAME IP=$NODE_IP GPU=$GPU_ENABLED"
}

mark_reboot() {
    NEEDS_REBOOT=true
    printf '%s\n' "$*" >> "$STATE_DIR/reboot-required"
    cat /proc/sys/kernel/random/boot_id > "$STATE_DIR/reboot-boot-id"
    log "REBOOT REQUIRED: $*"
}

render_grub() {
    local huge_args="default_hugepagesz=2M hugepagesz=2M hugepages=$HUGEPAGES_2M"
    if ((HUGEPAGES_1G > 0)); then huge_args+=" hugepagesz=1G hugepages=$HUGEPAGES_1G"; fi
    cat <<EOF
# Managed by vCloud Module -1. Preserve unrelated boot arguments, replace our own once.
vcloud_strip_boot_args() {
    printf '%s' "\$1" | sed -E 's/(^|[[:space:]])(systemd.unified_cgroup_hierarchy|cgroup_no_v1|default_hugepagesz|hugepagesz|hugepages)=[^[:space:]]+//g'
}
GRUB_CMDLINE_LINUX="\$(vcloud_strip_boot_args "\${GRUB_CMDLINE_LINUX:-}") systemd.unified_cgroup_hierarchy=1 cgroup_no_v1=all $huge_args"
GRUB_CMDLINE_LINUX_DEFAULT="\$(vcloud_strip_boot_args "\${GRUB_CMDLINE_LINUX_DEFAULT:-}")"
unset -f vcloud_strip_boot_args
EOF
}

prepare_kernel() {
    PHASE=kernel
    # SSoT requires Ubuntu 24.04's supported kernel track.
    if ! version_at_least "$(uname -r | cut -d- -f1)" 6.8; then
        [[ $REBOOT_ATTEMPTED == false ]] || die 'The requested kernel is still not active after reboot; inspect the provider/GRUB boot selection'
        apt-get install -y linux-generic linux-headers-generic
        mark_reboot 'Boot the installed Ubuntu kernel >= 6.8'
    fi
    # GRUB is explicit: fail clearly on images booted by systemd-boot/UKI/provider-specific
    # bootloaders; do not pretend that editing an unused file configures their kernel.
    command -v update-grub >/dev/null && [[ -f /etc/default/grub ]] || die 'GRUB boot configuration required; adapt kernel arguments for this image bootloader'
    write_file /etc/default/grub.d/99-vcloud-host.cfg < <(render_grub)
    if [[ $FILE_CHANGED == true ]]; then update-grub; mark_reboot 'Activate cgroup v2 and persistent HugeTLB boot reservations'; fi
    [[ $(stat -fc '%T' /sys/fs/cgroup) == cgroup2fs ]] || mark_reboot 'cgroup v2 is not active'
    # Kernel/module checks run only on the requested kernel, after a possible reboot.
    if version_at_least "$(uname -r | cut -d- -f1)" 6.8; then
        if ! modinfo overlay >/dev/null 2>&1 || ! modinfo br_netfilter >/dev/null 2>&1; then
            install_missing "linux-modules-extra-$(uname -r)"
        fi
        validate_kernel
        printf 'overlay\nbr_netfilter\n' | write_file /etc/modules-load.d/99-vcloud.conf
        modprobe overlay; modprobe br_netfilter
        mkdir -p /sys/fs/bpf
        # Mount via a dedicated systemd unit, avoiding duplicate /etc/fstab entries.
        write_file /etc/systemd/system/sys-fs-bpf.mount <<'EOF'
[Unit]
Description=vCloud BPF filesystem
Before=containerd.service kubelet.service
[Mount]
What=bpffs
Where=/sys/fs/bpf
Type=bpf
Options=rw,nosuid,nodev,noexec,mode=700
[Install]
WantedBy=multi-user.target
EOF
        systemctl daemon-reload
        if ! mountpoint -q /sys/fs/bpf; then systemctl start sys-fs-bpf.mount; fi
        systemctl enable sys-fs-bpf.mount
        [[ $(findmnt -n -o FSTYPE --target /sys/fs/bpf) == bpf ]] || die 'Unexpected filesystem at /sys/fs/bpf'
    fi
}

validate_kernel() {
    local config option
    config="/boot/config-$(uname -r)"
    version_at_least "$(uname -r | cut -d- -f1)" 6.8 || die 'Running kernel is older than 6.8'
    [[ -r $config ]] || die "Cannot verify running kernel configuration: $config"
    for option in BPF BPF_SYSCALL BPF_JIT BPF_EVENTS CGROUPS CGROUP_BPF CGROUP_HUGETLB DEBUG_INFO_BTF \
        PERF_EVENTS SCHEDSTATS CRYPTO_SHA1 NET_CLS_BPF NET_CLS_ACT NET_SCH_INGRESS FIB_RULES \
        OVERLAY_FS BRIDGE_NETFILTER HUGETLBFS HUGETLB_PAGE; do
        grep -Eq "^CONFIG_${option}=(y|m)$" "$config" || die "Kernel lacks CONFIG_$option"
    done
    [[ -r /sys/kernel/btf/vmlinux ]] || die 'Kernel BTF is unavailable'
}

render_sysctl() {
    cat <<'EOF'
# Managed by vCloud. HugeTLB pools use per-size sysfs/boot reservations, not nr_hugepages.
net.core.somaxconn = 65535
net.core.netdev_max_backlog = 16384
net.ipv4.tcp_max_syn_backlog = 8192
net.ipv4.ip_forward = 1
net.ipv4.conf.all.rp_filter = 0
net.ipv4.conf.default.rp_filter = 0
net.bridge.bridge-nf-call-iptables = 1
net.bridge.bridge-nf-call-ip6tables = 1
vm.max_map_count = 262144
vm.swappiness = 0
fs.file-max = 2097152
fs.inotify.max_user_instances = 8192
fs.inotify.max_user_watches = 1048576
EOF
}

prepare_memory_network() {
    PHASE=memory-network
    # Capture swap units before swapoff so systemd cannot later reactivate them.
    local unit size count path actual
    while read -r unit _; do
        [[ $unit == *.swap ]] && systemctl mask "$unit"
    done < <(systemctl list-units --all --type=swap --no-legend --plain)
    swapoff -a
    awk '$0 !~ /^[[:space:]]*#/ && $3 == "swap" {$0="# vCloud disabled swap: " $0} {print}' /etc/fstab > "$WORK_DIR/fstab"
    write_file /etc/fstab < "$WORK_DIR/fstab"
    # bridge sysctls do not exist until br_netfilter is loaded on the new kernel.
    render_sysctl | write_file /etc/sysctl.d/99-vcloud.conf
    if [[ -e /proc/sys/net/bridge/bridge-nf-call-iptables ]]; then sysctl -p /etc/sysctl.d/99-vcloud.conf; fi
    for size in 2048 1048576; do
        if [[ $size == 2048 ]]; then count=$HUGEPAGES_2M; else count=$HUGEPAGES_1G; fi
        path="/sys/kernel/mm/hugepages/hugepages-${size}kB/nr_hugepages"
        if [[ ! -e $path ]]; then
            if ((count > 0)); then
                [[ $REBOOT_ATTEMPTED == false ]] || die "Kernel still lacks the ${size}kB pool after reboot; expose CPU features in the hypervisor"
                mark_reboot "Kernel does not expose the ${size}kB HugeTLB pool"
            fi
            continue
        fi
        actual=$(cat "$path")
        # Never shrink pools in use on a rerun. Changing sizes belongs to maintenance.
        if ((actual < count)); then printf '%s\n' "$count" > "$path" || true; fi
        actual=$(cat "$path")
        if ((actual < count)); then
            [[ $REBOOT_ATTEMPTED == false ]] || die "${size}kB HugePages remain insufficient after reboot; inspect boot arguments/RAM/NUMA"
            mark_reboot "${size}kB HugePages allocated $actual of $count; reserve at boot"
        fi
    done
    # Kernel boot allocation persists both sizes. Mount each pool for host-side HPC consumers.
    # Kubernetes HugePages volumes are mounted by kubelet independently of these directories.
    for size in 2M 1G; do
        if [[ $size == 2M ]]; then count=$HUGEPAGES_2M; else count=$HUGEPAGES_1G; fi
        ((count > 0)) || continue
        mkdir -p "/dev/hugepages-$size"
        awk -v p="/dev/hugepages-$size" '$2 != p' /etc/fstab > "$WORK_DIR/fstab-huge"
        printf 'none /dev/hugepages-%s hugetlbfs pagesize=%s,mode=1770,nofail 0 0\n' "$size" "$size" >> "$WORK_DIR/fstab-huge"
        write_file /etc/fstab < "$WORK_DIR/fstab-huge"
        if [[ $NEEDS_REBOOT == false ]] && ! mountpoint -q "/dev/hugepages-$size"; then mount "/dev/hugepages-$size"; fi
    done
    systemctl daemon-reload
}

install_gpu() {
    [[ $GPU_ENABLED == true ]] || { log 'GPU setup skipped: no requested/visible GPU'; return; }
    PHASE=gpu
    local driver package candidate loaded_branch boot_id
    boot_id=$(cat /proc/sys/kernel/random/boot_id)
    install_missing ubuntu-drivers-common "linux-headers-$(uname -r)" mokutil
    driver=$(nvidia-smi --query-gpu=driver_version --format=csv,noheader 2>/dev/null | head -n1 || true)
    if [[ -z $driver ]] || ! version_at_least "$driver" 550; then
        package=$NVIDIA_DRIVER_PACKAGE
        if [[ $package == auto ]]; then
            package=$(ubuntu-drivers devices | awk '/recommended/ && /nvidia-driver-/ {print $3; exit}')
        fi
        [[ $package =~ ^nvidia-driver-([0-9]+)(-server)?(-open)?$ ]] || die 'No recommended NVIDIA package; set NVIDIA_DRIVER_PACKAGE for your GPU'
        candidate=${BASH_REMATCH[1]}
        ((candidate >= 550)) || die 'NVIDIA driver branch must be >= 550'
        install_missing "$package"
        modprobe nvidia || true
        driver=$(nvidia-smi --query-gpu=driver_version --format=csv,noheader 2>/dev/null | head -n1 || true)
        if [[ -z $driver ]] || ! version_at_least "$driver" 550; then
            if [[ -f $STATE_DIR/gpu-pending-boot && $(cat "$STATE_DIR/gpu-pending-boot") != "$boot_id" ]]; then
                die 'GPU still unavailable after reboot; inspect Secure Boot/MOK, DKMS and passthrough; no reboot loop'
            fi
            printf '%s\n' "$boot_id" > "$STATE_DIR/gpu-pending-boot"
            mark_reboot 'Load NVIDIA driver; Secure Boot may require signed modules or MOK enrollment'
        fi
    fi
    # Signed repository, exact toolkit package family version, no deprecated apt-key.
    fetch https://nvidia.github.io/libnvidia-container/gpgkey "$WORK_DIR/nvidia.key"
    gpg --batch --yes --dearmor -o "$WORK_DIR/nvidia.gpg" "$WORK_DIR/nvidia.key"
    write_file /usr/share/keyrings/nvidia-container-toolkit.gpg < "$WORK_DIR/nvidia.gpg"
    # shellcheck disable=SC2016 # $(ARCH) is an APT substitution, not a shell command.
    printf 'deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit.gpg] https://nvidia.github.io/libnvidia-container/stable/deb/$(ARCH) /\n' \
        | write_file /etc/apt/sources.list.d/nvidia-container-toolkit.list
    apt-get update
    apt-get install -y --no-install-recommends \
        "nvidia-container-toolkit=$NVIDIA_TOOLKIT_VERSION" "nvidia-container-toolkit-base=$NVIDIA_TOOLKIT_VERSION" \
        "libnvidia-container-tools=$NVIDIA_TOOLKIT_VERSION" "libnvidia-container1=$NVIDIA_TOOLKIT_VERSION"
    if command -v nvidia-smi >/dev/null && nvidia-smi >/dev/null 2>&1; then
        loaded_branch=$(nvidia-smi --query-gpu=driver_version --format=csv,noheader | head -n1)
        if ! version_at_least "$loaded_branch" 550 && [[ $NEEDS_REBOOT == false ]]; then die 'Loaded driver is older than 550'; fi
    fi
}

render_containerd() {
    local major=${1%%.*} plugin cni_bin_setting image_extra
    if [[ $major == 1 ]]; then
        plugin=io.containerd.grpc.v1.cri
        cat <<EOF
version = 2
[plugins."$plugin"]
  sandbox_image = "$PAUSE_IMAGE"
[plugins."$plugin".registry]
  config_path = "/etc/containerd/certs.d"
[plugins."$plugin".containerd]
  snapshotter = "overlayfs"
  default_runtime_name = "runc"
[plugins."$plugin".cni]
  bin_dir = "/opt/cni/bin"
  conf_dir = "/etc/cni/net.d"
EOF
    elif [[ $major == 2 ]]; then
        plugin=io.containerd.cri.v1.runtime
        # 2.0 has bin_dir; 2.1+ adds bin_dirs and the transfer-service/local-pull switch.
        if [[ $1 == 2.0 || $1 == 2.0.* ]]; then
            cni_bin_setting='  bin_dir = "/opt/cni/bin"'
            image_extra=
        else
            cni_bin_setting='  bin_dirs = ["/opt/cni/bin"]'
            image_extra='  use_local_image_pull = true'
        fi
        cat <<EOF
version = 3
[plugins."io.containerd.cri.v1.images"]
  snapshotter = "overlayfs"
$image_extra
[plugins."io.containerd.cri.v1.images".pinned_images]
  sandbox = "$PAUSE_IMAGE"
[plugins."io.containerd.cri.v1.images".registry]
  config_path = "/etc/containerd/certs.d"
[plugins."$plugin".containerd]
  default_runtime_name = "runc"
[plugins."$plugin".cni]
$cni_bin_setting
  conf_dir = "/etc/cni/net.d"
EOF
    else die 'Only containerd 1.7+ and 2.x are supported'; fi
    cat <<EOF
[plugins."$plugin".containerd.runtimes.runc]
  runtime_type = "io.containerd.runc.v2"
[plugins."$plugin".containerd.runtimes.runc.options]
  SystemdCgroup = true
EOF
}

render_mirror() {
    # Upstream names map into mirror /v2/<upstream>/<repository>. override_path
    # describes this explicit API root; it does not rewrite a bare hostname.
    # Root and host share the same private endpoint, including CA and capabilities.
    local upstream=${1:-} endpoint=$REGISTRY_MIRROR
    case "$upstream" in ''|quay.io|docker.io|registry.k8s.io|ghcr.io|public.ecr.aws|nvcr.io) ;; *) die 'Unsupported upstream mirror';; esac
    [[ -z $upstream ]] || endpoint="$REGISTRY_MIRROR/v2/$upstream"
    if [[ $MIRROR_REQUIRED == true ]]; then printf 'server = "%s"\n' "$endpoint"; fi
    printf 'capabilities = ["pull", "resolve"]\n'
    [[ -z $upstream ]] || printf 'override_path = true\n'
    if [[ -n $REGISTRY_CA_FILE ]]; then printf 'ca = "%s"\n' "$REGISTRY_CA_FILE"; fi
    printf '\n[host."%s"]\n  capabilities = ["pull", "resolve"]\n' "$endpoint"
    [[ -z $upstream ]] || printf '  override_path = true\n'
    if [[ -n $REGISTRY_CA_FILE ]]; then printf '  ca = "%s"\n' "$REGISTRY_CA_FILE"; fi
}

configure_containerd() {
    PHASE=containerd
    local version changed=false
    version=$(containerd --version | awk '{gsub(/^v/,"",$3); print $3}')
    version_at_least "$version" 1.7 || die 'containerd >= 1.7 is required (enable Ubuntu updates/security repositories)'
    mkdir -p /opt/cni/bin /etc/cni/net.d /etc/containerd/certs.d/_default
    render_containerd "$version" > "$WORK_DIR/containerd.toml"
    if [[ $GPU_ENABLED == true ]]; then
        # Explicit empty drop-in path writes the staged config rather than modifying live imports.
        nvidia-ctk runtime configure --runtime=containerd --config="$WORK_DIR/containerd.toml" --drop-in-config=""
        python3 - "$WORK_DIR/containerd.toml" <<'PY'
import sys, toml
path = sys.argv[1]
data = toml.load(path)
for plugin in data.get('plugins', {}).values():
    for runtime in plugin.get('containerd', {}).get('runtimes', {}).values():
        runtime.setdefault('options', {})['SystemdCgroup'] = True
with open(path, 'w') as f:
    toml.dump(data, f)
PY
    fi
    containerd --config "$WORK_DIR/containerd.toml" config dump > "$WORK_DIR/containerd-parsed.toml"
    write_file /etc/containerd/config.toml < "$WORK_DIR/containerd.toml"
    [[ $FILE_CHANGED == true ]] && changed=true
    touch "$STATE_DIR/containerd-owned"
    render_mirror | write_file /etc/containerd/certs.d/_default/hosts.toml
    local upstream
    for upstream in "$IMAGE_REGISTRY" quay.io docker.io registry.k8s.io ghcr.io public.ecr.aws nvcr.io; do
        mkdir -p "/etc/containerd/certs.d/$upstream"
        if [[ $upstream == "$IMAGE_REGISTRY" ]]; then
            render_mirror | write_file "/etc/containerd/certs.d/$upstream/hosts.toml"
        else
            render_mirror "$upstream" | write_file "/etc/containerd/certs.d/$upstream/hosts.toml"
        fi
    done
    write_file /etc/crictl.yaml <<EOF
runtime-endpoint: $CRI_SOCKET
image-endpoint: $CRI_SOCKET
timeout: 30
debug: false
EOF
    write_file /etc/systemd/system/containerd.service.d/99-vcloud.conf <<'EOF'
[Unit]
Requires=sys-fs-bpf.mount
After=sys-fs-bpf.mount
[Service]
LimitNOFILE=1048576
TasksMax=infinity
EOF
    [[ $FILE_CHANGED == true ]] && changed=true
    systemctl daemon-reload
    systemctl enable containerd
    if [[ $changed == true ]]; then systemctl restart containerd; else systemctl start containerd; fi
    timeout 60 bash -c 'until crictl info >/dev/null 2>&1; do sleep 2; done'
    crictl info | jq -e '.status.conditions[] | select(.type == "RuntimeReady") | .status == true' >/dev/null
    if [[ $IMAGE_STAGING == true ]]; then
        stage_bootstrap_images
        return
    fi
    # A 401 response proves TLS reachability but not permission to pull the probe image.
    local -a ca_args=()
    [[ -z $REGISTRY_CA_FILE ]] || ca_args=(--cacert "$REGISTRY_CA_FILE")
    if curl --silent --show-error --connect-timeout 10 --max-time 15 "${ca_args[@]}" "$REGISTRY_MIRROR/v2/" -o /dev/null; then
        MIRROR_STATUS=reachable-cri-pull-pending
        log 'Registry endpoint responded; validating the CRI image pull'
    elif [[ $MIRROR_REQUIRED == true ]]; then
        die 'Required registry mirror unreachable; configure DNS/TLS before bootstrapping'
    else
        MIRROR_STATUS=unreachable-using-fallback
        log 'Mirror unreachable; configured upstream fallback will be used (mirror gate remains unverified)'
    fi
    crictl pull "$REGISTRY_PROBE_IMAGE"
    [[ $MIRROR_REQUIRED == false ]] || MIRROR_STATUS=verified-cri-pull-mirror-only
}

stage_bootstrap_images() {
    [[ $PLATFORM_PROFILE == dev-cairo-1 || $PLATFORM_PROFILE == dev-cairo-2 ]] || die 'IMAGE_STAGING is dev-only'
    [[ $MIRROR_REQUIRED == true ]] || die 'Dev staging requires mirror-only CRI; no upstream fallback'
    [[ -r /etc/twinfra/bootstrap-images.lock.json && -r /usr/local/lib/twinfra/stage-images.py ]] || die 'Missing generated dev bootstrap image lock/staging agent'
    PHASE=bootstrap-image-staging
    python3 /usr/local/lib/twinfra/stage-images.py --lock /etc/twinfra/bootstrap-images.lock.json || die 'Bootstrap image staging failed; inspect missing/mismatched image report'
    MIRROR_STATUS=staged-verified
}

install_tooling() {
    PHASE=tooling
    install_cli cilium "$CILIUM_CLI_VERSION" cilium/cilium-cli "cilium-linux-$ARCH.tar.gz" cilium
    install_cli kubeconform "$KUBECONFORM_VERSION" yannh/kubeconform "kubeconform-linux-$ARCH.tar.gz" kubeconform
    install_cli tkn "$TKN_VERSION" tektoncd/cli "tkn_${TKN_VERSION#v}_Linux_$TKN_ARCH.tar.gz" tkn
    install_cli argocd "$ARGOCD_VERSION" argoproj/argo-cd "argocd-linux-$ARCH"
    install_cli yq "$YQ_VERSION" mikefarah/yq "yq_linux_$ARCH"
    install_cli crictl "$CRICTL_VERSION" kubernetes-sigs/cri-tools "crictl-$CRICTL_VERSION-linux-$ARCH.tar.gz" crictl
    # Helm publishes archives at get.helm.sh, with a detached SHA-256 file.
    local asset stamp digest
    stamp="$STATE_DIR/cli-helm"
    asset="helm-$HELM_VERSION-linux-$ARCH.tar.gz"
    if [[ ! -x /usr/local/bin/helm || ! -f $stamp ]] ||
        [[ $(head -n1 "$stamp") != "$HELM_VERSION/$ARCH" ]] ||
        [[ $(tail -n1 "$stamp") != "$(sha256sum /usr/local/bin/helm | cut -d' ' -f1)" ]]; then
        fetch "https://get.helm.sh/$asset" "$WORK_DIR/$asset"
        fetch "https://get.helm.sh/$asset.sha256sum" "$WORK_DIR/helm.sha256"
        digest=$(awk 'NR==1 {print $1}' "$WORK_DIR/helm.sha256")
        [[ $digest =~ ^[a-f0-9]{64}$ ]] || die 'Invalid Helm checksum'
        printf '%s  %s\n' "$digest" "$WORK_DIR/$asset" | sha256sum -c -
        tar -xzf "$WORK_DIR/$asset" -C "$WORK_DIR" "linux-$ARCH/helm"
        install -m 0755 "$WORK_DIR/linux-$ARCH/helm" /usr/local/bin/helm
        printf '%s/%s\n%s\n' "$HELM_VERSION" "$ARCH" "$(sha256sum /usr/local/bin/helm | cut -d' ' -f1)" > "$stamp"
    fi
}

install_kubernetes_packages() {
    PHASE=kubernetes-packages
    local minor=${KUBERNETES_VERSION%.*} package_version package current
    fetch "https://pkgs.k8s.io/core:/stable:/$minor/deb/Release.key" "$WORK_DIR/kubernetes.key"
    gpg --batch --yes --dearmor -o "$WORK_DIR/kubernetes.gpg" "$WORK_DIR/kubernetes.key"
    write_file /etc/apt/keyrings/kubernetes.gpg < "$WORK_DIR/kubernetes.gpg"
    printf 'deb [signed-by=/etc/apt/keyrings/kubernetes.gpg] https://pkgs.k8s.io/core:/stable:/%s/deb/ /\n' "$minor" \
        | write_file /etc/apt/sources.list.d/kubernetes.list
    apt-get update
    package_version=$(apt-cache madison kubeadm | awk -v v="${KUBERNETES_VERSION#v}-" 'index($3,v)==1 {print $3; exit}')
    [[ -n $package_version ]] || die "Kubernetes package not available: $KUBERNETES_VERSION"
    for package in kubeadm kubelet kubectl; do
        current=$(dpkg-query -W -f='${Version}' "$package" 2>/dev/null || true)
        if [[ $current != "$package_version" ]]; then
            [[ ! -f /etc/kubernetes/admin.conf ]] || die 'Refusing in-place Kubernetes package upgrade/downgrade'
            apt-get install -y --no-install-recommends "$package=$package_version"
        fi
    done
    apt-mark hold kubeadm kubelet kubectl
    # Kubelet configuration is generated by kubeadm; it cannot start fully until init.
    systemctl enable kubelet
}

install_hpc_kvm() {
    if [[ $INSTALL_HPC == true ]]; then
        PHASE=hpc
        install_missing openmpi-bin libopenmpi-dev libucx0 libucx-dev ucx-utils \
            hwloc libhwloc-dev libpmix-dev rdma-core ibverbs-utils slurm-client libslurm-dev
        if ! dpkg-query -W -f='${Status}' apptainer 2>/dev/null | grep -q 'install ok installed'; then
            add-apt-repository -y ppa:apptainer/ppa
            apt-get update
            install_missing apptainer
        fi
        # User namespaces are necessary for non-setuid Apptainer. Retain Ubuntu AppArmor
        # restrictions; package-supplied profiles and site policy must allow the user.
        [[ ! -r /proc/sys/user/max_user_namespaces || $(cat /proc/sys/user/max_user_namespaces) -gt 0 ]] || die 'Unprivileged user namespaces are disabled'
    fi
    if [[ $ENABLE_KVM == true ]]; then
        PHASE=kvm
        [[ $ARCH == amd64 ]] || die 'This optional nested-KVM profile currently supports amd64'
        install_missing qemu-system-x86 qemu-utils cpu-checker
        if grep -qw vmx /proc/cpuinfo; then modprobe kvm_intel;
        elif grep -qw svm /proc/cpuinfo; then modprobe kvm_amd;
        else die 'Expose hardware virtualization / nested KVM in the parent hypervisor'; fi
        [[ -c /dev/kvm ]] || die 'KVM device is unavailable'
        kvm-ok
    fi
}

render_kubeadm() {
    local resolv_conf=/etc/resolv.conf endpoint=${CONTROL_PLANE_ENDPOINT:-"$NODE_IP:6443"} dev_proxy=
    # skipPhases alone does not disable kubeadm's kube-proxy image preflight.
    [[ ${IMAGE_STAGING:-false} != true ]] || dev_proxy=$'proxy:\n  disabled: true\n'
    [[ ! -e /run/systemd/resolve/resolv.conf ]] || resolv_conf=/run/systemd/resolve/resolv.conf
    cat <<EOF
apiVersion: kubeadm.k8s.io/v1beta4
kind: InitConfiguration
localAPIEndpoint:
  advertiseAddress: "$NODE_IP"
  bindPort: 6443
nodeRegistration:
  name: "$NODE_NAME"
  criSocket: "$CRI_SOCKET"
  taints: []
  kubeletExtraArgs:
    - name: node-ip
      value: "$NODE_IP"
patches:
  directory: "$STATE_DIR/kubeadm-patches"
skipPhases:
  - addon/kube-proxy
---
apiVersion: kubeadm.k8s.io/v1beta4
kind: ClusterConfiguration
kubernetesVersion: "$KUBERNETES_VERSION"
clusterName: "$CLUSTER_NAME"
imageRepository: "$IMAGE_REGISTRY/registry.k8s.io"
${dev_proxy}controlPlaneEndpoint: "$endpoint"
networking:
  podSubnet: "$POD_CIDR"
  serviceSubnet: "$SERVICE_CIDR"
  dnsDomain: cluster.local
apiServer:
  certSANs:
    - "$NODE_IP"
    - "$NODE_NAME"
---
apiVersion: kubelet.config.k8s.io/v1beta1
kind: KubeletConfiguration
cgroupDriver: systemd
failSwapOn: true
resolvConf: "$resolv_conf"
maxPods: 110
EOF
}

render_cilium_values() {
    cat <<EOF
kubeProxyReplacement: true
k8sServiceHost: "$NODE_IP"
k8sServicePort: 6443
containerRuntimeEndpoint: /run/containerd/containerd.sock
cni:
  binPath: /opt/cni/bin
  confPath: /etc/cni/net.d
  exclusive: true
bpf:
  masquerade: true
  autoMount:
    enabled: false
cgroup:
  autoMount:
    enabled: false
  hostRoot: /sys/fs/cgroup
ipam:
  mode: kubernetes
ipv4:
  enabled: true
ipv6:
  enabled: false
routingMode: native
ipv4NativeRoutingCIDR: "$POD_CIDR"
# Route distribution is site-specific. Enable direct routes only on a verified common L2.
autoDirectNodeRoutes: false
cluster:
  name: "$CLUSTER_DNS_NAME"
image:
  repository: "$IMAGE_REGISTRY/quay.io/cilium/cilium"
envoy:
  image:
    repository: "$IMAGE_REGISTRY/quay.io/cilium/cilium-envoy"
operator:
  replicas: 1
  image:
    repository: "$IMAGE_REGISTRY/quay.io/cilium/operator"
  securityContext:
    runAsNonRoot: true
    runAsUser: 65532
    runAsGroup: 65532
    allowPrivilegeEscalation: false
    capabilities: {drop: [ALL]}
# Full kube-proxy replacement is strict about required kernel features. Policy mode
# 'default' enforces selected policies. render_foundation denies both directions in
# all three core namespaces; essential node components remain in kube-system.
policyEnforcementMode: default
EOF
    if [[ $PLATFORM_PROFILE == dev-* ]]; then
        cat <<EOF
commonLabels:
  twinfra.io/environment: dev
  twinfra.io/region: "${PLATFORM_PROFILE#dev-}"
  twinfra.io/component: cilium
EOF
    fi
}

bootstrap_kubernetes() {
    [[ $BOOTSTRAP_K8S == true ]] || return
    check_policy_gate || return $?
    write_manifest_validators
    write_file "$STATE_DIR/kubeadm-patches/etcd+strategic.yaml" < <(render_etcd_patch)
    PHASE=kubeadm-init
    write_file "$STATE_DIR/kubeadm.yaml" 0600 < <(render_kubeadm)
    kubeadm config validate --config "$STATE_DIR/kubeadm.yaml"
    if [[ ! -f /etc/kubernetes/admin.conf ]]; then
        # Generate outside kubelet's watched directory, then check actual static Pods
        # against the approved host mounts BEFORE starting the real control plane.
        validate_kubeadm_preview
        # Write ownership before init so an interrupted run can be diagnosed. A partial
        # init is NOT reset automatically: inspect and recover with kubeadm deliberately.
        touch "$STATE_DIR/cluster-owned"
        printf '%s\n' "$KUBERNETES_VERSION" > "$STATE_DIR/cluster-version"
        if [[ -e /etc/kubernetes/manifests/kube-apiserver.yaml ]]; then die 'Partial kubeadm init: inspect manifests; no automatic reset'; fi
        kubeadm init --config "$STATE_DIR/kubeadm.yaml" --skip-phases=addon/kube-proxy
    fi
    validate_static_control_plane /etc/kubernetes/manifests
    export KUBECONFIG=/etc/kubernetes/admin.conf
    chmod 0600 "$KUBECONFIG"
    kubectl --request-timeout=30s get --raw=/readyz >/dev/null
    PHASE=cilium
    write_file "$STATE_DIR/cilium-values.yaml" < <(render_cilium_values)
    helm upgrade --install cilium cilium --repo https://helm.cilium.io/ \
        --version "$CILIUM_VERSION" --namespace kube-system --values "$STATE_DIR/cilium-values.yaml" \
        --post-renderer "$STATE_DIR/validate-chart" --wait --timeout 10m --history-max 3
    cilium status --wait --wait-duration 10m
    kubectl wait --for=condition=Ready "node/$NODE_NAME" --timeout=300s
    kubectl -n kube-system rollout status deployment/coredns --timeout=300s
    render_foundation > "$STATE_DIR/foundation.yaml"
    validate_manifests workloads "$STATE_DIR/foundation.yaml"
    kubectl apply -f "$STATE_DIR/foundation.yaml"
    if [[ $GPU_ENABLED == true ]]; then
        PHASE=gpu-kubernetes
        render_gpu_runtime_class > "$STATE_DIR/runtimeclass.yaml"
        validate_manifests workloads "$STATE_DIR/runtimeclass.yaml"
        kubectl apply -f "$STATE_DIR/runtimeclass.yaml"
        helm upgrade --install nvidia-device-plugin nvidia-device-plugin \
            --repo https://nvidia.github.io/k8s-device-plugin --version "$NVIDIA_DEVICE_PLUGIN_VERSION" \
            --namespace kube-system --set runtimeClassName=nvidia \
            --set gfd.enabled=false --set nfd.enabled=false \
            --set image.repository="$IMAGE_REGISTRY/nvcr.io/nvidia/k8s-device-plugin" \
            --set image.tag="v$NVIDIA_DEVICE_PLUGIN_VERSION" \
            --post-renderer "$STATE_DIR/filter-nvidia-chart" --wait --timeout 5m --history-max 3
        # shellcheck disable=SC2016 # $1 belongs to the nested shell.
        timeout 180 bash -c 'until kubectl get node "$1" -o json | jq -e '\''.status.allocatable["nvidia.com/gpu"] | tonumber > 0'\'' >/dev/null; do sleep 3; done' _ "$NODE_NAME"
    fi
}

render_chart_validator() {
    cat <<EOF
#!/usr/bin/env bash
set -Eeuo pipefail
candidate=\$(mktemp --suffix=.yaml)
trap 'rm -f -- "\$candidate"' EXIT
cat > "\$candidate"
[[ -s "\$candidate" ]] || { echo 'Empty Helm manifest output' >&2; exit 1; }
# ADR-0047: label all upstream objects, including chart-created namespaces.
# Kustomize never includes these labels in selectors.
if [[ "$PLATFORM_PROFILE" == dev-* ]]; then
    labels_dir=\$(mktemp -d)
    cp "\$candidate" "\$labels_dir/upstream.yaml"
    cat > "\$labels_dir/kustomization.yaml" <<'VCLOUD_LABELS'
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization
resources: [upstream.yaml]
labels:
- pairs:
    twinfra.io/environment: dev
    twinfra.io/region: "${PLATFORM_PROFILE#dev-}"
    twinfra.io/component: cilium
  includeSelectors: false
  includeTemplates: true
VCLOUD_LABELS
    kubectl kustomize "\$labels_dir" > "\$candidate"
    rm -rf -- "\$labels_dir"
fi
# Summary goes to stderr: Helm requires stdout to contain YAML only.
kubeconform -strict -summary -kubernetes-version "${KUBERNETES_VERSION#v}" "\$candidate" >&2
yq eval-all -o=json -I=0 '[.]' "\$candidate" |
    python3 "$STATE_DIR/check-manifest-contract.py" --policy "$STATE_DIR/node-exceptions.json" >&2
cat "\$candidate"
EOF
}

render_nvidia_filter() {
    cat <<EOF
#!/usr/bin/env bash
set -Eeuo pipefail
# The upstream chart always emits the privileged MPS DaemonSet when the device
# plugin is enabled. MPS sharing is outside this profile: remove that object.
yq eval 'select(.kind != "DaemonSet" or .metadata.name != "nvidia-device-plugin-mps-control-daemon")' - |
    "$STATE_DIR/validate-chart"
EOF
}

write_manifest_validators() {
    render_exception_policy | write_file "$STATE_DIR/node-exceptions.json" 0600
    render_policy_checker | write_file "$STATE_DIR/check-manifest-contract.py" 0700
    render_chart_validator | write_file "$STATE_DIR/validate-chart" 0755
    render_nvidia_filter | write_file "$STATE_DIR/filter-nvidia-chart" 0755
}

# BEGIN GENERATED EXCEPTION POLICY
render_exception_policy() {
    if [[ $PLATFORM_PROFILE == dev-* ]]; then
        cat <<'VCLOUD_DEV_POLICY_JSON'
{
  "status": "approved",
  "approval": {
    "by": "user",
    "date": "2026-10-05",
    "decision": "Approve the documented node exception",
    "adr": "docs/adr-0001-node-host-mounts.md",
    "inventorySHA256": "bbb08cd371ab6321f9620d7db4280b3515a24db0825d171c116c34d6f0946f81"
  },
  "registry": "registry.twinfra.example.com",
  "versions": {
    "kubernetes": "v1.36.5",
    "cilium": "1.20.2",
    "nvidiaDevicePlugin": "0.20.1"
  },
  "agents": {
    "DaemonSet/kube-system/cilium": {
      "hostNetwork": true,
      "hostPID": false,
      "hostIPC": false,
      "hostPaths": [
        {
          "name": "bpf-maps",
          "hostPath": {
            "type": "DirectoryOrCreate",
            "path": "/sys/fs/bpf"
          }
        },
        {
          "name": "cilium-cgroup",
          "hostPath": {
            "type": "DirectoryOrCreate",
            "path": "/sys/fs/cgroup"
          }
        },
        {
          "name": "cilium-netns",
          "hostPath": {
            "type": "DirectoryOrCreate",
            "path": "/var/run/netns"
          }
        },
        {
          "name": "cilium-run",
          "hostPath": {
            "type": "DirectoryOrCreate",
            "path": "/var/run/cilium"
          }
        },
        {
          "name": "cni-path",
          "hostPath": {
            "type": "DirectoryOrCreate",
            "path": "/opt/cni/bin"
          }
        },
        {
          "name": "envoy-sockets",
          "hostPath": {
            "type": "DirectoryOrCreate",
            "path": "/var/run/cilium/envoy/sockets"
          }
        },
        {
          "name": "etc-cni-netd",
          "hostPath": {
            "type": "DirectoryOrCreate",
            "path": "/etc/cni/net.d"
          }
        },
        {
          "name": "host-proc-sys-kernel",
          "hostPath": {
            "type": "Directory",
            "path": "/proc/sys/kernel"
          }
        },
        {
          "name": "host-proc-sys-net",
          "hostPath": {
            "type": "Directory",
            "path": "/proc/sys/net"
          }
        },
        {
          "name": "hostproc",
          "hostPath": {
            "type": "Directory",
            "path": "/proc"
          }
        },
        {
          "name": "lib-modules",
          "hostPath": {
            "type": "",
            "path": "/lib/modules"
          }
        },
        {
          "name": "xtables-lock",
          "hostPath": {
            "type": "FileOrCreate",
            "path": "/run/xtables.lock"
          }
        }
      ],
      "containers": [
        {
          "name": "cilium-agent",
          "category": "containers",
          "image": "registry.twinfra.example.com/quay.io/cilium/cilium:v1.20.2@sha256:2939231d0d3e3ebddcd80fffa168b7ddcc78fdf0dc864d1c8c126ff523c54f01",
          "securityContext": {
            "privileged": false,
            "allowPrivilegeEscalation": true,
            "runAsNonRoot": false,
            "runAsUser": null,
            "runAsGroup": null,
            "readOnlyRootFilesystem": false,
            "procMount": "Default",
            "appArmorProfile": {
              "type": "Unconfined"
            },
            "seccompProfile": {
              "type": "Unconfined"
            },
            "seLinuxOptions": {
              "level": "s0",
              "type": "spc_t"
            },
            "capabilities": {
              "add": [
                "CHOWN",
                "DAC_OVERRIDE",
                "FOWNER",
                "IPC_LOCK",
                "KILL",
                "NET_ADMIN",
                "NET_RAW",
                "SETGID",
                "SETUID",
                "SYSLOG",
                "SYS_ADMIN",
                "SYS_MODULE",
                "SYS_RESOURCE"
              ],
              "drop": [
                "ALL"
              ]
            }
          },
          "hostMounts": [
            {
              "readOnly": false,
              "mountPropagation": "HostToContainer",
              "subPath": "",
              "subPathExpr": "",
              "name": "bpf-maps",
              "mountPath": "/sys/fs/bpf"
            },
            {
              "readOnly": false,
              "mountPropagation": null,
              "subPath": "",
              "subPathExpr": "",
              "name": "cilium-cgroup",
              "mountPath": "/sys/fs/cgroup"
            },
            {
              "readOnly": false,
              "mountPropagation": "HostToContainer",
              "subPath": "",
              "subPathExpr": "",
              "name": "cilium-netns",
              "mountPath": "/var/run/cilium/netns"
            },
            {
              "readOnly": false,
              "mountPropagation": null,
              "subPath": "",
              "subPathExpr": "",
              "name": "cilium-run",
              "mountPath": "/var/run/cilium"
            },
            {
              "readOnly": false,
              "mountPropagation": null,
              "subPath": "",
              "subPathExpr": "",
              "name": "envoy-sockets",
              "mountPath": "/var/run/cilium/envoy/sockets"
            },
            {
              "readOnly": false,
              "mountPropagation": null,
              "subPath": "",
              "subPathExpr": "",
              "name": "etc-cni-netd",
              "mountPath": "/host/etc/cni/net.d"
            },
            {
              "readOnly": false,
              "mountPropagation": null,
              "subPath": "",
              "subPathExpr": "",
              "mountPath": "/host/proc/sys/kernel",
              "name": "host-proc-sys-kernel"
            },
            {
              "readOnly": false,
              "mountPropagation": null,
              "subPath": "",
              "subPathExpr": "",
              "mountPath": "/host/proc/sys/net",
              "name": "host-proc-sys-net"
            },
            {
              "readOnly": true,
              "mountPropagation": null,
              "subPath": "",
              "subPathExpr": "",
              "name": "lib-modules",
              "mountPath": "/lib/modules"
            },
            {
              "readOnly": false,
              "mountPropagation": null,
              "subPath": "",
              "subPathExpr": "",
              "name": "xtables-lock",
              "mountPath": "/run/xtables.lock"
            }
          ],
          "command": [
            "cilium-agent"
          ],
          "args": [
            "--config-dir=/tmp/cilium/config-map"
          ]
        },
        {
          "name": "apply-sysctl-overwrites",
          "category": "initContainers",
          "image": "registry.twinfra.example.com/quay.io/cilium/cilium:v1.20.2@sha256:2939231d0d3e3ebddcd80fffa168b7ddcc78fdf0dc864d1c8c126ff523c54f01",
          "securityContext": {
            "privileged": false,
            "allowPrivilegeEscalation": true,
            "runAsNonRoot": false,
            "runAsUser": null,
            "runAsGroup": null,
            "readOnlyRootFilesystem": false,
            "procMount": "Default",
            "appArmorProfile": {
              "type": "Unconfined"
            },
            "seccompProfile": {
              "type": "Unconfined"
            },
            "seLinuxOptions": {
              "level": "s0",
              "type": "spc_t"
            },
            "capabilities": {
              "add": [
                "SYS_ADMIN",
                "SYS_CHROOT",
                "SYS_PTRACE"
              ],
              "drop": [
                "ALL"
              ]
            }
          },
          "hostMounts": [
            {
              "readOnly": false,
              "mountPropagation": null,
              "subPath": "",
              "subPathExpr": "",
              "name": "cni-path",
              "mountPath": "/hostbin"
            },
            {
              "readOnly": false,
              "mountPropagation": null,
              "subPath": "",
              "subPathExpr": "",
              "name": "hostproc",
              "mountPath": "/hostproc"
            }
          ],
          "command": [
            "bash",
            "-ec",
            "cp /usr/bin/cilium-sysctlfix /hostbin/cilium-sysctlfix;\nnsenter --mount=/hostproc/1/ns/mnt \"${BIN_PATH}/cilium-sysctlfix\";\nrm /hostbin/cilium-sysctlfix\n"
          ],
          "args": []
        },
        {
          "name": "clean-cilium-state",
          "category": "initContainers",
          "image": "registry.twinfra.example.com/quay.io/cilium/cilium:v1.20.2@sha256:2939231d0d3e3ebddcd80fffa168b7ddcc78fdf0dc864d1c8c126ff523c54f01",
          "securityContext": {
            "privileged": false,
            "allowPrivilegeEscalation": true,
            "runAsNonRoot": false,
            "runAsUser": null,
            "runAsGroup": null,
            "readOnlyRootFilesystem": false,
            "procMount": "Default",
            "appArmorProfile": {
              "type": "Unconfined"
            },
            "seccompProfile": {
              "type": "Unconfined"
            },
            "seLinuxOptions": {
              "level": "s0",
              "type": "spc_t"
            },
            "capabilities": {
              "add": [
                "NET_ADMIN",
                "SYS_ADMIN",
                "SYS_MODULE",
                "SYS_RESOURCE"
              ],
              "drop": [
                "ALL"
              ]
            }
          },
          "hostMounts": [
            {
              "readOnly": false,
              "mountPropagation": null,
              "subPath": "",
              "subPathExpr": "",
              "name": "bpf-maps",
              "mountPath": "/sys/fs/bpf"
            },
            {
              "readOnly": false,
              "mountPropagation": "HostToContainer",
              "subPath": "",
              "subPathExpr": "",
              "name": "cilium-cgroup",
              "mountPath": "/sys/fs/cgroup"
            },
            {
              "readOnly": false,
              "mountPropagation": null,
              "subPath": "",
              "subPathExpr": "",
              "name": "cilium-run",
              "mountPath": "/var/run/cilium"
            }
          ],
          "command": [
            "/init-container.sh"
          ],
          "args": []
        },
        {
          "name": "config",
          "category": "initContainers",
          "image": "registry.twinfra.example.com/quay.io/cilium/cilium:v1.20.2@sha256:2939231d0d3e3ebddcd80fffa168b7ddcc78fdf0dc864d1c8c126ff523c54f01",
          "securityContext": {
            "privileged": false,
            "allowPrivilegeEscalation": true,
            "runAsNonRoot": false,
            "runAsUser": null,
            "runAsGroup": null,
            "readOnlyRootFilesystem": false,
            "procMount": "Default",
            "appArmorProfile": {
              "type": "Unconfined"
            },
            "seccompProfile": {
              "type": "Unconfined"
            },
            "capabilities": {
              "add": [
                "NET_ADMIN"
              ],
              "drop": [
                "ALL"
              ]
            }
          },
          "hostMounts": [],
          "command": [
            "cilium-dbg",
            "build-config",
            "--k8s-api-server-urls="
          ],
          "args": []
        },
        {
          "name": "install-cni-binaries",
          "category": "initContainers",
          "image": "registry.twinfra.example.com/quay.io/cilium/cilium:v1.20.2@sha256:2939231d0d3e3ebddcd80fffa168b7ddcc78fdf0dc864d1c8c126ff523c54f01",
          "securityContext": {
            "privileged": false,
            "allowPrivilegeEscalation": true,
            "runAsNonRoot": false,
            "runAsUser": null,
            "runAsGroup": null,
            "readOnlyRootFilesystem": false,
            "procMount": "Default",
            "appArmorProfile": {
              "type": "Unconfined"
            },
            "seccompProfile": {
              "type": "Unconfined"
            },
            "seLinuxOptions": {
              "level": "s0",
              "type": "spc_t"
            },
            "capabilities": {
              "add": [],
              "drop": [
                "ALL"
              ]
            }
          },
          "hostMounts": [
            {
              "readOnly": false,
              "mountPropagation": null,
              "subPath": "",
              "subPathExpr": "",
              "name": "cni-path",
              "mountPath": "/host/opt/cni/bin"
            }
          ],
          "command": [
            "/install-plugin.sh"
          ],
          "args": []
        }
      ]
    },
    "DaemonSet/kube-system/cilium-envoy": {
      "hostNetwork": true,
      "hostPID": false,
      "hostIPC": false,
      "hostPaths": [
        {
          "name": "envoy-artifacts",
          "hostPath": {
            "type": "DirectoryOrCreate",
            "path": "/var/run/cilium/envoy/artifacts"
          }
        },
        {
          "name": "envoy-sockets",
          "hostPath": {
            "type": "DirectoryOrCreate",
            "path": "/var/run/cilium/envoy/sockets"
          }
        }
      ],
      "containers": [
        {
          "name": "cilium-envoy",
          "category": "containers",
          "image": "registry.twinfra.example.com/quay.io/cilium/cilium-envoy:v1.37.6-1789133542-cbec91f666af0bf742da986d43832932dbb26b82@sha256:af7382699576b9e65e9184efa52eeca0b58aea70ad6e511bf260c91d9f740463",
          "securityContext": {
            "privileged": false,
            "allowPrivilegeEscalation": true,
            "runAsNonRoot": false,
            "runAsUser": null,
            "runAsGroup": null,
            "readOnlyRootFilesystem": false,
            "procMount": "Default",
            "appArmorProfile": {
              "type": "Unconfined"
            },
            "seLinuxOptions": {
              "level": "s0",
              "type": "spc_t"
            },
            "capabilities": {
              "add": [
                "NET_ADMIN",
                "SYS_ADMIN"
              ],
              "drop": [
                "ALL"
              ]
            }
          },
          "hostMounts": [
            {
              "readOnly": true,
              "mountPropagation": null,
              "subPath": "",
              "subPathExpr": "",
              "name": "envoy-artifacts",
              "mountPath": "/var/run/cilium/envoy/artifacts"
            },
            {
              "readOnly": false,
              "mountPropagation": null,
              "subPath": "",
              "subPathExpr": "",
              "name": "envoy-sockets",
              "mountPath": "/var/run/cilium/envoy/sockets"
            }
          ],
          "command": [
            "/usr/bin/cilium-envoy-starter"
          ],
          "args": [
            "--",
            "-c /var/run/cilium/envoy/bootstrap-config.json",
            "--base-id 0",
            "--log-level info"
          ]
        }
      ]
    },
    "Deployment/kube-system/cilium-operator": {
      "hostNetwork": true,
      "hostPID": false,
      "hostIPC": false,
      "hostPaths": [],
      "containers": [
        {
          "name": "cilium-operator",
          "category": "containers",
          "image": "registry.twinfra.example.com/quay.io/cilium/operator-generic:v1.20.2@sha256:64d8798350e8569b8e7622563fed6e44dce2625f311e4651b774816516c744fc",
          "securityContext": {
            "privileged": false,
            "allowPrivilegeEscalation": false,
            "runAsNonRoot": true,
            "runAsUser": 65532,
            "runAsGroup": 65532,
            "readOnlyRootFilesystem": false,
            "procMount": "Default",
            "seccompProfile": {
              "type": "RuntimeDefault"
            },
            "capabilities": {
              "add": [],
              "drop": [
                "ALL"
              ]
            }
          },
          "hostMounts": [],
          "command": [
            "cilium-operator-generic"
          ],
          "args": [
            "--config-dir=/tmp/cilium/config-map",
            "--debug=$(CILIUM_DEBUG)"
          ]
        }
      ]
    },
    "DaemonSet/kube-system/nvidia-device-plugin": {
      "hostNetwork": false,
      "hostPID": false,
      "hostIPC": false,
      "hostPaths": [
        {
          "name": "cdi-root",
          "hostPath": {
            "type": "DirectoryOrCreate",
            "path": "/var/run/cdi"
          }
        },
        {
          "name": "kubelet-device-plugins-dir",
          "hostPath": {
            "type": "Directory",
            "path": "/var/lib/kubelet/device-plugins"
          }
        },
        {
          "name": "mps-root",
          "hostPath": {
            "type": "DirectoryOrCreate",
            "path": "/run/nvidia/mps"
          }
        },
        {
          "name": "mps-shm",
          "hostPath": {
            "type": "",
            "path": "/run/nvidia/mps/shm"
          }
        }
      ],
      "containers": [
        {
          "name": "nvidia-device-plugin-ctr",
          "category": "containers",
          "image": "registry.twinfra.example.com/nvcr.io/nvidia/k8s-device-plugin:v0.20.1",
          "securityContext": {
            "privileged": false,
            "allowPrivilegeEscalation": false,
            "runAsNonRoot": false,
            "runAsUser": null,
            "runAsGroup": null,
            "readOnlyRootFilesystem": false,
            "procMount": "Default",
            "capabilities": {
              "add": [],
              "drop": [
                "ALL"
              ]
            }
          },
          "hostMounts": [
            {
              "readOnly": false,
              "mountPropagation": null,
              "subPath": "",
              "subPathExpr": "",
              "name": "cdi-root",
              "mountPath": "/var/run/cdi"
            },
            {
              "readOnly": false,
              "mountPropagation": null,
              "subPath": "",
              "subPathExpr": "",
              "name": "kubelet-device-plugins-dir",
              "mountPath": "/var/lib/kubelet/device-plugins"
            },
            {
              "readOnly": false,
              "mountPropagation": null,
              "subPath": "",
              "subPathExpr": "",
              "name": "mps-root",
              "mountPath": "/mps"
            },
            {
              "readOnly": false,
              "mountPropagation": null,
              "subPath": "",
              "subPathExpr": "",
              "name": "mps-shm",
              "mountPath": "/dev/shm"
            }
          ],
          "command": [
            "nvidia-device-plugin"
          ],
          "args": []
        }
      ]
    }
  },
  "controlPlane": {
    "Pod/kube-system/kube-apiserver": {
      "image": "registry.twinfra.example.com/registry.k8s.io/kube-apiserver:v1.36.5",
      "mounts": {
        "/etc/kubernetes/pki": {
          "readOnly": true,
          "type": "DirectoryOrCreate",
          "required": true
        },
        "/etc/ssl/certs": {
          "readOnly": true,
          "type": "DirectoryOrCreate",
          "required": true
        },
        "/etc/ca-certificates": {
          "readOnly": true,
          "type": "DirectoryOrCreate",
          "required": false
        },
        "/usr/share/ca-certificates": {
          "readOnly": true,
          "type": "DirectoryOrCreate",
          "required": false
        },
        "/usr/local/share/ca-certificates": {
          "readOnly": true,
          "type": "DirectoryOrCreate",
          "required": false
        },
        "/etc/pki/ca-trust": {
          "readOnly": true,
          "type": "DirectoryOrCreate",
          "required": false
        },
        "/etc/pki/tls/certs": {
          "readOnly": true,
          "type": "DirectoryOrCreate",
          "required": false
        }
      }
    },
    "Pod/kube-system/kube-controller-manager": {
      "image": "registry.twinfra.example.com/registry.k8s.io/kube-controller-manager:v1.36.5",
      "mounts": {
        "/etc/kubernetes/pki": {
          "readOnly": true,
          "type": "DirectoryOrCreate",
          "required": true
        },
        "/etc/ssl/certs": {
          "readOnly": true,
          "type": "DirectoryOrCreate",
          "required": true
        },
        "/etc/ca-certificates": {
          "readOnly": true,
          "type": "DirectoryOrCreate",
          "required": false
        },
        "/usr/share/ca-certificates": {
          "readOnly": true,
          "type": "DirectoryOrCreate",
          "required": false
        },
        "/usr/local/share/ca-certificates": {
          "readOnly": true,
          "type": "DirectoryOrCreate",
          "required": false
        },
        "/etc/pki/ca-trust": {
          "readOnly": true,
          "type": "DirectoryOrCreate",
          "required": false
        },
        "/etc/pki/tls/certs": {
          "readOnly": true,
          "type": "DirectoryOrCreate",
          "required": false
        },
        "/etc/kubernetes/controller-manager.conf": {
          "readOnly": true,
          "type": "FileOrCreate",
          "required": true
        }
      }
    },
    "Pod/kube-system/kube-scheduler": {
      "image": "registry.twinfra.example.com/registry.k8s.io/kube-scheduler:v1.36.5",
      "mounts": {
        "/etc/kubernetes/scheduler.conf": {
          "readOnly": true,
          "type": "FileOrCreate",
          "required": true
        }
      }
    },
    "Pod/kube-system/etcd": {
      "image": "registry.twinfra.example.com/registry.k8s.io/etcd:3.6.8-0",
      "mounts": {
        "/etc/kubernetes/pki/etcd": {
          "readOnly": true,
          "type": "DirectoryOrCreate",
          "required": true
        },
        "/var/lib/etcd": {
          "readOnly": false,
          "type": "DirectoryOrCreate",
          "required": true
        }
      }
    }
  },
  "sourcePolicySHA256": "d9799b19ff5fb101cde1870840f29b6d54d6e6cff2c22b389a62d9adfe7cd253",
  "profile": "WO-21 dev mirror relocation only; same images, mounts and security"
}
VCLOUD_DEV_POLICY_JSON
    else
    cat <<'VCLOUD_POLICY_JSON'
{
  "status": "approved",
  "approval": {
    "by": "user",
    "date": "2026-10-05",
    "decision": "Approve the documented node exception",
    "adr": "docs/adr-0001-node-host-mounts.md",
    "inventorySHA256": "bbb08cd371ab6321f9620d7db4280b3515a24db0825d171c116c34d6f0946f81"
  },
  "registry": "registry.vcloud.example.com",
  "versions": {
    "kubernetes": "v1.36.5",
    "cilium": "1.20.2",
    "nvidiaDevicePlugin": "0.20.1"
  },
  "agents": {
    "DaemonSet/kube-system/cilium": {
      "hostNetwork": true,
      "hostPID": false,
      "hostIPC": false,
      "hostPaths": [
        {
          "name": "bpf-maps",
          "hostPath": {
            "type": "DirectoryOrCreate",
            "path": "/sys/fs/bpf"
          }
        },
        {
          "name": "cilium-cgroup",
          "hostPath": {
            "type": "DirectoryOrCreate",
            "path": "/sys/fs/cgroup"
          }
        },
        {
          "name": "cilium-netns",
          "hostPath": {
            "type": "DirectoryOrCreate",
            "path": "/var/run/netns"
          }
        },
        {
          "name": "cilium-run",
          "hostPath": {
            "type": "DirectoryOrCreate",
            "path": "/var/run/cilium"
          }
        },
        {
          "name": "cni-path",
          "hostPath": {
            "type": "DirectoryOrCreate",
            "path": "/opt/cni/bin"
          }
        },
        {
          "name": "envoy-sockets",
          "hostPath": {
            "type": "DirectoryOrCreate",
            "path": "/var/run/cilium/envoy/sockets"
          }
        },
        {
          "name": "etc-cni-netd",
          "hostPath": {
            "type": "DirectoryOrCreate",
            "path": "/etc/cni/net.d"
          }
        },
        {
          "name": "host-proc-sys-kernel",
          "hostPath": {
            "type": "Directory",
            "path": "/proc/sys/kernel"
          }
        },
        {
          "name": "host-proc-sys-net",
          "hostPath": {
            "type": "Directory",
            "path": "/proc/sys/net"
          }
        },
        {
          "name": "hostproc",
          "hostPath": {
            "type": "Directory",
            "path": "/proc"
          }
        },
        {
          "name": "lib-modules",
          "hostPath": {
            "type": "",
            "path": "/lib/modules"
          }
        },
        {
          "name": "xtables-lock",
          "hostPath": {
            "type": "FileOrCreate",
            "path": "/run/xtables.lock"
          }
        }
      ],
      "containers": [
        {
          "name": "cilium-agent",
          "category": "containers",
          "image": "registry.vcloud.example.com/quay.io/cilium/cilium:v1.20.2@sha256:2939231d0d3e3ebddcd80fffa168b7ddcc78fdf0dc864d1c8c126ff523c54f01",
          "securityContext": {
            "privileged": false,
            "allowPrivilegeEscalation": true,
            "runAsNonRoot": false,
            "runAsUser": null,
            "runAsGroup": null,
            "readOnlyRootFilesystem": false,
            "procMount": "Default",
            "appArmorProfile": {
              "type": "Unconfined"
            },
            "seccompProfile": {
              "type": "Unconfined"
            },
            "seLinuxOptions": {
              "level": "s0",
              "type": "spc_t"
            },
            "capabilities": {
              "add": [
                "CHOWN",
                "DAC_OVERRIDE",
                "FOWNER",
                "IPC_LOCK",
                "KILL",
                "NET_ADMIN",
                "NET_RAW",
                "SETGID",
                "SETUID",
                "SYSLOG",
                "SYS_ADMIN",
                "SYS_MODULE",
                "SYS_RESOURCE"
              ],
              "drop": [
                "ALL"
              ]
            }
          },
          "hostMounts": [
            {
              "readOnly": false,
              "mountPropagation": "HostToContainer",
              "subPath": "",
              "subPathExpr": "",
              "name": "bpf-maps",
              "mountPath": "/sys/fs/bpf"
            },
            {
              "readOnly": false,
              "mountPropagation": null,
              "subPath": "",
              "subPathExpr": "",
              "name": "cilium-cgroup",
              "mountPath": "/sys/fs/cgroup"
            },
            {
              "readOnly": false,
              "mountPropagation": "HostToContainer",
              "subPath": "",
              "subPathExpr": "",
              "name": "cilium-netns",
              "mountPath": "/var/run/cilium/netns"
            },
            {
              "readOnly": false,
              "mountPropagation": null,
              "subPath": "",
              "subPathExpr": "",
              "name": "cilium-run",
              "mountPath": "/var/run/cilium"
            },
            {
              "readOnly": false,
              "mountPropagation": null,
              "subPath": "",
              "subPathExpr": "",
              "name": "envoy-sockets",
              "mountPath": "/var/run/cilium/envoy/sockets"
            },
            {
              "readOnly": false,
              "mountPropagation": null,
              "subPath": "",
              "subPathExpr": "",
              "name": "etc-cni-netd",
              "mountPath": "/host/etc/cni/net.d"
            },
            {
              "readOnly": false,
              "mountPropagation": null,
              "subPath": "",
              "subPathExpr": "",
              "mountPath": "/host/proc/sys/kernel",
              "name": "host-proc-sys-kernel"
            },
            {
              "readOnly": false,
              "mountPropagation": null,
              "subPath": "",
              "subPathExpr": "",
              "mountPath": "/host/proc/sys/net",
              "name": "host-proc-sys-net"
            },
            {
              "readOnly": true,
              "mountPropagation": null,
              "subPath": "",
              "subPathExpr": "",
              "name": "lib-modules",
              "mountPath": "/lib/modules"
            },
            {
              "readOnly": false,
              "mountPropagation": null,
              "subPath": "",
              "subPathExpr": "",
              "name": "xtables-lock",
              "mountPath": "/run/xtables.lock"
            }
          ],
          "command": [
            "cilium-agent"
          ],
          "args": [
            "--config-dir=/tmp/cilium/config-map"
          ]
        },
        {
          "name": "apply-sysctl-overwrites",
          "category": "initContainers",
          "image": "registry.vcloud.example.com/quay.io/cilium/cilium:v1.20.2@sha256:2939231d0d3e3ebddcd80fffa168b7ddcc78fdf0dc864d1c8c126ff523c54f01",
          "securityContext": {
            "privileged": false,
            "allowPrivilegeEscalation": true,
            "runAsNonRoot": false,
            "runAsUser": null,
            "runAsGroup": null,
            "readOnlyRootFilesystem": false,
            "procMount": "Default",
            "appArmorProfile": {
              "type": "Unconfined"
            },
            "seccompProfile": {
              "type": "Unconfined"
            },
            "seLinuxOptions": {
              "level": "s0",
              "type": "spc_t"
            },
            "capabilities": {
              "add": [
                "SYS_ADMIN",
                "SYS_CHROOT",
                "SYS_PTRACE"
              ],
              "drop": [
                "ALL"
              ]
            }
          },
          "hostMounts": [
            {
              "readOnly": false,
              "mountPropagation": null,
              "subPath": "",
              "subPathExpr": "",
              "name": "cni-path",
              "mountPath": "/hostbin"
            },
            {
              "readOnly": false,
              "mountPropagation": null,
              "subPath": "",
              "subPathExpr": "",
              "name": "hostproc",
              "mountPath": "/hostproc"
            }
          ],
          "command": [
            "bash",
            "-ec",
            "cp /usr/bin/cilium-sysctlfix /hostbin/cilium-sysctlfix;\nnsenter --mount=/hostproc/1/ns/mnt \"${BIN_PATH}/cilium-sysctlfix\";\nrm /hostbin/cilium-sysctlfix\n"
          ],
          "args": []
        },
        {
          "name": "clean-cilium-state",
          "category": "initContainers",
          "image": "registry.vcloud.example.com/quay.io/cilium/cilium:v1.20.2@sha256:2939231d0d3e3ebddcd80fffa168b7ddcc78fdf0dc864d1c8c126ff523c54f01",
          "securityContext": {
            "privileged": false,
            "allowPrivilegeEscalation": true,
            "runAsNonRoot": false,
            "runAsUser": null,
            "runAsGroup": null,
            "readOnlyRootFilesystem": false,
            "procMount": "Default",
            "appArmorProfile": {
              "type": "Unconfined"
            },
            "seccompProfile": {
              "type": "Unconfined"
            },
            "seLinuxOptions": {
              "level": "s0",
              "type": "spc_t"
            },
            "capabilities": {
              "add": [
                "NET_ADMIN",
                "SYS_ADMIN",
                "SYS_MODULE",
                "SYS_RESOURCE"
              ],
              "drop": [
                "ALL"
              ]
            }
          },
          "hostMounts": [
            {
              "readOnly": false,
              "mountPropagation": null,
              "subPath": "",
              "subPathExpr": "",
              "name": "bpf-maps",
              "mountPath": "/sys/fs/bpf"
            },
            {
              "readOnly": false,
              "mountPropagation": "HostToContainer",
              "subPath": "",
              "subPathExpr": "",
              "name": "cilium-cgroup",
              "mountPath": "/sys/fs/cgroup"
            },
            {
              "readOnly": false,
              "mountPropagation": null,
              "subPath": "",
              "subPathExpr": "",
              "name": "cilium-run",
              "mountPath": "/var/run/cilium"
            }
          ],
          "command": [
            "/init-container.sh"
          ],
          "args": []
        },
        {
          "name": "config",
          "category": "initContainers",
          "image": "registry.vcloud.example.com/quay.io/cilium/cilium:v1.20.2@sha256:2939231d0d3e3ebddcd80fffa168b7ddcc78fdf0dc864d1c8c126ff523c54f01",
          "securityContext": {
            "privileged": false,
            "allowPrivilegeEscalation": true,
            "runAsNonRoot": false,
            "runAsUser": null,
            "runAsGroup": null,
            "readOnlyRootFilesystem": false,
            "procMount": "Default",
            "appArmorProfile": {
              "type": "Unconfined"
            },
            "seccompProfile": {
              "type": "Unconfined"
            },
            "capabilities": {
              "add": [
                "NET_ADMIN"
              ],
              "drop": [
                "ALL"
              ]
            }
          },
          "hostMounts": [],
          "command": [
            "cilium-dbg",
            "build-config",
            "--k8s-api-server-urls="
          ],
          "args": []
        },
        {
          "name": "install-cni-binaries",
          "category": "initContainers",
          "image": "registry.vcloud.example.com/quay.io/cilium/cilium:v1.20.2@sha256:2939231d0d3e3ebddcd80fffa168b7ddcc78fdf0dc864d1c8c126ff523c54f01",
          "securityContext": {
            "privileged": false,
            "allowPrivilegeEscalation": true,
            "runAsNonRoot": false,
            "runAsUser": null,
            "runAsGroup": null,
            "readOnlyRootFilesystem": false,
            "procMount": "Default",
            "appArmorProfile": {
              "type": "Unconfined"
            },
            "seccompProfile": {
              "type": "Unconfined"
            },
            "seLinuxOptions": {
              "level": "s0",
              "type": "spc_t"
            },
            "capabilities": {
              "add": [],
              "drop": [
                "ALL"
              ]
            }
          },
          "hostMounts": [
            {
              "readOnly": false,
              "mountPropagation": null,
              "subPath": "",
              "subPathExpr": "",
              "name": "cni-path",
              "mountPath": "/host/opt/cni/bin"
            }
          ],
          "command": [
            "/install-plugin.sh"
          ],
          "args": []
        }
      ]
    },
    "DaemonSet/kube-system/cilium-envoy": {
      "hostNetwork": true,
      "hostPID": false,
      "hostIPC": false,
      "hostPaths": [
        {
          "name": "envoy-artifacts",
          "hostPath": {
            "type": "DirectoryOrCreate",
            "path": "/var/run/cilium/envoy/artifacts"
          }
        },
        {
          "name": "envoy-sockets",
          "hostPath": {
            "type": "DirectoryOrCreate",
            "path": "/var/run/cilium/envoy/sockets"
          }
        }
      ],
      "containers": [
        {
          "name": "cilium-envoy",
          "category": "containers",
          "image": "registry.vcloud.example.com/quay.io/cilium/cilium-envoy:v1.37.6-1789133542-cbec91f666af0bf742da986d43832932dbb26b82@sha256:af7382699576b9e65e9184efa52eeca0b58aea70ad6e511bf260c91d9f740463",
          "securityContext": {
            "privileged": false,
            "allowPrivilegeEscalation": true,
            "runAsNonRoot": false,
            "runAsUser": null,
            "runAsGroup": null,
            "readOnlyRootFilesystem": false,
            "procMount": "Default",
            "appArmorProfile": {
              "type": "Unconfined"
            },
            "seLinuxOptions": {
              "level": "s0",
              "type": "spc_t"
            },
            "capabilities": {
              "add": [
                "NET_ADMIN",
                "SYS_ADMIN"
              ],
              "drop": [
                "ALL"
              ]
            }
          },
          "hostMounts": [
            {
              "readOnly": true,
              "mountPropagation": null,
              "subPath": "",
              "subPathExpr": "",
              "name": "envoy-artifacts",
              "mountPath": "/var/run/cilium/envoy/artifacts"
            },
            {
              "readOnly": false,
              "mountPropagation": null,
              "subPath": "",
              "subPathExpr": "",
              "name": "envoy-sockets",
              "mountPath": "/var/run/cilium/envoy/sockets"
            }
          ],
          "command": [
            "/usr/bin/cilium-envoy-starter"
          ],
          "args": [
            "--",
            "-c /var/run/cilium/envoy/bootstrap-config.json",
            "--base-id 0",
            "--log-level info"
          ]
        }
      ]
    },
    "Deployment/kube-system/cilium-operator": {
      "hostNetwork": true,
      "hostPID": false,
      "hostIPC": false,
      "hostPaths": [],
      "containers": [
        {
          "name": "cilium-operator",
          "category": "containers",
          "image": "registry.vcloud.example.com/quay.io/cilium/operator-generic:v1.20.2@sha256:64d8798350e8569b8e7622563fed6e44dce2625f311e4651b774816516c744fc",
          "securityContext": {
            "privileged": false,
            "allowPrivilegeEscalation": false,
            "runAsNonRoot": true,
            "runAsUser": 65532,
            "runAsGroup": 65532,
            "readOnlyRootFilesystem": false,
            "procMount": "Default",
            "seccompProfile": {
              "type": "RuntimeDefault"
            },
            "capabilities": {
              "add": [],
              "drop": [
                "ALL"
              ]
            }
          },
          "hostMounts": [],
          "command": [
            "cilium-operator-generic"
          ],
          "args": [
            "--config-dir=/tmp/cilium/config-map",
            "--debug=$(CILIUM_DEBUG)"
          ]
        }
      ]
    },
    "DaemonSet/kube-system/nvidia-device-plugin": {
      "hostNetwork": false,
      "hostPID": false,
      "hostIPC": false,
      "hostPaths": [
        {
          "name": "cdi-root",
          "hostPath": {
            "type": "DirectoryOrCreate",
            "path": "/var/run/cdi"
          }
        },
        {
          "name": "kubelet-device-plugins-dir",
          "hostPath": {
            "type": "Directory",
            "path": "/var/lib/kubelet/device-plugins"
          }
        },
        {
          "name": "mps-root",
          "hostPath": {
            "type": "DirectoryOrCreate",
            "path": "/run/nvidia/mps"
          }
        },
        {
          "name": "mps-shm",
          "hostPath": {
            "type": "",
            "path": "/run/nvidia/mps/shm"
          }
        }
      ],
      "containers": [
        {
          "name": "nvidia-device-plugin-ctr",
          "category": "containers",
          "image": "registry.vcloud.example.com/nvcr.io/nvidia/k8s-device-plugin:v0.20.1",
          "securityContext": {
            "privileged": false,
            "allowPrivilegeEscalation": false,
            "runAsNonRoot": false,
            "runAsUser": null,
            "runAsGroup": null,
            "readOnlyRootFilesystem": false,
            "procMount": "Default",
            "capabilities": {
              "add": [],
              "drop": [
                "ALL"
              ]
            }
          },
          "hostMounts": [
            {
              "readOnly": false,
              "mountPropagation": null,
              "subPath": "",
              "subPathExpr": "",
              "name": "cdi-root",
              "mountPath": "/var/run/cdi"
            },
            {
              "readOnly": false,
              "mountPropagation": null,
              "subPath": "",
              "subPathExpr": "",
              "name": "kubelet-device-plugins-dir",
              "mountPath": "/var/lib/kubelet/device-plugins"
            },
            {
              "readOnly": false,
              "mountPropagation": null,
              "subPath": "",
              "subPathExpr": "",
              "name": "mps-root",
              "mountPath": "/mps"
            },
            {
              "readOnly": false,
              "mountPropagation": null,
              "subPath": "",
              "subPathExpr": "",
              "name": "mps-shm",
              "mountPath": "/dev/shm"
            }
          ],
          "command": [
            "nvidia-device-plugin"
          ],
          "args": []
        }
      ]
    }
  },
  "controlPlane": {
    "Pod/kube-system/kube-apiserver": {
      "image": "registry.vcloud.example.com/registry.k8s.io/kube-apiserver:v1.36.5",
      "mounts": {
        "/etc/kubernetes/pki": {
          "readOnly": true,
          "type": "DirectoryOrCreate",
          "required": true
        },
        "/etc/ssl/certs": {
          "readOnly": true,
          "type": "DirectoryOrCreate",
          "required": true
        },
        "/etc/ca-certificates": {
          "readOnly": true,
          "type": "DirectoryOrCreate",
          "required": false
        },
        "/usr/share/ca-certificates": {
          "readOnly": true,
          "type": "DirectoryOrCreate",
          "required": false
        },
        "/usr/local/share/ca-certificates": {
          "readOnly": true,
          "type": "DirectoryOrCreate",
          "required": false
        },
        "/etc/pki/ca-trust": {
          "readOnly": true,
          "type": "DirectoryOrCreate",
          "required": false
        },
        "/etc/pki/tls/certs": {
          "readOnly": true,
          "type": "DirectoryOrCreate",
          "required": false
        }
      }
    },
    "Pod/kube-system/kube-controller-manager": {
      "image": "registry.vcloud.example.com/registry.k8s.io/kube-controller-manager:v1.36.5",
      "mounts": {
        "/etc/kubernetes/pki": {
          "readOnly": true,
          "type": "DirectoryOrCreate",
          "required": true
        },
        "/etc/ssl/certs": {
          "readOnly": true,
          "type": "DirectoryOrCreate",
          "required": true
        },
        "/etc/ca-certificates": {
          "readOnly": true,
          "type": "DirectoryOrCreate",
          "required": false
        },
        "/usr/share/ca-certificates": {
          "readOnly": true,
          "type": "DirectoryOrCreate",
          "required": false
        },
        "/usr/local/share/ca-certificates": {
          "readOnly": true,
          "type": "DirectoryOrCreate",
          "required": false
        },
        "/etc/pki/ca-trust": {
          "readOnly": true,
          "type": "DirectoryOrCreate",
          "required": false
        },
        "/etc/pki/tls/certs": {
          "readOnly": true,
          "type": "DirectoryOrCreate",
          "required": false
        },
        "/etc/kubernetes/controller-manager.conf": {
          "readOnly": true,
          "type": "FileOrCreate",
          "required": true
        }
      }
    },
    "Pod/kube-system/kube-scheduler": {
      "image": "registry.vcloud.example.com/registry.k8s.io/kube-scheduler:v1.36.5",
      "mounts": {
        "/etc/kubernetes/scheduler.conf": {
          "readOnly": true,
          "type": "FileOrCreate",
          "required": true
        }
      }
    },
    "Pod/kube-system/etcd": {
      "image": "registry.vcloud.example.com/registry.k8s.io/etcd:3.6.8-0",
      "mounts": {
        "/etc/kubernetes/pki/etcd": {
          "readOnly": true,
          "type": "DirectoryOrCreate",
          "required": true
        },
        "/var/lib/etcd": {
          "readOnly": false,
          "type": "DirectoryOrCreate",
          "required": true
        }
      }
    }
  }
}
VCLOUD_POLICY_JSON
    fi
}
# END GENERATED EXCEPTION POLICY

# BEGIN GENERATED POLICY CHECKER
render_policy_checker() {
    cat <<'VCLOUD_POLICY_PYTHON'
#!/usr/bin/env python3
"""Dependency-free manifest policy engine; shared by offline checks and host bootstrap."""
import argparse
import json
from pathlib import Path
import re
import sys


def flatten(objects):
    for obj in objects:
        if not obj:
            continue
        if obj.get('kind') == 'List':
            yield from flatten(obj.get('items', []))
        else:
            yield obj


def podspec(obj):
    if obj['kind'] == 'Pod':
        return obj.get('spec', {})
    if obj['kind'] == 'CronJob':
        return obj.get('spec', {}).get('jobTemplate', {}).get('spec', {}).get('template', {}).get('spec')
    return obj.get('spec', {}).get('template', {}).get('spec')


def security_context(context):
    defaults = dict(privileged=False, allowPrivilegeEscalation=True, runAsNonRoot=False,
                    runAsUser=None, runAsGroup=None, readOnlyRootFilesystem=False, procMount='Default')
    result = defaults | context
    caps = result.get('capabilities', {})
    result['capabilities'] = dict(add=sorted(caps.get('add', [])), drop=sorted(caps.get('drop', [])))
    return result


def mounts(values):
    return sorted([dict(readOnly=False, mountPropagation=None, subPath='', subPathExpr='') | v
                   for v in values], key=lambda v: v['name'])


def hostpaths(values):
    return sorted([dict(name=v['name'], hostPath=dict(type='') | v['hostPath'])
                   for v in values], key=lambda v: v['name'])


def pod_projection(obj):
    spec = podspec(obj)
    volumes = {v['name']: v for v in spec.get('volumes', []) if 'hostPath' in v}
    containers = []
    for category in ('containers', 'initContainers', 'ephemeralContainers'):
        for c in spec.get(category, []):
            containers.append(dict(name=c['name'], category=category, image=c.get('image', ''),
                command=c.get('command', []), args=c.get('args', []),
                securityContext=security_context(spec.get('securityContext', {}) | c.get('securityContext', {})),
                hostMounts=mounts([m for m in c.get('volumeMounts', []) if m['name'] in volumes])))
    return dict(hostNetwork=spec.get('hostNetwork', False), hostPID=spec.get('hostPID', False),
                hostIPC=spec.get('hostIPC', False), hostPaths=hostpaths(volumes.values()),
                containers=sorted(containers, key=lambda c: (c['category'], c['name'])))


def control_plane_problems(obj, expected):
    spec, issues = obj['spec'], []
    projection = pod_projection(obj)
    name = obj['metadata']['name']
    if not spec.get('hostNetwork') or spec.get('hostPID', False) or spec.get('hostIPC', False):
        issues.append('unapproved host namespace configuration')
    if spec.get('initContainers') or spec.get('ephemeralContainers') or len(spec.get('containers', [])) != 1:
        issues.append('unapproved control-plane container layout')
        return issues
    container = projection['containers'][0]
    if container['name'] != name or container['image'] != expected['image']:
        issues.append('unapproved control-plane container name/image')
    if not container['command'] or container['command'][0] != name or container['args']:
        issues.append('unapproved control-plane executable')
    sc = container['securityContext']
    allowed_keys = {'privileged', 'allowPrivilegeEscalation', 'runAsNonRoot', 'runAsUser', 'runAsGroup',
                    'readOnlyRootFilesystem', 'procMount', 'capabilities', 'seccompProfile'}
    if (set(sc) - allowed_keys or sc['privileged'] or sc['procMount'] != 'Default' or
            sc['capabilities']['add'] or sc['runAsUser'] not in (None, 0) or
            sc['runAsGroup'] not in (None, 0) or sc.get('seccompProfile') != {'type': 'RuntimeDefault'}):
        issues.append('unapproved control-plane security settings')
    allowed = expected['mounts']
    volumes = {v['name']: v['hostPath'] for v in projection['hostPaths']}
    seen = set()
    # No extra non-host volumes or mounts may hide a change in node interface usage.
    if len(volumes) != len(spec.get('volumes', [])):
        issues.append('unapproved control-plane volume type')
    for mount in container['hostMounts']:
        source = volumes[mount['name']]
        path = source['path']
        if path not in allowed:
            issues.append('unapproved control-plane host path: ' + path)
            continue
        rule = allowed[path]
        if (source['type'] != rule['type'] or mount['mountPath'] != path or
                mount['readOnly'] != rule['readOnly'] or mount['mountPropagation'] is not None or
                mount['subPath'] or mount['subPathExpr']):
            issues.append('unapproved access mode or target for ' + path)
        if path in seen:
            issues.append('duplicate control-plane host path: ' + path)
        seen.add(path)
    if len(container['hostMounts']) != len(spec['containers'][0].get('volumeMounts', [])):
        issues.append('unapproved control-plane mount')
    if len(container['hostMounts']) != len(volumes):
        issues.append('unmounted/duplicate control-plane host volume')
    for path, rule in allowed.items():
        if rule.get('required') and path not in seen:
            issues.append('missing required control-plane host path: ' + path)
    return issues


def audit_objects(objects, policy, mode='workloads'):
    registry = policy['registry']
    active = policy.get('status') == 'approved'
    agents = policy.get('agents', {}) if active else {}
    control = policy.get('controlPlane', {}) if active and mode == 'control-plane' else {}
    problems, inventory, accepted, seen = [], [], [], set()
    objects = list(flatten(objects))
    if not objects:
        problems.append('empty manifest input')
    for obj in objects:
        key = f"{obj.get('kind')}/{obj.get('metadata', {}).get('namespace', 'cluster')}/{obj.get('metadata', {}).get('name')}"
        if key in seen:
            problems.append(f'{key}: duplicate resource')
        seen.add(key)
        if re.search(r'/(v[0-9]+(?:alpha|beta)[0-9]+)$', obj.get('apiVersion', '')):
            problems.append(f'{key}: non-stable workload API')
        if obj.get('kind') == 'PersistentVolume':
            spec = obj.get('spec', {})
            if 'hostPath' in spec:
                problems.append(f'{key}: forbidden hostPath PV')
            if 'local' in spec and (not spec.get('nodeAffinity') or obj.get('metadata', {}).get('annotations', {}).get('vcloud.io/vetted', obj.get('metadata', {}).get('annotations', {}).get('twinfra.io/vetted')) != 'true'):
                problems.append(f'{key}: Local PV requires documented vetting and nodeAffinity')
            if 'local' in spec:
                # An annotation alone is not approval to expose an arbitrary host path.
                vetted = policy.get('localPVs', {}).get(obj['metadata']['name'])
                scope = {k: spec.get(k) for k in ('local', 'nodeAffinity', 'accessModes', 'volumeMode', 'storageClassName')}
                if vetted != scope:
                    problems.append(f'{key}: Local PV outside vetted storage allowlist')
            if 'local' not in spec and 'csi' not in spec:
                problems.append(f'{key}: persistent storage requires CSI or vetted Local PV')
        spec = podspec(obj)
        if spec is None:
            continue
        entry = dict(resource=key, **pod_projection(obj))
        inventory.append(entry)
        scoped = key in agents or key in control
        if key in agents and mode == 'workloads':
            expected = agents[key]
            actual = {k: v for k, v in entry.items() if k != 'resource'}
            if actual != expected:
                problems.append(f'{key}: drift from approved node-agent images/mounts/security/container layout')
            else:
                accepted.append(key)
        elif key in control:
            issues = control_plane_problems(obj, control[key])
            problems.extend(f'{key}: {issue}' for issue in issues)
            if not issues:
                accepted.append(key)
        elif mode == 'control-plane':
            problems.append(f'{key}: resource outside approved static control plane')
        else:
            if entry['hostPaths']:
                problems.append(f'{key}: forbidden hostPath volume(s)')
            if entry['hostNetwork'] or entry['hostPID'] or entry['hostIPC']:
                problems.append(f'{key}: host namespaces outside approved node scope')
        for c in entry['containers']:
            image, sc = c['image'], c['securityContext']
            if not image.startswith(registry + '/'):
                problems.append(f'{key}/{c["name"]}: image outside SSoT registry')
            if not re.search(r'@sha256:[a-f0-9]{64}$|:v?\d+\.\d+\.\d+(?:[._+-][A-Za-z0-9._+-]+)?$', image):
                problems.append(f'{key}/{c["name"]}: image is not pinned to a digest or semantic version')
            if sc['privileged']:
                problems.append(f'{key}/{c["name"]}: privileged containers prohibited')
            if not scoped and (sc['runAsUser'] == 0 or not sc['runAsNonRoot']):
                problems.append(f'{key}/{c["name"]}: root execution outside approved node scope')
            if not scoped and sc['capabilities']['add']:
                problems.append(f'{key}/{c["name"]}: added capabilities outside approved node scope')
    if mode == 'control-plane' and set(control) != seen:
        problems.append('control-plane input must contain exactly the four approved static Pods')
    return dict(status='blocked' if problems else 'passed', authorization=policy.get('approval', 'none'),
                violations=problems, acceptedExceptions=accepted, resources=inventory)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--policy', type=Path, required=True)
    parser.add_argument('--mode', choices=['workloads', 'control-plane'], default='workloads')
    args = parser.parse_args()
    result = audit_objects(json.load(sys.stdin), json.loads(args.policy.read_text()), args.mode)
    print(f'SSoT contract: {result["status"]}; {len(result["violations"])} findings', file=sys.stderr)
    for finding in result['violations']:
        print(finding, file=sys.stderr)
    return 1 if result['violations'] else 0


if __name__ == '__main__':
    raise SystemExit(main())
VCLOUD_POLICY_PYTHON
}
# END GENERATED POLICY CHECKER

validate_manifests() {
    local mode=$1
    shift
    kubeconform -strict -summary -kubernetes-version "${KUBERNETES_VERSION#v}" "$@"
    yq eval-all -o=json -I=0 '[.]' "$@" |
        python3 "$STATE_DIR/check-manifest-contract.py" --policy "$STATE_DIR/node-exceptions.json" --mode "$mode"
}

render_etcd_patch() {
    # kubeadm's default etcd certificate mount is writable; the approved scope is read-only.
    # This is a strategic merge PATCH fragment, not a standalone Kubernetes resource.
    cat <<'EOF'
spec:
  containers:
    - name: etcd
      volumeMounts:
        - name: etcd-certs
          readOnly: true
EOF
}

validate_static_control_plane() {
    local directory=$1
    local -a manifests=()
    local component entry
    # A fifth static Pod must not bypass the four-component exception by living next
    # to the checked files. Kubelet ignores dot files; every other entry is restricted.
    for entry in "$directory"/*; do
        [[ -e $entry || -L $entry ]] || continue
        case ${entry##*/} in
            kube-apiserver.yaml|kube-controller-manager.yaml|kube-scheduler.yaml|etcd.yaml)
                [[ -f $entry && ! -L $entry ]] || die "Unexpected static Pod file type: $entry";;
            *) die "Unapproved static Pod directory entry: $entry";;
        esac
    done
    for component in kube-apiserver kube-controller-manager kube-scheduler etcd; do
        [[ -s $directory/$component.yaml ]] || die "Missing static Pod manifest: $component"
        manifests+=("$directory/$component.yaml")
    done
    validate_manifests control-plane "${manifests[@]}"
}

validate_kubeadm_preview() {
    local preview
    preview=$(mktemp -d "$WORK_DIR/kubeadm-preview.XXXXXX")
    # Upstream kubeadm honors this variable for dry-run output. Only manifest-generation
    # phases run here; they do not start kubelet or create a cluster.
    KUBEADM_INIT_DRYRUN_DIR="$preview" kubeadm init phase control-plane all --config "$STATE_DIR/kubeadm.yaml" --dry-run
    KUBEADM_INIT_DRYRUN_DIR="$preview" kubeadm init phase etcd local --config "$STATE_DIR/kubeadm.yaml" --dry-run
    validate_static_control_plane "$preview"
}

# BEGIN GENERATED FOUNDATION
render_foundation() {
    if [[ $PLATFORM_PROFILE == dev-* ]]; then
        cat <<'EOF'
apiVersion: v1
kind: Namespace
metadata:
  name: twinfra-platform-services
  labels:
    twinfra.io/managed: 'true'
    pod-security.kubernetes.io/enforce: restricted
    pod-security.kubernetes.io/enforce-version: v1.30
    pod-security.kubernetes.io/audit: restricted
    pod-security.kubernetes.io/audit-version: v1.30
    pod-security.kubernetes.io/warn: restricted
    pod-security.kubernetes.io/warn-version: v1.30
---
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: twinfra-default-deny
  namespace: twinfra-platform-services
  labels: {}
spec:
  podSelector: {}
  policyTypes:
  - Ingress
  - Egress
  ingress: []
  egress: []
---
apiVersion: v1
kind: Namespace
metadata:
  name: twinfra-workload-apps
  labels:
    twinfra.io/managed: 'true'
    pod-security.kubernetes.io/enforce: restricted
    pod-security.kubernetes.io/enforce-version: v1.30
    pod-security.kubernetes.io/audit: restricted
    pod-security.kubernetes.io/audit-version: v1.30
    pod-security.kubernetes.io/warn: restricted
    pod-security.kubernetes.io/warn-version: v1.30
---
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: twinfra-default-deny
  namespace: twinfra-workload-apps
  labels: {}
spec:
  podSelector: {}
  policyTypes:
  - Ingress
  - Egress
  ingress: []
  egress: []
---
apiVersion: v1
kind: Namespace
metadata:
  name: twinfra-hpc-compute
  labels:
    twinfra.io/managed: 'true'
    pod-security.kubernetes.io/enforce: restricted
    pod-security.kubernetes.io/enforce-version: v1.30
    pod-security.kubernetes.io/audit: restricted
    pod-security.kubernetes.io/audit-version: v1.30
    pod-security.kubernetes.io/warn: restricted
    pod-security.kubernetes.io/warn-version: v1.30
---
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: twinfra-default-deny
  namespace: twinfra-hpc-compute
  labels: {}
spec:
  podSelector: {}
  policyTypes:
  - Ingress
  - Egress
  ingress: []
  egress: []
EOF
    else
    cat <<'EOF'
# Generated from vcloud-ssot.yaml by tools/render_ssot.py.
apiVersion: v1
kind: Namespace
metadata:
  name: platform-services
  labels:
    vcloud.io/managed: 'true'
    pod-security.kubernetes.io/enforce: restricted
    pod-security.kubernetes.io/enforce-version: v1.30
    pod-security.kubernetes.io/audit: restricted
    pod-security.kubernetes.io/audit-version: v1.30
    pod-security.kubernetes.io/warn: restricted
    pod-security.kubernetes.io/warn-version: v1.30
  annotations:
    vcloud.io/cluster: vCloud-prod-01
    vcloud.io/base-domain: vcloud.example.com
    vcloud.io/gitops-repository: amazen33/twinfra
---
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: default-deny-all
  namespace: platform-services
spec:
  podSelector: {}
  policyTypes:
  - Ingress
  - Egress
  ingress: []
  egress: []
---
apiVersion: v1
kind: Namespace
metadata:
  name: workload-apps
  labels:
    vcloud.io/managed: 'true'
    pod-security.kubernetes.io/enforce: restricted
    pod-security.kubernetes.io/enforce-version: v1.30
    pod-security.kubernetes.io/audit: restricted
    pod-security.kubernetes.io/audit-version: v1.30
    pod-security.kubernetes.io/warn: restricted
    pod-security.kubernetes.io/warn-version: v1.30
  annotations:
    vcloud.io/cluster: vCloud-prod-01
    vcloud.io/base-domain: vcloud.example.com
    vcloud.io/gitops-repository: amazen33/twinfra
---
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: default-deny-all
  namespace: workload-apps
spec:
  podSelector: {}
  policyTypes:
  - Ingress
  - Egress
  ingress: []
  egress: []
---
apiVersion: v1
kind: Namespace
metadata:
  name: hpc-compute
  labels:
    vcloud.io/managed: 'true'
    pod-security.kubernetes.io/enforce: restricted
    pod-security.kubernetes.io/enforce-version: v1.30
    pod-security.kubernetes.io/audit: restricted
    pod-security.kubernetes.io/audit-version: v1.30
    pod-security.kubernetes.io/warn: restricted
    pod-security.kubernetes.io/warn-version: v1.30
  annotations:
    vcloud.io/cluster: vCloud-prod-01
    vcloud.io/base-domain: vcloud.example.com
    vcloud.io/gitops-repository: amazen33/twinfra
---
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: default-deny-all
  namespace: hpc-compute
spec:
  podSelector: {}
  policyTypes:
  - Ingress
  - Egress
  ingress: []
  egress: []
EOF
    fi
}
# END GENERATED FOUNDATION

render_gpu_runtime_class() {
    cat <<'EOF'
apiVersion: node.k8s.io/v1
kind: RuntimeClass
metadata:
  name: nvidia
handler: nvidia
EOF
}

# Render ephemeral, isolated acceptance objects. The denied job only runs after the
# allowed job proves the server/DNS work, so an unreachable server cannot produce a
# false positive for policy enforcement. The trap removes only this dedicated namespace.
render_smoke() {
    cat <<EOF
apiVersion: v1
kind: Namespace
metadata:
  name: vcloud-host-validation
  labels:
    vcloud.io/owner: host-bootstrap
---
apiVersion: v1
kind: Pod
metadata:
  name: server
  namespace: vcloud-host-validation
  labels: {role: server}
spec:
  automountServiceAccountToken: false
  securityContext:
    runAsNonRoot: true
    runAsUser: 10001
    runAsGroup: 10001
    fsGroup: 10001
    seccompProfile: {type: RuntimeDefault}
  containers:
    - name: http
      image: "$REGISTRY_PROBE_IMAGE"
      command: [sh, -c, 'mkdir -p /tmp/www; echo vcloud-ok > /tmp/www/index.html; httpd -f -p 8080 -h /tmp/www']
      securityContext:
        allowPrivilegeEscalation: false
        readOnlyRootFilesystem: true
        capabilities: {drop: [ALL]}
      volumeMounts: [{name: scratch, mountPath: /tmp}]
      readinessProbe:
        tcpSocket: {port: 8080}
      resources:
        requests: {cpu: 10m, memory: 16Mi}
        limits: {memory: 64Mi}
  volumes: [{name: scratch, emptyDir: {sizeLimit: 16Mi}}]
---
apiVersion: v1
kind: Service
metadata: {name: server, namespace: vcloud-host-validation}
spec:
  selector: {role: server}
  ports: [{port: 80, targetPort: 8080}]
---
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata: {name: deny-all, namespace: vcloud-host-validation}
spec:
  podSelector: {}
  policyTypes: [Ingress, Egress]
---
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata: {name: client-egress, namespace: vcloud-host-validation}
spec:
  podSelector: {matchLabels: {role: client}}
  policyTypes: [Egress]
  egress:
    - to:
        - namespaceSelector: {matchLabels: {kubernetes.io/metadata.name: kube-system}}
          podSelector: {matchLabels: {k8s-app: kube-dns}}
      ports: [{protocol: UDP, port: 53}, {protocol: TCP, port: 53}]
    - to: [{podSelector: {matchLabels: {role: server}}}]
      ports: [{protocol: TCP, port: 8080}]
---
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata: {name: server-ingress, namespace: vcloud-host-validation}
spec:
  podSelector: {matchLabels: {role: server}}
  policyTypes: [Ingress]
  ingress:
    - from: [{podSelector: {matchLabels: {role: client, access: allowed}}}]
      ports: [{protocol: TCP, port: 8080}]
EOF
}

render_probe_job() {
    local access=$1 command
    if [[ $access == allowed ]]; then
        command='nslookup kubernetes.default.svc.cluster.local && wget -T 10 -O - http://server | grep -q vcloud-ok'
    else
        command='nslookup server && if wget -T 5 -O /dev/null http://server; then echo POLICY_NOT_ENFORCED; exit 1; fi'
    fi
    cat <<EOF
apiVersion: batch/v1
kind: Job
metadata: {name: $access, namespace: vcloud-host-validation}
spec:
  backoffLimit: 0
  activeDeadlineSeconds: 120
  template:
    metadata:
      labels: {role: client, access: $access}
    spec:
      restartPolicy: Never
      automountServiceAccountToken: false
      securityContext:
        runAsNonRoot: true
        runAsUser: 10001
        runAsGroup: 10001
        seccompProfile: {type: RuntimeDefault}
      containers:
        - name: probe
          image: "$REGISTRY_PROBE_IMAGE"
          command: [sh, -ec, '$command']
          securityContext:
            allowPrivilegeEscalation: false
            readOnlyRootFilesystem: true
            capabilities: {drop: [ALL]}
          resources:
            requests: {cpu: 10m, memory: 16Mi}
            limits: {memory: 64Mi}
EOF
}

render_hugepage_job() {
    # mmap, rather than dd/write(2), is required for hugetlbfs files. Allocate one page
    # from each requested pool; touching byte zero commits that entire HugeTLB page.
    local size count resource volume
    cat <<EOF
apiVersion: batch/v1
kind: Job
metadata: {name: hugepages, namespace: vcloud-host-validation}
spec:
  backoffLimit: 0
  activeDeadlineSeconds: 180
  template:
    spec:
      restartPolicy: Never
      automountServiceAccountToken: false
      securityContext:
        runAsNonRoot: true
        runAsUser: 10001
        runAsGroup: 10001
        fsGroup: 10001
        seccompProfile: {type: RuntimeDefault}
      containers:
        - name: probe
          image: "$HUGEPAGE_SMOKE_IMAGE"
          securityContext:
            allowPrivilegeEscalation: false
            readOnlyRootFilesystem: true
            capabilities: {drop: [ALL]}
          command:
            - python3
            - -c
            - |
              import mmap, os
              for root, size in [("/huge-2M", 2*1024**2), ("/huge-1G", 1024**3)]:
                  if not os.path.isdir(root):
                      continue
                  with open(root + "/probe", "w+b") as f:
                      f.truncate(size)
                      with mmap.mmap(f.fileno(), size) as mapping:
                          mapping[0] = 42
                          assert mapping[0] == 42
                  print(root, "mmap allocation passed", flush=True)
          resources:
            requests:
              cpu: 10m
              memory: 64Mi
EOF
    for size in 2M 1G; do
        if [[ $size == 2M ]]; then count=$HUGEPAGES_2M; resource=2Mi; else count=$HUGEPAGES_1G; resource=1Gi; fi
        ((count > 0)) || continue
        printf '              hugepages-%s: %s\n' "$resource" "$resource"
    done
    cat <<'EOF'
            limits:
              memory: 256Mi
EOF
    for size in 2M 1G; do
        if [[ $size == 2M ]]; then count=$HUGEPAGES_2M; resource=2Mi; else count=$HUGEPAGES_1G; resource=1Gi; fi
        ((count > 0)) || continue
        printf '              hugepages-%s: %s\n' "$resource" "$resource"
    done
    printf '          volumeMounts:\n'
    for size in 2M 1G; do
        if [[ $size == 2M ]]; then count=$HUGEPAGES_2M; else count=$HUGEPAGES_1G; fi
        ((count > 0)) || continue
        volume="huge-${size,,}"
        printf '            - {name: %s, mountPath: /huge-%s}\n' "$volume" "$size"
    done
    printf '      volumes:\n'
    for size in 2M 1G; do
        if [[ $size == 2M ]]; then count=$HUGEPAGES_2M; resource=2Mi; else count=$HUGEPAGES_1G; resource=1Gi; fi
        ((count > 0)) || continue
        volume="huge-${size,,}"
        printf '        - name: %s\n          emptyDir: {medium: HugePages-%s}\n' "$volume" "$resource"
    done
}

render_gpu_job() {
    [[ $GPU_SMOKE_TEST == true ]] || return 0
    cat <<EOF
apiVersion: batch/v1
kind: Job
metadata: {name: gpu, namespace: vcloud-host-validation}
spec:
  backoffLimit: 0
  activeDeadlineSeconds: 180
  template:
    spec:
      restartPolicy: Never
      runtimeClassName: nvidia
      automountServiceAccountToken: false
      securityContext:
        runAsNonRoot: true
        runAsUser: 10001
        runAsGroup: 10001
        seccompProfile: {type: RuntimeDefault}
      containers:
        - name: probe
          image: "$GPU_SMOKE_IMAGE"
          command: [nvidia-smi]
          securityContext:
            allowPrivilegeEscalation: false
            readOnlyRootFilesystem: true
            capabilities: {drop: [ALL]}
          resources:
            limits: {nvidia.com/gpu: 1, memory: 256Mi}
EOF
}

cleanup_smoke() {
    if [[ ${SMOKE_OWNED:-false} == true ]]; then
        kubectl delete namespace vcloud-host-validation --wait=true --timeout=120s || true
        SMOKE_OWNED=false
    fi
}

run_smoke_tests() {
    [[ $BOOTSTRAP_K8S == true && $RUN_SMOKE_TESTS == true ]] || return
    PHASE=cluster-smoke
    if kubectl get namespace vcloud-host-validation >/dev/null 2>&1; then
        [[ $(kubectl get namespace vcloud-host-validation -o jsonpath='{.metadata.labels.vcloud\.io/owner}') == host-bootstrap ]] || die 'Validation namespace is owned by another user'
        kubectl delete namespace vcloud-host-validation --wait=true --timeout=120s
    fi
    SMOKE_OWNED=true
    render_smoke > "$STATE_DIR/smoke-base.yaml"
    validate_manifests workloads "$STATE_DIR/smoke-base.yaml"
    kubectl apply -f "$STATE_DIR/smoke-base.yaml"
    kubectl -n vcloud-host-validation wait --for=condition=Ready pod/server --timeout=120s
    local access
    for access in allowed denied; do
        render_probe_job "$access" > "$STATE_DIR/smoke-$access.yaml"
        validate_manifests workloads "$STATE_DIR/smoke-$access.yaml"
        kubectl apply -f "$STATE_DIR/smoke-$access.yaml"
        kubectl -n vcloud-host-validation wait --for=condition=complete "job/$access" --timeout=150s
        kubectl -n vcloud-host-validation logs "job/$access"
    done
    if ((HUGEPAGES_2M > 0 || HUGEPAGES_1G > 0)); then
        render_hugepage_job > "$STATE_DIR/smoke-hugepages.yaml"
        validate_manifests workloads "$STATE_DIR/smoke-hugepages.yaml"
        kubectl apply -f "$STATE_DIR/smoke-hugepages.yaml"
        kubectl -n vcloud-host-validation wait --for=condition=complete job/hugepages --timeout=210s
        kubectl -n vcloud-host-validation logs job/hugepages
    fi
    if [[ $GPU_ENABLED == true && $GPU_SMOKE_TEST == true ]]; then
        render_gpu_job > "$STATE_DIR/smoke-gpu.yaml"
        validate_manifests workloads "$STATE_DIR/smoke-gpu.yaml"
        kubectl apply -f "$STATE_DIR/smoke-gpu.yaml"
        kubectl -n vcloud-host-validation wait --for=condition=complete job/gpu --timeout=210s
        kubectl -n vcloud-host-validation logs job/gpu
    fi
    cleanup_smoke
}

validate_host() {
    PHASE=validation
    validate_kernel
    [[ $(stat -fc '%T' /sys/fs/cgroup) == cgroup2fs ]] || die 'cgroup v2 is not active'
    local controller
    for controller in cpu cpuset memory pids hugetlb; do
        grep -qw "$controller" /sys/fs/cgroup/cgroup.controllers || die "Missing cgroup v2 controller: $controller"
    done
    [[ $(findmnt -n -o FSTYPE --target /sys/fs/bpf) == bpf ]] || die 'bpffs is not mounted'
    grep -qw overlay /proc/filesystems || die 'overlayfs unavailable'
    [[ $(wc -l < /proc/swaps) -eq 1 ]] || die 'Swap is still active'
    local key expected actual size count
    while read -r key _ expected; do
        [[ $key == \#* || -z $key ]] && continue
        [[ $(sysctl -n "$key") == "$expected" ]] || die "Sysctl mismatch: $key"
    done < /etc/sysctl.d/99-vcloud.conf
    for size in 2048 1048576; do
        if [[ $size == 2048 ]]; then count=$HUGEPAGES_2M; else count=$HUGEPAGES_1G; fi
        ((count == 0)) && continue
        actual=$(cat "/sys/kernel/mm/hugepages/hugepages-${size}kB/nr_hugepages")
        ((actual >= count)) || die "${size}kB pool insufficient"
        if [[ $size == 2048 ]]; then
            [[ $(findmnt -n -o FSTYPE --target /dev/hugepages-2M) == hugetlbfs ]] || die '2 MiB host HugeTLB mount missing'
        else
            [[ $(findmnt -n -o FSTYPE --target /dev/hugepages-1G) == hugetlbfs ]] || die '1 GiB host HugeTLB mount missing'
        fi
    done
    systemctl is-active --quiet containerd || die 'containerd is not active'
    crictl info | jq -e '.status.conditions[] | select(.type == "RuntimeReady") | .status == true' >/dev/null
    python3 - /etc/containerd/config.toml <<'PY'
import sys, toml
data = toml.load(sys.argv[1])
plugins = data['plugins']
runtime = plugins.get('io.containerd.cri.v1.runtime', plugins.get('io.containerd.grpc.v1.cri'))
assert runtime is not None, 'Missing CRI runtime plugin'
for name, settings in runtime['containerd']['runtimes'].items():
    assert settings['options']['SystemdCgroup'] is True, name + ' does not use systemd cgroups'
assert 'cri' not in data.get('disabled_plugins', []), 'CRI is disabled'
PY
    kubectl version --client; kubeadm version -o short; helm version --short; cilium version --client
    kubeconform -v; tkn version --client; argocd version --client; yq --version; jq --version
    if [[ $INSTALL_HPC == true ]]; then
        mpirun --version; ucx_info -v; apptainer --version; srun --version
    fi
    if [[ $GPU_ENABLED == true ]]; then
        nvidia-smi
        nvidia-ctk --version
        version_at_least "$(nvidia-smi --query-gpu=driver_version --format=csv,noheader | head -n1)" 550 || die 'Driver < 550'
    fi
    if [[ $BOOTSTRAP_K8S == true ]]; then
        check_policy_gate || return $?
        # Validation checks current policy/compiler bytes without modifying the host.
        cmp -s "$STATE_DIR/node-exceptions.json" <(render_exception_policy) || die 'Installed node exception policy drift'
        cmp -s "$STATE_DIR/check-manifest-contract.py" <(render_policy_checker) || die 'Installed manifest checker drift'
        validate_static_control_plane /etc/kubernetes/manifests
        export KUBECONFIG=/etc/kubernetes/admin.conf
        kubectl --request-timeout=30s get --raw=/readyz >/dev/null
        kubectl wait --for=condition=Ready "node/$NODE_NAME" --timeout=300s
        [[ $(kubectl -n kube-system get daemonset -o json | jq '[.items[] | select(.metadata.name == "kube-proxy" or (.metadata.name | contains("flannel")))] | length') == 0 ]] || die 'Unexpected kube-proxy/Flannel daemonset'
        cilium status --wait --wait-duration 5m
        kubectl -n kube-system get daemonset/cilium daemonset/cilium-envoy deployment/cilium-operator -o json |
            python3 "$STATE_DIR/check-manifest-contract.py" --policy "$STATE_DIR/node-exceptions.json"
        [[ $(kubectl -n kube-system get configmap cilium-config -o jsonpath='{.data.kube-proxy-replacement}') == true ]] || die 'Cilium kube-proxy replacement is not enabled'
        # Verify kubelet registered both pool sizes as schedulable resources.
        kubectl get node "$NODE_NAME" -o json | python3 -c '
import json, sys
capacity = json.load(sys.stdin)["status"]["capacity"]
def mib(s):
    for suffix, scale in [("Gi",1024), ("Mi",1), ("Ki",1/1024)]:
        if s.endswith(suffix): return float(s[:-len(suffix)]) * scale
    return int(s)/(1024*1024)
for name, required in [("hugepages-2Mi",int(sys.argv[1])*2), ("hugepages-1Gi",int(sys.argv[2])*1024)]:
    assert mib(capacity.get(name,"0")) >= required, name + " capacity is insufficient"
' "$HUGEPAGES_2M" "$HUGEPAGES_1G"
        if [[ $GPU_ENABLED == true ]]; then
            kubectl -n kube-system get daemonset/nvidia-device-plugin -o json |
                python3 "$STATE_DIR/check-manifest-contract.py" --policy "$STATE_DIR/node-exceptions.json"
            kubectl get node "$NODE_NAME" -o json | jq -e '.status.allocatable["nvidia.com/gpu"] | tonumber > 0' >/dev/null
        fi
    fi
    log 'Requested host and readiness gates passed. Deployment/performance gates are listed in the runbook.'
}

write_result() {
    jq -n --arg status "$1" --arg phase "$PHASE" --arg kernel "$(uname -r)" \
        --arg kubernetes "$KUBERNETES_VERSION" --arg cilium "$CILIUM_VERSION" \
        --arg mirror "$MIRROR_STATUS" --argjson mirror_required "$MIRROR_REQUIRED" \
        --argjson gpu "$GPU_ENABLED" --argjson bootstrap "$BOOTSTRAP_K8S" --argjson smoke "$RUN_SMOKE_TESTS" \
        '{status:$status,phase:$phase,kernel:$kernel,kubernetes:$kubernetes,cilium:$cilium,gpu_detected:$gpu,bootstrap_requested:$bootstrap,smoke_requested:$smoke,mirror_status:$mirror,mirror_required:$mirror_required}' \
        > "$STATE_DIR/result.json"
}

cleanup() {
    cleanup_smoke
    # mktemp's private work directory is always inside our fixed state directory.
    if [[ -n $WORK_DIR && $WORK_DIR == "$STATE_DIR"/work.* && -d $WORK_DIR ]]; then rm -rf -- "$WORK_DIR"; fi
}

on_error() {
    local code=$1 line=$2
    trap - ERR
    log "Failed in phase $PHASE at line $line (exit $code). Inspect the journal; no automatic reset." >&2
    if command -v jq >/dev/null && [[ -d $STATE_DIR ]]; then write_result failed || true; fi
    exit "$code"
}

main() {
    set -Eeuo pipefail
    export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
    load_config
    case ${1:---plan} in
        --plan) validate_config; plan; return;;
        --apply|--validate) ;;
        *) bad_config 'Usage: --plan, --apply or --validate';;
    esac
    validate_config
    # Reject version drift from the approved node exception before preflight or APT.
    if [[ $1 == --apply ]]; then check_policy_gate || return $?; fi
    preflight
    if [[ $1 == --validate ]]; then validate_host; return; fi
    umask 022
    mkdir -p "$STATE_DIR"
    chmod 0700 "$STATE_DIR"
    exec 9> "$STATE_DIR/bootstrap.lock"
    flock -n 9 || die 'Another bootstrap is running'
    WORK_DIR=$(mktemp -d "$STATE_DIR/work.XXXXXX")
    APPLY_ACTIVE=true
    trap 'on_error $? $LINENO' ERR
    trap cleanup EXIT
    # Preserve a same-boot pending request; never claim readiness by rerunning before reboot.
    if [[ -f $STATE_DIR/reboot-boot-id ]] &&
        [[ $(cat "$STATE_DIR/reboot-boot-id") == "$(cat /proc/sys/kernel/random/boot_id)" ]]; then
        NEEDS_REBOOT=true
    else
        [[ ! -f $STATE_DIR/reboot-boot-id ]] || REBOOT_ATTEMPTED=true
        rm -f "$STATE_DIR/reboot-required" "$STATE_DIR/reboot-boot-id"
    fi
    rm -f "$STATE_DIR/complete"
    export DEBIAN_FRONTEND=noninteractive
    apt-get -o DPkg::Lock::Timeout=300 update
    install_missing ca-certificates curl gnupg jq python3 python3-toml pciutils \
        software-properties-common apt-transport-https conntrack iptables socat ethtool iproute2 util-linux
    add-apt-repository -y universe
    apt-get update
    install_missing containerd runc
    # Ubuntu's package may start containerd with its packaged default config. Record
    # ownership now so the post-reboot preflight recognizes that installation.
    touch "$STATE_DIR/containerd-owned"
    prepare_kernel
    prepare_memory_network
    install_gpu
    install_tooling
    install_kubernetes_packages
    install_hpc_kvm
    if [[ $NEEDS_REBOOT == true ]]; then
        write_result reboot-required
        log 'Reboot Ubuntu, then rerun --apply. Kubernetes initialization was deferred.'
        exit 20
    fi
    configure_containerd
    bootstrap_kubernetes
    validate_host
    run_smoke_tests
    dpkg-query -W -f='${Package}\t${Version}\n' > "$STATE_DIR/package-versions.tsv"
    write_result ready
    touch "$STATE_DIR/complete"
}

if [[ ${BASH_SOURCE[0]} == "$0" ]]; then main "$@"; fi
