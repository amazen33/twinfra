#!/usr/bin/env bash
# Bootstrap lab serving certificates without writing private keys into Git.
# Only /run temporary files and in-cluster Secrets hold private material.
set -euo pipefail
umask 077
export KUBECONFIG=/etc/vcloud-wsl/kubeconfig.yaml
kubectl() { /usr/local/bin/k3s kubectl --context vcloud-wsl-local "$@"; }
[[ $EUID == 0 && -f /var/lib/vcloud-wsl/owner.json ]] || exit 1
for entry in platform-services/argocd-repo-server-tls/argocd-repo-server kube-system/vcloud-metrics-tls/metrics-server; do
    IFS=/ read -r namespace secret service <<< "$entry"
    if kubectl get secret "$secret" -n "$namespace" > /dev/null 2>&1; then continue; fi
    TEMPORARY=$(mktemp -d /run/vcloud-wsl-tls.XXXXXX)
    openssl req -x509 -newkey rsa:2048 -nodes -days 30 -subj /CN=vcloud-wsl-local-CA -keyout "$TEMPORARY/ca.key" -out "$TEMPORARY/ca.crt" > /dev/null 2>&1
    openssl req -newkey rsa:2048 -nodes -subj "/CN=$service.$namespace.svc" -keyout "$TEMPORARY/tls.key" -out "$TEMPORARY/tls.csr" > /dev/null 2>&1
    printf 'subjectAltName=DNS:%s,DNS:%s.%s,DNS:%s.%s.svc,DNS:%s.%s.svc.cluster.local\n' "$service" "$service" "$namespace" "$service" "$namespace" "$service" "$namespace" > "$TEMPORARY/extensions"
    openssl x509 -req -in "$TEMPORARY/tls.csr" -CA "$TEMPORARY/ca.crt" -CAkey "$TEMPORARY/ca.key" -CAcreateserial -days 30 -extfile "$TEMPORARY/extensions" -out "$TEMPORARY/tls.crt" > /dev/null 2>&1
    kubectl create secret generic "$secret" -n "$namespace" --from-file="tls.crt=$TEMPORARY/tls.crt" --from-file="tls.key=$TEMPORARY/tls.key" --from-file="ca.crt=$TEMPORARY/ca.crt" --dry-run=client -o json | kubectl apply -f - > /dev/null
    rm -- "$TEMPORARY/ca.key" "$TEMPORARY/ca.crt" "$TEMPORARY/ca.srl" "$TEMPORARY/tls.key" "$TEMPORARY/tls.csr" "$TEMPORARY/tls.crt" "$TEMPORARY/extensions"
    rmdir "$TEMPORARY"
done
if ! kubectl get secret argocd-redis -n platform-services > /dev/null 2>&1; then
    TEMPORARY=$(mktemp /run/vcloud-wsl-redis.XXXXXX)
    openssl rand -hex 32 | tr -d '\n' > "$TEMPORARY"
    kubectl create secret generic argocd-redis -n platform-services --from-file="auth=$TEMPORARY" --dry-run=client -o json | kubectl apply -f - > /dev/null
    rm -- "$TEMPORARY"
fi
kubectl create configmap vcloud-kubelet-trust -n kube-system --from-file=kubelet-ca.crt=/var/lib/rancher/k3s/server/tls/server-ca.crt --dry-run=client -o json | kubectl apply -f - > /dev/null
printf 'Lab serving TLS and kubelet CA trust prepared; private values remain outside Git.\n'
