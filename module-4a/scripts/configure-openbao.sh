#!/usr/bin/env bash
# Reconcile public engine/auth/role configuration; never initialize/unseal a server.
# No live change occurs without --apply. Supply short-lived admin token on descriptor 3,
# initial manager password on 4 (only for a new connection), optional API key on 5.
set +x
set -Eeuo pipefail
script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
# shellcheck source=module-4a/scripts/lib.sh
source "$script_dir/lib.sh"
module_dir=$(cd -- "$script_dir/.." && pwd)
bao_address='https://openbao.platform-services.svc.cluster.local:8200'
pg_host='vcloud-postgres-rw.platform-services.svc.cluster.local'
bao_ca='' pg_ca='' scratch_parent=/dev/shm token_fd=3 apply=false rotate_api_key=false api_key_fd=''
while (($#)); do
  case $1 in
    --apply) apply=true; shift;;
    --plan) shift;;
    --bao-address) bao_address=${2:?}; shift 2;;
    --bao-ca) bao_ca=${2:?}; shift 2;;
    --pg-ca) pg_ca=${2:?}; shift 2;;
    --scratch-dir) scratch_parent=${2:?}; shift 2;;
    --token-fd) token_fd=${2:?}; shift 2;;
    --api-key-fd) api_key_fd=${2:?}; shift 2;;
    --rotate-api-key) rotate_api_key=true; shift;;
    *) printf 'Unsupported option\n' >&2; exit 2;;
  esac
done
if [[ $apply == false ]]; then
  printf '%s\n' 'PLAN: ensure database/, kv/ (v2), auth/kubernetes/; configure KV CAS and Kubernetes reviewer.' \
    'PLAN: install bounded workload/validation policies and exact namespace/SA/audience roles.' \
    'PLAN: register a new PostgreSQL connection with descriptor-4 password; rotate its management credential through the plugin.' \
    'PLAN: reconcile both database roles; optionally write a static API key using versioned CAS.'
  exit 0
fi
vcloud_begin
finish() { local status=$?; trap - EXIT; vcloud_remove_temp; exit "$status"; }
trap finish EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
vcloud_read_token

vcloud_http GET sys/mounts '' "$VCLOUD_TEMP/mounts.json" 200 || exit 1
for name in database kv; do
  if jq -e --arg key "$name/" '.data | has($key)' "$VCLOUD_TEMP/mounts.json" >/dev/null; then
    jq -e --arg key "$name/" --arg kind "$([[ $name == kv ]] && printf kv || printf database)" \
      '.data[$key].type == $kind and (if $kind == "kv" then .data[$key].options.version == "2" else true end)' \
      "$VCLOUD_TEMP/mounts.json" >/dev/null || vcloud_die 'Existing backend type/version differs; refusing remount'
  else
    vcloud_http POST "sys/mounts/$name" "$module_dir/openbao/$name-mount.json" "$VCLOUD_TEMP/write.json" 204 || exit 1
  fi
done
vcloud_http POST kv/config "$module_dir/openbao/kv-config.json" "$VCLOUD_TEMP/write.json" 204 || exit 1
vcloud_http GET sys/auth '' "$VCLOUD_TEMP/auth.json" 200 || exit 1
if jq -e '.data | has("kubernetes/")' "$VCLOUD_TEMP/auth.json" >/dev/null; then
  jq -e '.data["kubernetes/"].type == "kubernetes"' "$VCLOUD_TEMP/auth.json" >/dev/null || vcloud_die 'Existing auth mount has a different type'
else
  vcloud_http POST sys/auth/kubernetes "$module_dir/openbao/kubernetes-mount.json" "$VCLOUD_TEMP/write.json" 204 || exit 1
fi
vcloud_http POST auth/kubernetes/config "$module_dir/openbao/kubernetes-config.json" "$VCLOUD_TEMP/write.json" 204 || exit 1
for pair in 'workload:vcloud-secrets-workload' 'validation:vcloud-secrets-validation'; do
  source_name=${pair%%:*} policy_name=${pair##*:}
  jq -n --rawfile policy "$module_dir/openbao/policies/$source_name.hcl" '{policy:$policy}' >"$VCLOUD_TEMP/policy.json"
  vcloud_http POST "sys/policies/acl/$policy_name" "$VCLOUD_TEMP/policy.json" "$VCLOUD_TEMP/write.json" 204 || exit 1
done
for role in vcloud-csi-client vcloud-validation; do
  vcloud_http POST "auth/kubernetes/role/$role" "$module_dir/openbao/kubernetes-role-$role.json" "$VCLOUD_TEMP/write.json" 204 || exit 1
done

# Never overwrite a connection's rotated password on a repeated configuration run.
vcloud_http GET database/config/vcloud-postgres '' "$VCLOUD_TEMP/connection.json" '200|404' || exit 1
if [[ $VCLOUD_HTTP_STATUS == 404 ]]; then
  manager_password=''
  IFS= read -r manager_password <&4 || [[ -n $manager_password ]] || vcloud_die 'Descriptor 4 must supply the initial manager password'
  [[ -n $manager_password && $manager_password != *$'\r'* ]] || vcloud_die 'Invalid initial manager password'
  printf '%s' "$manager_password" >"$VCLOUD_TEMP/initial-password"
  unset manager_password
  jq --rawfile password "$VCLOUD_TEMP/initial-password" '. + {password:$password}' \
    "$module_dir/openbao/database-connection.json" >"$VCLOUD_TEMP/register.json"
  vcloud_http POST database/config/vcloud-postgres "$VCLOUD_TEMP/register.json" "$VCLOUD_TEMP/write.json" 204 || exit 1
else
  jq -e --slurpfile wanted "$module_dir/openbao/database-connection.json" \
    '.data.plugin_name == $wanted[0].plugin_name and .data.connection_details.username == $wanted[0].username and
     .data.connection_details.connection_url == $wanted[0].connection_url and
     .data.connection_details.password_authentication == "scram-sha-256" and
     .data.connection_details.username_template == $wanted[0].username_template and
     (.data.allowed_roles|sort) == ($wanted[0].allowed_roles|sort)' \
    "$VCLOUD_TEMP/connection.json" >/dev/null || vcloud_die 'Existing PostgreSQL connection identity differs'
fi
# Also handles an interrupted first registration whose initial rotation failed.
# Existing encrypted connection credentials are retained; descriptor 4 is never
# used to overwrite a connection that OpenBao already manages.
vcloud_http POST database/rotate-root/vcloud-postgres '' "$VCLOUD_TEMP/write.json" 204 || exit 1
for role in vcloud-app-readonly vcloud-validation; do
  vcloud_http POST "database/roles/$role" "$module_dir/openbao/database-role-$role.json" "$VCLOUD_TEMP/write.json" 204 || exit 1
done
if [[ -n $api_key_fd ]]; then
  [[ $api_key_fd =~ ^[5-9]$ ]] || vcloud_die 'API-key descriptor must be 5..9'
  vcloud_http GET kv/metadata/vcloud/api '' "$VCLOUD_TEMP/metadata.json" '200|404' || exit 1
  if [[ $VCLOUD_HTTP_STATUS == 404 || $rotate_api_key == true ]]; then
    version=0
    if [[ $VCLOUD_HTTP_STATUS == 200 ]]; then version=$(jq -er '.data.current_version' "$VCLOUD_TEMP/metadata.json"); fi
    api_key=''
    IFS= read -r api_key <&"$api_key_fd" || [[ -n $api_key ]] || vcloud_die 'Empty API-key descriptor'
    printf '%s' "$api_key" >"$VCLOUD_TEMP/api-key"
    unset api_key
    jq -n --rawfile key "$VCLOUD_TEMP/api-key" --argjson version "$version" \
      '{options:{cas:$version},data:{api_key:$key}}' >"$VCLOUD_TEMP/api.json"
    vcloud_http POST kv/data/vcloud/api "$VCLOUD_TEMP/api.json" "$VCLOUD_TEMP/write.json" 200 || exit 1
  fi
fi
printf 'PASS: OpenBao backend/auth configuration reconciled; credentials redacted\n'
