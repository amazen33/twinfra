# Deliberately separate from application leases and static API keys.
path "database/creds/vcloud-validation" { capabilities = ["read"] }
path "sys/leases/revoke/database/creds/vcloud-validation/*" {
  capabilities = ["update"]
  # The API accepts a body lease_id that overrides its URL. Explicitly forbid
  # that override so this path-scoped privilege cannot revoke application leases.
  denied_parameters = { "lease_id" = [] }
  allowed_parameters = { "sync" = [true] }
}
path "auth/token/lookup-self" { capabilities = ["read"] }
path "auth/token/renew-self" { capabilities = ["update"] }
path "auth/token/revoke-self" { capabilities = ["update"] }
