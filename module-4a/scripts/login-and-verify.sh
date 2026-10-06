#!/usr/bin/env bash
# Authenticate a projected Kubernetes JWT without printing a JWT/OpenBao token.
set +x
set -Eeuo pipefail
script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
# shellcheck source=module-4a/scripts/lib.sh
source "$script_dir/lib.sh"
bao_address='https://openbao.platform-services.svc.cluster.local:8200'
pg_host='vcloud-postgres-rw.platform-services.svc.cluster.local'
pg_port=5432 pg_database=vcloud scratch_parent=/dev/shm bao_ca='' pg_ca=''
jwt_file='/run/openbao-identity/jwt'
while (($#)); do
  case $1 in
    --bao-address) bao_address=${2:?}; shift 2;;
    --bao-ca) bao_ca=${2:?}; shift 2;;
    --pg-ca) pg_ca=${2:?}; shift 2;;
    --pg-host) pg_host=${2:?}; shift 2;;
    --pg-port) pg_port=${2:?}; shift 2;;
    --scratch-dir) scratch_parent=${2:?}; shift 2;;
    --jwt-file) jwt_file=${2:?}; shift 2;;
    *) printf 'Unsupported option\n' >&2; exit 2;;
  esac
done
vcloud_begin
finish() {
  local status=$?
  trap - EXIT
  if [[ -n $VCLOUD_TOKEN ]]; then
    if ! vcloud_http POST auth/token/revoke-self '' "$VCLOUD_TEMP/logout.json" 204; then
      printf 'FAIL: validation-token cleanup failed\n' >&2; status=1
    fi
  fi
  vcloud_remove_temp
  exit "$status"
}
trap finish EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
[[ -r $jwt_file ]] || vcloud_die 'A readable short-lived projected JWT is required'
# rawfile puts the JWT in the HTTPS body, never a command argument or environment.
jq -n --rawfile jwt "$jwt_file" '{role:"vcloud-validation",jwt:($jwt|rtrimstr("\n"))}' >"$VCLOUD_TEMP/login.json"
vcloud_http POST auth/kubernetes/login "$VCLOUD_TEMP/login.json" "$VCLOUD_TEMP/login-response.json" 200 || exit 1
VCLOUD_TOKEN=$(jq -r '.auth.client_token // empty' "$VCLOUD_TEMP/login-response.json")
if [[ ! $VCLOUD_TOKEN =~ ^[A-Za-z0-9._=-]+$ ]] || (( ${#VCLOUD_TOKEN} < 20 || ${#VCLOUD_TOKEN} > 4096 )); then
  vcloud_die 'Missing/invalid Kubernetes-auth client token'
fi
bash "$script_dir/verify-rotation.sh" --bao-address "$bao_address" --bao-ca "$bao_ca" --pg-ca "$pg_ca" \
  --pg-host "$pg_host" --pg-port "$pg_port" --scratch-dir "$scratch_parent" --token-fd 3 \
  3< <(printf '%s\n' "$VCLOUD_TOKEN")
