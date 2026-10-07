#!/usr/bin/env bash
# Fail closed on the actual AWS backend; a generic gateway HTTP 200 is insufficient.
set -euo pipefail
here=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
root=$(cd -- "$here/../../.." && pwd)
for tool in kubectl jq curl ip; do
  command -v "$tool" >/dev/null || { echo "Missing dependency: $tool" >&2; exit 1; }
done
[[ ${EUID} -eq 0 && $(uname -r) == *microsoft* && -f /var/lib/vcloud-wsl/owner.json ]] || { echo 'Refusing verification outside the owned WSL lab' >&2; exit 1; }
export KUBECONFIG=/etc/vcloud-wsl/kubeconfig.yaml
k() { kubectl --context=vcloud-wsl-local --request-timeout=30s "$@"; }
mkdir -p "$root/.build/localstack"
k get nodes -o json | jq -e '.items | length==1 and .[0].metadata.name=="vcloud-wsl-local"' >/dev/null
k get namespace platform-services -o json | jq -e '.metadata.labels["pod-security.kubernetes.io/enforce"]=="restricted" and .metadata.labels["pod-security.kubernetes.io/enforce-version"]=="v1.30"' >/dev/null
k -n platform-services rollout status deployment/localstack-aws-console --timeout=300s
k -n platform-services get pods -l app.kubernetes.io/name=localstack-aws-console -o json > "$root/.build/localstack/pods.json"
jq -e '.items | length==1 and all(.[];
  .spec.securityContext.runAsNonRoot==true and .spec.securityContext.runAsUser>0 and
  .spec.securityContext.seccompProfile.type=="RuntimeDefault" and
  all(.spec.containers[]; .securityContext.runAsNonRoot==true and
    .securityContext.allowPrivilegeEscalation==false and
    .securityContext.capabilities.drop==["ALL"] and
    .securityContext.seccompProfile.type=="RuntimeDefault") and
  all(.status.containerStatuses[]; .ready==true))' "$root/.build/localstack/pods.json" >/dev/null
# Fake, process-local test credentials never reach a real AWS endpoint.
k -n platform-services exec -i deployment/localstack-aws-console -- python - < "$here/test-api.py" | tee "$root/.build/localstack/api-operations.json"
bash "$here/access.sh"
curl --fail --silent --show-error --retry 15 --retry-connrefused --retry-delay 1 --max-time 5 \
  http://127.0.0.1:4566/_localstack/health > "$root/.build/localstack/direct-health.json"
jq -e '.services | [.s3,.ec2,.iam,.dynamodb] | all(.=="running")' "$root/.build/localstack/direct-health.json" >/dev/null
code=$(curl --silent --show-error --max-time 10 -H 'Host: aws.platform.example.com' \
  -o "$root/.build/localstack/ingress-root.txt" -w '%{http_code}' http://127.0.0.1:18080/)
[[ $code == 200 || $code == 302 ]] || { echo "FAIL: APISIX root HTTP $code" >&2; exit 1; }
curl --fail --silent --show-error --max-time 10 -H 'Host: aws.platform.example.com' \
  http://127.0.0.1:18080/_localstack/health > "$root/.build/localstack/ingress-health.json"
jq -e '.services | [.s3,.ec2,.iam,.dynamodb] | all(.=="running")' "$root/.build/localstack/ingress-health.json" >/dev/null
echo "PASS: restricted LocalStack; four signed AWS API calls HTTP 200; services running; APISIX HTTP $code"
