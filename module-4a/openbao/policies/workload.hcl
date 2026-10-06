# CSI application identity: read its own database role and one KV-v2 key only.
path "database/creds/vcloud-app-readonly" { capabilities = ["read"] }
path "kv/data/vcloud/api" {
  capabilities = ["read"]
  denied_parameters = { "version" = [] }
}
path "auth/token/lookup-self" { capabilities = ["read"] }
path "auth/token/renew-self" { capabilities = ["update"] }
path "auth/token/revoke-self" { capabilities = ["update"] }
