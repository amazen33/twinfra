#!/usr/bin/env bash
# Shared transport for Linux validation/configuration. Callers never export credentials.
set +x
set -Eeuo pipefail
umask 077
# Imported Bash variables retain their export attribute after assignment. Clear it
# before reading credentials so child processes cannot inherit newly read values.
export -n VCLOUD_TOKEN db_user db_password manager_password api_key
# Public caller options; credentials are deliberately absent from these defaults.
bao_address='' bao_ca='' pg_ca='' pg_host='' pg_port=5432 pg_database=vcloud
scratch_parent=/dev/shm token_fd=3

vcloud_die() { printf 'FAIL: %s\n' "$1" >&2; exit 1; }

vcloud_begin() {
  for tool in curl jq psql findmnt mktemp stat; do
    command -v "$tool" >/dev/null || vcloud_die "Missing required tool: $tool"
  done
  [[ ${BAO_TOKEN+x}${VAULT_TOKEN+x}${PGPASSWORD+x} == '' ]] ||
    vcloud_die 'Supply credentials through protected file descriptors, not environment variables'
  [[ $bao_address =~ ^https://[A-Za-z0-9][A-Za-z0-9.-]*(:[0-9]{1,5})?$ ]] || vcloud_die 'OpenBao requires an HTTPS DNS address without userinfo, path or query'
  [[ -r $bao_ca && -r $pg_ca ]] || vcloud_die 'Readable OpenBao and PostgreSQL CA certificates are required'
  [[ $pg_host =~ ^[A-Za-z0-9][A-Za-z0-9.-]*$ && $pg_port =~ ^[0-9]{1,5}$ && $pg_database == vcloud ]] ||
    vcloud_die 'Use the vcloud database and a valid PostgreSQL DNS host/port'
  (( pg_port >= 1 && pg_port <= 65535 )) || vcloud_die 'Invalid PostgreSQL port'
  [[ -d $scratch_parent && $(findmnt -n -o FSTYPE --target "$scratch_parent") == tmpfs ]] ||
    vcloud_die 'Scratch directory must be Linux tmpfs; disk-backed fallback is prohibited'
  VCLOUD_TEMP=$(mktemp -d "$scratch_parent/vcloud-bao.XXXXXXXX")
  chmod 700 "$VCLOUD_TEMP"
  VCLOUD_TOKEN=''
}

vcloud_read_token() {
  [[ $token_fd =~ ^[3-9]$ ]] || vcloud_die 'Token descriptor must be 3..9'
  IFS= read -r VCLOUD_TOKEN <&"$token_fd" || [[ -n $VCLOUD_TOKEN ]] || vcloud_die 'Empty token descriptor'
  if [[ ! $VCLOUD_TOKEN =~ ^[A-Za-z0-9._=-]+$ ]] || (( ${#VCLOUD_TOKEN} < 20 || ${#VCLOUD_TOKEN} > 4096 )); then
    vcloud_die 'Invalid token or header injection'
  fi
}

vcloud_http() {
  local method=$1 path=$2 payload=$3 destination=$4 expected=$5 code
  local -a command=(curl -q --config - --proto '=https' --tlsv1.2 --cacert "$bao_ca"
    --silent --show-error --connect-timeout 5 --max-time 20 --request "$method"
    --header 'Content-Type: application/json' --output "$destination" --write-out '%{http_code}')
  [[ -z $payload ]] || command+=(--data-binary "@$payload")
  # STDIN carries the token header. Neither argv, environment nor curlrc carries it.
  # Redirects are never followed, so credentials cannot be forwarded to another host.
  if ! code=$({ if [[ -n $VCLOUD_TOKEN ]]; then printf 'header = "X-Vault-Token: %s"\n' "$VCLOUD_TOKEN"; fi; } |
      "${command[@]}" "$bao_address/v1/$path" 2>"$VCLOUD_TEMP/curl.error"); then
    printf 'FAIL: OpenBao transport/TLS request failed\n' >&2
    return 1
  fi
  [[ "|$expected|" == *"|$code|"* ]] || { printf 'FAIL: OpenBao returned HTTP %s (response redacted)\n' "$code" >&2; return 1; }
  # Public response status is consumed by configure-openbao.sh after this call.
  # shellcheck disable=SC2034
  VCLOUD_HTTP_STATUS=$code
  chmod 600 "$destination"
}

vcloud_remove_temp() {
  # The only recursively removed target is the exact directory returned by mktemp.
  [[ ${VCLOUD_TEMP:-} == "$scratch_parent"/vcloud-bao.* && -d $VCLOUD_TEMP && ! -L $VCLOUD_TEMP ]] || return 0
  rm -rf -- "$VCLOUD_TEMP"
  unset VCLOUD_TOKEN
}
