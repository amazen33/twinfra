#!/usr/bin/env bash
# Three real integration steps: issue -> TLS database login -> revoke + reject login.
# Executes only against explicitly configured live endpoints; no secret value is printed.
set +x
set -Eeuo pipefail
script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
# shellcheck source=module-4a/scripts/lib.sh
source "$script_dir/lib.sh"
bao_address='https://openbao.platform-services.svc.cluster.local:8200'
pg_host='vcloud-postgres-rw.platform-services.svc.cluster.local'
pg_port=5432 pg_database=vcloud scratch_parent=/dev/shm token_fd=3 bao_ca='' pg_ca=''
usage() {
  printf '%s\n' 'Usage: verify-rotation.sh --bao-ca FILE --pg-ca FILE [--token-fd 3] [--bao-address https://HOST:8200] [--pg-host HOST] [--scratch-dir /dev/shm]'
}
while (($#)); do
  case $1 in
    --bao-address) bao_address=${2:?}; shift 2;;
    --bao-ca) bao_ca=${2:?}; shift 2;;
    --pg-ca) pg_ca=${2:?}; shift 2;;
    --pg-host) pg_host=${2:?}; shift 2;;
    --pg-port) pg_port=${2:?}; shift 2;;
    --scratch-dir) scratch_parent=${2:?}; shift 2;;
    --token-fd) token_fd=${2:?}; shift 2;;
    --help) usage; exit 0;;
    *) usage >&2; exit 2;;
  esac
done
vcloud_begin
lease_id='' revoked=false
finish() {
  local status=$?
  trap - EXIT
  if [[ -n $lease_id && $revoked == false ]]; then
    if ! vcloud_http POST "sys/leases/revoke/$lease_id" "$VCLOUD_TEMP/revoke.json" "$VCLOUD_TEMP/cleanup.json" 204; then
      printf 'FAIL: cleanup revocation failed; operator review required before the short lease expires\n' >&2
      status=1
    fi
  fi
  vcloud_remove_temp
  exit "$status"
}
trap finish EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
vcloud_read_token
printf '{"sync":true}\n' >"$VCLOUD_TEMP/revoke.json"

# 1. The separate validation role cannot issue/revoke application-role leases.
vcloud_http GET database/creds/vcloud-validation '' "$VCLOUD_TEMP/lease.json" 200 || exit 1
lease_id=$(jq -r '.lease_id // empty' "$VCLOUD_TEMP/lease.json")
[[ $lease_id =~ ^database/creds/vcloud-validation/[A-Za-z0-9._-]+$ ]] ||
  { lease_id=''; vcloud_die 'Invalid lease identity; inspect server audit records'; }
jq -e '.lease_duration | type == "number" and . >= 30 and . <= 300' "$VCLOUD_TEMP/lease.json" >/dev/null || vcloud_die 'Invalid validation lease TTL'
jq -e '.renewable == true and (.data.username | test("^vcloud_dyn_[A-Za-z0-9]{20}$")) and (.data.password | type == "string" and length >= 20 and length <= 128 and test("^[A-Za-z0-9_-]+$"))' \
  "$VCLOUD_TEMP/lease.json" >/dev/null || vcloud_die 'Invalid lease credentials or renewable flag'
db_user=$(jq -r '.data.username' "$VCLOUD_TEMP/lease.json")
db_password=$(jq -r '.data.password' "$VCLOUD_TEMP/lease.json")
# Restricted characters above need no pgpass escaping. Never use PGPASSWORD or a
# password-bearing URI; the private pgpass stays in verified memory-backed storage.
printf '%s:%s:%s:%s:%s\n' "$pg_host" "$pg_port" "$pg_database" "$db_user" "$db_password" >"$VCLOUD_TEMP/pgpass"
chmod 600 "$VCLOUD_TEMP/pgpass"
unset db_password
printf '[1/3] PASS: renewable validation lease issued (values redacted)\n'

psql_command=(env -u PGPASSWORD -u PGSERVICE -u PGOPTIONS -u PGHOSTADDR
  "PGPASSFILE=$VCLOUD_TEMP/pgpass" 'PGSSLMODE=verify-full' "PGSSLROOTCERT=$pg_ca"
  'PGCONNECT_TIMEOUT=5' 'PGAPPNAME=vcloud-openbao-lease-test' 'LC_ALL=C'
  psql --no-psqlrc --no-password --host "$pg_host" --port "$pg_port" --dbname "$pg_database"
  --username "$db_user" --set ON_ERROR_STOP=1 --tuples-only --no-align)

# 2. An actual new session must identify the leased role/database and negotiated TLS.
if ! "${psql_command[@]}" --command "SELECT current_user || '|' || current_database() || '|' || ssl::text FROM pg_catalog.pg_stat_ssl WHERE pid = pg_backend_pid();" \
    >"$VCLOUD_TEMP/active.out" 2>"$VCLOUD_TEMP/active.error"; then
  vcloud_die 'Issued credential could not open the expected TLS database session'
fi
[[ $(<"$VCLOUD_TEMP/active.out") == "$db_user|vcloud|true" ]] || vcloud_die 'Database identity/TLS mismatch'
printf '[2/3] PASS: leased identity connected to vcloud using verified TLS\n'

# 3. sync=true must finish revocation; an arbitrary connection failure is not proof.
vcloud_http POST "sys/leases/revoke/$lease_id" "$VCLOUD_TEMP/revoke.json" "$VCLOUD_TEMP/revoked.json" 204 || exit 1
revoked=true
if "${psql_command[@]}" --command 'SELECT 1;' >"$VCLOUD_TEMP/retry.out" 2>"$VCLOUD_TEMP/retry.error"; then
  vcloud_die 'Revoked database credential still authenticates'
fi
if ! grep -Fq "password authentication failed for user \"$db_user\"" "$VCLOUD_TEMP/retry.error" &&
   ! grep -Fq "role \"$db_user\" is not permitted to log in" "$VCLOUD_TEMP/retry.error"; then
  vcloud_die 'Post-revocation failure was not a PostgreSQL authentication rejection; network/TLS failures do not pass'
fi
printf '[3/3] PASS: synchronous revocation completed; a fresh login was rejected\n'
