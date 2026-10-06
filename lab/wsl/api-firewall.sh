#!/usr/bin/env bash
# Required host-level boundary for the mirrored-network local API. Never flush
# global rules: only this profile's dedicated chain is reconciled. IPv6 has no
# cluster PodCIDR; only loopback is allowed there.
set -euo pipefail
for tool in iptables ip6tables; do
    if [[ ${1:-} == --check ]]; then
        "$tool" -w -C INPUT -p tcp --dport 16443 -j VCLOUD_WSL_API
        "$tool" -w -C VCLOUD_WSL_API -i lo -j ACCEPT
        "$tool" -w -C VCLOUD_WSL_API -j DROP
        continue
    fi
    # Remove only this bootstrap's initial failed-port jump; keep other rules.
    if "$tool" -w -C INPUT -p tcp --dport 6443 -j VCLOUD_WSL_API 2>/dev/null; then
        "$tool" -w -D INPUT -p tcp --dport 6443 -j VCLOUD_WSL_API
    fi
    "$tool" -w -S VCLOUD_WSL_API > /dev/null 2>&1 || "$tool" -w -N VCLOUD_WSL_API
    "$tool" -w -F VCLOUD_WSL_API
    "$tool" -w -A VCLOUD_WSL_API -i lo -j ACCEPT
    if [[ $tool == iptables ]]; then "$tool" -w -A VCLOUD_WSL_API -s 10.42.0.0/16 -j ACCEPT; fi
    "$tool" -w -A VCLOUD_WSL_API -j DROP
    "$tool" -w -C INPUT -p tcp --dport 16443 -j VCLOUD_WSL_API 2>/dev/null || \
        "$tool" -w -I INPUT 1 -p tcp --dport 16443 -j VCLOUD_WSL_API
done
if [[ ${1:-} != --check ]]; then
    sysctl -w net.ipv4.ip_forward=1
    mountpoint -q /sys/fs/bpf || mount -t bpf bpf /sys/fs/bpf
fi
